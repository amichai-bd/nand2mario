# The 50 MHz CLOCK_50 reference, the two ALTPLL clocks the clock contract derives
# from it, and the ADV7123's own clock at the VGA_CLK pin.
create_clock -name clk_reference -period 20.000 [get_ports clk_reference]
derive_pll_clocks
derive_clock_uncertainty
# Same-clock hold margin: register-to-hard-block paths (the M9K stores' address
# registers) have no logic to absorb the block's later clock and the fitter pads
# hold only to zero; add 0.150 ns so it routes each with that physical margin
# (wiki/src/clocks-resets-cdc.md#timing-constraints). Same-edge hold checks
# ignore clock uncertainty unless it is enabled explicitly, and the fitter treats
# a user hold assignment as the transfer's whole assignment
# (Critical Warning 332168), so the derived setup value is re-declared unchanged.
set_clock_uncertainty -setup -add -from [get_clocks {u_clocking|u_system_pll|altpll_component|auto_generated|pll1|clk[0]}] -to [get_clocks {u_clocking|u_system_pll|altpll_component|auto_generated|pll1|clk[0]}] 0.000
set_clock_uncertainty -hold -add -enable_same_physical_edge -from [get_clocks {u_clocking|u_system_pll|altpll_component|auto_generated|pll1|clk[0]}] -to [get_clocks {u_clocking|u_system_pll|altpll_component|auto_generated|pll1|clk[0]}] 0.150
# Every asynchronous board input terminates at a checked two-stage synchronizer:
# the reset control's for KEY[0], the shared button filter's for the other twelve.
set_input_delay -clock [get_clocks {u_clocking|u_system_pll|altpll_component|auto_generated|pll1|clk*}] -source_latency_included -max 2.000 [get_ports {board_reset_n key_action_n[*] sw_buttons[*] sw_view[*]}]
set_input_delay -clock [get_clocks {u_clocking|u_system_pll|altpll_component|auto_generated|pll1|clk*}] -source_latency_included -min 0.000 [get_ports {board_reset_n key_action_n[*] sw_buttons[*] sw_view[*]}]
# The DAC latches data and controls on the rising edge of its CLOCK input, so the
# pin carries the 25.2 MHz pixel clock inverted: the DAC samples half a pixel
# period after the fabric drove the data
# (wiki/src/de2-115-board.md#the-dacs-clock-blank-and-sync-inputs).
create_generated_clock -name vga_dac_clk -source [get_pins {u_clocking|u_pll|altpll_component|auto_generated|pll1|clk[0]}] -invert [get_ports {vga_clk}]
