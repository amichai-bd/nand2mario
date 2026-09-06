import unittest
from check_sv_style import legacy_declarations, violations


class DeclarationStyleTests(unittest.TestCase):
    def test_rejected_declarations(self):
        for source in ["logic q = 0;", "wire [3:0] d = x;", "output\n logic q = 1,", "logic a, b = 0;", "longint unsigned n=0;", 'string mode="normal";', "initial begin int i=0; end", "for (int i=0; i<3; i++) begin end", "for (genvar i=0; i<3; i++) begin end", "logic NAME``_history=0;", "typedef logic [7:0] byte_t; byte_t x=0;", "typedef struct packed {logic a;} pair_t; pair_t p=0;", "typedef union packed {logic a; bit b;} pair_t; pair_t p=0;", "typedef logic array_t[WIDTH]; array_t a=0;", "logic [7:0] x [2] = '{0,0};"]:
            with self.subTest(source=source):
                self.assertTrue(violations(source))

    def test_separate_assignments_and_constants(self):
        for source in ["logic q; initial q=0;", "wire d; assign d=x;", "parameter logic [3:0] X=0;", "localparam integer N=2;", "typedef enum logic [1:0] {A=0,B=1} state_t; state_t state;", "int i; for(i=0;i<3;i++) begin end", "genvar i; for(i=0;i<3;i++) begin end", 'logic q; // logic q=0;\ninitial $display("logic x=0;");', "/* wire d=x; */ logic q;", "function automatic logic [3:0] f(input logic a); f = a; endfunction"]:
            with self.subTest(source=source):
                self.assertEqual(violations(source), [])

    def test_logic_signal_types(self):
        for source in ["wire q;", "reg [7:0] q;", "input wire logic q;",
                       "module m(output wire q); endmodule", "wire [1:0] bank [0:2];"]:
            with self.subTest(source=source):
                self.assertTrue(legacy_declarations(source))
        for source in ["logic q; assign q = a;", "input var logic q;",
                       "output logic [7:0] q;", "`default_nettype none\nlogic q;\n`default_nettype wire",
                       '// wire q;\n/* reg q; */ initial $display("wire reg");',
                       "int count; string mode; localparam logic [7:0] LIMIT = 8'hff;"]:
            with self.subTest(source=source):
                self.assertEqual(legacy_declarations(source), [])
        self.assertEqual(legacy_declarations('`default_nettype wire\nwire q;'), [2])

    def test_both_style_rules(self):
        for source in ["logic q; assign q = d;", "logic q; initial q = 0;"]:
            self.assertFalse(legacy_declarations(source))
            self.assertFalse(violations(source))
        self.assertTrue(legacy_declarations("wire q = d;"))
        self.assertTrue(violations("wire q = d;"))
        self.assertFalse(legacy_declarations("logic q = d;"))
        self.assertTrue(violations("logic q = d;"))
        self.assertTrue(legacy_declarations("reg q; initial q = 0;"))
        self.assertFalse(violations("reg q; initial q = 0;"))

    def test_line_numbers(self):
        self.assertEqual(violations('// comment\nlogic a;\nlogic b = 0;'), [3])


if __name__ == '__main__':
    unittest.main()
