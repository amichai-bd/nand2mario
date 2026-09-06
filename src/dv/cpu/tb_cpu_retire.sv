`timescale 1ns/1ps
`default_nettype none

module tb_cpu_retire;
    logic clk_sys;
    logic reset_sys;
    logic core_reset;
    logic event_valid;
    logic event_interrupt;
    n2m_cpu_pkg::cpu_registers_t registers_after;
    logic [15:0] pc_before;
    logic [15:0] pc_after;
    logic [23:0] fetched_bytes;
    logic [1:0] fetched_length;
    logic ime_after;
    logic ime_delay_after;
    logic halted_after;
    logic stopped_after;
    logic halt_bug_after;
    logic [31:0] epoch;
    logic [63:0] dot_after;
    logic [7:0] ie;
    logic [4:0] iflags;
    logic [7:0] buttons;
    logic retirement_valid;
    n2m_interfaces_pkg::retirement_t retirement;
    logic [383:0] expected;
    integer event_number;
    integer sequence_expected;
    integer checks;
    integer idle_cycle;
    integer trace;
    bit corrupt;

    n2m_cpu_pkg::cpu_retire_capture_t capture;
    assign capture.valid = event_valid;
    assign capture.is_interrupt = event_interrupt;
    assign capture.registers_after = registers_after;
    assign capture.pc_before = pc_before;
    assign capture.pc_after = pc_after;
    assign capture.fetched_bytes = fetched_bytes;
    assign capture.fetched_length = fetched_length;
    assign capture.ime_after = ime_after;
    assign capture.ime_delay_after = ime_delay_after;
    assign capture.halted_after = halted_after;
    assign capture.stopped_after = stopped_after;
    assign capture.halt_bug_after = halt_bug_after;
    assign capture.epoch = epoch;
    assign capture.dot_after = dot_after;

    n2m_cpu_retire dut (.*);

    task automatic edge_cycle;
        clk_sys = 0;
        #5 clk_sys = 1;
        #1;
        #4 clk_sys = 0;
    endtask

    task automatic make_expected;
        // Independent literal ABI byte offsets; no product serialization helper.
        expected = '0;
        expected[0 +: 8] = 1;
        expected[8 +: 8] = event_interrupt ? 1 : 0;
        expected[16 +: 32] = epoch;
        expected[48 +: 64] = 64'(sequence_expected);
        expected[112 +: 64] = dot_after;
        expected[176 +: 16] = pc_before;
        expected[192 +: 16] = pc_after;
        if (!event_interrupt) begin
            expected[208 +: 8] = fetched_bytes[7:0];
            if (fetched_length > 1) expected[216 +: 8] = fetched_bytes[15:8];
            if (fetched_length > 2) expected[224 +: 8] = fetched_bytes[23:16];
            expected[232 +: 8] = {6'b0, fetched_length};
        end
        expected[240 +: 64] = 64'h776655443322f011;
        expected[304 +: 16] = 16'h8899;
        expected[320 +: 8] = {7'b0, ime_after};
        expected[328 +: 8] = {7'b0, ime_delay_after};
        expected[336 +: 8] = {7'b0, halted_after};
        expected[344 +: 8] = {7'b0, stopped_after};
        expected[352 +: 8] = {7'b0, halt_bug_after};
        expected[360 +: 8] = 8'h04;
        expected[368 +: 8] = 8'h15;
        expected[376 +: 8] = 8'hc3;
    endtask

    initial begin
        clk_sys = 0;
        reset_sys = 1;
        core_reset = 0;
        event_valid = 0;
        event_interrupt = 0;
        registers_after = '0;
        registers_after.a = 8'h11;
        registers_after.f = 8'hf0;
        registers_after.b = 8'h22;
        registers_after.c = 8'h33;
        registers_after.d = 8'h44;
        registers_after.e = 8'h55;
        registers_after.h = 8'h66;
        registers_after.l = 8'h77;
        registers_after.sp = 16'h8899;
        pc_before = 16'h1234;
        pc_after = 16'h5678;
        fetched_bytes = 24'h1234c3;
        fetched_length = 3;
        ime_after = 0;
        ime_delay_after = 0;
        halted_after = 0;
        stopped_after = 0;
        halt_bug_after = 0;
        epoch = 32'h01020304;
        dot_after = 64'h0102030405060708;
        ie = 8'ha5;
        iflags = 5'h02;
        buttons = 8'h55;
        checks = 0;
        sequence_expected = 0;
        corrupt = $test$plusargs("corrupt");
        trace = $fopen("retirement-trace.csv", "w");
        if (!trace) $fatal(1, "CPU_RETIRE_TRACE_OPEN");
        $fdisplay(trace, "event,expected,actual");
        $dumpfile("waves/cpu-retire.vcd");
        $dumpvars(0,clk_sys,reset_sys,core_reset,capture,event_valid,event_interrupt,registers_after,
            pc_before,pc_after,fetched_bytes,fetched_length,ime_after,ime_delay_after,halted_after,
            stopped_after,halt_bug_after,epoch,dot_after,ie,iflags,buttons,retirement_valid,
            retirement);
        edge_cycle();
        reset_sys = 0;
        for (event_number = 0; event_number < 5; event_number = event_number + 1) begin
            event_interrupt = event_number == 3;
            fetched_length = 2'((event_number % 3) + 1);
            ime_after = event_number == 1;
            ime_delay_after = event_number == 0;
            halted_after = event_number == 2;
            stopped_after = event_number == 4;
            halt_bug_after = event_number == 2;
            ie = 8'ha5;
            iflags = 5'h02;
            buttons = 8'h55;
            make_expected();
            event_valid = 1;
            edge_cycle();
            if (retirement_valid) $fatal(1, "CPU_RETIRE_EARLY");
            event_valid = 0;
            // Bus-side effects become visible after event capture.
            ie = 8'h04;
            iflags = 5'h15;
            buttons = 8'hc3;
            edge_cycle();
            if (corrupt && event_number == 1) force dut.retirement.opcode = 24'h000001;
            #1;
            $fdisplay(trace, "%0d,%096h,%096h", event_number, expected, retirement);
            if (!retirement_valid || retirement !== expected)
                $fatal(1, "CPU_RETIRE_MISMATCH case=%0d expected=%096h actual=%096h", event_number, expected, retirement);
            sequence_expected = sequence_expected + 1;
            checks = checks + 1;
            for (idle_cycle = 0; idle_cycle < 3; idle_cycle = idle_cycle + 1) begin
                edge_cycle();
                if (retirement_valid) $fatal(1, "CPU_RETIRE_DUPLICATE");
            end
            dot_after = dot_after + 64'd4;
        end
        // Reset between capture and publication cancels the old event.
        event_valid = 1;
        edge_cycle();
        event_valid = 0;
        core_reset = 1;
        edge_cycle();
        if (retirement_valid) $fatal(1, "CPU_RETIRE_STALE_AFTER_RESET");
        core_reset = 0;
        epoch = epoch + 1;
        sequence_expected = 0;
        event_interrupt = 0;
        fetched_length = 3;
        make_expected();
        event_valid = 1;
        edge_cycle();
        event_valid = 0;
        edge_cycle();
        if (!retirement_valid || retirement !== expected) $fatal(1, "CPU_RETIRE_EPOCH_RESET");
        checks = checks + 1;
        $fclose(trace);
        $display("PASS CPU retirement events=6 lengths=1,2,3 irq_zero=1 reset_cancel=1");
        $finish;
    end

    initial begin
        #10000;
        $fatal(1, "CPU_RETIRE_TIMEOUT");
    end
endmodule
