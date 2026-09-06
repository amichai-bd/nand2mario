`timescale 1ns/1ps
`default_nettype none
// Reuse the existing independent source/raster/ownership fixture unchanged.
module tb_snapshot_vga;
    tb_vga video();
    logic snapshot_request, snapshot_ready, snapshot_done, snapshot_ok, snapshot_valid;
    n2m_interfaces_pkg::snapshot_t snapshot_metadata;
    logic frame_read, frame_valid;
    logic [12:0] frame_address;
    logic [7:0] frame_data;
    integer expected_epoch, expected_sequence, latest_epoch, latest_sequence;
    logic [63:0] expected_dot, latest_dot, requested_dot;
    integer requested_epoch, requested_sequence;
    integer source_frames, host_reads, acquisitions, copies_during_swap, resets;
    integer read_offset, read_spacing;
    bit copy_active, host_initialized, had_display;
    logic [63:0] old_display_sequence;
    logic [31:0] old_display_epoch;
    n2m_frame_snapshot u_snapshot (
        .clk_sys(video.clk_sys), .reset_sys(video.reset_sys), .core_reset(video.core_reset),
        .observe_valid(video.observe_valid), .observe_complete(video.observe_complete),
        .observe_abort(video.observe_abort), .observe_index(video.observe_index),
        .observe_shade(video.observe_shade), .observe_epoch(video.observe_epoch),
        .observe_sequence(video.observe_sequence), .observe_dot(video.observe_dot),
        .snapshot_request, .snapshot_ready, .snapshot_done, .snapshot_ok, .snapshot_valid,
        .snapshot_metadata, .frame_read, .frame_address, .frame_data, .frame_valid
    );
    // Independent formula matches the original producer, not snapshot state.
    function automatic logic [1:0] shade(input integer epoch_number, sequence_number, index);
        integer x, y;
        x=index%160; y=index/160;
        return 2'((epoch_number*3+sequence_number+x/7+y/5+(x*y)%3)%4);
    endfunction
    function automatic logic [7:0] expected_byte(input integer ep, seq, address);
        return {shade(ep,seq,address*4+3),shade(ep,seq,address*4+2),
                shade(ep,seq,address*4+1),shade(ep,seq,address*4)};
    endfunction
    always @(posedge video.clk_sys) begin
        if (video.observe_complete) begin
            source_frames=source_frames+1;
            latest_epoch=int'(video.observe_epoch); latest_sequence=int'(video.observe_sequence);
            latest_dot=video.observe_dot;
        end
        #1;
        if (frame_read && host_initialized && !video.reset_sys) begin
            if (!frame_valid || frame_data !== expected_byte(expected_epoch,expected_sequence,int'(frame_address)))
                $fatal(1,"SNAPSHOT_VGA_READ byte=%0d epoch=%0d sequence=%0d expected=%02h actual=%02h",
                    frame_address,expected_epoch,expected_sequence,
                    expected_byte(expected_epoch,expected_sequence,int'(frame_address)),frame_data);
            host_reads=host_reads+1;
        end
        // The response on this edge still belongs to the pre-edge host bank.
        if (snapshot_done && !video.reset_sys) begin
            if (!snapshot_ok || !snapshot_valid || snapshot_metadata.epoch !== 32'(requested_epoch)
                || snapshot_metadata.seq !== 64'(requested_sequence) || snapshot_metadata.dot !== requested_dot
                || snapshot_metadata.size !== 32'd5760) $fatal(1,"SNAPSHOT_VGA_METADATA");
            expected_epoch=requested_epoch; expected_sequence=requested_sequence; expected_dot=requested_dot;
            acquisitions=acquisitions+1; copy_active=0; host_initialized=1;
        end
        if (host_initialized && !video.reset_sys && !snapshot_done &&
            (!snapshot_valid || snapshot_metadata.epoch !== 32'(expected_epoch)
             || snapshot_metadata.seq !== 64'(expected_sequence) || snapshot_metadata.dot !== expected_dot))
            $fatal(1,"SNAPSHOT_VGA_IMMUTABLE_METADATA");
    end
    always @(posedge video.core_reset) if (host_initialized) resets=resets+1;
    always @(posedge video.clk_pix) begin
        #1;
        if (video.display_valid) begin
            if ((!had_display || video.display_sequence != old_display_sequence || video.display_epoch != old_display_epoch)
                && copy_active) copies_during_swap=copies_during_swap+1;
            old_display_sequence=video.display_sequence; old_display_epoch=video.display_epoch; had_display=1;
        end
    end
    // Slow host chunks span new frames, display swaps and core resets.
    always @(negedge video.clk_sys) begin
        frame_read=0;
        if (host_initialized && !video.reset_sys) begin
            if (read_spacing==0) begin
                frame_read=1; frame_address=13'(read_offset);
                read_offset=(read_offset+1)%5760; read_spacing=200;
            end else read_spacing=read_spacing-1;
        end
    end
    task automatic acquire;
        @(negedge video.clk_sys);
        if (!snapshot_ready) $fatal(1,"SNAPSHOT_VGA_BUSY");
        requested_epoch=latest_epoch; requested_sequence=latest_sequence; requested_dot=latest_dot;
        snapshot_request=1; copy_active=1;
        @(negedge video.clk_sys); snapshot_request=0;
    endtask
    initial begin
        snapshot_request=0; frame_read=0; frame_address=0; source_frames=0; host_reads=0;
        acquisitions=0; copies_during_swap=0; resets=0; copy_active=0; host_initialized=0;
        had_display=0; old_display_sequence=0; old_display_epoch=0;
        expected_epoch=0; expected_sequence=0; latest_epoch=0; latest_sequence=0;
        expected_dot=0; latest_dot=0; requested_dot=0; requested_epoch=0; requested_sequence=0;
        read_offset=0; read_spacing=0;
        $dumpvars(0,snapshot_request,snapshot_ready,snapshot_done,snapshot_ok,snapshot_valid,
            snapshot_metadata,frame_read,frame_address,frame_data,frame_valid);
        wait(source_frames==1); acquire(); wait(acquisitions==1);
        // Four scanlines before wrap: the 230.4us copy overlaps the first swap.
        wait(video.video_y==520 && video.video_x==0); acquire(); wait(acquisitions==2);
    end
    always @(negedge video.pll_locked) begin
        if ($time>0 && host_initialized) begin
            if (source_frames!=16 || host_reads<5760 || acquisitions!=2 || resets!=2 || copies_during_swap<1)
                $fatal(1,"SNAPSHOT_VGA_COVERAGE frames=%0d reads=%0d copies=%0d resets=%0d overlaps=%0d",
                    source_frames,host_reads,acquisitions,resets,copies_during_swap);
            $display("PASS snapshot VGA frames=16 immutable reads=%0d swaps_during_copy=%0d core_resets=2",host_reads,copies_during_swap);
        end
    end
endmodule
