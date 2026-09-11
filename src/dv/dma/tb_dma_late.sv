`timescale 1ns/1ps
`default_nettype none
module tb_dma_late;
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
    integer index, case_index, checks, transfer, r, late_reads;
    logic [15:0] target;
    logic [15:0] expected_pair;
    bit corrupt;
    assign init_done=memory_init_done && !setup;
    logic oam_cpu_late_write, oam_late_future;
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
    always #20 clk_sys=~clk_sys;
    always @(posedge clk_sys) begin
        if(!reset_sys && !core_reset && oam_request.read && dut.service.pair_grant_kind==5)
            late_reads=late_reads+1;
    end
    task automatic load_byte(input integer offset, input logic [7:0] value);
        @(negedge clk_sys); setup_address=15'(offset); setup_data=value;
        setup_write=1; @(negedge clk_sys); setup_write=0;
    endtask
    task automatic dot_step;
        repeat(cpu_phase==0 ? 4 : 5) @(negedge clk_sys);
        gb_tick=1; bus_commit=request_valid && cpu_phase==3; address_effect_sample=bus_commit;
        @(negedge clk_sys); gb_tick=0; bus_commit=0; address_effect_sample=0; cpu_phase=cpu_phase+2'd1;
        if(fault) $fatal(1,"DMA_LATE_FAULT case=%0d",case_index);
    endtask
    task automatic readback;
        setup=1; setup_store=n2m_memory_pkg::STORE_OAM;
        for(index=0;index<160;index=index+1) begin
            @(negedge clk_sys); setup_address=15'(index); setup_read=1;
            @(negedge clk_sys);
            if(!access_valid || access_rdata!==expected_oam[index])
                $fatal(1,"DMA_LATE_STORAGE case=%0d offset=%0d expected=%02x actual=%02x",
                    case_index,index,expected_oam[index],access_rdata);
            setup_read=0;
        end
        checks=checks+1;
    endtask
    initial begin
        clk_sys=0; reset_sys=1; core_reset=0; setup=1; setup_read=0; setup_write=0;
        setup_store=n2m_memory_pkg::STORE_OAM; setup_address=0; setup_data=0; host_write=0; host_address=0; host_data=0;
        gb_tick=0; cpu_phase=0; cpu_halted=0; cpu_stopped=0; request_valid=0;
        bus_plan='0; bus_commit=0; address_effect='0; address_effect_resolved=1; address_effect_sample=0;
        peripheral_rdata=0; peripheral_valid=1; peripheral_available=1;
        vram_cpu_allow=1; oam_cpu_allow=0; ppu_vram_request=0; ppu_vram_address=0;
        ppu_oam_phase=0; ppu_scan_index=0; ppu_oam_pair=78;
        oam_cpu_late_write=0; oam_late_future=0; checks=0;late_reads=0;
        corrupt=$test$plusargs("CORRUPT_LATE_READY");
        $dumpfile("dma-late.vcd");
        $dumpvars(0,clk_sys,reset_sys,core_reset,gb_tick,cpu_phase,request_valid,bus_commit,
            bus_plan,oam_request,oam_response,raw_oam_read,raw_oam_pair,raw_oam_data,
            raw_oam_valid,ppu_oam_data,ppu_oam_valid,oam_late_future,oam_cpu_late_write,
            dut.service.slot_q,dut.service.late_ready_q,dut.service.late_selected_q,
            fault,case_index,checks);
        repeat(3) @(negedge clk_sys); reset_sys=0;
        wait(memory_init_done);
        for(case_index=0;case_index<8;case_index=case_index+1) begin
            setup=1; core_reset=1; @(negedge clk_sys); core_reset=0;
            wait(memory_init_done); cpu_phase=0;
            request_valid=0;bus_plan='0;address_effect='0;oam_cpu_late_write=0;oam_late_future=0;
            ppu_oam_phase=0;setup_store=n2m_memory_pkg::STORE_WRAM;
            for(index=0;index<160;index=index+1) load_byte(index,index==159 ? 8'h5a : 8'(37*index+11));
            setup_store=n2m_memory_pkg::STORE_OAM;
            for(index=0;index<160;index=index+1) begin
                expected_oam[index]=8'(37*index+11); load_byte(index,expected_oam[index]);
            end
            case(case_index)
                0:target=16'hfe9c;
                1:target=16'hfe9d;
                default:target=16'hfe20;
            endcase
            if(target==16'hfe20 && case_index<6) begin
                expected_oam[32]='h81;expected_oam[33]='h90;expected_oam[34]='h4d;expected_oam[35]='h72;
                expected_oam[36]='h97;expected_oam[37]='hbc;expected_oam[38]='he1;expected_oam[39]='h06;
            end else if(case_index<6) expected_oam[target-16'hfe00]='h81;
            expected_pair={expected_oam[157],expected_oam[156]};
            setup=0;
            if(case_index>=5) begin
                request_valid=1;bus_plan.address=16'hff46;bus_plan.write_enable=1;bus_plan.write_data=8'hc0;
                repeat(4) dot_step(); // M0 trigger.
                request_valid=0;bus_plan='0;repeat(4) dot_step(); // M1 activation.
                for(transfer=0;transfer<(case_index==7 ? 20 : 158);transfer=transfer+1) repeat(4) dot_step();
            end
            if(case_index==4 || case_index==5) begin
                // Prior M prepares ordinary row18 operands, after byte158 for case5.
                ppu_oam_phase=1;ppu_scan_index=35;repeat(4) dot_step();
                request_valid=1;bus_plan.address=16'hfe00;bus_plan.write_enable=0;
                address_effect.valid=1;address_effect.address=16'hfe00;
                address_effect.known_mask=16'hffff;address_effect.write_effect=1;
                // Independent READ_WRITE row18 literals for the seeded rows16..18.
                for(r=16;r<=18;r=r+1) begin
                    expected_oam[8*r]='h93;expected_oam[8*r+1]='hd8;
                    expected_oam[8*r+2]='hfd;expected_oam[8*r+3]='h22;
                    expected_oam[8*r+4]='h47;expected_oam[8*r+5]='h6c;
                    expected_oam[8*r+6]='h91;expected_oam[8*r+7]='hb6;
                end
            end
            if(case_index==7) begin
                request_valid=1;bus_plan.address=16'hff46;bus_plan.write_enable=1;bus_plan.write_data=8'hc0;
            end
            ppu_oam_phase=1; ppu_scan_index=37; oam_late_future=1;
            repeat(4) dot_step(); // P drains the preceding combined job before late operands.
            if(case_index==5) begin
                if(dma_active || !dut.pair_pending) $fatal(1,"DMA_LATE_TERMINAL_SETUP");
                expected_oam[159]='h5a;expected_oam[39]='h5a;
            end
            address_effect='0;
            oam_late_future=0; request_valid=1; bus_plan.address=target;
            bus_plan.write_enable=1; bus_plan.write_data='h81;
            if(case_index==3) begin
                // Pause immediately after P while the system service still drains.
                repeat(60) @(negedge clk_sys);
                if(!dut.service.late_ready_q || cpu_phase!=0 || fault)
                    $fatal(1,"DMA_LATE_PAUSED_PREPARE");
                checks=checks+1;
            end
            repeat(3) dot_step(); ppu_scan_index=39; oam_cpu_late_write=!dma_active;
            if(case_index>=6) begin
                if(!dma_active || dut.service.late_selected_q) $fatal(1,"DMA_LATE_ACTIVE_DENIAL");
                // Active DMA preserves the ordinary scanned-row write projection.
                expected_oam[152]='h4b;expected_oam[153]=0;expected_oam[154]='h25;expected_oam[155]='h4a;
                expected_oam[156]='h6f;expected_oam[157]='h94;expected_oam[158]='hb9;expected_oam[159]='hde;
            end
            expected_pair={expected_oam[157],expected_oam[156]};
            if(corrupt) force dut.service.late_ready_q=1'b0;
            dot_step(); // A at the same legal T4, no stretched CPU cycle.
            request_valid=0; bus_plan='0; oam_cpu_late_write=0;
            repeat(4) @(negedge clk_sys);
            // Before the A+5 edge, registered pair78 must already be fresh.
            if(case_index<6 && (!ppu_oam_valid || ppu_oam_data!==expected_pair))
                $fatal(1,"DMA_LATE_CAPTURE case=%0d expected=%04x actual=%04x valid=%0b",
                    case_index,expected_pair,ppu_oam_data,ppu_oam_valid);
            checks=checks+1;
            repeat(30) @(negedge clk_sys); ppu_oam_phase=0;
            readback();
            if(case_index==0) begin
                // Same-address reprepare without reset, then an immediate next read.
                setup=0;ppu_oam_phase=1;ppu_scan_index=37;oam_late_future=1;
                repeat(4) dot_step();oam_late_future=0;late_reads=0;
                request_valid=1;bus_plan.address=target;bus_plan.write_enable=1;bus_plan.write_data='h42;
                repeat(3) dot_step();ppu_scan_index=39;oam_cpu_late_write=1;dot_step();
                if(late_reads!=5 || dut.service.late_ready_q) $fatal(1,"DMA_LATE_REPREPARE");
                checks=checks+1;expected_oam[156]='h42;
                bus_plan.write_enable=0;bus_plan.write_data=0;oam_cpu_allow=1;oam_cpu_late_write=0;
                repeat(4) @(negedge clk_sys);
                if(!ppu_oam_valid || ppu_oam_data!==16'hbc42) $fatal(1,"DMA_LATE_REPEAT_CAPTURE");
                checks=checks+1;
                // Consume T1 at A+5, then the next read at A+23.
                gb_tick=1;@(negedge clk_sys);gb_tick=0;cpu_phase=1;ppu_oam_phase=0;
                repeat(2) dot_step();repeat(5) @(negedge clk_sys);
                gb_tick=1;bus_commit=1;address_effect_sample=1;
                if(!response_valid || read_data!==8'h42) $fatal(1,"DMA_LATE_NEXT_READ");
                @(negedge clk_sys);gb_tick=0;bus_commit=0;address_effect_sample=0;cpu_phase=0;
                request_valid=0;bus_plan='0;oam_cpu_allow=0;checks=checks+1;
                repeat(30) @(negedge clk_sys);readback();
            end
        end
        // Reset during operand preparation and after the first drain write.
        for(r=0;r<2;r=r+1) begin
            core_reset=1;request_valid=0;bus_plan='0;oam_cpu_late_write=0;ppu_oam_phase=0;
            @(negedge clk_sys);core_reset=0;wait(memory_init_done);
            setup=0;cpu_phase=0;ppu_oam_phase=1;ppu_scan_index=37;oam_late_future=1;
            repeat(4) dot_step();oam_late_future=0;
            request_valid=1;bus_plan.address=16'hfe20;bus_plan.write_enable=1;bus_plan.write_data='h81;
            if(r==0) repeat(16) @(negedge clk_sys);
            else begin
                repeat(3) dot_step();ppu_scan_index=39;oam_cpu_late_write=1;dot_step();
                @(negedge clk_sys);
            end
            core_reset=1;request_valid=0;bus_plan='0;oam_cpu_late_write=0;ppu_oam_phase=0;
            @(negedge clk_sys);
            if(oam_request.read || |oam_request.write_enable || access_write || dut.service.late_ready_q
                || ppu_oam_valid || fault) $fatal(1,"DMA_LATE_RESET_CANCEL");
            checks=checks+1;core_reset=0;wait(memory_init_done);
        end
        if(checks!=23) $fatal(1,"DMA_LATE_COUNTS");
        $display("PASS DMA late owner checks=23");$finish;
    end
    initial begin #10000000;$fatal(1,"DMA_LATE_WATCHDOG");end
endmodule
