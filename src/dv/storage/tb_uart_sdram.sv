`timescale 1ns/1ps
`default_nettype none
// Full-wire host SDRAM line commands: SDRAM_WRITE and SDRAM_READ packets go
// through the real UART endpoint into the SDRAM controller and the pin-level
// device model. Contract: wiki/src/rtl/storage/MAS_sdram.md and the host rules
// in wiki/src/rtl/cartridge/MAS_loader_profile.md#host-interaction.
// Lint waiver: byte array elements are passed to integer CRC and index
// arithmetic; both width lints are false positives.
/* verilator lint_off WIDTHEXPAND */
/* verilator lint_off WIDTHTRUNC */
module tb_uart_sdram;
    logic clk_sys, reset_sys, uart_rx, uart_tx;
    logic gb_tick, paused, pause_request, core_reset;
    logic [7:0] endpoint_state;
    logic physical_commit;
    logic [7:0] physical_buttons, effective_buttons;
    n2m_input_pkg::input_update_t effective_update;
    logic sdram_initialized, sdram_request_valid, sdram_request_write, sdram_request_ready;
    logic sdram_response_valid, sdram_idle;
    logic [25:0] sdram_request_address;
    logic [127:0] sdram_request_data, sdram_response_data;
    logic [12:0] dram_addr;
    logic [1:0] dram_ba;
    logic dram_cas_n, dram_cke, dram_clk, dram_cs_n, dram_dqml, dram_dqmh, dram_ras_n, dram_we_n;
    tri [15:0] dram_dq;
    logic [31:0] model_refreshes, model_reads, model_writes;
    // Sized for the oversize sixteen-line frame (272 raw bytes) as well as
    // every in-limit packet.
    logic [7:0] request_payload [0:271];
    logic [7:0] expected_payload [0:255];
    logic [7:0] raw_request [0:283];
    logic [7:0] encoded_request [0:287];
    logic [7:0] encoded_reply [0:270];
    logic [7:0] raw_reply [0:267];
    integer encoded_size, reply_size, expected_size, command_count;
    integer written, read_lines, rejected, discarded;
    logic [31:0] token, expected_token;
    logic [7:0] expected_command, expected_status;
    bit waiting_reply, payload_fault;
    logic [7:0] memory [int unsigned];

    // The SDRAM timing is in 40 ns clocks, so the wire runs at 3.125 MBaud to
    // keep eight clocks per bit for the bit-level driver and monitor below.
    n2m_uart #(.CLOCK_HZ(25000000), .BAUD(3125000)) dut (
        .input_source_observe(),
        .clk_sys(clk_sys), .reset_sys(reset_sys), .uart_rx(uart_rx), .uart_tx(uart_tx),
        .build_id(128'hfedcba98765432100123456789abcdef), .gb_tick(gb_tick), .paused(paused),
        .core_initialized(1'b0), .instruction_complete(1'b0), .retirement_valid(1'b0), .cpu_stopped(1'b0),
        .pause_request(pause_request), .core_reset(core_reset), .buttons(),
        .physical_commit(physical_commit), .physical_buttons(physical_buttons),
        .effective_buttons(effective_buttons), .effective_update(effective_update),
        .epoch(), .dot_count(), .retirement_count(), .profile(), .image_valid(), .endpoint_state(endpoint_state),
        .rom_write(), .rom_read(), .rom_address(), .rom_write_data(), .rom_read_data(8'd0), .rom_read_valid(1'b0),
        .snapshot_request(), .snapshot_ready(1'b0), .snapshot_done(1'b0), .snapshot_ok(1'b0),
        .snapshot_valid(1'b0), .snapshot_metadata('0), .frame_read(), .frame_address(),
        .frame_data(8'd0), .frame_valid(1'b0),
        .io_lcdc(8'd0), .io_stat(8'd0), .io_ly(8'd0), .io_lyc(8'd0), .io_scy(8'd0),
        .io_scx(8'd0), .io_wy(8'd0), .io_wx(8'd0), .io_bgp(8'd0), .io_obp0(8'd0),
        .io_obp1(8'd0), .io_div(8'd0), .io_tima(8'd0), .io_tma(8'd0), .io_tac(8'd0),
        .io_if(8'd0), .io_ie(8'd0),
        .peek_ready(1'b0), .peek_read(), .peek_select(), .peek_offset(), .peek_rdata(8'd0), .peek_valid(1'b0),
        .sdram_initialized(sdram_initialized), .sdram_request_valid(sdram_request_valid),
        .sdram_request_write(sdram_request_write), .sdram_request_address(sdram_request_address),
        .sdram_request_data(sdram_request_data), .sdram_request_ready(sdram_request_ready),
        .sdram_response_valid(sdram_response_valid), .sdram_response_data(sdram_response_data),
        .loader_copy_busy(1'b0), .loader_swap_busy(1'b0), .engine_invalidate(1'b0), .engine_publish(1'b0),
        .engine_profile(8'd0), .library_status(32'd0), .library_key1(32'd0), .engine_pause(1'b0),
        .engine_reset_request(1'b0), .boot_run(1'b0), .engine_reset_accept(), .engine_reset_done(), .host_session(), .host_loading(),
        .host_port_busy(), .library_return()
    );
    n2m_timebase u_timebase (.clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset),
        .pause_request(pause_request), .gb_tick(gb_tick), .paused(paused));
    n2m_sdram_ctrl u_sdram (
        .clk_sys(clk_sys), .reset_sys(reset_sys),
        .request_valid(sdram_request_valid), .request_write(sdram_request_write),
        .request_address(sdram_request_address), .request_data(sdram_request_data),
        .request_ready(sdram_request_ready), .response_valid(sdram_response_valid),
        .response_data(sdram_response_data), .idle(sdram_idle), .initialized(sdram_initialized),
        .DRAM_ADDR(dram_addr), .DRAM_BA(dram_ba), .DRAM_CAS_N(dram_cas_n), .DRAM_CKE(dram_cke),
        .DRAM_CLK(dram_clk), .DRAM_CS_N(dram_cs_n), .DRAM_DQ(dram_dq), .DRAM_DQML(dram_dqml),
        .DRAM_DQMH(dram_dqmh), .DRAM_RAS_N(dram_ras_n), .DRAM_WE_N(dram_we_n)
    );
    n2m_sim_sdram u_device (
        .dram_clk(dram_clk), .dram_addr(dram_addr), .dram_ba(dram_ba),
        .dram_ras_n(dram_ras_n), .dram_cas_n(dram_cas_n), .dram_we_n(dram_we_n),
        .dram_cke(dram_cke), .dram_cs_n(dram_cs_n), .dram_dqml(dram_dqml), .dram_dqmh(dram_dqmh),
        .dram_dq(dram_dq), .refreshes(model_refreshes), .reads(model_reads), .writes(model_writes)
    );
    always #20 clk_sys = !clk_sys;

    function automatic logic [7:0] line_byte(input logic [31:0] address, input integer index);
        return 8'((address >> 4) * 29 + index * 71 + (address >> 18) + 17);
    endfunction
    function automatic integer crc_update(input integer crc, input integer data);
        integer result, bit_number;
        result = crc ^ (data*256);
        for (bit_number=0;bit_number<8;bit_number=bit_number+1)
            result = result >= 32768 ? ((result*2)^4129)&65535 : (result*2)&65535;
        return result;
    endfunction
    task automatic check_reply;
        integer source, destination, code, item, checksum, payload_index;
        source=0;destination=0;
        while (source<reply_size) begin
            code=encoded_reply[source];source=source+1;
            if (code==0 || source+code-1>reply_size) $fatal(1,"UART_SDRAM_COBS");
            for(item=1;item<code;item=item+1) begin raw_reply[destination]=encoded_reply[source];destination=destination+1;source=source+1;end
            if(code!=255 && source<reply_size) begin raw_reply[destination]=0;destination=destination+1;end
        end
        if (!waiting_reply) $fatal(1,"UART_SDRAM_UNEXPECTED_REPLY bytes=%0d",destination);
        if (destination!=12+expected_size) $fatal(1,"UART_SDRAM_REPLY_SIZE expected=%0d actual=%0d",12+expected_size,destination);
        checksum=65535;
        for(item=0;item<destination-2;item=item+1) checksum=crc_update(checksum,raw_reply[item]);
        if(raw_reply[destination-2]!=8'(checksum) || raw_reply[destination-1]!=8'(checksum>>8)) $fatal(1,"UART_SDRAM_CRC");
        if(raw_reply[0]!=1 || raw_reply[1]!=1 || {raw_reply[5],raw_reply[4],raw_reply[3],raw_reply[2]}!=expected_token ||
            raw_reply[6]!=expected_command || raw_reply[7]!=expected_status || {raw_reply[9],raw_reply[8]}!=16'(expected_size))
            $fatal(1,"UART_SDRAM_HEADER seq=%0d cmd=%0d status=%0d/%0d size=%0d",expected_token,raw_reply[6],raw_reply[7],expected_status,{raw_reply[9],raw_reply[8]});
        for(payload_index=0;payload_index<expected_size;payload_index=payload_index+1)
            if(raw_reply[10+payload_index]!=expected_payload[payload_index])
                $fatal(1,"UART_SDRAM_PAYLOAD cmd=%0d index=%0d expected=%02h actual=%02h",
                    expected_command,payload_index,expected_payload[payload_index],raw_reply[10+payload_index]);
        waiting_reply=0;reply_size=0;
    endtask
    initial begin : pin_monitor
        integer bit_number;
        logic [7:0] value;
        forever begin
            @(negedge uart_tx);
            if (!reset_sys) begin
                repeat(4) @(negedge clk_sys);
                if(uart_tx!=0) $fatal(1,"UART_SDRAM_TX_START");
                for(bit_number=0;bit_number<8;bit_number=bit_number+1) begin repeat(8) @(negedge clk_sys);value[bit_number]=uart_tx;end
                repeat(8) @(negedge clk_sys);
                if(uart_tx!=1) $fatal(1,"UART_SDRAM_TX_STOP");
                repeat(4) @(negedge clk_sys);
                if(value==0) check_reply();
                else begin if(reply_size>=270) $fatal(1,"UART_SDRAM_TX_OVERFLOW");encoded_reply[reply_size]=value;reply_size=reply_size+1;end
            end
        end
    end
    task automatic send_byte(input logic [7:0] value);
        integer bit_number;
        @(negedge clk_sys);uart_rx=0;repeat(8) @(negedge clk_sys);
        for(bit_number=0;bit_number<8;bit_number=bit_number+1) begin uart_rx=value[bit_number];repeat(8) @(negedge clk_sys);end
        uart_rx=1;repeat(8) @(negedge clk_sys);
    endtask
    task automatic send_request(input logic [31:0] seq, input logic [7:0] cmd, input integer size);
        integer item, checksum, code, code_index, position;
        raw_request[0]=1;raw_request[1]=0;
        for(item=0;item<4;item=item+1) raw_request[2+item]=8'(seq>>(item*8));
        raw_request[6]=cmd;raw_request[7]=0;raw_request[8]=8'(size);raw_request[9]=8'(size>>8);
        for(item=0;item<size;item=item+1) raw_request[10+item]=request_payload[item];
        checksum=65535;for(item=0;item<10+size;item=item+1) checksum=crc_update(checksum,raw_request[item]);
        raw_request[10+size]=8'(checksum);raw_request[11+size]=8'(checksum>>8);
        code=1;code_index=0;position=1;
        for(item=0;item<12+size;item=item+1) begin
            if(raw_request[item]==0) begin encoded_request[code_index]=8'(code);code_index=position;position=position+1;code=1;end
            else begin
                encoded_request[position]=raw_request[item];position=position+1;code=code+1;
                if(code==255) begin encoded_request[code_index]=255;code_index=position;position=position+1;code=1;end
            end
        end
        encoded_request[code_index]=8'(code);encoded_request[position]=0;encoded_size=position+1;
        for(item=0;item<encoded_size;item=item+1) send_byte(encoded_request[item]);
    endtask
    task automatic exchange(input logic [7:0] cmd, input integer size, input logic [7:0] result_status, input integer result_size);
        integer cycles;
        expected_token=token;expected_command=cmd;expected_status=result_status;expected_size=result_size;waiting_reply=1;
        send_request(token,cmd,size);cycles=0;
        while(waiting_reply && cycles<400000) begin @(negedge clk_sys);cycles=cycles+1;end
        if(waiting_reply) $fatal(1,"UART_SDRAM_TIMEOUT token=%0d command=%0d",token,cmd);
        repeat(4) @(negedge clk_sys);token=token+1;command_count=command_count+1;
    endtask
    // SDRAM_WRITE: address then count*16 line bytes, byte 0 of the first line
    // first; the line count is carried by the payload length alone.
    task automatic write_lines(input logic [31:0] address, input integer count);
        integer item;
        for(item=0;item<4;item=item+1) request_payload[item]=8'(address>>(item*8));
        for(item=0;item<count*16;item=item+1) begin
            request_payload[4+item]=line_byte(address+32'(item-item%16),item%16);
            memory[address+item]=line_byte(address+32'(item-item%16),item%16);
        end
        exchange(n2m_interfaces_pkg::COMMAND_SDRAM_WRITE,4+count*16,0,0);
        written=written+count;
    endtask
    task automatic write_line(input logic [31:0] address);
        write_lines(address,1);
    endtask
    // SDRAM_READ: address and line count; the reply carries count*16 bytes.
    task automatic read_lines_at(input logic [31:0] address, input integer count);
        integer item;
        for(item=0;item<4;item=item+1) request_payload[item]=8'(address>>(item*8));
        request_payload[4]=8'(count);
        for(item=0;item<count*16;item=item+1) expected_payload[item]=memory[address+item];
        if(payload_fault) expected_payload[0]=~expected_payload[0];
        exchange(n2m_interfaces_pkg::COMMAND_SDRAM_READ,5,0,count*16);
        read_lines=read_lines+count;
    endtask
    task automatic reject_write(input logic [31:0] address, input integer size, input logic [7:0] status);
        integer item;
        for(item=0;item<4;item=item+1) request_payload[item]=8'(address>>(item*8));
        for(item=0;item<size;item=item+1) request_payload[4+item]=8'(item);
        exchange(n2m_interfaces_pkg::COMMAND_SDRAM_WRITE,size,status,0);
        rejected=rejected+1;
    endtask
    // A payload over the 256-byte limit is not a command: the endpoint discards
    // the frame through its delimiter and answers nothing (MAS_uart). The pin
    // monitor fails on any reply while none is awaited.
    task automatic discard_write(input logic [31:0] address, input integer size);
        integer item;
        for(item=0;item<4;item=item+1) request_payload[item]=8'(address>>(item*8));
        for(item=0;item<size;item=item+1) request_payload[4+item]=8'(item);
        waiting_reply=0;
        send_request(token,n2m_interfaces_pkg::COMMAND_SDRAM_WRITE,size);
        repeat(20000) @(negedge clk_sys);
        if (reply_size!=0) $fatal(1,"UART_SDRAM_DISCARD_REPLY bytes=%0d",reply_size);
        token=token+1;discarded=discarded+1;
    endtask
    task automatic reject_read(input logic [31:0] address, input integer count, input integer size, input logic [7:0] status);
        integer item;
        for(item=0;item<4;item=item+1) request_payload[item]=8'(address>>(item*8));
        request_payload[4]=8'(count);
        exchange(n2m_interfaces_pkg::COMMAND_SDRAM_READ,size,status,0);
        rejected=rejected+1;
    endtask
    initial begin
        clk_sys=0;reset_sys=1;uart_rx=1;physical_commit=0;physical_buttons=0;
        reply_size=0;expected_size=0;command_count=0;token=1;waiting_reply=0;
        written=0;read_lines=0;rejected=0;discarded=0;
        payload_fault=$test$plusargs("payload_fault");
        $dumpfile("waves.vcd");
        $dumpvars(0,reset_sys,uart_rx,uart_tx,endpoint_state,sdram_initialized,sdram_request_valid,
            sdram_request_write,sdram_request_address,sdram_request_ready,sdram_response_valid,
            written,read_lines,rejected,discarded,command_count);
        repeat(5) @(negedge clk_sys);reset_sys=0;
        // The first write arrives long before the 5038-clock initialization: BAD_VALUE.
        if (sdram_initialized) $fatal(1,"UART_SDRAM_EARLY_INIT");
        reject_write(32'h0000000,20,4);
        if (sdram_initialized) $fatal(1,"UART_SDRAM_LATE_REJECT");
        while(!sdram_initialized) @(negedge clk_sys);
        // Single lines at slot 0 start, device end, slot 15 end and catalogue
        // start; then multi-line writes: fifteen lines in one command, the last
        // fifteen lines of the device, seven lines across a row boundary
        // (rows are 2 KiB) and two lines in bank 2; each read back in one command.
        write_line(32'h0000000);
        write_line(32'h3fffff0);
        write_line(32'h007fff0);
        write_line(32'h0088000);
        write_lines(32'h1002800,15);
        write_lines(32'h3ffff10,15);
        write_lines(32'h00007c0,7);
        write_lines(32'h2000000,2);
        read_lines_at(32'h0000000,1);
        read_lines_at(32'h3fffff0,1);
        read_lines_at(32'h007fff0,1);
        read_lines_at(32'h0088000,1);
        read_lines_at(32'h1002800,15);
        read_lines_at(32'h1002880,3);
        read_lines_at(32'h3ffff10,15);
        read_lines_at(32'h00007c0,7);
        read_lines_at(32'h2000000,2);
        // Overwrite then read: the later write wins.
        write_line(32'h0000000);
        read_lines_at(32'h0000000,1);
        // Structural refusals, none of which reaches the controller: misaligned,
        // past the device, a two-line run crossing the device end (BAD_VALUE);
        // 19, 21, 4 (zero lines) and 252 (fifteen and a half lines) payload
        // bytes (BAD_LENGTH); a sixteen-line payload (260 bytes) is discarded
        // as oversize and the next command still answers.
        reject_write(32'h0000008,20,4);
        reject_write(32'h4000000,20,4);
        reject_write(32'h3fffff0,36,4);
        reject_write(32'h0000000,19,3);
        reject_write(32'h0000000,21,3);
        reject_write(32'h0000000,4,3);
        reject_write(32'h0000000,252,3);
        discard_write(32'h0000000,260);
        read_lines_at(32'h0000000,1);
        reject_read(32'h0000010,0,5,4);
        reject_read(32'h0000010,16,5,4);
        reject_read(32'h0000004,1,5,4);
        reject_read(32'h3fffff0,2,5,4);
        reject_read(32'h4000000,1,5,4);
        reject_read(32'h0000000,1,4,3);
        if (model_writes!=written || model_reads!=read_lines || read_lines!=48 || written!=44)
            $fatal(1,"UART_SDRAM_COUNTS writes=%0d/%0d reads=%0d/%0d",model_writes,written,model_reads,read_lines);
        $display("PASS UART SDRAM wire writes=%0d lines_read=%0d rejected=%0d discarded=%0d commands=%0d refreshes=%0d",
            written,read_lines,rejected,discarded,command_count,model_refreshes);
        $finish;
    end
    initial begin #1600000000;$fatal(1,"UART_SDRAM_WATCHDOG");end
endmodule
`default_nettype wire
