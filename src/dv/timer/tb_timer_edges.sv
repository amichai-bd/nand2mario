`timescale 1ns/1ps
`default_nettype none
module tb_timer_edges;
    logic clk_sys,reset_sys,core_reset,gb_tick,divider_reset_request;
    logic io_commit,io_write,io_selected;
    logic [15:0] io_address;
    logic [7:0] io_wdata,io_rdata;
    n2m_timer_pkg::timer_request_t interrupt_request;
    logic [4:0] if_stored,if_observe;
    logic if_commit;
    logic [4:0] sources;
    integer scenario,tick_count,checks,trace,index,selector,period,edge_case,offset,reset_kind;
    integer new_selector,pattern,target_count,expected_count;
    logic [3:0] high_mask;
    bit edge_fault,bad_commit;
    // Host observation outputs; this fixture checks the CPU read port.
    logic [7:0] div_observe, tima_observe, tma_observe, tac_observe;
    n2m_timer dut (.*);
    assign sources={2'b00,interrupt_request.request,2'b00};
    n2m_interrupts u_interrupts (
        .clk_sys(clk_sys),.reset_sys(reset_sys),.core_reset(core_reset),.gb_tick(gb_tick),
        .io_commit(if_commit),.io_write(if_commit),.io_address(16'hFF0F),.io_wdata(8'd0),
        .source_event(5'd0), .source_level(sources),.irq_ack(5'd0),.io_selected(),.io_rdata(),
        .ie_stored(),.if_stored(if_stored),.ie_observe(),.if_observe(if_observe)
    );
    task automatic system_edge;
        #4;clk_sys=1;#1;clk_sys=0;
    endtask
    task automatic tick_a;
        gb_tick=1;system_edge();gb_tick=0;tick_count=tick_count+1;
        io_commit=0;io_write=0;divider_reset_request=0;if_commit=0;
    endtask
    task automatic tick_b;
        system_edge();system_edge();
    endtask
    task automatic tick;
        tick_a();tick_b();
    endtask
    task automatic read_check(input logic [15:0] address,input logic [7:0] expected);
        io_address=address;#1;
        $fdisplay(trace,"%0d,%0d,%04h,%02h,%02h,%0d,%02h",scenario,tick_count,address,expected,io_rdata,interrupt_request.request,if_observe);
        if(!io_selected||io_rdata!==expected)
            $fatal(1,"TIMER_EDGE_READ case=%0d tick=%0d address=%04h expected=%02h actual=%02h",scenario,tick_count,address,expected,io_rdata);
        checks=checks+1;
    endtask
    task automatic request_check(input bit expected);
        #1;
        if(interrupt_request.request!==expected)$fatal(1,"TIMER_EDGE_REQUEST case=%0d tick=%0d expected=%0d actual=%0d",scenario,tick_count,expected,interrupt_request.request);
    endtask
    task automatic reset_case(input bit global_reset);
        gb_tick=0;io_commit=0;io_write=0;divider_reset_request=0;if_commit=0;
        if(global_reset)reset_sys=1;else core_reset=1;
        read_check(16'hFF04,0);read_check(16'hFF05,0);read_check(16'hFF06,0);read_check(16'hFF07,8'hF8);
        request_check(0);if(if_observe!==0)$fatal(1,"TIMER_RESET_IF");
        system_edge();reset_sys=0;core_reset=0;system_edge();tick_count=0;
    endtask
    task automatic write_register(input logic [15:0] address,input logic [7:0] data);
        repeat(3)tick();
        io_commit=1;io_write=1;io_address=address;io_wdata=data;tick();
    endtask
    task automatic overflow_setup(input bit stop_reset,input logic [7:0] modulo);
        reset_case(0);
        write_register(16'hFF06,modulo);write_register(16'hFF05,8'hFF);write_register(16'hFF07,8'h05);
        repeat(3)tick();
        if(stop_reset)divider_reset_request=1;
        else begin io_commit=1;io_write=1;io_address=16'hFF04;io_wdata=8'hA5;end
        tick_a();read_check(16'hFF05,0);request_check(0);tick_b();tick_count=0;
    endtask
    initial begin
        clk_sys=0;reset_sys=1;core_reset=0;gb_tick=0;divider_reset_request=0;
        io_commit=0;io_write=0;io_address=0;io_wdata=0;if_commit=0;
        scenario=0;tick_count=0;checks=0;
        edge_fault=$test$plusargs("edge_fault");bad_commit=$test$plusargs("bad_commit");
        trace=$fopen("trace.csv","w");if(!trace)$fatal(1,"TIMER_EDGE_TRACE");
        $fdisplay(trace,"case,tick,address,expected,actual,request,if_observe");
        $dumpfile("waves.vcd");$dumpvars(0,clk_sys,reset_sys,core_reset,gb_tick,divider_reset_request,
            io_commit,io_write,io_address,io_wdata,io_rdata,interrupt_request,if_commit,if_stored,if_observe);
        system_edge();reset_sys=0;system_edge();
        if(bad_commit)begin io_commit=1;io_write=1;io_address=16'hFF05;system_edge();$fatal(1,"TIMER_BAD_COMMIT_UNDETECTED");end
        // Independent elapsed-enable arithmetic covers every visible divider
        // value and full16-bit wrap, with the programmable timer disabled.
        for(index=1;index<=65536;index=index+1)begin
            tick();read_check(16'hFF04,8'(index/256));
            if(index%256==0)begin read_check(16'hFF05,0);request_check(0);end
        end
        scenario=scenario+1;
        for(selector=0;selector<4;selector=selector+1)begin
            reset_case(0);write_register(16'hFF07,8'(4+selector));write_register(16'hFF04,0);write_register(16'hFF05,0);
            // Four ticks elapsed after DIV reset when the TIMA clear ends.
            tick_count=0;
            case(selector)0:period=1024;1:period=16;2:period=64;3:period=256;endcase
            for(index=1;index<=2*period;index=index+1)begin
                if(edge_fault&&selector==0&&index==1)begin
                    tick_a();force dut.state_q.tac=3'd0;tick_b();
                end else tick();
                read_check(16'hFF05,8'((index+4)/period));read_check(16'hFF04,8'((index+4)/256));request_check(0);
            end
            scenario=scenario+1;
        end
        reset_case(0);
        for(index=0;index<256;index=index+1)begin write_register(16'hFF07,8'(index));read_check(16'hFF07,8'hF8|8'(index&7));end
        scenario=scenario+1;
        // Literal legal T4 write witnesses; all start from reset divider0.
        for(edge_case=0;edge_case<9;edge_case=edge_case+1)begin
            reset_case(0);
            case(edge_case)
                0:begin write_register(16'hFF07,5);write_register(16'hFF07,0);read_check(16'hFF05,1);end // rise then disable at8
                1:begin write_register(16'hFF07,5);repeat(4)tick();write_register(16'hFF04,8'hFF);read_check(16'hFF05,1);end
                2:begin write_register(16'hFF07,5);write_register(16'hFF07,4);read_check(16'hFF05,1);end // high to low mux
                3:begin write_register(16'hFF07,4);write_register(16'hFF07,5);read_check(16'hFF05,0);end
                4:begin write_register(16'hFF07,0);write_register(16'hFF07,5);read_check(16'hFF05,0);end // enable high
                5:begin write_register(16'hFF07,5);write_register(16'hFF07,8'hFD);read_check(16'hFF05,0);end
                6:begin write_register(16'hFF07,5);repeat(8)tick();write_register(16'hFF07,0);read_check(16'hFF05,1);end // one natural fall
                7:begin write_register(16'hFF07,4);write_register(16'hFF04,8'hFF);read_check(16'hFF05,0);end
                8:begin write_register(16'hFF07,5);repeat(4)tick();write_register(16'hFF07,5);read_check(16'hFF05,0);end // held high
            endcase
            scenario=scenario+1;
        end
        // Every selectable divider bit can create the DIV-write fall.
        for(selector=0;selector<4;selector=selector+1)begin
            reset_case(0);write_register(16'hFF07,8'(4+selector));write_register(16'hFF05,0);
            case(selector)0:period=1024;1:period=16;2:period=64;3:period=256;endcase
            repeat(period/2-8)tick();write_register(16'hFF04,8'h5A);
            read_check(16'hFF05,1);scenario=scenario+1;
        end
        // All16 enabled mux transitions at two literal divider positions.
        // At552 selected bits9/3/5 are high and7 low; at148 only7 is high.
        // Expected natural counts use elapsed periods, not private DUT state.
        for(pattern=0;pattern<2;pattern=pattern+1)
            for(selector=0;selector<4;selector=selector+1)
                for(new_selector=0;new_selector<4;new_selector=new_selector+1)begin
                    reset_case(0);write_register(16'hFF07,8'(4+selector));write_register(16'hFF05,0);
                    case(selector)0:period=1024;1:period=16;2:period=64;3:period=256;endcase
                    target_count=pattern==0?552:148;high_mask=pattern==0?4'b0111:4'b1000;
                    repeat(target_count-12)tick();write_register(16'hFF07,8'(4+new_selector));
                    expected_count=target_count/period;
                    if(high_mask[selector]&&!high_mask[new_selector])expected_count=expected_count+1;
                    read_check(16'hFF05,8'(expected_count));scenario=scenario+1;
                end
        // Pause one enable before a fall. HALT needs no timer control input:
        // normal enabled progression above and after pause continues unchanged.
        reset_case(0);write_register(16'hFF07,5);write_register(16'hFF04,0);write_register(16'hFF05,0);
        repeat(11)tick();read_check(16'hFF05,0);
        repeat(100)begin system_edge();read_check(16'hFF05,0);end
        tick();read_check(16'hFF05,1);scenario=scenario+1;
        // STOP resets only DIV and freezes enabled time. A pending overflow
        // survives, and the actual IF owner consumes a reload after resume.
        overflow_setup(1,8'h23);
        repeat(100)begin system_edge();read_check(16'hFF05,0);request_check(0);end
        for(index=1;index<=4;index=index+1)begin
            tick_a();read_check(16'hFF05,index==4?8'h23:8'h00);request_check(index==4);
            if(index==4&&if_observe!==4)$fatal(1,"TIMER_STOP_PRE_B_IF");
            tick_b();
        end
        repeat(100)begin system_edge();read_check(16'hFF05,8'h23);request_check(0);end
        if(if_stored!==4)$fatal(1,"TIMER_STOP_STORED_IF");
        for(index=5;index<=16;index=index+1)begin tick();read_check(16'hFF05,index==16?8'h24:8'h23);end
        scenario=scenario+1;
        // DIV and TAC updates at reload cannot cancel the pending request.
        for(index=0;index<2;index=index+1)begin
            overflow_setup(0,8'h23);repeat(3)tick();
            io_commit=1;io_write=1;io_address=index==0?16'hFF04:16'hFF07;io_wdata=0;
            tick_a();read_check(16'hFF05,8'h23);request_check(1);tick_b();
            if(if_stored!==4)$fatal(1,"TIMER_RELOAD_WRITE_IF");scenario=scenario+1;
        end
        // TMA FF repeats overflow at the selected period, not the reload delay.
        // Clear real IF between requests and check no duplicate pulse.
        overflow_setup(0,8'hFF);
        for(index=1;index<=20;index=index+1)begin
            if(index==8)if_commit=1;
            tick_a();request_check(index==4||index==20);
            read_check(16'hFF05,(index<4||(index>=16&&index<20))?8'h00:8'hFF);
            tick_b();
            if(if_stored!==((index>=4&&index<8)||index==20?5'h04:5'h00))$fatal(1,"TIMER_REPEAT_IF tick=%0d",index);
        end
        scenario=scenario+1;
        // Reset at each pending-delay boundary, including before B of the
        // actual reload pulse. Both reset controls cancel observations at once.
        for(reset_kind=0;reset_kind<2;reset_kind=reset_kind+1)
            for(offset=0;offset<=4;offset=offset+1)begin
                overflow_setup(0,8'h23);
                for(index=1;index<=offset;index=index+1)begin tick_a();if(index<offset)tick_b();end
                reset_case(reset_kind!=0);
                repeat(20)system_edge();
                repeat(16)tick();read_check(16'hFF05,0);request_check(0);
                if(if_stored!==0)$fatal(1,"TIMER_RESET_STALE_IF");scenario=scenario+1;
            end
        reset_case(0);io_address=16'hFF03;#1;if(io_selected)$fatal(1,"TIMER_ALIAS_LOW");
        io_address=16'hFF08;#1;if(io_selected)$fatal(1,"TIMER_ALIAS_HIGH");
        repeat(3)tick();io_address=16'hFF05;io_commit=1;io_write=0;tick();read_check(16'hFF05,0);
        scenario=scenario+1;
        if(scenario!=67)$fatal(1,"TIMER_EDGE_CASE_COUNT");
        $display("PASS timer frequencies edges wrap pause STOP resets cases=67 checks=%0d",checks);
        $fclose(trace);$finish;
    end
    initial begin #10000000;$fatal(1,"TIMER_EDGE_WATCHDOG");end
endmodule
