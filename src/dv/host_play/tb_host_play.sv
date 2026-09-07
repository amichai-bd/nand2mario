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
    logic dumping;
    n2m_smoke_system #(.HOST_PLAY(1)) dut (.*);
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
        #1;
        if (!reset_sys) begin
            if (fault) $fatal(1,"PLAY_OWNER_FAULT");
            if (dot_count > 1000000) $fatal(1,"PLAY_DOT_TIMEOUT");
            if (dot_count != 0 && !dumping) begin dumping=1; $dumpon; end
            if (finish_request) begin
                if (!paused || epoch != 2) $fatal(1,"PLAY_COMPLETION");
                $display("PASS host play five immutable images four transitions"); $finish;
            end
        end
    end
    initial begin
        clk_sys=0; reset_sys=1; uart_rx=1; simulation_ns=0; dumping=0;
        tx_go=0; tx_busy=0; rx_done=0; finish_request=0; tx_count=0; rx_count=0;
        $dumpfile("waves/host-play.vcd");
        $dumpvars(0,clk_sys,reset_sys,uart_rx,uart_tx,gb_tick,paused,core_reset,epoch,dot_count,
            retirement_valid,retirement,bus_commit,address,write_enable,write_data,read_data,irq_ack,
            source_valid,source_start,source_shade,source_x,source_y,source_epoch,source_dot,source_display_eligible,fault);
        $dumpoff;
        repeat(8) @(negedge clk_sys); reset_sys=0;
        fork
            begin if ($test$plusargs("frame_fault")) begin
                wait(dut.frame_read); force dut.frame_data=8'hff;
            end end
            begin if ($test$plusargs("missing_frame")) begin
                force dut.g_play.u_snapshot.observe_complete=1'b0;
            end end
            begin if ($test$plusargs("input_fault")) begin
                wait(dut.effective_update.valid && dut.effective_update.buttons==1);
                force dut.g_play.u_joypad.input_buttons=8'd2;
            end end
            begin if ($test$plusargs("release_fault")) begin
                wait(dut.effective_update.valid && dut.effective_update.buttons==1);
                wait(!dut.effective_update.valid);
                wait(dut.effective_update.valid && dut.effective_update.buttons==0);
                force dut.g_play.u_joypad.input_commit=1'b0;
            end end
        join_none
    end
    initial begin #1000000000; $fatal(1,"PLAY_TIMEOUT"); end
endmodule
