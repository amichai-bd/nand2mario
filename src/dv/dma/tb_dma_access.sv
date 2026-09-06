`timescale 1ns/1ps
`default_nettype none
module tb_dma_access;
    import n2m_interfaces_pkg::*;
    import n2m_cpu_pkg::*;
    import n2m_memory_pkg::*;
    logic clk_sys, reset_sys, core_reset, init_done, memory_init_done, gb_tick;
    logic [1:0] cpu_phase;
    logic cpu_halted, cpu_stopped, request_valid, bus_commit;
    cpu_bus_plan_t bus_plan;
    cpu_address_effect_t address_effect;
    logic address_effect_resolved, address_effect_sample;
    logic [7:0] read_data;
    logic response_valid, fault, ppu_fault;
    logic peripheral_prepare, peripheral_commit, peripheral_write;
    memory_destination_t peripheral_destination;
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
    memory_store_t access_store;
    logic [14:0] access_address;
    logic [7:0] access_wdata, access_rdata;
    logic raw_vram_read, raw_vram_valid, raw_oam_read, raw_oam_valid;
    logic [12:0] raw_vram_address;
    logic [7:0] raw_vram_data;
    logic [6:0] raw_oam_pair;
    logic [15:0] raw_oam_data;
    logic setup, setup_read, setup_write, host_write, host_valid;
    memory_store_t setup_store;
    logic [14:0] setup_address;
    logic [7:0] setup_data, host_data, unused_host, unused_wave;
    logic [31:0] host_address;
    logic unused_wave_valid;
    logic [7:0] expected_oam [160];
    integer index, case_index, age, writes, reads_checked, probe_index;
    logic [7:0] active_page;
    bit observe, corrupt, check_read;
    logic [7:0] expected_read;
    assign init_done=memory_init_done && !setup;
    n2m_dma dut (.*);
    n2m_memory_stores stores (.clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset),
        .init_done(memory_init_done), .access_read(setup ? setup_read : access_read),
        .access_write(setup ? setup_write : access_write), .access_store(setup ? setup_store : access_store),
        .access_address(setup ? setup_address : access_address), .access_wdata(setup ? setup_data : access_wdata),
        .access_rdata(access_rdata), .access_valid(access_valid), .host_read(1'b0),
        .host_write(host_write), .host_offset(host_address), .host_wdata(host_data),
        .host_rdata(unused_host), .host_valid(host_valid), .ppu_vram_read(raw_vram_read),
        .ppu_vram_address(raw_vram_address), .ppu_vram_rdata(raw_vram_data), .ppu_vram_valid(raw_vram_valid),
        .ppu_oam_read(raw_oam_read), .ppu_oam_pair(raw_oam_pair), .ppu_oam_rdata(raw_oam_data),
        .ppu_oam_valid(raw_oam_valid), .wave_read(1'b0), .wave_address(4'd0),
        .wave_rdata(unused_wave), .wave_valid(unused_wave_valid));
    always #5 clk_sys=~clk_sys;
    function automatic logic [7:0] source_byte(input integer offset);
        source_byte=8'(offset+129);
    endfunction
    task automatic load_byte(input memory_store_t bank,input integer offset,input logic [7:0] value);
        @(negedge clk_sys); setup_store=bank; setup_address=15'(offset); setup_data=value;
        setup_write=1; @(negedge clk_sys); setup_write=0;
    endtask
    task automatic dot_step;
        repeat(11) @(negedge clk_sys);
        gb_tick=1; bus_commit=request_valid && cpu_phase==3; address_effect_sample=bus_commit;
        if(bus_commit && !bus_plan.write_enable && check_read) begin
            if(!response_valid || read_data!==expected_read)
                $fatal(1,"DMA_ACCESS_READ case=%0d address=%04x expected=%02x actual=%02x",case_index,bus_plan.address,expected_read,read_data);
            reads_checked=reads_checked+1;
        end
        @(negedge clk_sys); gb_tick=0; bus_commit=0; address_effect_sample=0; cpu_phase=cpu_phase+2'd1;
        if(fault) $fatal(1,"DMA_ACCESS_FAULT");
    endtask
    task automatic transaction(input logic valid_request,input logic wr,input logic[15:0] address,
        input logic[7:0] data,input logic verify_read,input logic[7:0] expected);
        if(cpu_phase!=0) $fatal(1,"DMA_ACCESS_PREPARE_PHASE");
        request_valid=valid_request; bus_plan.address=address; bus_plan.write_enable=wr;
        bus_plan.write_data=data; check_read=verify_read; expected_read=expected;
        repeat(4) dot_step();
        request_valid=0; bus_plan='0; check_read=0;
    endtask
    task automatic readback(input memory_store_t bank,input integer offset,input logic[7:0] expected);
        @(negedge clk_sys); setup_store=bank; setup_address=15'(offset); setup_read=1;
        @(negedge clk_sys);
        if(!access_valid || access_rdata!==expected)
            $fatal(1,"DMA_ACCESS_STORAGE case=%0d store=%0d offset=%0d expected=%02x actual=%02x",case_index,bank,offset,expected,access_rdata);
        setup_read=0;
    endtask
    always @(posedge clk_sys) begin
        if(observe && gb_tick && cpu_phase==3) begin
            if(bus_commit && bus_plan.write_enable && bus_plan.address==16'hff46) age=0;
            else age=age+1;
            if(age>=2 && age<=161) begin
                probe_index=age-2;
                expected_oam[probe_index]=active_page==8'ha0 ? 8'hff : source_byte(probe_index);
                if(case_index==0 && probe_index==1) expected_oam[probe_index]=8'h02;
            end
        end
        if(observe && access_write && access_store==STORE_OAM) begin
            if(access_address!=15'(writes) || access_wdata!==expected_oam[writes])
                $fatal(1,"DMA_ACCESS_WRITE case=%0d index=%0d address=%0d expected=%02x actual=%02x",case_index,writes,access_address,expected_oam[writes],access_wdata);
            writes=writes+1;
        end
    end
    initial begin
        clk_sys=0; reset_sys=1; core_reset=0; setup=1; setup_read=0; setup_write=0;
        setup_store=STORE_OAM; setup_address=0; setup_data=0; host_write=0; host_address=0; host_data=0;
        gb_tick=0; cpu_phase=0; cpu_halted=0; cpu_stopped=0; request_valid=0;
        bus_plan='0; bus_commit=0; address_effect='0; address_effect_resolved=1; address_effect_sample=0;
        peripheral_rdata=0; peripheral_valid=1; peripheral_available=1;
        vram_cpu_allow=1; oam_cpu_allow=1; ppu_vram_request=0; ppu_vram_address=0;
        ppu_oam_phase=0; ppu_scan_index=0; ppu_oam_pair=0; observe=0; check_read=0;
        expected_read=0; active_page=0; age=0; writes=0; reads_checked=0; probe_index=0;
        corrupt=$test$plusargs("CORRUPT_ACCESS");
        $dumpfile("dma-access.vcd");
        $dumpvars(0,clk_sys,reset_sys,core_reset,gb_tick,cpu_phase,request_valid,bus_commit,
            bus_plan,read_data,response_valid,dma_active,access_write,access_address,access_store,
            access_wdata,fault,age,writes,reads_checked,case_index,expected_read,active_page,vram_cpu_allow);
        repeat(3) @(negedge clk_sys); reset_sys=0;
        wait(memory_init_done); repeat(3) @(negedge clk_sys);
        for(case_index=0;case_index<7;case_index=case_index+1) begin
            setup=1; observe=0; writes=0; age=0; vram_cpu_allow=case_index!=3;
            case(case_index)
                0:active_page=8'hc0; 1:active_page=8'h00;
                2,3:active_page=8'h80; 4:active_page=8'ha0;
                5:active_page=8'he0; default:active_page=8'hfe;
            endcase
            for(index=0;index<160;index=index+1) begin
                expected_oam[index]=0; load_byte(STORE_OAM,index,0);
                load_byte(STORE_WRAM,index,source_byte(index));
                load_byte(STORE_WRAM,16'h1e00+index,source_byte(index));
                load_byte(STORE_VRAM,index,source_byte(index));
                @(negedge clk_sys);host_write=1;host_address=32'(index);host_data=source_byte(index);
                @(negedge clk_sys);host_write=0;
            end
            load_byte(STORE_WRAM,16'h123,8'h55);load_byte(STORE_VRAM,16'h1000,8'h66);
            load_byte(STORE_HRAM,0,8'h5a);
            setup=0;observe=1;
            transaction(1,1,16'hff46,active_page,0,0); // M0
            transaction(1,0,16'hc123,0,1,8'h55); // M1 remains accessible before activation
            if(case_index==2 || case_index==3)
                transaction(1,1,16'h9000,8'hd4,0,0); // M2 samples old81, optional redirected source write
            else begin
                if(corrupt && case_index==0) force dut.read_data=8'hff;
                transaction(1,0,16'hc123,0,1,case_index==4 ? 8'hff : 8'h81);
            end
            if(case_index==0 || case_index==1)
                transaction(1,1,16'hc123,8'h0f,0,0); // RAM AND feedback versus ignored ROM-source write
            else if(case_index==2 || case_index==3) transaction(1,0,16'h9000,0,1,8'h82);
            else transaction(0,0,0,0,0,0);
            transaction(1,0,16'hff80,0,1,8'h5a);
            transaction(1,0,16'hff46,0,1,active_page);
            transaction(1,0,16'hfe00,0,1,8'hff);
            transaction(1,0,16'hfea0,0,1,8'hff);
            if(case_index==2 || case_index==3) transaction(1,0,16'hc123,0,1,8'h55);
            while(age<161) transaction(0,0,0,0,0,0);
            repeat(30) @(negedge clk_sys);
            if(dma_active || writes!=160) $fatal(1,"DMA_ACCESS_COUNT case=%0d writes=%0d",case_index,writes);
            observe=0;setup=1;
            for(index=0;index<160;index=index+1) readback(STORE_OAM,index,expected_oam[index]);
            readback(STORE_WRAM,16'h123,8'h55);
            readback(STORE_VRAM,16'h1000,8'h66);
            readback(STORE_VRAM,0,case_index==2 ? 8'hd4 : 8'h81);
        end
        if(reads_checked!=44) $fatal(1,"DMA_ACCESS_READ_COUNT expected=44 actual=%0d",reads_checked);
        $display("PASS DMA access seven source cases bytes=1120 reads=%0d",reads_checked);$finish;
    end
    initial begin #20000000;$fatal(1,"DMA_ACCESS_WATCHDOG");end
endmodule
