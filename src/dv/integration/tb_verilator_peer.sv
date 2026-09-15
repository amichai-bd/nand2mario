`timescale 1ns/1ps
`default_nettype none
// Unit fixture for the Verilator peer: the tb_integration mailboxes and
// completion path without product RTL. A byte endpoint answers each request
// with every byte inverted by 0x5a and a terminating zero, so the Python peer
// can check the round trip. dot_count advances once per system clock.
module tb_verilator_peer;
    logic clk_sys;
    logic [63:0] dot_count;
    logic [63:0] simulation_ns;
    logic [7:0] tx_bytes [0:271];
    logic [7:0] rx_bytes [0:271];
    integer tx_count, rx_count, transactions;
    logic tx_go, tx_busy, rx_done, finish_request;
    bit echo_fault;
    always #20 clk_sys = !clk_sys;
    always @(posedge clk_sys) begin
        simulation_ns = $time;
        dot_count = dot_count + 1;
    end

    initial begin : endpoint
        integer i;
        forever begin
            wait(tx_go);
            tx_go = 0; tx_busy = 1;
            if (tx_count < 1 || tx_count > 271) $fatal(1, "PEER_TX_SIZE");
            repeat(8) @(negedge clk_sys);
            for (i = 0; i < tx_count; i = i + 1) begin
                rx_bytes[i] = tx_bytes[i] ^ 8'h5a;
                @(negedge clk_sys);
            end
            transactions = transactions + 1;
            // The deliberate fault ends the run inside the second transaction,
            // as an owner check would, while the peer is waiting for the reply.
            if (echo_fault && transactions == 2) $fatal(1, "PEER_ECHO_FAULT seq=2");
            rx_bytes[tx_count] = 8'h00;
            rx_count = tx_count + 1;
            rx_done = 1;
            @(negedge clk_sys);
            tx_busy = 0;
        end
    end

    always @(posedge clk_sys) begin
        #1;
        if (finish_request) begin
            if (dot_count < 64'd136280) $fatal(1, "PEER_FINISH_EARLY dot=%0d", dot_count);
            $display("PASS verilator-peer transactions=%0d", transactions);
            $finish;
        end
    end

    initial begin
        clk_sys = 0; dot_count = 0; simulation_ns = 0;
        tx_count = 0; rx_count = 0; transactions = 0;
        tx_go = 0; tx_busy = 0; rx_done = 0; finish_request = 0;
        echo_fault = $test$plusargs("echo_fault");
    end
    // 136280 dots at 25 MHz take 5.45 ms; the watchdog bounds a stalled peer.
    initial begin #20000000; $fatal(1, "PEER_TIMEOUT"); end
endmodule
