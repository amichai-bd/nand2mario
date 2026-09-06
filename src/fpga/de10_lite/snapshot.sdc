# Snapshot service with virtual ports, not physical board I/O.
create_clock -name clk_sys -period 20.000 [get_ports clk_sys]
derive_clock_uncertainty
set_input_delay -clock clk_sys -max 2.000 [get_ports {reset_sys core_reset observe* snapshot_request frame_read frame_address*}]
set_input_delay -clock clk_sys -min 0.000 [get_ports {reset_sys core_reset observe* snapshot_request frame_read frame_address*}]
set_output_delay -clock clk_sys -max 2.000 [all_outputs]
set_output_delay -clock clk_sys -min 0.000 [all_outputs]
