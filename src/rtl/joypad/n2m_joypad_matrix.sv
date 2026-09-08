`timescale 1ns/1ps
`default_nettype none

module n2m_joypad_matrix (
    input var logic [7:0] buttons,
    input var logic [1:0] select_bits,
    output logic [7:0] read_data,
    output logic selected_active
);
    logic [3:0] directions, actions, pressed;
    assign directions = {|(buttons & n2m_interfaces_pkg::BUTTON_DOWN), |(buttons & n2m_interfaces_pkg::BUTTON_UP),
        |(buttons & n2m_interfaces_pkg::BUTTON_LEFT), |(buttons & n2m_interfaces_pkg::BUTTON_RIGHT)};
    assign actions = {|(buttons & n2m_interfaces_pkg::BUTTON_START), |(buttons & n2m_interfaces_pkg::BUTTON_SELECT),
        |(buttons & n2m_interfaces_pkg::BUTTON_B), |(buttons & n2m_interfaces_pkg::BUTTON_A)};
    assign pressed = (select_bits[0] ? 4'd0 : directions) |
        (select_bits[1] ? 4'd0 : actions);
    assign read_data = {2'b11, select_bits, ~pressed};
    assign selected_active = |pressed;
endmodule
