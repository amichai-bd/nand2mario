# Independent physical board references; derived clocks retain real PLL relations.
create_clock -name clk_sys -period 20.000 [get_ports clk_sys]
create_clock -name clk_adc_reference -period 100.000 [get_ports clk_adc_reference]
derive_pll_clocks
derive_clock_uncertainty
# Asynchronous external controls have no source-clock phase relationship.
# Their 0-2ns bookkeeping budgets end at checked first-stage synchronizers;
# following stages and every internal control path retain normal timing checks.
set_input_delay -clock clk_sys -max 2.000 [get_ports {board_reset_n uart_rx buttons_n*}]
set_input_delay -clock clk_sys -min 0.000 [get_ports {board_reset_n uart_rx buttons_n*}]
