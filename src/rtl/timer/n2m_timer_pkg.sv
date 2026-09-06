`default_nettype none
package n2m_timer_pkg;
    typedef struct packed {
        logic [15:0] divider;
        logic [7:0] tima;
        logic [7:0] tma;
        logic [2:0] tac;
        logic [2:0] reload_delay;
        logic [1:0] reload_hold;
    } timer_state_t;
    typedef struct packed {
        logic request;
    } timer_request_t;
endpackage
