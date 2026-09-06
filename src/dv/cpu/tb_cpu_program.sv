`timescale 1ns/1ps
`default_nettype none

module tb_cpu_program;
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
    n2m_cpu_pkg::cpu_address_effect_t address_effect;
    logic address_effect_resolved;
    logic address_effect_sample;
    logic [1:0] address_effect_phase;
    logic [7:0] memory [65536];
    logic [15:0] expected_address [50];
    logic [3:0] expected_kind [50];
    logic [7:0] expected_data [50];
    logic [15:0] expected_before [18];
    logic [15:0] expected_after [18];
    logic [23:0] expected_opcode [18];
    logic [1:0] expected_length [18];
    logic [63:0] expected_dot [18];
    logic [383:0] expected_record;
    integer bus_index;
    integer event_index;
    integer cycle;
    integer item;
    integer trace;
    integer records;
    integer encoded_kind;
    logic expected_write;
    bit state_fault;
    bit timing_fault;
    bit retirement_fault;
    logic expected_effect_valid [50];
    logic [15:0] expected_effect_address [50];
    logic [15:0] expected_effect_mask;
    integer effect_trace;
    integer pause_edge;
    integer reset_phase;
    integer reset_tick;
    bit effect_fault;

    n2m_cpu_control dut (.*);
    assign read_data = memory[address];

    always @(posedge clk_sys) begin
        if (reset_sys || core_reset) dot_before <= 0;
        else if (gb_tick) dot_before <= dot_before + 64'd1;
        if (bus_commit && write_enable) memory[address] <= write_data;
    end

    task automatic check_address_effect;
        if (reset_sys || core_reset) begin
            if (address_effect_sample || address_effect.valid)
                $fatal(1, "CPU_PROGRAM_IDU_RESET");
        end else begin
            if (address_effect_phase !== dot_before[1:0] ||
                    address_effect_sample !== (gb_tick && dot_before[1:0] == 3))
                $fatal(1, "CPU_PROGRAM_IDU_EDGE dot=%0d", dot_before);
            if (bus_index < 50) begin
                expected_effect_mask = expected_effect_valid[bus_index] ? 16'hffff : 0;
                if (bus_index == 32) expected_effect_mask = 16'hff00;
                if (!address_effect_resolved ||
                        address_effect.valid !== expected_effect_valid[bus_index] ||
                        address_effect.write_effect !== expected_effect_valid[bus_index] ||
                        address_effect.address !== expected_effect_address[bus_index] ||
                        address_effect.known_mask !== expected_effect_mask)
                    $fatal(1, "CPU_PROGRAM_IDU cycle=%0d dot=%0d expected=%0d/%04h/%04h actual=%0d/%04h/%04h resolved=%0d",
                        bus_index, dot_before, expected_effect_valid[bus_index],
                        expected_effect_address[bus_index], expected_effect_mask,
                        address_effect.valid, address_effect.address, address_effect.known_mask,
                        address_effect_resolved);
                if (address_effect_sample)
                    $fdisplay(effect_trace, "%0d,%0d,%0d,%04h,%04h,%0d", dot_before+1,
                        bus_index, address_effect.valid, address_effect.address,
                        address_effect.known_mask, address_effect.write_effect);
            end else if (address_effect_resolved)
                $fatal(1, "CPU_PROGRAM_IDU_UNRESOLVED_HALT");
        end
    endtask

    task automatic check_bus;
        if (!gb_tick && bus_commit) $fatal(1, "CPU_PROGRAM_TIMING commit without tick");
        if (gb_tick && dot_before[1:0] != 3 && bus_commit)
            $fatal(1, "CPU_PROGRAM_TIMING commit before T4 dot=%0d", dot_before + 1);
        if (gb_tick && dot_before[1:0] == 3) begin
            if (bus_index < 50) begin
                encoded_kind = expected_kind[bus_index];
                expected_write = encoded_kind >= 7;
                if (expected_write) encoded_kind = encoded_kind - 4;
                $fdisplay(trace, "%0d,%0d,%04h,%0d,%02h,%0d", dot_before+1, access_kind, address, write_enable, write_enable ? write_data : read_data, bus_commit);
                if (bus_commit !== (encoded_kind != 0))
                    $fatal(1, "CPU_PROGRAM_TIMING dot=%0d expected_access=%0d actual_commit=%0d", dot_before+1, encoded_kind, bus_commit);
                if (encoded_kind != 0 && (access_kind !== 3'(encoded_kind) || address !== expected_address[bus_index] || write_enable !== expected_write || (write_enable ? write_data : read_data) !== expected_data[bus_index]))
                    $fatal(1, "CPU_PROGRAM_BUS dot=%0d expected_address=%04h actual_address=%04h expected_data=%02h actual_data=%02h", dot_before+1, expected_address[bus_index], address, expected_data[bus_index], write_enable ? write_data : read_data);
                bus_index = bus_index + 1;
            end else if (bus_commit || request_valid) $fatal(1, "CPU_PROGRAM_HALTED_ACCESS");
        end
    endtask

    task automatic check_retirement;
        if (retirement_valid) begin
            if (event_index >= 18) $fatal(1, "CPU_PROGRAM_EXTRA_RETIREMENT");
            expected_record = '0;
            expected_record[0 +: 8] = 1;
            expected_record[16 +: 32] = 1;
            expected_record[48 +: 64] = 64'(event_index);
            expected_record[112 +: 64] = expected_dot[event_index];
            expected_record[176 +: 16] = expected_before[event_index];
            expected_record[192 +: 16] = expected_after[event_index];
            expected_record[208 +: 24] = expected_opcode[event_index];
            expected_record[232 +: 8] = {6'b0, expected_length[event_index]};
            if (event_index >= 3 && event_index <= 5) expected_record[240 +: 8] = 8'h80;
            if (event_index >= 11 && event_index <= 13) expected_record[240 +: 8] = 1;
            if (event_index >= 14) expected_record[240 +: 8] = 2;
            if (event_index >= 5 && event_index <= 8) expected_record[248 +: 8] = 8'h90;
            if (event_index == 9 || event_index == 10) expected_record[248 +: 8] = 8'h80;
            if (event_index >= 1) expected_record[256 +: 16] = 16'h3412;
            if (event_index >= 8) expected_record[272 +: 16] = 16'h3412;
            if (event_index >= 2) expected_record[288 +: 16] = 16'h00c0;
            expected_record[304 +: 16] = (event_index == 7 || event_index == 13 || event_index == 14) ? 16'hcffe : 16'hd000;
            if (event_index == 17) expected_record[336 +: 8] = 1;
            $fdisplay(records, "%0d,%096h,%096h", event_index, expected_record, retirement);
            if (retirement !== expected_record)
                $fatal(1, "CPU_PROGRAM_STATE event=%0d expected=%096h actual=%096h", event_index, expected_record, retirement);
            event_index = event_index + 1;
        end
    endtask

    task automatic edge_cycle(input bit tick);
        clk_sys = 0;
        gb_tick = tick;
        #4;
        check_address_effect();
        if (!reset_sys && !core_reset) check_bus();
        #1 clk_sys = 1;
        #1;
        if (retirement_fault && retirement_valid && event_index == 3)
            force dut.observer.retirement.pc_after = 16'hffff;
        #1;
        if (!reset_sys && !core_reset) check_retirement();
        #3 clk_sys = 0;
    endtask

    initial begin
        clk_sys = 0;
        reset_sys = 1;
        core_reset = 0;
        gb_tick = 0;
        profile_id = 1;
        epoch = 1;
        dot_before = 0;
        ie = 0;
        iflags = 0;
        buttons = 0;
        response_valid = 1;
        stop_action = 0;
        stop_padding = 0;
        wake_request = 0;
        bus_index = 0;
        event_index = 0;
        state_fault = $test$plusargs("state_fault");
        timing_fault = $test$plusargs("timing_fault");
        retirement_fault = $test$plusargs("retirement_fault");
        effect_fault = $test$plusargs("effect_fault");
        for (item = 0; item < 65536; item = item + 1) memory[item] = 0;
        memory[16'h0100] = 8'h31;
        memory[16'h0101] = 8'h00;
        memory[16'h0102] = 8'hd0;
        memory[16'h0103] = 8'h01;
        memory[16'h0104] = 8'h34;
        memory[16'h0105] = 8'h12;
        memory[16'h0106] = 8'h21;
        memory[16'h0107] = 8'h00;
        memory[16'h0108] = 8'hc0;
        memory[16'h0109] = 8'h3e;
        memory[16'h010a] = 8'h80;
        memory[16'h010b] = 8'h77;
        memory[16'h010c] = 8'hcb;
        memory[16'h010d] = 8'h16;
        memory[16'h010e] = 8'h7e;
        memory[16'h010f] = 8'hc5;
        memory[16'h0110] = 8'hd1;
        memory[16'h0111] = 8'haf;
        memory[16'h0112] = 8'h20;
        memory[16'h0113] = 8'h02;
        memory[16'h0114] = 8'h3c;
        memory[16'h0115] = 8'h20;
        memory[16'h0116] = 8'h02;
        memory[16'h0117] = 8'h3e;
        memory[16'h0118] = 8'hff;
        memory[16'h0119] = 8'hcd;
        memory[16'h011a] = 8'h20;
        memory[16'h011b] = 8'h01;
        memory[16'h011c] = 8'hc3;
        memory[16'h011d] = 8'h30;
        memory[16'h011e] = 8'h01;
        memory[16'h0120] = 8'h3c;
        memory[16'h0121] = 8'hc9;
        memory[16'h0130] = 8'h76;
        expected_address = '{16'h100, 16'h101, 16'h102, 16'h103, 16'h104, 16'h105, 16'h106, 16'h107, 16'h108, 16'h109, 16'h10a, 16'h10b, 16'hc000, 16'h10c, 16'h10d, 16'hc000, 16'hc000, 16'h10e, 16'hc000, 16'h10f, 16'h0, 16'hcfff, 16'hcffe, 16'h110, 16'hcffe, 16'hcfff, 16'h111, 16'h112, 16'h113, 16'h114, 16'h115, 16'h116, 16'h0, 16'h119, 16'h11a, 16'h11b, 16'h0, 16'hcfff, 16'hcffe, 16'h120, 16'h121, 16'hcffe, 16'hcfff, 16'h0, 16'h11c, 16'h11d, 16'h11e, 16'h0, 16'h130, 16'h131};
        expected_kind = '{4'h1, 4'h2, 4'h2, 4'h1, 4'h2, 4'h2, 4'h1, 4'h2, 4'h2, 4'h1, 4'h2, 4'h1, 4'h7, 4'h1, 4'h2, 4'h3, 4'h7, 4'h1, 4'h3, 4'h1, 4'h0, 4'h8, 4'h8, 4'h1, 4'h4, 4'h4, 4'h1, 4'h1, 4'h2, 4'h1, 4'h1, 4'h2, 4'h0, 4'h1, 4'h2, 4'h2, 4'h0, 4'h8, 4'h8, 4'h1, 4'h1, 4'h4, 4'h4, 4'h0, 4'h1, 4'h2, 4'h2, 4'h0, 4'h1, 4'h1};
        expected_data = '{8'h31, 8'h0, 8'hd0, 8'h1, 8'h34, 8'h12, 8'h21, 8'h0, 8'hc0, 8'h3e, 8'h80, 8'h77, 8'h80, 8'hcb, 8'h16, 8'h80, 8'h0, 8'h7e, 8'h0, 8'hc5, 8'h0, 8'h12, 8'h34, 8'hd1, 8'h34, 8'h12, 8'haf, 8'h20, 8'h2, 8'h3c, 8'h20, 8'h2, 8'h0, 8'hcd, 8'h20, 8'h1, 8'h0, 8'h1, 8'h1c, 8'h3c, 8'hc9, 8'h1c, 8'h1, 8'h0, 8'hc3, 8'h30, 8'h1, 8'h0, 8'h76, 8'h0};
        expected_before = '{16'h100, 16'h103, 16'h106, 16'h109, 16'h10b, 16'h10c, 16'h10e, 16'h10f, 16'h110, 16'h111, 16'h112, 16'h114, 16'h115, 16'h119, 16'h120, 16'h121, 16'h11c, 16'h130};
        expected_after = '{16'h103, 16'h106, 16'h109, 16'h10b, 16'h10c, 16'h10e, 16'h10f, 16'h110, 16'h111, 16'h112, 16'h114, 16'h115, 16'h119, 16'h120, 16'h121, 16'h11c, 16'h130, 16'h131};
        expected_opcode = '{24'hd00031, 24'h123401, 24'hc00021, 24'h803e, 24'h77, 24'h16cb, 24'h7e, 24'hc5, 24'hd1, 24'haf, 24'h220, 24'h3c, 24'h220, 24'h120cd, 24'h3c, 24'hc9, 24'h130c3, 24'h76};
        expected_length = '{2'h3, 2'h3, 2'h3, 2'h2, 2'h1, 2'h2, 2'h1, 2'h1, 2'h1, 2'h1, 2'h2, 2'h1, 2'h2, 2'h3, 2'h1, 2'h1, 2'h3, 2'h1};
        expected_dot = '{64'h10, 64'h1c, 64'h28, 64'h30, 64'h38, 64'h48, 64'h50, 64'h60, 64'h6c, 64'h70, 64'h78, 64'h7c, 64'h88, 64'ha0, 64'ha4, 64'hb4, 64'hc4, 64'hc8};
        expected_effect_valid = '{1'b1, 1'b1, 1'b1, 1'b1, 1'b1, 1'b1, 1'b1, 1'b1, 1'b1, 1'b1, 1'b1, 1'b1, 1'b0, 1'b1, 1'b1, 1'b0, 1'b0, 1'b1, 1'b0, 1'b1, 1'b1, 1'b1, 1'b0, 1'b1, 1'b1, 1'b0, 1'b1, 1'b1, 1'b1, 1'b1, 1'b1, 1'b1, 1'b1, 1'b1, 1'b1, 1'b1, 1'b1, 1'b1, 1'b0, 1'b1, 1'b1, 1'b1, 1'b0, 1'b0, 1'b1, 1'b1, 1'b1, 1'b0, 1'b1, 1'b0};
        expected_effect_address = '{16'h0100, 16'h0101, 16'h0102, 16'h0103, 16'h0104, 16'h0105, 16'h0106, 16'h0107, 16'h0108, 16'h0109, 16'h010a, 16'h010b, 16'h0000, 16'h010c, 16'h010d, 16'h0000, 16'h0000, 16'h010e, 16'h0000, 16'h010f, 16'hd000, 16'hcfff, 16'h0000, 16'h0110, 16'hcffe, 16'h0000, 16'h0111, 16'h0112, 16'h0113, 16'h0114, 16'h0115, 16'h0116, 16'h0100, 16'h0119, 16'h011a, 16'h011b, 16'hd000, 16'hcfff, 16'h0000, 16'h0120, 16'h0121, 16'hcffe, 16'h0000, 16'h0000, 16'h011c, 16'h011d, 16'h011e, 16'h0000, 16'h0130, 16'h0000};
        effect_trace = $fopen("program-address-effects.csv", "w");
        if (!effect_trace) $fatal(1, "CPU_PROGRAM_IDU_TRACE_OPEN");
        $fdisplay(effect_trace, "dot,cycle,valid,address,known_mask,write_effect");
        trace = $fopen("program-bus.csv", "w");
        records = $fopen("program-retirement.csv", "w");
        if (!trace || !records) $fatal(1, "CPU_PROGRAM_TRACE_OPEN");
        $fdisplay(trace, "dot,kind,address,write,data,commit");
        $fdisplay(records, "event,expected,actual");
        $dumpfile("waves/cpu-program.vcd");
        $dumpvars(0, tb_cpu_program);
        edge_cycle(0);
        reset_sys = 0;
        core_reset = 1;
        edge_cycle(0);
        core_reset = 0;
        // Cancel a prepared opcode increment at every M-phase while paused.
        // No partial attempt reaches T4, so the original program oracle starts
        // untouched after each synchronous or asynchronous reset.
        for (reset_phase = 0; reset_phase < 4; reset_phase = reset_phase + 1) begin
            for (reset_tick = 0; reset_tick < reset_phase; reset_tick = reset_tick + 1) edge_cycle(1);
            for (pause_edge = 0; pause_edge < 20; pause_edge = pause_edge + 1) edge_cycle(0);
            core_reset = 1;
            edge_cycle(0);
            core_reset = 0;
            for (reset_tick = 0; reset_tick < reset_phase; reset_tick = reset_tick + 1) edge_cycle(1);
            for (pause_edge = 0; pause_edge < 20; pause_edge = pause_edge + 1) edge_cycle(0);
            reset_sys = 1;
            edge_cycle(0);
            reset_sys = 0;
            core_reset = 1;
            edge_cycle(0);
            core_reset = 0;
        end
        for (cycle = 0; cycle < 660; cycle = cycle + 1) begin
            if (state_fault && dot_before == 120) force dut.registers.a = 8'h40;
            if (timing_fault && dot_before == 10) force dut.bus.commit = 1'b1;
            if (cycle >= 240 && cycle < 252 && (cycle % 3) == 0)
                for (pause_edge = 0; pause_edge < 20; pause_edge = pause_edge + 1) edge_cycle(0);
            if (effect_fault && dot_before == 81)
                force dut.address_effect.address = 16'h0000;
            edge_cycle((cycle % 3) == 0);
        end
        if (fault || locked || !initialized || !halted || stopped || bus_index != 50 || event_index != 18 || memory['hc000] != 0)
            $fatal(1, "CPU_PROGRAM_FINAL events=%0d cycles=%0d halted=%0d fault=%0d", event_index, bus_index, halted, fault);
        $fclose(trace);
        $fclose(records);
        $fclose(effect_trace);
        $display("PASS CPU program events=18 Mcycles=50 dots=220 HALT=1");
        $finish;
    end

    initial begin
        #100000;
        $fatal(1, "CPU_PROGRAM_TIMEOUT");
    end
endmodule
