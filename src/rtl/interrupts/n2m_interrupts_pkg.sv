`default_nettype none
package n2m_interrupts_pkg;
    typedef struct packed {
        logic write_if;
        logic write_ie;
        logic [7:0] data;
        logic [4:0] ack;
    } interrupt_operation_t;
endpackage
