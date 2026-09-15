`timescale 1ns/1ps
`default_nettype none
// The built menu image in the composed system: the real CPU runs the menu
// from SDRAM slot 16 over the fixture library, the joypad reaches it through
// the physical producer, and every displayed frame is compared pixel for
// pixel with the independent reference. Contract: wiki/src/sw/menu/SPEC.md;
// hardware: wiki/src/rtl/cartridge/MAS_loader_profile.md. The `menu`
// preload writes menu-library.hex (the SDRAM bytes) and menu-frames.hex
// (the scripted reference frames) into the attempt directory.
// Fixtures: `frame` (boot frame, Down, Down, Up), `select` (Down, A: the
// select register receives 1 and the game boots) and `refused` (A on the
// empty slot 3 shows SLOT 03 INVALID, Up, A starts slot 2).
// Lint waiver: integer arithmetic on byte and address values.
/* verilator lint_off WIDTHEXPAND */
/* verilator lint_off WIDTHTRUNC */
module tb_menu_system;
    import n2m_interfaces_pkg::*;
    localparam int LIBRARY_BYTES = 32'h8C000;
    localparam int FRAME_PIXELS = 23040;
    localparam int FRAMES = 6;
    localparam int SWAP_BOUND = 80000;
    localparam logic [7:0] STATE_PAUSE = STATE_PAUSED;

    logic clk_sys, clk_pix, reset_sys, reset_pix, uart_rx, uart_tx, key1_n;
    logic physical_commit;
    logic [7:0] physical_buttons;
    logic [3:0] red, green, blue;
    logic hsync_n, vsync_n;
    logic [63:0] display_sequence, dot_count;
    logic [31:0] display_epoch, epoch;
    logic gb_tick, paused, core_reset, fault;
    logic source_valid, source_start, source_abort, source_display_eligible;
    logic [1:0] source_shade;
    logic [7:0] source_x, source_y;
    logic sdram_initialized, sdram_request_valid, sdram_request_write, sdram_request_ready, sdram_response_valid, sdram_idle;
    logic [25:0] sdram_request_address;
    logic [127:0] sdram_request_data, sdram_response_data;
    logic [12:0] dram_addr;
    logic [1:0] dram_ba;
    logic dram_cas_n, dram_cke, dram_clk, dram_cs_n, dram_dqml, dram_dqmh, dram_ras_n, dram_we_n;
    tri [15:0] dram_dq;
    logic [31:0] model_refreshes, model_reads, model_writes;
    // Fixture inputs prepared by the preload builder.
    logic [7:0] library_mem [0:LIBRARY_BYTES-1];
    logic [7:0] frames_mem [0:FRAMES*FRAME_PIXELS-1];
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
    bit waiting_reply, ignore_payload, pixel_fault;
    string fixture;
    // Passive frame observer: the pixel source of the composed system.
    logic [1:0] captured [0:FRAME_PIXELS-1];
    integer pixel_index, frames_seen, frames_checked, checks, selects;
    bit capturing, frame_complete;
    logic [7:0] select_data;
    bit select_seen;

    n2m_v05_system #(.UART_BAUD(3125000)) dut (
        .clk_sys, .reset_sys, .clk_pix, .reset_pix, .uart_rx, .uart_tx,
        .physical_commit, .physical_buttons, .effective_buttons(), .input_source_observe(),
        .red, .green, .blue, .hsync_n, .vsync_n, .display_sequence, .display_epoch,
        .gb_tick, .paused, .core_reset, .epoch, .dot_count, .retirement_valid(), .retirement(),
        .bus_commit(), .write_enable(), .address(), .write_data(), .read_data(), .irq_ack(),
        .source_valid, .source_start, .source_abort, .source_display_eligible, .source_shade,
        .source_x, .source_y, .source_epoch(), .source_dot(), .fault,
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
    always @(posedge clk_sys) if (!reset_sys && fault) $fatal(1, "MENU_SYS_FAULT");

    task automatic preload_library;
        int address;
        for (address = 0; address < LIBRARY_BYTES; address = address + 2)
            u_device.preload_word(26'(address), {library_mem[address + 1], library_mem[address]});
    endtask

    // Frame observer: pixels of display-eligible frames in source order.
    always @(posedge clk_sys) begin
        if (!reset_sys && source_valid && source_display_eligible) begin
            if (source_start) begin
                pixel_index <= 0;
                frames_seen <= frames_seen + 1;
                capturing <= 1;
                frame_complete <= 0;
                if (source_x != 0 || source_y != 0) $fatal(1, "MENU_SYS_FRAME_START x=%0d y=%0d", source_x, source_y);
                captured[0] <= source_shade;
                pixel_index <= 1;
            end else if (capturing) begin
                if (pixel_index >= FRAME_PIXELS) $fatal(1, "MENU_SYS_EXTRA_PIXEL");
                if (source_x != 8'(pixel_index % 160) || source_y != 8'(pixel_index / 160))
                    $fatal(1, "MENU_SYS_PIXEL_ORDER index=%0d x=%0d y=%0d", pixel_index, source_x, source_y);
                captured[pixel_index] <= source_shade;
                pixel_index <= pixel_index + 1;
                if (pixel_index == FRAME_PIXELS - 1) begin
                    frame_complete <= 1;
                    capturing <= 0;
                end
            end
        end
    end
    // The select register commit: the menu's only write into $6000-$7FFF.
    always @(posedge clk_sys) begin
        if (!reset_sys && dut.bus_commit && dut.write_enable && dut.address >= 16'h6000 && dut.address <= 16'h7FFF) begin
            select_data <= dut.write_data;
            select_seen <= 1;
        end
    end

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
            if (code==0 || source+code-1>reply_size) $fatal(1,"MENU_SYS_COBS");
            for(item=1;item<code;item=item+1) begin raw_reply[destination]=encoded_reply[source];destination=destination+1;source=source+1;end
            if(code!=255 && source<reply_size) begin raw_reply[destination]=0;destination=destination+1;end
        end
        if (!waiting_reply || destination!=12+expected_size) $fatal(1,"MENU_SYS_REPLY_SIZE cmd=%0d expected=%0d actual=%0d status=%0d",expected_command,12+expected_size,destination,raw_reply[7]);
        checksum=65535;
        for(item=0;item<destination-2;item=item+1) checksum=crc_update(checksum,raw_reply[item]);
        if(raw_reply[destination-2]!=8'(checksum) || raw_reply[destination-1]!=8'(checksum>>8)) $fatal(1,"MENU_SYS_CRC");
        if(raw_reply[0]!=1 || raw_reply[1]!=1 || {raw_reply[5],raw_reply[4],raw_reply[3],raw_reply[2]}!=expected_token ||
            raw_reply[6]!=expected_command || raw_reply[7]!=expected_status || {raw_reply[9],raw_reply[8]}!=16'(expected_size))
            $fatal(1,"MENU_SYS_HEADER seq=%0d cmd=%0d status=%0d/%0d size=%0d",expected_token,raw_reply[6],raw_reply[7],expected_status,{raw_reply[9],raw_reply[8]});
        if (!ignore_payload)
            for(payload_index=0;payload_index<expected_size;payload_index=payload_index+1)
                if((raw_reply[10+payload_index] & expected_mask[payload_index])!=(expected_payload[payload_index] & expected_mask[payload_index]))
                    $fatal(1,"MENU_SYS_PAYLOAD cmd=%0d index=%0d expected=%02h actual=%02h",
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
                if(uart_tx!=0) $fatal(1,"MENU_SYS_TX_START");
                for(bit_number=0;bit_number<8;bit_number=bit_number+1) begin repeat(8) @(negedge clk_sys);value[bit_number]=uart_tx;end
                repeat(8) @(negedge clk_sys);
                if(uart_tx!=1) $fatal(1,"MENU_SYS_TX_STOP");
                repeat(4) @(negedge clk_sys);
                if(value==0) check_reply();
                else begin if(reply_size>=270) $fatal(1,"MENU_SYS_TX_OVERFLOW");encoded_reply[reply_size]=value;reply_size=reply_size+1;end
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
        if(waiting_reply) $fatal(1,"MENU_SYS_TIMEOUT token=%0d command=%0d",token,cmd);
        repeat(4) @(negedge clk_sys);token=token+1;command_count=command_count+1;
        ignore_payload=0;
        for (cycles=0;cycles<256;cycles=cycles+1) expected_mask[cycles]=8'hFF;
    endtask
    task automatic word_request(input logic [31:0] value);
        integer item;
        for(item=0;item<4;item=item+1) request_payload[item]=8'(value>>(item*8));
    endtask
    task automatic read_host(input logic [31:0] register, input logic [31:0] expected);
        integer item;
        word_request(register);
        for(item=0;item<4;item=item+1) expected_payload[item]=8'(expected>>(item*8));
        exchange(COMMAND_READ_HOST,4,STATUS_OK,4);
        checks = checks + 1;
    endtask
    // A masked LIBRARY_STATUS read for bits the contract leaves open here.
    task automatic read_status(input logic [31:0] expected, input logic [31:0] mask);
        integer item;
        word_request(HOST_REG_LIBRARY_STATUS);
        for(item=0;item<4;item=item+1) begin expected_payload[item]=8'(expected>>(item*8)); expected_mask[item]=8'(mask>>(item*8)); end
        exchange(COMMAND_READ_HOST,4,STATUS_OK,4);
        checks = checks + 1;
    endtask
    task automatic write_host(input logic [31:0] register, input logic [31:0] value);
        integer item;
        word_request(register);
        for(item=0;item<4;item=item+1) request_payload[4+item]=8'(value>>(item*8));
        ignore_payload = 1;
        exchange(COMMAND_WRITE_HOST,8,STATUS_OK,8);
    endtask
    task automatic simple(input logic [7:0] cmd);
        ignore_payload = 1;
        exchange(cmd,0,STATUS_OK,0);
    endtask
    // The board's own joypad producer: one coherent mask on a tick-free edge.
    task automatic press_buttons(input logic [7:0] mask);
        @(negedge clk_sys);
        while (gb_tick) @(negedge clk_sys);
        physical_buttons = mask; physical_commit = 1;
        @(negedge clk_sys);
        physical_commit = 0;
    endtask
    task automatic wait_copy(input int bound, input string what);
        int edges;
        edges = 0;
        while (dut.loader_copy_busy) begin
            @(negedge clk_sys); edges = edges + 1;
            if (edges > bound) $fatal(1, "MENU_SYS_BOUND %s edges=%0d", what, edges);
        end
    endtask
    task automatic wait_profile(input logic [7:0] wanted, input int bound, input string what);
        int edges;
        edges = 0;
        while (dut.profile != wanted || !dut.image_valid || dut.loader_copy_busy || paused) begin
            @(negedge clk_sys); edges = edges + 1;
            if (edges > bound) $fatal(1, "MENU_SYS_PROFILE_WAIT %s profile=%02h valid=%b busy=%b paused=%b",
                what, dut.profile, dut.image_valid, dut.loader_copy_busy, paused);
        end
    endtask

    // Wait for the first pixel of the next display-eligible frame.
    task automatic frame_start(input int bound_edges);
        int seen, edges;
        seen = frames_seen; edges = 0;
        while (frames_seen == seen) begin
            @(negedge clk_sys); edges = edges + 1;
            if (edges > bound_edges) $fatal(1, "MENU_SYS_NO_FRAME frames=%0d", frames_seen);
        end
    endtask
    // Wait for the frame that started last to complete, then compare it
    // with reference frame `index` from menu-frames.hex.
    task automatic check_frame(input int index);
        int edges, pixel;
        edges = 0;
        while (!frame_complete) begin
            @(negedge clk_sys); edges = edges + 1;
            if (edges > 600000) $fatal(1, "MENU_SYS_FRAME_INCOMPLETE index=%0d pixels=%0d", index, pixel_index);
        end
        for (pixel = 0; pixel < FRAME_PIXELS; pixel = pixel + 1)
            if (captured[pixel] != frames_mem[index * FRAME_PIXELS + pixel][1:0])
                $fatal(1, "MENU_PIXEL frame=%0d x=%0d y=%0d expected=%0d actual=%0d",
                    index, pixel % 160, pixel / 160, frames_mem[index * FRAME_PIXELS + pixel], captured[pixel]);
        frames_checked = frames_checked + 1;
        checks = checks + 1;
        $display("MENU_SYS frame=%0d matched time_ns=%0t", index, $time);
    endtask
    // One joypad step: press at the start of a visible frame so the menu
    // samples it in that frame's VBlank; release at the start of the next
    // frame, which shows the result, and compare that frame.
    task automatic step(input logic [7:0] mask, input int index);
        frame_start(1200000);
        press_buttons(mask);
        frame_start(1200000);
        press_buttons(8'h00);
        check_frame(index);
    endtask
    // A on the cursor: the select register receives `slot` and the game boots.
    task automatic select_game(input logic [7:0] slot);
        logic [31:0] epoch_before;
        epoch_before = epoch;
        select_seen = 0;
        frame_start(1200000);
        press_buttons(BUTTON_A);
        wait_profile(PROFILE_DIRECT_ID, 1200000, "game");
        if (!select_seen || select_data != slot) $fatal(1, "MENU_SYS_SELECT expected=%0d seen=%b data=%0d", slot, select_seen, select_data);
        if (epoch != epoch_before + 1) $fatal(1, "MENU_SYS_GAME_EPOCH slot=%0d", slot);
        read_host(HOST_REG_PROFILE, PROFILE_DIRECT_ID);
        // The swap cleared window_ready; the bank register keeps 34.
        read_host(HOST_REG_LIBRARY_STATUS, {2'b0, 6'd34, 8'(slot), LIBRARY_RESULT_OK, 8'h20});
        press_buttons(8'h00);
        selects = selects + 1;
        checks = checks + 1;
        $display("MENU_SYS select=%0d booted time_ns=%0t", slot, $time);
    endtask

    // Power-up: no image, paused. The return swaps the menu in from SDRAM;
    // the board's joypad is selected and the console runs.
    task automatic boot_menu;
        read_host(HOST_REG_STATE, STATE_PAUSE);
        write_host(HOST_REG_LIBRARY_CONTROL, LIBRARY_CONTROL_RETURN);
        wait_copy(SWAP_BOUND, "menu swap");
        read_host(HOST_REG_PROFILE, PROFILE_LOADER_ID);
        write_host(HOST_REG_INPUT_SOURCE, INPUT_SOURCE_PHYSICAL);
        simple(COMMAND_RUN);
        // The checker must reject a wrong shade on the very first pixel.
        if (pixel_fault) force dut.source_shade = 2'd2;
        // The first display-eligible frame is the complete menu.
        frame_start(6000000);
        check_frame(0);
        // The catalogue window is bank 34; the return swapped index 16 without a select commit.
        read_host(HOST_REG_LIBRARY_STATUS, {2'b0, 6'd34, 8'hFF, LIBRARY_RESULT_OK, 8'h60});
    endtask

    task automatic fixture_frame;
        boot_menu();
        step(BUTTON_DOWN, 1);
        step(BUTTON_DOWN, 2);
        step(BUTTON_UP, 1);
        // Up at the top and a held button change nothing.
        step(BUTTON_UP, 0);
        step(BUTTON_UP, 0);
    endtask

    task automatic fixture_select;
        boot_menu();
        step(BUTTON_DOWN, 1);
        select_game(8'd1);
    endtask

    task automatic fixture_refused;
        boot_menu();
        step(BUTTON_DOWN, 1);
        step(BUTTON_DOWN, 2);
        step(BUTTON_DOWN, 3);
        // Slot 3 is empty: the select is refused and the status row says so.
        // window_ready (bit 6) is masked: the hardware clears it on a refused
        // select against the contract (#685); the menu never depends on it.
        step(BUTTON_A, 4);
        read_status({2'b0, 6'd34, 8'd3, LIBRARY_RESULT_INVALID_SLOT, 8'h20}, 32'h3FFFFFBF);
        step(BUTTON_UP, 5);
        select_game(8'd2);
    endtask

    initial begin
        clk_sys = 0; clk_pix = 0; reset_sys = 1; reset_pix = 1; uart_rx = 1; key1_n = 1;
        physical_commit = 0; physical_buttons = 0;
        reply_size = 0; expected_size = 0; command_count = 0; token = 1; waiting_reply = 0; ignore_payload = 0;
        checks = 0; selects = 0; frames_seen = 0; frames_checked = 0; pixel_index = 0;
        for (command_count=0;command_count<256;command_count=command_count+1) expected_mask[command_count]=8'hFF;
        command_count = 0;
        capturing = 0; frame_complete = 0; select_seen = 0; select_data = 0;
        if (!$value$plusargs("fixture=%s", fixture)) fixture = "frame";
        pixel_fault = $test$plusargs("pixel_fault");
        $readmemh("menu-library.hex", library_mem);
        $readmemh("menu-frames.hex", frames_mem);
        repeat (5) @(negedge clk_sys);
        reset_sys = 0; reset_pix = 0;
        repeat (3) @(negedge clk_sys);
        preload_library();
        while (!sdram_initialized) @(negedge clk_sys);
        repeat (4) @(negedge clk_sys);
        case (fixture)
            "frame": fixture_frame();
            "select": fixture_select();
            "refused": fixture_refused();
            default: $fatal(1, "MENU_SYS_FIXTURE %s", fixture);
        endcase
        $display("PASS menu-%s checks=%0d frames=%0d selects=%0d commands=%0d", fixture, checks, frames_checked, selects, command_count);
        $finish;
    end
    initial begin #1500000000; $fatal(1, "MENU_SYS_WATCHDOG"); end
endmodule
`default_nettype wire
