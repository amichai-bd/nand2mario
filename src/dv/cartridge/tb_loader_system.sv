`timescale 1ns/1ps
`default_nettype none
// Loader profile in the composed system: the real CPU runs a menu program
// from SDRAM, the host drives the UART wire, the SDRAM controller and device
// model hold a fixture library. Contract:
// wiki/src/rtl/cartridge/MAS_loader_profile.md#host-interaction and the
// issue #667 goal. Fixtures: `host` (LOAD_BEGIN during a swap and a fill,
// SDRAM line round trips, LIBRARY_STATUS, the LIBRARY_CONTROL return, a
// direct host load after a swap, CRC-mismatch recovery) and `menu` (the menu
// selects slots through the joypad, each game boots, KEY1 returns). KEY1 uses
// shortened thresholds here; tb_loader proves the real 5 ms / 0.5 s timing.
// Lint waiver: integer arithmetic on byte and address values.
/* verilator lint_off WIDTHEXPAND */
/* verilator lint_off WIDTHTRUNC */
module tb_loader_system #(
    parameter int unsigned KEY1_DEBOUNCE_EDGES = 5000,
    parameter int unsigned KEY1_HOLD_EDGES = 50000
);
    import n2m_interfaces_pkg::*;
    localparam int IMAGES = 17;
    localparam int SLOT = 32768;
    localparam int LIBRARY_BYTES = 32'h8C000;
    localparam int MENU = 16;
    localparam int SWAP_BOUND = 80000;
    localparam int FILL_BOUND = 40000;
    localparam logic [7:0] STATE_RUN = STATE_RUNNING;
    localparam logic [7:0] STATE_PAUSE = STATE_PAUSED;
    localparam logic [7:0] STATE_LOAD = STATE_LOADING;

    logic clk_sys, clk_pix, reset_sys, reset_pix, uart_rx, uart_tx, key1_n;
    logic physical_commit;
    logic [7:0] physical_buttons;
    logic [3:0] red, green, blue;
    logic hsync_n, vsync_n;
    logic [63:0] display_sequence, dot_count;
    logic [31:0] display_epoch, epoch;
    logic gb_tick, paused, core_reset, fault;
    logic sdram_initialized, sdram_request_valid, sdram_request_write, sdram_request_ready, sdram_response_valid, sdram_idle;
    logic [25:0] sdram_request_address;
    logic [127:0] sdram_request_data, sdram_response_data;
    logic [12:0] dram_addr;
    logic [1:0] dram_ba;
    logic dram_cas_n, dram_cke, dram_clk, dram_cs_n, dram_dqml, dram_dqmh, dram_ras_n, dram_we_n;
    tri [15:0] dram_dq;
    logic [31:0] model_refreshes, model_reads, model_writes;
    // Wire driver state (3.125 MBaud: eight system clocks per bit).
    logic [7:0] request_payload [0:255];
    logic [7:0] expected_payload [0:255];
    logic [7:0] expected_mask [0:255];
    logic [7:0] raw_request [0:267];
    logic [7:0] encoded_request [0:270];
    logic [7:0] encoded_reply [0:270];
    logic [7:0] raw_reply [0:267];
    integer encoded_size, reply_size, expected_size, command_count;
    logic [31:0] token, expected_token;
    logic [7:0] expected_command, expected_status;
    bit waiting_reply, ignore_payload;
    string fixture;
    logic [255:0] entries [0:IMAGES-1];
    logic [31:0] image_crc [0:IMAGES-1];
    integer checks, swaps, returns;

    n2m_v05_system #(.UART_BAUD(3125000), .KEY1_DEBOUNCE_EDGES(KEY1_DEBOUNCE_EDGES), .KEY1_HOLD_EDGES(KEY1_HOLD_EDGES)) dut (
        .clk_sys, .reset_sys, .clk_pix, .reset_pix, .uart_rx, .uart_tx,
        .physical_commit, .physical_buttons, .effective_buttons(), .input_source_observe(),
        .red, .green, .blue, .hsync_n, .vsync_n, .display_sequence, .display_epoch,
        .gb_tick, .paused, .core_reset, .epoch, .dot_count, .retirement_valid(), .retirement(),
        .bus_commit(), .write_enable(), .address(), .write_data(), .read_data(), .irq_ack(),
        .source_valid(), .source_start(), .source_abort(), .source_display_eligible(), .source_shade(),
        .source_x(), .source_y(), .source_epoch(), .source_dot(), .fault,
        .key1_n, .sdram_initialized, .sdram_request_valid, .sdram_request_write, .sdram_request_address,
        .sdram_request_data, .sdram_request_ready, .sdram_response_valid, .sdram_response_data
    );
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
    always #19.841 clk_pix = !clk_pix;
    always @(posedge clk_sys) if (!reset_sys && fault) $fatal(1, "LOADER_SYS_FAULT");

    // The library. Games hold an endless loop at the entry point and their
    // slot number at $0150; the menu polls the action buttons and selects
    // the pressed nibble, refilling window bank 33 while nothing is pressed.
    function automatic logic [7:0] menu_byte(input int offset);
        case (offset)
            16'h0100: return 8'h3E; 16'h0101: return 8'h21;                        // ld a,$21
            16'h0102: return 8'hEA; 16'h0103: return 8'h00; 16'h0104: return 8'h20; // ld ($2000),a
            16'h0105: return 8'hFA; 16'h0106: return 8'h00; 16'h0107: return 8'hA0; // ld a,($A000)
            16'h0108: return 8'hCB; 16'h0109: return 8'h7F;                        // bit 7,a
            16'h010A: return 8'h20; 16'h010B: return 8'hF9;                        // jr nz,$0105
            16'h010C: return 8'h3E; 16'h010D: return 8'h10;                        // ld a,$10
            16'h010E: return 8'hE0; 16'h010F: return 8'h00;                        // ldh ($FF00),a
            16'h0110: return 8'hF0; 16'h0111: return 8'h00;                        // ldh a,($FF00)
            16'h0112: return 8'h2F;                                                // cpl
            16'h0113: return 8'hE6; 16'h0114: return 8'h0F;                        // and $0F
            16'h0115: return 8'h28; 16'h0116: return 8'hE9;                        // jr z,$0100
            16'h0117: return 8'hEA; 16'h0118: return 8'h00; 16'h0119: return 8'h60; // ld ($6000),a
            16'h011A: return 8'h18; 16'h011B: return 8'hFE;                        // jr $011A
            default: return 8'h00;
        endcase
    endfunction
    function automatic logic [7:0] image_byte(input int index, input int offset);
        if (index == MENU) return menu_byte(offset);
        if (offset == 16'h0100) return 8'h18;
        if (offset == 16'h0101) return 8'hFE;
        if (offset == 16'h0150) return 8'(index);
        if (offset >= 16'h4000) return 8'((index * 37 + offset * 11 + (offset >> 7) * 5) ^ (offset >> 12));
        return 8'h00;
    endfunction
    function automatic logic [7:0] library_byte(input int address);
        int entry, offset;
        if (address < IMAGES * SLOT) return image_byte(address / SLOT, address % SLOT);
        if (address < 32'h88000 + IMAGES * 32) begin
            entry = (address - 32'h88000) / 32;
            offset = (address - 32'h88000) % 32;
            return entries[entry][offset*8 +: 8];
        end
        return 8'h00;
    endfunction
    task automatic build_library;
        int index, offset, k;
        logic [31:0] crc;
        logic [255:0] entry;
        for (index = 0; index < IMAGES; index = index + 1) begin
            crc = WIRE_CRC32_INIT;
            for (offset = 0; offset < SLOT; offset = offset + 1)
                crc = n2m_uart_pkg::crc32_byte(crc, image_byte(index, offset));
            image_crc[index] = crc ^ WIRE_CRC32_INIT;
            entry = '0;
            entry[7:0] = LIBRARY_CATALOGUE_VALID;
            entry[15:8] = index == MENU ? PROFILE_LOADER_ID : PROFILE_DIRECT_ID;
            entry[31:16] = 16'(SLOT);
            entry[63:32] = index == 9 ? image_crc[index] ^ 32'h1 : image_crc[index];
            for (k = 0; k < 16; k = k + 1) entry[64 + k*8 +: 8] = image_byte(index, 32'h134 + k);
            entries[index] = entry;
        end
    endtask
    task automatic preload_library;
        int address;
        for (address = 0; address < LIBRARY_BYTES; address = address + 2)
            u_device.preload_word(26'(address), {library_byte(address + 1), library_byte(address)});
    endtask

    // Wire driver: COBS-framed packets with CRC-16, byte level on uart_rx/uart_tx.
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
            if (code==0 || source+code-1>reply_size) $fatal(1,"LOADER_SYS_COBS");
            for(item=1;item<code;item=item+1) begin raw_reply[destination]=encoded_reply[source];destination=destination+1;source=source+1;end
            if(code!=255 && source<reply_size) begin raw_reply[destination]=0;destination=destination+1;end
        end
        if (!waiting_reply || destination!=12+expected_size) $fatal(1,"LOADER_SYS_REPLY_SIZE cmd=%0d expected=%0d actual=%0d status=%0d",expected_command,12+expected_size,destination,raw_reply[7]);
        checksum=65535;
        for(item=0;item<destination-2;item=item+1) checksum=crc_update(checksum,raw_reply[item]);
        if(raw_reply[destination-2]!=8'(checksum) || raw_reply[destination-1]!=8'(checksum>>8)) $fatal(1,"LOADER_SYS_CRC");
        if(raw_reply[0]!=1 || raw_reply[1]!=1 || {raw_reply[5],raw_reply[4],raw_reply[3],raw_reply[2]}!=expected_token ||
            raw_reply[6]!=expected_command || raw_reply[7]!=expected_status || {raw_reply[9],raw_reply[8]}!=16'(expected_size))
            $fatal(1,"LOADER_SYS_HEADER seq=%0d cmd=%0d status=%0d/%0d size=%0d",expected_token,raw_reply[6],raw_reply[7],expected_status,{raw_reply[9],raw_reply[8]});
        if (!ignore_payload)
            for(payload_index=0;payload_index<expected_size;payload_index=payload_index+1)
                if((raw_reply[10+payload_index] & expected_mask[payload_index])!=(expected_payload[payload_index] & expected_mask[payload_index]))
                    $fatal(1,"LOADER_SYS_PAYLOAD cmd=%0d index=%0d expected=%02h actual=%02h",
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
                if(uart_tx!=0) $fatal(1,"LOADER_SYS_TX_START");
                for(bit_number=0;bit_number<8;bit_number=bit_number+1) begin repeat(8) @(negedge clk_sys);value[bit_number]=uart_tx;end
                repeat(8) @(negedge clk_sys);
                if(uart_tx!=1) $fatal(1,"LOADER_SYS_TX_STOP");
                repeat(4) @(negedge clk_sys);
                if(value==0) check_reply();
                else begin if(reply_size>=270) $fatal(1,"LOADER_SYS_TX_OVERFLOW");encoded_reply[reply_size]=value;reply_size=reply_size+1;end
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
        while(waiting_reply && cycles<600000) begin @(negedge clk_sys);cycles=cycles+1;end
        if(waiting_reply) $fatal(1,"LOADER_SYS_TIMEOUT token=%0d command=%0d",token,cmd);
        repeat(4) @(negedge clk_sys);token=token+1;command_count=command_count+1;
        ignore_payload=0;
        for (cycles=0;cycles<256;cycles=cycles+1) expected_mask[cycles]=8'hFF;
        $display("LOADER_SYS command=%0d status=%0d time_ns=%0t", cmd, result_status, $time);
    endtask
    task automatic word_request(input logic [31:0] value);
        integer item;
        for(item=0;item<4;item=item+1) request_payload[item]=8'(value>>(item*8));
    endtask
    task automatic read_host(input logic [31:0] register, input logic [31:0] expected, input string what);
        integer item;
        word_request(register);
        for(item=0;item<4;item=item+1) expected_payload[item]=8'(expected>>(item*8));
        exchange(COMMAND_READ_HOST,4,STATUS_OK,4);
        checks = checks + 1;
    endtask
    // A masked LIBRARY_STATUS read: the running menu refills its window, so
    // copy_busy and window_ready are not stable between two host commands.
    task automatic read_status(input logic [31:0] expected, input logic [31:0] mask, input string what);
        integer item;
        word_request(HOST_REG_LIBRARY_STATUS);
        for(item=0;item<4;item=item+1) begin expected_payload[item]=8'(expected>>(item*8)); expected_mask[item]=8'(mask>>(item*8)); end
        exchange(COMMAND_READ_HOST,4,STATUS_OK,4);
        checks = checks + 1;
    endtask
    task automatic write_host(input logic [31:0] register, input logic [31:0] value, input logic [7:0] status);
        integer item;
        word_request(register);
        for(item=0;item<4;item=item+1) request_payload[4+item]=8'(value>>(item*8));
        ignore_payload = 1;
        exchange(COMMAND_WRITE_HOST,8,status,status==STATUS_OK ? 8 : 0);
        checks = checks + 1;
    endtask
    task automatic simple(input logic [7:0] cmd, input logic [7:0] status, input integer result_size);
        ignore_payload = 1;
        exchange(cmd,0,status,status==STATUS_OK ? result_size : 0);
        checks = checks + 1;
    endtask
    // The board's own joypad producer: one coherent mask on a tick-free edge,
    // usable in every endpoint state like the physical buttons.
    task automatic press_buttons(input logic [7:0] mask);
        @(negedge clk_sys);
        while (gb_tick) @(negedge clk_sys);
        physical_buttons = mask; physical_commit = 1;
        @(negedge clk_sys);
        physical_commit = 0;
    endtask
    task automatic load_begin(input logic [7:0] profile_value, input logic [31:0] crc, input logic [7:0] status);
        integer item;
        request_payload[0]=profile_value;
        for(item=0;item<4;item=item+1) request_payload[1+item]=8'(SLOT>>(item*8));
        for(item=0;item<4;item=item+1) request_payload[5+item]=8'(crc>>(item*8));
        exchange(COMMAND_LOAD_BEGIN,9,status,0);
        checks = checks + 1;
    endtask
    task automatic load_image(input int index);
        integer offset, item, count;
        offset = 0;
        while (offset < SLOT) begin
            count = SLOT - offset < 252 ? SLOT - offset : 252;
            for(item=0;item<4;item=item+1) request_payload[item]=8'(offset>>(item*8));
            for(item=0;item<count;item=item+1) request_payload[4+item]=image_byte(index, offset+item);
            exchange(COMMAND_LOAD_WRITE,4+count,STATUS_OK,0);
            offset = offset + count;
        end
        exchange(COMMAND_LOAD_END,0,STATUS_OK,0);
        checks = checks + 1;
    endtask
    task automatic read_rom(input int index, input logic [15:0] offset, input integer count);
        integer item;
        for(item=0;item<4;item=item+1) request_payload[item]=8'(offset>>(item*8));
        request_payload[4]=8'(count); request_payload[5]=8'(count>>8);
        for(item=0;item<count;item=item+1) expected_payload[item]=image_byte(index, offset+item);
        exchange(COMMAND_READ_ROM,6,STATUS_OK,count);
        checks = checks + 1;
    endtask
    task automatic sdram_write_line(input logic [31:0] address);
        integer item;
        for(item=0;item<4;item=item+1) request_payload[item]=8'(address>>(item*8));
        for(item=0;item<16;item=item+1) request_payload[4+item]=8'(address + item * 13 + 7);
        exchange(COMMAND_SDRAM_WRITE,20,STATUS_OK,0);
        checks = checks + 1;
    endtask
    task automatic sdram_read_line(input logic [31:0] address, input bit written);
        integer item;
        for(item=0;item<4;item=item+1) request_payload[item]=8'(address>>(item*8));
        request_payload[4]=8'd1;
        for(item=0;item<16;item=item+1) expected_payload[item]= written ? 8'(address + item * 13 + 7) : library_byte(address + item);
        exchange(COMMAND_SDRAM_READ,5,STATUS_OK,16);
        checks = checks + 1;
    endtask
    task automatic wait_copy(input int bound, input string what);
        int edges;
        edges = 0;
        while (dut.loader_copy_busy) begin
            @(negedge clk_sys); edges = edges + 1;
            if (edges > bound) $fatal(1, "LOADER_SYS_BOUND %s edges=%0d", what, edges);
        end
    endtask
    task automatic wait_profile(input logic [7:0] wanted, input int bound, input string what);
        int edges;
        edges = 0;
        while (dut.profile != wanted || !dut.image_valid || dut.loader_copy_busy || paused) begin
            @(negedge clk_sys); edges = edges + 1;
            if (edges > bound) $fatal(1, "LOADER_SYS_PROFILE_WAIT %s profile=%02h valid=%b busy=%b paused=%b",
                what, dut.profile, dut.image_valid, dut.loader_copy_busy, paused);
        end
    endtask
    task automatic press_key1;
        key1_n = 0;
        repeat (KEY1_DEBOUNCE_EDGES + KEY1_HOLD_EDGES + 200) @(negedge clk_sys);
        key1_n = 1;
        repeat (KEY1_DEBOUNCE_EDGES + 200) @(negedge clk_sys);
    endtask
    // The host's return through LIBRARY_CONTROL, then the menu running.
    task automatic host_return(input string what);
        logic [31:0] epoch_before;
        epoch_before = epoch;
        write_host(HOST_REG_LIBRARY_CONTROL, LIBRARY_CONTROL_RETURN, STATUS_OK);
        wait_copy(SWAP_BOUND, what);
        if (epoch != epoch_before + 1 || dut.profile != PROFILE_LOADER_ID) $fatal(1, "LOADER_SYS_RETURN %s", what);
        returns = returns + 1;
    endtask

    task automatic fixture_host;
        logic [31:0] epoch_before;
        int edges;
        // Power-up: no image, paused. The return swaps the menu in from SDRAM.
        read_host(HOST_REG_STATE, STATE_PAUSE, "initial state");
        read_host(HOST_REG_LIBRARY_STATUS, 32'h00FF0020, "initial library status");
        epoch_before = epoch;
        write_host(HOST_REG_LIBRARY_CONTROL, LIBRARY_CONTROL_RETURN, STATUS_OK);
        wait_copy(SWAP_BOUND, "first return");
        if (epoch != epoch_before + 1) $fatal(1, "LOADER_SYS_FIRST_EPOCH");
        read_host(HOST_REG_PROFILE, PROFILE_LOADER_ID, "menu profile");
        read_host(HOST_REG_IMAGE_VALID, 1, "menu valid");
        read_host(HOST_REG_STATE, STATE_PAUSE, "menu paused until RUN");
        read_host(HOST_REG_LIBRARY_STATUS, 32'h00FF0120, "menu library status");
        // A control value outside the mask is refused before any effect.
        write_host(HOST_REG_LIBRARY_CONTROL, 32'd2, STATUS_BAD_VALUE);
        write_host(HOST_REG_INPUT_SOURCE, INPUT_SOURCE_PHYSICAL, STATUS_OK);
        simple(COMMAND_RUN, STATUS_OK, 0);
        // The menu fills bank 33 over and over; the host sees the fill state
        // and drives SDRAM lines through the arbiter meanwhile.
        edges = 0;
        while (!dut.loader_copy_busy) begin @(negedge clk_sys); edges = edges + 1; if (edges > 200000) $fatal(1, "LOADER_SYS_NO_FILL"); end
        read_host(HOST_REG_STATE, STATE_RUN, "running during fill");
        sdram_write_line(32'h1000000);
        sdram_read_line(32'h1000000, 1);
        sdram_read_line(32'h0088000, 0);
        read_host(HOST_REG_LIBRARY_KEY1, 0, "key1 idle");
        // LOAD_BEGIN during a fill waits for the fill, then opens the session.
        while (dut.loader_copy_busy) @(negedge clk_sys);
        while (!dut.loader_copy_busy) @(negedge clk_sys);
        load_begin(PROFILE_DIRECT_ID, image_crc[5], STATUS_OK);
        if (dut.loader_copy_busy) $fatal(1, "LOADER_SYS_SESSION_DURING_FILL");
        read_host(HOST_REG_STATE, STATE_LOAD, "loading");
        // A direct host load of a game behaves as today.
        load_image(5);
        read_host(HOST_REG_PROFILE, PROFILE_DIRECT_ID, "game profile after host load");
        read_host(HOST_REG_STATE, STATE_PAUSE, "paused after LOAD_END");
        read_rom(5, 16'h0100, 96);
        simple(COMMAND_RUN, STATUS_OK, 0);
        read_host(HOST_REG_STATE, STATE_RUN, "game running");
        repeat (2000) @(negedge clk_sys);
        // The window state survives untouched in the game profile.
        read_host(HOST_REG_LIBRARY_STATUS, 32'h21FF0120, "status in the game");
        // The return from a running game; LOAD_BEGIN during the swap is refused.
        epoch_before = epoch;
        write_host(HOST_REG_LIBRARY_CONTROL, LIBRARY_CONTROL_RETURN, STATUS_OK);
        if (!dut.loader_swap_busy) $fatal(1, "LOADER_SYS_RETURN_NOT_BUSY");
        load_begin(PROFILE_DIRECT_ID, image_crc[5], STATUS_BAD_STATE);
        wait_copy(SWAP_BOUND, "return from game");
        if (epoch != epoch_before + 1) $fatal(1, "LOADER_SYS_RETURN_EPOCH");
        read_host(HOST_REG_PROFILE, PROFILE_LOADER_ID, "menu again");
        read_host(HOST_REG_STATE, STATE_RUN, "menu runs without RUN");
        returns = returns + 1;
        // CRC mismatch through the menu: LOADING, the control write refused,
        // the physical KEY1 recovers.
        write_host(HOST_REG_INPUT_SOURCE, INPUT_SOURCE_PHYSICAL, STATUS_OK);
        press_buttons(8'h90);
        edges = 0;
        while (dut.image_valid) begin @(negedge clk_sys); edges = edges + 1; if (edges > 400000) $fatal(1, "LOADER_SYS_NO_SELECT"); end
        press_buttons(8'h00);
        wait_copy(SWAP_BOUND, "mismatch swap");
        read_host(HOST_REG_STATE, STATE_LOAD, "loading after mismatch");
        read_host(HOST_REG_PROFILE, 0, "profile cleared");
        read_host(HOST_REG_LIBRARY_STATUS, {2'b0, 6'd33, 8'd9, LIBRARY_RESULT_CRC_MISMATCH, 8'h20}, "mismatch status");
        write_host(HOST_REG_LIBRARY_CONTROL, LIBRARY_CONTROL_RETURN, STATUS_BAD_STATE);
        epoch_before = epoch;
        press_key1();
        wait_copy(SWAP_BOUND, "key1 recovery");
        if (epoch != epoch_before + 1) $fatal(1, "LOADER_SYS_KEY1_EPOCH");
        read_host(HOST_REG_PROFILE, PROFILE_LOADER_ID, "recovered menu");
        read_host(HOST_REG_STATE, STATE_RUN, "recovered running");
        read_status({2'b0, 6'd33, 8'd9, LIBRARY_RESULT_OK, 8'h20}, 32'h3FFFFF3F, "recovered status");
        read_host(HOST_REG_LIBRARY_KEY1, 0, "key1 released");
        returns = returns + 1;
    endtask

    task automatic fixture_menu;
        int slots [0:3];
        int s, edges;
        logic [31:0] epoch_before;
        logic [63:0] dots_before;
        slots = '{1, 2, 3, 15};
        write_host(HOST_REG_LIBRARY_CONTROL, LIBRARY_CONTROL_RETURN, STATUS_OK);
        wait_copy(SWAP_BOUND, "menu");
        simple(COMMAND_RUN, STATUS_OK, 0);
        for (s = 0; s < 4; s = s + 1) begin
            // The pressed action nibble is the slot the menu selects.
            epoch_before = epoch;
            // Every core reset restores UART input ownership; select the board.
            write_host(HOST_REG_INPUT_SOURCE, INPUT_SOURCE_PHYSICAL, STATUS_OK);
            press_buttons(8'(slots[s] << 4));
            wait_profile(PROFILE_DIRECT_ID, 600000, "game");
            if (epoch != epoch_before + 1) $fatal(1, "LOADER_SYS_GAME_EPOCH slot=%0d", slots[s]);
            read_status({2'b0, 6'd33, 8'(slots[s]), LIBRARY_RESULT_OK, 8'h20}, 32'h3FFFFF3F, "game status");
            read_host(HOST_REG_STATE, STATE_RUN, "game running");
            // The game executes: the emulated dot count advances.
            dots_before = dot_count;
            repeat (5000) @(negedge clk_sys);
            if (dot_count <= dots_before) $fatal(1, "LOADER_SYS_GAME_STALLED slot=%0d", slots[s]);
            press_buttons(8'h00);
            swaps = swaps + 1;
            // KEY1 returns to the menu every time.
            epoch_before = epoch;
            press_key1();
            wait_profile(PROFILE_LOADER_ID, SWAP_BOUND, "return");
            if (epoch != epoch_before + 1) $fatal(1, "LOADER_SYS_RETURN_EPOCH slot=%0d", slots[s]);
            read_host(HOST_REG_PROFILE, PROFILE_LOADER_ID, "menu after return");
            returns = returns + 1;
        end
        checks = checks + 1;
    endtask

    initial begin
        clk_sys = 0; clk_pix = 0; reset_sys = 1; reset_pix = 1; uart_rx = 1; key1_n = 1;
        physical_commit = 0; physical_buttons = 0;
        reply_size = 0; expected_size = 0; command_count = 0; token = 1; waiting_reply = 0; ignore_payload = 0;
        checks = 0; swaps = 0; returns = 0;
        for (command_count=0;command_count<256;command_count=command_count+1) expected_mask[command_count]=8'hFF;
        command_count = 0;
        if (!$value$plusargs("fixture=%s", fixture)) fixture = "host";
        build_library();
        $dumpfile("waves.vcd");
        $dumpvars(0, reset_sys, uart_rx, uart_tx, paused, core_reset, epoch, key1_n,
            sdram_request_valid, sdram_request_ready, sdram_response_valid, fault,
            dut.address, dut.read_data, dut.write_enable, dut.bus_commit, dut.request_valid, dut.response_valid,
            dut.loader_read_override, dut.loader_copy_busy, dut.loader_swap_busy, dut.profile, dut.image_valid,
            dut.engine_pause, dut.host_session, dut.host_loading, dut.gb_tick, dut.raw_write, dut.raw_store,
            dut.raw_offset, dut.raw_wdata, dut.rom_host_write, dut.rom_host_offset);
        repeat (5) @(negedge clk_sys);
        reset_sys = 0; reset_pix = 0;
        repeat (3) @(negedge clk_sys);
        preload_library();
        while (!sdram_initialized) @(negedge clk_sys);
        repeat (4) @(negedge clk_sys);
        case (fixture)
            "host": fixture_host();
            "menu": fixture_menu();
            default: $fatal(1, "LOADER_SYS_FIXTURE %s", fixture);
        endcase
        $display("PASS loader-system-%s checks=%0d swaps=%0d returns=%0d commands=%0d", fixture, checks, swaps, returns, command_count);
        $finish;
    end
    initial begin #2000000000; $fatal(1, "LOADER_SYS_WATCHDOG"); end
endmodule
`default_nettype wire
