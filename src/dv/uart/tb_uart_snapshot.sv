`timescale 1ns/1ps
`default_nettype none
module tb_uart_snapshot;
    logic clk_sys, reset_sys, uart_rx, uart_tx;
    logic gb_tick, paused, pause_request, core_reset, core_initialized;
    logic instruction_complete, retirement_valid, cpu_stopped;
    logic [7:0] buttons, profile, endpoint_state;
    logic [31:0] epoch;
    logic [63:0] dot_count, retirement_count;
    logic image_valid, rom_write, rom_read, rom_read_valid;
    logic [14:0] rom_address;
    logic [7:0] rom_write_data, rom_read_data;
    logic snapshot_request, snapshot_ready, snapshot_done, snapshot_ok, snapshot_valid;
    n2m_interfaces_pkg::snapshot_t snapshot_metadata;
    logic frame_read, frame_valid;
    logic [12:0] frame_address;
    logic [7:0] frame_data;
    logic frame_available;
    integer snapshot_delay;
    logic [7:0] request_payload [0:255];
    logic [7:0] expected_payload [0:255];
    logic [7:0] raw_request [0:267];
    logic [7:0] encoded_request [0:270];
    logic [7:0] encoded_reply [0:270];
    logic [7:0] raw_reply [0:267];
    integer encoded_size, reply_size, expected_size, reply_count, command_count;
    integer rom_writes, reset_count, irq_count, trace;
    logic [63:0] observed_dots, observed_retirements;
    logic [31:0] token, expected_token;
    logic [7:0] expected_command, expected_status;
    bit waiting_reply, forbid_reset, duplicate_fault, readback_fault;
    bit dot_reply, input_reply;
    logic [63:0] observed_input_dot;
    logic [7:0] prior_buttons;
    n2m_uart #(.CLOCK_HZ(100000),.BAUD(12500)) dut (
        .input_source_observe(),
        .clk_sys(clk_sys),.reset_sys(reset_sys),.uart_rx(uart_rx),.uart_tx(uart_tx),
        .build_id(128'hfedcba98765432100123456789abcdef),.gb_tick(gb_tick),.paused(paused),
        .core_initialized(core_initialized),.instruction_complete(instruction_complete),
        .retirement_valid(retirement_valid),.cpu_stopped(cpu_stopped),.pause_request(pause_request),
        .physical_commit(1'b0),.physical_buttons(8'd0),.effective_buttons(),.effective_update(),
        .core_reset(core_reset),.buttons(buttons),.epoch(epoch),.dot_count(dot_count),
        .retirement_count(retirement_count),.profile(profile),.image_valid(image_valid),
        .endpoint_state(endpoint_state),.rom_write(rom_write),.rom_read(rom_read),
        .rom_address(rom_address),.rom_write_data(rom_write_data),.rom_read_data(rom_read_data),
        .rom_read_valid(rom_read_valid),.snapshot_request(snapshot_request),.snapshot_ready(snapshot_ready),
        .snapshot_done(snapshot_done),.snapshot_ok(snapshot_ok),.snapshot_valid(snapshot_valid),
        .snapshot_metadata(snapshot_metadata),.frame_read(frame_read),.frame_address(frame_address),
        .frame_data(frame_data),.frame_valid(frame_valid),
        .io_lcdc(8'd0), .io_stat(8'd0), .io_ly(8'd0), .io_lyc(8'd0), .io_scy(8'd0),
        .io_scx(8'd0), .io_wy(8'd0), .io_wx(8'd0), .io_bgp(8'd0), .io_obp0(8'd0),
        .io_obp1(8'd0), .io_div(8'd0), .io_tima(8'd0), .io_tma(8'd0), .io_tac(8'd0),
        .io_if(8'd0), .io_ie(8'd0),
        .peek_ready(1'b0), .peek_read(), .peek_select(), .peek_offset(), .peek_rdata(8'd0), .peek_valid(1'b0)
    );

    logic observe_valid, observe_complete, observe_abort;
    logic [14:0] observe_index;
    logic [1:0] observe_shade;
    logic [31:0] observe_epoch;
    logic [63:0] observe_sequence, observe_dot;
    integer init_delay, publication_count, checked_bytes;
    logic was_valid;
    n2m_interfaces_pkg::snapshot_t old_metadata;
    bit copy_active, corrupt_frame;
    n2m_frame_snapshot u_snapshot (.*);
    // This fixture exercises snapshot commands only. Core initialization is
    // an explicit delayed boundary; LOAD_BEGIN supplies the real reset pulse.
    assign paused = 1'b1;
    assign gb_tick = 1'b0;
    assign instruction_complete = 1'b0;
    assign retirement_valid = 1'b0;
    assign cpu_stopped = 1'b0;
    assign core_initialized = init_delay == 0;
    assign rom_read_valid = 1'b0;
    assign rom_read_data = 8'd0;
    always #5 clk_sys = !clk_sys;
    always @(posedge clk_sys) begin
        if(reset_sys) init_delay <= 0;
        else if(core_reset) begin init_delay <= 16;reset_count = reset_count + 1;end
        else if(init_delay != 0) init_delay <= init_delay - 1;
        if(rom_read || rom_write) $fatal(1,"UART_SNAPSHOT_UNEXPECTED_ROM_ACCESS");
        if(reset_sys) begin copy_active=0;publication_count=0;end
        else begin
            if(snapshot_request && snapshot_ready) begin
                copy_active=1;old_metadata=snapshot_metadata;was_valid=snapshot_valid;
            end
            if(copy_active && !snapshot_done && (snapshot_metadata !== old_metadata || snapshot_valid !== was_valid))
                $fatal(1,"UART_SNAPSHOT_EARLY_PUBLICATION");
            if(snapshot_done) begin copy_active=0;if(snapshot_ok)publication_count=publication_count+1;end
        end
    end
    function automatic logic [1:0] source_shade(input integer pixel, input integer frame);
        return 2'((pixel/160 + pixel%160 + pixel/7 + frame)%4);
    endfunction
    function automatic logic [7:0] packed_source(input integer at, input integer frame);
        return {source_shade(at*4+3,frame),source_shade(at*4+2,frame),source_shade(at*4+1,frame),source_shade(at*4,frame)};
    endfunction
    task automatic publish_source(input integer frame);
        integer pixel;
        for(pixel=0;pixel<23040;pixel=pixel+1) begin
            @(negedge clk_sys);observe_valid=1;observe_index=15'(pixel);
            observe_shade=source_shade(pixel,frame);observe_complete=pixel==23039;
            observe_epoch=32'(40+frame);observe_sequence=64'(1000+frame);observe_dot=64'(70224*frame);
        end
        @(negedge clk_sys);observe_valid=0;observe_complete=0;
    endtask
    task automatic expect_snapshot(input integer frame);
        integer item;
        for(item=0;item<24;item=item+1) expected_payload[item]=0;
        for(item=0;item<4;item=item+1)expected_payload[item]=8'((40+frame)>>(item*8));
        for(item=0;item<8;item=item+1)begin
            expected_payload[4+item]=8'(64'(1000+frame)>>(item*8));
            expected_payload[12+item]=8'(64'(70224*frame)>>(item*8));
        end
        expected_payload[20]=128;expected_payload[21]=22;
    endtask
    task automatic read_frame(input integer frame);
        integer at, amount, item;
        for(at=0;at<5760;at=at+256)begin
            amount=5760-at<256 ? 5760-at : 256;
            word_request(32'(at));request_payload[4]=8'(amount);request_payload[5]=8'(amount>>8);
            for(item=0;item<amount;item=item+1)expected_payload[item]=packed_source(at+item,frame);
            exchange(13,6,0,amount);checked_bytes=checked_bytes+amount;
        end
    endtask
    function automatic integer crc_update(input integer crc, input integer data);
        integer result, bit_number;
        result = crc ^ (data*256);
        for (bit_number=0;bit_number<8;bit_number=bit_number+1)
            result = result >= 32768 ? ((result*2)^4129)&65535 : (result*2)&65535;
        return result;
    endfunction
    task automatic check_reply;
        integer source, destination, code, item, checksum, payload_index;
        logic [7:0] expected;
        source=0;destination=0;
        while (source<reply_size) begin
            code=encoded_reply[source];source=source+1;
            if (code==0 || source+code-1>reply_size) $fatal(1,"UART_SNAPSHOT_COBS");
            for(item=1;item<code;item=item+1) begin raw_reply[destination]=encoded_reply[source];destination=destination+1;source=source+1;end
            if(code!=255 && source<reply_size) begin raw_reply[destination]=0;destination=destination+1;end
        end
        if (!waiting_reply || destination!=12+expected_size) $fatal(1,"UART_SNAPSHOT_REPLY_SIZE expected=%0d actual=%0d",12+expected_size,destination);
        checksum=65535;
        for(item=0;item<destination-2;item=item+1) checksum=crc_update(checksum,raw_reply[item]);
        if(raw_reply[destination-2]!=8'(checksum) || raw_reply[destination-1]!=8'(checksum>>8)) $fatal(1,"UART_SNAPSHOT_CRC");
        if(raw_reply[0]!=1 || raw_reply[1]!=1 || {raw_reply[5],raw_reply[4],raw_reply[3],raw_reply[2]}!=expected_token ||
            raw_reply[6]!=expected_command || raw_reply[7]!=expected_status || {raw_reply[9],raw_reply[8]}!=16'(expected_size))
            $fatal(1,"UART_SNAPSHOT_HEADER seq=%0d cmd=%0d status=%0d expected=%0d",expected_token,raw_reply[6],raw_reply[7],expected_status);
        for(payload_index=0;payload_index<expected_size;payload_index=payload_index+1) begin
            expected=expected_payload[payload_index];
            if(dot_reply) expected=8'((input_reply ? observed_input_dot : observed_dots)>>(payload_index*8));
            if(raw_reply[10+payload_index]!==expected) $fatal(1,"UART_SNAPSHOT_PAYLOAD cmd=%0d index=%0d expected=%02h actual=%02h",expected_command,payload_index,expected,raw_reply[10+payload_index]);
        end
        if (expected_status==0 && (expected_command==3 || expected_command==7 || expected_command==9) && (!paused || !core_initialized))
            $fatal(1,"UART_SNAPSHOT_EARLY_RESET_REPLY");
        $fdisplay(trace,"%0d,%0d,%0d,%0d,%0d,%0d",expected_token,expected_command,expected_status,expected_size,observed_dots,rom_writes);
        reply_count=reply_count+1;waiting_reply=0;reply_size=0;
    endtask
    initial begin : pin_monitor
        integer bit_number;
        logic [7:0] value;
        forever begin
            @(negedge uart_tx);
            if (!reset_sys) begin
                repeat(4) @(negedge clk_sys);
                if(uart_tx!==0) $fatal(1,"UART_SNAPSHOT_TX_START");
                for(bit_number=0;bit_number<8;bit_number=bit_number+1) begin repeat(8) @(negedge clk_sys);value[bit_number]=uart_tx;end
                repeat(8) @(negedge clk_sys);
                if(uart_tx!==1) $fatal(1,"UART_SNAPSHOT_TX_STOP");
                repeat(4) @(negedge clk_sys);
                if(value==0) check_reply();
                else begin if(reply_size>=270) $fatal(1,"UART_SNAPSHOT_TX_OVERFLOW");encoded_reply[reply_size]=value;reply_size=reply_size+1;end
            end
        end
    end
    task automatic send_byte(input logic [7:0] value);
        integer bit_number;
        @(negedge clk_sys);uart_rx=0;repeat(8) @(negedge clk_sys);
        for(bit_number=0;bit_number<8;bit_number=bit_number+1) begin uart_rx=value[bit_number];repeat(8) @(negedge clk_sys);end
        uart_rx=1;repeat(8) @(negedge clk_sys);
    endtask
    task automatic send_request(input logic [31:0] seq, input logic [7:0] cmd, input integer size, input integer declared, input integer version);
        integer item, checksum, code, code_index, position;
        raw_request[0]=8'(version);raw_request[1]=0;
        for(item=0;item<4;item=item+1) raw_request[2+item]=8'(seq>>(item*8));
        raw_request[6]=cmd;raw_request[7]=0;raw_request[8]=8'(declared);raw_request[9]=8'(declared>>8);
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
    task automatic exchange_header(input logic [7:0] cmd, input integer size, input integer declared, input integer version, input logic [7:0] result_status, input integer result_size);
        integer cycles;
        expected_token=token;expected_command=cmd;expected_status=result_status;expected_size=result_size;waiting_reply=1;
        send_request(token,cmd,size,declared,version);cycles=0;
        while(waiting_reply && cycles<180000) begin @(negedge clk_sys);cycles=cycles+1;end
        if(waiting_reply) $fatal(1,"UART_SNAPSHOT_TIMEOUT token=%0d command=%0d",token,cmd);
        repeat(4) @(negedge clk_sys);token=token+1;command_count=command_count+1;
    endtask
    task automatic exchange(input logic [7:0] cmd, input integer size, input logic [7:0] result_status, input integer result_size);
        exchange_header(cmd,size,size,1,result_status,result_size);
    endtask
    task automatic word_request(input logic [31:0] value);
        integer item;
        for(item=0;item<4;item=item+1) request_payload[item]=8'(value>>(item*8));
    endtask
    task automatic expect_word(input logic [31:0] value);
        integer item;
        for(item=0;item<4;item=item+1) expected_payload[item]=8'(value>>(item*8));
    endtask
    task automatic expect_dot(input logic [63:0] value);
        integer item;
        for(item=0;item<8;item=item+1) expected_payload[item]=8'(value>>(item*8));
    endtask
    task automatic begin_image;
        request_payload[0]=1;request_payload[1]=0;request_payload[2]=128;request_payload[3]=0;request_payload[4]=0;
        request_payload[5]=8'h28;request_payload[6]=8'h46;request_payload[7]=8'hbb;request_payload[8]=8'h83;
        exchange(7,9,0,0);
    endtask

    initial begin
        integer before_resets;
        clk_sys=0;reset_sys=1;uart_rx=1;init_delay=0;
        observe_valid=0;observe_complete=0;observe_abort=0;observe_index=0;observe_shade=0;
        observe_epoch=0;observe_sequence=0;observe_dot=0;
        reply_size=0;expected_size=0;reply_count=0;command_count=0;token=1;
        waiting_reply=0;dot_reply=0;input_reply=0;forbid_reset=0;
        rom_writes=0;reset_count=0;observed_dots=0;observed_retirements=0;observed_input_dot=0;
        checked_bytes=0;publication_count=0;copy_active=0;was_valid=0;old_metadata='0;
        corrupt_frame=$test$plusargs("corrupt_frame");
        trace=$fopen("commands.csv","w");if(!trace)$fatal(1,"UART_SNAPSHOT_TRACE");
        $fdisplay(trace,"seq,command,status,payload,dots,rom_writes");
        $dumpfile("waves.vcd");
        $dumpvars(0,reset_sys,uart_rx,uart_tx,core_reset,core_initialized,epoch,endpoint_state,
            snapshot_request,snapshot_ready,snapshot_done,snapshot_ok,snapshot_valid,snapshot_metadata,
            frame_read,frame_address,frame_data,frame_valid,observe_valid,observe_complete,observe_index,
            observe_shade,observe_epoch,observe_sequence,observe_dot,publication_count,checked_bytes,reply_count);
        repeat(5)@(negedge clk_sys);reset_sys=0;
        exchange(12,0,7,0);word_request(0);request_payload[4]=1;request_payload[5]=0;exchange(13,6,7,0);
        publish_source(1);expect_snapshot(1);exchange(12,0,0,24);
        if(corrupt_frame)force dut.frame_data=8'h00;
        read_frame(1);
        publish_source(2);
        // A newer source cannot alter the published host bytes before SNAPSHOT.
        read_frame(1);expect_snapshot(2);exchange(12,0,0,24);read_frame(2);
        before_resets=reset_count;begin_image();
        if(reset_count!=before_resets+1 || !snapshot_valid)$fatal(1,"UART_SNAPSHOT_CORE_RESET");
        exchange(12,0,5,0);read_frame(2);
        @(negedge clk_sys);reset_sys=1;repeat(5)@(negedge clk_sys);reset_sys=0;
        exchange(12,0,7,0);word_request(0);request_payload[4]=1;request_payload[5]=0;exchange(13,6,7,0);
        publish_source(3);expect_snapshot(3);exchange(12,0,0,24);
        word_request(5759);request_payload[4]=1;request_payload[5]=0;expected_payload[0]=packed_source(5759,3);exchange(13,6,0,1);
        word_request(5760);exchange(13,6,4,0);
        if(reply_count!=command_count || checked_bytes!=23040)$fatal(1,"UART_SNAPSHOT_CHECK_COUNT");
        $fclose(trace);$display("PASS UART snapshot actual_Intel wire bytes=%0d commands=%0d",checked_bytes,command_count);$finish;
    end
    initial begin #80000000;$fatal(1,"UART_SNAPSHOT_WATCHDOG");end
endmodule
`default_nettype wire
