`timescale 1ns/1ps
`default_nettype none

module tb_cpu_stop_wake;
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
    logic [15:0] expected_address;
    integer scenario;
    integer item;
    integer event_index;
    integer commits;
    integer effects;
    integer phase_case;
    integer records;
    integer trace;
    bit ime_case;
    bit global_case;
    bit fresh;
    bit corrupt;

    logic instruction_complete;
    n2m_cpu dut (.*);
    assign read_data = memory[address];
    always @(posedge clk_sys) begin
        if (reset_sys || core_reset) dot_before <= 0;
        else if (gb_tick) dot_before <= dot_before + 64'd1;
    end

    task automatic check_bus;
        if (irq_ack || write_enable || fault || locked) $fatal(1,"CPU_STOP_WAKE_CONTROL case=%0d",scenario);
        if (!gb_tick && (bus_commit || address_effect_sample)) $fatal(1,"CPU_STOP_WAKE_PAUSE");
        if (gb_tick && ((dot_before+1)%4==0)) begin
            expected_address = fresh ? 16'h100 + 16'((dot_before+1)/4-1) :
                (dot_before < 16 ? 16'h100 + 16'((dot_before+1)/4-1) : 16'h104 + 16'((dot_before-16)/4));
            if (!bus_commit || !request_valid || access_kind!=n2m_cpu_pkg::ACCESS_OPCODE || address!==expected_address)
                $fatal(1,"CPU_STOP_WAKE_BUS case=%0d dot=%0d expected=%04h actual=%04h commit=%0d",scenario,dot_before+1,expected_address,address,bus_commit);
            // Entry's analog/pending mapping is separate. Every restarted normal
            // fetch has its own fully known increment observation.
            if (fresh || dot_before>=16) begin
                if (!address_effect_sample || !address_effect_resolved || !address_effect.valid ||
                    address_effect.address!==expected_address || address_effect.known_mask!==16'hffff || !address_effect.write_effect)
                    $fatal(1,"CPU_STOP_WAKE_IDU case=%0d dot=%0d",scenario,dot_before+1);
                effects=effects+1;
            end
            commits=commits+1;
            $fdisplay(trace,"%0d,%0d,%04h,%02h,%0d,%04h,%04h",scenario,dot_before+1,address,read_data,address_effect_resolved,address_effect.address,address_effect.known_mask);
        end else if (bus_commit) $fatal(1,"CPU_STOP_WAKE_EARLY");
    endtask

    task automatic check_event;
        if (retirement_valid) begin
            expected='0;
            expected[0+:8]=1; expected[16+:32]=epoch; expected[48+:64]=64'(event_index);
            expected[304+:16]=16'hfffe; expected[360+:8]=ie;
            if (fresh) begin
                expected[112+:64]=8; expected[176+:16]=16'h100; expected[192+:16]=16'h101; expected[232+:8]=1;
                if (event_index!=0) $fatal(1,"CPU_STOP_WAKE_RESET_EXTRA");
            end else begin
                case(event_index)
                    0: begin
                        expected[112+:64]=8; expected[176+:16]=16'h100; expected[192+:16]=16'h101;
                        expected[208+:24]=ime_case ? 24'hfb : 0; expected[232+:8]=1; expected[328+:8]=8'(ime_case);
                    end
                    1: begin
                        expected[112+:64]=12; expected[176+:16]=16'h101; expected[192+:16]=16'h102;
                        expected[232+:8]=1; expected[320+:8]=8'(ime_case);
                    end
                    2: begin
                        expected[112+:64]=16; expected[176+:16]=16'h102; expected[192+:16]=16'h104;
                        expected[208+:24]=24'h10; expected[232+:8]=2; expected[320+:8]=8'(ime_case); expected[344+:8]=1;
                    end
                    3,4: begin
                        expected[112+:64]=event_index==3 ? 24 : 28;
                        expected[176+:16]=event_index==3 ? 16'h104 : 16'h105;
                        expected[192+:16]=event_index==3 ? 16'h105 : 16'h106;
                        expected[208+:24]=event_index==3 ? 24'h3c : 0;
                        expected[232+:8]=1; expected[240+:8]=1; expected[320+:8]=8'(ime_case);
                    end
                    default: $fatal(1,"CPU_STOP_WAKE_EXTRA case=%0d",scenario);
                endcase
            end
            $fdisplay(records,"%0d,%0d,%096h,%096h",scenario,event_index,expected,retirement);
            if(retirement!==expected) $fatal(1,"CPU_STOP_WAKE_RECORD case=%0d event=%0d expected=%096h actual=%096h",scenario,event_index,expected,retirement);
            event_index=event_index+1;
        end
    endtask

    task automatic edge_cycle(input bit tick);
        clk_sys=0; gb_tick=tick;
        #4;
        if(reset_sys || core_reset) begin
            if(bus_commit || address_effect_sample || divider_reset_request) $fatal(1,"CPU_STOP_WAKE_RESET_COMMIT");
        end else check_bus();
        #1 clk_sys=1;
        #2;
        if(!reset_sys && !core_reset) check_event();
        #3 clk_sys=0;
    endtask

    initial begin
        clk_sys=0; reset_sys=1; core_reset=0; gb_tick=0; profile_id=1; epoch=0; dot_before=0;
        ie=0; iflags=0; buttons=0; response_valid=1; joyp_selected_active=0; wake_request=0;
        corrupt=$test$plusargs("corrupt"); fresh=0; event_index=0; commits=0; effects=0;
        trace=$fopen("stop-wake-bus.csv","w"); records=$fopen("stop-wake-records.csv","w");
        if(!trace || !records) $fatal(1,"CPU_STOP_WAKE_TRACE");
        $fdisplay(trace,"case,dot,address,data,resolved,effect_address,known_mask");
        $fdisplay(records,"case,event,expected,actual");
        $dumpfile("waves/cpu-stop-wake.vcd"); $dumpvars(0,tb_cpu_stop_wake);
        edge_cycle(0); reset_sys=0;
        for(scenario=0;scenario<20;scenario=scenario+1) begin
            ime_case=scenario%2!=0; global_case=((scenario-4)/2)%2!=0;
            phase_case=(scenario-4)/4;
            for(item=0;item<65536;item=item+1) memory[item]=0;
            memory['h100]=ime_case ? 8'hfb : 0; memory['h102]=8'h10;
            // Change the resumed opcode only after STOP has entered.
            fresh=0; event_index=0; commits=0; effects=0; ie=scenario<2 ? 0 : 8'h10;
            epoch=32'(scenario*2+1); core_reset=1; edge_cycle(0); core_reset=0;
            while(dot_before<16) begin edge_cycle(1); edge_cycle(0); edge_cycle(0); end
            if(!stopped || event_index!=3 || commits!=4) $fatal(1,"CPU_STOP_WAKE_ENTRY");
            response_valid=0;
            repeat(9) edge_cycle(0);
            if(!stopped || commits!=4 || event_index!=3) $fatal(1,"CPU_STOP_WAKE_SLEEP");
            memory['h104]=8'h3c;
            // The enclosing owner retained a selected-line pulse and now reports
            // qualified stable clocks. Raw selected lines may already be high.
            wake_request=1; edge_cycle(0); wake_request=0;
            repeat(7) edge_cycle(0);
            if(stopped || !request_valid || address!=16'h104 || commits!=4) $fatal(1,"CPU_STOP_WAKE_PREPARE");
            response_valid=1;
            if(scenario<4) begin
                while(dot_before<28) begin
                    if(corrupt && scenario==0 && dot_before==19) force dut.read_data=8'h00;
                    edge_cycle(1); release dut.read_data; edge_cycle(0); edge_cycle(0);
                end
                if(event_index!=5 || commits!=7 || effects!=3) $fatal(1,"CPU_STOP_WAKE_TOTAL");
            end else begin
                repeat(phase_case) begin edge_cycle(1); edge_cycle(0); edge_cycle(0); end
                repeat(5) edge_cycle(0);
                if(global_case) reset_sys=1; else core_reset=1;
                edge_cycle(1);
                if(retirement_valid || stopped || halted || address_effect_phase!=0) $fatal(1,"CPU_STOP_WAKE_RESET_STATE");
                reset_sys=0; core_reset=1; memory['h100]=0; fresh=1; event_index=0; epoch=32'(scenario*2+2);
                edge_cycle(0); core_reset=0;
                while(dot_before<8) begin edge_cycle(1); edge_cycle(0); edge_cycle(0); end
                if(event_index!=1 || ime_observe || ime_delay_observe) $fatal(1,"CPU_STOP_WAKE_FRESH");
            end
        end
        $fclose(trace); $fclose(records);
        $display("PASS CPU normal STOP wake cases=20 normal=4 reset=16"); $finish;
    end
    initial begin
        #3000000;
        $fatal(1,"CPU_STOP_WAKE_TIMEOUT");
    end
endmodule
