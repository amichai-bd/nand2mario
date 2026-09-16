create_clock -name clk_reference -period 20.000 [get_ports clk_reference]
derive_pll_clocks
derive_clock_uncertainty
# Same-clock hold margin: register-to-hard-block paths (M9K address registers,
# the flash IP's LUT-gated drclk) have no logic to absorb the block's later
# clock and the fitter pads hold only to zero; add 0.150 ns so it routes each
# with that physical margin (wiki/src/clocks-resets-cdc.md#timing-constraints).
# Same-edge hold checks ignore clock uncertainty unless it is enabled explicitly.
set_clock_uncertainty -hold -add -enable_same_physical_edge -from [get_clocks {u_clocking|u_system_pll|altpll_component|auto_generated|pll1|clk[0]}] -to [get_clocks {u_clocking|u_system_pll|altpll_component|auto_generated|pll1|clk[0]}] 0.150
# Virtual system inputs land directly on M9K input registers, whose clock arrives
# about 0.8 ns after the PLL-compensated logic clock. A zero minimum budget on a
# virtual pin is fictional and reports a hold violation; 1.000 ns keeps the
# 1-2 ns bookkeeping window and leaves every physical path unchanged.
set_input_delay -clock [get_clocks {u_clocking|u_system_pll|altpll_component|auto_generated|pll1|clk*}] -source_latency_included -max 2.000 [get_ports {board_reset_n a_read a_write a_address* a_wdata* a_byte_enable* b_read b_address*}]
set_input_delay -clock [get_clocks {u_clocking|u_system_pll|altpll_component|auto_generated|pll1|clk*}] -source_latency_included -min 1.000 [get_ports {board_reset_n a_read a_write a_address* a_wdata* a_byte_enable* b_read b_address*}]
