`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// Bounded composition for the original smoke ROM, not a full board top.
module n2m_smoke_system (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic uart_rx,
    output logic uart_tx,
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
    import n2m_interfaces_pkg::*;
    import n2m_memory_pkg::*;
    logic pause_request, core_initialized, instruction_complete, cpu_stopped;
    logic [7:0] buttons, profile, endpoint_state;
    logic [63:0] retirement_count;
    logic image_valid, rom_write, rom_read, rom_read_valid;
    logic [14:0] rom_address;
    logic [7:0] rom_write_data, rom_read_data;
    logic snapshot_request, frame_read;
    logic [12:0] frame_address;
    logic request_valid, response_valid, cpu_initialized, cpu_fault, memory_fault, ppu_fault;
    logic memory_initialized, storage_read, storage_write;
    memory_store_t storage_store, raw_store;
    memory_destination_t destination;
    logic [14:0] storage_offset, raw_offset;
    logic [7:0] storage_wdata, storage_rdata;
    logic storage_valid, owner_prepare, owner_commit, owner_write;
    logic [15:0] owner_address;
    logic [7:0] owner_wdata, owner_rdata;
    logic owner_valid, owner_service;
    logic raw_read, raw_write, video_owner, video_allowed, video_read;
    logic video_pending;
    logic [15:0] video_address;
    logic [7:0] ppu_rdata, irq_rdata;
    logic ppu_selected, irq_selected;
    logic [7:0] ie_stored, ie_observe;
    logic [4:0] if_stored, if_observe;
    logic vram_request, vram_valid;
    logic [12:0] vram_address;
    logic [7:0] vram_data;
    logic [6:0] oam_pair_address;
    logic [1:0] oam_phase;
    logic [15:0] oam_data;
    logic oam_valid, vram_cpu_allow, oam_cpu_allow, stat_condition, vblank_condition;
    logic reset;
    assign reset = reset_sys || core_reset;
    assign core_initialized = memory_initialized && cpu_initialized;
    assign fault = cpu_fault || memory_fault || ppu_fault;

    n2m_uart #(.CLOCK_HZ(50000000), .BAUD(6250000)) u_uart (
        .clk_sys, .reset_sys, .uart_rx, .uart_tx,
        .build_id(128'h14000000000000000000000000000001), .gb_tick, .paused,
        .core_initialized, .instruction_complete, .retirement_valid, .cpu_stopped,
        .pause_request, .core_reset, .buttons, .epoch, .dot_count, .retirement_count,
        .profile, .image_valid, .endpoint_state, .rom_write, .rom_read, .rom_address,
        .rom_write_data, .rom_read_data, .rom_read_valid,
        .snapshot_request, .snapshot_ready(1'b0), .snapshot_done(1'b0),
        .snapshot_ok(1'b0), .snapshot_valid(1'b0), .snapshot_metadata('0),
        .frame_read, .frame_address, .frame_data(8'd0), .frame_valid(1'b0)
    );
    n2m_timebase u_timebase (.clk_sys, .reset_sys, .core_reset, .pause_request, .gb_tick, .paused);
    n2m_cpu u_cpu (
        .clk_sys, .reset_sys, .core_reset, .gb_tick, .profile_id(profile), .epoch,
        .dot_before(dot_count), .ie(ie_observe), .iflags(if_observe), .buttons,
        .read_data, .response_valid, .joyp_selected_active(1'b0), .wake_request(1'b0),
        .request_valid, .address, .write_data, .write_enable, .bus_commit, .irq_ack,
        .access_kind(), .address_effect(), .address_effect_resolved(),
        .address_effect_sample(), .address_effect_phase(), .halted(), .stopped(cpu_stopped),
        .locked(), .initialized(cpu_initialized), .fault(cpu_fault), .ime_observe(),
        .ime_delay_observe(), .stop_execute(), .divider_reset_request(),
        .instruction_complete, .retirement_valid, .retirement
    );
    n2m_memory_cpu_port u_cpu_port (
        .clk_sys, .reset_sys, .core_reset, .init_done(memory_initialized && image_valid),
        .request_valid, .address, .write_enable, .write_data, .bus_commit,
        .read_data, .response_valid, .contract_fault(memory_fault),
        .storage_read, .storage_write, .storage_store, .storage_offset,
        .storage_wdata, .storage_rdata, .storage_valid,
        .owner_prepare, .owner_commit, .owner_destination(destination),
        .owner_address, .owner_write, .owner_wdata, .owner_rdata, .owner_valid,
        .owner_service_available(owner_service)
    );
    // One raw A port: the public CPU address can select only one destination.
    // PPU permissions apply to CPU video accesses; its own B reads remain live.
    assign video_owner = destination == MEMORY_VRAM || destination == MEMORY_OAM;
    assign video_allowed = destination == MEMORY_VRAM ? vram_cpu_allow : oam_cpu_allow;
    assign video_read = owner_prepare && video_owner && video_allowed && !owner_write;
    assign raw_read = storage_read || video_read;
    assign raw_write = storage_write || (owner_commit && video_owner && video_allowed && owner_write);
    assign raw_store = video_owner ? (destination == MEMORY_VRAM ? STORE_VRAM : STORE_OAM) : storage_store;
    assign raw_offset = video_owner ? (destination == MEMORY_VRAM ? {2'd0,address[12:0]} : {7'd0,address[7:0]}) : storage_offset;
    `DFF_ARST_VAL(video_pending, video_read, clk_sys, reset, 1'b0)
    `DFF_EN(video_address, address, clk_sys, video_read)
    always_comb begin
        owner_service = 1;
        owner_valid = 1;
        owner_rdata = 0;
        case (destination)
            MEMORY_VRAM, MEMORY_OAM: begin
                owner_rdata = video_allowed ? storage_rdata : 8'hff;
                owner_valid = !video_allowed || (video_pending && video_address == address && storage_valid);
            end
            MEMORY_PPU: owner_rdata = ppu_rdata;
            MEMORY_IRQ: owner_rdata = irq_rdata;
            default: begin owner_service = 0; owner_valid = 0; end
        endcase
    end
    n2m_memory_stores u_stores (
        .clk_sys, .reset_sys, .core_reset, .init_done(memory_initialized),
        .access_read(raw_read), .access_write(raw_write), .access_store(raw_store),
        .access_address(raw_offset), .access_wdata(write_data),
        .access_rdata(storage_rdata), .access_valid(storage_valid),
        .host_read(rom_read), .host_write(rom_write), .host_offset({17'd0,rom_address}),
        .host_wdata(rom_write_data), .host_rdata(rom_read_data), .host_valid(rom_read_valid),
        .ppu_vram_read(vram_request), .ppu_vram_address(vram_address),
        .ppu_vram_rdata(vram_data), .ppu_vram_valid(vram_valid),
        .ppu_oam_read(oam_phase != 0), .ppu_oam_pair(oam_pair_address),
        .ppu_oam_rdata(oam_data), .ppu_oam_valid(oam_valid),
        .wave_read(1'b0), .wave_address(4'd0), .wave_rdata(), .wave_valid()
    );
    n2m_interrupts u_interrupts (
        .clk_sys, .reset_sys, .core_reset, .gb_tick,
        .io_commit(owner_commit && destination == MEMORY_IRQ), .io_write(owner_write),
        .io_address(owner_address), .io_wdata(owner_wdata),
        .source_level({3'd0,stat_condition,vblank_condition}), .source_event(5'd0),
        .irq_ack, .io_selected(irq_selected), .io_rdata(irq_rdata),
        .ie_stored, .if_stored, .ie_observe, .if_observe
    );
    n2m_ppu u_ppu (
        .clk_sys, .reset_sys, .core_reset, .gb_tick, .epoch, .dot_before(dot_count),
        .io_commit(owner_commit && destination == MEMORY_PPU), .io_write(owner_write),
        .io_address(owner_address), .io_wdata(owner_wdata), .io_selected(ppu_selected),
        .io_rdata(ppu_rdata), .vram_request, .vram_address, .vram_data, .vram_valid,
        .oam_pair_address, .oam_phase, .oam_scan_index(), .oam_data, .oam_valid,
        .dma_active(1'b0), .vram_cpu_allow, .oam_cpu_allow, .stat_condition,
        .vblank_condition, .stat_rise(), .vblank_rise(), .fault(ppu_fault),
        .source_valid, .source_start, .source_shade, .source_x, .source_y,
        .source_epoch, .source_dot, .source_abort, .blank_assert(), .source_display_eligible
    );
    `N2M_ASSERT(SMOKE_NO_SNAPSHOT, clk_sys, reset_sys, !snapshot_request && !frame_read)
    `N2M_ASSERT(SMOKE_RELEASED_INPUT, clk_sys, reset_sys, buttons == 0)
    `N2M_ASSERT(SMOKE_NO_STOP, clk_sys, reset, !cpu_stopped)
endmodule
