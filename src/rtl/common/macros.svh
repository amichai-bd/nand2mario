// Original register definitions. Contract: wiki/src/rtl-reference-style.md
`ifndef N2M_REGISTERS_SVH
`define N2M_REGISTERS_SVH

`define DFF(Q, D, CLK) \
    always_ff @(posedge CLK) Q <= (D);

`define DFF_RST(Q, D, CLK, RST) \
    always_ff @(posedge CLK) if (RST) Q <= '0; else Q <= (D);

`define DFF_RST_VAL(Q, D, CLK, RST, RESET_VAL) \
    always_ff @(posedge CLK) if (RST) Q <= (RESET_VAL); else Q <= (D);

`define DFF_EN(Q, D, CLK, EN) \
    always_ff @(posedge CLK) if (EN) Q <= (D);

`define DFF_RST_EN(Q, D, CLK, EN, RST, RESET_VAL) \
    always_ff @(posedge CLK) \
        if (RST) Q <= (RESET_VAL); else if (EN) Q <= (D);


// Explicit asynchronous reset polarity; reset has priority over the D input.
`define DFF_ARST_VAL(Q, D, CLK, RST, RESET_VAL) \
    always_ff @(posedge CLK or posedge RST) \
        if (RST) Q <= (RESET_VAL); else Q <= (D);

`define DFF_ARST_N_VAL(Q, D, CLK, RST_N, RESET_VAL) \
    always_ff @(posedge CLK or negedge RST_N) \
        if (!(RST_N)) Q <= (RESET_VAL); else Q <= (D);

// Explicit power-up initialization needs a second process. Questa rejects an
// initial writer alongside always_ff (vopt-7061), so only these forms use always.
`define DFF_INIT_ARST_VAL(Q, D, CLK, RST, RESET_VAL) \
    initial Q = (RESET_VAL); \
    always @(posedge CLK or posedge RST) \
        if (RST) Q <= (RESET_VAL); else Q <= (D);

`define DFF_INIT_ARST_N_VAL(Q, D, CLK, RST_N, RESET_VAL) \
    initial Q = (RESET_VAL); \
    always @(posedge CLK or negedge RST_N) \
        if (!(RST_N)) Q <= (RESET_VAL); else Q <= (D);

// Assertions are simulation checks, never synthesized circuitry.
`ifdef SYNTHESIS
`define N2M_ASSERT(NAME, CLK, RESET, PROPERTY)
`define N2M_ASSERT_NO_RST(NAME, CLK, PROPERTY)
`define N2M_ASSERT_NEVER(NAME, CLK, RESET, CONDITION)
`define N2M_ASSERT_KNOWN(NAME, CLK, RESET, SIGNAL)
`define N2M_ASSERT_STABLE_WHEN(NAME, CLK, RESET, HOLD, SIGNAL)
`else
`define N2M_ASSERT(NAME, CLK, RESET, PROPERTY) \
    NAME: assert property (@(posedge CLK) disable iff (RESET) (PROPERTY)) \
        else $fatal(1, "N2M_ASSERT %s instance=%m", `"NAME`");

`define N2M_ASSERT_NO_RST(NAME, CLK, PROPERTY) \
    NAME: assert property (@(posedge CLK) (PROPERTY)) \
        else $fatal(1, "N2M_ASSERT %s instance=%m", `"NAME`");

`define N2M_ASSERT_NEVER(NAME, CLK, RESET, CONDITION) \
    `N2M_ASSERT(NAME, CLK, RESET, !(CONDITION))

`define N2M_ASSERT_KNOWN(NAME, CLK, RESET, SIGNAL) \
    `N2M_ASSERT(NAME, CLK, RESET, !$isunknown(SIGNAL))

// HOLD at the prior edge controls the update observed now. A reset clears
// history asynchronously; the first subsequent sampled edge has no predecessor.
`define N2M_ASSERT_STABLE_WHEN(NAME, CLK, RESET, HOLD, SIGNAL) \
    logic NAME``_history; \
    `DFF_INIT_ARST_VAL(NAME``_history, 1'b1, CLK, RESET, 1'b0) \
    `N2M_ASSERT(NAME, CLK, RESET, (NAME``_history && $past(HOLD)) |-> $stable(SIGNAL))
`endif

`endif
