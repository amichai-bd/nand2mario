# Separate external clocks; no generated relationship or blanket clock exception.
create_clock -name clk_sys -period 20.000 [get_ports clk_sys]
create_clock -name clk_pix -period 39.682540 [get_ports clk_pix]
derive_clock_uncertainty
set_input_delay -clock clk_sys -max 2.000 [get_ports {reset_sys uart_rx}]
set_input_delay -clock clk_sys -min 0.000 [get_ports {reset_sys uart_rx}]
set_input_delay -clock clk_pix -max 2.000 [get_ports reset_pix]
set_input_delay -clock clk_pix -min 0.000 [get_ports reset_pix]
set_output_delay -clock clk_sys -max 2.000 [get_ports {uart_tx paused fault}]
set_output_delay -clock clk_sys -min 0.000 [get_ports {uart_tx paused fault}]
set_output_delay -clock clk_pix -max 2.000 [get_ports {red* green* blue* hsync_n vsync_n}]
set_output_delay -clock clk_pix -min 0.000 [get_ports {red* green* blue* hsync_n vsync_n}]
