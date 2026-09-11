`timescale 1ns/1ps
`default_nettype none
module tb_dma_restart;
    integer lane;
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
    logic [7:0] expected_oam [160];
    logic expected_pending;
    logic [7:0] expected_offset, expected_byte;
    integer system_edges, accepted_edge, expected_edge, write_count, case_index, index, dot;
    integer trace;
    bit observe, early_write;
    assign init_done=memory_init_done && !setup;
    logic oam_cpu_late_write, oam_late_future;
    assign oam_cpu_late_write=1'b0;
    assign oam_late_future=1'b0;
    n2m_dma dut (.*);
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
        .wave_rdata(unused_wave), .wave_valid(unused_wave_valid),
        .core_paused(1'b0), .peek_read(1'b0), .peek_select(8'd0), .peek_offset(13'd0),
        .peek_rdata(), .peek_valid());
    always #5 clk_sys=~clk_sys;
    function automatic logic [7:0] value_at(input logic page,input integer offset);
        value_at=8'(offset) ^ (page ? 8'hc3 : 8'h69);
    endfunction
    task automatic load_byte(input n2m_memory_pkg::memory_store_t bank,input integer offset,input logic[7:0] value);
        @(negedge clk_sys);setup_store=bank;setup_address=15'(offset);setup_data=value;
        setup_write=1;@(negedge clk_sys);setup_write=0;
    endtask
    // Every caller supplies the literal next write and ownership outcome.
    task automatic mcycle(input logic restart,input logic[7:0] page,input logic write_now,
        input logic[7:0] offset,input logic[7:0] value,input logic active_after);
        if(cpu_phase!=0) $fatal(1,"DMA_RESTART_PREPARE_PHASE");
        request_valid=restart;bus_plan='0;bus_plan.address=16'hff46;
        bus_plan.write_enable=restart;bus_plan.write_data=page;
        for(dot=0;dot<4;dot=dot+1) begin
            repeat(cpu_phase==0 ? 4 : 5) @(negedge clk_sys);
            gb_tick=1;bus_commit=restart && cpu_phase==3;address_effect_sample=bus_commit;
            if(cpu_phase==3) begin
                if(expected_pending) $fatal(1,"DMA_RESTART_PREVIOUS_SERVICE");
                expected_pending=write_now;expected_offset=offset;expected_byte=value;
                accepted_edge=system_edges+1;expected_edge=accepted_edge+13;
                if(write_now) expected_oam[offset]=value;
            end
            @(negedge clk_sys);gb_tick=0;bus_commit=0;address_effect_sample=0;cpu_phase=cpu_phase+2'd1;
        end
        request_valid=0;bus_plan='0;
        if(fault || dma_active!==active_after)
            $fatal(1,"DMA_RESTART_ACTIVE case=%0d expected=%0d actual=%0d fault=%0d",case_index,active_after,dma_active,fault);
    endtask
    task automatic final_readback;
        repeat(30) @(negedge clk_sys);
        if(expected_pending || dma_active) $fatal(1,"DMA_RESTART_INCOMPLETE");
        observe=0;setup=1;
        for(index=0;index<160;index=index+1) begin
            @(negedge clk_sys);setup_store=n2m_memory_pkg::STORE_OAM;setup_address=15'(index);setup_read=1;
            @(negedge clk_sys);
            if(!access_valid || access_rdata!==value_at(1,index) || access_rdata!==expected_oam[index])
                $fatal(1,"DMA_RESTART_READBACK case=%0d offset=%0d expected=%02x actual=%02x",case_index,index,value_at(1,index),access_rdata);
        end
        setup_read=0;setup=0;observe=1;
    endtask
    always @(posedge clk_sys) begin
        system_edges=system_edges+1;
        if(observe && access_write && access_store==n2m_memory_pkg::STORE_OAM) begin
            if(!expected_pending) $fatal(1,"DMA_RESTART_UNEXPECTED_WRITE");
            if(system_edges!=expected_edge)
                $fatal(1,"DMA_RESTART_WRITE_TIME expected_delta=13 actual_delta=%0d",system_edges-accepted_edge);
            if(access_address!=={7'd0,expected_offset} || access_wdata!==expected_byte)
                $fatal(1,"DMA_RESTART_WRITE case=%0d expected=%0d:%02x actual=%0d:%02x",case_index,expected_offset,expected_byte,access_address,access_wdata);
            $fdisplay(trace,"%0d,%0d,%0d,%02x,%0d,%0d",case_index,write_count,access_address,access_wdata,system_edges,expected_edge);
            expected_pending=0;write_count=write_count+1;
        end
            for (lane=0; lane<2; lane=lane+1) if (observe && oam_request.write_enable[lane]) begin
            if(!expected_pending) $fatal(1,"DMA_RESTART_UNEXPECTED_WRITE");
            if(system_edges!=expected_edge)
                $fatal(1,"DMA_RESTART_WRITE_TIME expected_delta=13 actual_delta=%0d",system_edges-accepted_edge);
            if((15'(oam_request.pair)*15'd2+15'(lane))!=={7'd0,expected_offset} || oam_request.data[8*lane +: 8]!==expected_byte)
                $fatal(1,"DMA_RESTART_WRITE case=%0d expected=%0d:%02x actual=%0d:%02x",case_index,expected_offset,expected_byte,(15'(oam_request.pair)*15'd2+15'(lane)),oam_request.data[8*lane +: 8]);
            $fdisplay(trace,"%0d,%0d,%0d,%02x,%0d,%0d",case_index,write_count,(15'(oam_request.pair)*15'd2+15'(lane)),oam_request.data[8*lane +: 8],system_edges,expected_edge);
            expected_pending=0;write_count=write_count+1;
        end
    end
    initial begin
        clk_sys=0;reset_sys=1;core_reset=0;setup=1;setup_read=0;setup_write=0;
        setup_store=n2m_memory_pkg::STORE_OAM;setup_address=0;setup_data=0;host_write=0;host_address=0;host_data=0;
        gb_tick=0;cpu_phase=0;cpu_halted=0;cpu_stopped=0;request_valid=0;bus_commit=0;
        bus_plan='0;address_effect='0;address_effect_resolved=1;address_effect_sample=0;
        peripheral_rdata=0;peripheral_valid=1;peripheral_available=1;
        vram_cpu_allow=1;oam_cpu_allow=1;ppu_vram_request=0;ppu_vram_address=0;
        ppu_oam_phase=0;ppu_scan_index=0;ppu_oam_pair=0;
        expected_pending=0;expected_offset=0;expected_byte=0;system_edges=0;accepted_edge=0;expected_edge=0;
        write_count=0;case_index=0;observe=0;early_write=$test$plusargs("EARLY_WRITE");
        trace=$fopen("dma-restart.csv","w");if(!trace)$fatal(1,"DMA_RESTART_TRACE");
        $dumpfile("dma-restart.vcd");
        $dumpvars(0,clk_sys,reset_sys,core_reset,gb_tick,cpu_phase,request_valid,bus_commit,bus_plan,
            dma_active,access_write,access_address,access_store,access_wdata,fault,expected_pending,
            expected_offset,expected_byte,system_edges,accepted_edge,expected_edge,write_count,case_index);
        repeat(3) @(negedge clk_sys);reset_sys=0;wait(memory_init_done);repeat(3) @(negedge clk_sys);
        for(index=0;index<160;index=index+1) begin
            load_byte(n2m_memory_pkg::STORE_WRAM,index,value_at(0,index));load_byte(n2m_memory_pkg::STORE_WRAM,256+index,value_at(1,index));
            load_byte(n2m_memory_pkg::STORE_OAM,index,0);expected_oam[index]=0;
        end
        setup=0;observe=1;
        // Different-page restart at20: old20, new21, new0.
        mcycle(1,8'hc0,0,0,0,0);mcycle(0,0,0,0,0,1);
        for(index=0;index<20;index=index+1)mcycle(0,0,1,8'(index),value_at(0,index),1);
        mcycle(1,8'hc1,1,20,value_at(0,20),1);
        mcycle(0,0,1,21,value_at(1,21),1);
        for(index=0;index<160;index=index+1)mcycle(0,0,1,8'(index),value_at(1,index),index!=159);
        final_readback();
        // Each old pending trigger matures even while another FF46 arrives.
        case_index=1;mcycle(1,8'hc0,0,0,0,0);mcycle(1,8'hc1,0,0,0,1);
        mcycle(1,8'hc0,1,0,value_at(1,0),1);mcycle(1,8'hc1,1,0,value_at(0,0),1);
        mcycle(0,0,1,0,value_at(1,0),1);
        for(index=0;index<160;index=index+1)mcycle(0,0,1,8'(index),value_at(1,index),index!=159);
        final_readback();
        // Mature trigger wins over old offset159 completion, without inactive gap.
        case_index=2;mcycle(1,8'hc0,0,0,0,0);mcycle(0,0,0,0,0,1);
        for(index=0;index<158;index=index+1)mcycle(0,0,1,8'(index),value_at(0,index),1);
        mcycle(1,8'hc1,1,158,value_at(0,158),1);mcycle(0,0,1,159,value_at(1,159),1);
        for(index=0;index<160;index=index+1)mcycle(0,0,1,8'(index),value_at(1,index),index!=159);
        final_readback();
        // A new trigger on final159 is not already mature: inactive M1 has no old byte.
        case_index=3;mcycle(1,8'hc0,0,0,0,0);mcycle(0,0,0,0,0,1);
        for(index=0;index<159;index=index+1)mcycle(0,0,1,8'(index),value_at(0,index),1);
        mcycle(1,8'hc1,1,159,value_at(0,159),0);mcycle(0,0,0,0,0,1);
        for(index=0;index<160;index=index+1)mcycle(0,0,1,8'(index),value_at(1,index),index!=159);
        final_readback();
        if(write_count!=985)$fatal(1,"DMA_RESTART_TOTAL expected=985 actual=%0d",write_count);
        $fclose(trace);$display("PASS DMA restart four literal timelines writes=985 readback=640");$finish;
    end
    initial begin
        wait(observe && early_write && expected_pending && expected_offset==5);
        wait(system_edges==expected_edge-2);@(negedge clk_sys);
        force dut.access_address=15'd5;force dut.access_wdata=8'h6c;force dut.access_write=1'b1;
    end
    initial begin #20000000;$fatal(1,"DMA_RESTART_WATCHDOG");end
endmodule
