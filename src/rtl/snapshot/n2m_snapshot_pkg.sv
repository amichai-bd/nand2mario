`timescale 1ns/1ps
`default_nettype none
package n2m_snapshot_pkg;
    typedef struct packed {
        logic latest_valid;
        logic latest_bank;
        logic assembly_bank;
        logic [5:0] packed_shades;
        logic host_valid;
        logic host_bank;
        logic busy;
        logic copy_bank;
        logic copy_pending;
        logic [12:0] copy_address;
        n2m_interfaces_pkg::snapshot_t latest_metadata;
        n2m_interfaces_pkg::snapshot_t copy_metadata;
        n2m_interfaces_pkg::snapshot_t host_metadata;
    } snapshot_state_t;
endpackage
