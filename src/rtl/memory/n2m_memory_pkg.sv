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
    // Internal store selector, not a CPU/host address or a wire ABI.
    typedef enum logic [2:0] {
        STORE_ROM = 3'd0,
        STORE_WRAM = 3'd1,
        STORE_HRAM = 3'd2,
        STORE_VRAM = 3'd3,
        STORE_OAM = 3'd4,
        STORE_WAVE = 3'd5
    } memory_store_t;

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
