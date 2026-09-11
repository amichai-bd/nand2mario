`timescale 1ns/1ps
// Two identical copies of every module that owns an exposed DMG I/O register
// run on the same stimulus. Copy A is peeked: the host register decode sweeps
// every exposed host address on every edge. Copy B is never peeked. If a read
// could clear, latch or advance anything, the two copies diverge.
//
// +PEEK_DISTURB is the negative case. It routes the peek through copy A's DMG
// I/O port, which is the wiring mistake this design avoids: a peek of DIV then
// lands as a CPU write and resets the divider. The checker must see that.
module tb_io_peek;
    localparam int unsigned PEEK_FIRST = 32'h00010050;
    localparam int unsigned PEEK_LAST = 32'h00010094;
    localparam int unsigned PEEK_WORDS = (PEEK_LAST - PEEK_FIRST) / 4 + 1;
    localparam int unsigned CYCLES = 20000;

    logic clk_sys, reset, gb_tick;
    logic disturb;
    integer cycle, checks, peeks;
    logic [31:0] lfsr;
    logic [31:0] peek_address;
    logic [4:0] peek_index;

    // Shared stimulus. One commit at a time, always on a tick, always to the
    // module that owns the address, so each owner's boundary assertions hold.
    logic io_write;
    logic [15:0] io_address;
    logic [7:0] io_wdata;
    logic timer_commit, irq_commit, ppu_commit;
    logic divider_reset_request;
    logic [4:0] source_level, source_event, irq_ack;
    logic [7:0] ly;
    logic [1:0] mode;
    logic coincidence;

    // Copy A, peeked.
    logic [7:0] a_timer_rdata, a_div, a_tima, a_tma, a_tac;
    logic [7:0] a_ie_stored, a_irq_rdata, a_ie_observe;
    logic [4:0] a_if_stored, a_if_observe;
    logic [7:0] a_lcdc, a_scy, a_scx, a_lyc, a_bgp, a_obp0, a_obp1, a_wy, a_wx;
    logic [7:0] a_stat, a_ppu_rdata, a_render_bgp, a_render_obp0, a_render_obp1;
    logic [3:0] a_stat_enable;
    logic a_stat_write, a_lyc_write, a_lcd_enable, a_lcd_disable, a_ppu_selected;
    n2m_timer_pkg::timer_request_t a_timer_request;
    // Copy B, never peeked.
    logic [7:0] b_timer_rdata, b_div, b_tima, b_tma, b_tac;
    logic [7:0] b_ie_stored, b_irq_rdata, b_ie_observe;
    logic [4:0] b_if_stored, b_if_observe;
    logic [7:0] b_lcdc, b_scy, b_scx, b_lyc, b_bgp, b_obp0, b_obp1, b_wy, b_wx;
    logic [7:0] b_stat, b_ppu_rdata, b_render_bgp, b_render_obp0, b_render_obp1;
    logic [3:0] b_stat_enable;
    logic b_stat_write, b_lyc_write, b_lcd_enable, b_lcd_disable, b_ppu_selected;
    n2m_timer_pkg::timer_request_t b_timer_request;

    // The injected fault. A peek of the divider address becomes a DMG write.
    logic inject_commit;
    logic [15:0] inject_address;
    // Inject only on ticks the stimulus leaves the timer port idle, so the
    // injected read is added to copy A rather than stealing a real write.
    assign inject_commit = disturb && gb_tick && !timer_commit
        && peek_address == n2m_interfaces_pkg::HOST_REG_IO_DIV;
    assign inject_address = n2m_interfaces_pkg::GB_REG_DIV;

    logic [31:0] peek_data;
    logic peek_valid;
    n2m_uart_host_registers u_peek (
        .address(peek_address), .endpoint_state(8'h01), .image_valid(1'b1), .profile(8'hA6),
        .dot_count(64'd0), .retirement_count(64'd0), .buttons(8'd0), .input_source(8'd0),
        .physical_buttons(8'd0), .effective_buttons(8'd0), .snapshot_valid(1'b0),
        .snapshot_metadata('0), .build_id(128'd1),
        .io_lcdc(a_lcdc), .io_stat(a_stat), .io_ly(ly), .io_lyc(a_lyc), .io_scy(a_scy),
        .io_scx(a_scx), .io_wy(a_wy), .io_wx(a_wx), .io_bgp(a_bgp), .io_obp0(a_obp0),
        .io_obp1(a_obp1), .io_div(a_div), .io_tima(a_tima), .io_tma(a_tma), .io_tac(a_tac),
        .io_if({3'b0, a_if_stored}), .io_ie(a_ie_stored),
        .address_valid(peek_valid), .data(peek_data)
    );

    n2m_timer a_timer (
        .clk_sys(clk_sys), .reset_sys(reset), .core_reset(1'b0), .gb_tick(gb_tick),
        .divider_reset_request(divider_reset_request),
        .io_commit(timer_commit || inject_commit), .io_write(io_write || inject_commit),
        .io_address(inject_commit ? inject_address : io_address),
        .io_wdata(io_wdata), .io_selected(), .io_rdata(a_timer_rdata),
        .interrupt_request(a_timer_request), .div_observe(a_div), .tima_observe(a_tima),
        .tma_observe(a_tma), .tac_observe(a_tac)
    );
    n2m_timer b_timer (
        .clk_sys(clk_sys), .reset_sys(reset), .core_reset(1'b0), .gb_tick(gb_tick),
        .divider_reset_request(divider_reset_request),
        .io_commit(timer_commit), .io_write(io_write), .io_address(io_address),
        .io_wdata(io_wdata), .io_selected(), .io_rdata(b_timer_rdata),
        .interrupt_request(b_timer_request), .div_observe(b_div), .tima_observe(b_tima),
        .tma_observe(b_tma), .tac_observe(b_tac)
    );
    n2m_interrupts a_irq (
        .clk_sys(clk_sys), .reset_sys(reset), .core_reset(1'b0), .gb_tick(gb_tick),
        .io_commit(irq_commit), .io_write(io_write), .io_address(io_address),
        .io_wdata(io_wdata), .source_level(source_level), .source_event(source_event),
        .irq_ack(irq_ack), .io_selected(), .io_rdata(a_irq_rdata),
        .ie_stored(a_ie_stored), .if_stored(a_if_stored),
        .ie_observe(a_ie_observe), .if_observe(a_if_observe)
    );
    n2m_interrupts b_irq (
        .clk_sys(clk_sys), .reset_sys(reset), .core_reset(1'b0), .gb_tick(gb_tick),
        .io_commit(irq_commit), .io_write(io_write), .io_address(io_address),
        .io_wdata(io_wdata), .source_level(source_level), .source_event(source_event),
        .irq_ack(irq_ack), .io_selected(), .io_rdata(b_irq_rdata),
        .ie_stored(b_ie_stored), .if_stored(b_if_stored),
        .ie_observe(b_ie_observe), .if_observe(b_if_observe)
    );
    n2m_ppu_registers a_ppu (
        .clk_sys(clk_sys), .reset(reset), .gb_tick(gb_tick), .io_commit(ppu_commit),
        .io_write(io_write), .io_address(io_address), .io_wdata(io_wdata), .ly(ly),
        .mode(mode), .coincidence(coincidence), .quarter_phase(2'd3),
        .io_selected(a_ppu_selected), .io_rdata(a_ppu_rdata), .lcdc(a_lcdc), .scy(a_scy),
        .scx(a_scx), .lyc(a_lyc), .bgp(a_bgp), .obp0(a_obp0), .obp1(a_obp1),
        .render_bgp(a_render_bgp), .render_obp0(a_render_obp0), .render_obp1(a_render_obp1),
        .wy(a_wy), .wx(a_wx), .stat_enable(a_stat_enable), .stat_observe(a_stat),
        .stat_write(a_stat_write), .lyc_write(a_lyc_write),
        .lcd_enable(a_lcd_enable), .lcd_disable(a_lcd_disable)
    );
    n2m_ppu_registers b_ppu (
        .clk_sys(clk_sys), .reset(reset), .gb_tick(gb_tick), .io_commit(ppu_commit),
        .io_write(io_write), .io_address(io_address), .io_wdata(io_wdata), .ly(ly),
        .mode(mode), .coincidence(coincidence), .quarter_phase(2'd3),
        .io_selected(b_ppu_selected), .io_rdata(b_ppu_rdata), .lcdc(b_lcdc), .scy(b_scy),
        .scx(b_scx), .lyc(b_lyc), .bgp(b_bgp), .obp0(b_obp0), .obp1(b_obp1),
        .render_bgp(b_render_bgp), .render_obp0(b_render_obp0), .render_obp1(b_render_obp1),
        .wy(b_wy), .wx(b_wx), .stat_enable(b_stat_enable), .stat_observe(b_stat),
        .stat_write(b_stat_write), .lyc_write(b_lyc_write),
        .lcd_enable(b_lcd_enable), .lcd_disable(b_lcd_disable)
    );

    task automatic same(input string signal, input logic [31:0] a, input logic [31:0] b);
        if (a !== b) $fatal(1, "IO_PEEK_DIVERGENCE signal=%0s", signal);
        checks = checks + 1;
    endtask

    task automatic expect_word(input logic [31:0] value, input logic [31:0] expected);
        if (!peek_valid || value !== expected)
            $fatal(1, "IO_PEEK_VALUE address=%08x expected=%08x actual=%08x valid=%b",
                peek_address, expected, value, peek_valid);
        checks = checks + 1;
    endtask

    initial clk_sys = 0;
    always #5 clk_sys = ~clk_sys;

    // Deterministic stimulus. Commits land on ticks only, one owner at a time.
    always_comb begin
        gb_tick = !reset && lfsr[1:0] == 2'b01;
        io_wdata = lfsr[15:8];
        ly = lfsr[23:16] % 8'd154;
        mode = lfsr[5:4];
        coincidence = lfsr[6];
        source_level = lfsr[12:8];
        source_event = gb_tick ? lfsr[20:16] & 5'b10000 : 5'd0;
        irq_ack = gb_tick && lfsr[7] ? 5'(5'd1 << (lfsr[6:4] % 3'd5)) : 5'd0;
        divider_reset_request = gb_tick && lfsr[31:28] == 4'hF;
        io_write = 1;
        io_address = 16'hFF00;
        timer_commit = 0;
        irq_commit = 0;
        ppu_commit = 0;
        if (gb_tick && !reset) begin
            case (lfsr[27:26])
                2'd0: begin
                    io_address = n2m_interfaces_pkg::GB_REG_DIV + 16'(lfsr[25:24]);
                    timer_commit = 1;
                end
                2'd1: begin
                    io_address = lfsr[24] ? n2m_interfaces_pkg::GB_REG_IE : n2m_interfaces_pkg::GB_REG_IF;
                    irq_commit = 1;
                end
                default: begin
                    io_address = n2m_interfaces_pkg::GB_REG_LCDC + 16'(lfsr[25:22] % 4'd12);
                    ppu_commit = 1;
                end
            endcase
        end
    end

    // The peek agent. It walks every exposed host address, one per edge.
    assign peek_address = PEEK_FIRST + 32'(peek_index) * 32'd4;

    always @(posedge clk_sys) begin
        lfsr <= {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
        peek_index <= peek_index == 5'(PEEK_WORDS - 1) ? 5'd0 : peek_index + 5'd1;
    end

    // Every committed observation must match between the peeked and unpeeked
    // copies on every edge, including during reset.
    always @(negedge clk_sys) begin
        if (cycle > 0) begin
            same("div", {24'd0, a_div}, {24'd0, b_div});
            same("tima", {24'd0, a_tima}, {24'd0, b_tima});
            same("tma", {24'd0, a_tma}, {24'd0, b_tma});
            same("tac", {24'd0, a_tac}, {24'd0, b_tac});
            same("timer_request", {31'd0, a_timer_request.request}, {31'd0, b_timer_request.request});
            same("if", {27'd0, a_if_stored}, {27'd0, b_if_stored});
            same("ie", {24'd0, a_ie_stored}, {24'd0, b_ie_stored});
            same("if_observe", {27'd0, a_if_observe}, {27'd0, b_if_observe});
            same("ie_observe", {24'd0, a_ie_observe}, {24'd0, b_ie_observe});
            same("lcdc", {24'd0, a_lcdc}, {24'd0, b_lcdc});
            same("stat", {24'd0, a_stat}, {24'd0, b_stat});
            same("scy", {24'd0, a_scy}, {24'd0, b_scy});
            same("scx", {24'd0, a_scx}, {24'd0, b_scx});
            same("lyc", {24'd0, a_lyc}, {24'd0, b_lyc});
            same("bgp", {24'd0, a_bgp}, {24'd0, b_bgp});
            same("obp0", {24'd0, a_obp0}, {24'd0, b_obp0});
            same("obp1", {24'd0, a_obp1}, {24'd0, b_obp1});
            same("wy", {24'd0, a_wy}, {24'd0, b_wy});
            same("wx", {24'd0, a_wx}, {24'd0, b_wx});
            same("render_bgp", {24'd0, a_render_bgp}, {24'd0, b_render_bgp});
            same("render_obp0", {24'd0, a_render_obp0}, {24'd0, b_render_obp0});
            same("render_obp1", {24'd0, a_render_obp1}, {24'd0, b_render_obp1});
            // Injection deliberately drives copy A's DMG port with a different
            // address, so its port readback is not comparable; its state is.
            if (!disturb) same("timer_rdata", {24'd0, a_timer_rdata}, {24'd0, b_timer_rdata});
            same("irq_rdata", {24'd0, a_irq_rdata}, {24'd0, b_irq_rdata});
            same("ppu_rdata", {24'd0, a_ppu_rdata}, {24'd0, b_ppu_rdata});
            same("ppu_selected", {31'd0, a_ppu_selected}, {31'd0, b_ppu_selected});
            same("stat_enable", {28'd0, a_stat_enable}, {28'd0, b_stat_enable});
            same("stat_write", {31'd0, a_stat_write}, {31'd0, b_stat_write});
            same("lyc_write", {31'd0, a_lyc_write}, {31'd0, b_lyc_write});
            same("lcd_enable", {31'd0, a_lcd_enable}, {31'd0, b_lcd_enable});
            same("lcd_disable", {31'd0, a_lcd_disable}, {31'd0, b_lcd_disable});
            // The peeked word is the live committed value, never a stale copy.
            case (peek_address)
                n2m_interfaces_pkg::HOST_REG_IO_LCDC: expect_word(peek_data, {24'd0, a_lcdc});
                n2m_interfaces_pkg::HOST_REG_IO_STAT: expect_word(peek_data, {24'd0, a_stat});
                n2m_interfaces_pkg::HOST_REG_IO_LY: expect_word(peek_data, {24'd0, ly});
                n2m_interfaces_pkg::HOST_REG_IO_DIV: expect_word(peek_data, {24'd0, a_div});
                n2m_interfaces_pkg::HOST_REG_IO_TIMA: expect_word(peek_data, {24'd0, a_tima});
                n2m_interfaces_pkg::HOST_REG_IO_TAC: expect_word(peek_data, {24'd0, a_tac});
                n2m_interfaces_pkg::HOST_REG_IO_IF: expect_word(peek_data, {27'd0, a_if_stored});
                n2m_interfaces_pkg::HOST_REG_IO_IE: expect_word(peek_data, {24'd0, a_ie_stored});
                n2m_interfaces_pkg::HOST_REG_IO_LCD_STATUS:
                    expect_word(peek_data, {8'd0, a_lcdc, a_stat, ly});
                default: begin end
            endcase
            peeks = peeks + 1;
        end
        cycle = cycle + 1;
    end

    initial begin
        cycle = 0; checks = 0; peeks = 0; peek_index = 0; lfsr = 32'hACE1_2345;
        disturb = $test$plusargs("PEEK_DISTURB");
        reset = 1;
        $dumpfile("waves.vcd");
        $dumpvars(0, clk_sys, reset, gb_tick, peek_address, peek_data, peek_valid,
            a_div, b_div, a_if_stored, b_if_stored, a_stat, b_stat, cycle, checks);
        repeat (20) @(posedge clk_sys);
        reset = 0;
        repeat (CYCLES) @(posedge clk_sys);
        // Progress, so a silent stuck divider cannot pass as agreement.
        if (a_div === b_div && a_div === 8'd0 && a_tima === 8'd0)
            $fatal(1, "IO_PEEK_NO_PROGRESS div=%02x tima=%02x", a_div, a_tima);
        $display("PASS io peek isolation checks=%0d peeks=%0d", checks, peeks);
        $finish;
    end
endmodule
