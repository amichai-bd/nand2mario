`timescale 1ns/1ps
`default_nettype none
module tb_uart_endpoint;
    import n2m_interfaces_pkg::*;
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
    snapshot_t snapshot_metadata;
    logic frame_read, frame_valid;
    logic [12:0] frame_address;
    logic [7:0] frame_data;
    logic frame_available;
    integer snapshot_delay;
    logic request_valid, write_enable, bus_commit, cpu_initialized, cpu_fault;
    logic [15:0] address;
    logic [7:0] write_data, read_data, ie;
    logic response_valid;
    logic [4:0] iflags, irq_ack;
    n2m_cpu_pkg::access_kind_t access_kind;
    retirement_t retirement;
    logic memory_initialized;
    logic [7:0] unused_vram, unused_wave;
    logic [15:0] unused_oam;
    logic unused_vram_valid, unused_wave_valid, unused_oam_valid;
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
    logic physical_commit;
    logic [7:0] physical_buttons, effective_buttons;
    n2m_input_pkg::input_update_t effective_update;
    integer accepted_inputs;
    logic [63:0] observed_input_dot;
    logic [7:0] prior_buttons;
    n2m_uart #(.CLOCK_HZ(100000),.BAUD(12500)) dut (
        .input_source_observe(),
        .clk_sys(clk_sys),.reset_sys(reset_sys),.uart_rx(uart_rx),.uart_tx(uart_tx),
        .build_id(128'hfedcba98765432100123456789abcdef),.gb_tick(gb_tick),.paused(paused),
        .core_initialized(core_initialized),.instruction_complete(instruction_complete),
        .retirement_valid(retirement_valid),.cpu_stopped(cpu_stopped),.pause_request(pause_request),
        .physical_commit(physical_commit),.physical_buttons(physical_buttons),
        .effective_buttons(effective_buttons),.effective_update(effective_update),
        .core_reset(core_reset),.buttons(buttons),.epoch(epoch),.dot_count(dot_count),
        .retirement_count(retirement_count),.profile(profile),.image_valid(image_valid),
        .endpoint_state(endpoint_state),.rom_write(rom_write),.rom_read(rom_read),
        .rom_address(rom_address),.rom_write_data(rom_write_data),.rom_read_data(rom_read_data),
        .rom_read_valid(rom_read_valid),.snapshot_request(snapshot_request),.snapshot_ready(snapshot_ready),
        .snapshot_done(snapshot_done),.snapshot_ok(snapshot_ok),.snapshot_valid(snapshot_valid),
        .snapshot_metadata(snapshot_metadata),.frame_read(frame_read),.frame_address(frame_address),
        .frame_data(frame_data),.frame_valid(frame_valid)
    );
    n2m_timebase u_timebase (.*);
    n2m_cpu u_cpu (
        .clk_sys(clk_sys),.reset_sys(reset_sys),.core_reset(core_reset),.gb_tick(gb_tick),
        .profile_id(profile),.epoch(epoch),.dot_before(dot_count),.ie(ie),.iflags(iflags),.buttons(buttons),
        .read_data(read_data),.response_valid(response_valid),.joyp_selected_active(1'b0),.wake_request(1'b0),
        .request_valid(request_valid),.address(address),.write_data(write_data),.write_enable(write_enable),
        .access_kind(access_kind),.bus_commit(bus_commit),.irq_ack(irq_ack),.halted(),.stopped(cpu_stopped),
        .locked(),.initialized(cpu_initialized),.fault(cpu_fault),.ime_observe(),.ime_delay_observe(),
        .stop_execute(),.divider_reset_request(),.instruction_complete(instruction_complete),
        .retirement_valid(retirement_valid),.retirement(retirement),.address_effect(),
        .address_effect_resolved(),.address_effect_sample(),.address_effect_phase()
    );
    // This original program uses ROM and HRAM stack only. No peripheral decode
    // or full-system integration is claimed by this fixture's small responder.
    n2m_memory_stores u_memory (.oam_request('0), .oam_response(),
        .clk_sys(clk_sys),.reset_sys(reset_sys),.core_reset(core_reset),.init_done(memory_initialized),
        .access_read(memory_initialized && endpoint_state != 2 && request_valid && !write_enable),
        .access_write(memory_initialized && bus_commit && write_enable),
        .access_store(address >= 16'hff80 ? n2m_memory_pkg::STORE_HRAM : n2m_memory_pkg::STORE_ROM),
        .access_address(address >= 16'hff80 ? 15'(address-16'hff80) : address[14:0]),
        .access_wdata(write_data),.access_rdata(read_data),.access_valid(response_valid),
        .host_read(rom_read),.host_write(rom_write),.host_offset({17'b0,rom_address}),
        .host_wdata(rom_write_data),.host_rdata(rom_read_data),.host_valid(rom_read_valid),
        .ppu_vram_read(1'b0),.ppu_vram_address(13'd0),.ppu_vram_rdata(unused_vram),.ppu_vram_valid(unused_vram_valid),
        .ppu_oam_read(1'b0),.ppu_oam_pair(7'd0),.ppu_oam_rdata(unused_oam),.ppu_oam_valid(unused_oam_valid),
        .wave_read(1'b0),.wave_address(4'd0),.wave_rdata(unused_wave),.wave_valid(unused_wave_valid)
    );
    assign core_initialized = memory_initialized && cpu_initialized;
    assign snapshot_ready = snapshot_delay == 0;
    always #5 clk_sys = !clk_sys;
    always @(posedge clk_sys) begin
        bit sampled_tick, sampled_reset;
        sampled_tick = gb_tick;
        sampled_reset = core_reset;
        if (reset_sys) begin
            observed_dots = 0; observed_retirements = 0; prior_buttons = 0;
        end else if (core_reset) begin
            if (forbid_reset) $fatal(1,"UART_ENDPOINT_DUPLICATE_RESET");
            observed_dots = 0; observed_retirements = 0; reset_count = reset_count + 1;
            ie <= 0; iflags <= 0;
        end else begin
            if (gb_tick) observed_dots = observed_dots + 1;
            if (retirement_valid) observed_retirements = observed_retirements + 1;
            if (irq_ack) begin irq_count = irq_count + 1; iflags <= iflags & ~irq_ack; end
        end
        if (!reset_sys && rom_write) begin
            if (!paused || endpoint_state != 2) $fatal(1,"UART_ENDPOINT_RUNNING_WRITE");
            rom_writes = rom_writes + 1;
        end
        #1;
        if (!reset_sys) begin
            if (dot_count !== observed_dots || retirement_count !== observed_retirements) $fatal(1,"UART_ENDPOINT_COUNTS");
            if (buttons != prior_buttons) begin
                if (!sampled_reset && sampled_tick) $fatal(1,"UART_ENDPOINT_INPUT_DOT_EDGE");
                observed_input_dot = observed_dots;
                prior_buttons = buttons;
            end
            if (cpu_fault) $fatal(1,"UART_ENDPOINT_CPU_FAULT");
        end
    end
    // Explicit separate snapshot-owner model. Data and metadata are immutable
    // after publication; this is not a #93 storage implementation substitute.
    always @(posedge clk_sys) begin
        snapshot_done <= 0;
        frame_valid <= frame_read && !reset_sys;
        if (frame_read) frame_data <= 8'((int'(frame_address)*13)^85);
        if (reset_sys) begin
            snapshot_delay <= 0; snapshot_valid <= 0; snapshot_ok <= 0; snapshot_metadata <= '0;
        end else if (snapshot_request && snapshot_ready) snapshot_delay <= 4;
        else if (snapshot_delay != 0) begin
            snapshot_delay <= snapshot_delay - 1;
            if (snapshot_delay == 1) begin
                snapshot_done <= 1; snapshot_ok <= frame_available;
                if (frame_available) begin
                    snapshot_valid <= 1;
                    snapshot_metadata <= {32'd5760,64'(observed_dots),64'd7,epoch};
                end
            end
        end
    end
    function automatic logic [7:0] image_byte(input integer at);
        if (at >= 64 && at < 80) return 0;
        case (at)
            256: return 8'hfb;
            257: return 0;
            258: return 8'h3e;
            259: return 8'h5a;
            260: return 8'h76;
            default: return 8'(((at*29)+(at>>8))^165);
        endcase
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
        logic [7:0] expected;
        source=0;destination=0;
        while (source<reply_size) begin
            code=encoded_reply[source];source=source+1;
            if (code==0 || source+code-1>reply_size) $fatal(1,"UART_ENDPOINT_COBS");
            for(item=1;item<code;item=item+1) begin raw_reply[destination]=encoded_reply[source];destination=destination+1;source=source+1;end
            if(code!=255 && source<reply_size) begin raw_reply[destination]=0;destination=destination+1;end
        end
        if (!waiting_reply || destination!=12+expected_size) $fatal(1,"UART_ENDPOINT_REPLY_SIZE expected=%0d actual=%0d",12+expected_size,destination);
        checksum=65535;
        for(item=0;item<destination-2;item=item+1) checksum=crc_update(checksum,raw_reply[item]);
        if(raw_reply[destination-2]!=8'(checksum) || raw_reply[destination-1]!=8'(checksum>>8)) $fatal(1,"UART_ENDPOINT_CRC");
        if(raw_reply[0]!=1 || raw_reply[1]!=1 || {raw_reply[5],raw_reply[4],raw_reply[3],raw_reply[2]}!=expected_token ||
            raw_reply[6]!=expected_command || raw_reply[7]!=expected_status || {raw_reply[9],raw_reply[8]}!=16'(expected_size))
            $fatal(1,"UART_ENDPOINT_HEADER seq=%0d cmd=%0d status=%0d expected=%0d",expected_token,raw_reply[6],raw_reply[7],expected_status);
        for(payload_index=0;payload_index<expected_size;payload_index=payload_index+1) begin
            expected=expected_payload[payload_index];
            if(dot_reply) expected=8'((input_reply ? observed_input_dot : observed_dots)>>(payload_index*8));
            if(raw_reply[10+payload_index]!==expected) $fatal(1,"UART_ENDPOINT_PAYLOAD cmd=%0d index=%0d expected=%02h actual=%02h",expected_command,payload_index,expected,raw_reply[10+payload_index]);
        end
        if (expected_status==0 && (expected_command==3 || expected_command==7 || expected_command==9) && (!paused || !core_initialized))
            $fatal(1,"UART_ENDPOINT_EARLY_RESET_REPLY");
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
                if(uart_tx!==0) $fatal(1,"UART_ENDPOINT_TX_START");
                for(bit_number=0;bit_number<8;bit_number=bit_number+1) begin repeat(8) @(negedge clk_sys);value[bit_number]=uart_tx;end
                repeat(8) @(negedge clk_sys);
                if(uart_tx!==1) $fatal(1,"UART_ENDPOINT_TX_STOP");
                repeat(4) @(negedge clk_sys);
                if(value==0) check_reply();
                else begin if(reply_size>=270) $fatal(1,"UART_ENDPOINT_TX_OVERFLOW");encoded_reply[reply_size]=value;reply_size=reply_size+1;end
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
        if(waiting_reply) $fatal(1,"UART_ENDPOINT_TIMEOUT token=%0d command=%0d",token,cmd);
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
    task automatic physical_update(input logic [7:0] value);
        @(negedge clk_sys); while(gb_tick) @(negedge clk_sys);
        physical_buttons=value;physical_commit=1;
        @(negedge clk_sys);physical_commit=0;
    endtask
    task automatic input_readbacks(input logic [7:0] host_mask, input logic [7:0] source,
                                   input logic [7:0] physical_mask, input logic [7:0] effective_mask);
        word_request(32'h10020);expect_word({24'd0,host_mask});exchange(2,4,0,4);
        word_request(32'h10044);expect_word({24'd0,source});exchange(2,4,0,4);
        word_request(32'h10048);expect_word({24'd0,physical_mask});exchange(2,4,0,4);
        word_request(32'h1004c);expect_word({24'd0,effective_mask});exchange(2,4,0,4);
        if(buttons!==host_mask || effective_buttons!==effective_mask)$fatal(1,"UART_INPUT_OBSERVATION");
    endtask
    always @(posedge clk_sys) begin
        if(reset_sys) accepted_inputs=0;
        else if(dut.u_input.host_write.valid) accepted_inputs=accepted_inputs+1;
    end
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
        integer at, amount, item, before_writes, before_resets;
        logic [31:0] saved_token;
        clk_sys=0;reset_sys=1;uart_rx=1;ie=0;iflags=0;
        physical_commit=0;physical_buttons=0;accepted_inputs=0;
        frame_available=0;snapshot_delay=0;snapshot_done=0;snapshot_ok=0;snapshot_valid=0;snapshot_metadata='0;
        frame_valid=0;frame_data=0;reply_size=0;expected_size=0;reply_count=0;command_count=0;
        rom_writes=0;reset_count=0;irq_count=0;token=1;waiting_reply=0;forbid_reset=0;dot_reply=0;input_reply=0;
        observed_dots=0;observed_retirements=0;observed_input_dot=0;prior_buttons=0;
        duplicate_fault=$test$plusargs("duplicate_fault");readback_fault=$test$plusargs("readback_fault");
        trace=$fopen("commands.csv","w");if(!trace)$fatal(1,"UART_ENDPOINT_TRACE");
        $fdisplay(trace,"seq,command,status,payload,dots,rom_writes");
        $dumpfile("waves.vcd");
        $dumpvars(0,reset_sys,uart_rx,uart_tx,gb_tick,paused,pause_request,core_reset,core_initialized,
            buttons,physical_commit,physical_buttons,effective_buttons,effective_update,accepted_inputs,
            epoch,dot_count,retirement_count,profile,image_valid,endpoint_state,rom_write,rom_read,
            rom_address,rom_write_data,rom_read_data,rom_read_valid,snapshot_request,snapshot_done,snapshot_valid,
            frame_read,frame_address,frame_data,frame_valid,reply_count,command_count,rom_writes,reset_count);
        repeat(5) @(negedge clk_sys);reset_sys=0;
        if($test$plusargs("input_mmio")) begin
            input_readbacks(0,0,0,0);
            physical_update(8'ha5);input_readbacks(0,0,8'ha5,0);
            host_write_request(32'h10020,32'h3c);expect_dot(0);exchange(14,8,0,8);
            input_readbacks(8'h3c,0,8'ha5,8'h3c);
            host_write_request(32'h10044,1);expect_dot(0);exchange(14,8,0,8);
            input_readbacks(8'h3c,1,8'ha5,8'ha5);
            request_payload[0]=8'hc3;expect_dot(0);exchange(11,1,0,8);
            input_readbacks(8'hc3,1,8'ha5,8'ha5);
            physical_update(8'h5a);input_readbacks(8'hc3,1,8'h5a,8'h5a);
            host_write_request(32'h10044,0);expect_dot(0);exchange(14,8,0,8);
            if(accepted_inputs!=4)$fatal(1,"UART_INPUT_WRITE_COUNT expected=4 actual=%0d",accepted_inputs);
            saved_token=token;before_writes=accepted_inputs;
            token=saved_token-1;exchange(14,8,0,8);token=saved_token;
            if(accepted_inputs!=before_writes)$fatal(1,"UART_INPUT_REPLAY_EFFECT");
            input_readbacks(8'hc3,0,8'h5a,8'hc3);
            for(item=0;item<8;item=item+1) begin
                case(item)
                    0:host_write_request(32'hff00,0);
                    1:host_write_request(32'h10021,0);
                    2:host_write_request(32'h10000,0);
                    3:host_write_request(32'h10048,0);
                    4:host_write_request(32'h1004c,0);
                    5:host_write_request(32'h10050,0);
                    6:host_write_request(32'h10020,256);
                    7:host_write_request(32'h10044,2);
                endcase
                exchange(14,8,4,0);
            end
            host_write_request(32'h10020,0);exchange(14,7,3,0);
            if(accepted_inputs!=before_writes)$fatal(1,"UART_INPUT_INVALID_EFFECT");
            input_readbacks(8'hc3,0,8'h5a,8'hc3);
            begin_image();input_readbacks(0,0,8'h5a,0);
            host_write_request(32'h10044,2);exchange(14,7,3,0);exchange(14,8,4,0);
            host_write_request(32'h10044,1);exchange(14,8,5,0);
            input_readbacks(0,0,8'h5a,0);
            if(accepted_inputs!=before_writes)$fatal(1,"UART_INPUT_LOADING_EFFECT");
            $fclose(trace);$display("PASS UART_INPUT_MMIO writes=4 invalid=12 replay=1 physical_reset_retained");$finish;
        end
        expect_word(1);exchange(1,0,0,4);
        word_request(32'h1000c);expect_word(0);exchange(2,4,0,4);
        exchange(3,0,5,0);exchange(4,0,5,0);
        word_request(32'h10001);exchange(2,4,4,0);word_request(32'hffff);exchange(2,4,4,0);
        exchange(255,0,2,0);request_payload[0]=1;exchange(1,1,3,0);
        exchange_header(1,0,0,2,1,0);exchange_header(1,0,1,1,3,0);
        begin_image();before_resets=reset_count;before_writes=rom_writes;
        saved_token=token;token=token-1;forbid_reset=1;
        if(duplicate_fault) force dut.core_reset=1;
        exchange(7,9,0,0);forbid_reset=0;token=saved_token;
        if(reset_count!=before_resets || rom_writes!=before_writes) $fatal(1,"UART_ENDPOINT_REPLAY_EFFECT");
        // A conflicting reuse cannot replace the completed exchange cache.
        token=saved_token-1;request_payload[0]=2;exchange(7,9,9,0);
        token=saved_token-1;request_payload[0]=1;forbid_reset=1;exchange(7,9,0,0);forbid_reset=0;
        token=saved_token;
        if(reset_count!=before_resets || rom_writes!=before_writes) $fatal(1,"UART_ENDPOINT_SEQUENCE_EFFECT");
        exchange(9,0,6,0);exchange(4,0,5,0);exchange(3,0,5,0);exchange(11,1,5,0);
        for(at=0;at<32768;at=at+252) begin
            amount=32768-at<252 ? 32768-at : 252;
            word_request(32'(at));for(item=0;item<amount;item=item+1)request_payload[4+item]=image_byte(at+item);
            exchange(8,amount+4,0,0);
        end
        if(rom_writes!=32768) $fatal(1,"UART_ENDPOINT_LOAD_WRITES");
        exchange(9,0,0,0);
        if(!image_valid || endpoint_state!=0 || dot_count!=0) $fatal(1,"UART_ENDPOINT_LOAD_PUBLISH");
        if(readback_fault) force dut.rom_read_data=8'h00;
        for(at=0;at<32768;at=at+256) begin
            word_request(32'(at));request_payload[4]=0;request_payload[5]=1;
            for(item=0;item<256;item=item+1) expected_payload[item]=image_byte(at+item);
            exchange(10,6,0,256);
        end
        word_request(32'hffffffff);request_payload[4]=1;request_payload[5]=0;exchange(10,6,4,0);
        word_request(32768);request_payload[4]=1;exchange(10,6,4,0);
        word_request(0);request_payload[4]=0;request_payload[5]=0;exchange(10,6,4,0);
        word_request(0);exchange(6,4,4,0);word_request(70225);exchange(6,4,4,0);
        word_request(70224);expect_dot(8);exchange(6,4,0,8);
        expect_dot(12);exchange(6,4,0,8);expect_dot(20);exchange(6,4,0,8);expect_dot(24);exchange(6,4,0,8);
        word_request(5);exchange(6,4,8,0);if(dot_count!=29 || !paused)$fatal(1,"UART_ENDPOINT_STEP_LIMIT");
        for(item=0;item<10;item=item+1) begin
            request_payload[0]=item<8 ? 8'(1<<item) : (item==8 ? 255 : 0);
            expect_dot(29);exchange(11,1,0,8);
            if(buttons!==request_payload[0] || dot_count!=29)$fatal(1,"UART_ENDPOINT_BUTTONS");
        end
        exchange(4,0,0,0);
        before_writes=rom_writes;word_request(0);request_payload[4]=8'h11;exchange(8,5,5,0);
        if(rom_writes!=before_writes)$fatal(1,"UART_ENDPOINT_RUNNING_REJECT");
        request_payload[0]=8'hff;dot_reply=1;input_reply=1;exchange(11,1,0,8);input_reply=0;
        exchange(5,0,0,8);dot_reply=0;
        if(!paused || buttons!=255)$fatal(1,"UART_ENDPOINT_HALT_INPUT");
        exchange(3,0,0,0);
        if(buttons!=0 || dot_count!=0 || retirement_count!=0 || !image_valid)$fatal(1,"UART_ENDPOINT_RESET_STATE");
        ie=1;iflags=1;word_request(70224);expect_dot(8);exchange(6,4,0,8);
        expect_dot(12);exchange(6,4,0,8);expect_dot(36);exchange(6,4,0,8);
        if(irq_count!=1 || retirement_count!=4)$fatal(1,"UART_ENDPOINT_STEP_IRQ");
        word_request(0);request_payload[4]=1;request_payload[5]=0;exchange(13,6,7,0);exchange(12,0,7,0);
        frame_available=1;
        for(item=0;item<24;item=item+1) expected_payload[item]=0;
        for(item=0;item<4;item=item+1)expected_payload[item]=8'(epoch>>(item*8));
        expected_payload[4]=7;expected_payload[12]=36;expected_payload[20]=128;expected_payload[21]=22;
        exchange(12,0,0,24);
        word_request(5759);request_payload[4]=1;request_payload[5]=0;expected_payload[0]=8'((5759*13)^85);exchange(13,6,0,1);
        word_request(5760);exchange(13,6,4,0);
        frame_available=0;exchange(3,0,0,0);exchange(12,0,7,0);
        word_request(5759);request_payload[4]=1;request_payload[5]=0;exchange(13,6,0,1);
        if(!snapshot_valid)$fatal(1,"UART_ENDPOINT_SNAPSHOT_RESET");
        // Every generated host word is independently addressed while paused.
        for(item=0;item<12;item=item+1) begin
            word_request(32'h10000+32'(item*4));
            case(item)
                0,2,3,9: expect_word(1);
                10: expect_word(7);
                default: expect_word(0);
            endcase
            exchange(2,4,0,4);
        end
        word_request(32'h10040);expect_word(epoch-1);exchange(2,4,0,4);
        word_request(32'h10050);exchange(2,4,4,0);
        word_request(32'h10030);expect_word(32'h89abcdef);exchange(2,4,0,4);
        word_request(32'h10034);expect_word(32'h01234567);exchange(2,4,0,4);
        word_request(32'h10038);expect_word(32'h76543210);exchange(2,4,0,4);
        word_request(32'h1003c);expect_word(32'hfedcba98);exchange(2,4,0,4);
        if(reply_count!=command_count)$fatal(1,"UART_ENDPOINT_REPLY_COUNT");
        $fclose(trace);$display("PASS UART endpoint full_wire ROM32768 reset_ack replay STEP IRQ input snapshot host_space commands=%0d",command_count);$finish;
    end
    initial begin #150000000;$fatal(1,"UART_ENDPOINT_WATCHDOG");end
endmodule
`default_nettype wire
