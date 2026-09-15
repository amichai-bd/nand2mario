`timescale 1ns/1ps
`default_nettype none
// The host library loader against the real UART endpoint, SDRAM controller
// and pin-level device model, driven by the product host Client through the
// peer mailboxes of the Verilator driver (tb_integration's serial stimulus/receiver).
// Contract: wiki/src/rtl/storage/MAS_sdram.md#address-space-layout and the
// host rules in wiki/src/rtl/cartridge/MAS_loader_profile.md#host-interaction.
// No CPU or ROM store is present: the library lives in SDRAM only.
module tb_library_peer;
    logic clk_sys, reset_sys, uart_rx, uart_tx;
    logic gb_tick, paused, pause_request, core_reset;
    logic [7:0] endpoint_state;
    logic sdram_initialized, sdram_request_valid, sdram_request_write, sdram_request_ready;
    logic sdram_response_valid, sdram_idle;
    logic [25:0] sdram_request_address;
    logic [127:0] sdram_request_data, sdram_response_data;
    logic [12:0] dram_addr;
    logic [1:0] dram_ba;
    logic dram_cas_n, dram_cke, dram_clk, dram_cs_n, dram_dqml, dram_dqmh, dram_ras_n, dram_we_n;
    tri [15:0] dram_dq;
    logic [31:0] model_refreshes, model_reads, model_writes;
    // Only these serial stimulus/receiver mailboxes are writable by the peer driver.
    logic [7:0] tx_bytes [0:271];
    logic [7:0] rx_bytes [0:271];
    integer tx_count, rx_count, transactions;
    logic tx_go, tx_busy, rx_done, finish_request;
    logic [63:0] simulation_ns, dot_count;

    // 3.125 MBaud keeps eight system clocks per bit for the bit-level driver
    // and monitor below; the SDRAM timing is unchanged at 40 ns per clock.
    n2m_uart #(.CLOCK_HZ(25000000), .BAUD(3125000)) dut (
        .input_source_observe(),
        .clk_sys(clk_sys), .reset_sys(reset_sys), .uart_rx(uart_rx), .uart_tx(uart_tx),
        .build_id(128'h0123456789abcdeffedcba9876543210), .gb_tick(gb_tick), .paused(paused),
        .core_initialized(1'b0), .instruction_complete(1'b0), .retirement_valid(1'b0), .cpu_stopped(1'b0),
        .pause_request(pause_request), .core_reset(core_reset), .buttons(),
        .physical_commit(1'b0), .physical_buttons(8'd0), .effective_buttons(), .effective_update(),
        .epoch(), .dot_count(), .retirement_count(), .profile(), .image_valid(), .endpoint_state(endpoint_state),
        .rom_write(), .rom_read(), .rom_address(), .rom_write_data(), .rom_read_data(8'd0), .rom_read_valid(1'b0),
        .snapshot_request(), .snapshot_ready(1'b0), .snapshot_done(1'b0), .snapshot_ok(1'b0),
        .snapshot_valid(1'b0), .snapshot_metadata('0), .frame_read(), .frame_address(),
        .frame_data(8'd0), .frame_valid(1'b0),
        .io_lcdc(8'd0), .io_stat(8'd0), .io_ly(8'd0), .io_lyc(8'd0), .io_scy(8'd0),
        .io_scx(8'd0), .io_wy(8'd0), .io_wx(8'd0), .io_bgp(8'd0), .io_obp0(8'd0),
        .io_obp1(8'd0), .io_div(8'd0), .io_tima(8'd0), .io_tma(8'd0), .io_tac(8'd0),
        .io_if(8'd0), .io_ie(8'd0),
        .peek_ready(1'b0), .peek_read(), .peek_select(), .peek_offset(), .peek_rdata(8'd0), .peek_valid(1'b0),
        .sdram_initialized(sdram_initialized), .sdram_request_valid(sdram_request_valid),
        .sdram_request_write(sdram_request_write), .sdram_request_address(sdram_request_address),
        .sdram_request_data(sdram_request_data), .sdram_request_ready(sdram_request_ready),
        .sdram_response_valid(sdram_response_valid), .sdram_response_data(sdram_response_data)
    );
    n2m_timebase u_timebase (.clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset),
        .pause_request(pause_request), .gb_tick(gb_tick), .paused(paused));
    n2m_sdram_ctrl u_sdram (
        .clk_sys(clk_sys), .reset_sys(reset_sys),
        .request_valid(sdram_request_valid), .request_write(sdram_request_write),
        .request_address(sdram_request_address), .request_data(sdram_request_data),
        .request_ready(sdram_request_ready), .response_valid(sdram_response_valid),
        .response_data(sdram_response_data), .idle(sdram_idle), .initialized(sdram_initialized),
        .DRAM_ADDR(dram_addr), .DRAM_BA(dram_ba), .DRAM_CAS_N(dram_cas_n), .DRAM_CKE(dram_cke),
        .DRAM_CLK(dram_clk), .DRAM_CS_N(dram_cs_n), .DRAM_DQ(dram_dq), .DRAM_DQML(dram_dqml),
        .DRAM_DQMH(dram_dqmh), .DRAM_RAS_N(dram_ras_n), .DRAM_WE_N(dram_we_n)
    );
    n2m_sim_sdram u_device (
        .dram_clk(dram_clk), .dram_addr(dram_addr), .dram_ba(dram_ba),
        .dram_ras_n(dram_ras_n), .dram_cas_n(dram_cas_n), .dram_we_n(dram_we_n),
        .dram_cke(dram_cke), .dram_cs_n(dram_cs_n), .dram_dqml(dram_dqml), .dram_dqmh(dram_dqmh),
        .dram_dq(dram_dq), .refreshes(model_refreshes), .reads(model_reads), .writes(model_writes)
    );
    always #20 clk_sys = !clk_sys;
    always @(posedge clk_sys) begin
        simulation_ns = $time;
        if (gb_tick) dot_count = dot_count + 1;
    end

    // The first request waits for the SDRAM initialization sequence so no
    // line command meets BAD_VALUE; the endpoint itself needs no wait.
    initial begin : transmit
        integer i, b;
        wait(!reset_sys);
        wait(sdram_initialized);
        forever begin
            wait(tx_go);
            tx_go=0; tx_busy=1;
            if(tx_count<1 || tx_count>272) $fatal(1,"LIBRARY_SERIAL_TX_SIZE");
            for(i=0;i<tx_count;i=i+1) begin
                @(negedge clk_sys); uart_rx=0; repeat(8) @(negedge clk_sys);
                for(b=0;b<8;b=b+1) begin uart_rx=tx_bytes[i][b]; repeat(8) @(negedge clk_sys); end
                uart_rx=1; repeat(8) @(negedge clk_sys);
            end
            transactions = transactions + 1;
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
            if(uart_tx!=1 || rx_count>=272 || rx_done) $fatal(1,"LIBRARY_SERIAL_RX_FRAME");
            rx_bytes[rx_count]=value; rx_count=rx_count+1;
            if(value==0) rx_done=1;
        end
    end
    always @(posedge clk_sys) begin
        #1;
        if (!reset_sys && finish_request) begin
            if (model_writes == 0 || model_reads == 0) $fatal(1,"LIBRARY_NO_DEVICE_TRAFFIC");
            $display("PASS library-peer transactions=%0d device_writes=%0d device_reads=%0d",
                transactions, model_writes, model_reads);
            $finish;
        end
    end
    initial begin
        clk_sys=0; reset_sys=1; uart_rx=1; simulation_ns=0; dot_count=0; transactions=0;
        tx_go=0; tx_busy=0; rx_done=0; finish_request=0; tx_count=0; rx_count=0;
        repeat(8) @(negedge clk_sys); reset_sys=0;
    end
    // Two images plus the menu are about 6,700 host transactions of at most
    // 200 us each; the watchdog bounds a stalled peer well inside the wall budget.
    initial begin #(64'd4000000000); $fatal(1,"LIBRARY_TIMEOUT"); end
endmodule
