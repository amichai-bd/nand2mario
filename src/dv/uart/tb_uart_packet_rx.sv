`timescale 1ns/1ps
module tb_uart_packet_rx;
    import n2m_interfaces_pkg::*;
    import n2m_uart_pkg::*;
    logic clk;
    logic reset;
    logic rx_valid;
    logic [7:0] rx_data;
    logic rx_error;
    logic request_valid;
    packet_header_t header;
    logic [UART_ADDRESS_BITS-1:0] request_bytes;
    logic done;
    logic packet_read;
    logic [UART_ADDRESS_BITS-1:0] packet_address;
    logic [7:0] packet_data;
    logic packet_valid;
    byte unsigned raw [0:299];
    byte unsigned encoded [0:303];
    integer raw_size;
    integer encoded_size;
    integer accepted;
    integer checked_bytes;
    logic previous_valid;
    logic corrupt;
    logic bad_read;

    n2m_uart_packet_rx #(.CLOCK_HZ(1000)) dut (
        .clk_sys(clk), .reset_sys(reset), .rx_valid(rx_valid), .rx_data(rx_data), .rx_error(rx_error),
        .request_valid(request_valid), .request_header(header),
        .request_bytes(request_bytes), .request_done(done),
        .packet_read(packet_read), .packet_address(packet_address),
        .packet_data(packet_data), .packet_data_valid(packet_valid)
    );
    always #5 clk = !clk;
    always @(posedge clk) begin
        if (reset) previous_valid = 1'b0;
        else begin
            if (request_valid && !previous_valid) accepted = accepted + 1;
            previous_valid = request_valid;
        end
    end

    // Reference consumes literal wire bytes, never DUT decoded fields.
    function automatic logic [15:0] reference_crc(input integer count);
        logic [15:0] value;
        logic feedback;
        integer octet;
        integer bit_index;
        value = 16'hffff;
        for (octet = 0; octet < count; octet = octet + 1)
            for (bit_index = 7; bit_index >= 0; bit_index = bit_index - 1) begin
                feedback = value[15] ^ raw[octet][bit_index];
                value = {value[14:0], 1'b0};
                if (feedback) value = value ^ 16'h1021;
            end
        return value;
    endfunction

    task automatic encode;
        integer index;
        integer code_slot;
        integer code;
        code_slot = 0;
        code = 1;
        encoded_size = 1;
        for (index = 0; index < raw_size; index = index + 1) begin
            if (raw[index] == 0) begin
                encoded[code_slot] = 8'(code);
                code_slot = encoded_size;
                encoded_size = encoded_size + 1;
                code = 1;
            end else begin
                encoded[encoded_size] = raw[index];
                encoded_size = encoded_size + 1;
                code = code + 1;
                if (code == 255) begin
                    encoded[code_slot] = 255;
                    code_slot = encoded_size;
                    encoded_size = encoded_size + 1;
                    code = 1;
                end
            end
        end
        encoded[code_slot] = 8'(code);
    endtask

    task automatic make_packet(input integer payload, input logic [7:0] version,
                               input logic [7:0] kind, input logic [7:0] status);
        integer index;
        logic [15:0] checksum;
        raw[0] = version;
        raw[1] = kind;
        raw[2] = 8'h78;
        raw[3] = 8'h56;
        raw[4] = 8'h34;
        raw[5] = 8'h12;
        raw[6] = 8'h08;
        raw[7] = status;
        raw[8] = 8'(payload);
        raw[9] = 8'(payload >> 8);
        for (index = 0; index < payload; index = index + 1)
            raw[10 + index] = 8'(index);
        checksum = reference_crc(10 + payload);
        raw[10 + payload] = checksum[7:0];
        raw[11 + payload] = checksum[15:8];
        raw_size = 12 + payload;
        encode();
    endtask

    task automatic send_byte(input logic [7:0] value);
        @(negedge clk);
        rx_valid = 1'b1;
        rx_data = value;
        @(negedge clk);
        rx_valid = 1'b0;
    endtask

    task automatic send_frame;
        integer index;
        for (index = 0; index < encoded_size; index = index + 1)
            send_byte(encoded[index]);
        send_byte(0);
    endtask

    task automatic expect_silent(input integer old_count);
        repeat (1200) @(negedge clk);
        if (request_valid || accepted != old_count)
            $fatal(1, "UART_RX_UNEXPECTED_REQUEST expected=%0d actual=%0d", old_count, accepted);
    endtask

    task automatic check_request;
        integer count;
        integer index;
        count = 0;
        while (!request_valid && count < 2000) begin
            @(negedge clk);
            count = count + 1;
        end
        if (!request_valid || request_bytes != raw_size)
            $fatal(1, "UART_RX_REQUEST_SIZE expected=%0d actual=%0d valid=%b", raw_size, request_bytes, request_valid);
        if (header !== {raw[9],raw[8],raw[7],raw[6],raw[5],raw[4],raw[3],raw[2],raw[1],raw[0]})
            $fatal(1, "UART_RX_HEADER actual=%h", header);
        repeat (3) @(negedge clk);
        for (index = 0; index < raw_size; index = index + 1) begin
            packet_address = UART_ADDRESS_BITS'(index);
            packet_read = 1'b1;
            if (bad_read) packet_address = request_bytes;
            if (corrupt && index == 2) force dut.stores.decoded_read_data = 8'h00;
            @(posedge clk);
            #1;
            if (!packet_valid || packet_data !== raw[index])
                $fatal(1, "UART_RX_PACKET_BYTE index=%0d expected=%02h actual=%02h valid=%b", index, raw[index], packet_data, packet_valid);
            checked_bytes = checked_bytes + 1;
            @(negedge clk);
        end
        packet_read = 1'b0;
    endtask

    task automatic release_request;
        @(negedge clk);
        done = 1'b1;
        @(negedge clk);
        done = 1'b0;
    endtask

    initial begin
        integer index;
        integer old_count;
        logic [15:0] crc16;
        logic [31:0] crc32;
        clk = 1'b0;
        reset = 1'b1;
        rx_valid = 1'b0;
        rx_data = 0;
        rx_error = 1'b0;
        done = 1'b0;
        packet_read = 1'b0;
        packet_address = 0;
        accepted = 0;
        checked_bytes = 0;
        previous_valid = 1'b0;
        corrupt = $test$plusargs("corrupt");
        bad_read = $test$plusargs("bad_read");
        $dumpfile("waves.vcd");
        $dumpvars(0, clk, reset, rx_valid, rx_data, rx_error, request_valid, header,
            request_bytes, done, packet_read, packet_address, packet_data,
            packet_valid, accepted, checked_bytes);
        crc16 = 16'hffff;
        crc32 = 32'hffffffff;
        for (index = 0; index < 9; index = index + 1) begin
            raw[index] = 8'(49 + index);
            crc16 = crc16_byte(crc16, raw[index]);
            crc32 = crc32_byte(crc32, raw[index]);
        end
        if (reference_crc(9) != 16'h29b1 || crc16 != 16'h29b1 ||
            (crc32 ^ 32'hffffffff) != 32'hcbf43926)
            $fatal(1, "UART_CRC_KNOWN_VECTOR");
        repeat (3) @(negedge clk);
        reset = 1'b0;
        send_byte(0);
        make_packet(0, 1, 0, 0);
        send_frame();
        check_request();
        release_request();
        make_packet(256, 1, 0, 0);
        send_frame();
        check_request();
        old_count = accepted;
        // A complete busy frame is discarded without disturbing the request.
        send_frame();
        check_request();
        if (accepted != old_count) $fatal(1, "UART_RX_BUSY_REPEAT");
        // A busy frame suffix remains discarded after release.
        send_byte(5);
        release_request();
        send_byte(7);
        send_byte(0);
        expect_silent(old_count);
        make_packet(8, 2, 0, 0);
        send_frame();
        check_request();
        release_request();
        // An exact final 254-byte nonzero block permits either trailing form.
        make_packet(252, 1, 0, 0);
        for (index = 10; index < 262; index = index + 1) raw[index] = 1;
        raw[262] = 8'h5c;
        raw[263] = 8'h5d;
        if (reference_crc(262) != 16'h5d5c) $fatal(1, "UART_RX_LITERAL_BLOCK_CRC");
        encode();
        if (encoded[encoded_size-1] != 1) $fatal(1, "UART_RX_FINAL_CODE_FIXTURE");
        send_frame();
        check_request();
        release_request();
        encoded_size = encoded_size - 1;
        send_frame();
        check_request();
        release_request();
        // CRC-valid declared-length errors belong to dispatcher BAD_LENGTH.
        make_packet(1, 1, 0, 0);
        raw[8] = 2;
        crc16 = reference_crc(11);
        raw[11] = crc16[7:0];
        raw[12] = crc16[15:8];
        encode();
        send_frame();
        check_request();
        release_request();
        old_count = accepted;
        make_packet(8, 1, 1, 0);
        send_frame();
        expect_silent(old_count);
        make_packet(8, 1, 0, 1);
        send_frame();
        expect_silent(old_count);
        make_packet(8, 1, 0, 0);
        send_byte(encoded[0]);
        send_byte(encoded[1]);
        rx_error = 1'b1;
        @(negedge clk);
        rx_error = 1'b0;
        for (index = 2; index < encoded_size; index = index + 1)
            send_byte(encoded[index]);
        send_byte(0);
        expect_silent(old_count);
        raw[raw_size-1] = raw[raw_size-1] ^ 8'h01;
        encode();
        send_frame();
        expect_silent(old_count);
        send_byte(5);
        send_byte(1);
        send_byte(0);
        expect_silent(old_count);
        for (index = 0; index < 271; index = index + 1) send_byte(1);
        send_byte(0);
        expect_silent(old_count);
        send_byte(4);
        send_byte(2);
        repeat (510) @(negedge clk);
        make_packet(1, 1, 0, 0);
        send_frame();
        check_request();
        release_request();
        if (accepted != 7) $fatal(1, "UART_RX_ACCEPT_COUNT expected=7 actual=%0d", accepted);
        $display("PASS UART packet RX requests=%0d bytes=%0d CRC COBS max busy timeout", accepted, checked_bytes);
        $finish;
    end
    initial begin
        #2000000;
        $fatal(1, "UART_RX_WATCHDOG");
    end
endmodule
