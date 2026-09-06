`timescale 1ns/1ps
`default_nettype none
module tb_snapshot;
    logic clk_sys, reset_sys, core_reset;
    logic observe_valid, observe_complete, observe_abort;
    logic [14:0] observe_index;
    logic [1:0] observe_shade;
    logic [31:0] observe_epoch;
    logic [63:0] observe_sequence, observe_dot;
    logic snapshot_request, snapshot_ready, snapshot_done, snapshot_ok, snapshot_valid;
    n2m_interfaces_pkg::snapshot_t snapshot_metadata;
    logic frame_read, frame_valid;
    logic [12:0] frame_address;
    logic [7:0] frame_data;
    integer pixel, byte_index, waited, checks;
    string wave_path;
    n2m_frame_snapshot dut (.*);
    task automatic edge_cycle;
        #5; clk_sys = 1;
        #1;
        #4; clk_sys = 0;
    endtask
    function automatic logic [1:0] shade(input integer index);
        return 2'((index / 160 + index % 160 + index / 7) % 4);
    endfunction
    function automatic logic [7:0] expected_byte(input integer index);
        return {shade(index * 4 + 3), shade(index * 4 + 2), shade(index * 4 + 1), shade(index * 4)};
    endfunction
    initial begin
        clk_sys = 0; reset_sys = 1; core_reset = 0;
        observe_valid = 0; observe_complete = 0; observe_abort = 0;
        observe_index = 0; observe_shade = 0; observe_epoch = 7;
        observe_sequence = 0; observe_dot = 0; snapshot_request = 0;
        frame_read = 0; frame_address = 0; checks = 0;
        if (!$value$plusargs("wave=%s", wave_path)) wave_path = "wave.vcd";
        $dumpfile(wave_path);
        $dumpvars(0, clk_sys, reset_sys, core_reset, observe_valid, observe_complete,
            observe_abort, observe_index, observe_shade, observe_epoch, observe_sequence,
            observe_dot, snapshot_request, snapshot_ready, snapshot_done, snapshot_ok,
            snapshot_valid, snapshot_metadata, frame_read, frame_address, frame_data, frame_valid);
        edge_cycle(); reset_sys = 0; edge_cycle();
        snapshot_request = 1; edge_cycle(); snapshot_request = 0;
        if (!snapshot_done || snapshot_ok || snapshot_valid) $fatal(1, "SNAPSHOT_NO_FRAME");
        edge_cycle();
        for (pixel = 0; pixel < 23040; pixel = pixel + 1) begin
            observe_valid = 1; observe_index = 15'(pixel); observe_shade = shade(pixel);
            observe_dot = 64'(pixel + 1); observe_complete = pixel == 23039;
            edge_cycle();
        end
        observe_valid = 0; observe_complete = 0;
        snapshot_request = 1; edge_cycle(); snapshot_request = 0;
        waited = 0;
        while (!snapshot_done && waited < 12000) begin edge_cycle(); waited = waited + 1; end
        if (!snapshot_done || !snapshot_ok || !snapshot_valid) $fatal(1, "SNAPSHOT_COPY_TIMEOUT");
        if (snapshot_metadata.epoch !== 32'd7 || snapshot_metadata.seq !== 64'd0 ||
            snapshot_metadata.dot !== 64'd23040 || snapshot_metadata.size !== 32'd5760)
            $fatal(1, "SNAPSHOT_METADATA");
        for (byte_index = 0; byte_index < 5760; byte_index = byte_index + 1) begin
            frame_read = 1; frame_address = 13'(byte_index); edge_cycle();
            if (!frame_valid || frame_data !== expected_byte(byte_index))
                $fatal(1, "SNAPSHOT_BYTE index=%0d expected=%02h actual=%02h", byte_index, expected_byte(byte_index), frame_data);
            checks = checks + 1;
            frame_read = 0; edge_cycle();
            if (frame_valid) $fatal(1, "SNAPSHOT_READ_HOLD");
        end
        $display("PASS snapshot first copy bytes=%0d", checks);
        $finish;
    end
    initial begin #2000000; $fatal(1, "SNAPSHOT_WATCHDOG"); end
endmodule
