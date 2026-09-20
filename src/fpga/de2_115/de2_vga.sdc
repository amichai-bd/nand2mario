# The 50 MHz CLOCK_50 reference, the two ALTPLL clocks the clock contract derives
# from it, and the ADV7123's own clock at the VGA_CLK pin.
create_clock -name clk_reference -period 20.000 [get_ports clk_reference]
derive_pll_clocks
derive_clock_uncertainty
set_input_delay -clock [get_clocks {u_clocking|u_system_pll|altpll_component|auto_generated|pll1|clk*}] -source_latency_included -max 2.000 [get_ports {board_reset_n core_reset pause_request}]
set_input_delay -clock [get_clocks {u_clocking|u_system_pll|altpll_component|auto_generated|pll1|clk*}] -source_latency_included -min 0.000 [get_ports {board_reset_n core_reset pause_request}]
# The DAC latches data and controls on the rising edge of its CLOCK input, so the
# pin carries the 25.2 MHz pixel clock inverted: the DAC samples half a pixel
# period after the fabric drove the data
# (wiki/src/de2-115-board.md#the-dacs-clock-blank-and-sync-inputs).
create_generated_clock -name vga_dac_clk -source [get_pins {u_clocking|u_pll|altpll_component|auto_generated|pll1|clk[0]}] -invert [get_ports {vga_clk}]
