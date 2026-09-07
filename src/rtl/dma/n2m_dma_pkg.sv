`default_nettype none
package n2m_dma_pkg;
    typedef struct packed {
        logic [7:0] page;
        logic [7:0] offset;
        logic pending;
        logic active;
        logic fault;
    } dma_state_t;
endpackage
