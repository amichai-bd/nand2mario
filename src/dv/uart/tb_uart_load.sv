`timescale 1ns/1ps
`default_nettype none
module tb_uart_load;
    import n2m_uart_pkg::*;
    logic clk_sys, reset_sys, start, busy, done;
    uart_load_operation_t operation;
    logic [31:0] offset, expected_crc;
    logic [15:0] count;
    logic [7:0] status, input_data, output_data, rom_write_data, rom_read_data;
    logic input_valid, input_ready, output_valid, output_ready, rom_write, rom_read, rom_read_valid;
    logic [14:0] rom_address;
    logic init_done;
    logic [7:0] unused_access, unused_vram, unused_wave;
    logic [15:0] unused_oam;
    logic unused_access_valid, unused_vram_valid, unused_wave_valid, unused_oam_valid;
    integer writes, reads, endings, trace;
    bit crc_fault, presence_fault, checking_crc, checking_presence;
    n2m_uart_load dut (.*);
    n2m_memory_stores u_memory (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(1'b0), .init_done(init_done),
        .access_read(1'b0), .access_write(1'b0), .access_store(n2m_memory_pkg::STORE_ROM),
        .access_address(15'd0), .access_wdata(8'd0), .access_rdata(unused_access), .access_valid(unused_access_valid),
        .host_read(rom_read), .host_write(rom_write), .host_offset({17'b0,rom_address}),
        .host_wdata(rom_write_data), .host_rdata(rom_read_data), .host_valid(rom_read_valid),
        .ppu_vram_read(1'b0), .ppu_vram_address(13'd0), .ppu_vram_rdata(unused_vram), .ppu_vram_valid(unused_vram_valid),
        .ppu_oam_read(1'b0), .ppu_oam_pair(7'd0), .ppu_oam_rdata(unused_oam), .ppu_oam_valid(unused_oam_valid),
        .wave_read(1'b0), .wave_address(4'd0), .wave_rdata(unused_wave), .wave_valid(unused_wave_valid)
    );
    always #5 clk_sys = !clk_sys;
    function automatic logic [7:0] image_byte(input integer address);
        return 8'(((address*29)+(address>>8))^165);
    endfunction
    always @(posedge clk_sys) begin
        if (!reset_sys && rom_write) begin
            writes = writes + 1;
            $fdisplay(trace,"write,%0d,%02h",rom_address,rom_write_data);
        end
    end
    task automatic launch(input uart_load_operation_t op, input integer at, input integer size);
        @(negedge clk_sys); operation = op; offset = 32'(at); count = 16'(size); start = 1;
        @(negedge clk_sys); start = 0;
    endtask
    task automatic complete(input logic [7:0] expected_status);
        integer cycles;
        cycles = 0;
        while (!done && cycles < 70000) begin
            @(negedge clk_sys); cycles = cycles + 1;
            if (crc_fault && checking_crc && rom_read_valid && rom_address == 0)
                force dut.rom_read_data = 8'h00;
            if (presence_fault && checking_presence && rom_read_valid && rom_address == 7777)
                force dut.presence_value = 1'b1;
        end
        if (!done || status !== expected_status) $fatal(1,"UART_LOAD_RESULT op=%0d expected=%0d actual=%0d",operation,expected_status,status);
        if (operation == UART_LOAD_END) endings = endings + 1;
        @(negedge clk_sys);
        if (busy || done || rom_write || rom_read) $fatal(1,"UART_LOAD_IDLE");
    endtask
    task automatic write_bytes(input integer at, input integer size, input bit wrong);
        integer index, old_writes;
        old_writes = writes; launch(UART_LOAD_WRITE,at,size);
        for (index = 0; index < size; index = index + 1) begin
            if (!input_ready) $fatal(1,"UART_LOAD_WRITE_READY");
            input_data = image_byte(at+index) ^ (wrong ? 8'hff : 8'h00); input_valid = 1;
            @(negedge clk_sys); input_valid = 0;
            // Payload gaps cannot advance ROM address or lose a byte.
            if (index != size-1) @(negedge clk_sys);
        end
        complete(0);
        if (writes-old_writes != size) $fatal(1,"UART_LOAD_WRITE_COUNT");
    endtask
    task automatic write_missing_image;
        integer block, at;
        for (block = 127; block >= 0; block = block - 1) begin
            at = block*256;
            if (at <= 7777 && at+256 > 7777) begin
                write_bytes(at,7777-at,0);
                write_bytes(7778,at+256-7778,0);
            end else write_bytes(at,256,0);
        end
    endtask
    task automatic read_chunk(input integer at, input integer size);
        integer index, cycles;
        launch(UART_LOAD_READ,at,size); index = 0; cycles = 0;
        while (!done && cycles < 3000) begin
            if (output_valid) begin
                if (output_data !== image_byte(at+index)) $fatal(1,"UART_LOAD_READBACK index=%0d",at+index);
                // Hold the returned byte across host-response backpressure.
                repeat (2) @(negedge clk_sys);
                if (!output_valid || output_data !== image_byte(at+index)) $fatal(1,"UART_LOAD_READ_HOLD");
                output_ready = 1; @(negedge clk_sys); output_ready = 0;
                index = index + 1; reads = reads + 1;
            end else @(negedge clk_sys);
            cycles = cycles + 1;
        end
        if (index != size) $fatal(1,"UART_LOAD_READ_COUNT");
        complete(0);
    endtask
    initial begin
        integer block, old_writes;
        clk_sys = 0; reset_sys = 1; start = 0; operation = UART_LOAD_BEGIN;
        offset = 0; count = 0; expected_crc = 32'h2633e694;
        input_valid = 0; input_data = 0; output_ready = 0;
        writes = 0; reads = 0; endings = 0; checking_crc = 0; checking_presence = 0;
        crc_fault = $test$plusargs("crc_fault"); presence_fault = $test$plusargs("presence_fault");
        trace = $fopen("load.csv","w"); if (!trace) $fatal(1,"UART_LOAD_TRACE");
        $fdisplay(trace,"kind,address,data");
        $dumpfile("waves.vcd");
        $dumpvars(0,reset_sys,start,operation,busy,done,status,offset,count,
            input_valid,input_ready,input_data,output_valid,output_ready,output_data,
            rom_write,rom_read,rom_address,rom_write_data,rom_read_data,rom_read_valid,
            writes,reads,endings);
        repeat (3) @(negedge clk_sys); reset_sys = 0;
        // Expected whole-image CRC is supplied by a Python zlib calculation,
        // independently of the product's reflected bit recurrence.
        expected_crc = 32'h2633e694;
        launch(UART_LOAD_BEGIN,0,0);
        repeat (71) @(negedge clk_sys);
        old_writes = writes; #2; reset_sys = 1; #1;
        if (busy || done || rom_write || rom_read) $fatal(1,"UART_LOAD_RESET_CLEAR");
        repeat (3) @(negedge clk_sys); reset_sys = 0;
        launch(UART_LOAD_BEGIN,0,0); complete(0);
        if (writes != old_writes) $fatal(1,"UART_LOAD_CLEAR_ROM_WRITE");
        write_missing_image(); launch(UART_LOAD_END,0,0); complete(6);
        write_bytes(7777,1,0); checking_crc = 1;
        launch(UART_LOAD_END,0,0); complete(0); checking_crc = 0;
        write_bytes(100,1,1); launch(UART_LOAD_END,0,0); complete(6);
        write_bytes(100,1,0); launch(UART_LOAD_END,0,0); complete(0);
        for (block = 0; block < 128; block = block + 1) read_chunk(block*256,256);
        // Old correct ROM bytes cannot substitute for this load's presence.
        launch(UART_LOAD_BEGIN,0,0); complete(0); write_missing_image();
        checking_presence = 1; launch(UART_LOAD_END,0,0); complete(6); checking_presence = 0;
        write_bytes(7777,1,0); launch(UART_LOAD_END,0,0); complete(0);
        // Interrupted public write retains prior committed ROM bytes; a new
        // BEGIN must nevertheless replace all presence metadata before END.
        launch(UART_LOAD_WRITE,0,2); input_data = image_byte(0); input_valid = 1;
        @(negedge clk_sys); input_valid = 0; #2; reset_sys = 1; #1;
        if (rom_write || done || busy) $fatal(1,"UART_LOAD_RESET_WRITE");
        repeat (3) @(negedge clk_sys); reset_sys = 0;
        read_chunk(0,2);
        launch(UART_LOAD_BEGIN,0,0); complete(0); launch(UART_LOAD_END,0,0); complete(6);
        if (reads != 32770 || endings != 7 || writes != 65539) $fatal(1,"UART_LOAD_COUNTS writes=%0d reads=%0d ends=%0d",writes,reads,endings);
        $fclose(trace); $display("PASS UART load full_ROM CRC32 presence repair overlap readback reset"); $finish;
    end
    initial begin
        #20000000;
        $fatal(1,"UART_LOAD_WATCHDOG");
    end
endmodule
`default_nettype wire
