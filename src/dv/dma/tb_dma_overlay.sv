`timescale 1ns/1ps
`default_nettype none
module tb_dma_overlay;
    import n2m_interfaces_pkg::*;
    import n2m_cpu_pkg::*;
    import n2m_memory_pkg::*;
    integer lane;
    memory_oam_request_t oam_request;
    memory_oam_response_t oam_response;
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
    integer case_index, index, writes, total_writes, expected_address, trace;
    logic [7:0] expected_byte;
    logic [15:0] expected_pair;
    bit observe, overlay_job, corrupt;
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
        .ppu_oam_valid(raw_oam_valid), .wave_read(1'b0), .wave_address(4'd0),
        .wave_rdata(unused_wave), .wave_valid(unused_wave_valid));
    always #5 clk_sys=~clk_sys;
    function automatic logic[7:0] source_byte(input integer offset);
        case(offset)
            32,33:source_byte=8'h0f;
            34:source_byte=8'h55;35:source_byte=8'haa;
            36,37:source_byte=8'hf0;38:source_byte=8'h66;39:source_byte=8'h77;
            40:source_byte=8'hf3;
            default:source_byte=8'hcc;
        endcase
    endfunction
    function automatic logic[7:0] result_byte(input integer offset);
        case(offset)
            40:result_byte=case_index==0 ? 8'hf3:8'h03;
            41,42:result_byte=8'h55;43:result_byte=8'haa;
            44,45:result_byte=8'hf0;46:result_byte=8'h66;47:result_byte=8'h77;
            default:result_byte=0;
        endcase
    endfunction
    task automatic load_byte(input memory_store_t bank,input integer offset,input logic[7:0] value);
        @(negedge clk_sys);setup_store=bank;setup_address=15'(offset);setup_data=value;
        setup_write=1;@(negedge clk_sys);setup_write=0;
    endtask
    task automatic mcycle(input logic valid_request,input logic[15:0] address,input logic[7:0] data);
        if(cpu_phase!=0)$fatal(1,"DMA_OVERLAY_PREPARE_PHASE");
        request_valid=valid_request;bus_plan='0;bus_plan.address=address;
        bus_plan.write_enable=valid_request;bus_plan.write_data=data;
        repeat(4)begin
            repeat(cpu_phase==0 ? 4 : 5)@(negedge clk_sys);gb_tick=1;bus_commit=valid_request && cpu_phase==3;
            address_effect_sample=cpu_phase==3 && (valid_request || address_effect.valid);
            @(negedge clk_sys);gb_tick=0;bus_commit=0;address_effect_sample=0;cpu_phase=cpu_phase+2'd1;
        end
        request_valid=0;bus_plan='0;
        if(fault)$fatal(1,"DMA_OVERLAY_FAULT");
    endtask
    task automatic readback(input memory_store_t bank,input integer offset,input logic[7:0] expected);
        @(negedge clk_sys);setup_store=bank;setup_address=15'(offset);setup_read=1;
        @(negedge clk_sys);
        if(!access_valid || access_rdata!==expected)
            $fatal(1,"DMA_OVERLAY_READBACK case=%0d store=%0d address=%0d expected=%02x actual=%02x",case_index,bank,offset,expected,access_rdata);
        setup_read=0;
    endtask
    always @(posedge clk_sys)begin
        if(observe && access_write && access_store==STORE_OAM)begin
            if(!overlay_job)begin expected_address=writes;expected_byte=source_byte(writes);end
            else begin
                case(writes-40)
                    0:expected_address=44;1:expected_address=45;2:expected_address=40;3:expected_address=41;
                    4:expected_address=42;5:expected_address=43;6:expected_address=46;7:expected_address=47;
                    default:$fatal(1,"DMA_OVERLAY_EXTRA_WRITE");
                endcase
                expected_byte=result_byte(expected_address);
            end
            if(access_address!==15'(expected_address) || access_wdata!==expected_byte)
                $fatal(1,"DMA_OVERLAY_WRITE case=%0d address=%0d expected=%02x actual=%02x",case_index,access_address,expected_byte,access_wdata);
            $fdisplay(trace,"%0d,%0d,%0d,%02x",case_index,writes,access_address,access_wdata);
            writes=writes+1;total_writes=total_writes+1;
        end
            for (lane=0; lane<2; lane=lane+1) if (observe && oam_request.write_enable[lane]) begin
            if(!overlay_job)begin expected_address=writes;expected_byte=source_byte(writes);end
            else begin
                case(writes-40)
                    0:expected_address=44;1:expected_address=45;2:expected_address=40;3:expected_address=41;
                    4:expected_address=42;5:expected_address=43;6:expected_address=46;7:expected_address=47;
                    default:$fatal(1,"DMA_OVERLAY_EXTRA_WRITE");
                endcase
                expected_byte=result_byte(expected_address);
            end
            if((15'(oam_request.pair)*15'd2+15'(lane))!==15'(expected_address) || oam_request.data[8*lane +: 8]!==expected_byte)
                $fatal(1,"DMA_OVERLAY_WRITE case=%0d address=%0d expected=%02x actual=%02x",case_index,(15'(oam_request.pair)*15'd2+15'(lane)),expected_byte,oam_request.data[8*lane +: 8]);
            $fdisplay(trace,"%0d,%0d,%0d,%02x",case_index,writes,(15'(oam_request.pair)*15'd2+15'(lane)),oam_request.data[8*lane +: 8]);
            writes=writes+1;total_writes=total_writes+1;
        end
    end
    initial begin
        clk_sys=0;reset_sys=1;core_reset=0;setup=1;setup_read=0;setup_write=0;
        setup_store=STORE_OAM;setup_address=0;setup_data=0;host_write=0;host_address=0;host_data=0;
        gb_tick=0;cpu_phase=0;cpu_halted=0;cpu_stopped=0;request_valid=0;bus_commit=0;
        bus_plan='0;address_effect='0;address_effect_resolved=1;address_effect_sample=0;
        peripheral_rdata=0;peripheral_valid=1;peripheral_available=1;
        vram_cpu_allow=1;oam_cpu_allow=1;ppu_vram_request=0;ppu_vram_address=0;
        ppu_oam_phase=0;ppu_scan_index=0;ppu_oam_pair=0;
        case_index=0;writes=0;total_writes=0;expected_address=0;expected_byte=0;expected_pair=0;
        observe=0;overlay_job=0;corrupt=$test$plusargs("CORRUPT_OVERLAY");
        trace=$fopen("dma-overlay.csv","w");if(!trace)$fatal(1,"DMA_OVERLAY_TRACE");
        $dumpfile("dma-overlay.vcd");
        $dumpvars(0,clk_sys,reset_sys,core_reset,gb_tick,cpu_phase,request_valid,bus_commit,bus_plan,
            address_effect,address_effect_sample,dma_active,access_write,access_address,access_wdata,
            ppu_oam_phase,ppu_scan_index,ppu_oam_data,ppu_oam_valid,fault,case_index,writes,
            overlay_job,expected_address,expected_byte,expected_pair);
        repeat(3)@(negedge clk_sys);reset_sys=0;wait(memory_init_done);repeat(3)@(negedge clk_sys);
        for(case_index=0;case_index<2;case_index=case_index+1)begin
            setup=1;observe=0;writes=0;overlay_job=0;
            for(index=0;index<160;index=index+1)begin
                load_byte(STORE_WRAM,index,source_byte(index));load_byte(STORE_OAM,index,8'haa);
            end
            load_byte(STORE_OAM,41,8'h55);load_byte(STORE_WRAM,16'h123,8'h5a);
            setup=0;observe=1;
            mcycle(1,16'hff46,8'hc0);mcycle(0,0,0);
            for(index=0;index<39;index=index+1)mcycle(0,0,0);
            ppu_oam_phase=1;ppu_scan_index=8;mcycle(0,0,0);
            // Byte39 physically commits before row4 is prefetched for row5.
            ppu_scan_index=10;address_effect.valid=1;address_effect.write_effect=1;
            address_effect.address=16'hfe00;address_effect.known_mask=16'hffff;
            mcycle(case_index==1,16'hc123,8'h0f);
            overlay_job=1;address_effect='0;cpu_halted=1;ppu_oam_phase=2;ppu_oam_pair=20;
            expected_pair=case_index==0 ? 16'h55f3:16'h5503;
            repeat(40)begin
                @(negedge clk_sys);
                if(ppu_oam_valid && ppu_oam_data!==expected_pair)
                    $fatal(1,"DMA_OVERLAY_PAIR case=%0d expected=%04x actual=%04x",case_index,expected_pair,ppu_oam_data);
            end
            if(!ppu_oam_valid || writes!=48)$fatal(1,"DMA_OVERLAY_COMPLETE case=%0d writes=%0d valid=%0d",case_index,writes,ppu_oam_valid);
            observe=0;setup=1;
            for(index=0;index<40;index=index+1)readback(STORE_OAM,index,source_byte(index));
            for(index=40;index<48;index=index+1)readback(STORE_OAM,index,result_byte(index));
            readback(STORE_WRAM,40,8'hf3);readback(STORE_WRAM,16'h123,8'h5a);
            core_reset=1;ppu_oam_phase=0;repeat(2)@(negedge clk_sys);core_reset=0;
            wait(memory_init_done);repeat(3)@(negedge clk_sys);cpu_halted=0;
        end
        if(total_writes!=96)$fatal(1,"DMA_OVERLAY_TOTAL");
        $fclose(trace);$display("PASS DMA overlay feedback cases=2 writes=96 readback=100");$finish;
    end
    initial begin
        wait(corrupt && case_index==1 && overlay_job);
        wait(oam_request.write_enable[0] && oam_request.pair==20);@(negedge clk_sys);
        force dut.oam_request.data[7:0]=8'hf3;
    end
    initial begin #10000000;$fatal(1,"DMA_OVERLAY_WATCHDOG");end
endmodule
