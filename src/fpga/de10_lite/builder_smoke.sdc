create_clock -name clk -period 20.000 [get_ports clk]
derive_clock_uncertainty
set_output_delay -clock clk -max 2.000 [all_outputs]
set_output_delay -clock clk -min 0.000 [all_outputs]
