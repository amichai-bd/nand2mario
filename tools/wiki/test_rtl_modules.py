"""The RTL explorer must keep describing the RTL that is actually committed."""

from pathlib import Path
import re
import subprocess
import unittest

from tools.wiki import rtl_explorer as explorer, rtl_modules as rtl


ROOT = Path(__file__).resolve().parents[2]


def page() -> str:
    return (ROOT / explorer.PAGE).read_text(encoding="utf-8")


class GeneratorTests(unittest.TestCase):
    """The parser reads what the sources say, not what a convention suggests."""

    @classmethod
    def setUpClass(cls):
        cls.modules = rtl.composition(ROOT)

    def test_every_module_file_under_src_rtl_is_indexed_once(self):
        sources = rtl.tracked(ROOT, rtl.RTL)
        declared = {path for path in sources
                    if re.search(r"^[ \t]*module\s", (ROOT / path).read_text(encoding="utf-8"), re.M)}
        indexed = {module.path for module in self.modules.values()
                   if module.path.startswith(rtl.RTL)}
        self.assertEqual(declared, indexed)
        self.assertEqual(len(self.modules),
                         len(indexed) + len(rtl.BOARD_SOURCES),
                         "every board source adds exactly one module")

    def test_packages_are_counted_but_never_indexed_as_modules(self):
        names = {name for name, _, _, _ in rtl.packages(ROOT)}
        self.assertTrue(names, "src/rtl/ declares packages")
        self.assertFalse(names & set(self.modules), "a package is not an instantiable block")
        self.assertEqual(len(rtl.tracked(ROOT, rtl.RTL)),
                         len(names) + sum(1 for m in self.modules.values()
                                          if m.path.startswith(rtl.RTL)))

    def test_instances_without_the_u_prefix_are_found(self):
        # n2m_ppu writes `n2m_ppu_registers registers (`. A parser keyed on a
        # `u_` prefix drops eight instances here and says nothing about it.
        inside = {instance.name: instance.module for instance in self.modules["n2m_ppu"].instances}
        self.assertEqual(inside["registers"], "n2m_ppu_registers")
        self.assertEqual(len(inside), 8)
        self.assertFalse([name for name in inside if name.startswith("u_")])

    def test_the_system_instantiates_its_sixteen_owners(self):
        owners = [instance.module for instance in self.modules["n2m_v05_system"].instances]
        self.assertEqual(owners, [
            "n2m_uart", "n2m_boot_copier", "n2m_loader", "n2m_mbc1", "n2m_timebase", "n2m_cpu",
            "n2m_dma", "n2m_memory_stores", "n2m_timer", "n2m_interrupts", "n2m_ppu",
            "n2m_serial", "n2m_apu", "n2m_joypad", "n2m_frame_bridge", "n2m_frame_snapshot"])

    def test_every_instantiated_module_exists(self):
        for name, module in self.modules.items():
            for instance in module.instances:
                self.assertIn(instance.module, self.modules, f"{name} instantiates it")

    def test_register_macros_match_the_macro_file(self):
        # Adding a flop macro to macros.svh without adding it here would leave
        # its registers uncounted, so the page would quietly understate a module.
        defined = set(re.findall(r"^`define\s+(DFF\w*)",
                                 (ROOT / "src/rtl/common/macros.svh").read_text(encoding="utf-8"),
                                 re.M))
        self.assertEqual(defined, set(rtl.REGISTER_MACROS))

    def test_registers_are_counted_where_always_ff_finds_nothing(self):
        structural = self.modules["n2m_uart"]
        source = (ROOT / structural.path).read_text(encoding="utf-8")
        self.assertNotIn("always_ff", source)
        self.assertEqual(structural.registers, 0)
        self.assertEqual(self.modules["n2m_ppu_timing"].registers, 21)
        self.assertEqual(self.modules["n2m_ppu_timing"].register_macros,
                         {"DFF_RST": 1, "DFF_RST_EN": 20})

    def test_simulation_only_registers_and_instances_stay_out_of_the_hardware_count(self):
        bridge = self.modules["n2m_frame_bridge"]
        self.assertEqual((bridge.registers, bridge.simulation_registers), (32, 3))
        ram = self.modules["n2m_intel_ram"]
        views = {instance.module: instance.view for instance in ram.instances}
        self.assertEqual(views["n2m_sim_dual_port_ram"], "simulation")
        self.assertEqual([v.module for v in ram.vendor], ["altsyncram"])

    def test_ports_keep_their_direction_and_width(self):
        ports = {port.name: port for port in self.modules["n2m_v05_system"].ports}
        self.assertEqual((ports["clk_sys"].direction, ports["clk_sys"].kind), ("input", "logic"))
        self.assertEqual((ports["red"].direction, ports["red"].kind), ("output", "logic [3:0]"))
        # green and blue inherit the direction and width of the name before them.
        self.assertEqual((ports["blue"].direction, ports["blue"].kind), ("output", "logic [3:0]"))
        self.assertEqual(ports["retirement"].kind, "n2m_interfaces_pkg::retirement_t")
        self.assertEqual(self.modules["v05_proof"].ports[-1].direction, "output")
        self.assertEqual({p.name: p.kind for p in self.modules["v05_proof"].ports}["DRAM_DQ"],
                         "tri [15:0]")

    def test_present_but_unimplemented_owners_are_the_two_the_sources_declare(self):
        marked = {name for name, module in self.modules.items() if rtl.stub(module)}
        self.assertEqual(marked, {"n2m_apu", "n2m_serial"})

    def test_every_module_maps_to_a_tracked_specification(self):
        for name, module in self.modules.items():
            target = rtl.specification(module)
            self.assertTrue((ROOT / target).is_file(), f"{name} -> {target}")

    def test_block_area_follows_the_measured_weight(self):
        rects = explorer.squarify([100.0, 300.0, 100.0], 0, 0, 200, 100)
        areas = [width * height for _, _, width, height in rects]
        self.assertAlmostEqual(sum(areas), 200 * 100, places=3)
        self.assertAlmostEqual(areas[1] / areas[0], 3.0, places=3)
        self.assertAlmostEqual(explorer.own_weight(self.modules["n2m_ppu_timing"]),
                               200 + explorer.WEIGHT_REGISTER * 21)


class PageTests(unittest.TestCase):
    """The committed page is generated output, and it must stay generated."""

    @classmethod
    def setUpClass(cls):
        cls.modules = rtl.composition(ROOT)
        cls.html = page()

    def test_the_committed_page_equals_the_generator_output(self):
        self.assertEqual(
            self.html, explorer.document(ROOT),
            f"{explorer.PAGE} is stale; regenerate it with "
            "python -m tools.wiki.rtl_explorer")

    def test_every_block_names_a_real_module_and_opens_a_panel(self):
        blocks = set(re.findall(r'data-module="([^"]+)"', self.html))
        panels = re.findall(r'<details id="m-([^"]+)"', self.html)
        self.assertEqual(sorted(panels), sorted(set(panels)), "one panel per module")
        self.assertEqual(set(panels), set(self.modules))
        self.assertEqual(blocks - set(panels), set())
        self.assertEqual(blocks - set(self.modules), set())

    def test_every_panel_carries_its_counts_ports_source_and_specification(self):
        for name, module in self.modules.items():
            panel = self.html.split(f'<details id="m-{name}"', 1)[1].split("</details>", 1)[0]
            self.assertIn(f"{module.lines} lines", panel)
            self.assertIn(f'data-source="{module.path}"', panel)
            self.assertIn(f'data-line="{module.line}"', panel)
            self.assertIn(rtl.specification(module).rsplit("/", 1)[1], panel)
            for port in module.ports:
                self.assertIn(f"</code> {port.name}</li>", panel, f"{name}.{port.name}")

    def test_the_captions_name_every_module_outside_this_repository(self):
        # Four vendor primitives and Quartus-generated components are
        # instantiated but never drawn, because nothing here measures them.
        outside = sorted({instance.module for module in self.modules.values()
                          for instance in module.vendor})
        self.assertEqual(outside, ["altera_modular_adc_control", "altera_onchip_flash",
                                   "altsyncram", "n2m_adc_pll", "n2m_pixel_pll",
                                   "n2m_system_pll"])
        captions = re.findall(r'<p class="diagram-caption">(.*?)</p>', self.html, re.S)
        self.assertEqual(len(captions), 2)
        for name in outside:
            self.assertIn(name, " ".join(captions), "a caption must name it")
            self.assertNotIn(f'data-module="{name}"', self.html, "and must not draw it")

    def test_no_cell_alm_or_fitted_register_figure_is_shown(self):
        # A number beside one of these units would be a synthesis result, and
        # this repository holds none. Naming the units to refuse them is fine.
        text = re.sub(r"<[^>]+>", " ", self.html)
        units = r"(?:ALMs?|cells?|logic elements?|LUTs?|LEs?|flip-?flops?)"
        for claim in (rf"\d[\d,]*\s*{units}\b", rf"\b{units}\s*[:=]\s*\d[\d,]*",
                      r"utilis|utiliz|fit report says"):
            found = re.findall(claim, text, re.I)
            self.assertEqual(found, [], f"{claim} would be an unmeasured figure")
        self.assertIn("No cell, ALM or fitted-register figure", self.html)
        self.assertIn("lines + 4 × register macros", self.html)

    def test_both_boards_are_named_without_retiring_either(self):
        self.assertIn("10M50DAF484C7G", self.html)
        self.assertIn("5CSEBA6U23I7", self.html)
        self.assertIn("DE10-Nano", self.html)
        for retired in ("legacy", "superseded", "retired", "deprecated"):
            self.assertNotIn(retired, self.html.lower())

    def test_the_library_index_lists_the_explorer(self):
        readme = (ROOT / "wiki/presentations/README.md").read_text(encoding="utf-8")
        self.assertIn("rtl-explorer.html", readme)

    def test_the_page_loads_only_tracked_runtime_assets(self):
        for asset in ("../../tools/wiki/assets/presentation.css",
                      "../../tools/wiki/assets/presentation.js",
                      "assets/rtl-explorer.css", "assets/rtl-explorer.js"):
            self.assertIn(asset, self.html)
        for tracked in (explorer.STYLESHEET, explorer.SCRIPT):
            self.assertTrue((ROOT / tracked).is_file())
        listed = subprocess.check_output(["git", "ls-files", "-z", "wiki/presentations"],
                                         cwd=ROOT).decode().split("\0")
        for tracked in (explorer.PAGE, explorer.STYLESHEET, explorer.SCRIPT):
            self.assertIn(tracked, listed, "stage the page and its assets before checking")


if __name__ == "__main__":
    unittest.main()
