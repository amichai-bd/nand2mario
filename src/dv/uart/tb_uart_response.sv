`timescale 1ns/1ps
`default_nettype none
module tb_uart_response;
    import n2m_uart_pkg::*;
    logic clk_sys, reset_sys, start, busy, done;
    logic [31:0] sequence_token;
    logic [7:0] command, status, payload_data, response_data;
    logic [15:0] payload_bytes;
    logic payload_valid, payload_ready, response_write;
    logic [UART_ADDRESS_BITS-1:0] response_address, response_bytes;
    logic read_enable;
    logic [UART_ADDRESS_BITS-1:0] read_address;
    logic [23:0] read_data;
    logic [2:0] read_valid;
    integer scenario, writes, payload_index, completed, reads;
    integer trace;
    bit corrupt;
    n2m_uart_response dut (.*);
    n2m_uart_exchange_store u_store (
        .clk_sys(clk_sys), .reset_sys(reset_sys),
        .write_enable({response_write, 2'b0}),
        .write_address({response_address, {2*UART_ADDRESS_BITS{1'b0}}}),
        .write_data({response_data, 16'b0}),
        .read_enable({read_enable, 2'b0}),
        .read_address({read_address, {2*UART_ADDRESS_BITS{1'b0}}}),
        .read_data(read_data), .read_valid(read_valid)
    );
    `include "src/dv/uart/response_expected.svh"
    always #5 clk_sys = !clk_sys;
    always @(posedge clk_sys) begin
        if (!reset_sys && response_write) begin
            if (response_address != writes || response_data !== expected_byte(scenario, writes))
                $fatal(1,"UART_RESPONSE_BYTE case=%0d index=%0d expected=%02h actual=%02h",scenario,writes,expected_byte(scenario,writes),response_data);
            $fdisplay(trace,"write,%0d,%0d,%02h",scenario,writes,response_data);
            writes = writes + 1;
        end
        if (!reset_sys && payload_ready && payload_valid) payload_index = payload_index + 1;
        if (!reset_sys && done) begin
            if (writes != (scenario == 1 ? 268 : 12) || response_bytes != writes || response_write)
                $fatal(1,"UART_RESPONSE_COMPLETION case=%0d writes=%0d size=%0d",scenario,writes,response_bytes);
            completed = completed + 1;
        end
    end
    task automatic launch;
        writes = 0; payload_index = 0;
        @(negedge clk_sys);
        sequence_token = scenario == 0 ? 32'h78563412 : (scenario == 1 ? 32'hfedcba98 : 32'hffffffff);
        command = scenario == 0 ? 1 : (scenario == 1 ? 10 : 6);
        status = scenario == 2 ? 8 : 0;
        payload_bytes = scenario == 1 ? 256 : 0;
        start = 1;
        @(negedge clk_sys); start = 0;
    endtask
    task automatic finish_response;
        integer clocks, offset, before_completed;
        before_completed = completed; clocks = 0;
        while (!done && clocks < 2000) begin
            @(negedge clk_sys); clocks = clocks + 1;
            // The executor stalls between bytes. Once presented, each byte is
            // accepted at the next edge; the payload source never guesses time.
            payload_valid = payload_ready && clocks % 3 != 0;
            payload_data = 8'(payload_index);
            if (corrupt && response_write && response_address == 10) force dut.response_data = 8'h00;
        end
        if (!done) $fatal(1,"UART_RESPONSE_TIMEOUT");
        payload_valid = 0;
        @(posedge clk_sys); #1;
        if (completed != before_completed + 1) $fatal(1,"UART_RESPONSE_DONE_COUNT");
        for (offset = 0; offset < writes; offset = offset + 1) begin
            @(negedge clk_sys); read_enable = 1; read_address = UART_ADDRESS_BITS'(offset);
            @(posedge clk_sys); #1;
            if (!read_valid[2] || read_data[23:16] !== expected_byte(scenario, offset))
                $fatal(1,"UART_RESPONSE_STORED case=%0d index=%0d",scenario,offset);
            reads = reads + 1;
            $fdisplay(trace,"read,%0d,%0d,%02h",scenario,offset,read_data[23:16]);
        end
        @(negedge clk_sys); read_enable = 0;
        repeat (3) @(negedge clk_sys);
        if (busy || done || response_write) $fatal(1,"UART_RESPONSE_IDLE");
    endtask
    initial begin
        integer cancel, target_address, before_completed;
        clk_sys = 0; reset_sys = 1; start = 0; sequence_token = 0;
        command = 0; status = 0; payload_bytes = 0; payload_valid = 0; payload_data = 0;
        read_enable = 0; read_address = 0; scenario = 0; writes = 0;
        payload_index = 0; completed = 0; reads = 0;
        corrupt = $test$plusargs("corrupt");
        trace = $fopen("response.csv","w");
        if (!trace) $fatal(1,"UART_RESPONSE_TRACE");
        $fdisplay(trace,"kind,case,index,data");
        $dumpfile("waves.vcd");
        $dumpvars(0,reset_sys,start,busy,done,sequence_token,command,status,
            payload_bytes,payload_valid,payload_ready,payload_data,response_write,
            response_address,response_data,response_bytes,read_enable,read_address,
            read_data,read_valid,writes,completed,reads);
        repeat (3) @(negedge clk_sys); reset_sys = 0;
        for (scenario = 0; scenario < 3; scenario = scenario + 1) begin
            launch(); finish_response();
        end
        // Global cancellation at header, held payload and CRC. Partial staged
        // bytes remain unpublished; a fresh reply overwrites through public A.
        for (cancel = 0; cancel < 3; cancel = cancel + 1) begin
            scenario = cancel == 1 ? 1 : 0; before_completed = completed;
            launch(); target_address = cancel == 0 ? 4 : (cancel == 1 ? 10 : 11);
            while (response_address != target_address) @(negedge clk_sys);
            #2; reset_sys = 1; payload_valid = 0; #1;
            if (response_write || done || busy) $fatal(1,"UART_RESPONSE_RESET_CANCEL");
            repeat (3) @(negedge clk_sys); reset_sys = 0;
            repeat (3) @(negedge clk_sys);
            if (completed != before_completed) $fatal(1,"UART_RESPONSE_RESET_DONE");
            scenario = 0; launch(); finish_response();
        end
        if (completed != 6 || reads != 328) $fatal(1,"UART_RESPONSE_COUNTS");
        $fclose(trace);
        $display("PASS UART response packets=6 bytes=328 resets=3 Intel_staging CRC16");
        $finish;
    end
    initial begin
        #100000;
        $fatal(1,"UART_RESPONSE_WATCHDOG");
    end
endmodule
`default_nettype wire
