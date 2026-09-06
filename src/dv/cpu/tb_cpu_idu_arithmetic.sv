`timescale 1ns/1ps
`default_nettype none

module tb_cpu_idu_arithmetic;
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
    logic joyp_selected_active;
    logic divider_reset_request;
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
    logic [15:0] expected_address [17];
    logic [2:0] expected_kind [17];
    logic [7:0] expected_data [17];
    logic [15:0] expected_before [6];
    logic [15:0] expected_after [6];
    logic [23:0] expected_opcode [6];
    logic [7:0] expected_length [6];
    logic [63:0] expected_dot [6];
    logic [383:0] expected_record;
    logic expected_effect;
    integer cycle;
    integer bus_index;
    integer event_index;
    integer pause_edge;
    integer trace;
    integer records;
    bit corrupt;

    n2m_cpu dut (.*);

    // Original program. These bytes are separate from the expectation tables.
    always_comb begin
        case (address)
            16'h0100: read_data = 8'h21;
            16'h0101: read_data = 8'h00;
            16'h0102: read_data = 8'hfe;
            16'h0103: read_data = 8'h31;
            16'h0104: read_data = 8'h80;
            16'h0105: read_data = 8'hfe;
            16'h0106: read_data = 8'h39;
            16'h0107: read_data = 8'he8;
            16'h0108: read_data = 8'h01;
            16'h0109: read_data = 8'hf8;
            16'h010a: read_data = 8'h01;
            16'h010b: read_data = 8'h76;
            default: read_data = 0;
        endcase
    end

    always @(posedge clk_sys) begin
        if (reset_sys || core_reset) dot_before <= 0;
        else if (gb_tick) dot_before <= dot_before + 64'd1;
    end

    task automatic check_cycle;
        if (bus_index >= 17) $fatal(1, "CPU_IDU_ARITH_EXTRA_CYCLE");
        // Four arithmetic idle cycles and the final HALT dummy fetch have
        // no extra effect. All other cycles increment an observed PC.
        expected_effect = !(bus_index == 7 || bus_index == 10 || bus_index == 11 || bus_index == 14 || bus_index == 16);
        if (address_effect_phase !== dot_before[1:0] ||
                address_effect_sample !== (gb_tick && dot_before[1:0] == 3))
            $fatal(1, "CPU_IDU_ARITH_PHASE dot=%0d", dot_before);
        if (!address_effect_resolved || address_effect.valid !== expected_effect ||
                address_effect.write_effect !== expected_effect ||
                address_effect.address !== (expected_effect ? expected_address[bus_index] : 16'b0) ||
                address_effect.known_mask !== (expected_effect ? 16'hffff : 16'b0))
            $fatal(1, "CPU_IDU_ARITH_EFFECT cycle=%0d dot=%0d expected_valid=%0d actual=%0d/%04h/%04h resolved=%0d",
                bus_index, dot_before, expected_effect, address_effect.valid,
                address_effect.address, address_effect.known_mask, address_effect_resolved);
        if (gb_tick && dot_before[1:0] == 3) begin
            if (bus_commit !== (expected_kind[bus_index] != 0) ||
                    access_kind !== expected_kind[bus_index] || write_enable ||
                    (expected_kind[bus_index] != 0 && (address !== expected_address[bus_index] || read_data !== expected_data[bus_index])))
                $fatal(1, "CPU_IDU_ARITH_BUS cycle=%0d dot=%0d", bus_index, dot_before+1);
            $fdisplay(trace, "%0d,%0d,%0d,%04h,%0d,%04h,%04h,%0d", dot_before+1,
                bus_index, access_kind, address, address_effect.valid,
                address_effect.address, address_effect.known_mask, address_effect_resolved);
            bus_index = bus_index + 1;
        end
    endtask

    task automatic check_record;
        if (retirement_valid) begin
            if (event_index >= 6) $fatal(1, "CPU_IDU_ARITH_EXTRA_RECORD");
            expected_record = '0;
            expected_record[0 +: 8] = 1;
            expected_record[16 +: 32] = 3;
            expected_record[48 +: 64] = 64'(event_index);
            expected_record[112 +: 64] = expected_dot[event_index];
            expected_record[176 +: 16] = expected_before[event_index];
            expected_record[192 +: 16] = expected_after[event_index];
            expected_record[208 +: 24] = expected_opcode[event_index];
            expected_record[232 +: 8] = expected_length[event_index];
            if (event_index == 2) expected_record[248 +: 8] = 8'h30;
            expected_record[288 +: 16] = event_index < 2 ? 16'h00fe : (event_index < 4 ? 16'h80fc : 16'h82fe);
            expected_record[304 +: 16] = event_index == 0 ? 16'hfffe : (event_index < 3 ? 16'hfe80 : 16'hfe81);
            if (event_index == 5) expected_record[336 +: 8] = 1;
            $fdisplay(records, "%0d,%096h,%096h", event_index, expected_record, retirement);
            if (retirement !== expected_record)
                $fatal(1, "CPU_IDU_ARITH_RECORD event=%0d expected=%096h actual=%096h", event_index, expected_record, retirement);
            event_index = event_index + 1;
        end
    endtask

    task automatic edge_cycle(input bit tick);
        clk_sys = 0;
        gb_tick = tick;
        #4;
        if (!reset_sys && !core_reset && bus_index < 17) check_cycle();
        #1 clk_sys = 1;
        #2;
        if (!reset_sys && !core_reset) check_record();
        #3 clk_sys = 0;
    endtask

    initial begin
        clk_sys = 0;
        reset_sys = 1;
        core_reset = 0;
        gb_tick = 0;
        profile_id = 1;
        epoch = 3;
        dot_before = 0;
        ie = 0;
        iflags = 0;
        buttons = 0;
        response_valid = 1;
        joyp_selected_active = 0;
        wake_request = 0;
        bus_index = 0;
        event_index = 0;
        corrupt = $test$plusargs("corrupt");
        expected_address = '{16'h100,16'h101,16'h102,16'h103,16'h104,16'h105,16'h106,16'h0,16'h107,16'h108,16'h0,16'h0,16'h109,16'h10a,16'h0,16'h10b,16'h10c};
        expected_kind = '{3'd1,3'd2,3'd2,3'd1,3'd2,3'd2,3'd1,3'd0,3'd1,3'd2,3'd0,3'd0,3'd1,3'd2,3'd0,3'd1,3'd1};
        expected_data = '{8'h21,8'h00,8'hfe,8'h31,8'h80,8'hfe,8'h39,8'h00,8'he8,8'h01,8'h00,8'h00,8'hf8,8'h01,8'h00,8'h76,8'h00};
        expected_before = '{16'h100,16'h103,16'h106,16'h107,16'h109,16'h10b};
        expected_after = '{16'h103,16'h106,16'h107,16'h109,16'h10b,16'h10c};
        expected_opcode = '{24'hfe0021,24'hfe8031,24'h000039,24'h0001e8,24'h0001f8,24'h000076};
        expected_length = '{8'd3,8'd3,8'd1,8'd2,8'd2,8'd1};
        expected_dot = '{64'd16,64'd28,64'd36,64'd52,64'd64,64'd68};
        trace = $fopen("idu-arithmetic.csv", "w");
        records = $fopen("idu-arithmetic-retirement.csv", "w");
        if (!trace || !records) $fatal(1, "CPU_IDU_ARITH_TRACE_OPEN");
        $fdisplay(trace, "dot,cycle,kind,address,effect_valid,effect_address,known_mask,resolved");
        $fdisplay(records, "event,expected,actual");
        $dumpfile("waves/cpu-idu-arithmetic.vcd");
        $dumpvars(0, tb_cpu_idu_arithmetic);
        edge_cycle(0);
        reset_sys = 0;
        core_reset = 1;
        edge_cycle(0);
        core_reset = 0;
        for (cycle = 0; cycle < 204; cycle = cycle + 1) begin
            if (corrupt && dot_before == 29)
                force dut.address_effect = {1'b1, 16'hfe00, 16'hffff, 1'b1};
            if (cycle == 93)
                for (pause_edge = 0; pause_edge < 20; pause_edge = pause_edge + 1) edge_cycle(0);
            edge_cycle((cycle % 3) == 0);
        end
        if (fault || !initialized || !halted || locked || stopped || bus_index != 17 || event_index != 6)
            $fatal(1, "CPU_IDU_ARITH_FINAL cycles=%0d records=%0d", bus_index, event_index);
        $fclose(trace);
        $fclose(records);
        $display("PASS CPU IDU arithmetic cycles=17 events=6 resolved_no_effect=4");
        $finish;
    end

    initial begin
        #100000;
        $fatal(1, "CPU_IDU_ARITH_TIMEOUT");
    end
endmodule
