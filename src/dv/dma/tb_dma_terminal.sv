`timescale 1ns/1ps
`default_nettype none
module tb_dma_terminal;
    n2m_memory_pkg::memory_oam_request_t oam_request;
    n2m_memory_pkg::memory_oam_response_t oam_response;
    logic clk_sys, reset_sys, core_reset, init_done, memory_init_done, gb_tick;
    logic [1:0] cpu_phase;
    logic cpu_halted, cpu_stopped, request_valid, bus_commit;
    n2m_cpu_pkg::cpu_bus_plan_t bus_plan;
    n2m_cpu_pkg::cpu_address_effect_t address_effect;
    logic address_effect_resolved, address_effect_sample;
    logic [7:0] read_data;
    logic response_valid, fault, ppu_fault;
    logic peripheral_prepare, peripheral_commit, peripheral_write;
    n2m_memory_pkg::memory_destination_t peripheral_destination;
    logic [15:0] peripheral_address;
    logic [7:0] peripheral_wdata, peripheral_rdata;
    logic peripheral_valid, peripheral_available;
    logic vram_cpu_allow, oam_cpu_allow, ppu_vram_request, ppu_vram_valid;
    logic [12:0] ppu_vram_address;
    logic [7:0] ppu_vram_data;
    logic [1:0] ppu_oam_phase;
    logic [5:0] ppu_scan_index;
    logic [6:0] ppu_oam_pair;
    logic [15:0] ppu_oam_data;
    logic ppu_oam_valid, dma_active;
    logic access_read, access_write, access_valid;
    n2m_memory_pkg::memory_store_t access_store;
    logic [14:0] access_address;
    logic [7:0] access_wdata, access_rdata;
    logic raw_vram_read, raw_vram_valid, raw_oam_read, raw_oam_valid;
    logic [12:0] raw_vram_address;
    logic [7:0] raw_vram_data;
    logic [6:0] raw_oam_pair;
    logic [15:0] raw_oam_data;
    logic setup, setup_read, setup_write, host_write, host_valid;
    n2m_memory_pkg::memory_store_t setup_store;
    logic [14:0] setup_address;
    logic [7:0] setup_data, host_data, unused_host, unused_wave;
    logic [31:0] host_address;
    logic unused_wave_valid;
    logic [6:0] object_pair;
    logic scan_reset, fetch_mode, fetch_phase1, scan_active, scan_done, object_found;
    logic object_fault_now, other_pair;
    logic [10:0] tile_row_address;
    logic [7:0] object_attributes;
    logic [3:0] selected_index;
    integer i, count;
    bit corrupt;
    assign init_done=memory_init_done && !setup;
    assign ppu_oam_pair=other_pair ? 7'd78 : object_pair;
    logic oam_cpu_late_write, oam_late_future;
    assign oam_cpu_late_write=1'b0;
    assign oam_late_future=1'b0;
    n2m_dma dut (.*);
    n2m_ppu_objects objects (.clk_sys(clk_sys), .reset(reset_sys || core_reset),
        .gb_tick(gb_tick), .lcd_on(1'b1), .size16(1'b0), .object_enable(1'b1),
        .line_y(8'd0), .pixel_position(8'd8), .scan_reset(scan_reset),
        .fetch_mode(fetch_mode), .fetch_phase1(fetch_phase1), .fetch_done(1'b0),
        .dma_active(dma_active), .oam_data(ppu_oam_data), .oam_valid(ppu_oam_valid),
        .oam_pair_address(object_pair), .oam_phase(ppu_oam_phase), .scan_index(ppu_scan_index),
        .scan_active(scan_active), .scan_done(scan_done), .object_found(object_found),
        .tile_row_address(tile_row_address), .object_attributes(object_attributes),
        .selected_index(selected_index), .fault(ppu_fault), .fault_now(object_fault_now));
    n2m_memory_stores stores (.oam_request, .oam_response, .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset),
        .init_done(memory_init_done), .access_read(setup ? setup_read : access_read),
        .access_write(setup ? setup_write : access_write), .access_store(setup ? setup_store : access_store),
        .access_address(setup ? setup_address : access_address), .access_wdata(setup ? setup_data : access_wdata),
        .access_rdata(access_rdata), .access_valid(access_valid), .host_read(1'b0),
        .host_write(host_write), .host_offset(host_address), .host_wdata(host_data),
        .host_rdata(unused_host), .host_valid(host_valid), .ppu_vram_read(raw_vram_read),
        .ppu_vram_address(raw_vram_address), .ppu_vram_rdata(raw_vram_data), .ppu_vram_valid(raw_vram_valid),
        .ppu_oam_read(raw_oam_read), .ppu_oam_pair(raw_oam_pair), .ppu_oam_rdata(raw_oam_data),
        .ppu_oam_valid(raw_oam_valid), .wave_read(1'b0), .wave_write(1'b0), .wave_wdata(8'd0), .wave_address(4'd0),
        .wave_rdata(unused_wave), .wave_valid(unused_wave_valid));
    always #5 clk_sys=~clk_sys;
    task automatic load_byte(input n2m_memory_pkg::memory_store_t bank, input integer offset, input logic [7:0] value);
        @(negedge clk_sys); setup_store=bank; setup_address=15'(offset); setup_data=value;
        setup_write=1; @(negedge clk_sys); setup_write=0;
    endtask
    task automatic dot_step;
        repeat(cpu_phase==0 ? 4 : 5) @(negedge clk_sys);
        if(fetch_phase1) expect_pair();
        gb_tick=1;
        bus_commit=request_valid && cpu_phase==3;
        address_effect_sample=bus_commit;
        @(negedge clk_sys);
        gb_tick=0; bus_commit=0; address_effect_sample=0; cpu_phase=cpu_phase+2'd1;
        if(fault || ppu_fault) $fatal(1,"DMA_TERMINAL_FAULT");
        if(fetch_phase1 && object_attributes!==8'ha5) $fatal(1,"DMA_TERMINAL_CAPTURE");
    endtask
    task automatic begin_dma;
        while(cpu_phase!=0) dot_step();
        request_valid=1; bus_plan.address=16'hff46; bus_plan.write_enable=1;
        bus_plan.write_data=8'hc0;
        repeat(4) dot_step();
        request_valid=0; bus_plan='0;
    endtask
    task automatic expect_pair;
        if(ppu_oam_phase!=2 || object_pair!=79 || !ppu_oam_valid || ppu_oam_data!==16'ha52a)
            $fatal(1,"DMA_TERMINAL_PAIR expected=a52a actual=%04x phase=%0d pair=%0d",ppu_oam_data,ppu_oam_phase,object_pair);
    endtask
    initial begin
        clk_sys=0; reset_sys=1; core_reset=0; setup=1; setup_read=0; setup_write=0;
        setup_store=n2m_memory_pkg::STORE_OAM; setup_address=0; setup_data=0; host_write=0; host_address=0; host_data=0;
        gb_tick=0; cpu_phase=0; cpu_halted=0; cpu_stopped=0; request_valid=0;
        bus_plan='0; bus_commit=0; address_effect='0; address_effect_resolved=1; address_effect_sample=0;
        peripheral_rdata=0; peripheral_valid=1; peripheral_available=1;
        vram_cpu_allow=1; oam_cpu_allow=1; ppu_vram_request=0; ppu_vram_address=0;
        scan_reset=0; fetch_mode=0; fetch_phase1=0; other_pair=0; count=0;
        corrupt=$test$plusargs("CORRUPT_TERMINAL");
        $dumpfile("dma-terminal.vcd");
        $dumpvars(0,clk_sys,reset_sys,core_reset,gb_tick,cpu_phase,request_valid,bus_commit,
            dma_active,access_write,access_address,access_wdata,raw_oam_pair,raw_oam_data,
            raw_oam_valid,ppu_oam_phase,ppu_oam_pair,ppu_oam_data,ppu_oam_valid,
            object_attributes,tile_row_address,object_found,fetch_phase1,other_pair,
            dut.pair_pending,dut.pending_pair,dut.oam_dma_response_q,fault,ppu_fault,count);
        repeat(3) @(negedge clk_sys); reset_sys=0;
        wait(memory_init_done); repeat(3) @(negedge clk_sys);
        for(i=0;i<160;i=i+1) begin
            load_byte(n2m_memory_pkg::STORE_OAM,i,i==156 ? 8'd16 : i==157 ? 8'd8 : i==158 ? 8'h2a : i==159 ? 8'h3c : 8'd0);
            load_byte(n2m_memory_pkg::STORE_WRAM,i,i==156 ? 8'd16 : i==157 ? 8'd8 : i==158 ? 8'h2a : i==159 ? 8'ha5 : 8'd0);
        end
        setup=0; scan_reset=1; dot_step(); scan_reset=0;
        repeat(82) dot_step();
        fetch_mode=1; repeat(2) @(negedge clk_sys);
        if(!scan_done || !object_found || object_pair!=79) $fatal(1,"DMA_TERMINAL_OBJECT_ADMISSION");
        begin_dma();
        // M1 delay, then160 writes. This loop is independent of DUT offset/state.
        repeat(4) dot_step();
        for(count=0;count<160;count=count+1) repeat(4) dot_step();
        if(dma_active || !dut.pair_pending || dut.pending_pair!=79) $fatal(1,"DMA_TERMINAL_PENDING");
        // Different request tag must select its real raw pair while79 is pending.
        other_pair=1; repeat(3) @(negedge clk_sys);
        if(!ppu_oam_valid || ppu_oam_data!==16'h0810) $fatal(1,"DMA_TERMINAL_OTHER_PAIR");
        other_pair=0;
        repeat(2) @(negedge clk_sys);
        if(corrupt) force dut.ppu_oam_data=16'h002a;
        // Five clocks elapsed since A: consume the earliest next Game Boy dot.
        #1; expect_pair(); fetch_phase1=1; gb_tick=1;
        @(negedge clk_sys); gb_tick=0; cpu_phase=cpu_phase+2'd1;
        if(object_attributes!==8'ha5 || tile_row_address!==11'h150) $fatal(1,"DMA_TERMINAL_CAPTURE");
        dot_step(); expect_pair();
        if(!dut.pair_pending) $fatal(1,"DMA_TERMINAL_PRECOMMIT");
        dot_step(); expect_pair();
        if(dut.pair_pending) $fatal(1,"DMA_TERMINAL_POSTCOMMIT");
        // A new accepted byte followed by actual reset cancels pending forwarding.
        fetch_phase1=0; begin_dma(); repeat(8) dot_step();
        if(!dut.pair_pending) $fatal(1,"DMA_TERMINAL_RESET_SETUP");
        core_reset=1; @(negedge clk_sys);
        if(dut.pair_pending || ppu_oam_valid || access_write || (|oam_request.write_enable)) $fatal(1,"DMA_TERMINAL_RESET_CANCEL");
        $display("PASS DMA terminal actual object pair before and after commit"); $finish;
    end
    initial begin #5000000; $fatal(1,"DMA_TERMINAL_WATCHDOG"); end
endmodule
