`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// Loader profile owner. Contract: wiki/src/rtl/cartridge/MAS_loader_profile.md.
// Decodes the bank and select register commits the memory owner resolves as
// CPU ROM writes, serves the status bytes and the $FF window mask to the CPU
// read path, runs the copy engine, owns the ROM host-port and storage
// arbiters, detects the KEY1 return and publishes the host LIBRARY_* views.
// Register effects exist only while PROFILE == LOADER_ID, except the game
// exit register: the direct profile's one decoded cartridge write, a return
// request with the KEY1 rules.
module n2m_loader #(
    parameter int unsigned KEY1_DEBOUNCE_EDGES = 32'(n2m_interfaces_pkg::LIBRARY_KEY1_DEBOUNCE_EDGES),
    parameter int unsigned KEY1_HOLD_EDGES = 32'(n2m_interfaces_pkg::LIBRARY_KEY1_HOLD_EDGES)
) (
    input var logic clk_sys,
    input var logic reset_sys,
    // Endpoint state.
    input var logic [7:0] profile,
    input var logic image_valid,
    // host_session: the endpoint's claim (an open session or a LOAD_BEGIN
    // waiting for a fill); host_loading: the open session itself.
    input var logic host_session,
    input var logic host_loading,
    input var logic host_port_busy,
    input var logic host_return,
    input var logic paused,
    input var logic sdram_initialized,
    // CPU commits resolved to the ROM store by the memory owner.
    input var logic rom_commit,
    input var logic [14:0] commit_offset,
    input var logic [7:0] commit_data,
    // CPU read override: registered bytes and the $FF window mask.
    input var logic [15:0] cpu_address,
    output logic read_override,
    output logic [7:0] read_data,
    // KEY1 pin, active low.
    input var logic key1_n,
    // UART load owner side of the ROM host port.
    input var logic uart_rom_write,
    input var logic uart_rom_read,
    input var logic [15:0] uart_rom_address,
    input var logic [7:0] uart_rom_wdata,
    output logic rom_host_write,
    output logic rom_host_read,
    output logic [31:0] rom_host_offset,
    output logic [7:0] rom_host_wdata,
    // Boot copier client of the storage arbiter and its status
    // (wiki/src/rtl/storage/MAS_flash_library.md#boot-copier): copier_busy
    // is CHECK or COPY, copier_pending also WAIT_SDRAM, boot_return the menu
    // select the copier requests.
    input var logic copier_busy,
    input var logic copier_pending,
    input var logic copier_valid,
    input var logic copier_write,
    input var logic [n2m_interfaces_pkg::SDRAM_ADDRESS_BITS-1:0] copier_address,
    input var logic [n2m_interfaces_pkg::SDRAM_LINE_BYTES*8-1:0] copier_data,
    output logic copier_ready,
    output logic copier_response_valid,
    input var logic flash_boot,
    input var logic boot_return,
    // Host SDRAM bridge client of the storage arbiter.
    input var logic host_sdram_valid,
    input var logic host_sdram_write,
    input var logic [n2m_interfaces_pkg::SDRAM_ADDRESS_BITS-1:0] host_sdram_address,
    input var logic [n2m_interfaces_pkg::SDRAM_LINE_BYTES*8-1:0] host_sdram_data,
    output logic host_sdram_ready,
    output logic host_sdram_response_valid,
    // SDRAM controller line interface.
    output logic sdram_request_valid,
    output logic sdram_request_write,
    output logic [n2m_interfaces_pkg::SDRAM_ADDRESS_BITS-1:0] sdram_request_address,
    output logic [n2m_interfaces_pkg::SDRAM_LINE_BYTES*8-1:0] sdram_request_data,
    input var logic sdram_request_ready,
    input var logic sdram_response_valid,
    input var logic [n2m_interfaces_pkg::SDRAM_LINE_BYTES*8-1:0] sdram_response_data,
    // Core control owner.
    output logic engine_pause,
    output logic engine_reset_request,
    input var logic engine_reset_accept,
    input var logic engine_reset_done,
    // Image validity and profile, owned by the endpoint's command owner.
    output logic image_invalidate,
    output logic image_publish,
    output logic [7:0] image_profile,
    // Status. copy_busy and swap_busy include the boot copier's CHECK and
    // COPY, so the endpoint reports LOADING and refuses LOAD_BEGIN while
    // SDRAM fills; the engine's own bounds use engine_copy_busy/engine_swap_busy.
    output logic copy_busy,
    output logic swap_busy,
    output logic window_busy,
    output logic sdram_ready,
    output logic [31:0] library_status,
    output logic [31:0] library_key1
);
    localparam logic [7:0] LOADER_ID = n2m_interfaces_pkg::PROFILE_LOADER_ID;
    localparam logic [7:0] DIRECT_ID = n2m_interfaces_pkg::PROFILE_DIRECT_ID;
    localparam logic [7:0] MBC1_ID = n2m_interfaces_pkg::PROFILE_MBC1_ID;
    logic loader_active, bank_commit, select_commit, select_in_range, commit_accept;
    logic game_active, exit_commit, exit_return;
    logic engine_start, engine_busy, engine_done, engine_swap, engine_result_write;
    logic [7:0] engine_result;
    logic engine_sdram_valid, engine_sdram_ready, engine_sdram_response_valid;
    logic [n2m_interfaces_pkg::SDRAM_ADDRESS_BITS-1:0] engine_sdram_address;
    logic engine_rom_write;
    logic [14:0] engine_rom_address;
    logic [7:0] engine_rom_wdata;
    logic key1_pressed, key1_event;
    logic [5:0] bank, bank_next;
    logic window_ready, window_ready_next, fill_running;
    logic [7:0] result, result_next, last_index, last_index_next;
    logic key1_pending, key1_pending_next;
    logic job_valid, job_valid_next, job_swap, job_swap_next;
    logic [6:0] job_index, job_index_next;
    logic return_request, return_busy;
    logic [7:0] status_byte;
    logic [16:0] busy_edges, busy_edges_next;
    logic engine_copy_busy, engine_swap_busy;

    assign loader_active = profile == LOADER_ID;
    // The controller's initialized and the copier past COPY (BOOT or DONE).
    assign sdram_ready = sdram_initialized && !copier_pending;
    assign bank_commit = rom_commit && loader_active && commit_offset[14:13] == 2'b01;
    assign select_in_range = commit_data <= n2m_interfaces_pkg::LIBRARY_MENU_INDEX;
    assign select_commit = rom_commit && loader_active && commit_offset[14:13] == 2'b11 && select_in_range;
    // Game exit register (MAS_loader_profile.md#game-exit-register): in the
    // direct profile a write of LIBRARY_GAME_EXIT_VALUE to $6000-$7FFF is a
    // return request; refused NOT_READY like a select while SDRAM is not ready.
    // The MBC1 profile honors the same register with the same decode
    // (MAS_mbc1_profile.md#registers); its MODE register takes data[0] beside it.
    assign game_active = profile == DIRECT_ID || profile == MBC1_ID;
    assign exit_commit = rom_commit && game_active && commit_offset[14:13] == 2'b11 &&
        commit_data == n2m_interfaces_pkg::LIBRARY_GAME_EXIT_VALUE;
    assign exit_return = exit_commit && sdram_ready;
    // A host load session excludes the engine; the pending session and an
    // in-flight ROM readback are the endpoint's claim on the port.
    assign commit_accept = !engine_copy_busy && !host_session;
    assign return_request = key1_event || host_return || boot_return || exit_return;
    assign engine_copy_busy = job_valid || engine_busy;
    assign engine_swap_busy = (job_valid && job_swap) || (engine_busy && engine_swap);
    assign copy_busy = engine_copy_busy || copier_busy;
    assign swap_busy = engine_swap_busy || copier_busy;
    assign fill_running = (job_valid && !job_swap) || (engine_busy && !engine_swap);
    assign window_busy = fill_running;
    assign engine_start = job_valid && !engine_busy && !host_port_busy && !host_session;
    // On the engine's done edge the loader is free again for a return event.
    assign return_busy = job_valid || (engine_busy && !engine_done);

    always_comb begin
        bank_next = bank;
        window_ready_next = window_ready;
        result_next = result;
        last_index_next = last_index;
        key1_pending_next = key1_pending;
        job_valid_next = job_valid;
        job_swap_next = job_swap;
        job_index_next = job_index;
        if (engine_result_write) result_next = engine_result;
        if (engine_done) begin
            if (!engine_swap) window_ready_next = 1'b1;
            if (key1_pending && !host_session) begin
                job_valid_next = 1'b1;
                job_swap_next = 1'b1;
                job_index_next = 7'(n2m_interfaces_pkg::LIBRARY_MENU_INDEX);
            end
            key1_pending_next = 1'b0;
        end
        if (engine_start) job_valid_next = 1'b0;
        // A swap and a host load session both overwrite the upper half. The
        // swap clears the window on its invalidate step, after the catalogue
        // check passed and the core paused; a refused select changes nothing.
        if (host_loading || image_invalidate) window_ready_next = 1'b0;
        if (select_commit) last_index_next = commit_data;
        if (bank_commit && !engine_copy_busy) begin
            if (!sdram_ready) result_next = n2m_interfaces_pkg::LIBRARY_RESULT_NOT_READY;
            else if (commit_accept) begin
                bank_next = commit_data[5:0];
                window_ready_next = 1'b0;
                job_valid_next = 1'b1;
                job_swap_next = 1'b0;
                job_index_next = {1'b0, commit_data[5:0]};
            end
        end
        if (select_commit && !engine_copy_busy) begin
            if (!sdram_ready) result_next = n2m_interfaces_pkg::LIBRARY_RESULT_NOT_READY;
            else if (commit_accept) begin
                job_valid_next = 1'b1;
                job_swap_next = 1'b1;
                job_index_next = commit_data[6:0];
            end
        end
        if (exit_commit && !engine_copy_busy && !sdram_ready)
            result_next = n2m_interfaces_pkg::LIBRARY_RESULT_NOT_READY;
        // The return is dropped in a host session, queued behind a copy and
        // otherwise starts the menu swap; a second event while queued is dropped.
        if (return_request && !host_session) begin
            if (engine_done && key1_pending) begin end  // second event while queued: dropped
            else if (return_busy) key1_pending_next = 1'b1;
            else begin
                job_valid_next = 1'b1;
                job_swap_next = 1'b1;
                job_index_next = 7'(n2m_interfaces_pkg::LIBRARY_MENU_INDEX);
            end
        end
        if (host_session) begin
            // The host owns the console: a queued return or fill is dropped.
            key1_pending_next = 1'b0;
            if (!engine_busy) job_valid_next = 1'b0;
        end
        // The bound counts from each job's accepting edge.
        busy_edges_next = engine_copy_busy && !engine_done ? busy_edges + 17'd1 : 17'd0;
    end
    `DFF_ARST_VAL(bank, bank_next, clk_sys, reset_sys, 6'd0)
    `DFF_ARST_VAL(window_ready, window_ready_next, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(result, result_next, clk_sys, reset_sys, n2m_interfaces_pkg::LIBRARY_RESULT_NONE)
    `DFF_ARST_VAL(last_index, last_index_next, clk_sys, reset_sys, 8'hFF)
    `DFF_ARST_VAL(key1_pending, key1_pending_next, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(job_valid, job_valid_next, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(job_swap, job_swap_next, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(job_index, job_index_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(busy_edges, busy_edges_next, clk_sys, reset_sys, '0)

    // Status bytes and the CPU read override, one registered byte per address.
    assign status_byte = {engine_copy_busy, window_ready, sdram_ready, key1_pending, flash_boot, 3'b0};
    always_comb begin
        read_override = 1'b0;
        read_data = 8'hFF;
        if (loader_active && cpu_address[15:13] == 3'b101) begin
            read_override = 1'b1;
            case (cpu_address[12:0])
                13'h0000: read_data = status_byte;
                13'h0001: read_data = {2'b0, bank};
                13'h0002: read_data = result;
                13'h0003: read_data = last_index;
                default: read_data = 8'hFF;
            endcase
        end else if (loader_active && window_busy && cpu_address[15:14] == 2'b01) begin
            read_override = 1'b1;
        end
    end
    assign library_status = {2'b0, bank, last_index, result, status_byte};

    n2m_loader_key1 #(.DEBOUNCE_EDGES(KEY1_DEBOUNCE_EDGES), .HOLD_EDGES(KEY1_HOLD_EDGES)) u_key1 (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .key1_n(key1_n),
        .pressed(key1_pressed), .return_event(key1_event), .hold_count(library_key1)
    );
    n2m_loader_engine u_engine (
        .clk_sys(clk_sys), .reset_sys(reset_sys),
        .start(engine_start), .start_swap(job_swap), .start_index(job_index),
        .busy(engine_busy), .done(engine_done), .swap_job(engine_swap),
        .result_write(engine_result_write), .result_value(engine_result),
        .sdram_valid(engine_sdram_valid), .sdram_address(engine_sdram_address),
        .sdram_ready(engine_sdram_ready), .sdram_response_valid(engine_sdram_response_valid),
        .sdram_response_data(sdram_response_data),
        .rom_write(engine_rom_write), .rom_address(engine_rom_address), .rom_wdata(engine_rom_wdata),
        .pause_hold(engine_pause), .reset_request(engine_reset_request),
        .reset_accept(engine_reset_accept), .reset_done(engine_reset_done), .paused(paused),
        .release_fault_hold(host_loading), .image_valid(image_valid),
        .image_invalidate(image_invalidate), .image_publish(image_publish), .image_profile(image_profile)
    );
    n2m_rom_port_arbiter u_rom_port (
        .clk_sys(clk_sys), .reset_sys(reset_sys),
        .uart_owns(host_loading), .uart_write(uart_rom_write), .uart_read(uart_rom_read),
        .uart_address(uart_rom_address), .uart_wdata(uart_rom_wdata),
        .engine_owns(engine_busy), .engine_write(engine_rom_write),
        .engine_address(engine_rom_address), .engine_wdata(engine_rom_wdata),
        .host_write(rom_host_write), .host_read(rom_host_read),
        .host_offset(rom_host_offset), .host_wdata(rom_host_wdata)
    );
    n2m_storage_arbiter u_storage (
        .clk_sys(clk_sys), .reset_sys(reset_sys),
        .engine_valid(engine_sdram_valid), .engine_write(1'b0), .engine_address(engine_sdram_address),
        .engine_data('0), .engine_ready(engine_sdram_ready), .engine_response_valid(engine_sdram_response_valid),
        .swap_busy(engine_swap_busy),
        .host_valid(host_sdram_valid), .host_write(host_sdram_write), .host_address(host_sdram_address),
        .host_data(host_sdram_data), .host_ready(host_sdram_ready), .host_response_valid(host_sdram_response_valid),
        // The boot copier has priority while it fills SDRAM after power-up.
        .copier_active(copier_busy), .copier_valid(copier_valid), .copier_write(copier_write),
        .copier_address(copier_address), .copier_data(copier_data),
        .copier_ready(copier_ready), .copier_response_valid(copier_response_valid),
        .request_valid(sdram_request_valid), .request_write(sdram_request_write),
        .request_address(sdram_request_address), .request_data(sdram_request_data),
        .request_ready(sdram_request_ready), .response_valid(sdram_response_valid)
    );
    `N2M_ASSERT(LOADER_REGS_ONLY_IN_PROFILE, clk_sys, reset_sys,
        (bank_commit || select_commit || read_override) |-> profile == LOADER_ID)
    `N2M_ASSERT(LOADER_EXIT_ONLY_IN_GAME_PROFILE, clk_sys, reset_sys, exit_commit |-> profile == DIRECT_ID || profile == MBC1_ID)
    `N2M_ASSERT(LOADER_SWAP_BOUND, clk_sys, reset_sys,
        engine_copy_busy && engine_swap_busy |-> busy_edges < 17'(n2m_interfaces_pkg::LIBRARY_SWAP_BOUND_EDGES))
    `N2M_ASSERT(LOADER_FILL_BOUND, clk_sys, reset_sys,
        engine_copy_busy && !engine_swap_busy |-> busy_edges < 17'(n2m_interfaces_pkg::LIBRARY_FILL_BOUND_EDGES))
    // The copier never overlaps an engine job: the core is paused with an
    // invalid image until the boot select it requests, and the only other
    // return sources cannot fire first: a KEY1 return needs a 0.5 s hold
    // against a 32 ms boot, and a host packet cannot complete before
    // initialized at 115200 baud.
    `N2M_ASSERT(LOADER_COPIER_EXCLUSIVE, clk_sys, reset_sys, !(copier_busy && engine_copy_busy))
    `N2M_ASSERT(LOADER_ENGINE_NOT_IN_SESSION, clk_sys, reset_sys, !(engine_busy && host_loading))
    `N2M_ASSERT(LOADER_ENGINE_START_FREE, clk_sys, reset_sys, engine_start |-> !host_session && !host_port_busy)
    `N2M_ASSERT(LOADER_KEY1_PENDING_BUSY, clk_sys, reset_sys, key1_pending |-> engine_copy_busy)
endmodule
`default_nettype wire
