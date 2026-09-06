`timescale 1ns/1ps
`default_nettype none

// Scripted CPU inputs prove sampling boundaries, not peripheral collision rules.
module tb_cpu_if_observation;
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
    integer recognition_dot;
    integer elapsed;
    integer event_count;
    integer trace;
    integer records;
    bit corrupt;

    logic instruction_complete;
    n2m_cpu dut (.*);
    assign read_data=memory[address];
    always @(posedge clk_sys) begin
        if (reset_sys || core_reset) dot_before <= 0;
        else if (gb_tick) dot_before <= dot_before+64'd1;
        if (bus_commit && write_enable) memory[address] <= write_data;
        if (irq_ack!=0) iflags <= iflags & ~irq_ack;
    end

    task automatic check_bus;
        if (!gb_tick && (bus_commit || address_effect_sample)) $fatal(1,"CPU_IF_PAUSE_EFFECT");
        if (gb_tick && dot_before[1:0]==3) begin
            expected_kind=1; expected_address=16'('h100+int'(dot_before)/4);
            expected_write=0; expected_ack=0; expected_byte=0;
            if (dot_before+1 > 64'(recognition_dot)) begin
                elapsed=int'(dot_before+1)-recognition_dot; expected_kind=0;
                case (elapsed)
                    12: begin expected_kind=4; expected_address='hfffd; expected_write=1; expected_byte=1; end
                    16: begin
                        expected_kind=4; expected_address='hfffc; expected_write=1;
                        expected_byte=scenario==1 ? 8'h04 : 8'h03;
                        expected_ack=scenario==0 ? 0 : (scenario==1 ? 5'd1 : 5'd2);
                    end
                    20: begin expected_kind=1; expected_address=scenario==0 ? 0 : (scenario==1 ? 16'h40 : 16'h48); end
                    default: begin end
                endcase
            end
            if (!expected_write) expected_byte=memory[expected_address];
            if (bus_commit!==(expected_kind!=0) || irq_ack!==expected_ack ||
                    (expected_kind!=0 && (access_kind!==expected_kind || address!==expected_address ||
                    write_enable!==expected_write || (write_enable ? write_data : read_data)!==expected_byte)))
                $fatal(1,"CPU_IF_BUS case=%0d dot=%0d expected=%0d/%04h actual=%0d/%04h ack=%02h",scenario,dot_before+1,expected_kind,expected_address,access_kind,address,irq_ack);
            $fdisplay(trace,"%0d,%0d,%0d,%04h,%0d,%02h,%0d,%02h,%02h,%02h",scenario,dot_before+1,
                access_kind,address,write_enable,write_enable ? write_data : read_data,bus_commit,irq_ack,ie,iflags);
        end
    endtask

    task automatic check_event;
        if (retirement_valid) begin
            if (event_index>=event_count) $fatal(1,"CPU_IF_EXTRA_EVENT");
            expected='0; expected[0 +: 8]=1; expected[16 +: 32]=32'(scenario+1);
            expected[48 +: 64]=64'(event_index); expected[304 +: 16]='hfffe;
            expected[360 +: 8]=(event_index>=2 && scenario==2) ? 8'd2 : 8'd1;
            if (event_index>=2) begin
                expected[368 +: 8]=scenario==0 ? 0 : (scenario==1 ? 8'd1 : 8'd2);
                expected[376 +: 8]='h5a;
            end
            if (event_index==event_count-1) begin
                expected[8 +: 8]=1; expected[112 +: 64]=64'(recognition_dot+20);
                expected[176 +: 16]=scenario==1 ? 16'h104 : 16'h103;
                expected[192 +: 16]=scenario==0 ? 0 : (scenario==1 ? 16'h40 : 16'h48);
                expected[304 +: 16]='hfffc; expected[368 +: 8]=0;
            end else begin
                expected[112 +: 64]=64'(8+4*event_index);
                expected[176 +: 16]=16'('h100+event_index); expected[192 +: 16]=16'('h101+event_index);
                expected[232 +: 8]=1;
                if (event_index==0) begin expected[208 +: 24]='hfb; expected[328 +: 8]=1; end
                else expected[320 +: 8]=1;
            end
            $fdisplay(records,"%0d,%0d,%096h,%096h",scenario,event_index,expected,retirement);
            if (retirement!==expected) $fatal(1,"CPU_IF_RECORD case=%0d event=%0d expected=%096h actual=%096h",scenario,event_index,expected,retirement);
            event_index=event_index+1;
        end
    endtask

    task automatic edge_cycle(input bit tick);
        clk_sys=0; gb_tick=tick; #4;
        if (reset_sys || core_reset) begin if (bus_commit || address_effect_sample) $fatal(1,"CPU_IF_RESET"); end
        else check_bus();
        #1 clk_sys=1; #1;
        // A has captured the instruction. These resolved owner observations
        // become visible before B; they cannot retroactively change T3 capture.
        if (!reset_sys && !core_reset && tick && dot_before==16) begin
            iflags=scenario==0 ? 0 : (scenario==1 ? 5'd1 : 5'd2);
            ie=scenario==2 ? 8'd2 : 8'd1; buttons='h5a;
            if (corrupt && scenario==1) force dut.u_retire.retirement_b_next.iflags=8'h00;
        end
        #1;
        if (!reset_sys && !core_reset) check_event();
        #3 clk_sys=0;
    endtask

    initial begin
        clk_sys=0; reset_sys=1; core_reset=0; gb_tick=0; profile_id=1; epoch=0; dot_before=0;
        ie=1; iflags=0; buttons=0; response_valid=1; joyp_selected_active=0; wake_request=0;
        corrupt=$test$plusargs("corrupt");
        trace=$fopen("if-observation-bus.csv","w"); records=$fopen("if-observation-retirement.csv","w");
        if (!trace || !records) $fatal(1,"CPU_IF_TRACE_OPEN");
        $fdisplay(trace,"case,dot,kind,address,write,data,commit,ack,ie,iflags");
        $fdisplay(records,"case,event,expected,actual");
        $dumpfile("waves/cpu-if-observation.vcd"); $dumpvars(0,clk_sys,reset_sys,core_reset,gb_tick,profile_id,epoch,dot_before,ie,iflags,
            buttons,read_data,response_valid,joyp_selected_active,divider_reset_request,wake_request,
            request_valid,address,write_data,write_enable,access_kind,bus_commit,irq_ack,halted,
            stopped,locked,initialized,fault,ime_observe,ime_delay_observe,stop_execute,
            retirement_valid,retirement,address_effect,address_effect_resolved,address_effect_sample,
            address_effect_phase,instruction_complete);
        for (scenario=0; scenario<3; scenario=scenario+1) begin
            for (item=0; item<65536; item=item+1) memory[item]=0;
            memory['h100]='hfb;
            ie=1; iflags=0; buttons=0; epoch=32'(scenario+1); event_index=0;
            recognition_dot=scenario==1 ? 20 : 16; event_count=scenario==1 ? 5 : 4;
            reset_sys=1; core_reset=0; edge_cycle(0); reset_sys=0; core_reset=1; edge_cycle(0); core_reset=0;
            while (dot_before<64'(recognition_dot+20)) begin
                if (dot_before==14 && scenario!=1) iflags=1;
                edge_cycle(1); edge_cycle(0); edge_cycle(0);
            end
            if (event_index!=event_count || fault || halted || locked || stopped)
                $fatal(1,"CPU_IF_FINAL case=%0d events=%0d",scenario,event_index);
        end
        $fclose(trace); $fclose(records);
        $display("PASS CPU IF observation cases=3 records=13 T3_A_B_separate=1");
        $finish;
    end
    initial begin
        #2000000;
        $fatal(1,"CPU_IF_TIMEOUT");
    end
endmodule
