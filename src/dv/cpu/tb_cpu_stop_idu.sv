`timescale 1ns/1ps
`default_nettype none

module tb_cpu_stop_idu;
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
    logic [15:0] stop_address;
    logic [15:0] entry_address;
    logic [15:0] expected_address;
    logic [2:0] expected_kind;
    logic [7:0] expected_data;
    integer scenario;
    integer item;
    integer event_index;
    integer commits;
    integer cycles;
    integer effects;
    integer trace;
    integer records;
    bit pending_case;
    bit selected_case;
    bit page_case;
    bit corrupt;

    logic instruction_complete;
    n2m_cpu dut (.*);
    assign read_data=memory[address];
    always @(posedge clk_sys) begin
        if(reset_sys || core_reset) dot_before<=0;
        else if(gb_tick) dot_before<=dot_before+64'd1;
    end
    task automatic check_bus;
        if(irq_ack || fault || write_enable) $fatal(1,"CPU_STOP_IDU_CONTROL");
        if(!gb_tick && (bus_commit || address_effect_sample || divider_reset_request)) $fatal(1,"CPU_STOP_IDU_PAUSE");
        if(gb_tick && dot_before[1:0]==3) begin
            expected_kind=1; expected_address=0; expected_data=0;
            case(dot_before+1)
                4: begin expected_address=16'h100; expected_data=8'hc3; end
                8: begin expected_kind=2; expected_address=16'h101; expected_data=8'hff; end
                12: begin expected_kind=2; expected_address=16'h102; expected_data=page_case ? 8'hfd : 8'h01; end
                16: begin expected_kind=0; end // JP internal M-cycle, independently specified.
                20: begin expected_address=stop_address; expected_data=8'h10; end
                24: begin expected_address=entry_address; expected_data=8'h3c; end
                default: $fatal(1,"CPU_STOP_IDU_EXTRA_CYCLE");
            endcase
            if(bus_commit !== (expected_kind!=0) || (expected_kind!=0 &&
                    (!request_valid || address!==expected_address || access_kind!==expected_kind || read_data!==expected_data)))
                $fatal(1,"CPU_STOP_IDU_BUS case=%0d dot=%0d",scenario,dot_before+1);
            if(dot_before==23) begin
                if(!address_effect_sample || !address_effect_resolved || !address_effect.valid ||
                    address_effect.address!==entry_address || address_effect.known_mask!==16'hffff || !address_effect.write_effect)
                    $fatal(1,"CPU_STOP_ENTRY_IDU case=%0d expected=%04h actual=%04h",scenario,entry_address,address_effect.address);
                if(divider_reset_request!==!selected_case) $fatal(1,"CPU_STOP_IDU_DIVIDER");
                effects=effects+1;
            end
            commits=commits+integer'(bus_commit); cycles=cycles+1;
            $fdisplay(trace,"%0d,%0d,%0d,%04h,%02h,%0d,%04h,%04h,%0d",scenario,dot_before+1,access_kind,address,read_data,address_effect_resolved,address_effect.address,address_effect.known_mask,address_effect.write_effect);
        end else if(bus_commit) $fatal(1,"CPU_STOP_IDU_EARLY");
    endtask
    task automatic check_event;
        if(retirement_valid) begin
            expected='0; expected[0+:8]=1; expected[16+:32]=32'(scenario+1);
            expected[48+:64]=64'(event_index); expected[304+:16]=16'hfffe; expected[360+:8]=1;
            case(event_index)
                0: begin
                    expected[112+:64]=20; expected[176+:16]=16'h100; expected[192+:16]=stop_address;
                    expected[208+:24]=page_case ? 24'hfdffc3 : 24'h01ffc3; expected[232+:8]=3;
                end
                1: begin
                    expected[112+:64]=24; expected[176+:16]=stop_address;
                    expected[192+:16]=pending_case ? entry_address : entry_address+16'd1;
                    expected[208+:24]=pending_case ? 24'h10 : 24'h3c10;
                    expected[232+:8]=pending_case ? 8'd1 : 8'd2;
                    expected[336+:8]=8'(selected_case && !pending_case);
                    expected[344+:8]=8'(!selected_case); expected[368+:8]=8'(pending_case);
                end
                default: $fatal(1,"CPU_STOP_IDU_EXTRA_RECORD");
            endcase
            $fdisplay(records,"%0d,%0d,%096h,%096h",scenario,event_index,expected,retirement);
            if(retirement!==expected) $fatal(1,"CPU_STOP_IDU_RECORD case=%0d event=%0d expected=%096h actual=%096h",scenario,event_index,expected,retirement);
            event_index=event_index+1;
        end
    endtask
    task automatic edge_cycle(input bit tick);
        clk_sys=0; gb_tick=tick; #4;
        if(reset_sys || core_reset) begin
            if(bus_commit || address_effect_sample) $fatal(1,"CPU_STOP_IDU_RESET");
        end else check_bus();
        #1 clk_sys=1; #2;
        if(!reset_sys && !core_reset) check_event();
        #3 clk_sys=0;
    endtask
    initial begin
        clk_sys=0; reset_sys=1; core_reset=0; gb_tick=0; profile_id=1; epoch=0; dot_before=0;
        ie=1; iflags=0; buttons=0; response_valid=1; joyp_selected_active=0; wake_request=0;
        corrupt=$test$plusargs("corrupt"); event_index=0; commits=0; cycles=0; effects=0;
        trace=$fopen("stop-entry-idu.csv","w"); records=$fopen("stop-entry-records.csv","w");
        if(!trace || !records) $fatal(1,"CPU_STOP_IDU_TRACE");
        $fdisplay(trace,"case,dot,kind,address,data,resolved,effect_address,known_mask,write_effect");
        $fdisplay(records,"case,event,expected,actual");
        $dumpfile("waves/cpu-stop-idu.vcd"); $dumpvars(0,clk_sys,reset_sys,core_reset,gb_tick,profile_id,epoch,dot_before,ie,iflags,
            buttons,read_data,response_valid,joyp_selected_active,divider_reset_request,wake_request,
            request_valid,address,write_data,write_enable,access_kind,bus_commit,irq_ack,halted,
            stopped,locked,initialized,fault,ime_observe,ime_delay_observe,stop_execute,
            retirement_valid,retirement,address_effect,address_effect_resolved,address_effect_sample,
            address_effect_phase,instruction_complete);
        edge_cycle(0); reset_sys=0;
        for(scenario=0;scenario<8;scenario=scenario+1) begin
            pending_case=scenario%2!=0; selected_case=(scenario/2)%2!=0; page_case=scenario>=4;
            stop_address=page_case ? 16'hfdff : 16'h01ff;
            entry_address=page_case ? 16'hfe00 : 16'h0200;
            for(item=0;item<65536;item=item+1) memory[item]=0;
            memory['h100]=8'hc3; memory['h101]=8'hff; memory['h102]=page_case ? 8'hfd : 8'h01;
            memory[stop_address]=8'h10; memory[entry_address]=8'h3c;
            event_index=0; commits=0; cycles=0; effects=0; epoch=32'(scenario+1); iflags=0;
            joyp_selected_active=selected_case; core_reset=1; edge_cycle(0); core_reset=0;
            while(dot_before<24) begin
                if(dot_before==20) iflags=5'(pending_case);
                if(corrupt && scenario==4 && dot_before==23) force dut.address_effect.address=16'hfdff;
                edge_cycle(1); release dut.address_effect.address; edge_cycle(0); edge_cycle(0);
            end
            repeat(9) edge_cycle(0);
            if(event_index!=2 || commits!=5 || cycles!=6 || effects!=1 || stopped!==!selected_case || halted!==(selected_case && !pending_case))
                $fatal(1,"CPU_STOP_IDU_TOTAL case=%0d",scenario);
        end
        $fclose(trace); $fclose(records);
        $display("PASS CPU STOP entry IDU cases=8 pages=2 rows=4"); $finish;
    end
    initial begin
        #2000000; $fatal(1,"CPU_STOP_IDU_TIMEOUT");
    end
endmodule
