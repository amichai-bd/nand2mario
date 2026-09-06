create_clock -name clk_sys -period 20.000 [get_ports clk_sys]
derive_pll_clocks
derive_clock_uncertainty
set_input_delay -clock clk_sys -max 2.000 [get_ports {board_reset_n a_read a_write a_address* a_wdata* a_byte_enable* b_read b_address*}]
set_input_delay -clock clk_sys -min 0.000 [get_ports {board_reset_n a_read a_write a_address* a_wdata* a_byte_enable* b_read b_address*}]
# Synthetic virtual-port budget includes launch source latency. This proof
# does not specify a physical off-chip pixel source or board interface.
set_input_delay -clock [get_clocks {*pll1|clk*}] -source_latency_included -max 2.000 [get_ports {frame_read frame_address*}]
set_input_delay -clock [get_clocks {*pll1|clk*}] -source_latency_included -min 0.000 [get_ports {frame_read frame_address*}]
