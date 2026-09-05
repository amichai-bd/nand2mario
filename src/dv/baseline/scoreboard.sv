`timescale 1ns/1ps
module baseline_scoreboard(input logic strobe, reset, enable,
                           input logic [7:0] operand, actual,
                           input integer cycle, seed,
                           output integer checked);
  integer prior = 0;
  integer expected, trace_file;
  baseline_reference reference_model(prior, reset, enable, operand, expected);
  initial begin
    checked = 0;
    trace_file = $fopen("transactions.csv", "w");
    if (!trace_file) $fatal(1, "BASELINE_TRACE_OPEN");
    $fdisplay(trace_file, "seed,cycle,reset,enable,operand,expected,actual");
  end
  always @(strobe) if (cycle > 0) begin
    $fdisplay(trace_file, "%0d,%0d,%0d,%0d,%0d,%0d,%0d", seed, cycle, reset, enable, operand, expected, actual);
    $fflush(trace_file);
    // Directed literal checkpoints independently sanity-check the reference.
    if ((cycle == 4 && expected != 128) || (cycle == 6 && expected != 0))
      $fatal(1, "BASELINE_ORACLE cycle=%0d expected_checkpoint=128_or_0 actual=%0d seed=%0d", cycle, expected, seed);
    if (actual !== expected[7:0])
      $fatal(1, "BASELINE_MISMATCH cycle=%0d expected=%0d actual=%0d seed=%0d", cycle, expected, actual, seed);
    prior <= expected;
    checked = checked + 1;
  end
endmodule
