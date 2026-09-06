`timescale 1ns/1ps
`default_nettype none
module tb_dma_composition;
    import n2m_interfaces_pkg::*;
    import n2m_cpu_pkg::*;
    import n2m_memory_pkg::*;
    logic clk_sys, reset_sys, core_reset, init_done, memory_init_done, gb_tick, paused, run_enable;
    logic [63:0] dot_before;
    logic [1:0] cpu_phase;
    logic cpu_halted, cpu_stopped, cpu_initialized, request_valid, bus_commit;
    logic [7:0] test_ie;
    logic [4:0] test_if;
    logic [63:0] wake_dot;
    integer held_count;
    bit halt_case, seen_wake, resumed_dma;
    cpu_bus_plan_t bus_plan;
    cpu_address_effect_t address_effect;
    logic address_effect_resolved, address_effect_sample;
    logic [7:0] read_data;
    logic response_valid, fault, cpu_fault, ppu_fault;
    logic peripheral_prepare, peripheral_commit, peripheral_write;
    memory_destination_t peripheral_destination;
    logic [15:0] peripheral_address;
    logic [7:0] peripheral_wdata, peripheral_rdata;
    logic peripheral_valid, peripheral_available, ppu_selected;
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
    logic [7:0] program_bytes [128];
    logic [15:0] old_words [3][4];
    logic [15:0] new_words [3][4];
    logic [15:0] expected_held, observed_pair;
    logic [6:0] previous_pair;
    logic previous_pair_request;
    integer index, phase_count, dma_age, dma_count, checks, effects, row, r, w, b;
    integer selected_offset, trace, retired;
    bit observe, seen_start, a_bit, b_bit, c_bit, d_bit;
    bit corrupt_byte, invalid_case, hardware_fault;
    assign init_done=memory_init_done && !setup;
    n2m_dma dut (.*);
    n2m_timebase timebase (.clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset),
        .pause_request(!run_enable), .paused(paused), .gb_tick(gb_tick));
    n2m_cpu cpu (.clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset),
        .gb_tick(gb_tick), .profile_id(PROFILE_DIRECT_ID), .epoch(32'd1), .dot_before(dot_before),
        .ie(test_ie), .iflags(test_if), .buttons(8'd0), .read_data(read_data), .response_valid(response_valid),
        .joyp_selected_active(1'b0), .wake_request(1'b0), .request_valid(request_valid),
        .address(bus_plan.address), .write_data(bus_plan.write_data), .write_enable(bus_plan.write_enable),
        .access_kind(bus_plan.access_kind), .bus_commit(bus_commit), .address_effect(address_effect),
        .address_effect_resolved(address_effect_resolved), .address_effect_sample(address_effect_sample),
        .address_effect_phase(cpu_phase), .irq_ack(), .halted(cpu_halted), .stopped(cpu_stopped),
        .locked(), .initialized(cpu_initialized), .fault(cpu_fault), .ime_observe(), .ime_delay_observe(),
        .stop_execute(), .divider_reset_request(), .instruction_complete(), .retirement_valid(), .retirement());
    n2m_ppu ppu (.clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset),
        .gb_tick(gb_tick), .epoch(32'd1), .dot_before(dot_before),
        .io_commit(peripheral_commit), .io_write(peripheral_write), .io_address(peripheral_address),
        .io_wdata(peripheral_wdata), .io_selected(ppu_selected), .io_rdata(peripheral_rdata),
        .vram_request(ppu_vram_request), .vram_address(ppu_vram_address),
        .vram_data(ppu_vram_data), .vram_valid(ppu_vram_valid), .oam_pair_address(ppu_oam_pair),
        .oam_phase(ppu_oam_phase), .oam_scan_index(ppu_scan_index), .oam_data(ppu_oam_data),
        .oam_valid(ppu_oam_valid), .dma_active(dma_active), .vram_cpu_allow(vram_cpu_allow),
        .oam_cpu_allow(oam_cpu_allow), .stat_condition(), .vblank_condition(), .stat_rise(),
        .vblank_rise(), .fault(ppu_fault), .source_valid(), .source_start(), .source_shade(),
        .source_x(), .source_y(), .source_epoch(), .source_dot(), .source_abort(),
        .blank_assert(), .source_display_eligible());
    assign peripheral_valid=ppu_selected;
    assign peripheral_available=ppu_selected;
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
    function automatic logic [7:0] sprite_byte(input integer offset);
        case(offset%4)
            0: sprite_byte=16;
            1: sprite_byte=8'(8+(offset/4)*2);
            2: sprite_byte=0;
            default: sprite_byte=8'((offset/4)&7);
        endcase
    endfunction
    task automatic load_byte(input memory_store_t bank, input integer offset, input logic [7:0] value);
        @(negedge clk_sys); setup_store=bank; setup_address=15'(offset); setup_data=value;
        setup_write=1; @(negedge clk_sys); setup_write=0;
    endtask
    // Independent sequential word oracle, with every intermediate row retained.
    task automatic corrupt_row(input integer which, input bit read_access, input bit write_access);
        if(which>0 && (read_access || write_access)) begin
            for(r=0;r<3;r=r+1) for(w=0;w<4;w=w+1) begin
                old_words[r][w]=0;
                if(which-2+r>=0)
                    old_words[r][w]={expected_oam[(which-2+r)*8+w*2+1],expected_oam[(which-2+r)*8+w*2]};
                new_words[r][w]=old_words[r][w];
            end
            if(read_access && write_access && which>=4 && which<=18) begin
                for(b=0;b<16;b=b+1) begin
                    a_bit=old_words[0][0][b]; b_bit=old_words[1][0][b];
                    c_bit=old_words[2][0][b]; d_bit=old_words[1][2][b];
                    new_words[1][0][b]=(b_bit && (a_bit || c_bit || d_bit)) || (a_bit && c_bit && d_bit);
                end
                for(w=0;w<4;w=w+1) begin new_words[0][w]=new_words[1][w]; new_words[2][w]=new_words[1][w]; end
            end
            for(b=0;b<16;b=b+1) begin
                a_bit=new_words[2][0][b]; b_bit=new_words[1][0][b]; c_bit=new_words[1][2][b];
                new_words[2][0][b]=read_access ? b_bit || (a_bit && c_bit) :
                    int'(a_bit)+int'(b_bit)+int'(c_bit)>=2;
            end
            for(w=1;w<4;w=w+1) new_words[2][w]=new_words[1][w];
            for(r=0;r<3;r=r+1) if(r==2 || (read_access && write_access && which>=4 && which<=18))
                for(w=0;w<4;w=w+1) begin
                    expected_oam[(which-2+r)*8+w*2]=new_words[r][w][7:0];
                    expected_oam[(which-2+r)*8+w*2+1]=new_words[r][w][15:8];
                end
        end
    endtask
    always @(posedge clk_sys) begin
        if(reset_sys) dot_before<=0;
        else if(gb_tick) dot_before<=dot_before+1;
        if(observe) begin
            if((fault || cpu_fault || ppu_fault) && !hardware_fault) $fatal(1,"DMA_COMPOSITION_FAULT");
            if(invalid_case && address_effect_sample && !dut.qualify.effect_resolved &&
                (dut.engine.write_valid || access_write || peripheral_commit))
                $fatal(1,"DMA_INVALID_EFFECT_CANCEL");
            if(hardware_fault && fault && (access_write || peripheral_commit || dut.engine.write_valid))
                $fatal(1,"DMA_LATCHED_EFFECT_CANCEL");
            if(gb_tick && previous_pair_request && ppu_oam_phase!=0) begin
                if(!dma_active) observed_pair={expected_oam[int'(previous_pair)*2+1],expected_oam[int'(previous_pair)*2]};
                else observed_pair=expected_held;
                if((!dma_active || ppu_oam_phase==2) && (!ppu_oam_valid || ppu_oam_data!==observed_pair))
                    $fatal(1,"DMA_COMPOSITION_PPU pair=%0d expected=%04x actual=%04x",previous_pair,observed_pair,ppu_oam_data);
                checks=checks+1;
            end
            if(gb_tick && cpu_phase==3) begin
                if(bus_commit && bus_plan.write_enable && bus_plan.address==16'hff46) begin
                    if(seen_start) $fatal(1,"DMA_COMPOSITION_UNEXPECTED_RESTART");
                    seen_start=1; dma_age=0;
                end else if(seen_start && !cpu_halted && !cpu_stopped) dma_age=dma_age+1;
                if(seen_start && !cpu_halted && !cpu_stopped && dma_age>=2 && dma_age<=161) begin
                    selected_offset=dma_age-2;
                    if(seen_wake && !resumed_dma) begin
                        if(dot_before+1!=wake_dot+4) $fatal(1,"DMA_HALT_WAKE_DOT expected=%0d actual=%0d",wake_dot+4,dot_before+1);
                        resumed_dma=1;
                    end
                    expected_oam[selected_offset]=halt_case && selected_offset==1 ? 8'h27 : sprite_byte(selected_offset);
                    dma_count=dma_count+1;
                end
                if(address_effect_sample && address_effect.valid && address_effect.write_effect &&
                    address_effect.address[15:8]==8'hfe) begin
                    if(address_effect.address!==16'('hfe00+effects)) $fatal(1,"DMA_COMPOSITION_IDU");
                    effects=effects+1;
                    if(ppu_oam_phase==1) corrupt_row(int'(ppu_scan_index)/2,0,1);
                end
                if(seen_start && !cpu_halted && !cpu_stopped && dma_age>=2 && dma_age<=161)
                    expected_held={expected_oam[(selected_offset/2)*2+1],expected_oam[(selected_offset/2)*2]};
            end
            if(access_write && access_store==STORE_OAM) begin
                if(access_wdata!==expected_oam[access_address])
                    $fatal(1,"DMA_COMPOSITION_WRITE address=%0d expected=%02x actual=%02x",access_address,expected_oam[access_address],access_wdata);
                $fdisplay(trace,"%0d,%0d,%02x,%02x",dot_before,access_address,expected_oam[access_address],access_wdata);
            end
        end
        previous_pair=ppu_oam_pair;
        previous_pair_request=ppu_oam_phase!=0;
    end
    initial begin
        clk_sys=0; reset_sys=1; core_reset=0; run_enable=0; setup=1;
        setup_read=0; setup_write=0; setup_store=STORE_ROM; setup_address=0; setup_data=0;
        host_write=0; host_address=0; host_data=0; observe=0; seen_start=0;
        dma_age=0; dma_count=0; checks=0; effects=0; expected_held=0;
        previous_pair=0; previous_pair_request=0; dot_before=0;
        corrupt_byte=$test$plusargs("CORRUPT_BYTE");
        invalid_case=$test$plusargs("INVALID_OBSERVATION");
        hardware_fault=$test$plusargs("HARDWARE_FAULT");
        halt_case=$test$plusargs("HALT_CASE"); test_ie=0; test_if=0;
        seen_wake=0; resumed_dma=0; wake_dot=0; held_count=0;
        trace=$fopen("dma-composition.csv","w");
        $dumpfile("dma-composition.vcd");
        $dumpvars(0,clk_sys,gb_tick,cpu_phase,bus_commit,bus_plan,address_effect,address_effect_sample,
            dma_active,access_read,access_write,access_store,access_address,access_wdata,
            ppu_oam_phase,ppu_scan_index,ppu_oam_pair,ppu_oam_data,ppu_oam_valid,
            fault,cpu_fault,ppu_fault,read_data,response_valid,dma_count,effects,expected_held,
            reset_sys,core_reset,memory_init_done,cpu_initialized,setup,run_enable,paused,request_valid,
            cpu_halted,test_ie,test_if,wake_dot,seen_wake,resumed_dma,dut.invalid_observation,
            dut.engine.write_valid,peripheral_commit,dut.service.dma_held_pair);
        repeat(3) @(negedge clk_sys); reset_sys=0;
        core_reset=1; repeat(2) @(negedge clk_sys); core_reset=0;
        wait(memory_init_done); repeat(3) @(negedge clk_sys);
        for(index=0;index<160;index=index+1) begin
            load_byte(STORE_WRAM,index,halt_case && index==1 ? 8'h27 : sprite_byte(index));
            load_byte(STORE_OAM,index,sprite_byte(index)); expected_oam[index]=sprite_byte(index);
        end
        for(index=0;index<128;index=index+1) program_bytes[index]=0;
        // Original HRAM program: LCD on, HL=FE00, DMA C000,64 IDU increments.
        program_bytes[0]='h3e; program_bytes[1]='h93; program_bytes[2]='he0; program_bytes[3]='h40;
        program_bytes[4]='h21; program_bytes[5]='h00; program_bytes[6]='hfe;
        program_bytes[7]='h3e; program_bytes[8]='hc0; program_bytes[9]='he0; program_bytes[10]='h46;
        program_bytes[11]='h06; program_bytes[12]='h40; program_bytes[13]='h23;
        program_bytes[14]='h05; program_bytes[15]='h20; program_bytes[16]='hfc; program_bytes[17]='h76;
        if(halt_case) begin
            // LDH retirement spans M1; immediate HALT entry M2 writes even byte0.
            program_bytes[11]='h76; program_bytes[12]='h18; program_bytes[13]='hfe;
        end
        for(index=0;index<127;index=index+1) load_byte(STORE_HRAM,index,program_bytes[index]);
        for(index=0;index<3;index=index+1) begin
            @(negedge clk_sys); host_address=32'('h100+index);
            case(index) 0: host_data='hc3; 1: host_data='h80; default: host_data='hff; endcase
            host_write=1; @(negedge clk_sys); host_write=0;
        end
        if(!cpu_initialized) $fatal(1,"DMA_COMPOSITION_CORE_INITIALIZE");
        @(negedge clk_sys); setup=0; observe=1; run_enable=1;
        if(invalid_case) begin
            wait(seen_start && dma_age==4); @(negedge clk_sys);
            force dut.qualify.effect_resolved=1'b0;
            if(hardware_fault) begin
                wait(fault); repeat(200) @(negedge clk_sys);
                if(access_write || peripheral_commit || dut.engine.write_valid)
                    $fatal(1,"DMA_LATCHED_EFFECT_CANCEL");
                $display("PASS DMA invalid observation cancels current and latched effects");
                $finish;
            end
        end
        if(corrupt_byte) begin
            wait(seen_start && access_write && access_store==STORE_OAM && access_address==5);
            @(negedge clk_sys); force dut.access_wdata=8'h00;
        end
        wait(cpu_halted);
        if(halt_case) begin
            @(negedge clk_sys); held_count=dma_count;
            if(held_count!=1 || !dma_active || expected_held!==16'h0810 || dut.service.dma_held_pair!==16'h0810)
                $fatal(1,"DMA_HALT_EVEN_PAIR count=%0d pair=%04x",held_count,expected_held);
            repeat(1000) begin
                @(negedge clk_sys);
                if(dut.service.dma_held_pair!==16'h0810) $fatal(1,"DMA_HALT_ACTUAL_PAIR");
            end
            if(dma_count!=held_count || !dma_active) $fatal(1,"DMA_HALT_PROGRESS");
            test_ie=1; test_if=1;
            wait(!cpu_halted); wake_dot=dot_before; seen_wake=1;
            wait(dma_count==160);
            if(!resumed_dma) $fatal(1,"DMA_HALT_NO_RESUME");
        end
        @(negedge clk_sys); run_enable=0;
        repeat(60) @(negedge clk_sys);
        if(dma_count!=160 || effects!=(halt_case ? 0 : 64) || checks==0) $fatal(1,"DMA_COMPOSITION_COUNTS dma=%0d effects=%0d ppu=%0d",dma_count,effects,checks);
        observe=0; setup=1;
        for(index=0;index<160;index=index+1) begin
            @(negedge clk_sys); setup_read=1; setup_store=STORE_OAM; setup_address=15'(index);
            @(negedge clk_sys);
            if(!access_valid || access_rdata!==expected_oam[index])
                $fatal(1,"DMA_COMPOSITION_READBACK offset=%0d expected=%02x actual=%02x",index,expected_oam[index],access_rdata);
        end
        $fclose(trace);
        $display("PASS DMA composition bytes=160 idu=%0d halt=%0d ppu=%0d",effects,halt_case,checks); $finish;
    end
    initial begin #10000000; $fatal(1,"DMA_COMPOSITION_WATCHDOG"); end
endmodule
