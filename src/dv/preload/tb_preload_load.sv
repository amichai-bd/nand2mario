// Independent loader lifecycle checks using the actual initialized Intel RAM.
`timescale 1ns/1ps
`default_nettype none
module tb_preload_load;
    logic clk_sys, reset_sys, start, busy, done;
    n2m_uart_pkg::uart_load_operation_t operation;
    logic [31:0] offset, expected_crc;
    logic [15:0] count;
    logic [7:0] status, input_data, output_data;
    logic input_valid, input_ready, output_valid, output_ready;
    logic rom_write, rom_read, rom_read_valid;
    logic [14:0] rom_address;
    logic [7:0] rom_write_data, rom_read_data;
    logic unused_valid;
    logic [7:0] unused_data;
    logic [31:0] crc_word [0:0];
    logic [7:0] expected_bytes [0:32767];
    integer clear_writes, rom_reads, cycles;
    bit crc_fault;
    n2m_uart_load #(.SIM_PRELOAD(1)) dut (.*);
    defparam dut.u_presence.u_presence.SIM_INIT_FILE = "preload-presence.mif";
    n2m_intel_ram #(.DEPTH(32768),.ADDRESS_BITS(15),.SIM_INIT_FILE("preload-rom.mif")) rom (
        .clk_a(clk_sys),.clk_b(clk_sys),.reset_a(reset_sys),.reset_b(reset_sys),
        .a_read(rom_read),.a_write(rom_write),.a_address(rom_address),
        .a_wdata(rom_write_data),.a_byte_enable(1'b1),.a_rdata(rom_read_data),.a_valid(rom_read_valid),
        .b_read(1'b0),.b_address(15'd0),.b_rdata(unused_data),.b_valid(unused_valid)
    );
    always #10 clk_sys=!clk_sys;
    always @(posedge clk_sys) begin
        if(!reset_sys) begin
            cycles=cycles+1;
            if(rom_read) rom_reads=rom_reads+1;
            // Actual public presence-store write port, not owner next state.
            if(dut.u_presence.write_enable && !dut.u_presence.write_present)
                clear_writes=clear_writes+1;
        end
        if(cycles>400000) $fatal(1,"PRELOAD_LOAD_WATCHDOG");
    end
    task automatic launch(input n2m_uart_pkg::uart_load_operation_t op);
        @(negedge clk_sys); operation=op; start=1;
        @(negedge clk_sys); start=0;
    endtask
    task automatic finish_status(input logic [7:0] expected);
        wait(done); #1;
        if(status!==expected) $fatal(1,"PRELOAD_LOAD_STATUS expected=%02x actual=%02x",expected,status);
        @(negedge clk_sys); wait(!busy);
    endtask
    initial begin
        integer block_index, byte_index;
        clk_sys=0; reset_sys=1; start=0; operation=n2m_uart_pkg::UART_LOAD_BEGIN;
        offset=0; count=0; expected_crc=0; input_valid=0; input_data=0; output_ready=1;
        clear_writes=0; rom_reads=0; cycles=0; crc_fault=$test$plusargs("crc_fault");
        $readmemh("preload-crc.hex",crc_word);
        $readmemh("preload-bytes.hex",expected_bytes);
        $dumpfile("waves/public.vcd");
        $dumpvars(0,clk_sys,reset_sys,start,operation,busy,done,status,rom_read,rom_write,
            rom_address,rom_read_data,rom_read_valid,expected_crc,clear_writes,rom_reads);
        repeat(4) @(negedge clk_sys); reset_sys=0;
        expected_crc=crc_word[0] ^ (crc_fault ? 32'd1 : 32'd0);
        launch(n2m_uart_pkg::UART_LOAD_BEGIN); finish_status(n2m_interfaces_pkg::STATUS_OK);
        if(clear_writes!=0) $fatal(1,"PRELOAD_FIRST_CLEAR");
        launch(n2m_uart_pkg::UART_LOAD_END); finish_status(n2m_interfaces_pkg::STATUS_OK);
        if(rom_reads!=32768) $fatal(1,"PRELOAD_SCAN_COUNT");
        offset=32'h200; count=1;
        launch(n2m_uart_pkg::UART_LOAD_WRITE);
        @(negedge clk_sys); input_valid=1; input_data=expected_bytes[512]^8'h01;
        @(negedge clk_sys); input_valid=0;
        finish_status(n2m_interfaces_pkg::STATUS_OK);
        launch(n2m_uart_pkg::UART_LOAD_END); finish_status(n2m_interfaces_pkg::STATUS_BAD_IMAGE);
        // Reset must not re-arm adoption or initialize a replacement memory.
        @(negedge clk_sys); reset_sys=1;
        repeat(3) @(negedge clk_sys); reset_sys=0;
        launch(n2m_uart_pkg::UART_LOAD_BEGIN); finish_status(n2m_interfaces_pkg::STATUS_OK);
        if(clear_writes!=32768) $fatal(1,"PRELOAD_RESET_REARMED");
        launch(n2m_uart_pkg::UART_LOAD_END); finish_status(n2m_interfaces_pkg::STATUS_BAD_IMAGE);
        // Direct load owner accepts bounded chunks only: write128 chunks256.
        for(block_index=0;block_index<128;block_index=block_index+1) begin
            offset=32'(block_index*256); count=16'd256;
            launch(n2m_uart_pkg::UART_LOAD_WRITE);
            for(byte_index=0;byte_index<256;byte_index=byte_index+1) begin
                @(negedge clk_sys); input_valid=1;
                input_data=expected_bytes[block_index*256+byte_index];
            end
            @(negedge clk_sys); input_valid=0;
            finish_status(n2m_interfaces_pkg::STATUS_OK);
        end
        launch(n2m_uart_pkg::UART_LOAD_END); finish_status(n2m_interfaces_pkg::STATUS_OK);
        if(rom_reads!=131072) $fatal(1,"PRELOAD_FINAL_SCAN_COUNT");
        $display("PASS preload lifecycle bytes=32768 clear=32768 scans=4");
        $finish;
    end
endmodule
