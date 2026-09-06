`timescale 1ns/1ps
`default_nettype none

module tb_cpu_alu;
    logic [4:0] operation;
    logic [7:0] lhs;
    logic [7:0] rhs;
    logic [7:0] flags_in;
    logic [2:0] bit_index;
    logic [7:0] value;
    logic [7:0] flags_out;
    logic [15:0] expected;
    logic [15:0] observed;
    integer cases;
    integer op;
    integer a;
    integer b;
    integer f;
    integer bit_number;
    integer bit_count;
    integer trace;
    bit corrupt;

    n2m_cpu_alu dut (.*);

    task automatic check_case(input integer operation_id, left, right, flags, selected_bit);
        operation = 5'(operation_id);
        lhs = 8'(left);
        rhs = 8'(right);
        flags_in = 8'(flags);
        bit_index = 3'(selected_bit);
        expected = cpu_alu_reference::calculate(operation_id, left, right, flags, selected_bit);
        // Fault injection changes the actual DUT result, not the compared
        // observation or oracle. Normal expectations use only public inputs.
        if (corrupt && cases == 17) force dut.value = 8'h09;
        #1;
        observed = {value, flags_out};
        if (cases < 256 || observed !== expected)
            $fdisplay(trace, "%0d,%0d,%02h,%02h,%02h,%0d,%04h,%04h", cases, operation_id, lhs, rhs, flags_in, selected_bit, expected, observed);
        if (observed !== expected)
            $fatal(1, "CPU_ALU_MISMATCH case=%0d op=%0d lhs=%02h rhs=%02h flags=%02h bit=%0d expected=%04h actual=%04h", cases, operation_id, lhs, rhs, flags_in, selected_bit, expected, observed);
        cases = cases + 1;
        if (cases == 256) $dumpoff;
    endtask

    initial begin
        operation = 0;
        lhs = 0;
        rhs = 0;
        flags_in = 0;
        bit_index = 0;
        cases = 0;
        corrupt = $test$plusargs("corrupt");
        trace = $fopen("alu-trace.csv", "w");
        if (!trace) $fatal(1, "CPU_ALU_TRACE_OPEN");
        $fdisplay(trace, "case,operation,lhs,rhs,flags,bit,expected,actual");
        $dumpfile("waves/cpu-alu.vcd");
        $dumpvars(0,operation,lhs,rhs,flags_in,bit_index,value,flags_out);
        // Exhaust every input pair and both carry states. Irrelevant flags and
        // forbidden low bits vary, so accidental preservation is detected.
        for (op = 0; op < 8; op = op + 1)
            for (a = 0; a < 256; a = a + 1)
                for (b = 0; b < 256; b = b + 1)
                    for (f = 0; f < 2; f = f + 1)
                        check_case(op, a, b, f * 16 + ((a + b) % 8) * 32 + 15, 0);
        for (op = 8; op <= 31; op = op + 1) begin
            bit_count = (op >= 26 && op <= 28) ? 8 : 1;
            for (a = 0; a < 256; a = a + 1)
                for (f = 0; f < 16; f = f + 1)
                    for (bit_number = 0; bit_number < bit_count; bit_number = bit_number + 1)
                        check_case(op, a, 0, f * 16 + 15, bit_number);
        end
        if (cases != 1232896) $fatal(1, "CPU_ALU_COVERAGE expected=1232896 actual=%0d", cases);
        $fclose(trace);
        $display("PASS CPU ALU cases=1232896 operations=32 seed=none");
        $finish;
    end

    initial begin
        #2000000;
        $fatal(1, "CPU_ALU_TIMEOUT");
    end
endmodule
