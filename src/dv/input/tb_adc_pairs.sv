`timescale 1ns/1ps
module tb_adc_pairs;
    logic clk;
    logic reset;
    logic available;
    logic command_valid;
    logic [4:0] command_channel;
    logic command_ready;
    logic response_valid;
    logic [4:0] response_channel;
    logic [11:0] response_data;
    logic pair_valid;
    logic [11:0] pair_x;
    logic [11:0] pair_y;
    logic fresh;
    logic fault;
    logic expect_pair;
    logic [11:0] expected_x;
    logic [11:0] expected_y;
    integer pairs;
    integer commands;
    integer cycles;
    integer i;
    bit corrupt;
    bit wrong_channel;
    n2m_adc_pairs #(.INTERVAL_CYCLES(4), .LIMIT_CYCLES(64)) dut (
        .clk_sys(clk), .reset_sys(reset), .adc_available(available),
        .command_valid(command_valid), .command_channel(command_channel), .command_ready(command_ready),
        .response_valid(response_valid), .response_channel(response_channel), .response_data(response_data),
        .pair_valid(pair_valid), .pair_x(pair_x), .pair_y(pair_y), .fresh(fresh), .protocol_fault(fault)
    );
    initial begin clk = 1'b0; forever #10 clk = !clk; end
    always @(posedge clk) begin
        if (!reset) begin
            cycles = cycles + 1;
            if (command_valid && command_ready) commands = commands + 1;
            if (pair_valid !== expect_pair)
                $fatal(1, "ADC_PAIR_PUBLICATION cycle=%0d expected=%0b actual=%0b", cycles, expect_pair, pair_valid);
            if (pair_valid) begin
                if (pair_x !== expected_x || pair_y !== expected_y)
                    $fatal(1, "ADC_PAIR_DATA cycle=%0d expected=%0d,%0d actual=%0d,%0d", cycles, expected_x, expected_y, pair_x, pair_y);
                pairs = pairs + 1;
            end
        end
    end
    task automatic step;
        @(posedge clk); #1; @(negedge clk);
    endtask
    task automatic restart;
        reset = 1'b1; command_ready = 1'b0; response_valid = 1'b0; expect_pair = 1'b0;
        step(); reset = 1'b0; step();
        if (fresh !== 1'b0 || fault !== 1'b0) $fatal(1, "ADC_PAIR_RESET");
    endtask
    task automatic accept(input logic [4:0] channel);
        integer waited;
        waited = 0;
        while (!command_valid && waited < 8) begin step(); waited = waited + 1; end
        if (!command_valid || command_channel !== channel)
            $fatal(1, "ADC_PAIR_COMMAND expected=%0d actual=%0d valid=%0b", channel, command_channel, command_valid);
        command_ready = 1'b1; step(); command_ready = 1'b0;
    endtask
    task automatic respond(input logic [4:0] channel, input logic [11:0] data);
        response_channel = channel; response_data = data; response_valid = 1'b1;
        step(); response_valid = 1'b0;
    endtask
    task automatic complete_pair(input logic [11:0] x, input logic [11:0] y);
        accept(5'd1); respond(5'd1, x); accept(5'd2);
        expected_x = x; expected_y = y; expect_pair = 1'b1;
        respond(5'd2, corrupt ? 12'd0 : y); expect_pair = 1'b0;
        if (!fresh) $fatal(1, "ADC_PAIR_FRESH_MISSING");
    endtask
    initial begin
        reset = 1'b1; available = 1'b1; command_ready = 1'b0;
        response_valid = 1'b0; response_channel = 5'd0; response_data = 12'd0;
        expect_pair = 1'b0; expected_x = 12'd0; expected_y = 12'd0;
        pairs = 0; commands = 0; cycles = 0;
        corrupt = $test$plusargs("CORRUPT_PAIR"); wrong_channel = $test$plusargs("WRONG_CHANNEL");
        $dumpfile("waves.vcd");
        $dumpvars(0, clk, reset, available, command_valid, command_channel, command_ready,
            response_valid, response_channel, response_data, pair_valid, pair_x, pair_y,
            fresh, fault, expect_pair, expected_x, expected_y);
        @(negedge clk); restart();
        if (wrong_channel) begin
            accept(5'd1); respond(5'd2, 12'd1352);
            $fatal(1, "ADC_PAIR_EXPECTED_PROTOCOL_ASSERTION");
        end
        complete_pair(12'd1000, 12'd2703);

        // A timed-out outstanding X must drain before a new command appears.
        restart(); accept(5'd1);
        repeat (64) step();
        for (i = 0; i < 4; i = i + 1) begin
            if (fresh || command_valid) $fatal(1, "ADC_PAIR_DRAIN_REQUIRED");
            step();
        end
        respond(5'd1, 12'd4095);
        complete_pair(12'd1352, 12'd1352);

        // X completes at elapsed63; Y is accepted on the expiry edge64.
        // That accepted Y remains outstanding even though the pair is discarded.
        restart(); accept(5'd1); repeat (62) step(); respond(5'd1, 12'd17);
        accept(5'd2);
        if (fresh || command_valid) $fatal(1, "ADC_PAIR_EXPIRY_ACCEPT_DRAIN");
        repeat (3) step(); respond(5'd2, 12'd2703);
        if (fresh) $fatal(1, "ADC_PAIR_LATE_Y_REVIVED");
        complete_pair(12'd902, 12'd1802);

        // Availability loss cancels a transaction; no response from the old
        // reset ADC is needed for the new generation to make progress.
        restart(); accept(5'd1); available = 1'b0; step();
        if (fresh || command_valid) $fatal(1, "ADC_PAIR_LOCK_LOSS");
        available = 1'b1; complete_pair(12'd0, 12'd2703);
        if (pairs != 4 || fault) $fatal(1, "ADC_PAIR_COUNT expected=4 actual=%0d fault=%0b", pairs, fault);
        $display("PASS adc pairs pairs=%0d commands=%0d cycles=%0d", pairs, commands, cycles);
        $finish;
    end
    initial begin #100000; $fatal(1, "ADC_PAIR_WATCHDOG"); end
endmodule
