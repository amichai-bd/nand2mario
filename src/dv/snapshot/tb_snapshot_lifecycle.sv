`timescale 1ns/1ps
`default_nettype none
module tb_snapshot_lifecycle;
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
    integer p, b, elapsed, checked, scenario, reset_case, delay_edges, done_count;
    bit corrupt, latency_fault, ownership_fault;
    string wave_path;
    n2m_frame_snapshot dut (.*);
    function automatic logic [1:0] shade(input integer frame_number, index);
        return 2'((frame_number + index / 160 + index % 160 + index / 7) % 4);
    endfunction
    function automatic logic [7:0] expected_byte(input integer frame_number, index);
        return {shade(frame_number,index*4+3),shade(frame_number,index*4+2),
                shade(frame_number,index*4+1),shade(frame_number,index*4)};
    endfunction
    task automatic edge_cycle;
        #5; clk_sys = 1; #1;
        if (snapshot_done) done_count = done_count + 1;
        #4; clk_sys = 0;
    endtask
    task automatic pixels(input integer frame_number, first, last, epoch_number, sequence_number);
        for (p = first; p <= last; p = p + 1) begin
            observe_valid = 1; observe_index = 15'(p); observe_shade = shade(frame_number,p);
            observe_epoch = 32'(epoch_number); observe_sequence = 64'(sequence_number);
            observe_dot = 64'(frame_number*100000+p); observe_complete = p == 23039;
            edge_cycle();
        end
        observe_valid = 0; observe_complete = 0;
    endtask
    task automatic request_copy;
        if (!snapshot_ready) $fatal(1,"SNAPSHOT_NOT_READY case=%0d",scenario);
        snapshot_request = 1; edge_cycle(); snapshot_request = 0;
    endtask
    task automatic wait_copy;
        elapsed = 0;
        while (!snapshot_done && elapsed < 12000) begin edge_cycle(); elapsed = elapsed + 1; end
        if (!snapshot_done || !snapshot_ok) $fatal(1,"SNAPSHOT_COMPLETION case=%0d",scenario);
    endtask
    task automatic metadata(input integer frame_number, epoch_number, sequence_number);
        if (!snapshot_valid || snapshot_metadata.epoch !== 32'(epoch_number) ||
            snapshot_metadata.seq !== 64'(sequence_number) || snapshot_metadata.size !== 32'd5760 ||
            snapshot_metadata.dot !== 64'(frame_number*100000+23039))
            $fatal(1,"SNAPSHOT_PUBLISHED_METADATA case=%0d",scenario);
    endtask
    task automatic check_read(input integer frame_number, address);
        frame_read = 1; frame_address = 13'(address); edge_cycle();
        if (!frame_valid) $fatal(1,"SNAPSHOT_LIFECYCLE_LATENCY case=%0d byte=%0d",scenario,address);
        if (frame_data !== expected_byte(frame_number,address))
            $fatal(1,"SNAPSHOT_LIFECYCLE_DATA case=%0d byte=%0d expected=%02h actual=%02h",
                scenario,address,expected_byte(frame_number,address),frame_data);
        checked = checked + 1; frame_read = 0; edge_cycle();
        if (frame_valid) $fatal(1,"SNAPSHOT_LIFECYCLE_EXTRA_RESPONSE");
    endtask
    task automatic all_bytes(input integer frame_number);
        for (b = 0; b < 5760; b = b + 1) begin
            check_read(frame_number,b);
            if (b % 137 == 0) repeat (3) edge_cycle();
        end
    endtask
    initial begin
        clk_sys=0; reset_sys=1; core_reset=0; observe_valid=0; observe_complete=0;
        observe_abort=0; observe_index=0; observe_shade=0; observe_epoch=0;
        observe_sequence=0; observe_dot=0; snapshot_request=0; frame_read=0; frame_address=0;
        checked=0; scenario=0; done_count=0;
        corrupt=$test$plusargs("corrupt"); latency_fault=$test$plusargs("latency_fault");
        ownership_fault=$test$plusargs("ownership_fault");
        if (!$value$plusargs("wave=%s",wave_path)) wave_path="wave.vcd";
        $dumpfile(wave_path);
        $dumpvars(0,clk_sys,reset_sys,core_reset,observe_valid,observe_complete,observe_abort,
            observe_index,observe_shade,observe_epoch,observe_sequence,observe_dot,
            snapshot_request,snapshot_ready,snapshot_done,snapshot_ok,snapshot_valid,
            snapshot_metadata,frame_read,frame_address,frame_data,frame_valid);
        edge_cycle(); reset_sys=0; edge_cycle();
        pixels(1,0,23039,7,0); request_copy(); wait_copy(); metadata(1,7,0); all_bytes(1);
        scenario=1;
        pixels(2,0,19999,7,1); request_copy();
        // B completes while the previously complete A is pinned. Reads still use A.
        for (p=20000;p<23040;p=p+1) begin
            observe_valid=1; observe_index=15'(p); observe_shade=shade(2,p);
            observe_epoch=7; observe_sequence=1; observe_dot=64'(200000+p);
            observe_complete=p==23039; frame_read=1; frame_address=13'(p%5760);
            edge_cycle();
            if (!frame_valid || frame_data !== expected_byte(1,p%5760))
                $fatal(1,"SNAPSHOT_CONCURRENT_READ byte=%0d",p%5760);
            checked=checked+1;
        end
        observe_valid=0; observe_complete=0; frame_read=0;
        wait_copy(); metadata(1,7,0); all_bytes(1);
        request_copy(); wait_copy(); metadata(1,7,0);
        scenario=2; pixels(3,0,23039,7,2); request_copy();
        repeat (11519) edge_cycle();
        if (snapshot_done) $fatal(1,"SNAPSHOT_EARLY_PUBLICATION");
        // This final-write edge must return A, then subsequent requests return C.
        check_read(1,0); metadata(3,7,2); check_read(3,0);
        if (corrupt) begin
            force dut.banks[0].u_host.a_write=1'b1;
            force dut.banks[0].u_host.a_address=13'd3;
            force dut.banks[0].u_host.a_wdata=8'haa;
            edge_cycle();
            release dut.banks[0].u_host.a_write;
            release dut.banks[0].u_host.a_address;
            release dut.banks[0].u_host.a_wdata;
        end
        if (latency_fault) force dut.frame_valid=1'b0;
        check_read(3,3); all_bytes(3);
        if (ownership_fault) force dut.state_q.assembly_bank=1'b0;
        edge_cycle();
        scenario=3;
        pixels(4,0,23038,7,3);
        observe_valid=1; observe_complete=1; observe_abort=1; observe_index=23039;
        edge_cycle(); observe_valid=0; observe_complete=0; observe_abort=0;
        request_copy(); wait_copy(); metadata(3,7,2);
        for (reset_case=0;reset_case<4;reset_case=reset_case+1) begin
            scenario=4+reset_case;
            pixels(5+reset_case,0,23039,8+reset_case,0); request_copy();
            case(reset_case)
                0: delay_edges=0;
                1: delay_edges=1;
                2: delay_edges=5759;
                default: delay_edges=11519;
            endcase
            repeat(delay_edges) edge_cycle();
            done_count=0; core_reset=1;
            check_read(3,reset_case); repeat(3) edge_cycle();
            if (done_count!=1 || snapshot_ok) $fatal(1,"SNAPSHOT_CANCEL_COUNT case=%0d count=%0d",scenario,done_count);
            core_reset=0; edge_cycle(); request_copy();
            if (!snapshot_done || snapshot_ok) $fatal(1,"SNAPSHOT_RESET_NO_FRAME");
            metadata(3,7,2); all_bytes(3);
        end
        reset_sys=1; edge_cycle();
        if (snapshot_valid || frame_valid || snapshot_done) $fatal(1,"SNAPSHOT_GLOBAL_RESET");
        reset_sys=0; edge_cycle(); request_copy();
        if (!snapshot_done || snapshot_ok || snapshot_valid) $fatal(1,"SNAPSHOT_GLOBAL_NO_FRAME");
        $display("PASS snapshot lifecycle cases=8 bytes=%0d",checked); $finish;
    end
    initial begin #10000000; $fatal(1,"SNAPSHOT_LIFECYCLE_WATCHDOG"); end
endmodule
