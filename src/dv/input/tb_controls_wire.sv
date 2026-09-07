`timescale 1ns/1ps
`include "src/rtl/common/macros.svh"
// Actual input/UART/JOYP/Intel VGA composition, with explicit external ADC samples.
// Eight-clock UART and reduced filter intervals bound DV; physical values are fit separately.
module tb_controls_wire;
    logic clk_sys, board_reset_n, uart_rx, uart_tx;
    logic [3:0] buttons_n, red, green, blue;
    logic [9:0] leds, video_x, video_y;
    logic video_image, hsync_n, vsync_n, ready, paused, observed_complete;
    logic [63:0] discard_count, repeat_count, display_sequence, observed_sequence;
    logic [31:0] display_epoch;
    logic [14:0] observed_index;
    logic [11:0] sample_x, sample_y;
    logic [7:0] request_payload[0:255], expected_payload[0:255];
    logic [7:0] raw_request[0:267], raw_reply[0:267];
    logic [7:0] encoded_request[0:270], encoded_reply[0:270];
    integer encoded_size, reply_size, expected_size, reply_count, command_count, trace;
    logic [31:0] token, expected_token;
    logic [7:0] expected_command, expected_status;
    bit waiting_reply, corrupt_mask;
    integer pixel_checks, zero_index;
    logic clk_pix;
    logic reset_sys;
    logic reset_pix;
    logic clk_adc;
    logic adc_pll_reset;
    logic adc_pll_locked;
    logic adc_ready;
    logic adc_reset;
    logic adc_domain_reset;
    logic command_valid;
    logic [4:0] command_channel;
    logic command_ready;
    logic response_valid;
    logic [4:0] response_channel;
    logic [11:0] response_data;
    logic physical_commit;
    logic [7:0] physical_buttons;
    logic fresh;
    logic adc_fault;
    logic [7:0] effective_buttons;
    logic [7:0] input_source;
    n2m_input_pkg::input_update_t effective_update;
    logic core_reset;
    logic pause_request;
    logic gb_tick;
    logic [7:0] joypad_buttons;
    logic [3:0] display_divider;
    logic display_sample;
    logic [14:0] pixel_index;
    logic [63:0] display_dot;
    logic [31:0] source_epoch;
    logic [1:0] shade;
    n2m_physical_controls #(.BUTTON_CYCLES(8), .INTERVAL_CYCLES(32), .LIMIT_CYCLES(256)) u_physical (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .gb_tick(gb_tick), .buttons_n(buttons_n),
        .adc_available(1'b1), .command_valid(command_valid), .command_channel(command_channel),
        .command_ready(command_ready), .response_valid(response_valid), .response_channel(response_channel),
        .response_data(response_data), .physical_commit(physical_commit), .physical_buttons(physical_buttons),
        .adc_fresh(fresh), .adc_fault(adc_fault)
    );
    n2m_timebase u_timebase (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset), .pause_request(pause_request),
        .gb_tick(gb_tick), .paused(paused)
    );
    n2m_uart #(.CLOCK_HZ(100000), .BAUD(12500)) u_uart (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .uart_rx(uart_rx), .uart_tx(uart_tx), .build_id(128'h123456789abcdef00123456789abcdef),
        .gb_tick(gb_tick), .paused(paused), .core_initialized(1'b0), .instruction_complete(1'b0),
        .retirement_valid(1'b0), .cpu_stopped(1'b0), .pause_request(pause_request), .core_reset(core_reset),
        .buttons(), .physical_commit(physical_commit), .physical_buttons(physical_buttons),
        .effective_buttons(effective_buttons), .effective_update(effective_update), .input_source_observe(input_source),
        .epoch(), .dot_count(), .retirement_count(), .profile(), .image_valid(), .endpoint_state(),
        .rom_write(), .rom_read(), .rom_address(), .rom_write_data(), .rom_read_data(8'd0), .rom_read_valid(1'b0),
        .snapshot_request(), .snapshot_ready(1'b0), .snapshot_done(1'b0), .snapshot_ok(1'b0),
        .snapshot_valid(1'b0), .snapshot_metadata('0), .frame_read(), .frame_address(),
        .frame_data(8'd0), .frame_valid(1'b0)
    );
    n2m_joypad u_joypad (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset), .gb_tick(gb_tick),
        .input_commit(effective_update.valid), .input_buttons(effective_update.buttons),
        .io_commit(1'b0), .io_write(1'b0), .io_address(16'hFF00), .io_wdata(8'd0),
        .io_selected(), .io_rdata(), .buttons_observe(joypad_buttons), .selected_active(), .request_event()
    );
    assign leds = {fresh, input_source == n2m_interfaces_pkg::INPUT_SOURCE_PHYSICAL, effective_buttons};
    // Diagnostic producer runs while the emulation timebase is paused. It
    // supplies synthetic shades only and is never reported as PPU observation.
    assign display_sample = display_divider == 4'd11;
    `DFF_ARST_VAL(display_divider, display_sample ? 4'd0 : display_divider + 4'd1, clk_sys, reset_sys, 4'd0)
    `DFF_RST_EN(pixel_index, pixel_index == 15'd23039 ? 15'd0 : pixel_index + 15'd1,
        clk_sys, display_sample, reset_sys || core_reset, 15'd0)
    `DFF_RST_EN(display_dot, display_dot + 64'd1, clk_sys, display_sample, reset_sys || core_reset, 64'd0)
    `DFF_RST_EN(source_epoch, source_epoch + 32'd1, clk_sys, core_reset, reset_sys, 32'd0)
    assign shade = pixel_index[1:0] ^ pixel_index[9:8] ^ joypad_buttons[1:0] ^
        joypad_buttons[3:2] ^ joypad_buttons[5:4] ^ joypad_buttons[7:6];
    n2m_frame_bridge u_bridge (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset), .clk_pix(clk_pix), .reset_pix(reset_pix),
        .source_valid(display_sample), .source_start(pixel_index == 0), .source_shade(shade),
        .source_dot(display_dot), .source_epoch(source_epoch), .source_abort(1'b0), .blank_assert(1'b0),
        .source_display_eligible(1'b1), .observe_abort(), .observe_valid(), .observe_complete(observed_complete),
        .observe_index(observed_index), .observe_shade(), .observe_epoch(), .observe_sequence(observed_sequence), .observe_dot(),
        .discard_count(discard_count), .repeat_count(repeat_count), .display_valid(), .display_sequence(display_sequence), .display_epoch(display_epoch),
        .video_x(video_x), .video_y(video_y), .video_valid(), .video_active(), .video_image(video_image),
        .red(red), .green(green), .blue(blue), .hsync_n(hsync_n), .vsync_n(vsync_n)
    );
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
            if (code==0 || source+code-1>reply_size) $fatal(1,"CONTROLS_WIRE_COBS");
            for(item=1;item<code;item=item+1) begin raw_reply[destination]=encoded_reply[source];destination=destination+1;source=source+1;end
            if(code!=255 && source<reply_size) begin raw_reply[destination]=0;destination=destination+1;end
        end
        if (!waiting_reply || destination!=12+expected_size) $fatal(1,"CONTROLS_WIRE_REPLY_SIZE expected=%0d actual=%0d",12+expected_size,destination);
        checksum=65535;
        for(item=0;item<destination-2;item=item+1) checksum=crc_update(checksum,raw_reply[item]);
        if(raw_reply[destination-2]!=8'(checksum) || raw_reply[destination-1]!=8'(checksum>>8)) $fatal(1,"CONTROLS_WIRE_CRC");
        if(raw_reply[0]!=1 || raw_reply[1]!=1 || {raw_reply[5],raw_reply[4],raw_reply[3],raw_reply[2]}!=expected_token ||
            raw_reply[6]!=expected_command || raw_reply[7]!=expected_status || {raw_reply[9],raw_reply[8]}!=16'(expected_size))
            $fatal(1,"CONTROLS_WIRE_HEADER seq=%0d cmd=%0d status=%0d expected=%0d",expected_token,raw_reply[6],raw_reply[7],expected_status);
        for(payload_index=0;payload_index<expected_size;payload_index=payload_index+1) begin
            expected=expected_payload[payload_index];
            if(raw_reply[10+payload_index]!==expected) $fatal(1,"CONTROLS_WIRE_PAYLOAD cmd=%0d index=%0d expected=%02h actual=%02h",expected_command,payload_index,expected,raw_reply[10+payload_index]);
        end
        $fdisplay(trace,"%0d,%0d,%0d",expected_token,expected_command,expected_size);
        reply_count=reply_count+1;waiting_reply=0;reply_size=0;
    endtask
    initial begin : pin_monitor
        integer bit_number;
        logic [7:0] value;
        forever begin
            @(negedge uart_tx);
            if (!reset_sys) begin
                repeat(4) @(negedge clk_sys);
                if(uart_tx!==0) $fatal(1,"CONTROLS_WIRE_TX_START");
                for(bit_number=0;bit_number<8;bit_number=bit_number+1) begin repeat(8) @(negedge clk_sys);value[bit_number]=uart_tx;end
                repeat(8) @(negedge clk_sys);
                if(uart_tx!==1) $fatal(1,"CONTROLS_WIRE_TX_STOP");
                repeat(4) @(negedge clk_sys);
                if(value==0) check_reply();
                else begin if(reply_size>=270) $fatal(1,"CONTROLS_WIRE_TX_OVERFLOW");encoded_reply[reply_size]=value;reply_size=reply_size+1;end
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
        if(waiting_reply) $fatal(1,"CONTROLS_WIRE_TIMEOUT token=%0d command=%0d",token,cmd);
        repeat(4) @(negedge clk_sys);token=token+1;command_count=command_count+1;
    endtask
    task automatic exchange(input logic [7:0] cmd, input integer size, input logic [7:0] result_status, input integer result_size);
        exchange_header(cmd,size,size,1,result_status,result_size);
    endtask
    task automatic host_write_request(input logic [31:0] address_value, input logic [31:0] value);
        integer item;
        for(item=0;item<4;item=item+1) begin
            request_payload[item]=8'(address_value>>(item*8));
            request_payload[item+4]=8'(value>>(item*8));
        end
    endtask
    task automatic word_request(input logic [31:0] value);
        integer item;
        for(item=0;item<4;item=item+1) request_payload[item]=8'(value>>(item*8));
    endtask
    task automatic expect_word(input logic [31:0] value);
        integer item;
        for(item=0;item<4;item=item+1) expected_payload[item]=8'(value>>(item*8));
    endtask

    always #5 clk_sys = !clk_sys;
    always #10 clk_pix = !clk_pix;
    assign command_ready = 1'b1;
    // Public command acceptance produces a next-edge sample; no vendor module is substituted.
    `DFF_ARST_VAL(response_valid, command_valid && command_ready, clk_sys, reset_sys, 1'b0)
    `DFF_ARST_VAL(response_channel, command_channel, clk_sys, reset_sys, 5'd0)
    `DFF_ARST_VAL(response_data, command_channel == 5'd1 ? sample_x : sample_y, clk_sys, reset_sys, 12'd0)
    task automatic masks(input logic [7:0] host, input logic [7:0] source,
                         input logic [7:0] physical, input logic [7:0] effective);
        word_request(32'h10020); expect_word({24'd0,host}); exchange(2,4,0,4);
        word_request(32'h10044); expect_word({24'd0,source}); exchange(2,4,0,4);
        word_request(32'h10048); expect_word({24'd0,physical}); exchange(2,4,0,4);
        word_request(32'h1004c); expect_word({24'd0,effective}); exchange(2,4,0,4);
        if (corrupt_mask && effective == 8'h16) force joypad_buttons = 8'h00;
        if (joypad_buttons !== effective || leds !== {1'b1,source[0],effective})
            $fatal(1,"CONTROLS_WIRE_MASK expected=%02h joypad=%02h leds=%03h",effective,joypad_buttons,leds);
        if (!paused || gb_tick) $fatal(1,"CONTROLS_WIRE_PAUSED");
    endtask
    initial begin
        $dumpfile("waves.vcd");
        $dumpvars(0,clk_sys,clk_pix,reset_sys,uart_rx,uart_tx,buttons_n,sample_x,sample_y,
            command_valid,command_channel,response_valid,response_channel,response_data,
            physical_commit,physical_buttons,effective_buttons,input_source,joypad_buttons,
            leds,paused,gb_tick,core_reset,observed_complete,display_sequence,video_x,video_y,
            video_image,red,green,blue,hsync_n,vsync_n);
        trace=$fopen("controls.csv","w");
        clk_sys=0;clk_pix=0;reset_sys=1;reset_pix=1;uart_rx=1;buttons_n=15;
        sample_x=1352;sample_y=1352;token=1;reply_size=0;reply_count=0;command_count=0;
        waiting_reply=0;pixel_checks=0;corrupt_mask=$test$plusargs("corrupt_mask");
        repeat(8) @(negedge clk_sys);reset_sys=0;reset_pix=0;
        repeat(100) @(negedge clk_sys);
        masks(0,0,0,0);
        for(zero_index=0;zero_index<8;zero_index=zero_index+1) expected_payload[zero_index]=0;
        request_payload[0]=8'h5a; exchange(11,1,0,8);
        masks(8'h5a,0,0,8'h5a);
        @(negedge clk_sys);buttons_n=4'hd;sample_x=0;sample_y=0;
        repeat(100) @(negedge clk_sys);
        masks(8'h5a,0,8'h26,8'h5a);
        for(zero_index=0;zero_index<8;zero_index=zero_index+1) expected_payload[zero_index]=0;
        host_write_request(32'h10044,1); exchange(14,8,0,8);
        masks(8'h5a,1,8'h26,8'h26);
        @(negedge clk_sys);buttons_n=4'he;sample_x=0;sample_y=0;
        repeat(100) @(negedge clk_sys);
        masks(8'h5a,1,8'h16,8'h16);
        // After two more display publications every sampled image pixel has the stable mask.
        repeat(2) @(posedge observed_complete);
        repeat(2) @(negedge vsync_n);
        while(pixel_checks<96) begin
            @(negedge clk_pix);
            if(video_image) begin
                integer index, expected_shade;
                logic [3:0] expected_gray;
                index=((int'(video_y)-24)/3)*160+(int'(video_x)-80)/3;
                expected_shade=((index&3)^((index>>8)&3)^2);
                case(expected_shade)
                    0: expected_gray=15;
                    1: expected_gray=10;
                    2: expected_gray=5;
                    default: expected_gray=0;
                endcase
                if({red,green,blue}!=={3{expected_gray}})
                    $fatal(1,"CONTROLS_WIRE_VGA index=%0d expected=%0h actual=%0h",index,expected_gray,red);
                pixel_checks=pixel_checks+1;
            end
        end
        $fclose(trace);
        $display("PASS CONTROLS_WIRE commands=%0d replies=%0d pixels=%0d paused=1",command_count,reply_count,pixel_checks);
        $finish;
    end
    initial begin #40000000; $fatal(1,"CONTROLS_WIRE_WATCHDOG"); end
endmodule
