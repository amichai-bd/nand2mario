`timescale 1ns/1ps
`default_nettype none
// Two frame bridges on one stimulus: the shell bezel against the black border.
// The Python border model owns the border colours; this fixture owns the
// equality proof that the image, sync and snapshot bytes do not move.
// Lint waiver: the integer raster file handle is tested as a boolean.
/* verilator lint_off WIDTHTRUNC */
module tb_vga_bezel;
    localparam int unsigned CAPTURE_SAMPLES = 420000;
    localparam int unsigned SNAPSHOT_BYTES = 5760;
    logic clk_sys, clk_pix, reset_sys, reset_pix, core_reset;
    logic source_valid, source_start, source_abort, blank_assert;
    logic source_display_eligible;
    logic [1:0] source_shade;
    logic [31:0] source_epoch;
    logic [63:0] source_dot;
    logic [1:0] observe_valid, observe_complete, observe_abort, display_valid;
    logic [14:0] observe_index [0:1];
    logic [1:0] observe_shade [0:1];
    logic [31:0] observe_epoch [0:1], display_epoch [0:1];
    logic [63:0] observe_sequence [0:1], observe_dot [0:1];
    logic [63:0] discard_count [0:1], repeat_count [0:1], display_sequence [0:1];
    logic [9:0] video_x [0:1], video_y [0:1];
    logic [1:0] video_valid, video_active, video_image;
    logic [3:0] red [0:1], green [0:1], blue [0:1];
    logic [1:0] hsync_n, vsync_n;
    logic snapshot_request;
    logic [1:0] snapshot_ready, snapshot_done, snapshot_ok, snapshot_valid;
    n2m_interfaces_pkg::snapshot_t snapshot_metadata [0:1];
    logic frame_read;
    logic [12:0] frame_address;
    logic [1:0] frame_valid;
    logic [7:0] frame_data [0:1];

    genvar side;
    generate for (side = 0; side < 2; side = side + 1) begin : g_side
        n2m_frame_bridge #(.SHELL_BEZEL(side == 1)) u_bridge (
            .clk_sys, .reset_sys, .core_reset, .clk_pix, .reset_pix,
            .source_valid, .source_start, .source_abort, .blank_assert,
            .source_display_eligible, .source_shade, .source_epoch, .source_dot,
            .observe_valid(observe_valid[side]), .observe_complete(observe_complete[side]),
            .observe_abort(observe_abort[side]), .observe_index(observe_index[side]),
            .observe_shade(observe_shade[side]), .observe_epoch(observe_epoch[side]),
            .observe_sequence(observe_sequence[side]), .observe_dot(observe_dot[side]),
            .discard_count(discard_count[side]), .repeat_count(repeat_count[side]),
            .display_valid(display_valid[side]), .display_sequence(display_sequence[side]),
            .display_epoch(display_epoch[side]), .video_x(video_x[side]), .video_y(video_y[side]),
            .video_valid(video_valid[side]), .video_active(video_active[side]),
            .video_image(video_image[side]), .red(red[side]), .green(green[side]),
            .blue(blue[side]), .hsync_n(hsync_n[side]), .vsync_n(vsync_n[side])
        );
        n2m_frame_snapshot u_snapshot (
            .clk_sys, .reset_sys, .core_reset,
            .observe_valid(observe_valid[side]), .observe_complete(observe_complete[side]),
            .observe_abort(observe_abort[side]), .observe_index(observe_index[side]),
            .observe_shade(observe_shade[side]), .observe_epoch(observe_epoch[side]),
            .observe_sequence(observe_sequence[side]), .observe_dot(observe_dot[side]),
            .snapshot_request, .snapshot_ready(snapshot_ready[side]),
            .snapshot_done(snapshot_done[side]), .snapshot_ok(snapshot_ok[side]),
            .snapshot_valid(snapshot_valid[side]), .snapshot_metadata(snapshot_metadata[side]),
            .frame_read, .frame_address, .frame_valid(frame_valid[side]),
            .frame_data(frame_data[side])
        );
    end endgenerate

    always #20 clk_sys = !clk_sys;
    // Nominal 25.2 MHz rounded to the declared 1 ps fixture precision.
    always #19.84127 clk_pix = !clk_pix;

    logic image_area;
    assign image_area = video_x[1] >= 10'd80 && video_x[1] < 10'd560
        && video_y[1] >= 10'd24 && video_y[1] < 10'd456;
    int unsigned image_pixels, border_pixels, snapshot_reads;
    // The bezel is presentation only: everything except the border must match.
    always @(posedge clk_pix) begin
        #1;
        if (!reset_pix && video_valid[0]) begin
            if (video_x[0] != video_x[1] || video_y[0] != video_y[1]
                || video_valid[0] != video_valid[1] || video_active[0] != video_active[1]
                || video_image[0] != video_image[1] || hsync_n[0] != hsync_n[1]
                || vsync_n[0] != vsync_n[1])
                $fatal(1, "BEZEL_RASTER x=%0d y=%0d", video_x[1], video_y[1]);
            if (!video_active[1] || image_area) begin
                if ({red[0], green[0], blue[0]} != {red[1], green[1], blue[1]})
                    $fatal(1, "BEZEL_IMAGE x=%0d y=%0d none=%03h shell=%03h", video_x[1],
                           video_y[1], {red[0], green[0], blue[0]}, {red[1], green[1], blue[1]});
                if (video_active[1] && image_area) image_pixels = image_pixels + 1;
            end else begin
                if ({red[0], green[0], blue[0]} != 12'h000)
                    $fatal(1, "BEZEL_NONE_BORDER x=%0d y=%0d", video_x[1], video_y[1]);
                border_pixels = border_pixels + 1;
            end
        end
    end
    always @(posedge clk_sys) begin
        #1;
        if (!reset_sys) begin
            if (observe_valid[0] != observe_valid[1] || observe_complete[0] != observe_complete[1]
                || observe_abort[0] != observe_abort[1] || observe_index[0] != observe_index[1]
                || observe_shade[0] != observe_shade[1] || observe_epoch[0] != observe_epoch[1]
                || observe_sequence[0] != observe_sequence[1] || observe_dot[0] != observe_dot[1])
                $fatal(1, "BEZEL_OBSERVER");
            if (frame_read && snapshot_valid[0]) begin
                if (frame_valid[0] != frame_valid[1] || frame_data[0] != frame_data[1])
                    $fatal(1, "BEZEL_SNAPSHOT address=%0d none=%02h shell=%02h",
                           frame_address, frame_data[0], frame_data[1]);
                snapshot_reads = snapshot_reads + 1;
            end
        end
    end

    // Passive public-pin capture of the shell instance, after NBA settling.
    // One whole displayed raster, opened at its first pixel.
    integer raster_file;
    int unsigned capture_count;
    bit capturing;
    logic [14:0] public_raster;
    assign public_raster = {reset_pix, red[1], green[1], blue[1], hsync_n[1], vsync_n[1]};
    always @(posedge clk_pix) begin
        #1;
        if (!capturing && !reset_pix && display_valid[1] && video_valid[1]
            && video_x[1] == 10'd0 && video_y[1] == 10'd0)
            capturing = 1;
        if (capturing && capture_count < CAPTURE_SAMPLES) begin
            capture_count++;
            $fdisplay(raster_file, "%08h,%03h,%03h,%04h", capture_count,
                      video_x[1], video_y[1], public_raster);
            if (capture_count % 2048 == 0) $fflush(raster_file);
            if (capture_count == CAPTURE_SAMPLES) begin
                $fdisplay(raster_file, "END");
                $fclose(raster_file);
            end
        end
    end

    // One snapshot per instance from the same request, then a host walk of
    // every packed byte on both.
    task automatic acquire;
        @(negedge clk_sys);
        if (!snapshot_ready[0] || !snapshot_ready[1]) $fatal(1, "BEZEL_SNAPSHOT_BUSY");
        snapshot_request = 1;
        @(negedge clk_sys);
        snapshot_request = 0;
        wait (snapshot_done[0] && snapshot_done[1]);
        #1;
        if (!snapshot_ok[0] || !snapshot_ok[1]
            || snapshot_metadata[0] != snapshot_metadata[1])
            $fatal(1, "BEZEL_SNAPSHOT_METADATA ok=%b%b none=%p shell=%p",
                   snapshot_ok[0], snapshot_ok[1], snapshot_metadata[0], snapshot_metadata[1]);
    endtask
    initial begin
        capture_count = 0; capturing = 0; image_pixels = 0; border_pixels = 0;
        snapshot_reads = 0; snapshot_request = 0; frame_read = 0; frame_address = 0;
        raster_file = $fopen("public-raster.txt", "w");
        if (!raster_file) $fatal(1, "BEZEL_TRACE_OPEN");
    end
    initial begin
        clk_sys = 0; clk_pix = 0;
        reset_sys = 1; reset_pix = 1; core_reset = 0;
        source_valid = 0; source_start = 0; source_abort = 0;
        blank_assert = 0; source_display_eligible = 1;
        source_shade = 0; source_epoch = 0; source_dot = 0;
        #1000;
        fork
            begin @(negedge clk_sys); reset_sys = 0; end
            begin @(negedge clk_pix); reset_pix = 0; end
        join
        wait (observe_complete[0]);
        // The completing edge sets the snapshot's latest frame; request after it.
        repeat (8) @(posedge clk_sys);
        acquire();
        for (int unsigned address = 0; address < SNAPSHOT_BYTES; address++) begin
            @(negedge clk_sys);
            frame_read = 1;
            frame_address = 13'(address);
            @(negedge clk_sys);
            frame_read = 0;
        end
        wait (capture_count == CAPTURE_SAMPLES);
        if (snapshot_reads != SNAPSHOT_BYTES || image_pixels < 207360 || border_pixels < 99840)
            $fatal(1, "BEZEL_COVERAGE reads=%0d image=%0d border=%0d",
                   snapshot_reads, image_pixels, border_pixels);
        // The Python checker owns the PASS signature; this states the fixture side.
        $display("BEZEL_FIXTURE_COMPLETE image=%0d border=%0d snapshot_bytes=%0d",
                 image_pixels, border_pixels, snapshot_reads);
    end
    initial begin
        // The negative target corrupts one actual tile ROM read, before the
        // captured raster and outside the image path the equality checks own.
        if ($test$plusargs("bezel_corrupt")) begin
            #16000000;
            force g_side[1].u_bridge.u_scan.g_shell.tile_pixel = 4'd0;
        end
    end
    initial begin
        #42000000;
        $fatal(1, "BEZEL_WATCHDOG");
    end
endmodule
`default_nettype wire
