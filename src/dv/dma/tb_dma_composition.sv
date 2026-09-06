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
    bit halt_case, stop_case, power_case, seen_wake, resumed_dma;
    logic test_wake, stop_execute;
    cpu_stop_action_t clock_stop_action;
    logic [63:0] sleep_dot, pause_dot;
    logic [1:0] pause_sample_phase;
    integer pause_phase, pause_count, pause_edge;
    bit pause_done, corrupt_pause;
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
    bit read_case, read_increment_case, sampled_read, sampled_write;
    integer reads, scan_reads, scan_combined, excluded_reads;
    logic [19:0] read_rows;
    bit corrupt_row_case, row_fault_ready;
    logic [14:0] row_fault_address;
    assign init_done=memory_init_done && !setup;
    n2m_dma dut (.*);
    // Stop at the accepting carry, before registered stopped becomes visible.
    n2m_cpu_stop_policy clock_stop_policy (.selected_active(1'b0),
        .enabled_pending(|(test_ie[4:0] & test_if)), .execute(stop_execute),
        .action(clock_stop_action), .padding(), .divider_reset());
    n2m_timebase timebase (.clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset),
        .pause_request(!run_enable || cpu_stopped || (stop_execute && clock_stop_action==STOP_OSCILLATOR)), .paused(paused), .gb_tick(gb_tick));
    n2m_cpu cpu (.clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset),
        .gb_tick(gb_tick), .profile_id(PROFILE_DIRECT_ID), .epoch(32'd1), .dot_before(dot_before),
        .ie(test_ie), .iflags(test_if), .buttons(8'd0), .read_data(read_data), .response_valid(response_valid),
        .joyp_selected_active(1'b0), .wake_request(test_wake), .request_valid(request_valid),
        .address(bus_plan.address), .write_data(bus_plan.write_data), .write_enable(bus_plan.write_enable),
        .access_kind(bus_plan.access_kind), .bus_commit(bus_commit), .address_effect(address_effect),
        .address_effect_resolved(address_effect_resolved), .address_effect_sample(address_effect_sample),
        .address_effect_phase(cpu_phase), .irq_ack(), .halted(cpu_halted), .stopped(cpu_stopped),
        .locked(), .initialized(cpu_initialized), .fault(cpu_fault), .ime_observe(), .ime_delay_observe(),
        .stop_execute(stop_execute), .divider_reset_request(), .instruction_complete(), .retirement_valid(), .retirement());
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
                        if(dot_before+1!=wake_dot+4) $fatal(1,"DMA_POWER_WAKE_DOT expected=%0d actual=%0d",wake_dot+4,dot_before+1);
                        resumed_dma=1;
                    end
                    expected_oam[selected_offset]=power_case && selected_offset==1 ? 8'h27 : sprite_byte(selected_offset);
                    dma_count=dma_count+1;
                end
                sampled_read=0; sampled_write=0;
                if(read_case && bus_commit && bus_plan.address[15:8]==8'hfe) begin
                    if(bus_plan.write_enable || bus_plan.address!==16'('hfe00+(read_increment_case ? reads : 0)))
                        $fatal(1,"DMA_COMPOSITION_READ_ADDRESS index=%0d actual=%04x",reads,bus_plan.address);
                    reads=reads+1; sampled_read=1;
                end
                if(address_effect_sample && address_effect.valid && address_effect.write_effect &&
                    address_effect.address[15:8]==8'hfe) begin
                    if(address_effect.address!==16'('hfe00+effects)) $fatal(1,"DMA_COMPOSITION_IDU");
                    effects=effects+1; sampled_write=1;
                end
                // The original opcode fixes whether this accepted read has an IDU write.
                if(sampled_read && sampled_write!=read_increment_case)
                    $fatal(1,"DMA_COMPOSITION_READ_IDU expected=%0d actual=%0d",read_increment_case,sampled_write);
                if(ppu_oam_phase==1 && (sampled_read || sampled_write)) begin
                    corrupt_row(int'(ppu_scan_index)/2,sampled_read,sampled_write);
                    if(sampled_read) begin
                        read_rows[int'(ppu_scan_index)/2]=1;
                        if(corrupt_row_case && !row_fault_ready && ppu_scan_index/2>=4 && ppu_scan_index/2<=18) begin
                            row_fault_address=15'(8*(int'(ppu_scan_index)/2)+4);
                            row_fault_ready=1;
                        end
                        if(sampled_write) scan_combined=scan_combined+1;
                        else scan_reads=scan_reads+1;
                    end
                end else if(sampled_read) excluded_reads=excluded_reads+1;
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
        halt_case=$test$plusargs("HALT_CASE"); stop_case=$test$plusargs("STOP_CASE");
        power_case=halt_case || stop_case; test_ie=0; test_if=0; test_wake=0; sleep_dot=0;
        corrupt_pause=$test$plusargs("CORRUPT_PAUSE");
        pause_phase=-1; pause_count=0; pause_dot=0; pause_sample_phase=0; pause_done=0;
        if($value$plusargs("PAUSE_PHASE=%d",pause_phase) && (pause_phase<0 || pause_phase>3))
            $fatal(1,"DMA_PAUSE_PHASE_ARGUMENT");
        read_increment_case=$test$plusargs("READ_INCREMENT");
        read_case=$test$plusargs("READ_CASE") || read_increment_case;
        reads=0; scan_reads=0; scan_combined=0; excluded_reads=0; read_rows=0;
        sampled_read=0; sampled_write=0;
        corrupt_row_case=$test$plusargs("CORRUPT_ROW"); row_fault_ready=0; row_fault_address=0;
        seen_wake=0; resumed_dma=0; wake_dot=0; held_count=0;
        trace=$fopen("dma-composition.csv","w");
        $dumpfile("dma-composition.vcd");
        $dumpvars(0,clk_sys,gb_tick,cpu_phase,bus_commit,bus_plan,address_effect,address_effect_sample,
            dma_active,access_read,access_write,access_store,access_address,access_wdata,
            ppu_oam_phase,ppu_scan_index,ppu_oam_pair,ppu_oam_data,ppu_oam_valid,
            fault,cpu_fault,ppu_fault,read_data,response_valid,dma_count,effects,expected_held,
            reset_sys,core_reset,memory_init_done,cpu_initialized,setup,run_enable,paused,request_valid,
            cpu_halted,test_ie,test_if,wake_dot,seen_wake,resumed_dma,dut.invalid_observation,
            dut.engine.write_valid,peripheral_commit,dut.service.dma_held_pair,
            reads,scan_reads,scan_combined,excluded_reads,read_rows,sampled_read,sampled_write,row_fault_ready,row_fault_address,
            cpu_stopped,test_wake,sleep_dot,stop_execute,clock_stop_action,
            pause_phase,pause_done,pause_dot,pause_count,pause_sample_phase);
        repeat(3) @(negedge clk_sys); reset_sys=0;
        core_reset=1; repeat(2) @(negedge clk_sys); core_reset=0;
        wait(memory_init_done); repeat(3) @(negedge clk_sys);
        for(index=0;index<160;index=index+1) begin
            load_byte(STORE_WRAM,index,power_case && index==1 ? 8'h27 : sprite_byte(index));
            load_byte(STORE_OAM,index,sprite_byte(index)); expected_oam[index]=sprite_byte(index);
        end
        for(index=0;index<128;index=index+1) program_bytes[index]=0;
        // Original HRAM program: LCD on, HL=FE00, DMA C000,64 IDU increments.
        program_bytes[0]='h3e; program_bytes[1]='h93; program_bytes[2]='he0; program_bytes[3]='h40;
        program_bytes[4]='h21; program_bytes[5]='h00; program_bytes[6]='hfe;
        program_bytes[7]='h3e; program_bytes[8]='hc0; program_bytes[9]='he0; program_bytes[10]='h46;
        program_bytes[11]='h06; program_bytes[12]='h40; program_bytes[13]='h23;
        program_bytes[14]='h05; program_bytes[15]='h20; program_bytes[16]='hfc; program_bytes[17]='h76;
        // Both opcodes have a two-M-cycle body; DEC B/JR controls64 iterations.
        if(read_case) program_bytes[13]=read_increment_case ? 8'h2a : 8'h7e;
        if(power_case) begin
            // LDH retirement spans M1; immediate HALT entry M2 writes even byte0.
            if(stop_case) begin
                program_bytes[11]='h10; program_bytes[12]=0; program_bytes[13]='h18; program_bytes[14]='hfe;
            end else begin
                program_bytes[11]='h76; program_bytes[12]='h18; program_bytes[13]='hfe;
            end
        end
        for(index=0;index<127;index=index+1) load_byte(STORE_HRAM,index,program_bytes[index]);
        for(index=0;index<3;index=index+1) begin
            @(negedge clk_sys); host_address=32'('h100+index);
            case(index) 0: host_data='hc3; 1: host_data='h80; default: host_data='hff; endcase
            host_write=1; @(negedge clk_sys); host_write=0;
        end
        if(!cpu_initialized) $fatal(1,"DMA_COMPOSITION_CORE_INITIALIZE");
        @(negedge clk_sys); setup=0; observe=1; run_enable=1;
        if(pause_phase>=0) begin
            // Sample after CPU phase NBA updates; age changes on the same T4.
            @(negedge clk_sys);
            while(!(seen_start && dma_age>=10 && cpu_phase==2'(pause_phase))) @(negedge clk_sys);
            pause_dot=dot_before; pause_sample_phase=cpu_phase; run_enable=0;
            if(pause_sample_phase!==2'(pause_phase)) $fatal(1,"DMA_PAUSE_REQUEST_PHASE");
            wait(paused); @(negedge clk_sys);
            if(dot_before!=pause_dot+1 || cpu_phase!=pause_sample_phase+2'd1)
                $fatal(1,"DMA_PAUSE_ACCEPTING_DOT phase=%0d before=%0d after=%0d",pause_phase,pause_dot,dot_before);
            pause_dot=dot_before; pause_sample_phase=cpu_phase; pause_count=dma_count;
            // Accepted post-A writes finish while emulated time is paused.
            for(pause_edge=0;pause_edge<200;pause_edge=pause_edge+1) begin
                @(negedge clk_sys);
                if(corrupt_pause && pause_edge==99) force dut.access_write=1'b1;
                if(pause_edge>=47 && (access_write || peripheral_commit || dut.engine.write_valid))
                    $fatal(1,"DMA_PAUSE_SERVICE_DRAIN");
                if(gb_tick || dot_before!=pause_dot || cpu_phase!=pause_sample_phase || dma_count!=pause_count)
                    $fatal(1,"DMA_PAUSE_HOLD phase=%0d",pause_phase);
            end
            run_enable=1; pause_done=1;
        end
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
        if(corrupt_row_case) begin
            wait(row_fault_ready); @(negedge clk_sys);
            if(!access_write || access_store!=STORE_OAM || access_address!==row_fault_address || access_wdata!==8'h10)
                $fatal(1,"DMA_ROW_FAULT_PRECONDITION address=%0d actual=%0d data=%02x",row_fault_address,access_address,access_wdata);
            force dut.access_wdata=8'h00;
        end
        if(corrupt_byte) begin
            wait(seen_start && access_write && access_store==STORE_OAM && access_address==5);
            @(negedge clk_sys); force dut.access_wdata=8'h00;
        end
        wait(stop_case ? cpu_stopped : cpu_halted);
        if(power_case) begin
            @(negedge clk_sys); held_count=dma_count;
            if(held_count!=1 || !dma_active || expected_held!==16'h0810 || dut.service.dma_held_pair!==16'h0810)
                $fatal(1,"DMA_POWER_EVEN_PAIR count=%0d pair=%04x",held_count,expected_held);
            sleep_dot=dot_before;
            repeat(1000) begin
                @(negedge clk_sys);
                if(stop_case && dot_before!=sleep_dot) $fatal(1,"DMA_STOP_DOT_HOLD");
                if(dut.service.dma_held_pair!==16'h0810) $fatal(1,"DMA_POWER_ACTUAL_PAIR");
            end
            if(dma_count!=held_count || !dma_active) $fatal(1,"DMA_POWER_PROGRESS");
            if(stop_case) begin
                // Upstream supplies an already-qualified wake on stopped phase0/off-tick.
                if(gb_tick || cpu_phase!=0) $fatal(1,"DMA_STOP_WAKE_BOUNDARY");
                test_wake=1; @(negedge clk_sys); test_wake=0;
                wait(!cpu_stopped);
            end else begin
                test_ie=1; test_if=1; wait(!cpu_halted);
            end
            wake_dot=dot_before; seen_wake=1;
            wait(dma_count==160);
            if(!resumed_dma) $fatal(1,"DMA_POWER_NO_RESUME");
        end
        @(negedge clk_sys); run_enable=0;
        repeat(60) @(negedge clk_sys);
        if(dma_count!=160 || effects!=((power_case || (read_case && !read_increment_case)) ? 0 : 64) || checks==0) $fatal(1,"DMA_COMPOSITION_COUNTS dma=%0d effects=%0d ppu=%0d",dma_count,effects,checks);
        if(pause_phase>=0 && !pause_done) $fatal(1,"DMA_PAUSE_NOT_EXERCISED");
        if(read_case && (reads!=64 || excluded_reads==0 ||
            (read_increment_case ? scan_combined==0 : scan_reads==0)))
            $fatal(1,"DMA_COMPOSITION_READ_COUNTS reads=%0d scan=%0d combined=%0d excluded=%0d",
                reads,scan_reads,scan_combined,excluded_reads);
        observe=0; setup=1;
        for(index=0;index<160;index=index+1) begin
            @(negedge clk_sys); setup_read=1; setup_store=STORE_OAM; setup_address=15'(index);
            @(negedge clk_sys);
            if(!access_valid || access_rdata!==expected_oam[index])
                $fatal(1,"DMA_COMPOSITION_READBACK offset=%0d expected=%02x actual=%02x",index,expected_oam[index],access_rdata);
        end
        $fclose(trace);
        $display("PASS DMA composition bytes=160 idu=%0d halt=%0d stop=%0d ppu=%0d reads=%0d scan=%0d combined=%0d excluded=%0d rows=%05x pause=%0d",
            effects,halt_case,stop_case,checks,reads,scan_reads,scan_combined,excluded_reads,read_rows,pause_phase); $finish;
    end
    initial begin #10000000; $fatal(1,"DMA_COMPOSITION_WATCHDOG"); end
endmodule
