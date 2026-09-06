`timescale 1ns/1ps
`default_nettype none
module tb_interrupts;
    logic clk_sys, reset_sys, core_reset, gb_tick, io_commit, io_write;
    logic [15:0] io_address;
    logic [7:0] io_wdata, io_rdata, ie_stored, ie_observe;
    logic [4:0] source_level, irq_ack, if_stored, if_observe;
    logic io_selected;
    integer checks, trace_file, index, bit_number, initial_flag, writing, acknowledging, rising;
    logic [4:0] expected;
    logic [7:0] expected_ie;
    bit lost, duplicate, priority_fault;
    n2m_interrupts dut (.*);

    task automatic edge_cycle;
        #4; clk_sys = 1; #1; clk_sys = 0;
    endtask
    task automatic check(input logic [4:0] flags, input logic [7:0] enables);
        #1;
        $fdisplay(trace_file, "%0d,%02h,%02h,%02h,%02h,%02h,%02h", checks,
            flags, if_observe, enables, ie_observe, if_stored, ie_stored);
        if (if_observe !== flags || ie_observe !== enables)
            $fatal(1, "INTERRUPT_OBSERVE check=%0d expected_if=%02h actual_if=%02h expected_ie=%02h actual_ie=%02h",
                checks, flags, if_observe, enables, ie_observe);
        checks = checks + 1;
    endtask
    task automatic begin_a(input bit write_register, input logic [15:0] address,
                           input logic [7:0] data, input logic [4:0] ack);
        gb_tick = 1; io_commit = write_register; io_write = write_register;
        io_address = address; io_wdata = data; irq_ack = ack;
        edge_cycle();
        gb_tick = 0; io_commit = 0; io_write = 0; irq_ack = 0;
    endtask
    task automatic finish_b(input logic [4:0] flags, input logic [7:0] enables);
        check(flags, enables);
        edge_cycle();
        check(flags, enables);
        if (if_stored !== flags || ie_stored !== enables)
            $fatal(1, "INTERRUPT_STORED_AFTER_B");
    endtask
    task automatic write_if(input logic [4:0] flags);
        begin_a(1, 16'hFF0F, {3'b101, flags}, 0);
        finish_b(flags, expected_ie);
    endtask
    task automatic reset_case(input bit global_reset);
        gb_tick = 0; io_commit = 0; io_write = 0; irq_ack = 0;
        source_level = 0;
        if (global_reset) reset_sys = 1;
        else core_reset = 1;
        check(0, 0); edge_cycle();
        reset_sys = 0; core_reset = 0; expected_ie = 0;
        check(0, 0); edge_cycle();
    endtask

    initial begin
        $dumpfile("waves.vcd");
        $dumpvars(0, clk_sys, reset_sys, core_reset, gb_tick, io_commit, io_write,
            io_address, io_wdata, source_level, irq_ack, io_selected, io_rdata,
            if_stored, ie_stored, if_observe, ie_observe);
        trace_file = $fopen("trace.csv", "w");
        if (!trace_file) $fatal(1, "INTERRUPT_TRACE_OPEN");
        $fdisplay(trace_file, "check,expected_if,actual_if,expected_ie,actual_ie,stored_if,stored_ie");
        clk_sys = 0; reset_sys = 1; core_reset = 0; gb_tick = 0;
        io_commit = 0; io_write = 0; io_address = 0; io_wdata = 0;
        source_level = 0; irq_ack = 0; expected_ie = 0; checks = 0;
        lost = $test$plusargs("lost"); duplicate = $test$plusargs("duplicate");
        priority_fault = $test$plusargs("priority");
        edge_cycle(); reset_sys = 0; check(0, 0);

        // All five requests are recorded even with IE disabled. Repeated high
        // levels after a software clear cannot synthesize a second request.
        for (index = 0; index < 32; index = index + 1) begin
            source_level = 0; edge_cycle(); write_if(0);
            source_level = 5'(index);
            check(5'(index), 0); edge_cycle();
            if (lost && index == 1) force dut.flags_q = 5'd0;
            check(5'(index), 0);
            write_if(0);
            if (duplicate && index == 1) force dut.source_history = 5'd0;
            repeat (3) begin edge_cycle(); check(0, 0); end
        end
        source_level = 0; edge_cycle();

        // Byte-wide IE retention, low-five pending flags and fixed IF read mask.
        for (index = 0; index < 256; index = index + 1) begin
            begin_a(1, 16'hFFFF, 8'(index), 0);
            expected_ie = 8'(index); finish_b(0, expected_ie);
            io_address = 16'hFFFF; #1;
            if (!io_selected || io_rdata !== 8'(index)) $fatal(1, "INTERRUPT_IE_READ");
            write_if(5'(index));
            io_address = 16'hFF0F; #1;
            if (!io_selected || io_rdata !== (8'hE0 | 8'(index & 31)))
                $fatal(1, "INTERRUPT_IF_MASK");
            write_if(0);
        end
        io_address = 16'hFF0E; #1;
        if (io_selected) $fatal(1, "INTERRUPT_ADDRESS_ALIAS");
        io_address = 16'hFFFE; #1;
        if (io_selected) $fatal(1, "INTERRUPT_ADDRESS_ALIAS");
        reset_case(0);

        // Independent bit truth table: ack always zero; a write supplies its
        // literal value; without either operation a rise sets, otherwise hold.
        for (bit_number = 0; bit_number < 5; bit_number = bit_number + 1)
            for (initial_flag = 0; initial_flag < 2; initial_flag = initial_flag + 1)
                for (writing = 0; writing < 3; writing = writing + 1)
                    for (acknowledging = 0; acknowledging < 2; acknowledging = acknowledging + 1)
                        for (rising = 0; rising < 2; rising = rising + 1) begin
                            source_level = 0; edge_cycle();
                            write_if(5'(initial_flag << bit_number));
                            begin_a(writing != 0, 16'hFF0F,
                                writing == 2 ? 8'(1 << bit_number) : 8'd0,
                                acknowledging != 0 ? 5'(1 << bit_number) : 5'd0);
                            source_level = rising != 0 ? 5'(1 << bit_number) : 5'd0;
                            case ({1'(acknowledging), 2'(writing)})
                                3'b100, 3'b101, 3'b110, 3'b001: expected = 0;
                                3'b010: expected = 5'(1 << bit_number);
                                3'b000: expected = (initial_flag != 0 || rising != 0) ? 5'(1 << bit_number) : 5'd0;
                                default: $fatal(1, "INTERRUPT_ORACLE_CASE");
                            endcase
                            finish_b(expected, 0);
                            repeat (2) begin edge_cycle(); check(expected, 0); end
                        end

        reset_case(1);
        begin_a(1, 16'hFF0F, 8'h01, 5'h01);
        source_level = 1;
        if (priority_fault) force dut.operation_b = {1'b1, 1'b0, 8'h01, 5'h00};
        finish_b(0, 0);
        // A fully consumed overridden edge stays consumed after pause.
        repeat (5) begin edge_cycle(); check(0, 0); end
        source_level = 0; edge_cycle(); source_level = 1;
        check(1, 0); edge_cycle();

        // Reset cancels a real pending write before B, then a fresh source
        // rise is observable after release under either reset path.
        for (index = 0; index < 2; index = index + 1) begin
            source_level = 0; edge_cycle();
            begin_a(1, 16'hFFFF, 8'hA5, 0);
            check(1, 8'hA5);
            reset_case(index != 0);
            repeat (2) begin edge_cycle(); check(0, 0); end
            source_level = 1; check(1, 0); edge_cycle();
        end
        $display("PASS interrupt register truth table masks held sources reset observations checks=%0d", checks);
        $fclose(trace_file); $finish;
    end
    initial begin
        #200000;
        $fatal(1, "INTERRUPT_WATCHDOG");
    end
endmodule
