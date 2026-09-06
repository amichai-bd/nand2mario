`timescale 1ns/1ps
module tb_uart_exchange;
    import n2m_interfaces_pkg::*;
    import n2m_uart_pkg::*;
    logic clk;
    logic reset;
    logic request_valid;
    packet_header_t request_header;
    logic [UART_ADDRESS_BITS-1:0] request_bytes;
    logic request_done;
    logic packet_read;
    logic [UART_ADDRESS_BITS-1:0] packet_address;
    logic [7:0] packet_data;
    logic packet_data_valid;
    logic command_valid;
    logic [7:0] forced_status;
    logic command_packet_read;
    logic [UART_ADDRESS_BITS-1:0] command_packet_address;
    logic response_write;
    logic [UART_ADDRESS_BITS-1:0] response_address;
    logic [7:0] response_data;
    logic command_done;
    logic [UART_ADDRESS_BITS-1:0] response_bytes;
    logic transmit_valid;
    logic [UART_ADDRESS_BITS-1:0] transmit_bytes;
    logic transmit_read;
    logic [UART_ADDRESS_BITS-1:0] transmit_address;
    logic [7:0] transmit_data;
    logic transmit_data_valid;
    logic transmit_done;
    logic core_reset_effect;
    byte unsigned request [0:267];
    byte unsigned expected [0:267];
    byte unsigned cached [0:267];
    integer expected_size;
    integer cached_size;
    integer effects;
    integer dispatched;
    integer replies;
    integer bytes_checked;
    logic corrupt;
    logic duplicate;

    n2m_uart_exchange dut (
        .clk_sys(clk), .reset_sys(reset), .request_valid(request_valid),
        .request_header(request_header), .request_bytes(request_bytes),
        .request_done(request_done), .packet_read(packet_read),
        .packet_address(packet_address), .packet_data(packet_data),
        .packet_data_valid(packet_data_valid), .command_valid(command_valid),
        .command_forced_status(forced_status), .command_packet_read(command_packet_read),
        .command_packet_address(command_packet_address), .response_write(response_write),
        .response_address(response_address), .response_data(response_data),
        .command_done(command_done), .response_bytes(response_bytes),
        .transmit_valid(transmit_valid), .transmit_bytes(transmit_bytes),
        .transmit_read(transmit_read), .transmit_address(transmit_address),
        .transmit_data(transmit_data), .transmit_data_valid(transmit_data_valid),
        .transmit_done(transmit_done)
    );
    always #5 clk = !clk;

    // Original one-edge packet-source fixture; the actual three cache/staging
    // stores inside the DUT use the installed Intel model, never these arrays.
    always @(posedge clk) begin
        packet_data_valid <= !reset && packet_read;
        if (!reset && packet_read) begin
            if (packet_address >= request_bytes)
                $fatal(1, "UART_EXCHANGE_SOURCE_RANGE address=%0d size=%0d", packet_address, request_bytes);
            packet_data <= request[packet_address];
        end
        if (!reset && command_done && command_valid) begin
            dispatched = dispatched + 1;
            if (forced_status == 0) effects = effects + 1;
        end
        if (!reset && request_done) replies = replies + 1;
    end

    task automatic finish_request_crc;
        logic [15:0] value;
        logic feedback;
        integer octet;
        integer bit_index;
        value = 16'hffff;
        for (octet = 0; octet < int'(request_bytes)-2; octet = octet + 1)
            for (bit_index = 7; bit_index >= 0; bit_index = bit_index - 1) begin
                feedback = value[15] ^ request[octet][bit_index];
                value = {value[14:0], 1'b0};
                if (feedback) value = value ^ 16'h1021;
            end
        request[request_bytes-2] = value[7:0];
        request[request_bytes-1] = value[15:8];
    endtask

    task automatic make_request(input logic [31:0] sequence,
                                input integer count, input logic [7:0] salt);
        integer index;
        request_header = '0;
        request_header.version = 1;
        request_header.seq = sequence;
        request_header.command = COMMAND_INPUT;
        request_header.length = 16'(count-12);
        request_bytes = UART_ADDRESS_BITS'(count);
        for (index = 0; index < count; index = index + 1)
            request[index] = 8'(index) ^ salt;
        for (index = 0; index < 10; index = index + 1)
            request[index] = request_header[index*8 +: 8];
        finish_request_crc();
    endtask

    task automatic wait_command_or_reply;
        integer cycles;
        cycles = 0;
        while (!command_valid && !transmit_valid && cycles < 2000) begin
            @(negedge clk);
            cycles = cycles + 1;
        end
        if (cycles == 2000) $fatal(1, "UART_EXCHANGE_DISPATCH_TIMEOUT");
    endtask

    task automatic exchange(input logic execute, input logic [7:0] status,
                            input integer reply_size, input logic [7:0] salt);
        integer index;
        integer cycles;
        integer old_effects;
        integer old_dispatched;
        old_effects = effects;
        old_dispatched = dispatched;
        @(negedge clk);
        request_valid = 1'b1;
        wait_command_or_reply();
        if (!execute && duplicate) force dut.command_valid = 1'b1;
        #1;
        if (!execute && command_valid)
            $fatal(1, "UART_EXCHANGE_DUPLICATE_EXECUTION seq=%h", request_header.seq);
        if (execute && (!command_valid || forced_status !== status))
            $fatal(1, "UART_EXCHANGE_STATUS expected=%h actual=%h command=%b", status, forced_status, command_valid);
        if (execute) begin
            expected_size = reply_size;
            for (index = 0; index < reply_size; index = index + 1)
                expected[index] = 8'(index) ^ salt;
            // Distinguishable response bytes are driven by an independent
            // executor fixture; their command semantics are tested elsewhere.
            for (index = 0; index < reply_size; index = index + 1) begin
                @(negedge clk);
                response_write = 1'b1;
                response_address = UART_ADDRESS_BITS'(index);
                response_data = expected[index];
                if (transmit_valid) $fatal(1, "UART_EXCHANGE_PREMATURE_REPLY");
            end
            @(negedge clk);
            response_write = 1'b0;
            response_bytes = UART_ADDRESS_BITS'(reply_size);
            command_done = 1'b1;
            core_reset_effect = request_header.command == COMMAND_RESET && status == 0;
            @(negedge clk);
            command_done = 1'b0;
            core_reset_effect = 1'b0;
            if (status == 0) begin
                cached_size = expected_size;
                for (index = 0; index < expected_size; index = index + 1)
                    cached[index] = expected[index];
            end
        end else begin
            expected_size = cached_size;
            for (index = 0; index < cached_size; index = index + 1)
                expected[index] = cached[index];
        end
        cycles = 0;
        while (!transmit_valid && cycles < 2500) begin
            @(negedge clk);
            cycles = cycles + 1;
        end
        if (!transmit_valid || transmit_bytes != expected_size)
            $fatal(1, "UART_EXCHANGE_REPLY_SIZE expected=%0d actual=%0d", expected_size, transmit_bytes);
        repeat (7) @(negedge clk);
        if (request_done) $fatal(1, "UART_EXCHANGE_EARLY_RELEASE");
        for (index = 0; index < expected_size; index = index + 1) begin
            transmit_read = 1'b1;
            transmit_address = UART_ADDRESS_BITS'(index);
            if (corrupt && !execute && index == 2)
                force dut.stores.read_data = 24'h000000;
            @(posedge clk);
            #1;
            if (!transmit_data_valid || transmit_data !== expected[index])
                $fatal(1, "UART_EXCHANGE_REPLY_BYTE index=%0d expected=%02h actual=%02h valid=%b", index, expected[index], transmit_data, transmit_data_valid);
            bytes_checked = bytes_checked + 1;
            @(negedge clk);
        end
        transmit_read = 1'b0;
        repeat (3) @(negedge clk);
        transmit_done = 1'b1;
        #1;
        if (!request_done) $fatal(1, "UART_EXCHANGE_MISSING_RELEASE");
        @(negedge clk);
        transmit_done = 1'b0;
        request_valid = 1'b0;
        if (dispatched != old_dispatched + int'(execute) ||
            effects != old_effects + int'(execute && status == 0))
            $fatal(1, "UART_EXCHANGE_EFFECT_COUNTS dispatch=%0d effects=%0d", dispatched, effects);
    endtask

    initial begin
        clk = 1'b0;
        reset = 1'b1;
        request_valid = 1'b0;
        request_header = '0;
        request_bytes = '0;
        packet_data = 0;
        packet_data_valid = 1'b0;
        command_packet_read = 1'b0;
        command_packet_address = '0;
        response_write = 1'b0;
        response_address = '0;
        response_data = 0;
        command_done = 1'b0;
        response_bytes = '0;
        transmit_read = 1'b0;
        transmit_address = '0;
        transmit_done = 1'b0;
        core_reset_effect = 1'b0;
        effects = 0;
        dispatched = 0;
        replies = 0;
        bytes_checked = 0;
        corrupt = $test$plusargs("corrupt");
        duplicate = $test$plusargs("duplicate");
        $dumpfile("waves.vcd");
        $dumpvars(0, clk, reset, request_valid, request_header, request_bytes,
            request_done, packet_read, packet_address, packet_data, packet_data_valid,
            command_valid, forced_status, response_write, response_address, response_data,
            command_done, response_bytes, transmit_valid, transmit_bytes, transmit_read,
            transmit_address, transmit_data, transmit_data_valid, transmit_done,
            core_reset_effect, effects, dispatched, replies, bytes_checked);
        repeat (3) @(negedge clk);
        reset = 1'b0;
        make_request(1, 268, 8'h51);
        exchange(1, 0, 268, 8'h96);
        exchange(0, 0, 0, 0);
        // A final payload difference with a valid new CRC must not escape a
        // header-only comparator. These are intact decoded wire packets.
        request[265] = request[265] ^ 8'h01;
        finish_request_crc();
        exchange(1, 9, 12, 8'h3c);
        request[265] = request[265] ^ 8'h01;
        finish_request_crc();
        exchange(0, 0, 0, 0);
        make_request(1, 267, 8'h51);
        exchange(1, 9, 12, 8'h4c);
        make_request(1, 268, 8'h51);
        exchange(0, 0, 0, 0);
        make_request(2, 13, 8'h62);
        exchange(1, 0, 13, 8'ha5);
        make_request(1, 268, 8'h51);
        exchange(1, 0, 268, 8'h76);
        // A core RESET command remains an ordinary cached exchange.
        make_request(3, 12, 8'h73);
        request_header.command = COMMAND_RESET;
        request[6] = COMMAND_RESET;
        finish_request_crc();
        exchange(1, 0, 12, 8'h67);
        exchange(0, 0, 0, 0);
        make_request(32'hffffffff, 13, 8'h83);
        exchange(1, 0, 13, 8'h58);
        make_request(0, 13, 8'h94);
        exchange(1, 0, 13, 8'h49);
        exchange(0, 0, 0, 0);
        @(negedge clk);
        reset = 1'b1;
        #1;
        if (command_valid || transmit_valid || request_done)
            $fatal(1, "UART_EXCHANGE_RESET_VALID");
        repeat (3) @(negedge clk);
        reset = 1'b0;
        exchange(1, 0, 13, 8'h3a);
        if (effects != 7 || dispatched != 9 || replies != 14)
            $fatal(1, "UART_EXCHANGE_TOTALS effects=%0d dispatch=%0d replies=%0d", effects, dispatched, replies);
        $display("PASS UART exchange replies=%0d effects=%0d dispatch=%0d bytes=%0d replay sequence reset", replies, effects, dispatched, bytes_checked);
        $finish;
    end
    initial begin
        #2000000;
        $fatal(1, "UART_EXCHANGE_WATCHDOG");
    end
endmodule
