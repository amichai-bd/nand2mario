# The 50 MHz FPGA_CLK1_50 reference, the clocks the two Altera PLL instances
# derive from it, and the asynchronous board inputs of the UART endpoint image.
# The generated clock name is the fitted Altera PLL output counter, as in
# nano_clocking.sdc. KEY[0] and the serial receive line both end at checked
# synchronizers, so their bounds are the arrival window, not a data budget.
create_clock -name clk_reference -period 20.000 [get_ports clk_reference]
derive_pll_clocks
derive_clock_uncertainty
set_input_delay -clock [get_clocks {u_clocking|u_system_pll|altera_pll_i|cyclonev_pll|counter[0].output_counter|divclk}] -source_latency_included -max 2.000 [get_ports {board_reset_n uart_rx}]
set_input_delay -clock [get_clocks {u_clocking|u_system_pll|altera_pll_i|cyclonev_pll|counter[0].output_counter|divclk}] -source_latency_included -min 0.000 [get_ports {board_reset_n uart_rx}]
