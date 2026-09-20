"""Original fit fragments check rejection of broken storage evidence."""
import unittest
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m.fpga_memory_stores import verify_netlist, verify_rows, verify, FIT_ENCODING

# Quartus writes the junction temperature rows with a degree sign, so a real fit
# report is not ASCII; the fixture carries one byte of it.
FIT_PROLOGUE = "; Low Junction Temperature ; 0 \N{DEGREE SIGN}C ;\n"


def fixture(init_files=None):
    """Netlist atoms of the seven stores; a named owner carries its power-up image.

    Quartus states either the power-up attribute or the initialization, so an
    initialized owner's atoms drop power_up_uninitialized and carry the file, its
    layout and the mem_init words.
    """
    init_files = init_files or {}
    chunks = []
    for owner, depth, starts in (("rom", 65536, list(range(8)) * 8),
                                 ("wram", 8192, range(8)), ("vram", 8192, range(8)),
                                 ("hram", 127, [0]), ("oam_low", 80, [0]),
                                 ("oam_high", 80, [0]), ("wave_ram", 16, [0])):
        for index, bit in enumerate(starts):
            name = f"{owner}|ram|auto_generated|ram_block{index}"
            ports = {"clk0": r"\clk_sys~inputclkctrl_outclk", "clk1": "gnd",
                     "clr0": "gnd", "clr1": "gnd", "portbwe": "gnd",
                     "portabyteenamasks": "1'b1", "portbbyteenamasks": "1'b1",
                     "portaaddrstall": "gnd", "portbaddrstall": "gnd"}
            chunks.append(f"fiftyfivenm_ram_block \\{name} (" + ",".join(f".{key}({value})" for key, value in ports.items()) + ");")
            params = {"operation_mode": "bidir_dual_port", "ram_block_type": "M9K",
                      "mixed_port_feed_through_mode": "old",
                      "port_b_address_clock": "clock0", "port_b_read_enable_clock": "clock0"}
            if owner in init_files:
                params.update({"init_file": init_files[owner], "init_file_layout": "port_a"})
            else:
                params["power_up_uninitialized"] = "true"
            for port in ("a", "b"):
                params.update({f"port_{port}_logical_ram_depth": str(depth), f"port_{port}_logical_ram_width": "8",
                               f"port_{port}_data_out_clock": "none", f"port_{port}_address_clear": "none",
                               f"port_{port}_data_out_clear": "none", f"port_{port}_read_during_write_mode": "new_data_with_nbe_read",
                               f"port_{port}_data_width": "1" if depth >= 8192 else "18",
                               f"port_{port}_first_address": "0", f"port_{port}_first_bit_number": str(bit),
                               f"port_{port}_last_address": "8191" if depth >= 8192 else ("15" if depth == 16 else "127")})
            chunks += [f'defparam \\{name} .{key} = "{value}";' for key, value in params.items()]
            if owner in init_files:
                chunks += [f"defparam \\{name} .mem_init{word} = 2048'h{'0' * 512};" for word in range(4)]
    return "\n".join(chunks)


class StoreFitTests(unittest.TestCase):
    def test_logical_rows_and_missing_capacity(self):
        lines = []
        for owner, depth, blocks in (("rom", 65536, 64), ("wram", 8192, 8), ("vram", 8192, 8),
                                     ("hram", 127, 1), ("oam_low", 80, 1), ("oam_high", 80, 1), ("wave_ram", 16, 1)):
            fields = [f"n2m_intel_ram:{owner}|altsyncram:ram|ALTSYNCRAM", "M9K", "True Dual Port", "Single Clock",
                      str(depth), "8", str(depth), "8", "yes", "no", "yes", "no", str(depth * 8),
                      str(depth), "8", str(depth), "8", str(depth * 8), str(blocks), "None", "location",
                      "Old data", "New data with NBE Read", "New data with NBE Read"]
            lines.append("; " + " ; ".join(fields) + " ;")
        lines.append("; Total block memory bits ; 657,784 / 1,677,312 ;")
        original = FIT_PROLOGUE + "\n".join(lines)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "output").mkdir()
            (folder / "simulation/questa").mkdir(parents=True)
            (folder / "simulation/questa/design.vo").write_text(fixture())
            report = folder / "output/design.fit.rpt"
            report.write_text(original, encoding=FIT_ENCODING)
            self.assertEqual(len(verify(folder)["physical_atoms"]), 84)
            for changed in (original.replace("657,784", "262,144"),
                            original.replace("yes ; no ; yes ; no", "yes ; yes ; yes ; no", 1),
                            original.replace("64 ; None", "63 ; None", 1),
                            original + "\n" + lines[0], "\n".join(lines[1:])):
                report.write_text(changed, encoding=FIT_ENCODING)
                with self.assertRaises(ValueError):
                    verify(folder)

    def test_exact_inventory_and_mutations(self):
        original = fixture()
        self.assertEqual(len(verify_netlist(original)), 84)
        mutations = [
            original.replace("fiftyfivenm_ram_block", "other_ram_block", 1),
            original.replace("rom|ram|", "unowned|ram|"),
            original.replace("clk_sys~inputclkctrl_outclk", "other_clock", 1),
            original.replace('.port_b_read_enable_clock = "clock0"', '.port_b_read_enable_clock = "clock1"', 1),
            original.replace('.port_b_address_clock = "clock0"', '.port_b_address_clock = "clock1"', 1),
            original.replace('.port_a_data_out_clock = "none"', '.port_a_data_out_clock = "clock0"', 1),
            original.replace('.port_a_logical_ram_depth = "65536"', '.port_a_logical_ram_depth = "8192"', 1),
            original.replace('.port_a_first_bit_number = "0"', '.port_a_first_bit_number = "1"', 1),
            original.replace('.power_up_uninitialized = "true"', '.power_up_uninitialized = "false"', 1),
            original.replace(".portabyteenamasks(1'b1)", ".portabyteenamasks(1'b0)", 1),
            original.replace(".portbwe(gnd)", ".portbwe(vcc)", 1),
            original.replace(".clr0(gnd)", ".clr0(vcc)", 1),
            original + '\ndefparam \\rom|ram|auto_generated|ram_block0 .init_file = "image.mif";',
            original + '\ndefparam \\rom|ram|auto_generated|ram_block0 .ram_block_type = "M9K";',
        ]
        for index, changed in enumerate(mutations):
            with self.subTest(mutation=index), self.assertRaises(ValueError):
                verify_netlist(changed)


class CarriedImageTests(unittest.TestCase):
    """The fitted evidence states which stores power up holding an image."""

    FILES = {"rom": "preload-rom.mif"}

    def test_an_initialized_store_drops_the_power_up_attribute_and_names_its_file(self):
        evidence = verify_netlist(fixture(self.FILES), init_files=self.FILES)
        self.assertEqual(len(evidence), 84)
        initialized = [name for name, item in evidence.items() if "initialization" in item]
        self.assertEqual(len(initialized), 64)
        self.assertTrue(all(name.startswith("rom|ram|") for name in initialized))
        for name in initialized:
            item = evidence[name]
            self.assertNotIn("power_up_uninitialized", item["parameters"])
            self.assertEqual(item["initialization"]["init_file"], "preload-rom.mif")
            self.assertEqual(len([k for k in item["initialization"] if k.startswith("mem_init")]), 4)
        # The other twenty blocks keep the power-up they always had.
        for name, item in evidence.items():
            if "initialization" not in item:
                self.assertEqual(item["parameters"]["power_up_uninitialized"], "true")

    def test_a_declaration_and_the_netlist_must_agree(self):
        # An image declared but not fitted, and one fitted but not declared.
        with self.assertRaises(ValueError):
            verify_netlist(fixture(), init_files=self.FILES)
        with self.assertRaises(ValueError):
            verify_netlist(fixture(self.FILES))
        original = fixture(self.FILES)
        mutations = [
            original.replace('.init_file = "preload-rom.mif"', '.init_file = "other.mif"', 1),
            original.replace('.init_file_layout = "port_a"', '.init_file_layout = "port_b"', 1),
            # A block with no power-up words at all. One missing word of several
            # is the image owner's completeness check, not this inventory's.
            "\n".join(line for line in original.splitlines()
                       if not (line.startswith("defparam \\rom|ram|auto_generated|ram_block0 .mem_init")
                               and " .mem_init" in line)),
            original + '\ndefparam \\rom|ram|auto_generated|ram_block0 .power_up_uninitialized = "true";',
        ]
        for index, changed in enumerate(mutations):
            with self.subTest(mutation=index), self.assertRaises(ValueError):
                verify_netlist(changed, init_files=self.FILES)

    def test_the_fitted_row_names_the_initialization_file(self):
        rows = []
        for owner, depth, blocks in (("rom", 65536, 64), ("wram", 8192, 8), ("vram", 8192, 8),
                                     ("hram", 127, 1), ("oam_low", 80, 1), ("oam_high", 80, 1),
                                     ("wave_ram", 16, 1)):
            initialization = self.FILES.get(owner, "None")
            fields = [f"n2m_intel_ram:{owner}|altsyncram:ram|ALTSYNCRAM", "M9K", "True Dual Port", "Single Clock",
                      str(depth), "8", str(depth), "8", "yes", "no", "yes", "no", str(depth * 8),
                      str(depth), "8", str(depth), "8", str(depth * 8), str(blocks), initialization, "location",
                      "Old data", "New data with NBE Read", "New data with NBE Read"]
            rows.append("; " + " ; ".join(fields) + " ;")
        fit = FIT_PROLOGUE + "\n".join(rows)
        evidence = verify_rows(fit, init_files=self.FILES)
        self.assertEqual(evidence["rom"]["initialization"], "preload-rom.mif")
        self.assertNotIn("initialization", evidence["wram"])
        # The same rows without the declaration, and the uninitialized rows with it.
        with self.assertRaises(ValueError):
            verify_rows(fit)
        with self.assertRaises(ValueError):
            verify_rows(fit.replace("64 ; preload-rom.mif", "64 ; None"), init_files=self.FILES)


class StoreTargetTests(unittest.TestCase):
    def test_registry_assigns_every_store_port(self):
        """Every n2m_memory_stores port is the physical clock or a virtual pin; a new port must be registered."""
        import re
        from n2m import fpga
        root = Path(__file__).resolve().parents[3]
        target = fpga.target_definition(root, "memory-stores")
        source = (root / "src/rtl/memory/n2m_memory_stores.sv").read_text(encoding="utf-8")
        header = source[source.index("module n2m_memory_stores"):source.index(");")]
        ports = re.findall(r"(?m)^\s*(input|output)\s+(?:var\s+)?(\S+)\s+(?:\[[^\]]+\]\s+)?(\w+)\s*,?\s*$", header)
        self.assertEqual(len(ports), 41, "the store port list changed; update this count and the registry")
        assigned = {name.split("[")[0] for name in [*target["pins"], *target["virtual_pins"]]}
        structs = {name.split(".")[0] for name in target["virtual_pins"] if "." in name}
        for _, kind, name in ports:
            self.assertIn(name, structs if kind.startswith("n2m_memory_pkg::memory_oam") else assigned, name)
        self.assertEqual(target["pins"], {"clk_sys": "PIN_P11"})
        sdc = (root / "src/fpga/de10_lite/memory_stores.sdc").read_text(encoding="utf-8")
        budgets = [set(match.split()) for match in re.findall(r"set_input_delay .*\[get_ports \{([^}]*)\}\]", sdc)]
        self.assertEqual(len(budgets), 2, "one -max and one -min input budget")
        for direction, kind, name in ports:
            if direction != "input" or name == "clk_sys":
                continue
            declaration = header[:header.index(" " + name)].rsplit("\n", 1)[-1]
            token = name + ("*" if kind.startswith("n2m_memory_pkg::") or "[" in declaration else "")
            for budget in budgets:
                self.assertIn(token, budget, name)
