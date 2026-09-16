// Boot copier: fills SDRAM with the flash-resident game library at power-up.
// Contract: wiki/src/rtl/storage/MAS_flash_library.md#boot-copier.
//
// From reset_sys release: WAIT_SDRAM until the controller's initialized;
// CHECK reads catalogue entry 16 from flash (two lines) and leaves for DONE
// when the entry is not a valid LOADER_ID menu entry (erased flash); COPY
// moves the 17 images and the catalogue, 34,880 lines in ascending address
// order, through the storage arbiter's third client; BOOT raises the menu
// select and the host-pause release for one clock; DONE idles until the next
// reset_sys. The reader holds one published line until its next acceptance,
// so it is the first stage of a two-line pipeline: a published line moves
// into the pending SDRAM write as soon as that register is free, and the
// next flash line is requested only when the reader's line has moved. The
// SDRAM (18 clocks per line plus refresh) sets the pace; the flash (17 per
// line) stays ahead. flash_boot is set on the edge the last line is accepted
// and cleared only by reset_sys. Every register is in clk_sys. In the FPGA
// image the reader instantiates the On-Chip Flash IP; under VERILATOR it
// selects the repository double, which the fixture loads through u_flash.
`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

module n2m_boot_copier (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic sdram_initialized,
    // Storage arbiter client: writes only, one line outstanding.
    output logic sdram_active,
    output logic sdram_valid,
    output logic sdram_write,
    output logic [n2m_interfaces_pkg::SDRAM_ADDRESS_BITS-1:0] sdram_address,
    output logic [n2m_interfaces_pkg::SDRAM_LINE_BYTES*8-1:0] sdram_data,
    input var logic sdram_ready,
    // Status: busy (CHECK or COPY) makes the endpoint report LOADING;
    // library_pending (WAIT_SDRAM, CHECK or COPY) holds sdram_ready low until
    // the library question is settled, so sdram_ready never pulses in the one
    // clock between initialized and CHECK; flash_boot is the $A000 bit 3
    // source; boot_return and boot_run pulse together in BOOT.
    output logic busy,
    output logic library_pending,
    output logic flash_boot,
    output logic boot_return,
    output logic boot_run
);
    import n2m_flash_pkg::*;
    localparam int ADDRESS_BITS = 32'(n2m_interfaces_pkg::SDRAM_ADDRESS_BITS);
    localparam int LINE_BITS = 32'(n2m_interfaces_pkg::SDRAM_LINE_BYTES) * 8;
    localparam logic [ADDRESS_BITS-1:0] LINE_STEP = ADDRESS_BITS'(n2m_interfaces_pkg::SDRAM_LINE_BYTES);

    boot_phase_t phase, phase_next;
    logic line_valid;
    logic line_ready;
    logic line_data_valid;
    logic [FLASH_LINE_BITS-1:0] line_data;
    logic [FLASH_WORD_BITS-1:0] fetch_word, fetch_word_next;
    logic [FLASH_WORD_BITS-1:0] fetch_end;
    logic fetch_outstanding, fetch_outstanding_next;
    logic fetched_valid, fetched_valid_next;
    logic pending_valid, pending_valid_next;
    logic [LINE_BITS-1:0] pending_data, pending_data_next;
    logic [ADDRESS_BITS-1:0] pending_address, pending_address_next;
    logic [ADDRESS_BITS-1:0] write_address, write_address_next;
    logic [FLASH_LINE_BITS-1:0] check_low, check_low_next;
    logic check_second, check_second_next;
    logic flash_boot_next;
    logic [19:0] copy_clocks, copy_clocks_next;
    logic [ADDRESS_BITS-1:0] order_address, order_address_next;
    logic accept;
    logic fetch_accept;
    logic last_line;
    n2m_interfaces_pkg::catalogue_entry_t entry;
    logic entry_ok;

    n2m_flash_reader u_reader (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .line_valid(line_valid), .line_word(fetch_word),
        .line_ready(line_ready), .line_data_valid(line_data_valid), .line_data(line_data)
    );

    assign sdram_active = phase == BOOT_CHECK || phase == BOOT_COPY;
    assign busy = sdram_active;
    assign library_pending = phase == BOOT_WAIT_SDRAM || sdram_active;
    assign sdram_valid = phase == BOOT_COPY && pending_valid && !reset_sys;
    assign sdram_write = 1'b1;
    assign sdram_address = pending_address;
    assign sdram_data = pending_data;
    assign accept = sdram_valid && sdram_ready;
    assign last_line = pending_address == FLASH_COPY_LAST_LINE;
    assign boot_return = phase == BOOT_BOOT && !reset_sys;
    assign boot_run = boot_return;

    // One flash line in flight, requested only while the reader's published
    // line has moved on and lines remain in the current phase.
    assign fetch_end = phase == BOOT_CHECK ? FLASH_CHECK_END : FLASH_COPY_END_WORD;
    assign line_valid = sdram_active && !fetch_outstanding && !fetched_valid && fetch_word != fetch_end && !reset_sys;
    assign fetch_accept = line_valid && line_ready;

    // Entry 16 as the two catalogue lines, low line first.
    assign entry = {line_data, check_low};
    assign entry_ok = entry.valid == n2m_interfaces_pkg::LIBRARY_CATALOGUE_VALID &&
        32'(entry.length) == 32'(n2m_interfaces_pkg::LIBRARY_SLOT_BYTES) &&
        entry.profile == n2m_interfaces_pkg::PROFILE_LOADER_ID;

    always_comb begin
        phase_next = phase;
        fetch_word_next = fetch_word;
        fetch_outstanding_next = fetch_outstanding;
        fetched_valid_next = fetched_valid;
        pending_valid_next = pending_valid;
        pending_data_next = pending_data;
        pending_address_next = pending_address;
        write_address_next = write_address;
        check_low_next = check_low;
        check_second_next = check_second;
        flash_boot_next = flash_boot;
        copy_clocks_next = phase == BOOT_COPY ? copy_clocks + 20'd1 : 20'd0;
        // Independent order witness: the address every accepted write must carry.
        order_address_next = accept ? order_address + LINE_STEP : order_address;
        if (fetch_accept) begin
            fetch_word_next = fetch_word + FLASH_WORD_BITS'(FLASH_LINE_WORDS);
            fetch_outstanding_next = 1'b1;
        end
        if (line_data_valid) fetch_outstanding_next = 1'b0;
        case (phase)
            BOOT_WAIT_SDRAM: if (sdram_initialized) begin
                fetch_word_next = FLASH_CHECK_START;
                check_second_next = 1'b0;
                phase_next = BOOT_CHECK;
            end
            BOOT_CHECK: if (line_data_valid) begin
                if (!check_second) begin
                    check_low_next = line_data;
                    check_second_next = 1'b1;
                end else if (entry_ok) begin
                    fetch_word_next = FLASH_DATA_BASE;
                    write_address_next = '0;
                    phase_next = BOOT_COPY;
                end else phase_next = BOOT_DONE;
            end
            BOOT_COPY: begin
                // The accepted write frees the pending register; a line the
                // reader still holds moves in on the same edge.
                if (accept) begin
                    if (fetched_valid) begin
                        pending_data_next = line_data;
                        pending_address_next = write_address;
                        write_address_next = write_address + LINE_STEP;
                        fetched_valid_next = 1'b0;
                    end else pending_valid_next = 1'b0;
                    if (last_line) begin
                        flash_boot_next = 1'b1;
                        phase_next = BOOT_BOOT;
                    end
                end
                // A published line takes the free pending register or waits
                // in the reader; it is never dropped or reordered.
                if (line_data_valid) begin
                    if (pending_valid_next) fetched_valid_next = 1'b1;
                    else begin
                        pending_data_next = line_data;
                        pending_address_next = write_address;
                        write_address_next = write_address + LINE_STEP;
                        pending_valid_next = 1'b1;
                    end
                end
            end
            BOOT_BOOT: phase_next = BOOT_DONE;
            BOOT_DONE: begin end
            default: phase_next = BOOT_DONE;
        endcase
    end

    `DFF_ARST_VAL(phase, phase_next, clk_sys, reset_sys, BOOT_WAIT_SDRAM)
    `DFF_ARST_VAL(fetch_word, fetch_word_next, clk_sys, reset_sys, FLASH_CHECK_START)
    `DFF_ARST_VAL(fetch_outstanding, fetch_outstanding_next, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(fetched_valid, fetched_valid_next, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(pending_valid, pending_valid_next, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(pending_data, pending_data_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(pending_address, pending_address_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(write_address, write_address_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(check_low, check_low_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(check_second, check_second_next, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(flash_boot, flash_boot_next, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(copy_clocks, copy_clocks_next, clk_sys, reset_sys, '0)
    `DFF_ARST_VAL(order_address, order_address_next, clk_sys, reset_sys, '0)

    `N2M_ASSERT(FLASH_COPY_ORDER, clk_sys, reset_sys, accept |-> sdram_address == order_address)
    `N2M_ASSERT(FLASH_COPY_BOUND, clk_sys, reset_sys,
        phase == BOOT_COPY |-> copy_clocks < 20'(FLASH_COPY_BOUND_CLOCKS))
    `N2M_ASSERT(FLASH_COPY_REQUEST_IN_COPY, clk_sys, reset_sys, sdram_valid |-> phase == BOOT_COPY)
    `N2M_ASSERT(FLASH_COPY_LINE_EXPECTED, clk_sys, reset_sys, line_data_valid |-> fetch_outstanding)
    `N2M_ASSERT(FLASH_COPY_HOLD_FREE, clk_sys, reset_sys, fetch_accept |-> !fetched_valid)
    `N2M_ASSERT(FLASH_BOOT_AFTER_COPY, clk_sys, reset_sys, $rose(flash_boot) |-> $past(phase) == BOOT_COPY)
endmodule
`default_nettype wire
