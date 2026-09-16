# Board reference and the real parallel PLLs, as in the composed image.
create_clock -name clk_reference -period 20.000 [get_ports clk_reference]
derive_pll_clocks
derive_clock_uncertainty
# Same-clock hold margin: register-to-hard-block paths (M9K address registers,
# the flash IP's LUT-gated drclk) have no logic to absorb the block's later
# clock and the fitter pads hold only to zero; add 0.150 ns so it routes each
# with that physical margin (wiki/src/clocks-resets-cdc.md#timing-constraints).
# Same-edge hold checks ignore clock uncertainty unless it is enabled explicitly.
# The fitter treats a user hold assignment as the transfer's whole assignment
# (Critical Warning 332168), so the derived setup value is re-declared unchanged.
set_clock_uncertainty -setup -add -from [get_clocks {u_clocking|u_system_pll|altpll_component|auto_generated|pll1|clk[0]}] -to [get_clocks {u_clocking|u_system_pll|altpll_component|auto_generated|pll1|clk[0]}] 0.000
set_clock_uncertainty -hold -add -enable_same_physical_edge -from [get_clocks {u_clocking|u_system_pll|altpll_component|auto_generated|pll1|clk[0]}] -to [get_clocks {u_clocking|u_system_pll|altpll_component|auto_generated|pll1|clk[0]}] 0.150
# Asynchronous board inputs terminate at checked synchronization stages.
set_input_delay -clock [get_clocks {u_clocking|u_system_pll|altpll_component|auto_generated|pll1|clk*}] -source_latency_included -max 2.000 [get_ports {board_reset_n uart_rx}]
set_input_delay -clock [get_clocks {u_clocking|u_system_pll|altpll_component|auto_generated|pll1|clk*}] -source_latency_included -min 0.000 [get_ports {board_reset_n uart_rx}]
# SDRAM pin clock: the 25 MHz system clock inverted at the pin
# (wiki/src/rtl/storage/MAS_sdram.md#clock-relationship-and-constraints).
create_generated_clock -name sdram_clk -source [get_pins {u_clocking|u_system_pll|altpll_component|auto_generated|pll1|clk[0]}] -invert [get_ports {DRAM_CLK}]
# ISSI IS42S16320D at CL2: tAC 6.0 + 1 ns margin, tOH 2.5 - 1 ns, tIS 1.8 + 1 ns, tIH 0.8 + 1 ns.
set_input_delay -clock sdram_clk -max 7.0 [get_ports {DRAM_DQ[*]}]
set_input_delay -clock sdram_clk -min 1.5 [get_ports {DRAM_DQ[*]}]
set_output_delay -clock sdram_clk -max 2.8 [get_ports {DRAM_ADDR[*] DRAM_BA[*] DRAM_CAS_N DRAM_CKE DRAM_CS_N DRAM_DQ[*] DRAM_DQML DRAM_DQMH DRAM_RAS_N DRAM_WE_N}]
set_output_delay -clock sdram_clk -min -1.8 [get_ports {DRAM_ADDR[*] DRAM_BA[*] DRAM_CAS_N DRAM_CKE DRAM_CS_N DRAM_DQ[*] DRAM_DQML DRAM_DQMH DRAM_RAS_N DRAM_WE_N}]
