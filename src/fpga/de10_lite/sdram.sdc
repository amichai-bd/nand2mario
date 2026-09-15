# Board reference and the real parallel PLLs, as in the composed image.
create_clock -name clk_reference -period 20.000 [get_ports clk_reference]
derive_pll_clocks
derive_clock_uncertainty
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
# DRAM_CLK carries the generated clock itself and has no data path; the zero
# delays keep check_timing's output-delay inventory complete.
set_output_delay -clock sdram_clk -max 0.0 [get_ports {DRAM_CLK}]
set_output_delay -clock sdram_clk -min 0.0 [get_ports {DRAM_CLK}]
