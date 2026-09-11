`timescale 1ns/1ps
`default_nettype none
// Full-wire host peek. Bytes are placed through the core's own arbitrated
// access port and read back over UART from the five non-ROM stores while the
// core is paused. Contract: wiki/src/rtl/memory/MAS_memory.md.
module tb_uart_peek;
    logic clk_sys, reset_sys, uart_rx, uart_tx;
    logic gb_tick, paused, pause_request, core_reset, core_initialized;
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
    integer snapshot_delay;
    logic memory_initialized, access_read, access_write, access_valid;
    n2m_memory_pkg::memory_store_t access_store;
    logic [14:0] access_address;
    logic [7:0] access_wdata, access_rdata;
    logic peek_read, peek_valid;
    logic [7:0] peek_select, peek_rdata;
    logic [12:0] peek_offset;
    logic [7:0] unused_vram, unused_wave;
    logic [15:0] unused_oam;
    logic unused_vram_valid, unused_wave_valid, unused_oam_valid;
    logic physical_commit;
    logic [7:0] physical_buttons, effective_buttons;
    n2m_input_pkg::input_update_t effective_update;
    logic [7:0] request_payload [0:255];
    logic [7:0] expected_payload [0:255];
    logic [7:0] raw_request [0:267];
    logic [7:0] encoded_request [0:270];
    logic [7:0] encoded_reply [0:270];
    logic [7:0] raw_reply [0:267];
    integer encoded_size, reply_size, expected_size, command_count, trace;
    integer peeked, rejected;
    logic [31:0] token, expected_token;
    logic [7:0] expected_command, expected_status;
    bit waiting_reply, peek_fault, skip_payload;

    n2m_uart #(.CLOCK_HZ(100000),.BAUD(12500)) dut (
        .input_source_observe(),
        .clk_sys(clk_sys),.reset_sys(reset_sys),.uart_rx(uart_rx),.uart_tx(uart_tx),
        .build_id(128'hfedcba98765432100123456789abcdef),.gb_tick(gb_tick),.paused(paused),
        .core_initialized(core_initialized),.instruction_complete(1'b0),
        .retirement_valid(1'b0),.cpu_stopped(1'b0),.pause_request(pause_request),
        .physical_commit(physical_commit),.physical_buttons(physical_buttons),
        .effective_buttons(effective_buttons),.effective_update(effective_update),
        .core_reset(core_reset),.buttons(buttons),.epoch(epoch),.dot_count(dot_count),
        .retirement_count(retirement_count),.profile(profile),.image_valid(image_valid),
        .endpoint_state(endpoint_state),.rom_write(rom_write),.rom_read(rom_read),
        .rom_address(rom_address),.rom_write_data(rom_write_data),.rom_read_data(rom_read_data),
        .rom_read_valid(rom_read_valid),.snapshot_request(snapshot_request),.snapshot_ready(snapshot_ready),
        .snapshot_done(snapshot_done),.snapshot_ok(snapshot_ok),.snapshot_valid(snapshot_valid),
        .snapshot_metadata(snapshot_metadata),.frame_read(frame_read),.frame_address(frame_address),
        .frame_data(frame_data),.frame_valid(frame_valid),
        // This fixture has no PPU or timer; the live I/O view is not read here.
        .io_lcdc(8'd0), .io_stat(8'd0), .io_ly(8'd0), .io_lyc(8'd0), .io_scy(8'd0),
        .io_scx(8'd0), .io_wy(8'd0), .io_wx(8'd0), .io_bgp(8'd0), .io_obp0(8'd0),
        .io_obp1(8'd0), .io_div(8'd0), .io_tima(8'd0), .io_tma(8'd0), .io_tac(8'd0),
        .io_if(8'd0), .io_ie(8'd0),
        .peek_read(peek_read),.peek_select(peek_select),.peek_offset(peek_offset),
        .peek_rdata(peek_rdata),.peek_valid(peek_valid)
    );
    n2m_timebase u_timebase (.clk_sys(clk_sys),.reset_sys(reset_sys),.core_reset(core_reset),
        .pause_request(pause_request),.gb_tick(gb_tick),.paused(paused));
    n2m_memory_stores u_memory (.oam_request('0), .oam_response(),
        .clk_sys(clk_sys),.reset_sys(reset_sys),.core_reset(core_reset),.init_done(memory_initialized),
        .access_read(access_read),.access_write(access_write),.access_store(access_store),
        .access_address(access_address),.access_wdata(access_wdata),
        .access_rdata(access_rdata),.access_valid(access_valid),
        .host_read(rom_read),.host_write(rom_write),.host_offset({17'b0,rom_address}),
        .host_wdata(rom_write_data),.host_rdata(rom_read_data),.host_valid(rom_read_valid),
        .ppu_vram_read(1'b0),.ppu_vram_address(13'd0),.ppu_vram_rdata(unused_vram),.ppu_vram_valid(unused_vram_valid),
        .ppu_oam_read(1'b0),.ppu_oam_pair(7'd0),.ppu_oam_rdata(unused_oam),.ppu_oam_valid(unused_oam_valid),
        .wave_read(1'b0),.wave_write(1'b0),.wave_wdata(8'd0),.wave_address(4'd0),
        .wave_rdata(unused_wave),.wave_valid(unused_wave_valid),
        .core_paused(paused),.peek_read(peek_read),.peek_select(peek_select),.peek_offset(peek_offset),
        .peek_rdata(peek_rdata),.peek_valid(peek_valid)
    );
    assign core_initialized = memory_initialized;
    assign snapshot_ready = snapshot_delay == 0;
    always #5 clk_sys = !clk_sys;

    // Separate snapshot-owner model; peek must not disturb its held bytes.
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
                snapshot_done <= 1; snapshot_ok <= 1; snapshot_valid <= 1;
                snapshot_metadata <= {32'd5760,64'd0,64'd7,epoch};
            end
        end
    end

    function automatic integer store_bytes(input integer selector);
        case (selector)
            1, 3: return 8192;
            2: return 127;
            4: return 160;
            5: return 16;
            default: return 0;
        endcase
    endfunction
    function automatic logic [7:0] store_byte(input integer selector, input integer offset);
        return 8'((selector*53 + offset*31 + offset/256) ^ 90);
    endfunction
    // The same image and CRC32 the endpoint fixture loads.
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
        source=0;destination=0;
        while (source<reply_size) begin
            code=encoded_reply[source];source=source+1;
            if (code==0 || source+code-1>reply_size) $fatal(1,"UART_PEEK_COBS");
            for(item=1;item<code;item=item+1) begin raw_reply[destination]=encoded_reply[source];destination=destination+1;source=source+1;end
            if(code!=255 && source<reply_size) begin raw_reply[destination]=0;destination=destination+1;end
        end
        if (!waiting_reply || destination!=12+expected_size) $fatal(1,"UART_PEEK_REPLY_SIZE expected=%0d actual=%0d",12+expected_size,destination);
        checksum=65535;
        for(item=0;item<destination-2;item=item+1) checksum=crc_update(checksum,raw_reply[item]);
        if(raw_reply[destination-2]!=8'(checksum) || raw_reply[destination-1]!=8'(checksum>>8)) $fatal(1,"UART_PEEK_CRC");
        if(raw_reply[0]!=1 || raw_reply[1]!=1 || {raw_reply[5],raw_reply[4],raw_reply[3],raw_reply[2]}!=expected_token ||
            raw_reply[6]!=expected_command || raw_reply[7]!=expected_status || {raw_reply[9],raw_reply[8]}!=16'(expected_size))
            $fatal(1,"UART_PEEK_HEADER seq=%0d cmd=%0d status=%0d expected=%0d",expected_token,raw_reply[6],raw_reply[7],expected_status);
        for(payload_index=0;payload_index<expected_size && !skip_payload;payload_index=payload_index+1)
            if(raw_reply[10+payload_index]!==expected_payload[payload_index])
                $fatal(1,"UART_PEEK_PAYLOAD cmd=%0d index=%0d expected=%02h actual=%02h",
                    expected_command,payload_index,expected_payload[payload_index],raw_reply[10+payload_index]);
        $fdisplay(trace,"%0d,%0d,%0d,%0d",expected_token,expected_command,expected_status,expected_size);
        waiting_reply=0;reply_size=0;
    endtask
    initial begin : pin_monitor
        integer bit_number;
        logic [7:0] value;
        forever begin
            @(negedge uart_tx);
            if (!reset_sys) begin
                repeat(4) @(negedge clk_sys);
                if(uart_tx!==0) $fatal(1,"UART_PEEK_TX_START");
                for(bit_number=0;bit_number<8;bit_number=bit_number+1) begin repeat(8) @(negedge clk_sys);value[bit_number]=uart_tx;end
                repeat(8) @(negedge clk_sys);
                if(uart_tx!==1) $fatal(1,"UART_PEEK_TX_STOP");
                repeat(4) @(negedge clk_sys);
                if(value==0) check_reply();
                else begin if(reply_size>=270) $fatal(1,"UART_PEEK_TX_OVERFLOW");encoded_reply[reply_size]=value;reply_size=reply_size+1;end
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
        while(waiting_reply && cycles<180000) begin @(negedge clk_sys);cycles=cycles+1;end
        if(waiting_reply) $fatal(1,"UART_PEEK_TIMEOUT token=%0d command=%0d",token,cmd);
        repeat(4) @(negedge clk_sys);token=token+1;command_count=command_count+1;
    endtask
    task automatic peek_request(input integer selector, input logic [31:0] offset, input integer count);
        integer item;
        request_payload[0]=8'(selector);
        for(item=0;item<4;item=item+1) request_payload[1+item]=8'(offset>>(item*8));
        request_payload[5]=8'(count);request_payload[6]=8'(count>>8);
    endtask
    task automatic range_request(input integer offset, input integer count);
        integer item;
        for(item=0;item<4;item=item+1) request_payload[item]=8'(offset>>(item*8));
        request_payload[4]=8'(count);request_payload[5]=8'(count>>8);
    endtask
    // Seed one store through the core's arbitrated port, never through peek.
    task automatic seed_store(input integer selector);
        integer item;
        @(negedge clk_sys);
        access_store=n2m_memory_pkg::memory_store_t'(selector);
        access_write=1;
        for(item=0;item<store_bytes(selector);item=item+1) begin
            access_address=15'(item);access_wdata=store_byte(selector,item);
            @(negedge clk_sys);
        end
        access_write=0;access_address=0;access_wdata=0;
    endtask
    task automatic peek_store(input integer selector);
        integer offset, amount, item;
        for(offset=0;offset<store_bytes(selector);offset=offset+256) begin
            amount = store_bytes(selector)-offset < 256 ? store_bytes(selector)-offset : 256;
            peek_request(selector,32'(offset),amount);
            for(item=0;item<amount;item=item+1) expected_payload[item]=store_byte(selector,offset+item);
            exchange(16,7,0,amount);
            peeked=peeked+amount;
        end
    endtask
    task automatic reject(input integer selector, input logic [31:0] offset, input integer count,
                          input integer size, input logic [7:0] status);
        peek_request(selector,offset,count);
        exchange(16,size,status,0);
        rejected=rejected+1;
    endtask
    initial begin
        integer at, amount, item, selector;
        logic [7:0] held;
        clk_sys=0;reset_sys=1;uart_rx=1;physical_commit=0;physical_buttons=0;
        access_read=0;access_write=0;access_store=n2m_memory_pkg::STORE_ROM;
        access_address=0;access_wdata=0;
        reply_size=0;expected_size=0;command_count=0;token=1;waiting_reply=0;
        peeked=0;rejected=0;
        snapshot_delay=0;snapshot_done=0;snapshot_ok=0;snapshot_valid=0;snapshot_metadata='0;
        frame_valid=0;frame_data=0;
        peek_fault=$test$plusargs("peek_fault");skip_payload=0;
        trace=$fopen("commands.csv","w");if(!trace)$fatal(1,"UART_PEEK_TRACE");
        $fdisplay(trace,"seq,command,status,payload");
        $dumpfile("waves.vcd");
        $dumpvars(0,reset_sys,uart_rx,uart_tx,gb_tick,paused,core_reset,endpoint_state,image_valid,
            peek_read,peek_select,peek_offset,peek_rdata,peek_valid,frame_read,frame_valid,
            snapshot_request,snapshot_valid,peeked,rejected,command_count);
        repeat(5) @(negedge clk_sys);reset_sys=0;
        request_payload[0]=1;request_payload[1]=0;request_payload[2]=128;request_payload[3]=0;request_payload[4]=0;
        request_payload[5]=8'h28;request_payload[6]=8'h46;request_payload[7]=8'hbb;request_payload[8]=8'h83;
        exchange(7,9,0,0);
        // LOADING refuses peek before it can reach any store.
        reject(1,32'd0,1,7,5);
        for(at=0;at<32768;at=at+252) begin
            amount=32768-at<252 ? 32768-at : 252;
            range_request(at,0);
            for(item=0;item<amount;item=item+1)request_payload[4+item]=image_byte(at+item);
            exchange(8,amount+4,0,0);
        end
        exchange(9,0,0,0);
        if(!image_valid || endpoint_state!=0) $fatal(1,"UART_PEEK_LOAD_PUBLISH");
        // LOAD_END resets the core and clears every store, so seed afterwards.
        for(selector=1;selector<=5;selector=selector+1) seed_store(selector);
        if(peek_fault) force dut.peek_rdata=8'h00;
        for(selector=1;selector<=5;selector=selector+1) peek_store(selector);
        // Structural refusals, each before any store is addressed.
        reject(0,32'd0,1,7,4);
        reject(6,32'd0,1,7,4);
        reject(255,32'd0,1,7,4);
        reject(1,32'd0,0,7,4);
        reject(1,32'd0,257,7,4);
        reject(1,32'd8192,1,7,4);
        reject(1,32'd8191,2,7,4);
        reject(2,32'd127,1,7,4);
        reject(4,32'd160,1,7,4);
        reject(5,32'd16,1,7,4);
        reject(3,32'hffffffff,1,7,4);
        reject(1,32'd0,1,6,3);
        reject(1,32'd0,1,8,3);
        // Peek and snapshot readback are independent: disjoint storage, and a
        // peek between chunks leaves the held frame byte unchanged.
        for(item=0;item<24;item=item+1) expected_payload[item]=0;
        for(item=0;item<4;item=item+1) expected_payload[item]=8'(epoch>>(item*8));
        expected_payload[4]=7;expected_payload[20]=8'h80;expected_payload[21]=8'h16;
        exchange(12,0,0,24);
        range_request(5759,1);expected_payload[0]=8'((5759*13)^85);exchange(13,6,0,1);
        held=expected_payload[0];
        peek_request(1,32'd0,1);expected_payload[0]=store_byte(1,0);exchange(16,7,0,1);
        range_request(5759,1);expected_payload[0]=held;exchange(13,6,0,1);
        if(!snapshot_valid) $fatal(1,"UART_PEEK_SNAPSHOT_HELD");
        // A running core refuses every peek, and pausing restores service.
        exchange(4,0,0,0);
        if(endpoint_state!=1) $fatal(1,"UART_PEEK_NOT_RUNNING");
        for(selector=1;selector<=5;selector=selector+1) reject(selector,32'd0,1,7,5);
        skip_payload=1;exchange(5,0,0,8);skip_payload=0;
        if(endpoint_state!=0) $fatal(1,"UART_PEEK_NOT_PAUSED");
        peek_request(3,32'd8191,1);expected_payload[0]=store_byte(3,8191);exchange(16,7,0,1);
        peeked=peeked+1;
        $fclose(trace);
        $display("PASS UART peek wire stores=5 bytes=%0d rejected=%0d commands=%0d",peeked,rejected,command_count);
        $finish;
    end
    initial begin #150000000;$fatal(1,"UART_PEEK_WATCHDOG");end
endmodule
`default_nettype wire
