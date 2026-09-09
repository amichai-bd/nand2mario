`timescale 1ns/1ps
module tb_uart_validation;
    logic [31:0] address;
    logic [31:0] data;
    logic address_valid;
    logic [7:0] endpoint_state;
    n2m_interfaces_pkg::snapshot_t metadata;
    n2m_interfaces_pkg::packet_header_t header;
    logic [8:0] packet_bytes;
    logic [71:0] arguments;
    logic [7:0] status;
    logic [15:0] response_length;
    logic [31:0] expected_data;
    logic expected_valid;
    logic corrupt;
    integer checks;
    integer byte_index;
    integer bit_index;
    logic [31:0] words [0:19];
    n2m_uart_host_registers u_host (
        .address(address), .endpoint_state(endpoint_state), .image_valid(1'b1), .profile(8'hA6),
        .dot_count(64'h1122334455667788), .retirement_count(64'h99AABBCCDDEEFF00),
        .buttons(8'h5A), .input_source(8'h01), .physical_buttons(8'hA5), .effective_buttons(8'h3C),
        .snapshot_valid(1'b1), .snapshot_metadata(metadata),
        .build_id(128'h0123456789ABCDEF13579BDF2468ACE0), .address_valid(address_valid), .data(data)
    );
    n2m_uart_validate u_validate (
        .header(header), .packet_bytes(packet_bytes), .arguments(arguments), .forced_status(8'h00),
        .endpoint_state(endpoint_state), .image_valid(1'b1), .snapshot_valid(1'b1),
        .host_address_valid(address_valid), .status(status), .response_length(response_length)
    );
    task automatic check_address(input logic [31:0] value, input logic valid_value, input logic [31:0] word_value);
        address = value; expected_valid = valid_value; expected_data = word_value;
        #1;
        if (corrupt && value == 32'h00010030) force data = 32'h0;
        #1;
        if (address_valid !== expected_valid || data !== expected_data)
            $fatal(1, "UART_HOST_VALUE address=%08x expected=%08x actual=%08x valid=%b/%b",
                address, expected_data, data, expected_valid, address_valid);
        checks = checks + 1;
    endtask
    task automatic check_reply(input logic [7:0] expected_status, input logic [15:0] expected_length);
        #1;
        if (status !== expected_status || response_length !== expected_length)
            $fatal(1, "UART_VALIDATE_LENGTH command=%02x expected=%02x/%0d actual=%02x/%0d",
                header.command, expected_status, expected_length, status, response_length);
        checks = checks + 1;
    endtask
    task automatic command_case(input logic [7:0] command_value, input logic [15:0] request_length,
                                input logic [15:0] expected_length);
        header.command = command_value; header.length = request_length;
        packet_bytes = 9'(request_length) + 9'd12;
        check_reply(8'h00, expected_length);
        packet_bytes = packet_bytes - 9'd1;
        check_reply(8'h03, 16'd0);
    endtask
    initial begin
        words = '{32'h1,32'h2,32'h1,32'hA6,32'h55667788,32'h11223344,32'hDDEEFF00,32'h99AABBCC,
                  32'h5A,32'h1,32'hABCDEF01,32'h23456789,32'h2468ACE0,32'h13579BDF,32'h89ABCDEF,
                  32'h01234567,32'hA5A6A7A8,32'h1,32'hA5,32'h3C};
        metadata = '0; metadata.seq = 64'h23456789ABCDEF01; metadata.epoch = 32'hA5A6A7A8;
        endpoint_state = 8'h02; header = '0; header.version = 8'h01; header.kind = 8'h01;
        packet_bytes = 9'd12; arguments = '0; checks = 0; address = 0;
        expected_data = 0; expected_valid = 0; corrupt = $test$plusargs("CORRUPT_HOST");
        $dumpfile("waves.vcd");
        $dumpvars(0, address, data, address_valid, expected_data, expected_valid, endpoint_state,
            header, packet_bytes, arguments, status, response_length, checks);
        // All bytes around the twenty literal aligned ABI addresses, then high aliases.
        for (byte_index = 0; byte_index < 80; byte_index = byte_index + 1)
            check_address(32'h00010000 + 32'(byte_index), byte_index % 4 == 0,
                          byte_index % 4 == 0 ? words[byte_index / 4] : 32'd0);
        for (bit_index = 17; bit_index < 32; bit_index = bit_index + 1)
            check_address(32'h00010000 | (32'd1 << bit_index), 1'b0, 32'd0);
        check_address(32'h00000000, 1'b0, 32'd0);
        check_address(32'hFFFFFFFF, 1'b0, 32'd0);
        check_address(32'hXXXXXXXX, 1'b0, 32'd0);
        address = 32'h00010000; endpoint_state = 8'h00;
        command_case(8'h01,16'd0,16'd4);
        command_case(8'h02,16'd4,16'd4);
        command_case(8'h05,16'd0,16'd8);
        arguments = 72'd1;
        command_case(8'h06,16'd4,16'd8);
        command_case(8'h0F,16'd4,16'd13);
        packet_bytes = 9'd16;
        arguments = 72'd70224; check_reply(8'h00,16'd13);
        arguments = 72'd0; check_reply(8'h04,16'd0);
        arguments = 72'd70225; check_reply(8'h04,16'd0);
        arguments = 72'd1; endpoint_state = 8'h01; check_reply(8'h05,16'd0);
        endpoint_state = 8'h02; check_reply(8'h05,16'd0);
        endpoint_state = 8'h00;
        command_case(8'h0B,16'd1,16'd8);
        command_case(8'h0C,16'd0,16'd24);
        arguments = '0; arguments[31:0] = 32'h00010020; arguments[63:32] = 32'h5A;
        command_case(8'h0E,16'd8,16'd8);
        address = 32'hDEADBEEF; header.command = 8'h02; header.length = 16'd4; packet_bytes = 9'd16;
        check_reply(8'h04,16'd0);
        if (checks != 120) $fatal(1, "UART_VALIDATE_COVERAGE");
        $display("PASS UART validation checks=%0d", checks); $finish;
    end
endmodule
