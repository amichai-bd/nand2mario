`timescale 1ns/1ps
`default_nettype none

module tb_cpu_stop;
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
    logic [7:0] memory [65536];
    logic [383:0] expected;
    logic [2:0] expected_kind;
    logic [15:0] expected_address;
    logic [7:0] expected_byte;
    logic expected_write;
    logic expected_divider;
    logic [4:0] expected_ack;
    integer scenario;
    integer item;
    integer event_index;
    integer divider_count;
    integer trace;
    integer records;
    integer quiet;
    integer target_dot;
    bit pending_case;
    bit ime_case;
    bit continue_case;
    bit interrupt_case;
    bit corrupt_divider;
    bit corrupt_action;

    n2m_cpu_control dut (.*);
    assign read_data = memory[address];

    always @(posedge clk_sys) begin
        if (reset_sys || core_reset) dot_before <= 0;
        else if (gb_tick) dot_before <= dot_before + 64'd1;
        if (bus_commit && write_enable) memory[address] <= write_data;
        if (irq_ack != 0) iflags <= iflags & ~irq_ack;
    end

    task automatic check_bus;
        expected_divider = gb_tick && dot_before == 15 && !joyp_selected_active;
        if (divider_reset_request !== expected_divider)
            $fatal(1, "CPU_STOP_DIVIDER case=%0d dot=%0d expected=%0d actual=%0d", scenario, dot_before+1, expected_divider, divider_reset_request);
        if (expected_divider) divider_count = divider_count + 1;
        if (!gb_tick && (bus_commit || address_effect_sample)) $fatal(1, "CPU_STOP_PAUSE_COMMIT");
        if (gb_tick && dot_before[1:0] == 3) begin
            expected_kind = 0;
            expected_address = 0;
            expected_byte = 0;
            expected_write = 0;
            expected_ack = 0;
            case (dot_before+1)
                4: begin expected_kind=1; expected_address='h100; expected_byte=ime_case ? 8'hfb : 8'h00; end
                8: begin expected_kind=1; expected_address='h101; expected_byte=0; end
                12: begin expected_kind=1; expected_address='h102; expected_byte='h10; end
                16: begin expected_kind=1; expected_address='h103; expected_byte='h3c; end
                20: if (continue_case && !ime_case) begin expected_kind=1; expected_address='h104; expected_byte=0; end
                28: if (interrupt_case) begin expected_kind=4; expected_address='hfffd; expected_byte=1; expected_write=1; end
                32: if (interrupt_case) begin expected_kind=4; expected_address='hfffc; expected_byte=3; expected_write=1; expected_ack=1; end
                36: if (interrupt_case) begin expected_kind=1; expected_address='h40; expected_byte=0; end
                default: begin end
            endcase
            if (bus_commit !== (expected_kind != 0) || irq_ack !== expected_ack ||
                    (expected_kind != 0 && (access_kind !== expected_kind || address !== expected_address ||
                    write_enable !== expected_write || (write_enable ? write_data : read_data) !== expected_byte)))
                $fatal(1, "CPU_STOP_BUS case=%0d dot=%0d expected=%0d/%04h/%02h actual=%0d/%04h/%02h ack=%02h", scenario, dot_before+1,
                    expected_kind, expected_address, expected_byte, access_kind,address,write_enable ? write_data : read_data,irq_ack);
            $fdisplay(trace,"%0d,%0d,%0d,%04h,%0d,%02h,%0d,%0d",scenario,dot_before+1,access_kind,address,write_enable,write_enable ? write_data : read_data,bus_commit,divider_reset_request);
        end
    endtask

    task automatic check_event;
        if (retirement_valid) begin
            expected = '0;
            expected[0 +: 8] = 1;
            expected[16 +: 32] = 32'(scenario+1);
            expected[48 +: 64] = 64'(event_index);
            expected[304 +: 16] = 16'hfffe;
            expected[360 +: 8] = 1;
            expected[368 +: 8] = event_index >= 2 && pending_case ? 8'd1 : 8'd0;
            expected[376 +: 8] = joyp_selected_active ? 8'd1 : 8'd0;
            case (event_index)
                0: begin
                    expected[112 +: 64]=8; expected[176 +: 16]='h100; expected[192 +: 16]='h101;
                    expected[208 +: 24]=ime_case ? 24'hfb : 24'h00; expected[232 +: 8]=1;
                    expected[328 +: 8]=ime_case ? 8'd1 : 8'd0;
                end
                1: begin
                    expected[112 +: 64]=12; expected[176 +: 16]='h101; expected[192 +: 16]='h102;
                    expected[232 +: 8]=1; expected[320 +: 8]=ime_case ? 8'd1 : 8'd0;
                end
                2: begin
                    expected[112 +: 64]=16; expected[176 +: 16]='h102;
                    expected[192 +: 16]=pending_case ? 16'h103 : 16'h104;
                    expected[208 +: 24]=pending_case ? 24'h10 : 24'h3c10;
                    expected[232 +: 8]=pending_case ? 8'd1 : 8'd2;
                    expected[320 +: 8]=ime_case ? 8'd1 : 8'd0;
                    expected[336 +: 8]=joyp_selected_active && !pending_case ? 8'd1 : 8'd0;
                    expected[344 +: 8]=!joyp_selected_active ? 8'd1 : 8'd0;
                end
                3: begin
                    if (!continue_case) $fatal(1,"CPU_STOP_EXTRA_EVENT case=%0d",scenario);
                    expected[176 +: 16]='h103;
                    if (interrupt_case) begin
                        expected[8 +: 8]=1; expected[112 +: 64]=36;
                        expected[192 +: 16]='h40; expected[304 +: 16]='hfffc; expected[368 +: 8]=0;
                    end else begin
                        expected[112 +: 64]=20; expected[192 +: 16]='h104;
                        expected[208 +: 24]='h3c; expected[232 +: 8]=1; expected[240 +: 8]=1;
                    end
                end
                default: $fatal(1,"CPU_STOP_EXTRA_EVENT case=%0d event=%0d",scenario,event_index);
            endcase
            $fdisplay(records,"%0d,%0d,%096h,%096h",scenario,event_index,expected,retirement);
            if (retirement !== expected)
                $fatal(1,"CPU_STOP_RECORD case=%0d event=%0d expected=%096h actual=%096h",scenario,event_index,expected,retirement);
            event_index = event_index + 1;
        end
    endtask

    task automatic edge_cycle(input bit tick);
        clk_sys=0; gb_tick=tick;
        #4;
        if (reset_sys || core_reset) begin
            if (divider_reset_request || bus_commit) $fatal(1,"CPU_STOP_RESET_COMMIT");
        end else check_bus();
        #1 clk_sys=1;
        #2;
        if (!reset_sys && !core_reset) check_event();
        #3 clk_sys=0;
    endtask

    initial begin
        clk_sys=0; reset_sys=1; core_reset=0; gb_tick=0; profile_id=1; epoch=0; dot_before=0;
        ie=1; iflags=0; buttons=0; response_valid=1; joyp_selected_active=0; wake_request=0;
        corrupt_divider=$test$plusargs("corrupt_divider"); corrupt_action=$test$plusargs("corrupt_action");
        trace=$fopen("stop-bus.csv","w"); records=$fopen("stop-retirement.csv","w");
        if (!trace || !records) $fatal(1,"CPU_STOP_TRACE_OPEN");
        $fdisplay(trace,"case,dot,kind,address,write,data,commit,divider_reset");
        $fdisplay(records,"case,event,expected,actual");
        $dumpfile("waves/cpu-stop.vcd"); $dumpvars(0,tb_cpu_stop);
        for (scenario=0; scenario<8; scenario=scenario+1) begin
            pending_case=(scenario & 2)!=0; ime_case=(scenario & 4)!=0;
            joyp_selected_active=(scenario & 1)!=0;
            continue_case=joyp_selected_active && pending_case;
            interrupt_case=continue_case && ime_case;
            buttons=joyp_selected_active ? 8'd1 : 8'd0;
            ie=1; iflags=0; epoch=32'(scenario+1); event_index=0; divider_count=0;
            for (item=0; item<65536; item=item+1) memory[item]=0;
            memory['h100]=ime_case ? 8'hfb : 8'h00; memory['h101]=0;
            memory['h102]='h10; memory['h103]='h3c;
            reset_sys=1; core_reset=0; edge_cycle(0);
            reset_sys=0; core_reset=1; edge_cycle(0); core_reset=0;
            target_dot=!joyp_selected_active ? 16 : (!pending_case ? 32 : (ime_case ? 36 : 20));
            while (dot_before < 64'(target_dot)) begin
                if (dot_before==14 && pending_case) iflags=1;
                if (scenario==0 && dot_before==15 && corrupt_divider)
                    force dut.stop_policy.divider_reset=1'b0;
                if (scenario==0 && dot_before==15 && corrupt_action)
                    force dut.stop_policy.action=2'd0;
                edge_cycle(1); edge_cycle(0); edge_cycle(0);
            end
            for (quiet=0; quiet<40; quiet=quiet+1) edge_cycle(0);
            if (fault || locked || !initialized || event_index != (continue_case ? 4 : 3) ||
                    divider_count != (joyp_selected_active ? 0 : 1) ||
                    stopped !== !joyp_selected_active || halted !== (joyp_selected_active && !pending_case) || dot_before != 64'(target_dot))
                $fatal(1,"CPU_STOP_FINAL case=%0d events=%0d div=%0d halt=%0d stop=%0d dot=%0d",scenario,event_index,divider_count,halted,stopped,dot_before);
            if (interrupt_case && (memory['hfffd] != 1 || memory['hfffc] != 3)) $fatal(1,"CPU_STOP_STACK");
            core_reset=1; edge_cycle(0);
            if (stopped || halted || retirement_valid || divider_reset_request) $fatal(1,"CPU_STOP_RESET_STATE");
        end
        $fclose(trace); $fclose(records);
        $display("PASS CPU STOP entry cases=8 rows=4 IME_states=2");
        $finish;
    end

    initial begin
        #1000000;
        $fatal(1,"CPU_STOP_TIMEOUT");
    end
endmodule
