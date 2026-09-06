`timescale 1ns/1ps
`default_nettype none

module tb_cpu_vectors;
    logic clk_sys;
    logic reset_sys;
    logic core_reset;
    logic gb_tick;
    logic [7:0] profile_id;
    logic [31:0] epoch;
    logic [63:0] dot_before;
    logic [7:0] ie;
    logic [4:0] iflags;
    logic [7:0] buttons;
    logic [7:0] read_data;
    logic response_valid;
    logic [1:0] stop_action;
    logic stop_padding;
    logic wake_request;
    logic request_valid;
    logic [15:0] address;
    logic [7:0] write_data;
    logic write_enable;
    n2m_cpu_pkg::access_kind_t access_kind;
    logic bus_commit;
    logic [4:0] irq_ack;
    logic halted;
    logic stopped;
    logic locked;
    logic initialized;
    logic fault;
    logic ime_observe;
    logic ime_delay_observe;
    logic stop_execute;
    logic retirement_valid;
    n2m_interfaces_pkg::retirement_t retirement;

    logic [1023:0] vector_data [8000];
    logic [1023:0] vector_case;
    logic [7:0] memory [65536];
    n2m_cpu_pkg::cpu_registers_t initial_registers;
    n2m_cpu_pkg::cpu_registers_t corrupt_registers;
    n2m_cpu_pkg::cpu_control_t initial_control;
    logic [15:0] initial_pc;
    logic [15:0] final_pc;
    logic [383:0] expected_record;
    logic [23:0] expected_opcode;
    logic [27:0] expected_cycle;
    logic [15:0] expected_address;
    logic [7:0] expected_byte;
    logic expected_write;
    logic expected_commit;
    integer number;
    integer item;
    integer cycle;
    integer mcycle;
    integer count;
    integer skipped;
    integer ram_count;
    integer final_ram_count;
    integer instruction_cycles;
    integer instruction_bytes;
    integer opcode_number;
    integer trace;
    integer bus_trace;
    integer write_count;
    logic [15:0] written_addresses [8];
    bit complete;
    bit corrupt;
    bit missing;

    n2m_cpu_control dut (.*);
    assign read_data = memory[address];

    always @(posedge clk_sys) begin
        if (reset_sys || core_reset) dot_before <= 0;
        else if (gb_tick) dot_before <= dot_before + 64'd1;
        if (bus_commit && write_enable) begin
            if (write_count >= 8) $fatal(1,"CPU_VECTOR_WRITE_BOUND");
            written_addresses[write_count] = address;
            write_count = write_count + 1;
            memory[address] <= write_data;
        end
    end

    task automatic check_bus;
        if (bus_commit && (!gb_tick || dot_before[1:0] != 3))
            $fatal(1,"CPU_VECTOR_T4 case=%0d dot=%0d",number,dot_before+1);
        if (gb_tick && dot_before[1:0] == 3) begin
            mcycle = int'(dot_before / 4);
            if (mcycle > instruction_cycles) $fatal(1,"CPU_VECTOR_EXTRA_CYCLE case=%0d",number);
            expected_cycle = '0;
            expected_cycle[24] = 1;
            expected_cycle[26] = 1;
            expected_cycle[27] = 1;
            expected_cycle[15:0] = final_pc;
            expected_cycle[23:16] = memory[final_pc];
            if (mcycle < instruction_cycles)
                expected_cycle = vector_case[609 + 28*mcycle +: 28];
            expected_commit = expected_cycle[25:24] != 0;
            expected_write = expected_cycle[25:24] == 2;
            expected_address = expected_cycle[15:0];
            expected_byte = expected_cycle[23:16];
            $fdisplay(bus_trace,"%0d,%0d,%07h,%0d,%04h,%0d,%02h",number,dot_before+1,
                expected_cycle,bus_commit,address,write_enable,write_enable ? write_data : read_data);
            if (bus_commit !== expected_commit || (expected_commit &&
                (write_enable !== expected_write ||
                 (expected_cycle[26] && address !== expected_address) ||
                 (expected_cycle[27] && (write_enable ? write_data : read_data) !== expected_byte))))
                $fatal(1,"CPU_VECTOR_BUS case=%0d opcode=%03h M=%0d expected=%07h actual=%0d/%04h/%0d/%02h",
                    number,opcode_number,mcycle,expected_cycle,bus_commit,address,write_enable,
                    write_enable ? write_data : read_data);
        end
    endtask

    task automatic check_event;
        if (retirement_valid) begin
            if (complete) $fatal(1,"CPU_VECTOR_DUPLICATE case=%0d",number);
            expected_record = '0;
            expected_record[0 +: 8] = 1;
            expected_record[16 +: 32] = 32'(number+1);
            expected_record[112 +: 64] = 64'((instruction_cycles+1)*4);
            expected_record[176 +: 16] = initial_pc;
            expected_record[192 +: 16] = final_pc;
            expected_record[208 +: 24] = expected_opcode;
            expected_record[232 +: 8] = 8'(instruction_bytes);
            expected_record[240 +: 80] = vector_case[96 +: 80];
            // Upstream interrupt fields are excluded. These isolated IME=0
            // cases use separately documented direct EI/DI/RETI effects only.
            if (opcode_number == 9'h0fb) expected_record[328 +: 8] = 1;
            if (opcode_number == 9'h0d9) expected_record[320 +: 8] = 1;
            $fdisplay(trace,"%0d,%03h,%0d,%096h,%096h",number,opcode_number,
                vector_case[215 +: 10],expected_record,retirement);
            if (retirement !== expected_record)
                $fatal(1,"CPU_VECTOR_STATE case=%0d opcode=%03h expected=%096h actual=%096h",
                    number,opcode_number,expected_record,retirement);
            for (item=0; item<final_ram_count; item=item+1) begin
                expected_address=vector_case[417+24*item +: 16];
                expected_byte=vector_case[433+24*item +: 8];
                if (memory[expected_address] !== expected_byte)
                    $fatal(1,"CPU_VECTOR_RAM case=%0d address=%04h expected=%02h actual=%02h",
                        number,expected_address,expected_byte,memory[expected_address]);
            end
            complete=1;
        end
    endtask

    task automatic edge_cycle(input bit tick);
        clk_sys=0; gb_tick=tick; #4;
        if (!reset_sys && !core_reset) check_bus();
        #1 clk_sys=1; #2;
        if (!reset_sys && !core_reset) check_event();
        #3 clk_sys=0;
    endtask

    initial begin
        `include "src/dv/cpu/singlestep/vectors.svh"
        clk_sys=0; reset_sys=1; core_reset=0; gb_tick=0; profile_id=1;
        epoch=1; dot_before=0; ie=0; iflags=0; buttons=0;
        response_valid=1; stop_action=0; stop_padding=0; wake_request=0;
        count=0; skipped=0; write_count=0;
        corrupt=$test$plusargs("corrupt"); missing=$test$plusargs("missing");
        for (item=0; item<65536; item=item+1) memory[item]=0;
        trace=$fopen("vector-retirement.csv","w");
        bus_trace=$fopen("vector-bus.csv","w");
        if (!trace || !bus_trace) $fatal(1,"CPU_VECTOR_TRACE_OPEN");
        $dumpfile("waves/cpu-vectors.vcd");
        $dumpvars(0,tb_cpu_vectors);
        for (number=0; number<8000; number=number+1) begin
            vector_case=vector_data[number];
            opcode_number=int'(vector_case[206 +: 9]);
            if (opcode_number==9'h010 || opcode_number==9'h076) begin
                skipped=skipped+1;
                continue;
            end
            reset_sys=1; edge_cycle(0); reset_sys=0;
            epoch=32'(number+1); core_reset=1; edge_cycle(0); core_reset=0;
            complete=0; write_count=0;
            initial_registers.a=vector_case[0 +: 8];
            initial_registers.f=vector_case[8 +: 8];
            initial_registers.b=vector_case[16 +: 8];
            initial_registers.c=vector_case[24 +: 8];
            initial_registers.d=vector_case[32 +: 8];
            initial_registers.e=vector_case[40 +: 8];
            initial_registers.h=vector_case[48 +: 8];
            initial_registers.l=vector_case[56 +: 8];
            initial_registers.sp=vector_case[64 +: 16];
            initial_pc=vector_case[80 +: 16];
            final_pc=vector_case[176 +: 16];
            ram_count=int'(vector_case[192 +: 4]);
            final_ram_count=int'(vector_case[196 +: 4]);
            instruction_cycles=int'(vector_case[200 +: 4]);
            instruction_bytes=int'(vector_case[204 +: 2]);
            for (item=0; item<ram_count; item=item+1)
                memory[vector_case[225+24*item +: 16]]=vector_case[241+24*item +: 8];
            expected_opcode=0;
            for (item=0; item<instruction_bytes; item=item+1)
                expected_opcode[8*item +: 8]=memory[16'(initial_pc+item)];
            // Isolated simulation setup, not a product port. No DUT state is
            // read to calculate expectations; all expected values come from
            // the pinned input or the independent pipeline/retirement contract.
            initial_control='0;
            initial_control.mode=n2m_cpu_pkg::MODE_FETCH;
            initial_control.initialized=1;
            initial_control.pc=initial_pc;
            initial_control.instruction_pc=initial_pc;
            corrupt_registers=initial_registers;
            corrupt_registers.a=initial_registers.a ^ 8'h01;
            force dut.registers=initial_registers;
            force dut.control=initial_control;
            edge_cycle(0);
            release dut.registers;
            release dut.control;
            if (missing && number==0) force dut.observer.retirement_valid=0;
            for (cycle=0; cycle<(instruction_cycles+1)*12+2; cycle=cycle+1) begin
                if (corrupt && number==0 && dot_before==4)
                    force dut.registers=corrupt_registers;
                edge_cycle(cycle%3==0);
            end
            if (!complete) $fatal(1,"CPU_VECTOR_MISSING case=%0d",number);
            if (fault || locked || !initialized) $fatal(1,"CPU_VECTOR_FAULT case=%0d",number);
            count=count+1;
            for (item=0; item<ram_count; item=item+1)
                memory[vector_case[225+24*item +: 16]]=0;
            for (item=0; item<write_count; item=item+1) memory[written_addresses[item]]=0;
            if (count==32) $dumpoff;
        end
        $fclose(trace); $fclose(bus_trace);
        if (count!=7968 || skipped!=32) $fatal(1,"CPU_VECTOR_COUNT");
        $display("PASS CPU vectors cases=7968 forms=498 flags=16 excluded_STOP_HALT=32");
        $finish;
    end
    initial begin
        #100000000;
        $fatal(1,"CPU_VECTOR_TIMEOUT");
    end
endmodule
