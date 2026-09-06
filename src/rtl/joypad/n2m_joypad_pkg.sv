`timescale 1ns/1ps
package n2m_joypad_pkg;
    typedef struct packed {
        logic [7:0] buttons;
        logic [1:0] select_bits;
    } joypad_state_t;
endpackage
