# Virtual system-domain packet service ports; no physical UART timing claim.
create_clock -name clk_sys -period 20.000 [get_ports clk_sys]
derive_clock_uncertainty
set_input_delay -clock clk_sys -max 2.000 [get_ports {reset_sys encoded_write encoded_write_address* encoded_write_data* encoded_read encoded_read_address* decoded_write decoded_write_address* decoded_write_data* decoded_read decoded_read_address*}]
set_input_delay -clock clk_sys -min 0.000 [get_ports {reset_sys encoded_write encoded_write_address* encoded_write_data* encoded_read encoded_read_address* decoded_write decoded_write_address* decoded_write_data* decoded_read decoded_read_address*}]
set_output_delay -clock clk_sys -max 2.000 [all_outputs]
set_output_delay -clock clk_sys -min 0.000 [all_outputs]
