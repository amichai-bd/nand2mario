// Flash library constants and the flash reader's state record. Contract:
// wiki/src/rtl/storage/MAS_flash_library.md. Every address here is a 32-bit
// word address; the contract numbers words in the MAX 10 flash's own space,
// where the user range starts at UFM1 (word 0x00800), and the On-Chip Flash
// IP's Avalon-MM data slave numbers the same words from 0.
`timescale 1ns/1ps
package n2m_flash_pkg;
    localparam int FLASH_WORD_BITS = 20;
    localparam int FLASH_LINE_BITS = 128;
    localparam int FLASH_LINE_WORDS = 4;
    // 10M50 user range in the single compressed image mode: UFM1, UFM0, CFM2
    // and CFM1, words 0x00800-0x2E7FF (736 KiB). The IP maps Avalon word 0
    // onto flash word FLASH_DATA_BASE (its ADDR_RANGE1_OFFSET).
    localparam logic [FLASH_WORD_BITS-1:0] FLASH_DATA_BASE = 20'h00800;
    localparam logic [FLASH_WORD_BITS-1:0] FLASH_USER_LAST = 20'h2E7FF;
    localparam int FLASH_USER_WORDS = 32'h0002E000;
    // Sector starts in flash words (UG-M10UFM, 10M50 rows of the IP's
    // device_sector_address_offset table).
    localparam logic [FLASH_WORD_BITS-1:0] FLASH_UFM1_START = 20'h00800;
    localparam logic [FLASH_WORD_BITS-1:0] FLASH_UFM0_START = 20'h02800;
    localparam logic [FLASH_WORD_BITS-1:0] FLASH_CFM2_START = 20'h04800;
    localparam logic [FLASH_WORD_BITS-1:0] FLASH_CFM1_START = 20'h1C800;
    // Library layout: slot i at FLASH_DATA_BASE + i * FLASH_SLOT_WORDS, the
    // catalogue after slot 16.
    localparam int FLASH_SLOTS = 17;
    localparam int FLASH_SLOT_WORDS = 32'h00002000;
    localparam logic [FLASH_WORD_BITS-1:0] FLASH_CATALOGUE_START = 20'h22800;
    localparam int FLASH_CATALOGUE_WORDS = 256;
    // Avalon-MM data slave shape the IP derives for this configuration.
    localparam int FLASH_AVMM_ADDR_BITS = 18;
    localparam int FLASH_AVMM_BURST_BITS = 3;
    localparam logic [FLASH_AVMM_BURST_BITS-1:0] FLASH_BURST_COUNT = 3'd4;
    // Read cadence of the parallel 10M50 IP at 25 MHz, counted in clk_sys
    // edges from the edge the reader accepts a line: the IP accepts the
    // Avalon read three edges later, word 0 is sampled seven edges after that
    // acceptance and word 3 ten edges after it (edge 13); line_data_valid is
    // high in the following clock and line_ready in the one after, so a
    // back-to-back stream accepts one line every 15 clocks. A longer burst
    // would continue at four words per seven clocks.
    localparam int FLASH_AVMM_WAIT_CLOCKS = 3;
    localparam int FLASH_FIRST_WORD_CLOCK = 7;
    localparam int FLASH_LAST_WORD_CLOCK = 10;
    localparam int FLASH_LINE_CLOCKS = FLASH_AVMM_WAIT_CLOCKS + FLASH_LAST_WORD_CLOCK;
    localparam int FLASH_LINE_PERIOD_CLOCKS = FLASH_LINE_CLOCKS + 2;
    localparam int FLASH_BURST_PERIOD_CLOCKS = 7;
    localparam logic [31:0] FLASH_ERASED_WORD = 32'hFFFFFFFF;

    typedef enum logic [1:0] {
        FLASH_IDLE,
        FLASH_ISSUE,
        FLASH_DATA,
        FLASH_PUBLISH
    } flash_phase_t;

    typedef struct packed {
        flash_phase_t phase;
        logic [FLASH_AVMM_ADDR_BITS-1:0] address;
        logic [1:0] word;
        logic [FLASH_LINE_BITS-1:0] line;
    } flash_reader_state_t;

    localparam flash_reader_state_t FLASH_RESET_STATE = '{
        phase: FLASH_IDLE, address: '0, word: '0, line: '0
    };

    // Contract mapping: SDRAM device byte address a to its flash word.
    function automatic logic [FLASH_WORD_BITS-1:0] flash_word(input logic [25:0] address);
        return FLASH_DATA_BASE + 20'(address >> 2);
    endfunction

    // Flash word to the IP's Avalon-MM data slave word address.
    function automatic logic [FLASH_AVMM_ADDR_BITS-1:0] flash_avmm_address(input logic [FLASH_WORD_BITS-1:0] word);
        return FLASH_AVMM_ADDR_BITS'(word - FLASH_DATA_BASE);
    endfunction
endpackage
