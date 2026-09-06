// Compile the same product and fixture with hardware assertion exclusion.
// The normal targets separately require the named fatal service check.
`define SYNTHESIS
`include "src/rtl/common/n2m_intel_ram.sv"
`include "src/rtl/memory/n2m_memory_stores.sv"
`include "src/rtl/memory/n2m_memory_cpu_port.sv"
`include "src/dv/memory/tb_memory_cpu_port.sv"
`undef SYNTHESIS
