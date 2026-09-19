"""The accepted-vendor-source record: what it compares, records and refuses.

Every installation here is an original host-test tree and every digest is of
original bytes; no vendor source is read or copied. The tracked ledger is only
read, never written, because every test points `ledger_path` at its own file.
"""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import vendor_support
from n2m import fpga_pll_cyclonev, vendor_sources
from n2m.records import file_hash, read_json

ROOT = Path(__file__).resolve().parents[3]
MODEL = "quartus/eda/sim_lib/altera_mf.v"


class LayoutTests(unittest.TestCase):
    """The installation names its own platform, so no host setting can disagree."""

    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="quartus layout ")))

    def test_each_layout_names_its_platform_and_executables(self):
        for platform, bin_name in (("windows", "quartus/bin64"), ("linux", "quartus/bin")):
            with self.subTest(platform=platform):
                root = vendor_support.installation(self.root / platform, platform=platform)
                self.assertEqual(vendor_sources.platform_name(root), platform)
                self.assertEqual(vendor_sources.executables(root), root / bin_name)
                self.assertEqual(vendor_sources.quartus_release(root), "0.0 host-test")
                # Any directory inside the installation resolves to the same root.
                inside = root / "quartus/eda/sim_lib"
                inside.mkdir(parents=True)
                self.assertEqual(vendor_sources.installation(inside), root)

    def test_no_layout_and_both_layouts_are_refused(self):
        bare = self.root / "bare"
        bare.mkdir()
        with self.assertRaisesRegex(ValueError, "not inside a recognized Quartus installation"):
            vendor_sources.installation(bare)
        both = self.root / "both"
        for folder in vendor_sources.LAYOUTS.values():
            (both / folder).mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "unrecognized Quartus installation layout"):
            vendor_sources.platform_name(both)

    def test_an_installation_that_states_no_release_is_recorded_as_none(self):
        root = vendor_support.installation(self.root / "silent", release=None)
        self.assertIsNone(vendor_sources.quartus_release(root))


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="vendor record ")))
        self.root = vendor_support.installation(self.temp / "installation")
        self.model = self.root / MODEL
        self.model.parent.mkdir(parents=True)
        self.model.write_text("// Original host-test bytes, not a vendor model.\n")
        self.other = self.root / "quartus/eda/sim_lib/other.v"
        self.other.write_text("// A second original host-test file.\n")
        self.ledger = vendor_support.ledger(self, self.temp / "ledger.json")
        self.bin = self.root / "quartus/bin"

    def check(self, *names):
        paths = {"model": self.model, "other": self.other}
        return vendor_sources.check(self.bin, {name: paths[name] for name in names or paths})

    def test_a_first_sighting_records_and_says_so(self):
        result = self.check("model")
        self.assertEqual(result["model"], {"path": str(self.model), "sha256": file_hash(self.model),
                                          "source": MODEL, "installation": "linux",
                                          "accepted": "recorded"})
        entry = read_json(self.ledger)["installations"]["linux"]
        self.assertEqual(entry["sources"], {MODEL: file_hash(self.model)})
        self.assertEqual(entry["quartus"], "0.0 host-test")
        self.assertEqual(self.check("model")["model"]["accepted"], "unchanged")

    def test_a_changed_source_refuses_and_names_the_change(self):
        self.check("model")
        accepted = file_hash(self.model)
        self.model.write_text("// Different original host-test bytes.\n")
        with self.assertRaises(ValueError) as raised:
            self.check("model")
        message = str(raised.exception)
        for part in ("changed since it was accepted", MODEL, "linux", accepted, file_hash(self.model),
                     "vendor accept", vendor_sources.SPEC):
            self.assertIn(part, message)
        self.assertEqual(read_json(self.ledger)["installations"]["linux"]["sources"], {MODEL: accepted})

    def test_the_refusal_names_both_releases_when_they_differ(self):
        self.check("model")
        (self.root / "quartus/version.txt").write_text("[ACDS]\nVersion=9.9 host-test\n")
        self.model.write_text("// Different original host-test bytes.\n")
        with self.assertRaises(ValueError) as raised:
            self.check("model")
        self.assertIn("accepted record was made against Quartus 0.0 host-test", str(raised.exception))
        self.assertIn("states 9.9 host-test", str(raised.exception))

    def test_a_build_records_only_what_is_absent_and_writes_nothing_on_a_refusal(self):
        self.check("model")
        accepted = file_hash(self.model)
        self.model.write_text("// Different original host-test bytes.\n")
        # One new source and one changed source: the refusal wins and the new
        # source is not recorded, so a build never lands a half-checked record.
        with self.assertRaisesRegex(ValueError, "changed since it was accepted"):
            self.check()
        self.assertEqual(read_json(self.ledger)["installations"]["linux"]["sources"], {MODEL: accepted})
        # With the model restored, the new source is added beside the accepted one.
        self.model.write_text("// Original host-test bytes, not a vendor model.\n")
        result = self.check()
        self.assertEqual((result["model"]["accepted"], result["other"]["accepted"]), ("unchanged", "recorded"))
        self.assertEqual(read_json(self.ledger)["installations"]["linux"]["sources"],
                         {MODEL: accepted, "quartus/eda/sim_lib/other.v": file_hash(self.other)})

    def test_a_source_outside_the_installation_is_refused(self):
        outside = self.temp / "outside.v"
        outside.write_text("// Not inside the installation.\n")
        with self.assertRaisesRegex(ValueError, "outside the Quartus installation"):
            vendor_sources.check(self.bin, {"model": outside})
        with self.assertRaisesRegex(ValueError, "missing installed vendor source"):
            vendor_sources.check(self.bin, {"model": self.root / "absent.v"})

    def test_a_record_lost_to_a_concurrent_write_refuses_the_run(self):
        """The load-modify-save is unlocked, so the read-back is what closes it.

        A writer landing inside that window would otherwise leave the run holding
        bytes the ledger does not accept. Standing in for that writer here proves
        the run refuses instead of proceeding.
        """
        real_save = vendor_sources.save

        def hijacked(ledger):
            ledger["installations"]["linux"]["sources"][MODEL] = "f" * 64
            real_save(ledger)

        with patch.object(vendor_sources, "save", hijacked):
            with self.assertRaisesRegex(ValueError, "changed while this run was recording it"):
                self.check("model")
        self.assertEqual(read_json(self.ledger)["installations"]["linux"]["sources"][MODEL], "f" * 64)

    def test_notices_name_every_first_sighting_once(self):
        result = self.check()
        self.assertEqual(vendor_sources.notices({"tools": {"a": result, "b": result}}),
                         sorted(vendor_sources.NOTICE.format(installation="linux", source=entry["source"],
                                                             sha256=entry["sha256"])
                                for entry in result.values()))
        self.assertEqual(vendor_sources.notices({"tools": self.check()}), [])

    def test_notices_reach_a_descriptor_source_list(self):
        """A simulation descriptor keeps its sources in a list, not a mapping."""
        result = self.check()
        descriptor = {"selection": "intel-memory",
                      "sources": [{"name": entry["source"], **entry} for entry in result.values()]}
        self.assertEqual(vendor_sources.notices(descriptor),
                         sorted(vendor_sources.NOTICE.format(installation="linux", source=entry["source"],
                                                             sha256=entry["sha256"])
                                for entry in result.values()))


class AcceptTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="vendor accept ")))
        self.root = vendor_support.installation(self.temp / "installation")
        self.model = self.root / MODEL
        self.model.parent.mkdir(parents=True)
        self.model.write_text("// Original host-test bytes, not a vendor model.\n")
        self.ledger = vendor_support.ledger(self, self.temp / "ledger.json",
                                            sources={MODEL: "0" * 64})
        self.bin = self.root / "quartus/bin"
        self.reason = "Reviewed against the vendor release notes for this host test."

    def test_acceptance_records_the_change_its_reason_and_the_release(self):
        record = vendor_sources.accept(self.bin, [MODEL], self.reason, today="2026-09-19")
        self.assertEqual(record["changed"], {MODEL: {"from": "0" * 64, "to": file_hash(self.model)}})
        self.assertEqual((record["platform"], record["quartus"]), ("linux", "0.0 host-test"))
        entry = read_json(self.ledger)["installations"]["linux"]
        self.assertEqual(entry["sources"][MODEL], file_hash(self.model))
        self.assertEqual(entry["history"], [{"date": "2026-09-19", "reason": self.reason,
                                             "changed": record["changed"]}])
        self.assertTrue(any("Commit the ledger change" in line for line in record["notices"]))

    def test_a_reason_too_short_to_be_a_record_is_refused(self):
        for reason in ("", "   ", "ok", "fix build", None):
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, "needs a reason"):
                vendor_sources.accept(self.bin, [MODEL], reason)
        self.assertEqual(read_json(self.ledger)["installations"]["linux"]["sources"][MODEL], "0" * 64)

    def test_a_no_op_a_repeat_and_an_unsafe_name_are_refused(self):
        vendor_sources.accept(self.bin, [MODEL], self.reason)
        with self.assertRaisesRegex(ValueError, "already accepted with this digest"):
            vendor_sources.accept(self.bin, [MODEL], self.reason)
        with self.assertRaisesRegex(ValueError, "each named once"):
            vendor_sources.accept(self.bin, [MODEL, MODEL], self.reason)
        with self.assertRaisesRegex(ValueError, "at least one source"):
            vendor_sources.accept(self.bin, [], self.reason)
        for name in ("/etc/passwd", "../outside.v", "quartus/../../escape.v", "C:/vendor/model.v"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "installation-relative path"):
                vendor_sources.accept(self.bin, [name], self.reason)
        with self.assertRaisesRegex(ValueError, "missing installed vendor source"):
            vendor_sources.accept(self.bin, ["quartus/absent.v"], self.reason)
        self.assertEqual(len(read_json(self.ledger)["installations"]["linux"]["history"]), 1)


class AcceptCommandTests(unittest.TestCase):
    """`vendor accept` through the public command, with no build tag and no workspace."""

    def test_the_command_records_the_change_and_reports_it(self):
        temp = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="vendor command ")))
        root = vendor_support.installation(temp / "installation")
        model = root / MODEL
        model.parent.mkdir(parents=True)
        model.write_text("// Original host-test bytes, not a vendor model.\n")
        ledger = vendor_support.ledger(self, temp / "ledger.json", sources={MODEL: "0" * 64})
        from n2m.cli import main
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            self.assertEqual(main(["vendor", "accept", "--quartus-bin", str(root / "quartus/bin"),
                                   "--source", MODEL, "--reason",
                                   "Reviewed against the vendor release notes for this test.",
                                   "--json"], ROOT), 0)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["platform"], "linux")
        self.assertEqual(report["changed"], {MODEL: {"from": "0" * 64, "to": file_hash(model)}})
        self.assertEqual(read_json(ledger)["installations"]["linux"]["sources"][MODEL], file_hash(model))

    def test_the_command_reports_a_refusal_without_writing(self):
        temp = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="vendor command ")))
        root = vendor_support.installation(temp / "installation")
        ledger = vendor_support.ledger(self, temp / "ledger.json", sources={MODEL: "0" * 64})
        from n2m.cli import main
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            self.assertEqual(main(["vendor", "accept", "--quartus-bin", str(root / "quartus/bin"),
                                   "--source", MODEL, "--reason", "too short", "--json"], ROOT), 1)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("needs a reason", report["error"])
        self.assertEqual(read_json(ledger)["installations"]["linux"]["sources"], {MODEL: "0" * 64})


class RequireAcceptedTests(unittest.TestCase):
    """A classifier explaining one file's warnings refuses a record that skipped the ledger."""

    def setUp(self):
        self.entry = vendor_support.accepted("/vendor/altera_mf.v", "a" * 64, MODEL)

    def test_a_complete_record_returns_its_digest(self):
        self.assertEqual(vendor_sources.require_accepted({"model": self.entry}, "model"), {"model": "a" * 64})

    def test_every_incomplete_record_is_refused(self):
        for change in ({"accepted": None}, {"accepted": "assumed"}, {"sha256": "changed"},
                       {"sha256": "A" * 64}, {"source": "/absolute.v"}, {"source": ".."},
                       {"installation": "other"}):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "not an accepted ledger record"):
                vendor_sources.require_accepted({"model": {**self.entry, **change}}, "model")
        for entry in ({}, {"model": None}, {"model": "a" * 64}):
            with self.subTest(entry=entry), self.assertRaisesRegex(ValueError, "not an accepted ledger record"):
                vendor_sources.require_accepted(entry, "model")


class LedgerSchemaTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(self.enterContext(tempfile.TemporaryDirectory())) / "ledger.json"
        vendor_support.ledger(self, self.path, sources={MODEL: "a" * 64})
        self.good = read_json(self.path)

    def write(self, value):
        self.path.write_text(json.dumps(value), encoding="utf-8")

    def test_the_schema_is_checked_on_every_read(self):
        self.assertEqual(vendor_sources.load(), self.good)
        entry = self.good["installations"]["linux"]
        for mutation in ({"schema_version": 2}, {"purpose": ""}, {"installations": []},
                         {"extra": 1}, {"installations": {"solaris": entry}},
                         {"installations": {"linux": {**entry, "sources": {MODEL: "short"}}}},
                         {"installations": {"linux": {**entry, "sources": {"/absolute.v": "a" * 64}}}},
                         {"installations": {"linux": {**entry, "quartus": ""}}},
                         {"installations": {"linux": {**entry, "unknown": 1}}},
                         {"installations": {"linux": {**entry, "history": [{"date": "x", "reason": "y"}]}}},
                         {"installations": {"linux": {**entry, "history": [{"date": "", "reason": "y", "changed": {}}]}}}):
            with self.subTest(mutation=sorted(mutation)):
                self.write({**self.good, **mutation})
                with self.assertRaises(ValueError):
                    vendor_sources.load()
        self.path.unlink()
        with self.assertRaisesRegex(ValueError, "missing accepted vendor source ledger"):
            vendor_sources.load()


class TrackedLedgerTests(unittest.TestCase):
    """The tracked ledger keeps every digest the repository already recorded.

    The Windows entry was seeded from those numbers, so this is the proof that
    separating the record from the pin weakened no check that installation passed.
    """

    def test_the_tracked_ledger_loads_and_keeps_the_recorded_windows_digests(self):
        ledger = vendor_sources.load()
        self.assertEqual(vendor_sources.ledger_path(), ROOT / "tools/n2m/accepted_vendor_sources.json")
        windows = ledger["installations"]["windows"]["sources"]
        dependencies = read_json(ROOT / "tools/n2m/dependencies.json")
        self.assertEqual(windows[MODEL], dependencies["intel_memory"]["sources"]["altera_mf.v"])
        for name, digest in dependencies["intel_adc"]["sources"].items():
            self.assertEqual(windows[name], digest, name)
        # The six On-Chip Flash digests unblocked `flash-proof`, and the constants
        # they came from are gone, so every one is anchored here.
        flash = "ip/altera/altera_onchip_flash/"
        for name, digest in (
                ("altera_onchip_flash/altera_onchip_flash.v",
                 "03a088deb2baaef6b33229b2bf3717d659efceac30043a1243066672195db316"),
                ("altera_onchip_flash/altera_onchip_flash_avmm_data_controller.v",
                 "a87a4f86b581ba3b78fb9189bf6215bf1722bc56757fc5cd30a1853787d8f517"),
                ("altera_onchip_flash/altera_onchip_flash_util.v",
                 "4091b0255ebe2b534f87b6af95ee0d4dda965c975b9a0457c7e6f36d38b2e301"),
                ("rtl/altera_onchip_flash_block.v",
                 "6afaeaf53c8596647ee4e56b7d79193970c79efd7c774584a84b0e444a88dfb1"),
                ("altera_onchip_flash/altera_onchip_flash_hw.tcl",
                 "d4a832155d41eaf776d3fea061e22bc09ffc1050d2e7048c6e2e84c0b914f613"),
                ("altera_onchip_flash/altera_onchip_flash_hw_proc.tcl",
                 "bd6465a1f3cb08e65888ed5a7d5f085b5979bc8073d8878844bd8f422ac29a2c")):
            self.assertEqual(windows[flash + name], digest, name)
        # Exactly the seventeen the repository already recorded; a new seed needs
        # its own review rather than arriving unnoticed.
        self.assertEqual(len(windows), 17)


class CycloneVGeneratorTests(unittest.TestCase):
    """`ip-generate` is resolved per host, and the refusal names what it looked for.

    Windows accepts either spelling because the Windows filename has never been
    observed from this repository; the test states that rather than asserting one.
    """

    def host(self, name):
        return patch.object(fpga_pll_cyclonev, "os", type("os", (), {"name": name}))

    def test_each_host_resolves_the_generator_it_has(self):
        quartus = Path(self.enterContext(tempfile.TemporaryDirectory())) / "quartus"
        folder = quartus / "sopc_builder/bin"
        folder.mkdir(parents=True)
        for host, name in (("posix", "ip-generate"), ("nt", "ip-generate.exe"), ("nt", "ip-generate")):
            with self.subTest(host=host, name=name), self.host(host):
                path = folder / name
                path.write_text("host-test placeholder\n")
                self.assertEqual(fpga_pll_cyclonev.generator(quartus), path)
                path.unlink()

    def test_a_missing_generator_names_every_candidate(self):
        quartus = Path(self.enterContext(tempfile.TemporaryDirectory())) / "quartus"
        (quartus / "sopc_builder/bin").mkdir(parents=True)
        for host, expected, absent in (("posix", ["ip-generate"], "ip-generate.exe"),
                                       ("nt", ["ip-generate.exe", "ip-generate"], None)):
            with self.subTest(host=host), self.host(host):
                with self.assertRaises(ValueError) as raised:
                    fpga_pll_cyclonev.generator(quartus)
                message = str(raised.exception)
                self.assertIn("missing Quartus Altera PLL generator", message)
                for name in expected:
                    self.assertIn(name, message)
                if absent:
                    self.assertNotIn(absent, message)


if __name__ == "__main__":
    unittest.main()
