`timescale 1ns/1ps
`default_nettype none

// A discarded FDFF fetch exposes FE00 only in the following PC-repair cycle.
module tb_cpu_irq_idu;
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


    logic [15:0] addresses [14];
    logic [2:0] kinds [14];
    logic [7:0] bytes_expected [14];
    logic writes_expected [14];
    logic effects [14];
    logic [15:0] effect_addresses [14];
    logic [383:0] expected;
    integer cycle;
    integer item;
    integer event_index;
    integer qualified_effects;
    integer qualified_accesses;
    integer trace;
    integer records;
    integer quiet;
    bit corrupt;

    n2m_cpu_control dut (.*);
    assign read_data=memory[address];
    always @(posedge clk_sys) begin
        if (reset_sys || core_reset) dot_before <= 0;
        else if (gb_tick) dot_before <= dot_before + 64'd1;
        if (bus_commit && write_enable) memory[address] <= write_data;
        if (irq_ack!=0) iflags <= iflags & ~irq_ack;
    end

    task automatic check_bus;
        if (!gb_tick && (bus_commit || address_effect_sample)) $fatal(1,"CPU_IRQ_IDU_PAUSE");
        if (address_effect_phase!==dot_before[1:0] || !address_effect_resolved ||
                address_effect.valid!==effects[cycle] || address_effect.write_effect!==effects[cycle] ||
                address_effect.address!==effect_addresses[cycle] ||
                address_effect.known_mask!==(effects[cycle] ? 16'hffff : 16'h0000))
            $fatal(1,"CPU_IRQ_IDU_EFFECT cycle=%0d dot=%0d expected=%0d/%04h actual=%0d/%04h",
                cycle,dot_before,effects[cycle],effect_addresses[cycle],address_effect.valid,address_effect.address);
        if (gb_tick && dot_before[1:0]==3) begin
            if (!address_effect_sample || bus_commit!==(kinds[cycle]!=0) ||
                    irq_ack!==(cycle==12 ? 5'd1 : 5'd0) ||
                    (kinds[cycle]!=0 && (access_kind!==kinds[cycle] || address!==addresses[cycle] ||
                    write_enable!==writes_expected[cycle] || (write_enable ? write_data : read_data)!==bytes_expected[cycle])))
                $fatal(1,"CPU_IRQ_IDU_BUS cycle=%0d",cycle);
            if (address_effect.valid && address_effect.address[15:8]=='hfe) qualified_effects=qualified_effects+1;
            if (bus_commit && address[15:8]=='hfe) qualified_accesses=qualified_accesses+1;
            $fdisplay(trace,"%0d,%0d,%04h,%0d,%02h,%0d,%04h",dot_before+1,access_kind,address,
                bus_commit,write_enable ? write_data : read_data,address_effect.valid,address_effect.address);
        end
    endtask

    task automatic check_event;
        if (retirement_valid) begin
            expected='0; expected[0 +: 8]=1; expected[16 +: 32]=1;
            expected[48 +: 64]=64'(event_index); expected[304 +: 16]='hfffe; expected[360 +: 8]=1;
            case (event_index)
                0: begin
                    expected[112 +: 64]=8; expected[176 +: 16]='h100; expected[192 +: 16]='h101;
                    expected[208 +: 24]='hfb; expected[232 +: 8]=1; expected[328 +: 8]=1;
                end
                1: begin
                    expected[112 +: 64]=12; expected[176 +: 16]='h101; expected[192 +: 16]='h102;
                    expected[232 +: 8]=1; expected[320 +: 8]=1;
                end
                2: begin
                    expected[112 +: 64]=28; expected[176 +: 16]='h102; expected[192 +: 16]='hfdfd;
                    expected[208 +: 24]='hfdfdc3; expected[232 +: 8]=3; expected[320 +: 8]=1;
                end
                3: begin
                    expected[112 +: 64]=32; expected[176 +: 16]='hfdfd; expected[192 +: 16]='hfdfe;
                    expected[232 +: 8]=1; expected[320 +: 8]=1;
                end
                4: begin
                    expected[112 +: 64]=36; expected[176 +: 16]='hfdfe; expected[192 +: 16]='hfdff;
                    expected[232 +: 8]=1; expected[320 +: 8]=1; expected[368 +: 8]=1;
                end
                5: begin
                    expected[8 +: 8]=1; expected[112 +: 64]=56; expected[176 +: 16]='hfdff;
                    expected[192 +: 16]='h40; expected[304 +: 16]='hfffc;
                end
                default: $fatal(1,"CPU_IRQ_IDU_EXTRA_EVENT");
            endcase
            $fdisplay(records,"%0d,%096h,%096h",event_index,expected,retirement);
            if (retirement!==expected) $fatal(1,"CPU_IRQ_IDU_RECORD event=%0d",event_index);
            event_index=event_index+1;
        end
    endtask

    task automatic edge_cycle(input bit tick);
        clk_sys=0; gb_tick=tick; #4;
        if (reset_sys || core_reset) begin
            if (bus_commit || address_effect_sample) $fatal(1,"CPU_IRQ_IDU_RESET");
        end else if (dot_before<56) check_bus();
        else if (bus_commit || address_effect_sample) $fatal(1,"CPU_IRQ_IDU_TRAILING_EFFECT");
        #1 clk_sys=1; #2;
        if (!reset_sys && !core_reset) check_event();
        #3 clk_sys=0;
    endtask

    initial begin
        clk_sys=0; reset_sys=1; core_reset=0; gb_tick=0; profile_id=1; epoch=1; dot_before=0;
        ie=1; iflags=0; buttons=0; response_valid=1; joyp_selected_active=0; wake_request=0;
        event_index=0; cycle=0; qualified_effects=0; qualified_accesses=0;
        corrupt=$test$plusargs("corrupt");
        for (item=0; item<65536; item=item+1) memory[item]=0;
        memory['h100]='hfb; memory['h102]='hc3; memory['h103]='hfd; memory['h104]='hfd;
        addresses='{16'h100,16'h101,16'h102,16'h103,16'h104,0,16'hfdfd,16'hfdfe,16'hfdff,0,0,16'hfffd,16'hfffc,16'h40};
        kinds='{1,1,1,2,2,0,1,1,1,0,0,4,4,1};
        bytes_expected='{8'hfb,0,8'hc3,8'hfd,8'hfd,0,0,0,0,0,0,8'hfd,8'hff,0};
        writes_expected='{0,0,0,0,0,0,0,0,0,0,0,1,1,0};
        effects='{1,1,1,1,1,0,1,1,1,1,1,1,0,1};
        effect_addresses='{16'h100,16'h101,16'h102,16'h103,16'h104,0,16'hfdfd,16'hfdfe,16'hfdff,16'hfe00,16'hfffe,16'hfffd,0,16'h40};
        trace=$fopen("irq-idu-bus.csv","w"); records=$fopen("irq-idu-retirement.csv","w");
        if (!trace || !records) $fatal(1,"CPU_IRQ_IDU_TRACE_OPEN");
        $fdisplay(trace,"dot,kind,address,commit,data,effect,effect_address");
        $fdisplay(records,"event,expected,actual");
        $dumpfile("waves/cpu-irq-idu.vcd"); $dumpvars(0,tb_cpu_irq_idu);
        edge_cycle(0); reset_sys=0; core_reset=1; edge_cycle(0); core_reset=0;
        while (dot_before<56) begin
            cycle=int'(dot_before)/4;
            if (dot_before==34) iflags=1;
            if (corrupt && dot_before==36) force dut.address_effect.address=16'hfdff;
            if (dot_before>=36 && dot_before<40)
                for (quiet=0; quiet<8; quiet=quiet+1) edge_cycle(0);
            edge_cycle(1);
            // The newly prepared next plan belongs to the new M-cycle.
            cycle=int'(dot_before)/4;
            if (dot_before<56) begin edge_cycle(0); edge_cycle(0); end
        end
        edge_cycle(0);
        if (event_index!=6 || qualified_effects!=1 || qualified_accesses!=0 || fault)
            $fatal(1,"CPU_IRQ_IDU_FINAL events=%0d effects=%0d accesses=%0d",event_index,qualified_effects,qualified_accesses);
        $fclose(trace); $fclose(records);
        $display("PASS CPU IRQ IDU cycles=14 events=6 FE_effects=1 FE_accesses=0");
        $finish;
    end
    initial begin
        #1000000;
        $fatal(1,"CPU_IRQ_IDU_TIMEOUT");
    end
endmodule
