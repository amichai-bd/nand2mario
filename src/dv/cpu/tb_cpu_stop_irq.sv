`timescale 1ns/1ps
`default_nettype none

module tb_cpu_stop_irq;
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
    logic instruction_complete;
    logic [383:0] expected;
    logic [15:0] expected_address;
    logic [15:0] effect_address;
    logic [7:0] expected_data;
    logic [4:0] selected_ack;
    logic [4:0] remaining_if;
    logic [15:0] vector_address;
    logic [15:0] return_pc;
    integer scenario;
    integer item;
    integer event_index;
    integer total_records;
    integer t;
    integer offset_t;
    integer phase_case;
    integer trace;
    integer records;
    bit late_irq;
    bit fresh;
    bit effect_fault;
    bit stack_fault;
    bit expected_commit;
    bit expected_write;
    bit expected_effect;
    n2m_cpu_pkg::access_kind_t expected_kind;

    n2m_cpu dut (.*);
    assign read_data=memory[address];
    always @(posedge clk_sys) begin
        if (reset_sys || core_reset) dot_before <= 0;
        else if (gb_tick) dot_before <= dot_before + 64'd1;
        if (bus_commit && write_enable) memory[address] <= write_data;
        if (irq_ack!=0) iflags <= iflags & ~irq_ack;
        // NBA arrival on T3 is outside that edge's pre-edge snapshot.
        if (scenario==2 && gb_tick && dot_before==18) iflags <= 4;
    end

    task automatic check_bus;
        if (fault || locked || halted) $fatal(1,"CPU_STOP_IRQ_CONTROL case=%0d",scenario);
        if (!gb_tick && (bus_commit || address_effect_sample)) $fatal(1,"CPU_STOP_IRQ_PAUSE");
        if (gb_tick && dot_before[1:0]==3) begin
            t=int'(dot_before)+1;
            expected_commit=1; expected_write=0; expected_effect=1;
            expected_kind=n2m_cpu_pkg::ACCESS_OPCODE;
            expected_address=0; expected_data=0; effect_address=0;
            if (fresh || t<=16) begin
                expected_address=16'h100+16'(t/4-1);
                if (!fresh && t==4) expected_data=8'hfb;
                if (!fresh && t==12) expected_data=8'h10;
            end else if (t==20) begin
                expected_address=16'h104; expected_data=8'h3c;
            end else if (late_irq && t==24) expected_address=16'h105;
            else begin
                offset_t=t-(late_irq ? 4 : 0);
                case(offset_t)
                    24: begin expected_commit=0; effect_address=return_pc+1; end
                    28: begin expected_commit=0; effect_address=16'hfffe; end
                    32: begin
                        expected_address=16'hfffd; expected_data=8'h01; expected_write=1;
                        expected_kind=n2m_cpu_pkg::ACCESS_STACK; effect_address=16'hfffd;
                    end
                    36: begin
                        expected_address=16'hfffc; expected_data=return_pc[7:0]; expected_write=1;
                        expected_kind=n2m_cpu_pkg::ACCESS_STACK; expected_effect=0;
                    end
                    40: expected_address=vector_address;
                    44: expected_address=vector_address+1;
                    default: $fatal(1,"CPU_STOP_IRQ_UNEXPECTED_CYCLE case=%0d dot=%0d",scenario,t);
                endcase
            end
            if (expected_commit && expected_effect && !expected_write) effect_address=expected_address;
            if (bus_commit!==expected_commit ||
                (expected_commit && (address!==expected_address || write_enable!==expected_write ||
                access_kind!==expected_kind || (expected_write ? write_data : read_data)!==expected_data)))
                $fatal(1,"CPU_STOP_IRQ_BUS case=%0d dot=%0d expected=%04h/%02h actual=%04h/%02h",scenario,t,expected_address,expected_data,address,write_enable ? write_data : read_data);
            if (!address_effect_sample || !address_effect_resolved || address_effect.valid!==expected_effect ||
                address_effect.write_effect!==expected_effect || address_effect.address!==effect_address ||
                address_effect.known_mask!==(expected_effect ? 16'hffff : 16'h0000))
                $fatal(1,"CPU_STOP_IRQ_EFFECT case=%0d dot=%0d expected=%04h actual=%04h resolved=%0d",scenario,t,effect_address,address_effect.address,address_effect_resolved);
            if (irq_ack!==(!fresh && t==(late_irq ? 40 : 36) ? selected_ack : 5'd0))
                $fatal(1,"CPU_STOP_IRQ_ACK case=%0d dot=%0d",scenario,t);
            $fdisplay(trace,"%0d,%0d,%0d,%04h,%02h,%0d,%04h,%0d",scenario,t,bus_commit,address,write_enable ? write_data : read_data,address_effect.valid,address_effect.address,irq_ack);
        end else if (bus_commit || address_effect_sample || irq_ack) $fatal(1,"CPU_STOP_IRQ_EARLY");
    endtask

    task automatic check_event;
        if (retirement_valid) begin
            expected='0; expected[0+:8]=1; expected[16+:32]=epoch;
            expected[48+:64]=64'(event_index); expected[304+:16]=16'hfffe; expected[360+:8]=ie;
            if (fresh) begin
                if(event_index!=0) $fatal(1,"CPU_STOP_IRQ_RESET_EXTRA");
                expected[112+:64]=8; expected[176+:16]=16'h100; expected[192+:16]=16'h101; expected[232+:8]=1;
            end else if (event_index<3) begin
                expected[112+:64]=64'(8+4*event_index);
                expected[176+:16]=16'h100+16'(event_index);
                expected[192+:16]=event_index==2 ? 16'h104 : 16'h101+16'(event_index);
                expected[208+:24]=event_index==0 ? 24'hfb : (event_index==2 ? 24'h10 : 0);
                expected[232+:8]=event_index==2 ? 2 : 1;
                expected[320+:8]=event_index==0 ? 0 : 1;
                expected[328+:8]=event_index==0 ? 1 : 0;
                expected[344+:8]=event_index==2 ? 1 : 0;
            end else if (late_irq && event_index==3) begin
                expected[112+:64]=24; expected[176+:16]=16'h104; expected[192+:16]=16'h105;
                expected[208+:24]=24'h3c; expected[232+:8]=1; expected[240+:8]=1;
                expected[320+:8]=1; expected[368+:8]=4;
            end else begin
                if(event_index>(late_irq ? 5 : 4)) $fatal(1,"CPU_STOP_IRQ_EXTRA");
                expected[304+:16]=16'hfffc; expected[240+:8]=late_irq ? 1 : 0;
                expected[368+:8]={3'b0,remaining_if};
                if(event_index==(late_irq ? 4 : 3)) begin
                    expected[8+:8]=1; expected[112+:64]=late_irq ? 44 : 40;
                    expected[176+:16]=return_pc; expected[192+:16]=vector_address;
                end else begin
                    expected[112+:64]=late_irq ? 48 : 44;
                    expected[176+:16]=vector_address; expected[192+:16]=vector_address+1; expected[232+:8]=1;
                end
            end
            $fdisplay(records,"%0d,%0d,%096h,%096h",scenario,event_index,expected,retirement);
            if(retirement!==expected) $fatal(1,"CPU_STOP_IRQ_RECORD case=%0d event=%0d expected=%096h actual=%096h",scenario,event_index,expected,retirement);
            event_index=event_index+1; total_records=total_records+1;
        end
    endtask

    task automatic edge_cycle(input bit tick);
        clk_sys=0; gb_tick=tick; #4;
        if(reset_sys || core_reset) begin
            if(bus_commit || address_effect_sample || irq_ack || instruction_complete) $fatal(1,"CPU_STOP_IRQ_RESET_COMMIT");
        end else check_bus();
        #1 clk_sys=1; #2;
        if(!reset_sys && !core_reset) check_event();
        #3 clk_sys=0;
    endtask
    task automatic tick_cycle;
        edge_cycle(1); edge_cycle(0); edge_cycle(0);
    endtask

    initial begin
        clk_sys=0; reset_sys=1; core_reset=0; gb_tick=0; profile_id=1; epoch=0; dot_before=0;
        ie=0; iflags=0; buttons=0; response_valid=1; joyp_selected_active=0; wake_request=0;
        fresh=0; event_index=0; total_records=0; scenario=0; late_irq=0;
        effect_fault=$test$plusargs("effect_fault"); stack_fault=$test$plusargs("stack_fault");
        trace=$fopen("stop-irq-bus.csv","w"); records=$fopen("stop-irq-records.csv","w");
        if(!trace || !records) $fatal(1,"CPU_STOP_IRQ_TRACE");
        $fdisplay(trace,"case,dot,commit,address,data,effect,effect_address,ack");
        $fdisplay(records,"case,event,expected,actual");
        $dumpfile("waves/cpu-stop-irq.vcd"); $dumpvars(0,tb_cpu_stop_irq);
        edge_cycle(0); reset_sys=0;
        for(scenario=0;scenario<14;scenario=scenario+1) begin
            for(item=0;item<65536;item=item+1) memory[item]=0;
            memory['h100]=8'hfb; memory['h102]=8'h10;
            fresh=0; event_index=0; late_irq=scenario==2 || scenario==3;
            ie=scenario==0 ? 8'h1f : 8'h04; iflags=0;
            selected_ack=scenario==0 ? 5'd1 : (scenario==5 ? 5'd0 : 5'd4);
            vector_address=scenario==0 ? 16'h40 : (scenario==5 ? 16'h0 : 16'h50);
            remaining_if=scenario==0 ? 5'h1e : (scenario==4 ? 5'h1b : 5'd0);
            return_pc=late_irq ? 16'h105 : 16'h104;
            epoch=32'(scenario*2+1); core_reset=1; edge_cycle(0); core_reset=0;
            while(dot_before<16) tick_cycle();
            if(!stopped || event_index!=3) $fatal(1,"CPU_STOP_IRQ_ENTRY");
            response_valid=0; repeat(7) edge_cycle(0);
            memory['h104]=8'h3c;
            if(scenario==0 || scenario==4) iflags=5'h1f;
            else if(scenario>=5) iflags=4;
            wake_request=1; edge_cycle(0); wake_request=0;
            repeat(7) edge_cycle(0);
            if(stopped || !request_valid || address!=16'h104) $fatal(1,"CPU_STOP_IRQ_PREPARE");
            response_valid=1;
            if(scenario<6) begin
                while(dot_before<(late_irq ? 48 : 44)) begin
                    if(scenario==1 && dot_before==18) iflags=4;
                    if(scenario==3 && dot_before==19) iflags=4;
                    if(scenario==5 && dot_before==20) iflags=0;
                    if(effect_fault && scenario==0 && dot_before==19) force dut.address_effect_resolved=0;
                    if(stack_fault && scenario==0 && dot_before==31) force dut.write_data=8'h00;
                    tick_cycle();
                end
                if(event_index!=(late_irq ? 6 : 5) || memory['hfffd]!=1 || memory['hfffc]!=return_pc[7:0] || iflags!=remaining_if)
                    $fatal(1,"CPU_STOP_IRQ_FINAL case=%0d",scenario);
            end else begin
                phase_case=(scenario-6)/2;
                repeat(phase_case) tick_cycle();
                response_valid=0; repeat(5) edge_cycle(0);
                if(scenario%2) reset_sys=1; else core_reset=1;
                edge_cycle(1);
                if(retirement_valid || address_effect_phase!=0 || stopped) $fatal(1,"CPU_STOP_IRQ_RESET_STATE");
                reset_sys=0; core_reset=1; fresh=1; event_index=0; ie=0; iflags=0;
                memory['h100]=0; memory['h102]=0; response_valid=1; epoch=32'(scenario*2+2);
                edge_cycle(0); core_reset=0;
                while(dot_before<8) tick_cycle();
                if(event_index!=1 || memory['hfffd]!=0 || memory['hfffc]!=0) $fatal(1,"CPU_STOP_IRQ_RESET_FINAL");
            end
        end
        if(total_records!=64) $fatal(1,"CPU_STOP_IRQ_RECORD_COUNT actual=%0d",total_records);
        $fclose(trace); $fclose(records);
        $display("PASS CPU STOP interrupt restart cases=14 records=64 normal=6 reset=8"); $finish;
    end
    initial begin
        #3000000;
        $fatal(1,"CPU_STOP_IRQ_TIMEOUT");
    end
endmodule
