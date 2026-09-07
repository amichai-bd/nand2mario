// Hardware fault lifetime; separate normal target requires the named assertion.
`define SYNTHESIS
`include "src/rtl/input/n2m_button_filter.sv"
`include "src/rtl/input/n2m_adc_pairs.sv"
`include "src/rtl/input/n2m_controls_mask.sv"
`include "src/rtl/input/n2m_physical_controls.sv"
`include "src/rtl/input/n2m_input.sv"
`include "src/dv/input/tb_controls_lifecycle.sv"
`undef SYNTHESIS
