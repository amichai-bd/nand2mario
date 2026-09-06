`timescale 1ns/1ps
`default_nettype none

module tb_cpu_execute;
    import n2m_cpu_pkg::cpu_registers_t;
    import n2m_cpu_pkg::access_kind_t;
    cpu_registers_t registers;
    cpu_registers_t registers_next;
    cpu_registers_t expected_registers;
    logic [7:0] opcode;
    logic cb_bank;
    logic [2:0] step;
    logic [15:0] pc;
    logic [15:0] temporary;
    logic [7:0] data_in;
    logic [15:0] pc_next;
    logic [15:0] temporary_next;
    logic [15:0] address;
    logic [7:0] write_data;
    logic write_enable;
    access_kind_t access_kind;
    logic finish;
    logic prefix;
    logic halt_request;
    logic stop_request;
    logic illegal;
    logic enable_interrupts;
    logic disable_interrupts;
    logic return_interrupt;
    logic [15:0] expected_alu;
    integer base_cycles [256];
    integer instruction;
    integer flags;
    integer cycles;
    integer cycle;
    integer condition_value;
    integer value_byte;
    integer operand;
    integer operation_id;
    integer cases;
    integer trace;

    n2m_cpu_execute dut (.*);

    task automatic setup(input integer op, f);
        registers = '0;
        registers.a = 8'h81;
        registers.f = 8'(f * 16);
        registers.b = 8'h12;
        registers.c = 8'h34;
        registers.d = 8'h56;
        registers.e = 8'h78;
        registers.h = 8'hc0;
        registers.l = 0;
        registers.sp = 16'hfffe;
        opcode = 8'(op);
        cb_bank = 0;
        step = 0;
        pc = 16'h0101;
        temporary = 0;
        data_in = 8'h34;
    endtask

    task automatic advance;
        registers = registers_next;
        pc = pc_next;
        temporary = temporary_next;
        step = step + 3'd1;
        #1;
    endtask

    task automatic mismatch(input string reason);
        $fatal(1, "CPU_EXECUTE_MISMATCH reason=%s op=%02h cb=%0d step=%0d flags=%02h address=%04h data=%02h actualF=%02h", reason, opcode, cb_bank, step, registers.f, address, write_data, registers_next.f);
    endtask

    initial begin
        // Independently transcribed programmer M-cycle counts from the pinned
        // RGBDS manual. CB is checked separately; these are execution cycles
        // after the initial pipeline fetch. Conditional entries are taken.
        base_cycles = '{
            1, 3, 2, 2, 1, 1, 2, 1, 5, 2, 2, 2, 1, 1, 2, 1,
            1, 3, 2, 2, 1, 1, 2, 1, 3, 2, 2, 2, 1, 1, 2, 1,
            3, 3, 2, 2, 1, 1, 2, 1, 3, 2, 2, 2, 1, 1, 2, 1,
            3, 3, 2, 2, 3, 3, 3, 1, 3, 2, 2, 2, 1, 1, 2, 1,
            1, 1, 1, 1, 1, 1, 2, 1, 1, 1, 1, 1, 1, 1, 2, 1,
            1, 1, 1, 1, 1, 1, 2, 1, 1, 1, 1, 1, 1, 1, 2, 1,
            1, 1, 1, 1, 1, 1, 2, 1, 1, 1, 1, 1, 1, 1, 2, 1,
            2, 2, 2, 2, 2, 2, 1, 2, 1, 1, 1, 1, 1, 1, 2, 1,
            1, 1, 1, 1, 1, 1, 2, 1, 1, 1, 1, 1, 1, 1, 2, 1,
            1, 1, 1, 1, 1, 1, 2, 1, 1, 1, 1, 1, 1, 1, 2, 1,
            1, 1, 1, 1, 1, 1, 2, 1, 1, 1, 1, 1, 1, 1, 2, 1,
            1, 1, 1, 1, 1, 1, 2, 1, 1, 1, 1, 1, 1, 1, 2, 1,
            5, 3, 4, 4, 6, 4, 2, 4, 5, 4, 4, 1, 6, 6, 2, 4,
            5, 3, 4, 0, 6, 4, 2, 4, 5, 4, 4, 0, 6, 0, 2, 4,
            3, 3, 2, 0, 0, 4, 2, 4, 4, 1, 4, 0, 0, 0, 2, 4,
            3, 3, 2, 1, 0, 4, 2, 4, 3, 2, 4, 1, 0, 0, 2, 4
        };
        trace = $fopen("execute-trace.csv", "w");
        if (!trace) $fatal(1, "CPU_EXECUTE_TRACE_OPEN");
        $fdisplay(trace, "opcode,flags,cb,step,kind,address,write,data,finish,F");
        $dumpfile("waves/cpu-execute.vcd");
        $dumpvars(0, tb_cpu_execute);
        cases = 0;
        for (instruction = 0; instruction < 256; instruction = instruction + 1) begin
            for (flags = 0; flags < 16; flags = flags + 1) begin
                setup(instruction, flags);
                cycles = base_cycles[instruction];
                // Conditions are explicit opcode sets, independent of the
                // controller's bit-pattern classification.
                case (instruction)
                    'h20, 'hc0, 'hc2, 'hc4: condition_value = !(flags & 8);
                    'h28, 'hc8, 'hca, 'hcc: condition_value = (flags & 8) != 0;
                    'h30, 'hd0, 'hd2, 'hd4: condition_value = !(flags & 1);
                    'h38, 'hd8, 'hda, 'hdc: condition_value = (flags & 1) != 0;
                    default: condition_value = 1;
                endcase
                if (!condition_value) begin
                    case (instruction)
                        'hc0, 'hc8, 'hd0, 'hd8: cycles = 2;
                        'hc4, 'hcc, 'hd4, 'hdc: cycles = 3;
                        default: cycles = cycles - 1;
                    endcase
                end
                #1;
                if (cycles == 0) begin
                    if (!illegal || finish || access_kind != 0) mismatch("illegal lock request");
                end else if (instruction == 'hcb) begin
                    if (!prefix || finish || access_kind != 2 || pc_next != 'h0102)
                        mismatch("prefix operand fetch");
                end else begin
                    for (cycle = 0; cycle < cycles; cycle = cycle + 1) begin
                        if (finish !== (cycle == cycles - 1)) mismatch("M-cycle count");
                        if (illegal || prefix) mismatch("legal instruction classification");
                        if (finish && (access_kind != 1 || write_enable)) mismatch("final opcode fetch");
                        $fdisplay(trace, "%02h,%02h,0,%0d,%0d,%04h,%0d,%02h,%0d,%02h", opcode, 8'(flags*16), step, access_kind, address, write_enable, write_data, finish, registers_next.f);
                        if (cycle < cycles - 1) advance();
                    end
                end
                cases = cases + 1;
            end
        end
        $dumpoff;
        // Exhaust the public memory RMW sequence, including carry feedback at
        // final fetch. Expected values come from the separate integer model.
        for (instruction = 0; instruction < 256; instruction = instruction + 1) begin
            if (instruction % 8 == 6) begin
                for (value_byte = 0; value_byte < 256; value_byte = value_byte + 1) begin
                    for (flags = 0; flags < 16; flags = flags + 1) begin
                        setup(instruction, flags);
                        cb_bank = 1;
                        data_in = 8'(value_byte);
                        if (instruction < 64) operation_id = 18 + instruction / 8;
                        else operation_id = 25 + instruction / 64;
                        expected_alu = cpu_alu_reference::calculate(operation_id, value_byte, 0, flags * 16, (instruction / 8) % 8);
                        #1;
                        if (access_kind != 3 || address != 'hc000 || write_enable || finish)
                            mismatch("CB memory read");
                        advance();
                        if (instruction / 64 != 1) begin
                            if (access_kind != 3 || address != 'hc000 || !write_enable || finish || write_data !== expected_alu[15:8] || registers_next.f !== expected_alu[7:0])
                                mismatch("CB memory write/result flags");
                            advance();
                        end
                        if (!finish || access_kind != 1 || address != 'h0101 || registers_next.f !== expected_alu[7:0])
                            mismatch("CB final flags retained");
                        cases = cases + 1;
                    end
                end
            end
        end
        if (cases != 135168) $fatal(1, "CPU_EXECUTE_COVERAGE expected=135168 actual=%0d", cases);
        $fclose(trace);
        $display("PASS CPU execute cases=135168 base=256 flagsets=16 cb_memory=32 seed=none");
        $finish;
    end

    initial begin
        #1000000;
        $fatal(1, "CPU_EXECUTE_TIMEOUT");
    end
endmodule
