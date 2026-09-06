`timescale 1ns/1ps
`default_nettype none

// Original flat-memory CPU boundary examples, not an IF/IE register model.
module tb_cpu_wrap;
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


    logic [15:0] addresses [31];
    logic [2:0] kinds [31];
    logic [7:0] bytes_expected [31];
    logic writes_expected [31];
    logic [15:0] pc_before_expected [9];
    logic [15:0] pc_after_expected [9];
    logic [23:0] opcodes [9];
    logic [7:0] lengths [9];
    logic [15:0] stack_values [9];
    integer dots [9];
    logic [383:0] expected;
    integer scenario;
    integer item;
    integer cycle;
    integer cycles_expected;
    integer event_index;
    integer events_expected;
    integer writes;
    integer trace;
    integer records;
    bit corrupt;

    n2m_cpu_control dut (.*);
    assign read_data=memory[address];
    always @(posedge clk_sys) begin
        if (reset_sys || core_reset) dot_before <= 0;
        else if (gb_tick) dot_before <= dot_before + 64'd1;
        if (bus_commit && write_enable) begin memory[address] <= write_data; writes <= writes+1; end
    end

    task automatic check_bus;
        if (!gb_tick && bus_commit) $fatal(1,"CPU_WRAP_PAUSE");
        if (gb_tick && dot_before[1:0]==3) begin
            cycle=int'(dot_before)/4;
            if (cycle>=cycles_expected || bus_commit!==(kinds[cycle]!=0) ||
                    (kinds[cycle]!=0 && (access_kind!==kinds[cycle] || address!==addresses[cycle] ||
                    write_enable!==writes_expected[cycle] || (write_enable ? write_data : read_data)!==bytes_expected[cycle])))
                $fatal(1,"CPU_WRAP_BUS case=%0d cycle=%0d expected=%04h actual=%04h",scenario,cycle,addresses[cycle],address);
            $fdisplay(trace,"%0d,%0d,%0d,%04h,%0d,%02h,%0d",scenario,dot_before+1,access_kind,address,
                write_enable,write_enable ? write_data : read_data,bus_commit);
        end
    endtask

    task automatic check_event;
        if (retirement_valid) begin
            if (event_index>=events_expected) $fatal(1,"CPU_WRAP_EXTRA_EVENT");
            expected='0; expected[0 +: 8]=1; expected[16 +: 32]=32'(scenario+1);
            expected[48 +: 64]=64'(event_index); expected[112 +: 64]=64'(dots[event_index]);
            expected[176 +: 16]=pc_before_expected[event_index]; expected[192 +: 16]=pc_after_expected[event_index];
            expected[208 +: 24]=opcodes[event_index]; expected[232 +: 8]=lengths[event_index];
            expected[304 +: 16]=stack_values[event_index];
            if (event_index>=1) begin
                expected[256 +: 8]='h12; expected[264 +: 8]='h34;
            end
            if (scenario==0 && event_index>=3) begin expected[272 +: 8]='h12; expected[280 +: 8]='h34; end
            if (scenario==0 && event_index>=7) begin expected[288 +: 8]='h56; expected[296 +: 8]=1; end
            if (event_index==events_expected-1) expected[336 +: 8]=1;
            $fdisplay(records,"%0d,%0d,%096h,%096h",scenario,event_index,expected,retirement);
            if (retirement!==expected) $fatal(1,"CPU_WRAP_RECORD case=%0d event=%0d expected=%096h actual=%096h",scenario,event_index,expected,retirement);
            event_index=event_index+1;
        end
    endtask

    task automatic edge_cycle(input bit tick);
        clk_sys=0; gb_tick=tick; #4;
        if (reset_sys || core_reset) begin if (bus_commit) $fatal(1,"CPU_WRAP_RESET"); end
        else check_bus();
        #1 clk_sys=1; #2;
        if (!reset_sys && !core_reset) check_event();
        #3 clk_sys=0;
    endtask

    initial begin
        clk_sys=0; reset_sys=1; core_reset=0; gb_tick=0; profile_id=1; epoch=0; dot_before=0;
        ie=0; iflags=0; buttons=0; response_valid=1; joyp_selected_active=0; wake_request=0;
        corrupt=$test$plusargs("corrupt"); writes=0;
        trace=$fopen("wrap-bus.csv","w"); records=$fopen("wrap-retirement.csv","w");
        if (!trace || !records) $fatal(1,"CPU_WRAP_TRACE_OPEN");
        $fdisplay(trace,"case,dot,kind,address,write,data,commit");
        $fdisplay(records,"case,event,expected,actual");
        $dumpfile("waves/cpu-wrap.vcd"); $dumpvars(0,tb_cpu_wrap);
        for (scenario=0; scenario<2; scenario=scenario+1) begin
            for (item=0; item<65536; item=item+1) memory[item]=0;
            for (item=0; item<31; item=item+1) begin addresses[item]=0; kinds[item]=0; bytes_expected[item]=0; writes_expected[item]=0; end
            epoch=32'(scenario+1); event_index=0;
            if (scenario==0) begin
                memory['h100]='h31; memory['h103]='h01; memory['h104]='h34; memory['h105]='h12;
                memory['h106]='hc5; memory['h107]='hd1; memory['h108]='hcd; memory['h109]='h10; memory['h10a]=1;
                memory['h10b]='h31; memory['h10c]='hff; memory['h10d]='hff; memory['h10e]='he1; memory['h10f]='h76; memory['h110]='hc9; memory[0]='h56;
                addresses='{16'h100,16'h101,16'h102,16'h103,16'h104,16'h105,16'h106,0,16'hffff,16'hfffe,16'h107,16'hfffe,16'hffff,16'h108,16'h109,16'h10a,0,16'hffff,16'hfffe,16'h110,16'hfffe,16'hffff,0,16'h10b,16'h10c,16'h10d,16'h10e,16'hffff,0,16'h10f,16'h110};
                kinds='{1,2,2,1,2,2,1,0,4,4,1,4,4,1,2,2,0,4,4,1,4,4,0,1,2,2,1,4,4,1,1};
                bytes_expected='{8'h31,0,0,8'h01,8'h34,8'h12,8'hc5,0,8'h12,8'h34,8'hd1,8'h34,8'h12,8'hcd,8'h10,1,0,1,8'h0b,8'hc9,8'h0b,1,0,8'h31,8'hff,8'hff,8'he1,1,8'h56,8'h76,8'hc9};
                writes_expected[8]=1; writes_expected[9]=1; writes_expected[17]=1; writes_expected[18]=1;
                pc_before_expected='{16'h100,16'h103,16'h106,16'h107,16'h108,16'h110,16'h10b,16'h10e,16'h10f};
                pc_after_expected='{16'h103,16'h106,16'h107,16'h108,16'h110,16'h10b,16'h10e,16'h10f,16'h110};
                opcodes='{24'h000031,24'h123401,24'hc5,24'hd1,24'h0110cd,24'hc9,24'hffff31,24'he1,24'h76};
                lengths='{3,3,1,1,3,1,3,1,1}; stack_values='{0,0,16'hfffe,0,16'hfffe,0,16'hffff,1,1};
                dots='{16,28,44,56,80,96,108,120,124}; cycles_expected=31; events_expected=9;
            end else begin
                memory['h100]='hc3; memory['h101]='hfe; memory['h102]='hff;
                memory['hfffe]=1; memory['hffff]='h34; memory[0]='h12; memory[1]='h76;
                addresses[0]='h100; addresses[1]='h101; addresses[2]='h102; addresses[4]='hfffe;
                addresses[5]='hffff; addresses[6]=0; addresses[7]=1; addresses[8]=2;
                for (item=0; item<9; item=item+1) begin
                    kinds[item]=(item==1 || item==2 || item==5 || item==6) ? 2 : 1;
                    bytes_expected[item]=memory[addresses[item]];
                end
                kinds[3]=0;
                pc_before_expected[0]='h100; pc_before_expected[1]='hfffe; pc_before_expected[2]=1;
                pc_after_expected[0]='hfffe; pc_after_expected[1]=1; pc_after_expected[2]=2;
                opcodes[0]='hfffec3; opcodes[1]='h123401; opcodes[2]='h76;
                lengths[0]=3; lengths[1]=3; lengths[2]=1;
                stack_values[0]='hfffe; stack_values[1]='hfffe; stack_values[2]='hfffe;
                dots[0]=20; dots[1]=32; dots[2]=36; cycles_expected=9; events_expected=3;
            end
            reset_sys=1; core_reset=0; edge_cycle(0); reset_sys=0; core_reset=1; edge_cycle(0); core_reset=0;
            while (dot_before<64'(cycles_expected*4)) begin
                if (corrupt && scenario==0 && dot_before==51) force dut.read_data=8'h13;
                edge_cycle(1);
                if (corrupt && scenario==0 && dot_before==52) release dut.read_data;
                edge_cycle(0); edge_cycle(0);
            end
            if (event_index!=events_expected || writes!=4 || !halted || fault || locked || stopped)
                $fatal(1,"CPU_WRAP_FINAL case=%0d events=%0d writes=%0d",scenario,event_index,writes);
        end
        $fclose(trace); $fclose(records);
        $display("PASS CPU wrap cases=2 cycles=40 records=12 writes=4");
        $finish;
    end
    initial begin
        #2000000;
        $fatal(1,"CPU_WRAP_TIMEOUT");
    end
endmodule
