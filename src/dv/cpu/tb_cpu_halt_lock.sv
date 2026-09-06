`timescale 1ns/1ps
`default_nettype none

module tb_cpu_halt_lock;
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
    logic [7:0] illegal_opcodes [11];
    logic [15:0] addresses [6];
    logic [7:0] bytes_expected [6];
    logic [2:0] kinds [6];
    logic writes [6];
    logic [383:0] expected;
    integer scenario;
    integer item;
    integer cycle;
    integer pause_cycle;
    integer bus_index;
    integer event_index;
    integer bus_count;
    integer end_dot;
    integer write_count;
    integer trace;
    bit recovery;
    bit lock_fault;
    bit halt_fault;

    n2m_cpu_control dut (.*);
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
            $fatal(1,"CPU_POWER_EARLY_COMMIT");
        if (gb_tick && dot_before[1:0]==3) begin
            if (bus_index<bus_count) begin
                if (bus_commit!==(kinds[bus_index]!=0) || (kinds[bus_index]!=0 &&
                    (access_kind!==kinds[bus_index] || address!==addresses[bus_index] ||
                    write_enable!==writes[bus_index] ||
                    (write_enable ? write_data : read_data)!==bytes_expected[bus_index])))
                    $fatal(1,"CPU_POWER_BUS case=%0d dot=%0d address=%04h data=%02h",
                        scenario,dot_before+1,address,write_enable ? write_data : read_data);
                bus_index=bus_index+1;
            end else if (bus_commit || request_valid) $fatal(1,"CPU_POWER_LOCK_ACCESS case=%0d",scenario);
            $fdisplay(trace,"bus,%0d,%0d,%0d,%0d,%04h,%0d,%02h",scenario,recovery,
                dot_before+1,access_kind,address,write_enable,write_enable ? write_data : read_data);
        end
    endtask

    task automatic check_event;
        if (retirement_valid) begin
            if (scenario>=2 && !recovery) $fatal(1,"CPU_POWER_LOCK_EVENT case=%0d",scenario);
            if (event_index>=(recovery ? 1 : 2)) $fatal(1,"CPU_POWER_EXTRA_EVENT");
            expected='0;
            expected[0 +: 8]=1;
            expected[16 +: 32]=epoch;
            expected[48 +: 64]=64'(event_index);
            expected[112 +: 64]=(event_index==0 || recovery) ? 8 : (scenario==0 ? 16 : 24);
            expected[176 +: 16]=event_index==0 ? 16'h100 : 16'h101;
            expected[192 +: 16]=event_index==0 ? 16'h101 : (scenario==0 ? 16'h102 : 16'h8);
            expected[208 +: 24]=event_index==0 ? 24'h76 : (scenario==0 ? 24'h3e3e : 24'hcf);
            expected[232 +: 8]=(scenario==0 && event_index==1) ? 2 : 1;
            expected[304 +: 16]=(scenario==1 && event_index==1) ? 16'hfffc : 16'hfffe;
            expected[352 +: 8]=event_index==0 ? 1 : 0;
            expected[360 +: 8]=1;
            expected[368 +: 8]=1;
            if (scenario==0 && event_index==1) expected[240 +: 8]=8'h3e;
            if (recovery) begin expected[208 +: 24]=0; expected[352 +: 8]=0; end
            $fdisplay(trace,"event,%0d,%0d,%0d,%096h,%096h",scenario,recovery,event_index,expected,retirement);
            if (retirement!==expected)
                $fatal(1,"CPU_POWER_EVENT case=%0d event=%0d expected=%096h actual=%096h",
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
        epoch=1; dot_before=0; ie=1; iflags=1; buttons=0;
        response_valid=1; joyp_selected_active=0; wake_request=0;
        recovery=0; write_count=0; bus_index=0; event_index=0;
        lock_fault=$test$plusargs("lock_fault"); halt_fault=$test$plusargs("halt_fault");
        illegal_opcodes='{8'hd3,8'hdb,8'hdd,8'he3,8'he4,8'heb,8'hec,8'hed,8'hf4,8'hfc,8'hfd};
        trace=$fopen("halt-lock-trace.csv","w");
        if (!trace) $fatal(1,"CPU_POWER_TRACE_OPEN");
        $dumpfile("waves/cpu-halt-lock.vcd");
        $dumpvars(0,tb_cpu_halt_lock);
        for (scenario=0; scenario<13; scenario=scenario+1) begin
            reset_sys=1; edge_cycle(0); reset_sys=0;
            for (item=0; item<65536; item=item+1) memory[item]=0;
            epoch=32'(scenario+1); ie=1; iflags=1;
            core_reset=1; edge_cycle(0); core_reset=0;
            bus_index=0; event_index=0; write_count=0; recovery=0;
            addresses='{16'h100,16'h101,16'h101,16'h102,16'h0,16'h0};
            bytes_expected='{8'h76,8'h3e,8'h3e,8'h99,8'h0,8'h0};
            kinds='{3'd1,3'd1,3'd2,3'd1,3'd0,3'd0};
            writes='{0,0,0,0,0,0};
            bus_count=4; end_dot=16;
            memory[16'h100]=8'h76; memory[16'h101]=8'h3e; memory[16'h102]=8'h99;
            if (scenario==1) begin
                memory[16'h101]=8'hcf;
                addresses='{16'h100,16'h101,16'h0,16'hfffd,16'hfffc,16'h8};
                bytes_expected='{8'h76,8'hcf,8'h0,8'h1,8'h1,8'h0};
                kinds='{3'd1,3'd1,3'd0,3'd4,3'd4,3'd1};
                writes='{0,0,0,1,1,0};
                bus_count=6; end_dot=24;
            end
            if (scenario>=2) begin
                memory[16'h100]=illegal_opcodes[scenario-2]; memory[16'h101]=0; memory[16'h102]=0;
                bytes_expected[0]=illegal_opcodes[scenario-2];
                bus_count=1; end_dot=20;
            end
            for (cycle=0; cycle<end_dot*3+2; cycle=cycle+1) begin
                if (halt_fault && scenario==0 && dot_before==8) force dut.control.pc=16'h102;
                if (lock_fault && scenario==2 && dot_before==12) force dut.observer.retirement_valid=1'b1;
                edge_cycle(cycle%3==0);
            end
            if (fault || !initialized || halted || stopped || bus_index!=bus_count)
                $fatal(1,"CPU_POWER_FINAL case=%0d",scenario);
            if (scenario<2) begin
                if (event_index!=2 || locked || write_count!=(scenario==1 ? 2 : 0))
                    $fatal(1,"CPU_POWER_BUG_FINAL case=%0d",scenario);
                if (scenario==1 && (memory[16'hfffc]!==1 || memory[16'hfffd]!==1))
                    $fatal(1,"CPU_POWER_RST_RETURN");
            end else begin
                if (!locked || event_index!=0 || write_count!=0) $fatal(1,"CPU_POWER_LOCK_FINAL");
                ie=31; iflags=31;
                for (pause_cycle=0; pause_cycle<20; pause_cycle=pause_cycle+1) begin
                    edge_cycle(0);
                    if (!locked || bus_commit || request_valid || retirement_valid)
                        $fatal(1,"CPU_POWER_LOCK_PAUSE");
                end
                epoch=32'(scenario+101); ie=1; iflags=1;
                core_reset=1; edge_cycle(0); core_reset=0;
                memory[16'h100]=0;
                addresses[0]=16'h100; addresses[1]=16'h101;
                bytes_expected[0]=0; bytes_expected[1]=0;
                kinds[0]=1; kinds[1]=1;
                bus_index=0; bus_count=2; event_index=0; recovery=1;
                for (cycle=0; cycle<26; cycle=cycle+1) edge_cycle(cycle%3==0);
                if (locked || fault || event_index!=1 || bus_index!=2)
                    $fatal(1,"CPU_POWER_LOCK_RECOVERY");
            end
        end
        $fclose(trace);
        $display("PASS CPU HALT bug cases=2 illegal_locks=11 reset_recovery=11");
        $finish;
    end
    initial begin
        #1000000;
        $fatal(1,"CPU_POWER_TIMEOUT");
    end
endmodule
