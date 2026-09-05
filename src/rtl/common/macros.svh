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

`endif
