`timescale 1ns/1ps
`default_nettype none

// Original public-stream contrast: six NOPs versus IRQ entry plus JP HL.
module tb_cpu_wake;
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
    logic [4:0] expected_ack;
    integer scenario;
    integer item;
    integer event_index;
    integer wake_dot;
    integer elapsed;
    integer relative_event;
    integer trace;
    integer records;
    integer quiet;
    integer phase_probe;
    bit ime_case;
    bit modified_case;
    bit missing;
    bit stale;

    logic instruction_complete;
    n2m_cpu dut (.*);
    assign read_data = memory[address];
    always @(posedge clk_sys) begin
        if (reset_sys || core_reset) dot_before <= 0;
        else if (gb_tick) dot_before <= dot_before + 64'd1;
        if (bus_commit && write_enable) memory[address] <= write_data;
        if (irq_ack != 0) iflags <= iflags & ~irq_ack;
        // Same-edge peripheral arrival is after the closing T3 snapshot.
        if (gb_tick && dot_before == 34 && scenario % 3 == 1) iflags <= 1;
    end

    task automatic check_bus;
        if (!gb_tick && (bus_commit || address_effect_sample)) $fatal(1,"CPU_WAKE_PAUSE_EFFECT");
        if (fault) $fatal(1,"CPU_WAKE_UNUSED_RESPONSE_FAULT");
        if (dot_before >= 28 && dot_before < 64'(wake_dot)) begin
            if (!request_valid || address !== 16'h106 || write_enable || access_kind !== 1 ||
                    !address_effect_resolved || !address_effect.valid ||
                    address_effect.address !== 16'h106 || address_effect.known_mask !== 16'hffff)
                $fatal(1,"CPU_WAKE_PREPARE case=%0d dot=%0d",scenario,dot_before);
        end
        if (gb_tick && dot_before[1:0] == 3) begin
            expected_kind=0; expected_address=0; expected_byte=0; expected_write=0; expected_ack=0;
            case (dot_before+1)
                4: begin expected_kind=1; expected_address='h100; end
                8: begin expected_kind=2; expected_address='h101; end
                12: begin expected_kind=2; expected_address='h102; end
                16: begin expected_kind=1; expected_address='h103; end
                20: begin expected_kind=1; expected_address='h104; end
                24: begin expected_kind=1; expected_address='h105; end
                28: begin expected_kind=1; expected_address='h106; end
                default: begin end
            endcase
            if (dot_before+1 == 64'(wake_dot)) begin expected_kind=1; expected_address='h106; end
            if (dot_before+1 > 64'(wake_dot)) begin
                elapsed=int'(dot_before+1)-wake_dot;
                if (!ime_case && elapsed <= 24) begin expected_kind=1; expected_address=16'('h106+elapsed/4); end
                if (ime_case) begin
                    case (elapsed)
                        12: begin expected_kind=4; expected_address='hfffd; expected_write=1; expected_byte=1; end
                        16: begin expected_kind=4; expected_address='hfffc; expected_write=1; expected_byte=6; expected_ack=1; end
                        20: begin expected_kind=1; expected_address='h40; end
                        24: begin expected_kind=1; expected_address='h10c; end
                        default: begin end
                    endcase
                end
                case (elapsed)
                    28: begin expected_kind=2; expected_address='h10d; end
                    32: begin expected_kind=3; expected_address='hff04; end
                    36: begin expected_kind=1; expected_address='h10e; end
                    default: begin end
                endcase
            end
            if (!expected_write) expected_byte=memory[expected_address];
            if (missing && scenario==0 && dot_before+1 == 64'(wake_dot)) begin
                if (bus_commit || address_effect_sample) $fatal(1,"CPU_WAKE_MISSING_NOT_SUPPRESSED");
                $display("CPU_WAKE_MISSING_SUPPRESSED dot=%0d",dot_before+1);
            end else if (bus_commit !== (expected_kind!=0) || irq_ack !== expected_ack ||
                    (expected_kind!=0 && (access_kind !== expected_kind || address !== expected_address ||
                    write_enable !== expected_write || (write_enable ? write_data : read_data) !== expected_byte)))
                $fatal(1,"CPU_WAKE_BUS case=%0d dot=%0d expected=%0d/%04h actual=%0d/%04h commit=%0d",
                    scenario,dot_before+1,expected_kind,expected_address,access_kind,address,bus_commit);
            if (dot_before >= 28 && dot_before+1 < 64'(wake_dot) && address_effect_sample)
                $fatal(1,"CPU_WAKE_SLEEP_EFFECT");
            $fdisplay(trace,"%0d,%0d,%0d,%04h,%0d,%02h,%0d,%0d,%04h",scenario,dot_before+1,
                access_kind,address,write_enable,write_enable ? write_data : read_data,bus_commit,address_effect_sample,address_effect.address);
        end
    endtask

    task automatic check_event;
        if (retirement_valid) begin
            expected='0;
            expected[0 +: 8]=1; expected[16 +: 32]=32'(scenario+1);
            expected[48 +: 64]=64'(event_index); expected[304 +: 16]='hfffe;
            expected[288 +: 8]=1; expected[296 +: 8]='h0c;
            expected[360 +: 8]=1;
            if (event_index < 4) begin
                expected[112 +: 64]=64'(16+4*event_index);
                expected[176 +: 16]=event_index==0 ? 16'h100 : 16'('h102+event_index);
                expected[192 +: 16]=16'('h103+event_index);
                expected[232 +: 8]=event_index==0 ? 8'd3 : 8'd1;
                case (event_index)
                    0: expected[208 +: 24]='h010c21;
                    1: begin expected[208 +: 24]=ime_case ? 24'hfb : 0; expected[328 +: 8]=ime_case ? 8'd1 : 0; end
                    2: expected[320 +: 8]=ime_case ? 8'd1 : 0;
                    3: begin expected[208 +: 24]='h76; expected[320 +: 8]=ime_case ? 8'd1 : 0; expected[336 +: 8]=1; end
                    default: begin end
                endcase
            end else begin
                relative_event=event_index-4;
                expected[368 +: 8]=ime_case ? 0 : 8'd1;
                if (!ime_case && relative_event < 6) begin
                    expected[112 +: 64]=64'(wake_dot+4*(relative_event+1));
                    expected[176 +: 16]=16'('h106+relative_event);
                    expected[192 +: 16]=16'('h107+relative_event);
                    expected[232 +: 8]=1;
                    if (modified_case) begin
                        expected[240 +: 8]=1;
                        if (relative_event==0) expected[208 +: 24]='h3c;
                    end
                end else if (ime_case && relative_event < 2) begin
                    expected[304 +: 16]='hfffc;
                    expected[112 +: 64]=64'(wake_dot+20+4*relative_event);
                    if (relative_event==0) begin
                        expected[8 +: 8]=1; expected[176 +: 16]='h106; expected[192 +: 16]='h40;
                    end else begin
                        expected[176 +: 16]='h40; expected[192 +: 16]='h10c;
                        expected[208 +: 24]='he9; expected[232 +: 8]=1;
                    end
                end else begin
                    if (relative_event != (ime_case ? 2 : 6)) $fatal(1,"CPU_WAKE_EXTRA_EVENT");
                    expected[112 +: 64]=64'(wake_dot+36);
                    expected[176 +: 16]='h10c; expected[192 +: 16]='h10e;
                    expected[208 +: 24]='h04f0; expected[232 +: 8]=2;
                    expected[240 +: 8]='h5a;
                    if (ime_case) expected[304 +: 16]='hfffc;
                end
            end
            $fdisplay(records,"%0d,%0d,%096h,%096h",scenario,event_index,expected,retirement);
            if (retirement !== expected) $fatal(1,"CPU_WAKE_RECORD case=%0d event=%0d expected=%096h actual=%096h",scenario,event_index,expected,retirement);
            event_index=event_index+1;
        end
    endtask

    task automatic edge_cycle(input bit tick);
        clk_sys=0; gb_tick=tick; #4;
        if (reset_sys || core_reset) begin
            if (bus_commit || address_effect_sample || request_valid) $fatal(1,"CPU_WAKE_RESET_EFFECT");
        end else check_bus();
        #1 clk_sys=1; #2;
        if (!reset_sys && !core_reset) check_event();
        #3 clk_sys=0;
    endtask

    initial begin
        clk_sys=0; reset_sys=1; core_reset=0; gb_tick=0; profile_id=1; epoch=0; dot_before=0;
        ie=1; iflags=0; buttons=0; response_valid=1; joyp_selected_active=0; wake_request=0;
        missing=$test$plusargs("missing"); stale=$test$plusargs("stale");
        trace=$fopen("wake-bus.csv","w"); records=$fopen("wake-retirement.csv","w");
        if (!trace || !records) $fatal(1,"CPU_WAKE_TRACE_OPEN");
        $fdisplay(trace,"case,dot,kind,address,write,data,commit,effect_sample,effect_address");
        $fdisplay(records,"case,event,expected,actual");
        $dumpfile("waves/cpu-wake.vcd"); $dumpvars(0,tb_cpu_wake);
        for (scenario=0; scenario<7; scenario=scenario+1) begin
            ime_case=scenario>=3 && scenario<6; modified_case=scenario==6;
            wake_dot=scenario%3==0 ? 36 : 40;
            for (item=0; item<65536; item=item+1) memory[item]=0;
            memory['h100]='h21; memory['h101]='h0c; memory['h102]=1;
            memory['h103]=ime_case ? 8'hfb : 0; memory['h105]='h76;
            memory['h10c]='hf0; memory['h10d]=4; memory['h10e]='h76;
            memory['h40]='he9; memory['hff04]='h5a;
            ie=1; iflags=0; epoch=32'(scenario+1); event_index=0; response_valid=1;
            reset_sys=1; core_reset=0; edge_cycle(0);
            reset_sys=0; core_reset=1; edge_cycle(0); core_reset=0;
            while (dot_before < 64'(wake_dot+36)) begin
                if (dot_before==28) response_valid=0;
                if (dot_before==30 && modified_case) memory['h106]='h3c;
                if (dot_before==34 && scenario%3==0) iflags=1;
                if (dot_before==35 && scenario%3==2) iflags=1;
                if (dot_before==64'(wake_dot-1)) response_valid=!(missing && scenario==0);
                if (dot_before>=28 && dot_before<32)
                    for (quiet=0; quiet<8; quiet=quiet+1) edge_cycle(0);
                if (stale && modified_case && dot_before==64'(wake_dot-1)) force dut.u_control.control_next.opcode=8'h00;
                edge_cycle(1);
                if (stale && modified_case && dot_before==64'(wake_dot)) release dut.u_control.control_next.opcode;
                edge_cycle(0); edge_cycle(0);
            end
            if (event_index != (ime_case ? 7 : 11) || fault || halted || stopped || locked)
                $fatal(1,"CPU_WAKE_FINAL case=%0d events=%0d",scenario,event_index);
        end
        $fclose(trace); $fclose(records);
        $display("PASS CPU HALT wake cases=7 arrival_edges=3 IME_states=2 fresh_opcode=1");
        $finish;
    end
    initial begin
        #2000000;
        $fatal(1,"CPU_WAKE_TIMEOUT");
    end
endmodule
