`timescale 1ns/1ps
`default_nettype none

// One DE2-115 seven-segment digit: four bits of hexadecimal onto the seven
// segment cathodes the board wires, active low.
//
// Segment order and polarity are board facts and are recorded once, with their
// vendor provenance, at wiki/src/de2-115-board.md#seven-segment-displays. Bit i
// of `segments_n` drives `HEXn[i]`, the board's own bit numbering, and the
// display's common anode means a segment lights when its cathode is driven low.
// So this module states the lit pattern and inverts it in one place; nothing
// else in the image knows the polarity.
module de2_hex_digit (
    input var logic [3:0] value,
    output logic [6:0] segments_n
);
    // Bit 0 is segment a (top) and bit 6 is segment g (middle), running
    // a, b, c, d, e, f, g. A 1 here is a lit segment.
    logic [6:0] lit;
    always_comb begin
        case (value)
            4'h0: lit = 7'h3f;
            4'h1: lit = 7'h06;
            4'h2: lit = 7'h5b;
            4'h3: lit = 7'h4f;
            4'h4: lit = 7'h66;
            4'h5: lit = 7'h6d;
            4'h6: lit = 7'h7d;
            4'h7: lit = 7'h07;
            4'h8: lit = 7'h7f;
            4'h9: lit = 7'h6f;
            4'ha: lit = 7'h77;
            // Lower-case b and d, so 8 and B and 0 and D stay distinguishable.
            4'hb: lit = 7'h7c;
            4'hc: lit = 7'h39;
            4'hd: lit = 7'h5e;
            4'he: lit = 7'h79;
            4'hf: lit = 7'h71;
            default: lit = 7'h00;
        endcase
    end
    assign segments_n = ~lit;
endmodule
`default_nettype wire
