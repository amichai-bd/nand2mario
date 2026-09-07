# Real independent board references. Public proof outputs use clk_sys budgets.
create_clock -name clk_sys -period 20.000 [get_ports clk_sys]
create_clock -name clk_adc_reference -period 100.000 [get_ports clk_adc_reference]
derive_pll_clocks
derive_clock_uncertainty
set_false_path -from [get_ports board_reset_n] -to [get_registers {*u_reset|board_release*}]
# Virtual proof stimulus has a 0-2ns input budget; the asynchronous reset cut
# above remains the boundary, with release through the destination registers.
set_input_delay -clock clk_sys -max 2.000 [get_ports board_reset_n]
set_input_delay -clock clk_sys -min 0.000 [get_ports board_reset_n]
set_output_delay -clock clk_sys -max 2.000 [all_outputs]
set_output_delay -clock clk_sys -min 0.000 [all_outputs]
