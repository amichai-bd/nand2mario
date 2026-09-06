`timescale 1ns/1ps
`default_nettype none

module tb_cpu_reset;
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
    logic [15:0] before_pc [5];
    logic [15:0] after_pc [5];
    logic [23:0] opcodes [5];
    logic [63:0] event_dots [5];
    logic held_request;
    logic held_write;
    logic [15:0] held_address;
    logic [7:0] held_data;
    logic [63:0] held_dot;
    integer scenario;
    integer phase_case;
    integer cycle;
    integer item;
    integer pause_cycle;
    integer write_count;
    integer event_index;
    integer trace;
    bit fresh;
    bit corrupt;

    logic instruction_complete;
    n2m_cpu dut (.*);
    assign read_data=memory[address];
    always @(posedge clk_sys) begin
        if (reset_sys || core_reset) dot_before<=0;
        else if (gb_tick) dot_before<=dot_before+64'd1;
        if (bus_commit && write_enable) begin
            memory[address]<=write_data;
            write_count=write_count+1;
        end
    end

    task automatic check_bus;
        if (bus_commit && (!gb_tick || dot_before[1:0]!=3))
            $fatal(1,"CPU_RESET_EARLY_COMMIT case=%0d dot=%0d",scenario,dot_before+1);
        if (gb_tick && (dot_before==19 || dot_before==31)) begin
            if (!bus_commit || !write_enable || address!==16'hc000 ||
                write_data!==(dot_before==31 ? 8'h01 : 8'h00))
                $fatal(1,"CPU_RESET_WRITE case=%0d dot=%0d",scenario,dot_before+1);
        end
        if (bus_commit && write_enable) begin
            $fdisplay(trace,"write,%0d,%0d,%0d,%04h,%02h",scenario,epoch,dot_before+1,address,write_data);
            if (address!==16'hc000 || write_data!==(write_count==2 ? 8'h01 : 8'h00))
                $fatal(1,"CPU_RESET_WRITE_ORDER case=%0d count=%0d",scenario,write_count);
        end
    endtask

    task automatic check_event;
        if (fresh && retirement_valid) begin
            if (event_index>=5) $fatal(1,"CPU_RESET_EXTRA_EVENT");
            expected='0;
            expected[0 +: 8]=1;
            expected[16 +: 32]=32'(scenario+101);
            expected[48 +: 64]=64'(event_index);
            expected[112 +: 64]=event_dots[event_index];
            expected[176 +: 16]=before_pc[event_index];
            expected[192 +: 16]=after_pc[event_index];
            expected[208 +: 24]=opcodes[event_index];
            expected[232 +: 8]=event_index==0 ? 3 : 1;
            expected[240 +: 8]=event_index>=2 ? 1 : 0;
            expected[288 +: 16]=16'h00c0;
            expected[304 +: 16]=16'hfffe;
            if (event_index==4) expected[336 +: 8]=1;
            $fdisplay(trace,"event,%0d,%0d,%096h,%096h",scenario,event_index,expected,retirement);
            if (retirement!==expected)
                $fatal(1,"CPU_RESET_EVENT case=%0d event=%0d expected=%096h actual=%096h",
                    scenario,event_index,expected,retirement);
            event_index=event_index+1;
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
        clk_sys=0; reset_sys=1; core_reset=0; gb_tick=0; profile_id=1;
        epoch=1; dot_before=0; ie=0; iflags=0; buttons=0;
        response_valid=1; joyp_selected_active=0; wake_request=0;
        write_count=0; event_index=0; fresh=0;
        corrupt=$test$plusargs("corrupt");
        before_pc='{16'h100,16'h103,16'h104,16'h105,16'h106};
        after_pc='{16'h103,16'h104,16'h105,16'h106,16'h107};
        opcodes='{24'hc00021,24'h77,24'h3c,24'h77,24'h76};
        event_dots='{64'd16,64'd24,64'd28,64'd36,64'd40};
        trace=$fopen("reset-trace.csv","w");
        if (!trace) $fatal(1,"CPU_RESET_TRACE_OPEN");
        $dumpfile("waves/cpu-reset.vcd");
        $dumpvars(0,clk_sys,reset_sys,core_reset,gb_tick,profile_id,epoch,dot_before,ie,iflags,
            buttons,read_data,response_valid,joyp_selected_active,divider_reset_request,wake_request,
            request_valid,address,write_data,write_enable,access_kind,bus_commit,irq_ack,halted,
            stopped,locked,initialized,fault,ime_observe,ime_delay_observe,stop_execute,
            retirement_valid,retirement,address_effect,address_effect_resolved,address_effect_sample,
            address_effect_phase,instruction_complete);
        for (scenario=0; scenario<10; scenario=scenario+1) begin
            fresh=0; reset_sys=1; edge_cycle(0); reset_sys=0;
            for (item=0; item<65536; item=item+1) memory[item]=0;
            memory[16'h100]=8'h21; memory[16'h101]=0; memory[16'h102]=8'hc0;
            memory[16'h103]=8'h77; memory[16'h104]=8'h3c;
            memory[16'h105]=8'h77; memory[16'h106]=8'h76;
            epoch=32'(scenario+1); core_reset=1; edge_cycle(0); core_reset=0;
            write_count=0; event_index=0;
            phase_case=scenario%5;
            cycle=0;
            while (dot_before < 64'(28+(phase_case==4 ? 0 : phase_case))) begin
                edge_cycle(cycle%3==0);
                cycle=cycle+1;
            end
            if (write_count!=1 || memory[16'hc000]!==0) $fatal(1,"CPU_RESET_PARTIAL");
            if (phase_case!=4) begin
                held_request=request_valid; held_write=write_enable;
                held_address=address; held_data=write_data; held_dot=dot_before;
                for (pause_cycle=0; pause_cycle<20; pause_cycle=pause_cycle+1) begin
                    edge_cycle(0);
                    if (bus_commit || dot_before!==held_dot || request_valid!==held_request ||
                        write_enable!==held_write || address!==held_address || write_data!==held_data)
                        $fatal(1,"CPU_RESET_PAUSE case=%0d",scenario);
                end
            end
            // Each ordinary case resets a held write before its next T edge.
            // Case4 resets immediately after retirement capture, before publish.
            epoch=32'(scenario+101);
            if (scenario<5) core_reset=1;
            else reset_sys=1;
            #1;
            if (bus_commit || request_valid) $fatal(1,"CPU_RESET_CANCEL");
            edge_cycle(1);
            if (retirement_valid || write_count!=1) $fatal(1,"CPU_RESET_LEAK");
            reset_sys=0;
            #1;
            if (scenario>=5 && (initialized || retirement_valid || fault || halted || stopped || locked))
                $fatal(1,"CPU_RESET_GLOBAL_STATE case=%0d",scenario);
            core_reset=1; edge_cycle(0); core_reset=0;
            fresh=1;
            for (cycle=0; cycle<132; cycle=cycle+1) begin
                if (corrupt && scenario==0 && dot_before==31)
                    force dut.u_bus.commit=1'b0;
                edge_cycle(cycle%3==0);
            end
            if (write_count!=3 || event_index!=5 || !halted || fault ||
                memory[16'hc000]!==1) $fatal(1,"CPU_RESET_FINAL case=%0d",scenario);
        end
        $fclose(trace);
        $display("PASS CPU reset cases=10 phases=4 pending=2 pause=20 fresh_events=50");
        $finish;
    end
    initial begin
        #1000000;
        $fatal(1,"CPU_RESET_TIMEOUT");
    end
endmodule
