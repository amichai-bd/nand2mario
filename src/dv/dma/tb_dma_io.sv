`timescale 1ns/1ps
`default_nettype none
module tb_dma_io;
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
    logic irq_selected;
    logic [7:0] irq_rdata, ie_stored, ie_observe, owner_reply;
    logic [4:0] if_stored, if_observe, source_event;
    memory_destination_t expected_destination;
    integer index, writes, age, commits, reads, t3_checks;
    bit observe, seen_start, event_case, bad_irq;
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
    n2m_interrupts interrupts (.clk_sys(clk_sys),.reset_sys(reset_sys),.core_reset(core_reset),
        .gb_tick(gb_tick),.io_commit(peripheral_commit && peripheral_destination==MEMORY_IRQ),
        .io_write(peripheral_write),.io_address(peripheral_address),.io_wdata(peripheral_wdata),
        .source_level(5'd0),.source_event(source_event),.irq_ack(5'd0),
        .io_selected(irq_selected),.io_rdata(irq_rdata),.ie_stored(ie_stored),.if_stored(if_stored),
        .ie_observe(ie_observe),.if_observe(if_observe));
    // Other owners supply a declared boundary reply; no register shadow is implemented.
    assign peripheral_rdata=irq_selected ? irq_rdata:owner_reply;
    assign peripheral_valid=1'b1;
    assign peripheral_available=1'b1;
    task automatic load_byte(input memory_store_t bank,input integer offset,input logic[7:0] value);
        @(negedge clk_sys);setup_store=bank;setup_address=15'(offset);setup_data=value;
        setup_write=1;@(negedge clk_sys);setup_write=0;
    endtask
    task automatic transaction(input logic valid_request,input logic wr,input logic[15:0] address,
        input logic[7:0] value,input memory_destination_t destination,input logic[7:0] expected_read);
        if(cpu_phase!=0)$fatal(1,"DMA_IO_PREPARE_PHASE");
        request_valid=valid_request;bus_plan='0;bus_plan.address=address;
        bus_plan.write_enable=wr;bus_plan.write_data=value;expected_destination=destination;
        owner_reply=expected_read;
        repeat(4)begin
            if(event_case && cpu_phase==2)source_event=5'h04;
            repeat(11)@(negedge clk_sys);
            if(event_case && cpu_phase==2)begin
                if(bad_irq)force if_observe=5'h00;
                #1;
                if(ie_observe!==8'h1f || if_observe!==5'h04 || !access_read || access_store!=STORE_OAM)
                    $fatal(1,"DMA_IO_IRQ_PRE_T3 expected_ie=1f actual_ie=%02x expected_if=04 actual_if=%02x raw_read=%0d",ie_observe,if_observe,access_read);
                t3_checks=t3_checks+1;
            end
            gb_tick=1;bus_commit=valid_request && cpu_phase==3;address_effect_sample=bus_commit;
            #1;
            if(valid_request && destination!=MEMORY_DMA)begin
                if(!peripheral_prepare || peripheral_destination!==destination || peripheral_address!==address ||
                    peripheral_write!==wr || peripheral_wdata!==value || peripheral_commit!==bus_commit)
                    $fatal(1,"DMA_IO_ROUTE address=%04x destination=%0d actual=%0d commit=%0d",address,destination,peripheral_destination,peripheral_commit);
            end else if(peripheral_commit)$fatal(1,"DMA_IO_LOCAL_COMMIT");
            if(bus_commit && !wr)begin
                if(!response_valid || read_data!==expected_read)
                    $fatal(1,"DMA_IO_READ address=%04x expected=%02x actual=%02x",address,expected_read,read_data);
                reads=reads+1;
            end
            @(negedge clk_sys);gb_tick=0;bus_commit=0;address_effect_sample=0;source_event=0;cpu_phase=cpu_phase+2'd1;
        end
        request_valid=0;bus_plan='0;
        if(fault)$fatal(1,"DMA_IO_FAULT");
    endtask
    always @(posedge clk_sys)begin
        if(observe)begin
            if(peripheral_commit)commits=commits+1;
            if(gb_tick && cpu_phase==3)begin
                if(bus_commit && bus_plan.address==16'hff46)begin seen_start=1;age=0;end
                else if(seen_start)age=age+1;
            end
            if(access_write && access_store==STORE_OAM)begin
                if(access_address!==15'(writes) || access_wdata!==8'h7b)
                    $fatal(1,"DMA_IO_TRANSFER index=%0d actual=%0d:%02x",writes,access_address,access_wdata);
                writes=writes+1;
            end
        end
    end
    initial begin
        clk_sys=0;reset_sys=1;core_reset=0;setup=1;setup_read=0;setup_write=0;
        setup_store=STORE_OAM;setup_address=0;setup_data=0;host_write=0;host_address=0;host_data=0;
        gb_tick=0;cpu_phase=0;cpu_halted=0;cpu_stopped=0;request_valid=0;bus_commit=0;
        bus_plan='0;address_effect='0;address_effect_resolved=1;address_effect_sample=0;
        owner_reply=0;source_event=0;expected_destination=MEMORY_IRQ;
        vram_cpu_allow=1;oam_cpu_allow=1;ppu_vram_request=0;ppu_vram_address=0;
        ppu_oam_phase=0;ppu_scan_index=8;ppu_oam_pair=0;
        writes=0;age=0;commits=0;reads=0;t3_checks=0;observe=0;seen_start=0;event_case=0;
        bad_irq=$test$plusargs("BAD_IRQ");
        $dumpfile("dma-io.vcd");
        $dumpvars(0,clk_sys,reset_sys,gb_tick,cpu_phase,request_valid,bus_commit,bus_plan,
            peripheral_prepare,peripheral_commit,peripheral_destination,peripheral_address,
            peripheral_write,peripheral_wdata,read_data,response_valid,access_read,access_write,
            access_store,access_address,access_wdata,ie_observe,if_observe,source_event,dma_active,
            expected_destination,writes,commits,reads,t3_checks,fault);
        repeat(3)@(negedge clk_sys);reset_sys=0;wait(memory_init_done);repeat(3)@(negedge clk_sys);
        for(index=0;index<160;index=index+1)begin load_byte(STORE_WRAM,index,8'h7b);load_byte(STORE_OAM,index,8'h10);end
        setup=0;observe=1;
        transaction(1,1,16'hffff,8'h1f,MEMORY_IRQ,0);
        transaction(1,1,16'hff0f,0,MEMORY_IRQ,0);
        ppu_oam_phase=1;
        transaction(1,1,16'hff46,8'hc0,MEMORY_DMA,0);transaction(0,0,0,0,MEMORY_DIRECT,0);
        event_case=1;transaction(1,0,16'hff0f,0,MEMORY_IRQ,8'he4);event_case=0;
        transaction(1,0,16'hffff,0,MEMORY_IRQ,8'h1f);
        transaction(1,1,16'hff00,8'h20,MEMORY_JOYP,0);transaction(1,0,16'hff00,0,MEMORY_JOYP,8'hc3);
        transaction(1,1,16'hff04,8'h99,MEMORY_TIMER,0);transaction(1,0,16'hff04,0,MEMORY_TIMER,8'ha4);
        transaction(1,1,16'hff10,8'h23,MEMORY_APU,0);transaction(1,0,16'hff10,0,MEMORY_APU,8'hb5);
        transaction(1,1,16'hff40,8'h93,MEMORY_PPU,0);transaction(1,0,16'hff40,0,MEMORY_PPU,8'h96);
        transaction(1,1,16'hff01,8'h5a,MEMORY_SERIAL,0);transaction(1,0,16'hff01,0,MEMORY_SERIAL,8'h67);
        transaction(1,1,16'hff0f,8'h01,MEMORY_IRQ,0);transaction(1,0,16'hff0f,0,MEMORY_IRQ,8'he1);
        transaction(1,1,16'hffff,8'ha5,MEMORY_IRQ,0);transaction(1,0,16'hffff,0,MEMORY_IRQ,8'ha5);
        while(age<161)transaction(0,0,0,0,MEMORY_DIRECT,0);
        repeat(30)@(negedge clk_sys);
        if(dma_active || writes!=160 || commits!=18 || reads!=9 || t3_checks!=1)
            $fatal(1,"DMA_IO_TOTAL bytes=%0d commits=%0d reads=%0d t3=%0d",writes,commits,reads,t3_checks);
        observe=0;setup=1;
        for(index=0;index<160;index=index+1)begin
            @(negedge clk_sys);setup_store=STORE_OAM;setup_address=15'(index);setup_read=1;
            @(negedge clk_sys);if(!access_valid || access_rdata!==8'h7b)$fatal(1,"DMA_IO_READBACK");
        end
        $display("PASS DMA IO bytes=160 owner_commits=18 reads=9 preT3=1 readback=160");$finish;
    end
    initial begin #10000000;$fatal(1,"DMA_IO_WATCHDOG");end
endmodule
