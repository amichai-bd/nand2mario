`timescale 1ns/1ps
`default_nettype none

module n2m_joypad_matrix (
    input var logic [7:0] buttons,
    input var logic [1:0] select_bits,
    output logic [7:0] read_data,
    output logic selected_active
);
    import n2m_interfaces_pkg::*;
    logic [3:0] directions, actions, pressed;
    assign directions = {|(buttons & BUTTON_DOWN), |(buttons & BUTTON_UP),
        |(buttons & BUTTON_LEFT), |(buttons & BUTTON_RIGHT)};
    assign actions = {|(buttons & BUTTON_START), |(buttons & BUTTON_SELECT),
        |(buttons & BUTTON_B), |(buttons & BUTTON_A)};
    assign pressed = (select_bits[0] ? 4'd0 : directions) |
        (select_bits[1] ? 4'd0 : actions);
    assign read_data = {2'b11, select_bits, ~pressed};
    assign selected_active = |pressed;
endmodule
