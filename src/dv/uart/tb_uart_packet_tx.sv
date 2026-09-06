`timescale 1ns/1ps
`default_nettype none
module tb_uart_packet_tx;
    import n2m_uart_pkg::*;
    logic clk_sys, reset_sys, transmit_valid, transmit_done, transmit_read;
    logic [UART_ADDRESS_BITS-1:0] transmit_bytes, transmit_address;
    logic [7:0] transmit_data, byte_data;
    logic transmit_data_valid, byte_valid, byte_ready, tx_pin;
    logic [7:0] raw [0:267];
    logic [7:0] expected [0:270];
    integer expected_size, accepted, replies, reads, busy_edges;
    bit corrupt, missing;
    n2m_uart_packet_tx dut (.*);
    // Actual serial ownership makes ready fall at acceptance and rise only
    // after all ten cells. Faster legal parameters keep this packet test small.
    n2m_uart_tx #(.CLOCK_HZ(64), .BAUD(8)) serial (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .byte_valid(byte_valid),
        .byte_data(byte_data), .byte_ready(byte_ready), .uart_tx(tx_pin)
    );
    always #5 clk_sys = !clk_sys;
    always @(posedge clk_sys) begin
        transmit_data_valid <= !reset_sys && transmit_read && !missing;
        if (transmit_read) begin
            transmit_data <= raw[transmit_address];
            reads = reads + 1;
        end
        if (!reset_sys && byte_valid && byte_ready) begin
            if (accepted >= expected_size || byte_data !== expected[accepted])
                $fatal(1, "UART_PACKET_TX_BYTE index=%0d expected=%02h actual=%02h", accepted, expected[accepted], byte_data);
            accepted = accepted + 1;
        end
        if (!reset_sys && !byte_ready) busy_edges = busy_edges + 1;
        if (!reset_sys && transmit_done) begin
            if (!byte_ready || !tx_pin || accepted != expected_size)
                $fatal(1, "UART_PACKET_TX_EARLY_DONE accepted=%0d expected=%0d", accepted, expected_size);
            replies = replies + 1;
        end
    end

    // Build expected COBS independently in a flat byte vector. Code bytes are
    // reserved then backfilled, unlike DUT scan/reread state and pointer logic.
    task automatic encode_expected(input integer size);
        integer source_index, output_index, code_index, code;
        output_index = 1; code_index = 0; code = 1;
        for (source_index = 0; source_index < size; source_index = source_index + 1) begin
            if (raw[source_index] == 0) begin
                expected[code_index] = 8'(code);
                code_index = output_index; output_index = output_index + 1; code = 1;
            end else begin
                expected[output_index] = raw[source_index]; output_index = output_index + 1; code = code + 1;
                if (code == 255) begin
                    expected[code_index] = 255; code_index = output_index;
                    output_index = output_index + 1; code = 1;
                end
            end
        end
        expected[code_index] = 8'(code);
        expected[output_index] = 0;
        expected_size = output_index + 1;
    endtask

    task automatic send_response(input integer size);
        integer cycles, before_replies, before_busy;
        encode_expected(size); accepted = 0; before_replies = replies; before_busy = busy_edges;
        @(negedge clk_sys); transmit_bytes = UART_ADDRESS_BITS'(size); transmit_valid = 1;
        cycles = 0;
        while (!transmit_done && cycles < 40000) begin
            @(negedge clk_sys); cycles = cycles + 1;
            if (corrupt && byte_valid && accepted == 1) force dut.byte_data = 8'h00;
        end
        if (!transmit_done) $fatal(1, "UART_PACKET_TX_TIMEOUT");
        @(posedge clk_sys); #1; transmit_valid = 0;
        if (replies != before_replies + 1 || busy_edges - before_busy != expected_size * 80)
            $fatal(1, "UART_PACKET_TX_STOP_BOUND replies=%0d busy=%0d expected=%0d", replies, busy_edges - before_busy, expected_size * 80);
        repeat (3) @(negedge clk_sys);
        if (byte_valid || transmit_done || !byte_ready) $fatal(1, "UART_PACKET_TX_IDLE");
    endtask

    initial begin
        integer index, pattern, cancel, cycles, before_replies;
        clk_sys = 0; reset_sys = 1; transmit_valid = 0; transmit_bytes = 0;
        transmit_data = 0; transmit_data_valid = 0;
        expected_size = 0; accepted = 0; replies = 0; reads = 0; busy_edges = 0;
        corrupt = $test$plusargs("corrupt"); missing = $test$plusargs("missing");
        $dumpfile("waves.vcd");
        $dumpvars(0, reset_sys, transmit_valid, transmit_bytes, transmit_done,
            transmit_read, transmit_address, transmit_data, transmit_data_valid,
            byte_valid, byte_data, byte_ready, tx_pin, expected_size, accepted, replies);
        repeat (3) @(negedge clk_sys); reset_sys = 0;
        for (pattern = 0; pattern < 5; pattern = pattern + 1) begin
            for (index = 0; index < 268; index = index + 1) begin
                case (pattern)
                    0: raw[index] = 0;
                    1: raw[index] = 8'hA7;
                    2: raw[index] = 8'(index);
                    3: raw[index] = index == 254 ? 0 : 8'h63;
                    4: raw[index] = index == 267 ? 0 : 8'h12;
                    default: raw[index] = 0;
                endcase
            end
            send_response(268);
        end
        for (index = 0; index < 268; index = index + 1) raw[index] = 8'h5E;
        send_response(12); send_response(254); send_response(255);
        // Cancel during scan, after a code, and during the last data byte.
        // Only public read/accepted-byte boundaries select the reset instant.
        for (cancel = 0; cancel < 3; cancel = cancel + 1) begin
            encode_expected(12); accepted = 0; before_replies = replies;
            @(negedge clk_sys); transmit_bytes = 12; transmit_valid = 1;
            cycles = 0;
            while ((cancel == 0 ? !transmit_read : accepted < (cancel == 1 ? 1 : expected_size - 1)) && cycles < 2000) begin
                @(negedge clk_sys); cycles = cycles + 1;
            end
            if (cycles == 2000) $fatal(1, "UART_PACKET_TX_RESET_SETUP");
            #2; reset_sys = 1; transmit_valid = 0; #1;
            if (byte_valid || transmit_read || transmit_done || tx_pin !== 1'b1)
                $fatal(1, "UART_PACKET_TX_RESET_CANCEL");
            repeat (3) @(negedge clk_sys); reset_sys = 0;
            repeat (3) @(negedge clk_sys);
            if (replies != before_replies) $fatal(1, "UART_PACKET_TX_CANCEL_REPLY");
            send_response(12);
        end
        if (replies != 11) $fatal(1, "UART_PACKET_TX_COUNTS");
        $display("PASS UART packet TX replies=11 resets=3 COBS zero 254 max serial_stop reads=%0d", reads);
        $finish;
    end
    initial begin
        #3000000;
        $fatal(1, "UART_PACKET_TX_WATCHDOG");
    end
endmodule
`default_nettype wire
