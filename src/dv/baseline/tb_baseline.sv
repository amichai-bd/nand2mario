`timescale 1ns/1ps
module tb_baseline;
  logic clk;
  always #5 clk = ~clk;
  logic reset, enable, done, sampled_reset, sampled_enable, strobe;
  logic [7:0] operand, value, sampled_operand, actual, coverage_bits;
  integer seed, cycle, checked, coverage_file;
  baseline_stimulus stimulus(clk, reset, enable, operand, done, seed);
  baseline_fixture dut(clk, reset, enable, operand, value);
  baseline_monitor monitor(clk, reset, enable, operand, value,
                           sampled_reset, sampled_enable, sampled_operand, actual, strobe, cycle);
  baseline_scoreboard scoreboard(strobe, sampled_reset, sampled_enable, sampled_operand, actual, cycle, seed, checked);
  baseline_assertions assertions(strobe, sampled_reset, sampled_enable, actual, cycle, seed);
  baseline_coverage coverage_model(strobe, sampled_reset, sampled_enable, sampled_operand, actual, cycle, coverage_bits);
  initial begin
    clk = 0;
    $dumpfile("baseline.vcd");
    $dumpvars(0, tb_baseline);
    wait(done);
    #2;
    coverage_file = $fopen("coverage/bins.txt", "w");
    if (!coverage_file) $fatal(1, "BASELINE_COVERAGE_OPEN");
    $fdisplay(coverage_file, "seed=%0d cycles=%0d checked=%0d bins=%02h", seed, cycle, checked, coverage_bits);
    $fclose(coverage_file);
    if (checked != 75 || coverage_bits !== 8'hff)
      $fatal(1, "BASELINE_COVERAGE expected=75/ff actual=%0d/%02h seed=%0d", checked, coverage_bits, seed);
    $display("PASS baseline transactions=75 bins=ff seed=%0d", seed);
    $finish;
  end
  initial begin
    #1000;
    $fatal(1, "BASELINE_TIMEOUT expected=completion_before_1000ns actual_cycle=%0d seed=%0d", cycle, seed);
  end
endmodule
