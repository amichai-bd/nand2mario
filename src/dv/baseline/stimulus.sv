`timescale 1ns/1ps
module baseline_stimulus(input logic clk, output logic reset, enable,
                         output logic [7:0] operand, output logic done,
                         output integer seed);
  reg [31:0] random_state;
  integer i;
  task drive(input bit r, e, input logic [7:0] data);
    @(negedge clk);
    reset = r; enable = e; operand = data;
  endtask
  initial begin
    reset = 1; enable = 0; operand = 0; done = 0;
    seed = 1;
    if ($value$plusargs("seed=%d", seed)) begin end
    random_state = seed ^ 32'h9e3779b9;
    if (random_state == 0) random_state = 1;
    drive(1, 1, 255); // Reset wins over addition.
    drive(0, 1, 1);
    drive(0, 1, 127);
    drive(0, 0, 255); // Disabled input cannot change state.
    drive(0, 1, 128); // Wrap; the broken fixture ignores this high bit.
    drive(0, 1, 0);
    drive(0, 1, 255);
    drive(1, 1, 42);
    drive(0, 1, 42);
    drive(0, 0, 0);
    for (i = 0; i < 64; i = i + 1) begin
      // Fixed xorshift32 sequence: identical across simulators, including seed 0.
      random_state = random_state ^ (random_state << 13);
      random_state = random_state ^ (random_state >> 17);
      random_state = random_state ^ (random_state << 5);
      drive(i == 31, random_state[8], random_state[7:0]);
    end
    @(negedge clk);
    done = 1;
  end
endmodule
