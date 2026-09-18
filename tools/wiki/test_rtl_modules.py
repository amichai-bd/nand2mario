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

    def test_every_macro_that_creates_a_clocked_process_is_counted(self):
        # A flop macro added under any name would otherwise leave its registers
        # uncounted with every check green. Matching on the macro body rather
        # than on a DFF prefix is what closes that: the guard covers every
        # `define in every tracked src/rtl/ source, not one naming convention.
        # It does not reach a macro defined outside src/rtl/, or flops written
        # as a bare always_ff, which Module.raw_processes reports instead.
        creating = set()
        for path in subprocess.check_output(["git", "ls-files", "-z", "src/rtl"],
                                            cwd=ROOT).decode().split("\0"):
            if not path.endswith((".sv", ".svh")):
                continue
            text = (ROOT / path).read_text(encoding="utf-8")
            for match in re.finditer(r"^`define\s+(\w+)", text, re.M):
                body, index = [], text.index("\n", match.end()) if "\n" in text[match.end():] else len(text)
                line = text[match.end():index]
                body.append(line)
                while line.rstrip().endswith("\\"):
                    following = text.index("\n", index + 1) if "\n" in text[index + 1:] else len(text)
                    line = text[index + 1:following]
                    body.append(line)
                    index = following
                joined = "".join(body)
                if "always_ff" in joined or re.search(r"always\s*@\s*\(\s*posedge", joined):
                    creating.add(match.group(1))
        self.assertEqual(creating, set(rtl.REGISTER_MACROS))

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
        # Six vendor primitives and Quartus-generated components are
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


class ReplicationTests(unittest.TestCase):
    """A generate loop writes one site and elaborates several copies of it."""

    @classmethod
    def setUpClass(cls):
        cls.modules = rtl.composition(ROOT)

    def test_every_generate_loop_in_the_sources_is_found_with_a_literal_bound(self):
        loops = {(path, copies, exact) for path, _, copies, exact in rtl.loop_sites(ROOT)}
        self.assertEqual(loops, {
            ("src/rtl/input/n2m_button_filter.sv", 4, True),
            ("src/rtl/ppu/n2m_ppu_objects.sv", 10, True),
            ("src/rtl/snapshot/n2m_frame_snapshot.sv", 2, True),
            ("src/rtl/uart/n2m_uart_exchange_store.sv", 3, True),
            ("src/rtl/vga/n2m_frame_bridge.sv", 3, True),
        })

    def test_a_replicated_instance_counts_once_per_elaborated_copy(self):
        expected = {
            "n2m_frame_bridge": {("n2m_frame_ram", "u_ram"): 3, ("n2m_vga_scan", "u_scan"): 1},
            "n2m_frame_snapshot": {("n2m_intel_ram", "u_source"): 2,
                                   ("n2m_intel_ram", "u_host"): 2},
            "n2m_uart_exchange_store": {("n2m_intel_ram", "memory"): 3},
        }
        for name, sites in expected.items():
            found = {(instance.module, instance.name): instance.copies
                     for instance in self.modules[name].instances}
            self.assertEqual(found, sites, name)
            self.assertTrue(all(i.exact for i in self.modules[name].instances), name)

    def test_a_replicated_register_macro_counts_once_per_elaborated_copy(self):
        # Ten retained object slots hold three macros each, plus seven outside
        # the loop: 40, not the 13 sites the file writes.
        objects = self.modules["n2m_ppu_objects"]
        self.assertEqual((objects.registers, objects.register_sites), (40, 13))
        self.assertEqual(objects.register_macros, {"DFF_RST": 1, "DFF_RST_EN": 39})
        buttons = self.modules["n2m_button_filter"]
        self.assertEqual((buttons.registers, buttons.register_sites), (10, 4))
        self.assertTrue(objects.registers_exact and buttons.registers_exact)

    def test_an_unreplicated_module_is_unchanged(self):
        timing = self.modules["n2m_ppu_timing"]
        self.assertEqual((timing.registers, timing.register_sites), (21, 21))

    def test_the_diagram_draws_one_block_per_elaborated_copy(self):
        board = explorer.build(self.modules, rtl.BOARD_TOP, rtl.BOARD_TOP, set())
        drawn = {}
        for tile, _, _ in explorer.place(board, 0, 0, 1000, 1000, 0):
            if tile.kind == "module":
                drawn[tile.module] = drawn.get(tile.module, 0) + 1
        self.assertEqual(drawn["n2m_frame_ram"], 3, "three banks, three blocks")
        # The sources write 14 n2m_intel_ram instance sites; three of them sit
        # in a generate loop, so 18 copies elaborate at their own parents. The
        # tree draws 20, because n2m_frame_ram is itself one of three banks and
        # carries its store with it. Replication compounds down the hierarchy.
        sites = [instance for module in self.modules.values()
                 for instance in module.instances if instance.module == "n2m_intel_ram"]
        self.assertEqual((len(sites), sum(s.copies for s in sites)), (14, 18))
        self.assertEqual(drawn["n2m_intel_ram"], 20)
        names = [tile.instance for tile, _, _ in explorer.place(board, 0, 0, 1000, 1000, 0)
                 if tile.module == "n2m_frame_ram" and tile.kind == "module"]
        self.assertEqual(sorted(names), ["banks[0].u_ram", "banks[1].u_ram", "banks[2].u_ram"])

    def test_a_bound_that_is_not_literal_is_a_floor_rather_than_a_guess(self):
        source = ("module t (input var logic clk);\n"
                  "  genvar i;\n"
                  "  generate for (i = 0; i < WIDTH; i = i + 1) begin : g\n"
                  "    n2m_child u_kid (.clk);\n"
                  "    `DFF(q[i], d[i], clk)\n"
                  "  end endgenerate\n"
                  "endmodule\n")
        module = rtl.parse_module("src/rtl/t.sv", source)
        self.assertEqual((module.registers, module.register_sites), (1, 1))
        self.assertFalse(module.registers_exact)
        clean = rtl.blanked(source)
        body, offset = rtl.body_of("t", clean)
        repo, _ = rtl.parse_instances(body, offset, rtl.synthesis_view(source), {"n2m_child"})
        self.assertEqual([(i.module, i.copies, i.exact) for i in repo], [("n2m_child", 1, False)])

    def test_an_instance_array_with_a_literal_range_is_expanded(self):
        source = "module t ();\n  n2m_child u_kids [3:0] (.clk(clk));\nendmodule\n"
        clean = rtl.blanked(source)
        body, offset = rtl.body_of("t", clean)
        repo, _ = rtl.parse_instances(body, offset, rtl.synthesis_view(source), {"n2m_child"})
        self.assertEqual([(i.module, i.copies, i.exact) for i in repo], [("n2m_child", 4, True)])
        widened = source.replace("[3:0]", "[N-1:0]")
        clean = rtl.blanked(widened)
        body, offset = rtl.body_of("t", clean)
        repo, _ = rtl.parse_instances(body, offset, rtl.synthesis_view(widened), {"n2m_child"})
        self.assertEqual([(i.module, i.copies, i.exact) for i in repo], [("n2m_child", 1, False)])

    def test_a_procedural_for_loop_replicates_nothing(self):
        source = ("module t (input var logic clk);\n"
                  "  always_comb begin\n"
                  "    for (int i = 0; i < 8; i = i + 1) sum = sum + i;\n"
                  "  end\n"
                  "  `DFF(q, sum, clk)\n"
                  "endmodule\n")
        module = rtl.parse_module("src/rtl/t.sv", source)
        self.assertEqual((module.registers, module.register_sites), (1, 1))
        self.assertTrue(module.registers_exact)


class ParserGuardTests(unittest.TestCase):
    """Shapes the parser cannot measure must fail loudly, never quietly."""

    def test_a_second_module_in_one_file_is_refused(self):
        source = "module a ();\nendmodule\nmodule b ();\nendmodule\n"
        with self.assertRaises(ValueError) as raised:
            rtl.parse_module("src/rtl/two.sv", source)
        self.assertIn("more than one module", str(raised.exception))

    def test_a_non_ansi_port_header_is_refused(self):
        source = ("module t (a, b);\n  input logic [7:0] a;\n  output logic b;\nendmodule\n")
        with self.assertRaises(ValueError) as raised:
            rtl.parse_module("src/rtl/legacy.sv", source)
        self.assertIn("non-ANSI port header", str(raised.exception))

    def test_a_module_with_no_ports_is_not_mistaken_for_one(self):
        self.assertEqual(rtl.parse_module("src/rtl/t.sv", "module t ();\nendmodule\n").ports, [])


if __name__ == "__main__":
    unittest.main()
