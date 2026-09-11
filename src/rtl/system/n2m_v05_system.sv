`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// Required owners for the original v0.5 program; unused destinations reject service.
module n2m_v05_system #(
    parameter integer UART_BAUD = 115200,
    parameter logic [127:0] BUILD_ID = 128'h88000000000000000000000000000001
) (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic clk_pix,
    input var logic reset_pix,
    input var logic uart_rx,
    output logic uart_tx,
    input var logic physical_commit,
    input var logic [7:0] physical_buttons,
    output logic [7:0] effective_buttons,
    output logic [7:0] input_source_observe,
    output logic [3:0] red, green, blue,
    output logic hsync_n, vsync_n,
    output logic [63:0] display_sequence,
    output logic [31:0] display_epoch,
    output logic gb_tick, paused, core_reset,
    output logic [31:0] epoch,
    output logic [63:0] dot_count,
    output logic retirement_valid,
    output n2m_interfaces_pkg::retirement_t retirement,
    output logic bus_commit, write_enable,
    output logic [15:0] address,
    output logic [7:0] write_data, read_data,
    output logic [4:0] irq_ack,
    output logic source_valid, source_start, source_abort, source_display_eligible,
    output logic [1:0] source_shade,
    output logic [7:0] source_x, source_y,
    output logic [31:0] source_epoch,
    output logic [63:0] source_dot,
    output logic fault
);
    // Quartus 25.1 misresolves package constants inside instance connections.
    localparam n2m_memory_pkg::memory_destination_t IRQ_DESTINATION = n2m_memory_pkg::MEMORY_IRQ;
    localparam n2m_memory_pkg::memory_destination_t PPU_DESTINATION = n2m_memory_pkg::MEMORY_PPU;
    localparam n2m_memory_pkg::memory_destination_t JOYP_DESTINATION = n2m_memory_pkg::MEMORY_JOYP;
    localparam n2m_memory_pkg::memory_destination_t TIMER_DESTINATION = n2m_memory_pkg::MEMORY_TIMER;
    localparam n2m_memory_pkg::memory_destination_t SERIAL_DESTINATION = n2m_memory_pkg::MEMORY_SERIAL;
    localparam n2m_memory_pkg::memory_destination_t APU_DESTINATION = n2m_memory_pkg::MEMORY_APU;
    localparam n2m_memory_pkg::memory_destination_t WAVE_DESTINATION = n2m_memory_pkg::MEMORY_WAVE;
    n2m_timer_pkg::timer_request_t timer_request;
    logic divider_reset_request;
    logic [7:0] timer_rdata;
    logic pause_request, core_initialized, instruction_complete, cpu_stopped;
    logic [7:0] buttons, profile, endpoint_state;
    logic [63:0] retirement_count;
    logic image_valid, rom_write, rom_read, rom_read_valid;
    logic [14:0] rom_address;
    logic [7:0] rom_write_data, rom_read_data;
    logic snapshot_request, frame_read;
    logic snapshot_ready, snapshot_done, snapshot_ok, snapshot_valid, frame_valid;
    n2m_interfaces_pkg::snapshot_t snapshot_metadata;
    logic [7:0] frame_data, joyp_rdata;
    n2m_input_pkg::input_update_t effective_update;
    logic joyp_selected_active, joyp_event;
    logic core_active_reset, wake_pending, wake_request, emulated_tick;
    logic [12:0] frame_address;
    logic request_valid, response_valid, cpu_initialized, cpu_fault, memory_fault, ppu_fault;
    logic memory_initialized, storage_valid;
    n2m_memory_pkg::memory_store_t raw_store;
    n2m_memory_pkg::memory_destination_t destination;
    logic [14:0] raw_offset;
    logic [7:0] raw_wdata, storage_rdata;
    logic owner_prepare, owner_commit, owner_write;
    logic [15:0] owner_address;
    logic [7:0] owner_wdata, owner_rdata;
    logic owner_valid, owner_service;
    logic raw_read, raw_write, dma_active, cpu_halted;
    logic dma_vram_allow, dma_oam_allow, oam_cpu_late_write, oam_late_future;
    n2m_memory_pkg::memory_oam_request_t oam_request;
    n2m_memory_pkg::memory_oam_response_t oam_response;
    n2m_cpu_pkg::cpu_bus_plan_t bus_plan;
    n2m_cpu_pkg::cpu_address_effect_t address_effect;
    logic address_effect_resolved, address_effect_sample;
    logic [1:0] cpu_phase;
    logic [5:0] oam_scan_index;
    logic raw_vram_read, raw_vram_valid, raw_oam_read, raw_oam_valid;
    logic [12:0] raw_vram_address;
    logic [7:0] raw_vram_data;
    logic [6:0] raw_oam_pair;
    logic [15:0] raw_oam_data;
    logic [7:0] ppu_rdata, irq_rdata, serial_rdata, apu_rdata;
    logic apu_valid, apu_audio_io, wave_read, wave_write;
    logic [3:0] wave_address;
    logic [7:0] wave_wdata, wave_rdata;
    logic wave_valid;
    logic ppu_selected, irq_selected;
    logic [7:0] ie_stored, ie_observe;
    // Committed DMG I/O observations published to the host register map.
    logic [7:0] io_lcdc, io_stat, io_ly, io_lyc, io_scy, io_scx, io_wy, io_wx;
    logic [7:0] io_bgp, io_obp0, io_obp1, io_div, io_tima, io_tma, io_tac;
    logic [4:0] if_stored, if_observe;
    logic vram_request, vram_valid;
    logic [12:0] vram_address;
    logic [7:0] vram_data;
    logic [6:0] oam_pair_address;
    logic [1:0] oam_phase;
    logic [15:0] oam_data;
    logic oam_valid, vram_cpu_allow, vram_cpu_read_allow, oam_cpu_allow, oam_cpu_read_allow, stat_condition, vblank_condition;
    logic blank_assert;
    logic observe_valid, observe_complete, observe_abort;
    logic [14:0] observe_index;
    logic [1:0] observe_shade;
    logic [31:0] observe_epoch;
    logic [63:0] observe_sequence, observe_dot;
    assign core_initialized = memory_initialized && cpu_initialized;
    assign fault = cpu_fault || memory_fault || ppu_fault;

    n2m_uart #(.CLOCK_HZ(25000000), .BAUD(UART_BAUD)) u_uart (
        .clk_sys, .reset_sys, .uart_rx, .uart_tx,
        .build_id(BUILD_ID), .gb_tick, .paused,
        .io_lcdc, .io_stat, .io_ly, .io_lyc, .io_scy, .io_scx, .io_wy, .io_wx,
        .io_bgp, .io_obp0, .io_obp1, .io_div, .io_tima, .io_tma, .io_tac,
        .io_if({3'b0, if_stored}), .io_ie(ie_stored),
        .core_initialized, .instruction_complete, .retirement_valid, .cpu_stopped,
        .physical_commit, .physical_buttons, .effective_buttons, .effective_update,
        .input_source_observe,
        .pause_request, .core_reset, .buttons, .epoch, .dot_count, .retirement_count,
        .profile, .image_valid, .endpoint_state, .rom_write, .rom_read, .rom_address,
        .rom_write_data, .rom_read_data, .rom_read_valid,
        .snapshot_request, .snapshot_ready, .snapshot_done,
        .snapshot_ok, .snapshot_valid, .snapshot_metadata,
        .frame_read, .frame_address, .frame_data, .frame_valid
    );
    n2m_timebase u_timebase (.clk_sys, .reset_sys, .core_reset, .pause_request,
        .gb_tick(emulated_tick), .paused);
    // STOP withholds emulated ticks from every owner, so no dot elapses while
    // the CPU sleeps. The completing T4 still ticks: stopped is registered, so
    // that bookkeeping edge lands the M-cycle phase on zero for the wake.
    assign gb_tick = emulated_tick && !cpu_stopped;
    n2m_cpu u_cpu (
        .clk_sys, .reset_sys, .core_reset, .gb_tick, .profile_id(profile), .epoch,
        .dot_before(dot_count), .ie(ie_observe), .iflags(if_observe),
        .buttons(effective_buttons),
        .read_data, .response_valid, .joyp_selected_active, .wake_request,
        .request_valid, .address, .write_data, .write_enable, .bus_commit, .irq_ack,
        .access_kind(bus_plan.access_kind), .address_effect, .address_effect_resolved,
        .address_effect_sample, .address_effect_phase(cpu_phase), .halted(cpu_halted), .stopped(cpu_stopped),
        .locked(), .initialized(cpu_initialized), .fault(cpu_fault), .ime_observe(),
        .ime_delay_observe(), .stop_execute(), .divider_reset_request,
        .instruction_complete, .retirement_valid, .retirement
    );
    assign bus_plan.address = address;
    assign bus_plan.write_data = write_data;
    assign bus_plan.write_enable = write_enable;
    assign dma_vram_allow = bus_plan.write_enable ? vram_cpu_allow : vram_cpu_read_allow;
    assign dma_oam_allow = bus_plan.write_enable ? oam_cpu_allow : oam_cpu_read_allow;
    // CPU faults are registered. Stop subsequent work without feeding a missing
    // response back into the arbiter on the edge which discovers that fault.
    n2m_dma u_dma (
        .clk_sys, .reset_sys, .core_reset,
        .init_done(memory_initialized && image_valid && !cpu_fault),
        .gb_tick(gb_tick && !cpu_fault), .cpu_phase, .cpu_halted, .cpu_stopped,
        .request_valid(request_valid && !cpu_fault), .bus_plan,
        .bus_commit(bus_commit && !cpu_fault), .address_effect,
        .address_effect_resolved(address_effect_resolved && !cpu_fault),
        .address_effect_sample(address_effect_sample && !cpu_fault),
        .read_data, .response_valid, .fault(memory_fault),
        .peripheral_prepare(owner_prepare), .peripheral_commit(owner_commit),
        .peripheral_destination(destination), .peripheral_address(owner_address),
        .peripheral_write(owner_write), .peripheral_wdata(owner_wdata),
        .peripheral_rdata(owner_rdata), .peripheral_valid(owner_valid),
        .peripheral_available(owner_service), .vram_cpu_allow(dma_vram_allow),
        .oam_cpu_allow(dma_oam_allow), .oam_cpu_late_write, .oam_late_future,
        .ppu_vram_request(vram_request), .ppu_vram_address(vram_address),
        .ppu_vram_data(vram_data), .ppu_vram_valid(vram_valid),
        .ppu_oam_phase(oam_phase), .ppu_scan_index(oam_scan_index),
        .ppu_oam_pair(oam_pair_address), .ppu_oam_data(oam_data), .ppu_oam_valid(oam_valid),
        .dma_active, .access_read(raw_read), .access_write(raw_write),
        .access_store(raw_store), .access_address(raw_offset), .access_wdata(raw_wdata),
        .access_rdata(storage_rdata), .access_valid(storage_valid), .oam_request, .oam_response,
        .raw_vram_read, .raw_vram_address, .raw_vram_data, .raw_vram_valid,
        .raw_oam_read, .raw_oam_pair, .raw_oam_data, .raw_oam_valid
    );
    always_comb begin
        owner_service = 1;
        owner_valid = 1;
        owner_rdata = 0;
        case (destination)
            n2m_memory_pkg::MEMORY_TIMER: owner_rdata = timer_rdata;
            n2m_memory_pkg::MEMORY_PPU: owner_rdata = ppu_rdata;
            n2m_memory_pkg::MEMORY_IRQ: owner_rdata = irq_rdata;
            n2m_memory_pkg::MEMORY_JOYP: begin
                owner_rdata = joyp_rdata;
                owner_service = 1'b1;
                owner_valid = 1'b1;
            end
            n2m_memory_pkg::MEMORY_SERIAL: owner_rdata = serial_rdata;
            // One gateway answers the audio registers and wave RAM. Wave reads
            // return a registered store byte, so they carry their own validity.
            n2m_memory_pkg::MEMORY_APU, n2m_memory_pkg::MEMORY_WAVE: begin
                owner_rdata = apu_rdata;
                owner_valid = apu_valid;
            end
            default: begin owner_service = 0; owner_valid = 0; end
        endcase
    end
    assign apu_audio_io = destination == APU_DESTINATION || destination == WAVE_DESTINATION;
    n2m_memory_stores u_stores (.oam_request, .oam_response,
        .clk_sys, .reset_sys, .core_reset, .init_done(memory_initialized),
        .access_read(raw_read), .access_write(raw_write), .access_store(raw_store),
        .access_address(raw_offset), .access_wdata(raw_wdata),
        .access_rdata(storage_rdata), .access_valid(storage_valid),
        .host_read(rom_read), .host_write(rom_write), .host_offset({17'd0,rom_address}),
        .host_wdata(rom_write_data), .host_rdata(rom_read_data), .host_valid(rom_read_valid),
        .ppu_vram_read(raw_vram_read), .ppu_vram_address(raw_vram_address),
        .ppu_vram_rdata(raw_vram_data), .ppu_vram_valid(raw_vram_valid),
        .ppu_oam_read(raw_oam_read), .ppu_oam_pair(raw_oam_pair),
        .ppu_oam_rdata(raw_oam_data), .ppu_oam_valid(raw_oam_valid),
        .wave_read, .wave_write, .wave_address, .wave_wdata, .wave_rdata, .wave_valid
    );
    n2m_timer u_timer (
        .clk_sys, .reset_sys, .core_reset, .gb_tick, .divider_reset_request,
        .io_commit(owner_commit && destination == TIMER_DESTINATION), .io_write(owner_write),
        .io_address(owner_address), .io_wdata(owner_wdata),
        .io_selected(), .io_rdata(timer_rdata), .interrupt_request(timer_request),
        .div_observe(io_div), .tima_observe(io_tima), .tma_observe(io_tma), .tac_observe(io_tac)
    );
    n2m_interrupts u_interrupts (
        .clk_sys, .reset_sys, .core_reset, .gb_tick,
        .io_commit(owner_commit && destination == IRQ_DESTINATION), .io_write(owner_write),
        .io_address(owner_address), .io_wdata(owner_wdata),
        .source_level({2'd0,timer_request.request,stat_condition,vblank_condition}), .source_event({joyp_event,4'd0}),
        .irq_ack, .io_selected(irq_selected), .io_rdata(irq_rdata),
        .ie_stored, .if_stored, .ie_observe, .if_observe
    );
    n2m_ppu u_ppu (
        .clk_sys, .reset_sys, .core_reset, .gb_tick, .epoch, .dot_before(dot_count),
        .io_commit(owner_commit && destination == PPU_DESTINATION), .io_write(owner_write),
        .io_address(owner_address), .io_wdata(owner_wdata), .io_selected(ppu_selected),
        .io_rdata(ppu_rdata), .vram_request, .vram_address, .vram_data, .vram_valid,
        .oam_pair_address, .oam_phase, .oam_scan_index, .oam_data, .oam_valid,
        .dma_active, .vram_cpu_allow, .oam_cpu_allow, .vram_cpu_read_allow, .oam_cpu_read_allow, .oam_late_future, .oam_cpu_late_write, .stat_condition,
        .vblank_condition, .stat_rise(), .vblank_rise(), .fault(ppu_fault),
        .source_valid, .source_start, .source_shade, .source_x, .source_y,
        .source_epoch, .source_dot, .source_abort, .blank_assert, .source_display_eligible,
        .lcdc_observe(io_lcdc), .stat_observe(io_stat), .ly_observe(io_ly), .lyc_observe(io_lyc),
        .scy_observe(io_scy), .scx_observe(io_scx), .wy_observe(io_wy), .wx_observe(io_wx),
        .bgp_observe(io_bgp), .obp0_observe(io_obp0), .obp1_observe(io_obp1)
    );
    n2m_serial u_serial (
        .clk_sys, .reset_sys, .core_reset, .gb_tick,
        .io_commit(owner_commit && destination == SERIAL_DESTINATION), .io_write(owner_write),
        .io_address(owner_address), .io_wdata(owner_wdata),
        .io_selected(), .io_rdata(serial_rdata)
    );
    n2m_apu u_apu (
        .clk_sys, .reset_sys, .core_reset, .gb_tick,
        .io_prepare(owner_prepare && apu_audio_io),
        .io_commit(owner_commit && apu_audio_io), .io_write(owner_write),
        .io_address(owner_address), .io_wdata(owner_wdata),
        .io_selected(), .io_rdata(apu_rdata), .io_valid(apu_valid),
        .wave_read, .wave_write, .wave_address, .wave_wdata, .wave_rdata, .wave_valid
    );
    n2m_joypad u_joypad (
        .clk_sys, .reset_sys, .core_reset, .gb_tick,
        .input_commit(effective_update.valid), .input_buttons(effective_update.buttons),
        .io_commit(owner_commit && destination == JOYP_DESTINATION), .io_write(owner_write),
        .io_address(owner_address), .io_wdata(owner_wdata), .io_selected(),
        .io_rdata(joyp_rdata), .buttons_observe(),
        .selected_active(joyp_selected_active), .request_event(joyp_event)
    );
    n2m_frame_bridge u_bridge (
        .clk_sys, .reset_sys, .core_reset, .clk_pix, .reset_pix,
        .source_valid, .source_start, .source_abort, .blank_assert,
        .source_display_eligible, .source_shade, .source_epoch, .source_dot,
        .observe_valid, .observe_complete, .observe_abort, .observe_index,
        .observe_shade, .observe_epoch, .observe_sequence, .observe_dot,
        .discard_count(), .repeat_count(), .display_valid(), .display_sequence,
        .display_epoch, .video_x(), .video_y(), .video_valid(), .video_active(),
        .video_image(), .red, .green, .blue, .hsync_n, .vsync_n
    );
    n2m_frame_snapshot u_snapshot (
        .clk_sys, .reset_sys, .core_reset, .observe_valid, .observe_complete,
        .observe_abort, .observe_index, .observe_shade, .observe_epoch,
        .observe_sequence, .observe_dot, .snapshot_request, .snapshot_ready,
        .snapshot_done, .snapshot_ok, .snapshot_valid, .snapshot_metadata,
        .frame_read, .frame_address, .frame_valid, .frame_data
    );
    // This composition is the CPU's power owner. It retains one joypad
    // selected-line event raised while the CPU sleeps and presents it on the
    // boundary the CPU accepts: phase 0 before T1, with no tick on that edge.
    // Events outside STOP are not retained; only a fall during sleep wakes.
    assign core_active_reset = reset_sys || core_reset;
    assign wake_request = wake_pending && cpu_stopped && cpu_phase == 2'd0 && !gb_tick;
    `DFF_ARST_VAL(wake_pending, (wake_pending || (joyp_event && cpu_stopped)) && !wake_request,
        clk_sys, core_active_reset, 1'b0)
    `N2M_ASSERT(V05_STOP_WAKE_BOUNDARY, clk_sys, reset_sys || core_reset,
        !wake_request || (cpu_stopped && cpu_phase == 2'd0 && !gb_tick))
    `N2M_ASSERT_NEVER(V05_WAKE_WITHOUT_STOP, clk_sys, reset_sys || core_reset,
        wake_pending && !cpu_stopped)
    // Every destination reaching this composition has an owner. A missing arm
    // would fault the CPU port instead of returning a DMG value.
    `N2M_ASSERT(V05_OWNER_SERVICE, clk_sys, reset_sys || core_reset,
        !owner_prepare || owner_service)
endmodule
