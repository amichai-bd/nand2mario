`default_nettype none
package n2m_memory_pkg;
    // Internal store selector, not a CPU/host address or a wire ABI.
    typedef enum logic [2:0] {
        STORE_ROM = 3'd0,
        STORE_WRAM = 3'd1,
        STORE_HRAM = 3'd2,
        STORE_VRAM = 3'd3,
        STORE_OAM = 3'd4,
        STORE_WAVE = 3'd5
    } memory_store_t;
endpackage
