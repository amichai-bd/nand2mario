# RTL check

- Contract and edge cases linked
- Ownership map and RTL MAS aligned with source, tests, and evidence
- Clock and reset behavior explicit
- Widths and signedness explicit
- Sequential and combinational logic complete
- Crossings use an approved structure
- Assertions and directed tests updated
- Exact compile and simulation results recorded
- Shared synchronous/asynchronous register macros used; each raw block has a reviewed inference reason
- Named assertion macros follow argument order, prior-edge control and reset/history rules
- Assertion fatal negative and synthesis exclusion proven; names/attributes/initializers preserved
