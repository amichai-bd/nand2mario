`timescale 1ns/1ps
`default_nettype none
module tb_dma_tags;
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
    integer index, writes, expected_address;
    logic [7:0] expected_byte;
    bit observe, raw_fault, operand_fault, pair_fault, data_fault, armed;
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
    task automatic load_byte(input memory_store_t bank,input integer offset,input logic[7:0] value);
        @(negedge clk_sys);setup_store=bank;setup_address=15'(offset);setup_data=value;
        setup_write=1;@(negedge clk_sys);setup_write=0;
    endtask
    task automatic mcycle(input logic page_write,input logic effect);
        if(cpu_phase!=0)$fatal(1,"DMA_TAG_PREPARE_PHASE");
        request_valid=page_write;bus_plan='0;bus_plan.address=16'hff46;
        bus_plan.write_enable=page_write;bus_plan.write_data=8'hc0;
        address_effect='0;
        if(effect)address_effect={1'b1,16'hfe00,16'hffff,1'b1};
        repeat(4)begin
            repeat(11)@(negedge clk_sys);gb_tick=1;bus_commit=page_write && cpu_phase==3;
            address_effect_sample=cpu_phase==3 && (page_write || effect);
            @(negedge clk_sys);gb_tick=0;bus_commit=0;address_effect_sample=0;cpu_phase=cpu_phase+2'd1;
        end
        request_valid=0;bus_plan='0;address_effect='0;
    endtask
    always @(posedge clk_sys)begin
        if(observe && access_write && access_store==STORE_OAM)begin
            case(writes)
                0:expected_address=108;1:expected_address=109;2:expected_address=104;3:expected_address=105;
                4:expected_address=106;5:expected_address=107;6:expected_address=110;7:expected_address=111;
                default:$fatal(1,"DMA_TAG_EXTRA_WRITE");
            endcase
            expected_byte=8'(expected_address+24);
            if(access_address!==15'(expected_address) || access_wdata!==expected_byte)
                $fatal(1,"DMA_TAG_FRESH_ROW address=%0d expected=%02x actual=%02x",access_address,expected_byte,access_wdata);
            writes=writes+1;
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
        writes=0;expected_address=0;expected_byte=0;observe=0;armed=0;
        raw_fault=$test$plusargs("MISSING_RAW");operand_fault=$test$plusargs("MISSING_OPERAND");
        pair_fault=$test$plusargs("MISSING_PAIR");data_fault=$test$plusargs("BAD_TAG_DATA");
        $dumpfile("dma-tags.vcd");
        $dumpvars(0,clk_sys,reset_sys,gb_tick,cpu_phase,request_valid,bus_commit,address_effect,
            address_effect_sample,ppu_oam_phase,ppu_scan_index,access_read,access_write,
            access_address,access_wdata,access_rdata,access_valid,expected_address,expected_byte,
            writes,fault,armed,dma_active);
        repeat(3)@(negedge clk_sys);reset_sys=0;wait(memory_init_done);repeat(3)@(negedge clk_sys);
        for(index=0;index<160;index=index+1)begin
            load_byte(STORE_OAM,index,8'(index+32));load_byte(STORE_WRAM,index,8'h69);
        end
        setup=0;observe=1;armed=1;
        if(pair_fault)begin
            mcycle(1,0);mcycle(0,0);
            force dut.service.other_valid_q=1'b0;
            mcycle(0,0);$fatal(1,"DMA_TAG_PAIR_NOT_REJECTED");
        end
        // Row4 prepares row5. An excluded interval discards that old context.
        ppu_oam_phase=1;ppu_scan_index=8;mcycle(0,0);
        if(operand_fault)begin
            ppu_scan_index=26;mcycle(0,1);$fatal(1,"DMA_TAG_OPERAND_NOT_REJECTED");
        end
        ppu_oam_phase=0;mcycle(0,0);
        ppu_oam_phase=1;ppu_scan_index=24;mcycle(0,0);
        ppu_scan_index=26;mcycle(0,1);
        repeat(40)@(negedge clk_sys);
        if(fault || writes!=8)$fatal(1,"DMA_TAG_TOTAL writes=%0d fault=%0d",writes,fault);
        observe=0;setup=1;
        for(index=104;index<112;index=index+1)begin
            @(negedge clk_sys);setup_store=STORE_OAM;setup_address=15'(index);setup_read=1;
            @(negedge clk_sys);
            if(!access_valid || access_rdata!==8'(index+24))$fatal(1,"DMA_TAG_READBACK");
        end
        $display("PASS DMA scan tags row4 off row12 row13 writes=8 readback=8");$finish;
    end
    initial begin
        wait(armed && raw_fault && access_read);@(negedge clk_sys);force access_valid=1'b0;
    end
    initial begin
        wait(armed && data_fault && access_read && access_address==100);
        @(posedge clk_sys);@(negedge clk_sys);force access_rdata=8'h00;
        @(negedge clk_sys);release access_rdata;
    end
    initial begin #10000000;$fatal(1,"DMA_TAG_WATCHDOG");end
endmodule
