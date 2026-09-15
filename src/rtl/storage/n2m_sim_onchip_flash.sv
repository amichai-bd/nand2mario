// Simulation double of the MAX 10 On-Chip Flash IP's read-only Avalon-MM data
// slave, selected by n2m_flash_reader under the predefined VERILATOR macro.
// Quartus never sees it; the Questa compile gate compiles it with the RTL.
// Contract: wiki/src/rtl/storage/MAS_flash_library.md#on-chip-flash-ip-boundary.
//
// Words are the IP's 0-based Avalon data words (flash word minus 0x800). The
// image loads with $readmemh from a word-addressed Verilog hex file; every
// word the file does not define reads erased, 0xFFFFFFFF. The cadence is the
// shipped parallel 10M50 data controller's, traced from its RTL rather than
// copied: a read presented while idle is accepted at the third edge, word 0
// is valid seven clocks after that acceptance, the next three words follow on
// consecutive clocks, a longer burst continues at four words per seven clocks,
// and the slave captures its next read four edges after its last word. Every Avalon
// or range violation is a named fatal.
`timescale 1ns/1ps
`default_nettype none

module n2m_sim_onchip_flash #(
    parameter string INIT_FILE = "",
    parameter int AVMM_DATA_ADDR_WIDTH = 18,
    parameter int AVMM_DATA_BURSTCOUNT_WIDTH = 3,
    parameter int WORDS = 32'h0002E000,
    parameter int MAX_BURST = 128
) (
    input var logic clock,
    input var logic reset_n,
    input var logic avmm_data_read,
    input var logic avmm_data_write,
    input var logic [AVMM_DATA_ADDR_WIDTH-1:0] avmm_data_addr,
    input var logic [31:0] avmm_data_writedata,
    input var logic [AVMM_DATA_BURSTCOUNT_WIDTH-1:0] avmm_data_burstcount,
    output logic avmm_data_waitrequest,
    output logic avmm_data_readdatavalid,
    output logic [31:0] avmm_data_readdata
);
    localparam logic [31:0] ERASED = 32'hFFFFFFFF;
    // Clocks after the edge that captured an idle read: waitrequest falls in
    // clock 1 so the master sees acceptance at the second edge after capture
    // (the third after it presented the read); word 0 is valid in clock 8.
    localparam int ACCEPT_CLOCK = 1;
    localparam int FIRST_WORD_CLOCK = 8;
    localparam int GROUP_WORDS = 4;
    localparam int GROUP_PERIOD = 7;
    // The IP leaves its read state three clocks after the last word and
    // samples a waiting read at the edge after that: capture is possible
    // again four edges after the last word's clock.
    localparam int IDLE_AFTER_LAST = 4;

    logic [31:0] words [0:WORDS-1];
    logic busy;
    int elapsed;
    int unsigned base;
    int burst;
    int last_word_clock;
    int read_count;
    int word_count;
    logic [AVMM_DATA_ADDR_WIDTH-1:0] held_addr;
    logic [AVMM_DATA_BURSTCOUNT_WIDTH-1:0] held_burst;

    function automatic logic [31:0] stored(input int unsigned address);
        if (address < WORDS) return words[address];
        return ERASED;
    endfunction

    // Word j of a burst is valid in clock FIRST_WORD_CLOCK + (j % 4) + 7 * (j / 4).
    function automatic int word_clock(input int j);
        return FIRST_WORD_CLOCK + (j % GROUP_WORDS) + GROUP_PERIOD * (j / GROUP_WORDS);
    endfunction

    task automatic erase();
        int i;
        for (i = 0; i < WORDS; i = i + 1) words[i] = ERASED;
    endtask

    // Load a word-addressed Verilog hex image (`@<avalon word>` records) over
    // the current contents.
    task automatic load(input string path);
        $readmemh(path, words);
    endtask

    task automatic preload_word(input int unsigned address, input logic [31:0] value);
        words[address] = value;
    endtask

    task automatic clear_transfer();
        busy = 1'b0;
        elapsed = 0;
        base = 0;
        burst = 0;
        last_word_clock = 0;
        avmm_data_readdatavalid = 1'b0;
        avmm_data_readdata = ERASED;
    endtask

    initial begin
        erase();
        if (INIT_FILE != "") load(INIT_FILE);
        clear_transfer();
        read_count = 0;
        word_count = 0;
        held_addr = '0;
        held_burst = '0;
    end

    // Idle: waitrequest while the read has not been captured. Busy: high
    // except in the one clock that accepts the captured read.
    assign avmm_data_waitrequest = !reset_n || (avmm_data_read && !(busy && elapsed == ACCEPT_CLOCK));

    always @(posedge clock or negedge reset_n) begin : slave
        int j;
        if (!reset_n) begin
            clear_transfer();
        end else begin
            if (avmm_data_write)
                $fatal(1, "FLASH_MODEL_WRITE addr=%h data=%h", avmm_data_addr, avmm_data_writedata);
            avmm_data_readdatavalid = 1'b0;
            if (busy) begin
                elapsed = elapsed + 1;
                if (elapsed <= ACCEPT_CLOCK) begin
                    // Avalon: a read held under waitrequest keeps its fields.
                    if (!avmm_data_read || avmm_data_addr != held_addr || avmm_data_burstcount != held_burst)
                        $fatal(1, "FLASH_MODEL_HOLD read=%b addr=%h/%h burstcount=%0d/%0d",
                            avmm_data_read, avmm_data_addr, held_addr, avmm_data_burstcount, held_burst);
                end
                for (j = 0; j < burst; j = j + 1) begin
                    if (elapsed == word_clock(j)) begin
                        avmm_data_readdatavalid = 1'b1;
                        avmm_data_readdata = stored(base + j);
                        word_count = word_count + 1;
                    end
                end
                if (elapsed >= last_word_clock + IDLE_AFTER_LAST) busy = 1'b0;
            end
            if (!busy && avmm_data_read) begin
                // The IP samples a new read only from idle; a read raised
                // while the previous burst drains waits under waitrequest.
                if (avmm_data_burstcount == 0 || int'(avmm_data_burstcount) > MAX_BURST)
                    $fatal(1, "FLASH_MODEL_BURST burstcount=%0d", avmm_data_burstcount);
                if (int'(avmm_data_addr) + int'(avmm_data_burstcount) > WORDS)
                    $fatal(1, "FLASH_MODEL_RANGE addr=%h burstcount=%0d words=%0d", avmm_data_addr, avmm_data_burstcount, WORDS);
                if (avmm_data_addr[1:0] != 2'd0)
                    $fatal(1, "FLASH_MODEL_ALIGNED addr=%h", avmm_data_addr);
                busy = 1'b1;
                elapsed = 0;
                base = int'(avmm_data_addr);
                burst = int'(avmm_data_burstcount);
                held_addr = avmm_data_addr;
                held_burst = avmm_data_burstcount;
                last_word_clock = word_clock(burst - 1);
                read_count = read_count + 1;
            end
        end
    end
endmodule
`default_nettype wire
