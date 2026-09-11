`timescale 1ns/1ps
`default_nettype none
module tb_timer_reload;
    logic clk_sys,reset_sys,core_reset,gb_tick,divider_reset_request;
    logic io_commit,io_write,io_selected;
    logic [15:0] io_address;
    logic [7:0] io_wdata,io_rdata;
    n2m_timer_pkg::timer_request_t interrupt_request;
    logic [4:0] if_stored,if_observe;
    logic [7:0] ie_stored,ie_observe;
    logic [4:0] sources;
    integer scenario,tick_index,write_tick,checks,trace;
    logic [7:0] expected_tima;
    logic expected_irq;
    bit counter_fault,request_fault;
    // Host observation outputs; this fixture checks the CPU read port.
    logic [7:0] div_observe, tima_observe, tma_observe, tac_observe;
    n2m_timer dut (.*);
    assign sources = {2'b00,interrupt_request.request,2'b00};
    n2m_interrupts u_interrupts (
        .clk_sys(clk_sys),.reset_sys(reset_sys),.core_reset(core_reset),.gb_tick(gb_tick),
        .io_commit(1'b0),.io_write(1'b0),.io_address(16'hFF0F),.io_wdata(8'd0),
        .source_event(5'd0), .source_level(sources),.irq_ack(5'd0),.io_selected(),.io_rdata(),
        .ie_stored(ie_stored),.if_stored(if_stored),.ie_observe(ie_observe),.if_observe(if_observe)
    );
    task automatic system_edge;
        #4;clk_sys=1;#1;clk_sys=0;
    endtask
    task automatic tick_a;
        gb_tick=1;system_edge();gb_tick=0;
    endtask
    task automatic tick_b;
        system_edge();system_edge();
    endtask
    task automatic write_register(input logic [15:0] address,input logic [7:0] data);
        repeat(3) begin tick_a();tick_b();end
        io_commit=1;io_write=1;io_address=address;io_wdata=data;
        tick_a();io_commit=0;io_write=0;tick_b();
    endtask
    task automatic check_tima(input logic [7:0] value);
        io_address=16'hFF05;#1;
        $fdisplay(trace,"%0d,%0d,%02h,%02h,%0d,%0d,%02h",scenario,tick_index,value,io_rdata,
            expected_irq,interrupt_request.request,if_observe);
        if(io_rdata!==value) $fatal(1,"TIMER_COUNTER case=%0d tick=%0d expected=%02h actual=%02h",scenario,tick_index,value,io_rdata);
        checks=checks+1;
    endtask
    initial begin
        clk_sys=0;reset_sys=1;core_reset=0;gb_tick=0;divider_reset_request=0;
        io_commit=0;io_write=0;io_address=0;io_wdata=0;checks=0;
        expected_irq=0;counter_fault=$test$plusargs("counter_fault");request_fault=$test$plusargs("request_fault");
        trace=$fopen("trace.csv","w");if(!trace)$fatal(1,"TIMER_TRACE");
        $fdisplay(trace,"case,tick,expected_tima,actual_tima,expected_irq,actual_irq,if_observe");
        $dumpfile("waves.vcd");$dumpvars(0,clk_sys,reset_sys,core_reset,gb_tick,io_commit,io_write,io_address,io_wdata,io_rdata,interrupt_request,if_stored,if_observe);
        system_edge();reset_sys=0;
        // Original schedules derived from public Mooneye instruction timing,
        // not copied assembly or a software model of private timer state.
        for(scenario=0;scenario<8;scenario=scenario+1)begin
            core_reset=1;system_edge();core_reset=0;system_edge();
            write_register(16'hFF06,8'hFE);write_register(16'hFF05,8'hFE);
            write_register(16'hFF07,8'h06);write_register(16'hFF04,8'h00);
            if(scenario<4)write_tick=124+4*scenario;else write_tick=128+4*(scenario-4);
            for(tick_index=1;tick_index<=144;tick_index=tick_index+1)begin
                io_commit=tick_index==write_tick;io_write=io_commit;io_wdata=8'h7F;
                io_address=scenario<4?16'hFF05:16'hFF06;
                tick_a();io_commit=0;io_write=0;
                if(tick_index<64)expected_tima=8'hFE;
                else if(tick_index<128)expected_tima=8'hFF;
                else if(tick_index<132)expected_tima=8'h00;
                else expected_tima=8'hFE;
                case(scenario)
                    0:if(tick_index>=124)expected_tima=tick_index<128?8'h7F:8'h80;
                    1:if(tick_index>=128)expected_tima=8'h7F;
                    3:if(tick_index>=136)expected_tima=8'h7F;
                    4,5:if(tick_index>=132)expected_tima=8'h7F;
                    default:begin end
                endcase
                expected_irq=scenario>=2&&tick_index==132;
                if(counter_fault&&scenario==0&&tick_index==64)force dut.state_q.tima=8'h00;
                if(request_fault&&scenario==2&&tick_index==132)force dut.request_q='0;
                check_tima(expected_tima);
                if(interrupt_request.request!==expected_irq)$fatal(1,"TIMER_REQUEST case=%0d tick=%0d expected=%0d actual=%0d",scenario,tick_index,expected_irq,interrupt_request.request);
                if(if_observe!==(scenario>=2&&tick_index>=132?5'h04:5'h00))$fatal(1,"TIMER_PRE_B_IF");
                tick_b();
                if(interrupt_request.request!==0||if_stored!==(scenario>=2&&tick_index>=132?5'h04:5'h00))$fatal(1,"TIMER_B_IF");
            end
        end
        $display("PASS timer reload schedules cases=8 checks=1152");$fclose(trace);$finish;
    end
    initial begin #100000;$fatal(1,"TIMER_WATCHDOG");end
endmodule
