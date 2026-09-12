`default_nettype none
package n2m_memory_pkg;
    // One transaction on the authoritative even/odd OAM A banks.
    typedef struct packed {
        logic read;
        logic [1:0] write_enable;
        logic [6:0] pair;
        logic [15:0] data;
    } memory_oam_request_t;
    typedef struct packed {
        logic valid;
        logic [15:0] data;
    } memory_oam_response_t;
    // Source-qualified late addressed-row class; architectural byte is last.
    function automatic logic [63:0] oam_late_result(
        input logic [63:0] last_row,
        input logic [15:0] target_word,
        input logic [2:0] byte_index,
        input logic [7:0] data
    );
        logic [7:0] pivot;
        integer lane;
        pivot = last_row[39:32];
        oam_late_result = last_row;
        for (lane = 0; lane < 2; lane = lane + 1) begin
            oam_late_result[16*int'(byte_index[2:1])+8*lane +: 8] =
                (target_word[8*lane +: 8] & pivot)
                | (target_word[8*lane +: 8] & last_row[16*int'(byte_index[2:1])+8*lane +: 8])
                | (pivot & last_row[16*int'(byte_index[2:1])+8*lane +: 8]);
        end
        oam_late_result[8*int'(byte_index) +: 8] = data;
    endfunction
    // Internal store selector, not a CPU/host address or a wire ABI.
    typedef enum logic [2:0] {
        STORE_ROM = 3'd0,
        STORE_WRAM = 3'd1,
        STORE_HRAM = 3'd2,
        STORE_VRAM = 3'd3,
        STORE_OAM = 3'd4,
        STORE_WAVE = 3'd5
    } memory_store_t;

    // Host peek selectors are wire ABI values owned by the interface package,
    // deliberately separate from the internal store enum above. ROM is never a
    // peek target: its host load and readback keep port A.
    function automatic logic peek_known(input logic [7:0] selector);
        peek_known = selector == n2m_interfaces_pkg::PEEK_WRAM ||
            selector == n2m_interfaces_pkg::PEEK_HRAM ||
            selector == n2m_interfaces_pkg::PEEK_VRAM ||
            selector == n2m_interfaces_pkg::PEEK_OAM ||
            selector == n2m_interfaces_pkg::PEEK_WAVE;
    endfunction
    function automatic memory_store_t peek_store(input logic [7:0] selector);
        case (selector)
            n2m_interfaces_pkg::PEEK_WRAM: peek_store = STORE_WRAM;
            n2m_interfaces_pkg::PEEK_HRAM: peek_store = STORE_HRAM;
            n2m_interfaces_pkg::PEEK_VRAM: peek_store = STORE_VRAM;
            n2m_interfaces_pkg::PEEK_OAM: peek_store = STORE_OAM;
            default: peek_store = STORE_WAVE;
        endcase
    endfunction
    function automatic logic [31:0] peek_bytes(input logic [7:0] selector);
        case (selector)
            n2m_interfaces_pkg::PEEK_WRAM: peek_bytes =
                32'(n2m_interfaces_pkg::GB_WRAM_END) - 32'(n2m_interfaces_pkg::GB_WRAM_START) + 32'd1;
            n2m_interfaces_pkg::PEEK_HRAM: peek_bytes =
                32'(n2m_interfaces_pkg::GB_HRAM_END) - 32'(n2m_interfaces_pkg::GB_HRAM_START) + 32'd1;
            n2m_interfaces_pkg::PEEK_VRAM: peek_bytes =
                32'(n2m_interfaces_pkg::GB_VRAM_END) - 32'(n2m_interfaces_pkg::GB_VRAM_START) + 32'd1;
            n2m_interfaces_pkg::PEEK_OAM: peek_bytes =
                32'(n2m_interfaces_pkg::GB_OAM_END) - 32'(n2m_interfaces_pkg::GB_OAM_START) + 32'd1;
            n2m_interfaces_pkg::PEEK_WAVE: peek_bytes =
                32'(n2m_interfaces_pkg::GB_VIEW_WAVE_END) - 32'(n2m_interfaces_pkg::GB_VIEW_WAVE_START) + 32'd1;
            default: peek_bytes = 32'd0;
        endcase
    endfunction

    // Destinations select behavior owners; they never imply a read value.
    typedef enum logic [3:0] {
        MEMORY_DIRECT = 4'd0,
        MEMORY_VRAM = 4'd1,
        MEMORY_OAM = 4'd2,
        MEMORY_UNUSABLE = 4'd3,
        MEMORY_ABSENT_CART = 4'd4,
        MEMORY_JOYP = 4'd5,
        MEMORY_SERIAL = 4'd6,
        MEMORY_TIMER = 4'd7,
        MEMORY_IRQ = 4'd8,
        MEMORY_APU = 4'd9,
        MEMORY_WAVE = 4'd10,
        MEMORY_PPU = 4'd11,
        MEMORY_DMA = 4'd12,
        MEMORY_BOOT = 4'd13,
        MEMORY_UNUSED_IO = 4'd14
    } memory_destination_t;
endpackage
