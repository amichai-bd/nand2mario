`timescale 1ns/1ps
module tb_uart_serial;
    import n2m_interfaces_pkg::*;
    import n2m_uart_pkg::*;
    logic clk;
    logic reset;
    logic tx_valid;
    logic [7:0] tx_data;
    logic tx_ready;
    logic tx_pin;
    logic loopback;
    logic manual_rx;
    logic rx_pin;
    logic rx_valid;
    logic [7:0] rx_data;
    logic rx_error;
    logic expected_pending;
    logic [7:0] expected_byte;
    integer received;
    integer frame_errors;
    integer pin_samples;
    logic corrupt;
    logic packet_request_valid;
    packet_header_t packet_header;
    logic [UART_ADDRESS_BITS-1:0] packet_bytes;
    logic packet_done;
    logic packet_read;
    logic [UART_ADDRESS_BITS-1:0] packet_address;
    logic [7:0] packet_data;
    logic packet_data_valid;
    logic previous_packet_valid;
    integer packet_accepted;
    logic [111:0] wire_vector;
    logic [95:0] raw_vector;
    assign rx_pin = loopback ? tx_pin : manual_rx;
    n2m_uart_tx tx (
        .clk_sys(clk), .reset_sys(reset), .byte_valid(tx_valid),
        .byte_data(tx_data), .byte_ready(tx_ready), .uart_tx(tx_pin)
    );
    n2m_uart_rx rx (
        .clk_sys(clk), .reset_sys(reset), .uart_rx(rx_pin),
        .byte_valid(rx_valid), .byte_data(rx_data), .frame_error(rx_error)
    );
    n2m_uart_packet_rx packets (
        .clk_sys(clk), .reset_sys(reset), .rx_valid(rx_valid), .rx_data(rx_data),
        .rx_error(rx_error), .request_valid(packet_request_valid),
        .request_header(packet_header), .request_bytes(packet_bytes),
        .request_done(packet_done), .packet_read(packet_read),
        .packet_address(packet_address), .packet_data(packet_data),
        .packet_data_valid(packet_data_valid)
    );
    always #10 clk = !clk;
    always @(posedge clk) begin
        if (reset) previous_packet_valid = 1'b0;
        if (!reset) begin
            if (packet_request_valid && !previous_packet_valid)
                packet_accepted = packet_accepted + 1;
            previous_packet_valid = packet_request_valid;
            if (rx_error) frame_errors = frame_errors + 1;
            if (rx_valid) begin
                if (!expected_pending || rx_data !== expected_byte)
                    $fatal(1, "UART_SERIAL_RECEIVED expected=%02h actual=%02h pending=%b", expected_byte, rx_data, expected_pending);
                received = received + 1;
                expected_pending = 1'b0;
            end
        end
    end

    task automatic send_and_check(input logic [7:0] value);
        integer cycle;
        integer position;
        integer count_before;
        logic expected_level;
        count_before = received;
        @(negedge clk);
        if (!tx_ready) $fatal(1, "UART_SERIAL_NOT_READY");
        expected_pending = 1'b1;
        expected_byte = value;
        tx_data = value;
        tx_valid = 1'b1;
        @(posedge clk);
        #1;
        tx_valid = 1'b0;
        // Literal independent rational-rate oracle, including every clock
        // of the start/data/stop cells, not a second UART decoding loopback.
        for (cycle = 0; cycle < 4341; cycle = cycle + 1) begin
            // Queue the next byte while busy and hold it through acceptance.
            if (value == 0 && cycle == 100) begin
                tx_valid = 1'b1;
                tx_data = 1;
            end
            position = (cycle * 115200) / 50000000;
            if (position == 0) expected_level = 1'b0;
            else if (position == 9) expected_level = 1'b1;
            else expected_level = value[position-1];
            if (corrupt && cycle == 12) force tx.uart_tx = 1'b1;
            if (tx_pin !== expected_level || tx_ready)
                $fatal(1, "UART_SERIAL_TX_BIT cycle=%0d bit=%0d expected=%b actual=%b ready=%b", cycle, position, expected_level, tx_pin, tx_ready);
            pin_samples = pin_samples + 1;
            @(posedge clk);
            #1;
        end
        if (!tx_ready || !tx_pin || received != count_before + 1)
            $fatal(1, "UART_SERIAL_BYTE_END ready=%b pin=%b received=%0d", tx_ready, tx_pin, received);
    endtask

    task automatic send_packet(input logic broken_stop);
        integer index;
        for (index = 0; index < 14; index = index + 1) begin
            expected_byte = wire_vector[index*8 +: 8];
            expected_pending = !(broken_stop && index == 5);
            manual_byte(expected_byte, expected_pending);
        end
    endtask

    task automatic check_packet;
        integer index;
        integer cycles;
        cycles = 0;
        while (!packet_request_valid && cycles < 1000) begin
            @(negedge clk);
            cycles = cycles + 1;
        end
        if (!packet_request_valid || packet_bytes != 12 || packet_header !== raw_vector[79:0])
            $fatal(1, "UART_SERIAL_PACKET_HEADER valid=%b bytes=%0d header=%h", packet_request_valid, packet_bytes, packet_header);
        for (index = 0; index < 12; index = index + 1) begin
            packet_read = 1'b1;
            packet_address = UART_ADDRESS_BITS'(index);
            @(posedge clk);
            #1;
            if (!packet_data_valid || packet_data !== raw_vector[index*8 +: 8])
                $fatal(1, "UART_SERIAL_PACKET_BYTE index=%0d expected=%02h actual=%02h", index, raw_vector[index*8 +: 8], packet_data);
            @(negedge clk);
        end
        packet_read = 1'b0;
        packet_done = 1'b1;
        @(negedge clk);
        packet_done = 1'b0;
    endtask

    task automatic manual_byte(input logic [7:0] value, input logic good_stop);
        integer bit_index;
        manual_rx = 1'b0;
        #8680.555556;
        for (bit_index = 0; bit_index < 8; bit_index = bit_index + 1) begin
            manual_rx = value[bit_index];
            #8680.555556;
        end
        manual_rx = good_stop;
        #8680.555556;
        manual_rx = 1'b1;
        #17361.111112;
    endtask

    initial begin
        integer value;
        integer bit_index;
        integer phase;
        clk = 1'b0;
        reset = 1'b1;
        tx_valid = 1'b0;
        tx_data = 0;
        loopback = 1'b1;
        manual_rx = 1'b1;
        expected_pending = 1'b0;
        expected_byte = 0;
        received = 0;
        frame_errors = 0;
        pin_samples = 0;
        corrupt = $test$plusargs("corrupt");
        packet_done = 1'b0;
        packet_read = 1'b0;
        packet_address = '0;
        previous_packet_valid = 1'b0;
        packet_accepted = 0;
        // Literal PING seq12345678: independently cross-checked with host codec.
        raw_vector = 96'h745800000001123456780001;
        wire_vector = 112'h0074580301010112345678060102;
        $dumpfile("waves.vcd");
        $dumpvars(0, reset, tx_valid, tx_data, tx_ready, tx_pin, rx_pin,
            rx_valid, rx_data, rx_error, expected_pending, expected_byte,
            received, frame_errors, packet_request_valid, packet_header,
            packet_bytes, packet_done, packet_read, packet_address, packet_data,
            packet_data_valid, packet_accepted);
        repeat (3) @(negedge clk);
        reset = 1'b0;
        for (value = 0; value < 256; value = value + 1)
            send_and_check(8'(value));
        @(negedge clk);
        loopback = 1'b0;
        manual_rx = 1'b1;
        repeat (8) @(negedge clk);
        manual_rx = 1'b0;
        @(negedge clk);
        manual_rx = 1'b1;
        repeat (600) @(negedge clk);
        if (received != 256 || frame_errors != 0)
            $fatal(1, "UART_SERIAL_FALSE_START");
        for (phase = 1; phase <= 19; phase = phase + 6) begin
            #(phase);
            expected_pending = 1'b1;
            expected_byte = 8'(phase) ^ 8'h9c;
            manual_byte(expected_byte, 1'b1);
        end
        manual_byte(8'h55, 1'b0);
        if (received != 260 || frame_errors != 1)
            $fatal(1, "UART_SERIAL_BAD_STOP received=%0d errors=%0d", received, frame_errors);
        loopback = 1'b1;
        for (bit_index = 0; bit_index < 10; bit_index = bit_index + 1) begin
            @(negedge clk);
            tx_data = 8'ha5;
            tx_valid = 1'b1;
            @(posedge clk);
            #1;
            tx_valid = 1'b0;
            repeat (bit_index * 434 + 100) @(negedge clk);
            #3;
            reset = 1'b1;
            #1;
            if (tx_pin !== 1'b1 || rx_valid || rx_error)
                $fatal(1, "UART_SERIAL_ASYNC_RESET bit=%0d", bit_index);
            repeat (3) @(negedge clk);
            reset = 1'b0;
            repeat (6) @(negedge clk);
        end
        send_and_check(8'ha6);
        if (received != 261 || frame_errors != 1)
            $fatal(1, "UART_SERIAL_COUNTS received=%0d errors=%0d", received, frame_errors);
        @(negedge clk);
        reset = 1'b1;
        loopback = 1'b0;
        manual_rx = 1'b1;
        repeat (3) @(negedge clk);
        reset = 1'b0;
        send_packet(1'b0);
        check_packet();
        send_packet(1'b1);
        repeat (1000) @(negedge clk);
        if (packet_request_valid || packet_accepted != 1)
            $fatal(1, "UART_SERIAL_BAD_STOP_PACKET accepted=%0d valid=%b", packet_accepted, packet_request_valid);
        send_packet(1'b0);
        check_packet();
        if (packet_accepted != 2 || received != 302 || frame_errors != 2)
            $fatal(1, "UART_SERIAL_FINAL_COUNTS packets=%0d received=%0d errors=%0d", packet_accepted, received, frame_errors);
        $display("PASS UART serial bytes=%0d errors=%0d packets=%0d reset_bits=10 pin_samples=%0d", received, frame_errors, packet_accepted, pin_samples);
        $finish;
    end
    initial begin
        #35000000;
        $fatal(1, "UART_SERIAL_WATCHDOG");
    end
endmodule
