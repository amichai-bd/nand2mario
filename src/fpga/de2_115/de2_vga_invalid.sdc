# Deliberate invalid constraint: the DAC clock is sourced from the Cyclone V
# Altera PLL's output counter, which no Cyclone IV E netlist contains, so the
# generated pin clock has no source and the build must fail naming it.
create_clock -name clk_reference -period 20.000 [get_ports clk_reference]
derive_pll_clocks
derive_clock_uncertainty
set_input_delay -clock [get_clocks {u_clocking|u_system_pll|altpll_component|auto_generated|pll1|clk*}] -source_latency_included -max 2.000 [get_ports {board_reset_n core_reset pause_request}]
set_input_delay -clock [get_clocks {u_clocking|u_system_pll|altpll_component|auto_generated|pll1|clk*}] -source_latency_included -min 0.000 [get_ports {board_reset_n core_reset pause_request}]
create_generated_clock -name vga_dac_clk -source [get_pins {u_clocking|u_pll|altera_pll_i|cyclonev_pll|counter[0].output_counter|divclk}] -invert [get_ports {vga_clk}]
