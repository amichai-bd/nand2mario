`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// Architectural access and IDU address are independently qualified. Mode
// blocking never removes a separately observed internal-address effect.
module n2m_oam_qualify (
    input var logic clk_sys,
    input var logic reset,
    input var logic effect_sample,
    input var logic effect_resolved,
    input var n2m_cpu_pkg::cpu_address_effect_t address_effect,
    input var logic bus_commit,
    input var n2m_cpu_pkg::cpu_bus_plan_t bus_plan,
    input var logic [1:0] ppu_oam_phase,
    input var logic [5:0] ppu_scan_index,
    output n2m_oam_pkg::oam_effect_t kind,
    output logic [4:0] row_index,
    output logic invalid_observation
);
    import n2m_oam_pkg::*;
    logic ordinary_oam, idu_oam, read_effect, write_effect, scan;
    assign row_index = ppu_scan_index[5:1];
    assign scan = ppu_oam_phase == 2'd1 && ppu_scan_index < 6'd40;
    assign invalid_observation = effect_sample && (!effect_resolved ||
        (address_effect.valid && address_effect.known_mask[15:8] != 8'hff));
    assign ordinary_oam = bus_commit && bus_plan.address[15:8] == 8'hfe;
    assign idu_oam = effect_sample && address_effect.valid &&
        address_effect.write_effect && address_effect.address[15:8] == 8'hfe;
    assign read_effect = ordinary_oam && !bus_plan.write_enable;
    assign write_effect = (ordinary_oam && bus_plan.write_enable) || idu_oam;
    always_comb begin
        kind = OAM_NONE;
        if (!reset && !invalid_observation && scan && effect_sample) begin
            if (read_effect && write_effect) kind = OAM_READ_WRITE;
            else if (read_effect) kind = OAM_READ;
            else if (write_effect) kind = OAM_WRITE;
        end
    end
    `N2M_ASSERT(OAM_OBSERVATION_RESOLVED, clk_sys, reset, !invalid_observation)
    `N2M_ASSERT(OAM_COMMIT_SAMPLE, clk_sys, reset, !bus_commit || effect_sample)
    `N2M_ASSERT(OAM_SAMPLE_KNOWN, clk_sys, reset,
        !effect_sample || !$isunknown({effect_resolved, address_effect.valid,
            address_effect.known_mask, address_effect.write_effect, ppu_oam_phase, ppu_scan_index}))
    `N2M_ASSERT(OAM_MASKED_ADDRESS_KNOWN, clk_sys, reset,
        !(effect_sample && address_effect.valid) ||
            !$isunknown(address_effect.address & address_effect.known_mask))
endmodule
