`timescale 1ns/1ps
`default_nettype none
module tb_dma_reset;
    import n2m_interfaces_pkg::*;
    import n2m_cpu_pkg::*;
    import n2m_memory_pkg::*;
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
    integer case_index, reset_path, context_index, reset_phase, index, cycle_index;
    integer write_count, total_writes, readback_count, expected_count, expected_address;
    integer trace;
    logic [7:0] expected_byte;
    bit observe, clearing, stale_reset;
    assign init_done=memory_init_done && !setup;
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
    task automatic load_byte(input memory_store_t bank,input integer offset,input logic[7:0] value);
        @(negedge clk_sys);setup_store=bank;setup_address=15'(offset);setup_data=value;
        setup_write=1;@(negedge clk_sys);setup_write=0;
    endtask
    task automatic dot_step;
        repeat(cpu_phase==0 ? 4 : 5) @(negedge clk_sys);
        gb_tick=1;bus_commit=request_valid && cpu_phase==3;
        address_effect_sample=cpu_phase==3 && (request_valid || address_effect.valid);
        @(negedge clk_sys);gb_tick=0;bus_commit=0;address_effect_sample=0;cpu_phase=cpu_phase+2'd1;
    endtask
    task automatic mcycle(input logic write_page,input logic[7:0] page);
        if(cpu_phase!=0)$fatal(1,"DMA_RESET_PREPARE_PHASE");
        request_valid=write_page;bus_plan='0;bus_plan.address=16'hff46;
        bus_plan.write_enable=write_page;bus_plan.write_data=page;
        repeat(4)dot_step();request_valid=0;bus_plan='0;
    endtask
    task automatic check_cancel;
        if(dma_active || dut.engine_source_request || access_write || peripheral_commit ||
            ppu_oam_valid || dut.pair_pending || fault)
            $fatal(1,"DMA_RESET_CANCEL case=%0d active=%0d source=%0d write=%0d peripheral=%0d pair_valid=%0d pending=%0d fault=%0d",
                case_index,dma_active,dut.engine_source_request,access_write,peripheral_commit,ppu_oam_valid,dut.pair_pending,fault);
    endtask
    always @(posedge clk_sys) begin
        if(observe && !reset_sys && !core_reset && access_write && access_store==STORE_OAM) begin
            if(clearing)$fatal(1,"DMA_RESET_LATE_WRITE case=%0d",case_index);
            if(context_index==3) begin
                case(write_count)
                    0:expected_address=44;1:expected_address=45;2:expected_address=40;3:expected_address=41;
                    4:expected_address=42;5:expected_address=43;6:expected_address=46;7:expected_address=47;
                    default:$fatal(1,"DMA_RESET_EXTRA_CORRUPTION");
                endcase
                expected_byte=8'(expected_address+24);
            end else begin
                expected_address=write_count;expected_byte=8'(write_count)^8'h69;
                if(context_index==0 || write_count>1)$fatal(1,"DMA_RESET_EXTRA_TRANSFER");
            end
            if(access_address!==15'(expected_address) || access_wdata!==expected_byte)
                $fatal(1,"DMA_RESET_PREFIX case=%0d expected=%0d:%02x actual=%0d:%02x",
                    case_index,expected_address,expected_byte,access_address,access_wdata);
            $fdisplay(trace,"%0d,%0d,%0d,%02x",case_index,write_count,access_address,access_wdata);
            write_count=write_count+1;total_writes=total_writes+1;
        end
        if(clearing && !reset_sys && !core_reset && (dma_active || dut.engine_source_request || peripheral_commit || fault))
            $fatal(1,"DMA_RESET_ORPHAN case=%0d",case_index);
    end
    initial begin
        clk_sys=0;reset_sys=1;core_reset=0;setup=1;setup_read=0;setup_write=0;
        setup_store=STORE_OAM;setup_address=0;setup_data=0;host_write=0;host_address=0;host_data=0;
        gb_tick=0;cpu_phase=0;cpu_halted=0;cpu_stopped=0;request_valid=0;bus_commit=0;
        bus_plan='0;address_effect='0;address_effect_resolved=1;address_effect_sample=0;
        peripheral_rdata=0;peripheral_valid=1;peripheral_available=1;
        vram_cpu_allow=1;oam_cpu_allow=1;ppu_vram_request=0;ppu_vram_address=0;
        ppu_oam_phase=0;ppu_scan_index=0;ppu_oam_pair=0;
        case_index=0;write_count=0;total_writes=0;readback_count=0;expected_count=0;expected_address=0;expected_byte=0;
        observe=0;clearing=0;stale_reset=$test$plusargs("STALE_RESET");
        trace=$fopen("dma-reset.csv","w");if(!trace)$fatal(1,"DMA_RESET_TRACE");
        $dumpfile("dma-reset.vcd");
        $dumpvars(0,clk_sys,reset_sys,core_reset,memory_init_done,gb_tick,cpu_phase,request_valid,bus_commit,
            address_effect,address_effect_sample,dma_active,access_write,access_address,access_wdata,
            peripheral_commit,ppu_oam_valid,fault,case_index,context_index,reset_phase,reset_path,write_count,
            expected_count,total_writes,readback_count,clearing,dut.engine_source_request,dut.pair_pending);
        repeat(3)@(negedge clk_sys);reset_sys=0;wait(memory_init_done);repeat(3)@(negedge clk_sys);
        for(reset_path=0;reset_path<2;reset_path=reset_path+1)
        for(context_index=0;context_index<4;context_index=context_index+1)
        for(reset_phase=0;reset_phase<4;reset_phase=reset_phase+1) begin
            setup=1;observe=0;clearing=0;write_count=0;
            for(index=0;index<160;index=index+1) begin
                load_byte(STORE_WRAM,index,8'(index)^8'h69);
                load_byte(STORE_WRAM,256+index,8'(index)^8'hc3);
                load_byte(STORE_OAM,index,8'(index+32));
            end
            setup=0;observe=1;
            if(context_index==3) begin
                // A row4 prefetch supplies row5 operands; the next A starts eight writes.
                ppu_oam_phase=1;ppu_scan_index=8;mcycle(0,0);
                ppu_scan_index=10;address_effect.valid=1;address_effect.write_effect=1;
                address_effect.address=16'hfe00;address_effect.known_mask=16'hffff;
                mcycle(0,0);address_effect='0;
            end else begin
                mcycle(1,8'hc0);
                if(context_index>0) begin mcycle(0,0);mcycle(0,0);end
                if(context_index==2)mcycle(1,8'hc1);
            end
            repeat(reset_phase)dot_step();
            if(cpu_phase!==2'(reset_phase))$fatal(1,"DMA_RESET_PHASE");
            case(context_index)
                0:expected_count=0;
                1:expected_count=reset_phase==3 ? 1:0;
                2:expected_count=reset_phase==3 ? 2:1;
                3:expected_count=reset_phase==0 ? 0:8;
            endcase
            if(write_count!=expected_count)$fatal(1,"DMA_RESET_PREFIX_COUNT case=%0d expected=%0d actual=%0d",case_index,expected_count,write_count);
            // Reset is asserted after phase0/1/2/3, before the next accepting T4.
            core_reset=reset_path==1;reset_sys=reset_path==0;gb_tick=0;cpu_phase=0;
            request_valid=0;bus_commit=0;address_effect_sample=0;address_effect='0;ppu_oam_phase=0;
            clearing=1;
            repeat(2)@(negedge clk_sys);
            if(stale_reset && case_index==0)force dut.access_write=1'b1;
            #1;check_cancel();
            if(memory_init_done)$fatal(1,"DMA_RESET_CLEAR_START");
            @(negedge clk_sys);reset_sys=0;core_reset=0;
            wait(memory_init_done);repeat(3)@(negedge clk_sys);check_cancel();
            setup=1;
            for(index=0;index<160;index=index+1) begin
                @(negedge clk_sys);setup_store=STORE_OAM;setup_address=15'(index);setup_read=1;
                @(negedge clk_sys);
                if(!access_valid || access_rdata!==8'h00)$fatal(1,"DMA_RESET_READBACK case=%0d offset=%0d actual=%02x",case_index,index,access_rdata);
                readback_count=readback_count+1;
            end
            setup_read=0;setup=0;
            repeat(8)mcycle(0,0);
            request_valid=1;bus_plan='0;bus_plan.address=16'hff46;
            repeat(4)dot_step();
            if(!response_valid || read_data!==8'h00)$fatal(1,"DMA_RESET_FF46 case=%0d actual=%02x",case_index,read_data);
            request_valid=0;bus_plan='0;check_cancel();case_index=case_index+1;
        end
        if(total_writes!=60 || readback_count!=5120)$fatal(1,"DMA_RESET_TOTAL writes=%0d reads=%0d",total_writes,readback_count);
        $fclose(trace);$display("PASS DMA reset cases=32 prefix_writes=60 readback=5120 ff46=32");$finish;
    end
    initial begin #20000000;$fatal(1,"DMA_RESET_WATCHDOG");end
endmodule
