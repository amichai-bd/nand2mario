# The 50 MHz CLOCK_50 reference, the clocks the two ALTPLL instances derive from
# it, and the I/O bounds of the Cyclone IV E clocking proof. The generated clock
# names are ALTPLL's own, the same ones the DE10-Lite constrains.
create_clock -name clk_reference -period 20.000 [get_ports clk_reference]
derive_pll_clocks
derive_clock_uncertainty
set_input_delay -clock [get_clocks {u_clocking|u_system_pll|altpll_component|auto_generated|pll1|clk*}] -source_latency_included -max 2.000 [get_ports {board_reset_n core_reset pause_request}]
set_input_delay -clock [get_clocks {u_clocking|u_system_pll|altpll_component|auto_generated|pll1|clk*}] -source_latency_included -min 0.000 [get_ports {board_reset_n core_reset pause_request}]
