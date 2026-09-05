# Deliberate invalid constraint: proving failure is distinct from passing timing.
create_clock -name clk -period -1.000 [get_ports clk]
