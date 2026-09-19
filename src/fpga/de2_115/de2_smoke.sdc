# The 50 MHz CLOCK_50 reference and the I/O bounds of the flow proof.
create_clock -name clk_reference -period 20.000 [get_ports clk_reference]
derive_clock_uncertainty
set_input_delay -clock clk_reference -max 2.000 [get_ports key0_n]
set_input_delay -clock clk_reference -min 0.000 [get_ports key0_n]
set_output_delay -clock clk_reference -max 2.000 [all_outputs]
set_output_delay -clock clk_reference -min 0.000 [all_outputs]
