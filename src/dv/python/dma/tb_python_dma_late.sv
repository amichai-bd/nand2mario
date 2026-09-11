`timescale 1ns/1ps
`default_nettype none
module tb_python_dma_late;
    integer lane;
    n2m_memory_pkg::memory_oam_request_t oam_request;
    n2m_memory_pkg::memory_oam_response_t oam_response;
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
    n2m_cpu_pkg::cpu_stop_action_t clock_stop_action;
    logic [63:0] sleep_dot, pause_dot;
    logic [1:0] pause_sample_phase;
    integer pause_phase, pause_count, pause_edge;
    bit pause_done, corrupt_pause;
    n2m_cpu_pkg::cpu_bus_plan_t bus_plan;
    n2m_cpu_pkg::cpu_address_effect_t address_effect;
    logic address_effect_resolved, address_effect_sample;
    logic [7:0] read_data;
    logic response_valid, fault, cpu_fault, ppu_fault;
    logic peripheral_prepare, peripheral_commit, peripheral_write;
    n2m_memory_pkg::memory_destination_t peripheral_destination;
    logic [15:0] peripheral_address;
    logic [7:0] peripheral_wdata, peripheral_rdata;
    logic peripheral_valid, peripheral_available, ppu_selected;
    logic ppu_oam_write_allow, ppu_oam_read_allow;
    logic ppu_vram_write_allow, ppu_vram_read_allow;
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
    logic retirement_valid, record_event, bus_event;
    n2m_interfaces_pkg::retirement_t retirement;
    logic [383:0] record_sample;
    logic [88:0] bus_sample;
    logic inspection_enable;
    n2m_memory_pkg::memory_oam_request_t inspection_request, store_request;
    logic [16:0] inspection_response;
    logic [7:0] lcdc_observe;
    logic [5:0] service_slot;
    logic capture_scan;
    assign init_done=memory_init_done && !setup;
    assign vram_cpu_allow = bus_plan.write_enable ? ppu_vram_write_allow : ppu_vram_read_allow;
    assign oam_cpu_allow = bus_plan.write_enable ? ppu_oam_write_allow : ppu_oam_read_allow;
    logic oam_cpu_late_write, oam_late_future;
    n2m_dma dut (.*);
    // Stop at the accepting carry, before registered stopped becomes visible.
    n2m_cpu_stop_policy clock_stop_policy (.selected_active(1'b0),
        .enabled_pending(|(test_ie[4:0] & test_if)), .execute(stop_execute),
        .action(clock_stop_action), .padding(), .divider_reset());
    n2m_timebase timebase (.clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset),
        .pause_request(!run_enable || cpu_stopped || (stop_execute && clock_stop_action==n2m_cpu_pkg::STOP_OSCILLATOR)), .paused(paused), .gb_tick(gb_tick));
    n2m_cpu cpu (.clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset),
        .gb_tick(gb_tick), .profile_id(n2m_interfaces_pkg::PROFILE_DIRECT_ID), .epoch(32'd2), .dot_before(dot_before),
        .ie(test_ie), .iflags(test_if), .buttons(8'd0), .read_data(read_data), .response_valid(response_valid),
        .joyp_selected_active(1'b0), .wake_request(test_wake), .request_valid(request_valid),
        .address(bus_plan.address), .write_data(bus_plan.write_data), .write_enable(bus_plan.write_enable),
        .access_kind(bus_plan.access_kind), .bus_commit(bus_commit), .address_effect(address_effect),
        .address_effect_resolved(address_effect_resolved), .address_effect_sample(address_effect_sample),
        .address_effect_phase(cpu_phase), .irq_ack(), .halted(cpu_halted), .stopped(cpu_stopped),
        .locked(), .initialized(cpu_initialized), .fault(cpu_fault), .ime_observe(), .ime_delay_observe(),
        .stop_execute(stop_execute), .divider_reset_request(), .instruction_complete(), .retirement_valid(retirement_valid), .retirement(retirement));
    n2m_ppu ppu (.clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset),
        .gb_tick(gb_tick), .epoch(32'd2), .dot_before(dot_before),
        .io_commit(peripheral_commit), .io_write(peripheral_write), .io_address(peripheral_address),
        .io_wdata(peripheral_wdata), .io_selected(ppu_selected), .io_rdata(peripheral_rdata),
        .vram_request(ppu_vram_request), .vram_address(ppu_vram_address),
        .vram_data(ppu_vram_data), .vram_valid(ppu_vram_valid), .oam_pair_address(ppu_oam_pair),
        .oam_phase(ppu_oam_phase), .oam_scan_index(ppu_scan_index), .oam_data(ppu_oam_data),
        .oam_valid(ppu_oam_valid), .dma_active(dma_active), .vram_cpu_allow(ppu_vram_write_allow),
        .oam_cpu_allow(ppu_oam_write_allow), .vram_cpu_read_allow(ppu_vram_read_allow), .oam_cpu_read_allow(ppu_oam_read_allow), .oam_late_future(oam_late_future), .oam_cpu_late_write(oam_cpu_late_write), .stat_condition(), .vblank_condition(), .stat_rise(),
        .vblank_rise(), .fault(ppu_fault), .source_valid(), .source_start(), .source_shade(),
        .source_x(), .source_y(), .source_epoch(), .source_dot(), .source_abort(),
        .blank_assert(), .source_display_eligible());
    assign peripheral_valid=ppu_selected;
    assign peripheral_available=ppu_selected;
    n2m_memory_stores stores (.oam_request(store_request), .oam_response, .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset),
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
    defparam stores.rom.SIM_INIT_FILE = "preload-rom.mif";
    assign store_request = inspection_enable ? inspection_request : oam_request;
    assign inspection_response = oam_response;
    assign lcdc_observe = ppu.lcdc;
    assign service_slot = dut.service.slot_q;
    assign capture_scan = ppu.objects.capture_scan;
    always #20 clk_sys=~clk_sys;
    always @(posedge clk_sys) begin
        if(reset_sys || core_reset) dot_before <= 0;
        else if(gb_tick) dot_before <= dot_before + 1;
        if(!reset_sys && bus_commit) begin
            bus_sample <= {64'(dot_before+1),bus_plan.address,bus_plan.write_enable,
                bus_plan.write_enable ? bus_plan.write_data : read_data};
            bus_event <= !bus_event;
        end
        if(inspection_enable && (!paused || !cpu_halted || lcdc_observe!=0
            || service_slot!=0 || inspection_request.write_enable!=0))
            $fatal(1,"DMA_INSPECTION_READ_ONLY");
        #1;
        if(!reset_sys && retirement_valid) begin
            record_sample <= retirement; record_event <= !record_event;
        end
    end
    initial begin
        clk_sys=0;reset_sys=1;core_reset=0;setup=0;setup_read=0;setup_write=0;
        setup_store=n2m_memory_pkg::STORE_OAM;setup_address=0;setup_data=0;
        host_write=0;host_address=0;host_data=0;
        run_enable=0;test_ie=0;test_if=0;test_wake=0;
        dot_before=0;record_event=0;bus_event=0;
        inspection_enable=0;inspection_request='0;
    end
endmodule
