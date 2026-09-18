# The 50 MHz FPGA_CLK1_50 reference, the clocks derived from it by the two
# Altera PLL instances, and the I/O bounds of the Cyclone V clocking proof.
# The generated clock name is the fitted Altera PLL output counter; the Fitter
# and the Timing Analyzer both name it this way.
create_clock -name clk_reference -period 20.000 [get_ports clk_reference]
derive_pll_clocks
derive_clock_uncertainty
set_input_delay -clock [get_clocks {u_clocking|u_system_pll|altera_pll_i|general[0].gpll~PLL_OUTPUT_COUNTER|divclk}] -source_latency_included -max 2.000 [get_ports {board_reset_n core_reset pause_request}]
set_input_delay -clock [get_clocks {u_clocking|u_system_pll|altera_pll_i|general[0].gpll~PLL_OUTPUT_COUNTER|divclk}] -source_latency_included -min 0.000 [get_ports {board_reset_n core_reset pause_request}]
