# Virtual same-clock load-owner service ports; not physical UART timing.
create_clock -name clk_sys -period 20.000 [get_ports clk_sys]
derive_clock_uncertainty
set_input_delay -clock clk_sys -max 2.000 [get_ports {reset_sys write_enable write_address* write_present read_enable read_address*}]
set_input_delay -clock clk_sys -min 0.000 [get_ports {reset_sys write_enable write_address* write_present read_enable read_address*}]
set_output_delay -clock clk_sys -max 2.000 [all_outputs]
set_output_delay -clock clk_sys -min 0.000 [all_outputs]
