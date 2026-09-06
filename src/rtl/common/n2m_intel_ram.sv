`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// Contract: wiki/src/rtl/common/MAS_memory_primitives.md.
// The identical Intel instance is compiled in Questa and MAX 10 synthesis.
module n2m_intel_ram #(
    parameter integer DEPTH = 1024,
    parameter integer DATA_BITS = 8,
    parameter integer ADDRESS_BITS = $clog2(DEPTH),
    parameter integer BYTE_LANES = 1,
    parameter bit DUAL_CLOCK = 0
) (
    input var logic clk_a,
    input var logic clk_b,
    input var logic reset_a,
    input var logic reset_b,
    input var logic a_read,
    input var logic a_write,
    input var logic [ADDRESS_BITS-1:0] a_address,
    input var logic [DATA_BITS-1:0] a_wdata,
    input var logic [BYTE_LANES-1:0] a_byte_enable,
    output logic [DATA_BITS-1:0] a_rdata,
    output logic a_valid,
    input var logic b_read,
    input var logic [ADDRESS_BITS-1:0] b_address,
    output logic [DATA_BITS-1:0] b_rdata,
    output logic b_valid
);
    localparam integer PRIMITIVE_LANES = (DATA_BITS + 7) / 8;
    logic read_a, write_a, read_b;
    logic primitive_write;
    logic valid_a, valid_b;
    logic read_clock_b;
    logic [2:0] unused_ecc;
    logic [DATA_BITS-1:0] ram_data_a, ram_data_b;
    logic [PRIMITIVE_LANES-1:0] primitive_byte_enable;
    generate if (DATA_BITS < 8) begin : sub_byte_enable
        // Intel byte lanes are eight or nine bits. A shade uses whole-word
        // write gating and leaves the unsupported sub-byte lane port inactive.
        assign primitive_byte_enable = '1;
        assign primitive_write = write_a && a_byte_enable[0];
    end else if (BYTE_LANES == 1) begin : whole_word_enable
        assign primitive_byte_enable = {PRIMITIVE_LANES{a_byte_enable[0]}};
        assign primitive_write = write_a;
    end else begin : byte_lane_enable
        assign primitive_byte_enable = a_byte_enable;
        assign primitive_write = write_a;
    end endgenerate
    assign read_clock_b = DUAL_CLOCK ? clk_b : clk_a;
    assign read_a = a_read && !reset_a;
    assign write_a = a_write && !reset_a;
    assign read_b = b_read && !reset_b;
    `DFF_ARST_VAL(valid_a, read_a, clk_a, reset_a, 1'b0)
    `DFF_ARST_VAL(valid_b, read_b, read_clock_b, reset_b, 1'b0)
    assign a_valid = valid_a && !reset_a;
    assign b_valid = valid_b && !reset_b;
    assign a_rdata = ram_data_a;
    assign b_rdata = ram_data_b;

    // Input/address registers give one request edge of latency. An additional
    // output register would add a cycle and violate the consumer boundary.
    altsyncram #(
        .intended_device_family("MAX 10"), .ram_block_type("M9K"),
        .operation_mode("BIDIR_DUAL_PORT"), .lpm_type("altsyncram"),
        .width_a(DATA_BITS), .widthad_a(ADDRESS_BITS), .numwords_a(DEPTH),
        .width_b(DATA_BITS), .widthad_b(ADDRESS_BITS), .numwords_b(DEPTH),
        .width_byteena_a(PRIMITIVE_LANES), .width_byteena_b(PRIMITIVE_LANES),
        .byte_size(8),
        .address_reg_b(DUAL_CLOCK ? "CLOCK1" : "CLOCK0"),
        .rdcontrol_reg_b(DUAL_CLOCK ? "CLOCK1" : "CLOCK0"),
        .indata_reg_b(DUAL_CLOCK ? "CLOCK1" : "CLOCK0"),
        .wrcontrol_wraddress_reg_b(DUAL_CLOCK ? "CLOCK1" : "CLOCK0"),
        .byteena_reg_b(DUAL_CLOCK ? "CLOCK1" : "CLOCK0"),
        .outdata_reg_a("UNREGISTERED"), .outdata_reg_b("UNREGISTERED"),
        .clock_enable_input_a("BYPASS"), .clock_enable_input_b("BYPASS"),
        .clock_enable_output_a("BYPASS"), .clock_enable_output_b("BYPASS"),
        .read_during_write_mode_port_a("NEW_DATA_NO_NBE_READ"),
        .read_during_write_mode_port_b("NEW_DATA_NO_NBE_READ"),
        // Different-clock collisions have no defined device result. The pinned
        // Intel model's coercion diagnostic is recorded by the builder.
        .read_during_write_mode_mixed_ports(DUAL_CLOCK ? "DONT_CARE" : "OLD_DATA"),
        .power_up_uninitialized("TRUE"), .init_file("UNUSED")
    ) ram (
        .clock0(clk_a), .clock1(DUAL_CLOCK ? clk_b : 1'b1),
        .clocken0(1'b1), .clocken1(1'b1), .clocken2(1'b1), .clocken3(1'b1),
        .aclr0(1'b0), .aclr1(1'b0),
        .address_a(a_address), .data_a(a_wdata), .wren_a(primitive_write), .rden_a(read_a),
        .byteena_a(primitive_byte_enable), .addressstall_a(1'b0), .q_a(ram_data_a),
        .address_b(b_address), .data_b({DATA_BITS{1'b0}}), .wren_b(1'b0), .rden_b(read_b),
        .byteena_b({PRIMITIVE_LANES{1'b1}}), .addressstall_b(1'b0), .q_b(ram_data_b), .eccstatus(unused_ecc)
    );

    `N2M_ASSERT_NO_RST(INTEL_RAM_CONFIGURATION, clk_a,
        DEPTH > 1 && DEPTH <= (2 ** ADDRESS_BITS) && BYTE_LANES > 0 &&
        ((BYTE_LANES == 1 && (DATA_BITS == 1 || DATA_BITS == 2 || DATA_BITS == 8 || DATA_BITS == 16)) ||
         (DATA_BITS == 32 && BYTE_LANES == 4)))
    `N2M_ASSERT(INTEL_RAM_A_RANGE, clk_a, reset_a,
        !(a_read || a_write) || int'(a_address) < DEPTH)
    `N2M_ASSERT(INTEL_RAM_B_RANGE, read_clock_b, reset_b,
        !b_read || int'(b_address) < DEPTH)
    `N2M_ASSERT(INTEL_RAM_SAME_PORT_LANES, clk_a, reset_a,
        !(a_read && a_write) || (&a_byte_enable))
    // This is a deliberately stronger owner precondition than coincident
    // simulator edges: no active cross-port request window may overlap here.
    `N2M_ASSERT(INTEL_RAM_MIXED_PORT_A, clk_a, reset_a,
        !(write_a && read_b && a_address == b_address))
    generate if (DUAL_CLOCK) begin : dual_clock_checks
        `N2M_ASSERT(INTEL_RAM_MIXED_PORT_B, read_clock_b, reset_b,
            !(write_a && read_b && a_address == b_address))
    end endgenerate
    `N2M_ASSERT_KNOWN(INTEL_RAM_A_CONTROL, clk_a, reset_a,
        {a_read, a_write, a_address, a_byte_enable})
    `N2M_ASSERT_KNOWN(INTEL_RAM_B_CONTROL, read_clock_b, reset_b,
        {b_read, b_address})
    `N2M_ASSERT(INTEL_RAM_WRITE_KNOWN, clk_a, reset_a,
        !a_write || !$isunknown(a_wdata))
endmodule
