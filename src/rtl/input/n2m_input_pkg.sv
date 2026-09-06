`timescale 1ns/1ps
package n2m_input_pkg;
    typedef struct packed {
        logic valid;
        logic source_write;
        logic [7:0] value;
    } input_write_t;
    typedef struct packed {
        logic valid;
        logic [7:0] buttons;
    } input_update_t;
    typedef struct packed {
        logic physical_source;
        logic [7:0] host_buttons;
    } input_host_state_t;
endpackage
