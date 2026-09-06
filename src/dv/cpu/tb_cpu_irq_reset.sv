`timescale 1ns/1ps
`default_nettype none

module tb_cpu_irq_reset;
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
    integer scenario;
    integer slot;
    integer target_dot;
    integer item;
    integer event_index;
    integer writes;
    integer expected_writes;
    integer trace;
    integer records;
    integer quiet;
    bit global_case;
    bit capture_case;
    bit fresh;
    bit corrupt;

    logic instruction_complete;
    n2m_cpu dut (.*);
    assign read_data=memory[address];
    always @(posedge clk_sys) begin
        if (reset_sys || core_reset) dot_before <= 0;
        else if (gb_tick) dot_before <= dot_before+64'd1;
        if (bus_commit && write_enable) begin memory[address] <= write_data; writes <= writes+1; end
        if (irq_ack!=0) iflags <= iflags & ~irq_ack;
    end

    task automatic check_event;
        if (retirement_valid) begin
            expected='0; expected[0 +: 8]=1; expected[16 +: 32]=epoch;
            expected[48 +: 64]=64'(event_index); expected[304 +: 16]='hfffe; expected[360 +: 8]=1;
            if (fresh) begin
                if (event_index!=0) $fatal(1,"CPU_IRQ_RESET_EXTRA_FRESH");
                expected[112 +: 64]=8; expected[176 +: 16]='h100; expected[192 +: 16]='h101; expected[232 +: 8]=1;
            end else begin
                if (event_index>=3) $fatal(1,"CPU_IRQ_RESET_CANCELED_RECORD");
                expected[112 +: 64]=64'(8+4*event_index);
                expected[176 +: 16]=16'('h100+event_index); expected[192 +: 16]=16'('h101+event_index);
                expected[232 +: 8]=1;
                if (event_index==0) begin expected[208 +: 24]='hfb; expected[328 +: 8]=1; end
                else expected[320 +: 8]=1;
                if (event_index==2) expected[368 +: 8]=1;
            end
            $fdisplay(records,"%0d,%0d,%0d,%096h,%096h",scenario,fresh,event_index,expected,retirement);
            if (retirement!==expected) $fatal(1,"CPU_IRQ_RESET_RECORD case=%0d fresh=%0d event=%0d",scenario,fresh,event_index);
            event_index=event_index+1;
        end
    endtask

    task automatic check_bus;
        if (reset_sys || core_reset) begin
            if (bus_commit || request_valid || address_effect_sample || irq_ack!=0)
                $fatal(1,"CPU_IRQ_RESET_CANCEL case=%0d",scenario);
        end else begin
            if (fault || halted || stopped || locked) $fatal(1,"CPU_IRQ_RESET_STATE");
            if (!gb_tick && (bus_commit || address_effect_sample)) $fatal(1,"CPU_IRQ_RESET_PAUSE");
            if (address_effect_phase!==dot_before[1:0]) $fatal(1,"CPU_IRQ_RESET_PHASE");
            if (gb_tick && dot_before[1:0]==3) begin
                expected_kind=1; expected_address=16'('h100+int'(dot_before)/4); expected_write=0; expected_byte=0;
                if (!fresh) begin
                    case (dot_before+1)
                        20,24: expected_kind=0;
                        28: begin expected_kind=4; expected_address='hfffd; expected_write=1; expected_byte=1; end
                        32: begin expected_kind=4; expected_address='hfffc; expected_write=1; expected_byte=3; end
                        36: begin expected_kind=1; expected_address='h40; end
                        default: begin end
                    endcase
                end
                if (!expected_write) expected_byte=memory[expected_address];
                if (bus_commit!==(expected_kind!=0) ||
                        (expected_kind!=0 && (access_kind!==expected_kind || address!==expected_address ||
                        write_enable!==expected_write || (write_enable ? write_data : read_data)!==expected_byte)))
                    $fatal(1,"CPU_IRQ_RESET_BUS case=%0d dot=%0d",scenario,dot_before+1);
            end
        end
        $fdisplay(trace,"%0d,%0d,%0d,%0d,%0d,%04h,%0d,%0d",scenario,fresh,dot_before,
            reset_sys,core_reset,address,bus_commit,address_effect_sample);
    endtask

    task automatic edge_cycle(input bit tick);
        clk_sys=0; gb_tick=tick; #4; check_bus();
        #1 clk_sys=1; #2;
        if (!reset_sys && !core_reset) check_event();
        #3 clk_sys=0;
    endtask

    initial begin
        clk_sys=0; reset_sys=1; core_reset=0; gb_tick=0; profile_id=1; epoch=0; dot_before=0;
        ie=1; iflags=0; buttons=0; response_valid=1; joyp_selected_active=0; wake_request=0;
        corrupt=$test$plusargs("corrupt"); writes=0;
        trace=$fopen("irq-reset-bus.csv","w"); records=$fopen("irq-reset-retirement.csv","w");
        if (!trace || !records) $fatal(1,"CPU_IRQ_RESET_TRACE_OPEN");
        $fdisplay(trace,"case,fresh,dot,global_reset,core_reset,address,commit,effect_sample");
        $fdisplay(records,"case,fresh,event,expected,actual");
        $dumpfile("waves/cpu-irq-reset.vcd"); $dumpvars(0,tb_cpu_irq_reset);
        for (scenario=0; scenario<42; scenario=scenario+1) begin
            slot=scenario%21; global_case=scenario>=21; capture_case=slot==20;
            target_dot=16+slot; expected_writes=(target_dot>=28 ? 1 : 0)+(target_dot>=32 ? 1 : 0);
            for (item=0; item<65536; item=item+1) memory[item]=0;
            memory['h100]='hfb;
            epoch=32'(2*scenario+1); event_index=0; fresh=0; iflags=0; response_valid=1; writes=0;
            reset_sys=1; core_reset=0; edge_cycle(0); reset_sys=0; core_reset=1; edge_cycle(0); core_reset=0;
            while (dot_before<64'(target_dot)) begin
                if (dot_before==14) iflags=1;
                if (dot_before==32 && !capture_case) response_valid=0;
                edge_cycle(1);
                if (!(capture_case && dot_before==36)) begin edge_cycle(0); edge_cycle(0); end
            end
            if (target_dot>=32 && !capture_case) response_valid=0;
            // Do not publish the captured IRQ in the two trailing-edge cases.
            if (!capture_case) for (quiet=0; quiet<12; quiet=quiet+1) edge_cycle(0);
            if (dot_before!==64'(target_dot) || event_index!=3 || writes!=expected_writes)
                $fatal(1,"CPU_IRQ_RESET_HELD case=%0d writes=%0d expected=%0d",scenario,writes,expected_writes);
            if (global_case) reset_sys=1; else core_reset=1;
            if (corrupt && scenario==19) force dut.u_bus.commit=1'b1;
            #2; check_bus();
            if (global_case && (initialized || retirement_valid || address_effect_phase!=0))
                $fatal(1,"CPU_IRQ_RESET_ASYNC");
            edge_cycle(1);
            if (retirement_valid || halted || stopped || locked || fault || address_effect_phase!=0)
                $fatal(1,"CPU_IRQ_RESET_CLEARED");
            if (writes!=expected_writes || memory['hfffd] !== (expected_writes>=1 ? 8'd1 : 8'd0) ||
                    memory['hfffc] !== (expected_writes>=2 ? 8'd3 : 8'd0))
                $fatal(1,"CPU_IRQ_RESET_COMMITTED_MEMORY");
            iflags=0; response_valid=1; memory['h100]=0;
            fresh=1; event_index=0; epoch=32'(2*scenario+2);
            if (global_case) begin reset_sys=0; core_reset=1; edge_cycle(0); end
            core_reset=0;
            while (dot_before<8) begin edge_cycle(1); edge_cycle(0); edge_cycle(0); end
            if (event_index!=1 || writes!=expected_writes || ime_observe || ime_delay_observe)
                $fatal(1,"CPU_IRQ_RESET_FRESH");
        end
        $fclose(trace); $fclose(records);
        $display("PASS CPU IRQ reset cases=42 phases=4 entry_cycles=5 captured_cancel=2");
        $finish;
    end
    initial begin
        #4000000;
        $fatal(1,"CPU_IRQ_RESET_TIMEOUT");
    end
endmodule
