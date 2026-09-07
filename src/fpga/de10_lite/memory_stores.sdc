# Raw-store timing proof with virtual service ports, not physical board I/O.
create_clock -name clk_sys -period 40.000 [get_ports clk_sys]
derive_clock_uncertainty
set_input_delay -clock clk_sys -max 2.000 [get_ports {reset_sys core_reset access_read access_write access_store* access_address* access_wdata* host_read host_write host_offset* host_wdata* ppu_vram_read ppu_vram_address* ppu_oam_read ppu_oam_pair* wave_read wave_address* oam_request*}]
set_input_delay -clock clk_sys -min 0.000 [get_ports {reset_sys core_reset access_read access_write access_store* access_address* access_wdata* host_read host_write host_offset* host_wdata* ppu_vram_read ppu_vram_address* ppu_oam_read ppu_oam_pair* wave_read wave_address* oam_request*}]
set_output_delay -clock clk_sys -max 2.000 [all_outputs]
set_output_delay -clock clk_sys -min 0.000 [all_outputs]
