`timescale 1ns/1ps
`default_nettype none
module tb_integration;
    logic clk_sys, reset_sys, uart_rx, uart_tx;
    logic gb_tick, paused, core_reset;
    logic [31:0] epoch;
    logic [63:0] dot_count;
    logic retirement_valid;
    n2m_interfaces_pkg::retirement_t retirement;
    logic bus_commit, write_enable;
    logic [15:0] address;
    logic [7:0] write_data, read_data;
    logic [4:0] irq_ack;
    logic source_valid, source_start, source_abort, source_display_eligible;
    logic [1:0] source_shade;
    logic [7:0] source_x, source_y;
    logic [31:0] source_epoch;
    logic [63:0] source_dot;
    logic fault;
    // Only these serial stimulus/receiver mailboxes are writable by Tcl.
    logic [7:0] tx_bytes [0:271];
    logic [7:0] rx_bytes [0:271];
    integer tx_count, rx_count;
    logic tx_go, tx_busy, rx_done, finish_request;
    logic [63:0] simulation_ns;
    logic [383:0] expected_records [0:68];
    integer event_index, pixel_index, frame_index, ram_writes, stack_writes, video_writes;
    integer records_file, pixels_file, bus_file;
    logic [63:0] expected_pixel_dot;
    logic [1:0] expected_shade;
    bit data_fault, irq_fault, pixel_fault, dumping;
    string root_path;
    n2m_smoke_system dut (.*);
    always #20 clk_sys = !clk_sys;
    always @(posedge clk_sys) simulation_ns = $time;

    initial begin : transmit
        integer i, b;
        wait(!reset_sys);
        forever begin
            wait(tx_go);
            tx_go=0; tx_busy=1;
            if(tx_count<1 || tx_count>272) $fatal(1,"SMOKE_SERIAL_TX_SIZE");
            for(i=0;i<tx_count;i=i+1) begin
                @(negedge clk_sys); uart_rx=0; repeat(8) @(negedge clk_sys);
                for(b=0;b<8;b=b+1) begin uart_rx=tx_bytes[i][b]; repeat(8) @(negedge clk_sys); end
                uart_rx=1; repeat(8) @(negedge clk_sys);
            end
            tx_busy=0;
        end
    end
    initial begin : receive
        logic [7:0] value;
        integer b;
        wait(!reset_sys);
        forever begin
            @(negedge uart_tx);
            repeat(12) @(posedge clk_sys);
            for(b=0;b<8;b=b+1) begin value[b]=uart_tx; repeat(8) @(posedge clk_sys); end
            if(uart_tx!==1 || rx_count>=272 || rx_done) $fatal(1,"SMOKE_SERIAL_RX_FRAME");
            rx_bytes[rx_count]=value; rx_count=rx_count+1;
            if(value==0) rx_done=1;
        end
    end
    always @(posedge clk_sys) begin
        if(!reset_sys && bus_commit) begin
            $fdisplay(bus_file,"%0d,%04h,%0d,%02h",dot_count+1,address,write_enable,write_enable ? write_data : read_data);
            if(write_enable && address>=16'hc000 && address<=16'hc002) begin
                case(address)
                    16'hc000: if(write_data!==8'h3c) $fatal(1,"SMOKE_RAM_C000");
                    16'hc001: if(write_data!==8'h41) $fatal(1,"SMOKE_RAM_C001");
                    16'hc002: if(write_data!==8'ha7) $fatal(1,"SMOKE_RAM_C002");
                endcase
                ram_writes=ram_writes+1;
            end
            if(write_enable && address>=16'hdffa && address<=16'hdffd) begin
                case(stack_writes)
                    0: if(address!==16'hdffd || write_data!==2) $fatal(1,"SMOKE_STACK0");
                    1: if(address!==16'hdffc || write_data!==8'h22) $fatal(1,"SMOKE_STACK1");
                    2: if(address!==16'hdffb || write_data!==1) $fatal(1,"SMOKE_STACK2");
                    3: if(address!==16'hdffa || write_data!==8'h20) $fatal(1,"SMOKE_STACK3");
                    default: $fatal(1,"SMOKE_STACK_EXTRA");
                endcase
                stack_writes=stack_writes+1;
            end
            if(write_enable && address>=16'h8000 && address<=16'h9fff) begin
                if(address!==16'(16'h8000+video_writes) || write_data!==(video_writes%2==0 ? 8'h55 : 8'h33))
                    $fatal(1,"SMOKE_TILE_WRITE");
                video_writes=video_writes+1;
            end
        end
        #1;
        if(!reset_sys) begin
            if(fault) $fatal(1,"SMOKE_OWNER_FAULT");
            if(dot_count>220000) $fatal(1,"SMOKE_DOT_TIMEOUT");
            if(dot_count!=0 && !dumping) begin dumping=1; $dumpon; end
            if(retirement_valid) begin
                if(event_index>=69) $fatal(1,"SMOKE_EXTRA_RECORD");
                if(retirement!==expected_records[event_index])
                    $fatal(1,"SMOKE_RECORD seq=%0d expected=%096h actual=%096h",event_index,expected_records[event_index],retirement);
                $fdisplay(records_file,"%0d,%096h",event_index,retirement);
                event_index=event_index+1;
            end
            if(source_valid && frame_index<2) begin
                expected_shade=frame_index==0 ? 2'd0 : 2'(pixel_index%4);
                if(source_x!==8'(pixel_index%160) || source_y!==8'(pixel_index/160) ||
                    source_start!==(pixel_index==0) || source_epoch!==32'd2 ||
                    source_display_eligible!==(frame_index==1) || source_abort)
                    $fatal(1,"SMOKE_PIXEL_ORDER frame=%0d index=%0d",frame_index,pixel_index);
                if(source_shade!==expected_shade)
                    $fatal(1,"SMOKE_PIXEL frame=%0d index=%0d expected=%0d actual=%0d",frame_index,pixel_index,expected_shade,source_shade);
                if(frame_index==1) begin
                    expected_pixel_dot=64'd70908+64'(pixel_index/160)*456+64'(pixel_index%160);
                    if(source_dot!==expected_pixel_dot) $fatal(1,"SMOKE_PIXEL_DOT index=%0d expected=%0d actual=%0d",pixel_index,expected_pixel_dot,source_dot);
                end
                $fdisplay(pixels_file,"%0d,%0d,%0d,%0d",frame_index,pixel_index,source_dot,source_shade);
                if(pixel_index==23039) begin pixel_index=0; frame_index=frame_index+1; end
                else pixel_index=pixel_index+1;
            end
            if(finish_request) begin
                if(event_index!=69 || frame_index!=2 || ram_writes!=3 || stack_writes!=4 || video_writes!=16 || !paused)
                    $fatal(1,"SMOKE_COMPLETION records=%0d frames=%0d ram=%0d stack=%0d video=%0d",event_index,frame_index,ram_writes,stack_writes,video_writes);
                $fclose(records_file); $fclose(pixels_file); $fclose(bus_file);
                $display("PASS integration records=69 frames=2 pixels=46080 ram=3 stack=4 video=16"); $finish;
            end
        end
    end
    initial begin
        clk_sys=0; reset_sys=1; uart_rx=1; simulation_ns=0;
        tx_go=0; tx_busy=0; rx_done=0; finish_request=0; tx_count=0; rx_count=0;
        event_index=0; pixel_index=0; frame_index=0; ram_writes=0; stack_writes=0; video_writes=0; dumping=0;
        data_fault=$test$plusargs("data_fault"); irq_fault=$test$plusargs("irq_fault"); pixel_fault=$test$plusargs("pixel_fault");
        if(!$value$plusargs("smoke_root=%s",root_path)) $fatal(1,"SMOKE_ROOT");
        $readmemh("retirement.hex",expected_records);
        records_file=$fopen("retirement.csv","w"); pixels_file=$fopen("pixels.csv","w"); bus_file=$fopen("bus.csv","w");
        if(!records_file || !pixels_file || !bus_file) $fatal(1,"SMOKE_TRACE");
        $fdisplay(records_file,"seq,record"); $fdisplay(pixels_file,"frame,index,dot,shade"); $fdisplay(bus_file,"dot,address,write,data");
        $dumpfile("waves/integration.vcd");
        $dumpvars(0,clk_sys,reset_sys,uart_rx,uart_tx,gb_tick,paused,core_reset,epoch,dot_count,
            retirement_valid,retirement,bus_commit,address,write_enable,write_data,read_data,irq_ack,
            source_valid,source_start,source_shade,source_x,source_y,source_epoch,source_dot,source_display_eligible,fault);
        $dumpoff;
        repeat(8) @(negedge clk_sys); reset_sys=0;
        fork
            begin if(data_fault) begin wait(address==16'he000); force dut.read_data=8'h3d; end end
            begin if(irq_fault) begin wait(irq_ack!=0); force dut.irq_ack=5'd0; end end
            begin if(pixel_fault) begin wait(frame_index==1); force dut.source_shade=2'd1; end end
        join_none
    end
    // Retain the 12.5-million-system-edge watchdog at the 25 MHz clock.
    // UART load/readback now takes twice the time at the legal 3.125 Mbaud.
    initial begin #500000000; $fatal(1,"SMOKE_TIMEOUT"); end
endmodule
