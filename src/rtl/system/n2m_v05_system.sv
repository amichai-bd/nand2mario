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
    logic pause_request, core_initialized, instruction_complete, cpu_stopped;
    logic [7:0] buttons, profile, endpoint_state;
    logic [63:0] retirement_count;
    logic image_valid, rom_write, rom_read, rom_read_valid;
    logic [14:0] rom_address;
    logic [7:0] rom_write_data, rom_read_data;
    logic snapshot_request, frame_read;
    logic snapshot_ready, snapshot_done, snapshot_ok, snapshot_valid, frame_valid;
    n2m_interfaces_pkg::snapshot_t snapshot_metadata;
    logic [7:0] frame_data, effective_buttons, joyp_rdata;
    n2m_input_pkg::input_update_t effective_update;
    logic joyp_selected_active, joyp_event;
    logic [12:0] frame_address;
    logic request_valid, response_valid, cpu_initialized, cpu_fault, memory_fault, ppu_fault;
    logic memory_initialized, storage_read, storage_write;
    n2m_memory_pkg::memory_store_t storage_store, raw_store;
    n2m_memory_pkg::memory_destination_t destination;
    logic [14:0] storage_offset, raw_offset;
    logic [7:0] storage_wdata, storage_rdata;
    logic storage_valid, owner_prepare, owner_commit, owner_write;
    logic [15:0] owner_address;
    logic [7:0] owner_wdata, owner_rdata;
    logic owner_valid, owner_service;
    logic raw_read, raw_write, video_owner, video_allowed, video_read;
    logic oam_cpu_late_write, late_busy, late_fault, oam_read_allowed;
    n2m_memory_pkg::memory_oam_request_t late_request;
    n2m_memory_pkg::memory_oam_response_t late_response;
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
    logic oam_valid, vram_cpu_allow, vram_cpu_read_allow, oam_cpu_allow, oam_cpu_read_allow, stat_condition, vblank_condition;
    logic reset, blank_assert;
    logic observe_valid, observe_complete, observe_abort;
    logic [14:0] observe_index;
    logic [1:0] observe_shade;
    logic [31:0] observe_epoch;
    logic [63:0] observe_sequence, observe_dot;
    assign reset = reset_sys || core_reset;
    assign core_initialized = memory_initialized && cpu_initialized;
    assign fault = cpu_fault || memory_fault || ppu_fault || late_fault;

    n2m_uart #(.CLOCK_HZ(25000000), .BAUD(UART_BAUD)) u_uart (
        .clk_sys, .reset_sys, .uart_rx, .uart_tx,
        .build_id(BUILD_ID), .gb_tick, .paused,
        .core_initialized, .instruction_complete, .retirement_valid, .cpu_stopped,
        .physical_commit(1'b0), .physical_buttons(8'd0), .effective_buttons, .effective_update,
        .input_source_observe(),
        .pause_request, .core_reset, .buttons, .epoch, .dot_count, .retirement_count,
        .profile, .image_valid, .endpoint_state, .rom_write, .rom_read, .rom_address,
        .rom_write_data, .rom_read_data, .rom_read_valid,
        .snapshot_request, .snapshot_ready, .snapshot_done,
        .snapshot_ok, .snapshot_valid, .snapshot_metadata,
        .frame_read, .frame_address, .frame_data, .frame_valid
    );
    n2m_timebase u_timebase (.clk_sys, .reset_sys, .core_reset, .pause_request, .gb_tick, .paused);
    n2m_cpu u_cpu (
        .clk_sys, .reset_sys, .core_reset, .gb_tick, .profile_id(profile), .epoch,
        .dot_before(dot_count), .ie(ie_observe), .iflags(if_observe),
        .buttons(effective_buttons),
        .read_data, .response_valid, .joyp_selected_active, .wake_request(1'b0),
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
    assign video_owner = destination == n2m_memory_pkg::MEMORY_VRAM || destination == n2m_memory_pkg::MEMORY_OAM;
    assign video_allowed = destination == n2m_memory_pkg::MEMORY_VRAM ? (owner_write ? vram_cpu_allow : vram_cpu_read_allow)
        : (owner_write ? (oam_cpu_allow || oam_cpu_late_write) : oam_cpu_read_allow);
    assign video_read = owner_prepare && video_owner && video_allowed && !owner_write
        && !(destination == n2m_memory_pkg::MEMORY_OAM && late_busy);
    assign raw_read = storage_read || video_read;
    assign raw_write = storage_write || (owner_commit && video_owner && video_allowed && owner_write
        && !(destination == n2m_memory_pkg::MEMORY_OAM && (late_busy || oam_cpu_late_write)));
    assign raw_store = video_owner ? (destination == n2m_memory_pkg::MEMORY_VRAM ? n2m_memory_pkg::STORE_VRAM : n2m_memory_pkg::STORE_OAM) : storage_store;
    assign raw_offset = video_owner ? (destination == n2m_memory_pkg::MEMORY_VRAM ? {2'd0,address[12:0]} : {7'd0,address[7:0]}) : storage_offset;
    `DFF_ARST_VAL(video_pending, video_read, clk_sys, reset, 1'b0)
    `DFF_EN(video_address, address, clk_sys, video_read)
    always_comb begin
        owner_service = 1;
        owner_valid = 1;
        owner_rdata = 0;
        case (destination)
            n2m_memory_pkg::MEMORY_VRAM, n2m_memory_pkg::MEMORY_OAM: begin
                owner_rdata = video_allowed ? storage_rdata : 8'hff;
                owner_valid = !video_allowed || (video_pending && video_address == address && storage_valid);
            end
            n2m_memory_pkg::MEMORY_PPU: owner_rdata = ppu_rdata;
            n2m_memory_pkg::MEMORY_IRQ: owner_rdata = irq_rdata;
            n2m_memory_pkg::MEMORY_JOYP: begin
                owner_rdata = joyp_rdata;
                owner_service = 1'b1;
                owner_valid = 1'b1;
            end
            default: begin owner_service = 0; owner_valid = 0; end
        endcase
    end
    n2m_oam_late_write u_oam_late (
        .clk_sys, .reset_sys, .core_reset,
        .prepare(owner_prepare && destination == n2m_memory_pkg::MEMORY_OAM && owner_write),
        .commit(owner_commit && destination == n2m_memory_pkg::MEMORY_OAM && owner_write),
        .late_window(oam_cpu_late_write), .address(owner_address), .data(owner_wdata),
        .ppu_read(oam_phase != 0), .ppu_pair(oam_pair_address),
        .response(late_response), .request(late_request), .raw_oam_busy(late_busy),
        .late_commit(), .ppu_read_allowed(oam_read_allowed), .fault(late_fault)
    );
    n2m_memory_stores u_stores (.oam_request(late_request), .oam_response(late_response),
        .clk_sys, .reset_sys, .core_reset, .init_done(memory_initialized),
        .access_read(raw_read), .access_write(raw_write), .access_store(raw_store),
        .access_address(raw_offset), .access_wdata(write_data),
        .access_rdata(storage_rdata), .access_valid(storage_valid),
        .host_read(rom_read), .host_write(rom_write), .host_offset({17'd0,rom_address}),
        .host_wdata(rom_write_data), .host_rdata(rom_read_data), .host_valid(rom_read_valid),
        .ppu_vram_read(vram_request), .ppu_vram_address(vram_address),
        .ppu_vram_rdata(vram_data), .ppu_vram_valid(vram_valid),
        .ppu_oam_read(oam_read_allowed), .ppu_oam_pair(oam_pair_address),
        .ppu_oam_rdata(oam_data), .ppu_oam_valid(oam_valid),
        .wave_read(1'b0), .wave_address(4'd0), .wave_rdata(), .wave_valid()
    );
    n2m_interrupts u_interrupts (
        .clk_sys, .reset_sys, .core_reset, .gb_tick,
        .io_commit(owner_commit && destination == n2m_memory_pkg::MEMORY_IRQ), .io_write(owner_write),
        .io_address(owner_address), .io_wdata(owner_wdata),
        .source_level({3'd0,stat_condition,vblank_condition}), .source_event({joyp_event,4'd0}),
        .irq_ack, .io_selected(irq_selected), .io_rdata(irq_rdata),
        .ie_stored, .if_stored, .ie_observe, .if_observe
    );
    n2m_ppu u_ppu (
        .clk_sys, .reset_sys, .core_reset, .gb_tick, .epoch, .dot_before(dot_count),
        .io_commit(owner_commit && destination == n2m_memory_pkg::MEMORY_PPU), .io_write(owner_write),
        .io_address(owner_address), .io_wdata(owner_wdata), .io_selected(ppu_selected),
        .io_rdata(ppu_rdata), .vram_request, .vram_address, .vram_data, .vram_valid,
        .oam_pair_address, .oam_phase, .oam_scan_index(), .oam_data, .oam_valid,
        .dma_active(1'b0), .vram_cpu_allow, .oam_cpu_allow, .vram_cpu_read_allow, .oam_cpu_read_allow, .oam_late_future(), .oam_cpu_late_write, .stat_condition,
        .vblank_condition, .stat_rise(), .vblank_rise(), .fault(ppu_fault),
        .source_valid, .source_start, .source_shade, .source_x, .source_y,
        .source_epoch, .source_dot, .source_abort, .blank_assert, .source_display_eligible
    );
    n2m_joypad u_joypad (
        .clk_sys, .reset_sys, .core_reset, .gb_tick,
        .input_commit(effective_update.valid), .input_buttons(effective_update.buttons),
        .io_commit(owner_commit && destination == n2m_memory_pkg::MEMORY_JOYP), .io_write(owner_write),
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
    `N2M_ASSERT(V05_NO_STOP, clk_sys, reset, !cpu_stopped)
endmodule
