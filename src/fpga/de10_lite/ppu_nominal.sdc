create_clock -name clk_reference -period 20.000 [get_ports clk_reference]
derive_pll_clocks
derive_clock_uncertainty
# Same-clock hold margin: register-to-hard-block paths (M9K address registers,
# the flash IP's LUT-gated drclk) have no logic to absorb the block's later
# clock and the fitter pads hold only to zero; add 0.150 ns so it routes each
# with that physical margin (wiki/src/clocks-resets-cdc.md#timing-constraints).
set_clock_uncertainty -hold -add -from [get_clocks {u_clocking|u_system_pll|altpll_component|auto_generated|pll1|clk[0]}] -to [get_clocks {u_clocking|u_system_pll|altpll_component|auto_generated|pll1|clk[0]}] 0.150
set_input_delay -clock [get_clocks {u_clocking|u_system_pll|altpll_component|auto_generated|pll1|clk*}] -source_latency_included -max 2.000 [get_ports {board_reset_n core_reset pause_request}]
set_input_delay -clock [get_clocks {u_clocking|u_system_pll|altpll_component|auto_generated|pll1|clk*}] -source_latency_included -min 0.000 [get_ports {board_reset_n core_reset pause_request}]
set_input_delay -clock [get_clocks {u_clocking|u_system_pll|altpll_component|auto_generated|pll1|clk*}] -source_latency_included -max 2.000 [get_ports {io_commit io_write io_address* io_wdata* vram_data* vram_valid oam_data* oam_valid dma_active}]
set_input_delay -clock [get_clocks {u_clocking|u_system_pll|altpll_component|auto_generated|pll1|clk*}] -source_latency_included -min 0.000 [get_ports {io_commit io_write io_address* io_wdata* vram_data* vram_valid oam_data* oam_valid dma_active}]
