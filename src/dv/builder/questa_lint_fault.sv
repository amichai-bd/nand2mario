// Deliberate Questa compile-gate fault, compiled only under `lint questa
// --inject-fault`. An initial writer beside always_ff is legal to Verilator and
// rejected by vopt (vopt-7061), so the gate must FAIL naming this file.
`timescale 1ns/1ps
module questa_lint_fault (
    input  logic clk,
    output logic q
);
    initial q = 1'b0;
    always_ff @(posedge clk) q <= ~q;
endmodule
