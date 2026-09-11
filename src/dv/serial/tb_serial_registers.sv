`timescale 1ns/1ps
`default_nettype none
// Serial owner contract: SB is plain storage, SC keeps two DMG control bits
// and reads its unused bits as one. No transfer or interrupt behavior exists.
module tb_serial_registers;
    logic clk_sys, reset_sys, core_reset, gb_tick;
    logic io_commit, io_write, io_selected;
    logic [15:0] io_address;
    logic [7:0] io_wdata, io_rdata;
    integer item, case_number, checks, trace;
    bit corrupt, boundary_fault;
    n2m_serial dut (.*);

    task automatic edge_cycle;
        clk_sys = 0; #5 clk_sys = 1; #5 clk_sys = 0;
    endtask

    task automatic check_read(input logic [15:0] target, input logic [7:0] expected);
        io_address = target;
        #1;
        if (io_selected !== 1'b1 || io_rdata !== expected)
            $fatal(1, "SERIAL_REG_READ case=%0d address=%04h expected=%02h actual=%02h",
                case_number, target, expected, io_rdata);
        $fdisplay(trace, "%0d,%04h,%02h,%02h", case_number, target, expected, io_rdata);
        checks = checks + 1;
        case_number = case_number + 1;
    endtask

    task automatic write_reg(input logic [15:0] target, input logic [7:0] value);
        io_address = target; io_wdata = value; io_write = 1; io_commit = 1; gb_tick = 1;
        edge_cycle();
        io_write = 0; io_commit = 0; gb_tick = 0;
    endtask

    initial begin
        clk_sys = 0; reset_sys = 1; core_reset = 0; gb_tick = 0;
        io_commit = 0; io_write = 0; io_address = 16'hff01; io_wdata = 0;
        case_number = 0; checks = 0;
        corrupt = $test$plusargs("corrupt");
        boundary_fault = $test$plusargs("boundary_fault");
        trace = $fopen("serial-registers.csv", "w");
        if (!trace) $fatal(1, "SERIAL_REG_TRACE");
        $fdisplay(trace, "case,address,expected,actual");
        $dumpfile("serial-registers.vcd");
        $dumpvars(0, clk_sys, reset_sys, core_reset, gb_tick, io_commit, io_write,
            io_address, io_wdata, io_selected, io_rdata);
        edge_cycle();
        // Reset holds the profile peripheral fill; SC still reads its mask.
        check_read(16'hff01, 8'h00);
        check_read(16'hff02, 8'h7e);
        reset_sys = 0; edge_cycle();
        check_read(16'hff01, 8'h00);
        if (corrupt) force dut.io_rdata = 8'h7c;
        check_read(16'hff02, 8'h7e);
        if (boundary_fault) begin
            io_commit = 1; io_write = 1; gb_tick = 0; edge_cycle();
            $fatal(1, "SERIAL_REG_BOUNDARY_NOT_DETECTED");
        end
        // SB keeps every written byte; SC is unchanged by an SB write.
        for (item = 0; item < 256; item = item + 1) begin
            write_reg(16'hff01, 8'(item));
            check_read(16'hff01, 8'(item));
            check_read(16'hff02, 8'h7e);
        end
        // SC keeps only transfer enable and clock select; SB is unchanged.
        for (item = 0; item < 256; item = item + 1) begin
            write_reg(16'hff02, 8'(item));
            check_read(16'hff02, {item[7], 6'b000000, item[0]} | 8'h7e);
            check_read(16'hff01, 8'hff);
        end
        // Uncommitted and read commits leave both registers alone.
        io_wdata = 8'h5a; io_write = 1; repeat (4) edge_cycle();
        io_write = 0; io_commit = 1; gb_tick = 1; io_address = 16'hff01; edge_cycle();
        io_commit = 0; gb_tick = 0;
        check_read(16'hff01, 8'hff);
        check_read(16'hff02, 8'hff);
        // Both resets restore the profile fill under a competing write.
        for (item = 0; item < 2; item = item + 1) begin
            io_commit = 1; io_write = 1; gb_tick = 1; io_address = 16'hff01; io_wdata = 8'h3c;
            if (item == 0) core_reset = 1; else reset_sys = 1;
            check_read(16'hff01, 8'h00);
            check_read(16'hff02, 8'h7e);
            edge_cycle();
            io_commit = 0; io_write = 0; gb_tick = 0; core_reset = 0; reset_sys = 0;
            edge_cycle();
        end
        $fclose(trace);
        $display("PASS serial registers sb_writes=256 sc_writes=256 checks=%0d resets=2", checks);
        $finish;
    end
    initial begin
        #200000;
        $fatal(1, "SERIAL_REG_TIMEOUT");
    end
endmodule
