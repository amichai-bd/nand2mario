`timescale 1ns/1ps
`default_nettype none
// Flash reader fixtures against the On-Chip Flash IP double.
// Contract: wiki/src/rtl/storage/MAS_flash_library.md#verification. Test plan: README.md.
//
// One clock is 40 ns. The monitor samples mid-clock; a line accepted at the
// edge ending clock c is "accepted at edge c+1", and every cadence check
// counts clocks from that edge using the contract's numbers, never the DUT's
// state. The fixture writes its own word-addressed hex image, loads it into
// the double through the wrapper's VERILATOR instance, and keeps its own copy
// of every defined word; undefined words must read erased.
module tb_flash_reader;
    import n2m_flash_pkg::*;

    localparam int CLOCK_NS = 40;
    // Flash word numbering of the contract and the IP's 0-based Avalon space.
    localparam logic [19:0] DATA_BASE = 20'h00800;
    localparam logic [19:0] USER_LAST = 20'h2E7FF;
    localparam logic [19:0] SLOT_WORDS = 20'h2000;
    localparam logic [19:0] CATALOGUE = 20'h22800;
    localparam logic [19:0] RESERVED = 20'h22900;
    localparam int ERASED_SLOT = 5;
    // Clocks after the accepting edge A, as seen mid-clock: the Avalon read is
    // on the bus in clocks A..A+2 and accepted at edge A+3; word 0 is on the
    // bus in clock A+9 (sampled at edge A+10, seven edges after the Avalon
    // acceptance) through word 3 in A+12 (edge A+13); the line is published
    // in clock A+13, ready returns in A+14 and the next line can be accepted
    // at edge A+15.
    localparam int AVMM_ACCEPT = 3;
    localparam int FIRST_WORD = 9;
    localparam int LAST_WORD = 12;
    localparam int PUBLISH = 13;
    localparam int READY_AGAIN = 14;
    localparam int BACK_TO_BACK = 15;
    localparam string IMAGE = "flash-fixture.hex";

    logic clk_sys;
    logic reset_sys;
    logic line_valid;
    logic [19:0] line_word;
    logic line_ready;
    logic line_data_valid;
    logic [127:0] line_data;

    n2m_flash_reader dut (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .line_valid(line_valid), .line_word(line_word),
        .line_ready(line_ready), .line_data_valid(line_data_valid), .line_data(line_data)
    );

    string fixture;
    int clock_index;
    logic [31:0] image [int unsigned];
    // Monitor record of the accepted line.
    bit outstanding;
    int accept_edge;
    logic [19:0] accepted_word;
    bit accepted_back_to_back;
    int lines_accepted;
    int lines_published;
    int words_seen;
    int erased_lines;
    int back_to_back_lines;
    bit held;
    logic [127:0] held_line;
    int hold_checks;
    bit in_reset;

    always #(CLOCK_NS / 2) clk_sys = ~clk_sys;
    always @(posedge clk_sys) clock_index = clock_index + 1;

    function automatic logic [31:0] pattern(input logic [19:0] word);
        return (32'(word) * 32'h9E3779B1) ^ 32'hA5C31E7F ^ {12'd0, word};
    endfunction

    function automatic logic [31:0] expected(input logic [19:0] word);
        if (image.exists(32'(word))) return image[32'(word)];
        return 32'hFFFFFFFF;
    endfunction

    function automatic logic [127:0] expected_line(input logic [19:0] word);
        logic [127:0] value;
        int k;
        for (k = 0; k < 4; k = k + 1) value[k * 32 +: 32] = expected(word + 20'(k));
        return value;
    endfunction

    task automatic define_line(input logic [19:0] word);
        int k;
        for (k = 0; k < 4; k = k + 1) image[32'(word + 20'(k))] = pattern(word + 20'(k));
    endtask

    // Every slot's first and last line except one erased slot, the whole
    // catalogue, the line either side of each sector start, one mid-slot
    // line and the last user line.
    task automatic define_image();
        int i;
        logic [19:0] witness;
        logic [19:0] sector_starts [0:2];
        sector_starts[0] = 20'h02800;
        sector_starts[1] = 20'h04800;
        sector_starts[2] = 20'h1C800;
        for (i = 0; i < 17; i = i + 1) begin
            if (i == ERASED_SLOT) continue;
            define_line(DATA_BASE + 20'(i) * SLOT_WORDS);
            define_line(DATA_BASE + 20'(i) * SLOT_WORDS + SLOT_WORDS - 20'd4);
        end
        for (i = 0; i < 64; i = i + 1) define_line(CATALOGUE + 20'(i * 4));
        for (i = 0; i < 3; i = i + 1) begin
            define_line(sector_starts[i] - 20'd4);
            define_line(sector_starts[i]);
        end
        define_line(DATA_BASE + 20'd3 * SLOT_WORDS + 20'h1000);
        define_line(USER_LAST - 20'd3);
        // Byte order witness: little-endian word k of the line in bits 32k+31:32k.
        witness = DATA_BASE + 20'd3 * SLOT_WORDS + 20'h1000;
        image[32'(witness)] = 32'h03020100;
        image[32'(witness) + 1] = 32'h07060504;
    endtask

    // Word-addressed Verilog hex in the IP's Avalon numbering.
    task automatic write_image(input string path);
        int handle;
        int unsigned word;
        handle = $fopen(path, "w");
        if (handle == 0) $fatal(1, "FLASH_TB_IMAGE_FILE cannot write %s", path);
        if (image.first(word) != 0) begin
            do begin
                $fwrite(handle, "@%05X %08X\n", word - 32'(DATA_BASE), image[word]);
            end while (image.next(word) != 0);
        end
        $fclose(handle);
    endtask

    // Mid-clock monitor of the public boundary and the IP-side slave.
    always @(negedge clk_sys) begin : monitor
        int since;
        if (reset_sys) begin
            if (line_data_valid) $fatal(1, "FLASH_TB_VALID_IN_RESET clock=%0d", clock_index);
            if (line_ready) $fatal(1, "FLASH_TB_READY_IN_RESET clock=%0d", clock_index);
            outstanding = 1'b0;
            held = 1'b0;
            in_reset = 1'b1;
        end else begin
            since = clock_index - accept_edge;
            if (in_reset) begin
                // The reader returns to idle with reset release; nothing is published.
                if (!line_ready) $fatal(1, "FLASH_TB_READY_AFTER_RESET clock=%0d", clock_index);
                if (line_data_valid) $fatal(1, "FLASH_TB_VALID_AFTER_RESET clock=%0d", clock_index);
                in_reset = 1'b0;
            end
            if (dut.avmm_read) begin
                if (!outstanding || since < 0 || since >= AVMM_ACCEPT)
                    $fatal(1, "FLASH_TB_AVMM_READ_WINDOW clock=%0d accepted=%0d outstanding=%b", clock_index, accept_edge, outstanding);
                // Contract translation: the IP's Avalon word is the flash word less the UFM1 base.
                if (dut.avmm_address != 18'(accepted_word - DATA_BASE))
                    $fatal(1, "FLASH_TB_TRANSLATION word=%h avalon=%h expected=%h", accepted_word, dut.avmm_address, accepted_word - DATA_BASE);
                if (dut.avmm_burstcount != 3'd4)
                    $fatal(1, "FLASH_TB_BURSTCOUNT clock=%0d burstcount=%0d", clock_index, dut.avmm_burstcount);
                if (dut.avmm_waitrequest != (since < AVMM_ACCEPT - 1))
                    $fatal(1, "FLASH_TB_WAITREQUEST clock=%0d since=%0d waitrequest=%b", clock_index, since, dut.avmm_waitrequest);
            end else if (outstanding && since >= 0 && since < AVMM_ACCEPT)
                $fatal(1, "FLASH_TB_AVMM_READ_DROPPED clock=%0d since=%0d", clock_index, since);
            if (dut.avmm_readdatavalid) begin
                if (!outstanding || since < FIRST_WORD || since > LAST_WORD)
                    $fatal(1, "FLASH_TB_WORD_CLOCK clock=%0d since=%0d", clock_index, since);
                if (dut.avmm_readdata !== expected(accepted_word + 20'(since - FIRST_WORD)))
                    $fatal(1, "FLASH_TB_WORD word=%h k=%0d expected=%h actual=%h", accepted_word, since - FIRST_WORD,
                        expected(accepted_word + 20'(since - FIRST_WORD)), dut.avmm_readdata);
                words_seen = words_seen + 1;
            end else if (outstanding && since >= FIRST_WORD && since <= LAST_WORD)
                $fatal(1, "FLASH_TB_WORD_MISSING clock=%0d since=%0d", clock_index, since);
            if (line_data_valid) begin
                if (!outstanding || since != PUBLISH)
                    $fatal(1, "FLASH_TB_PUBLISH_CLOCK clock=%0d accepted=%0d outstanding=%b", clock_index, accept_edge, outstanding);
                if (line_data !== expected_line(accepted_word))
                    $fatal(1, "FLASH_TB_LINE word=%h expected=%h actual=%h", accepted_word, expected_line(accepted_word), line_data);
                if (expected_line(accepted_word) == {4{32'hFFFFFFFF}}) erased_lines = erased_lines + 1;
                lines_published = lines_published + 1;
                held = 1'b1;
                held_line = line_data;
            end else if (outstanding && since == PUBLISH)
                $fatal(1, "FLASH_TB_PUBLISH_MISSING clock=%0d accepted=%0d", clock_index, accept_edge);
            if (outstanding && line_ready != (since >= READY_AGAIN))
                $fatal(1, "FLASH_TB_READY clock=%0d since=%0d ready=%b", clock_index, since, line_ready);
            if (outstanding && since == READY_AGAIN) outstanding = 1'b0;
            if (held) begin
                if (line_data !== held_line)
                    $fatal(1, "FLASH_TB_LINE_CHANGED clock=%0d expected=%h actual=%h", clock_index, held_line, line_data);
                hold_checks = hold_checks + 1;
            end
            // Acceptance at the edge ending this clock.
            if (line_valid && line_ready) begin
                if (outstanding) $fatal(1, "FLASH_TB_OVERLAP clock=%0d", clock_index);
                accepted_back_to_back = lines_accepted != 0 && clock_index + 1 - accept_edge == BACK_TO_BACK;
                accept_edge = clock_index + 1;
                accepted_word = line_word;
                outstanding = 1'b1;
                held = 1'b0;
                lines_accepted = lines_accepted + 1;
                if (accepted_back_to_back) back_to_back_lines = back_to_back_lines + 1;
            end
        end
    end

    task automatic present(input logic [19:0] word);
        line_word = word;
        line_valid = 1'b1;
    endtask

    task automatic wait_accept();
        forever begin
            @(negedge clk_sys);
            if (line_valid && line_ready) break;
        end
        @(posedge clk_sys);
        #1;
    endtask

    // Present one line just after a rising edge and hold it until accepted.
    task automatic issue(input logic [19:0] word);
        @(posedge clk_sys);
        #1;
        present(word);
        wait_accept();
        line_valid = 1'b0;
    endtask

    task automatic wait_line();
        forever begin
            @(negedge clk_sys);
            if (line_data_valid) break;
        end
    endtask

    task automatic wait_ready();
        forever begin
            @(negedge clk_sys);
            if (line_ready && !outstanding) break;
        end
    endtask

    task automatic read_line(input logic [19:0] word);
        issue(word);
        wait_line();
        wait_ready();
    endtask

    task automatic run_reader();
        int i;
        int start_clock;
        int unsigned word;
        // Every defined line in ascending order, one at a time.
        if (image.first(word) != 0) begin
            do begin
                if (word % 4 == 0) read_line(20'(word));
            end while (image.next(word) != 0);
        end
        // Erased words: the untouched slot's first and last line, the first
        // reserved line, the last user line's neighbour.
        read_line(DATA_BASE + 20'(ERASED_SLOT) * SLOT_WORDS);
        read_line(DATA_BASE + 20'(ERASED_SLOT) * SLOT_WORDS + SLOT_WORDS - 20'd4);
        read_line(RESERVED);
        read_line(USER_LAST - 20'd7);
        if (erased_lines != 4) $fatal(1, "FLASH_TB_ERASED_LINES count=%0d", erased_lines);
        // The catalogue back to back with line_valid held high: one line
        // per BACK_TO_BACK clocks, the next word presented at each acceptance.
        @(posedge clk_sys);
        #1;
        start_clock = clock_index;
        for (i = 0; i < 64; i = i + 1) begin
            present(CATALOGUE + 20'(i * 4));
            wait_accept();
        end
        line_valid = 1'b0;
        wait_line();
        wait_ready();
        if (back_to_back_lines != 63)
            $fatal(1, "FLASH_TB_BACK_TO_BACK lines=%0d expected=63 clocks=%0d", back_to_back_lines, clock_index - start_clock);
        // Reset while the words are arriving abandons the read.
        @(posedge clk_sys);
        #1;
        present(DATA_BASE);
        wait_accept();
        line_valid = 1'b0;
        repeat (6) @(posedge clk_sys);
        #1;
        reset_sys = 1'b1;
        repeat (3) @(posedge clk_sys);
        #1;
        reset_sys = 1'b0;
        repeat (PUBLISH + 2) @(negedge clk_sys);
        read_line(CATALOGUE);
        read_line(USER_LAST - 20'd3);
        if (lines_published != lines_accepted - 1)
            $fatal(1, "FLASH_TB_COVERAGE accepted=%0d published=%0d", lines_accepted, lines_published);
        if (words_seen != 4 * lines_published || hold_checks == 0)
            $fatal(1, "FLASH_TB_WORDS words=%0d lines=%0d holds=%0d", words_seen, lines_published, hold_checks);
        if (dut.u_flash.read_count != lines_accepted || dut.u_flash.word_count != words_seen)
            $fatal(1, "FLASH_TB_MODEL_COUNTS reads=%0d/%0d words=%0d/%0d", dut.u_flash.read_count, lines_accepted, dut.u_flash.word_count, words_seen);
        $display("PASS flash-reader lines=%0d words=%0d erased=%0d back_to_back=%0d image_words=%0d",
            lines_published, words_seen, erased_lines, back_to_back_lines, image.size());
    endtask

    task automatic run_fault_misaligned();
        issue(DATA_BASE + 20'd2);
        wait_line();
        $fatal(1, "FLASH_TB_FAULT_NOT_CAUGHT misaligned line accepted");
    endtask

    task automatic run_fault_range();
        issue(USER_LAST + 20'd1);
        wait_line();
        $fatal(1, "FLASH_TB_FAULT_NOT_CAUGHT out-of-range line accepted");
    endtask

    initial begin
        clk_sys = 1'b0;
        reset_sys = 1'b1;
        line_valid = 1'b0;
        line_word = '0;
        clock_index = 0;
        outstanding = 1'b0;
        accept_edge = 0;
        accepted_word = '0;
        accepted_back_to_back = 1'b0;
        lines_accepted = 0;
        lines_published = 0;
        words_seen = 0;
        erased_lines = 0;
        back_to_back_lines = 0;
        held = 1'b0;
        held_line = '0;
        hold_checks = 0;
        in_reset = 1'b1;
        if (!$value$plusargs("fixture=%s", fixture)) fixture = "reader";
        define_image();
        write_image(IMAGE);
        dut.u_flash.load(IMAGE);
        repeat (4) @(posedge clk_sys);
        #1;
        reset_sys = 1'b0;
        repeat (2) @(posedge clk_sys);
        case (fixture)
            "reader": run_reader();
            "fault-misaligned": run_fault_misaligned();
            "fault-range": run_fault_range();
            default: $fatal(1, "FLASH_TB_FIXTURE unknown fixture %s", fixture);
        endcase
        $finish;
    end

    initial begin
        #(CLOCK_NS * 1ns * 20000);
        $fatal(1, "FLASH_TB_WATCHDOG fixture=%s clock=%0d", fixture, clock_index);
    end
endmodule
`default_nettype wire
