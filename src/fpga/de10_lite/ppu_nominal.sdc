create_clock -name clk_sys -period 20.000 [get_ports clk_sys]
derive_pll_clocks
derive_clock_uncertainty
set_input_delay -clock clk_sys -max 2.000 [get_ports {board_reset_n core_reset pause_request}]
set_input_delay -clock clk_sys -min 0.000 [get_ports {board_reset_n core_reset pause_request}]
set_input_delay -clock clk_sys -max 2.000 [get_ports {io_commit io_write io_address* io_wdata* vram_data* vram_valid oam_data* oam_valid dma_active}]
set_input_delay -clock clk_sys -min 0.000 [get_ports {io_commit io_write io_address* io_wdata* vram_data* vram_valid oam_data* oam_valid dma_active}]
