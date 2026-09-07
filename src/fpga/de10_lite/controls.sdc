# Independent physical board references; derived clocks retain real PLL relations.
create_clock -name clk_reference -period 20.000 [get_ports clk_reference]
create_clock -name clk_adc_reference -period 100.000 [get_ports clk_adc_reference]
derive_pll_clocks
derive_clock_uncertainty
# Asynchronous external controls have no source-clock phase relationship.
# Their 0-2ns bookkeeping budgets end at checked first-stage synchronizers;
# following stages and every internal control path retain normal timing checks.
set_input_delay -clock [get_clocks {u_clocking|u_system_pll|altpll_component|auto_generated|pll1|clk*}] -source_latency_included -max 2.000 [get_ports {board_reset_n uart_rx buttons_n*}]
set_input_delay -clock [get_clocks {u_clocking|u_system_pll|altpll_component|auto_generated|pll1|clk*}] -source_latency_included -min 0.000 [get_ports {board_reset_n uart_rx buttons_n*}]
