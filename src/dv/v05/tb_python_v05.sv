`timescale 1ns/1ps
`default_nettype none
// Passive owner-boundary samples. Python owns stimulus and all expectations.
module tb_python_v05 #(
    parameter bit PRELOADED = 0,
    parameter logic [127:0] BUILD_ID = 128'h88000000000000000000000000000001
);
    logic clk_sys, clk_pix, reset_sys, reset_pix, uart_rx, uart_tx;
    logic physical_commit;
    logic [7:0] physical_buttons, effective_buttons, input_source_observe;
    logic [3:0] red, green, blue;
    logic hsync_n, vsync_n;
    logic [63:0] display_sequence, dot_count;
    logic [31:0] display_epoch, epoch;
    logic gb_tick, paused, core_reset, retirement_valid, bus_commit, write_enable;
    n2m_interfaces_pkg::retirement_t retirement;
    logic [15:0] address;
    logic [7:0] write_data, read_data;
    logic [4:0] irq_ack;
    logic source_valid, source_start, source_abort, source_display_eligible, fault;
    logic [1:0] source_shade;
    logic [7:0] source_x, source_y;
    logic [31:0] source_epoch;
    logic [63:0] source_dot;
    logic record_event, pixel_event, input_event, write_event, bus_event;
    logic [88:0] bus_sample;
    logic dma_event, oam_store_event;
    logic [81:0] dma_sample;
    logic [88:0] oam_store_sample;
    n2m_interfaces_pkg::retirement_t record_sample;
    logic [116:0] pixel_sample;
    logic [103:0] input_sample;
    logic [87:0] write_sample;
    integer public_trace;
    integer public_lines;
    integer public_flushed;
    integer public_flush_age;
    logic public_trace_close;

    // Python opens fixed public-boundary observation windows. This projection
    // changes only waveform storage; stimulus/checkers stay continuous.
    logic wave_enable, wave_clock;
    logic [63:0] wave_dot;
    logic [31:0] wave_epoch;
    logic [7:0] wave_control;
    logic [116:0] wave_pixel;
    logic [383:0] wave_retirement;
    logic [23:0] wave_write;
    logic [103:0] wave_input;
    logic [33:0] wave_load;
    assign wave_clock = wave_enable && clk_sys;
    assign wave_dot = wave_enable ? dot_count : 64'd0;
    assign wave_epoch = wave_enable ? epoch : 32'd0;
    assign wave_control = wave_enable ? {reset_sys, core_reset, paused, fault,
        gb_tick, retirement_valid, bus_commit, source_valid} : 8'd0;
    assign wave_pixel = wave_enable ? pixel_sample : 117'd0;
    assign wave_retirement = wave_enable ? record_sample : 384'd0;
    assign wave_write = wave_enable ? {address,write_data} : 24'd0;
    assign wave_input = wave_enable ? input_sample : 104'd0;
    assign wave_load = wave_enable ? {dut.rom_write, dut.rom_read,
        dut.rom_address, dut.rom_write_data, dut.rom_read_valid, dut.rom_read_data} : 34'd0;

    n2m_v05_system #(.UART_BAUD(3125000), .BUILD_ID(BUILD_ID)) dut (.*);
    defparam dut.u_stores.rom.SIM_INIT_FILE = PRELOADED ? "preload-rom.mif" : "UNUSED";
    defparam dut.u_uart.u_commands.u_load.u_presence.u_presence.SIM_INIT_FILE = PRELOADED ? "preload-presence.mif" : "UNUSED";
    defparam dut.u_uart.u_commands.u_load.SIM_PRELOAD = PRELOADED;
    always #20 clk_sys = !clk_sys;
    always #19.841 clk_pix = !clk_pix;

    always @(posedge clk_sys) begin
        if (!reset_sys && !core_reset && gb_tick && dut.cpu_phase == 2'd3) begin
            dma_sample <= {64'(dot_count + 1), dut.dma_active,
                dut.u_dma.engine_write, dut.dma_active ? dut.u_dma.engine_offset : 8'd0,
                dut.u_dma.engine_write ? dut.u_dma.engine_data : 8'd0};
            dma_event <= !dma_event;
        end
        if (!reset_sys && !core_reset && |dut.oam_request.write_enable) begin
            oam_store_sample <= {dot_count, dut.oam_request.pair,
                dut.oam_request.write_enable, dut.oam_request.data};
            oam_store_event <= !oam_store_event;
        end
        if (!reset_sys && bus_commit) begin
            bus_sample <= {64'(dot_count + 1), address, write_enable,
                           write_enable ? write_data : read_data};
            bus_event <= !bus_event;
        end
        if (!reset_sys && bus_commit && write_enable) begin
            write_sample <= {64'(dot_count + 1), address, write_data};
            write_event <= !write_event;
            if (public_trace) begin
                $fdisplay(public_trace, "W %022h", {64'(dot_count + 1), address, write_data});
                public_lines = public_lines + 1;
            end
        end
        // Effective update is consumed by JOYP on this edge, off gb_tick.
        if (!reset_sys && !core_reset && dut.effective_update.valid) begin
            input_sample <= {epoch, dot_count, dut.effective_update.buttons};
            input_event <= !input_event;
            if (public_trace) begin
                $fdisplay(public_trace, "I %026h", {epoch, dot_count, dut.effective_update.buttons});
                public_lines = public_lines + 1;
            end
        end
        #1;
        if (!reset_sys && retirement_valid) begin
            record_sample <= retirement;
            record_event <= !record_event;
            if (public_trace) begin
                $fdisplay(public_trace, "R %096h", retirement);
                public_lines = public_lines + 1;
            end
        end
        if (!reset_sys && source_valid) begin
            pixel_sample <= {source_dot, source_epoch, source_x, source_y,
                             source_shade, source_start, source_abort, source_display_eligible};
            pixel_event <= !pixel_event;
            if (public_trace) begin
                $fdisplay(public_trace, "P %030h", {source_dot, source_epoch, source_x, source_y,
                    source_shade, source_start, source_abort, source_display_eligible});
                public_lines = public_lines + 1;
            end
        end
        // A final partial batch must become visible even when software HALTs
        // and produces no more events. This changes file visibility only.
        if (public_trace && public_lines != public_flushed)
            public_flush_age = public_flush_age + 1;
        if (public_trace && public_lines != public_flushed &&
            (public_lines - public_flushed >= 512 || public_flush_age >= 1024 || paused)) begin
            $fflush(public_trace);
            public_flushed = public_lines;
            public_flush_age = 0;
        end
        if (public_trace && public_trace_close) begin
            $fdisplay(public_trace, "END %0d", public_lines);
            $fclose(public_trace);
            public_trace = 0;
        end
    end

    // Stop actual emulated progress during CPU HALT; the Python watchdog must fail.
    initial begin
        public_trace = 0;
        public_lines = 0;
        public_flushed = 0;
        public_flush_age = 0;
        public_trace_close = 0;
        if ($test$plusargs("springtrail_trace")) begin
            public_trace = $fopen("springtrail.trace", "w");
            if (!public_trace) $fatal(1, "SPRINGTRAIL_TRACE_OPEN");
        end
        if ($test$plusargs("stackdrop_trace")) begin
            public_trace = $fopen("stackdrop.trace", "w");
            if (!public_trace) $fatal(1, "STACKDROP_TRACE_OPEN");
        end
        if ($test$plusargs("physical_mask_fault")) begin
            @(negedge clk_sys);
            force dut.u_uart.physical_buttons = 8'd1;
        end
    end

    // Corrupt only the first prepared Y store; publication must read it back.
    initial begin
        if ($test$plusargs("render_scene_fault")) begin
            do @(negedge clk_sys);
            while (!(dut.raw_write && dut.raw_store == n2m_memory_pkg::STORE_WRAM &&
                     dut.raw_offset == 15'h0100 && dut.raw_wdata == 8'd128));
            $display("RENDER_SCENE_MUTATION expected=128 actual=0 dot=%0d", dot_count);
            force dut.u_stores.ram_wdata = 8'd0;
            @(posedge clk_sys);
            @(negedge clk_sys);
            release dut.u_stores.ram_wdata;
        end
    end

    // Drop the first collected bit in the actual store only. The public CPU
    // write remains one; the next call must expose a second score increment.
    initial begin
        if ($test$plusargs("flow_item_fault")) begin
            do @(negedge clk_sys);
            while (!(dut.raw_write && dut.raw_store == n2m_memory_pkg::STORE_WRAM &&
                     dut.raw_offset == 15'h002c && dut.raw_wdata == 8'd1));
            $display("FLOW_ITEM_MUTATION expected=1 actual=0 dot=%0d", dot_count);
            force dut.u_stores.ram_wdata = 8'd0;
            @(posedge clk_sys);
            @(negedge clk_sys);
            release dut.u_stores.ram_wdata;
        end
    end

    // Change one real WRAM store after the original unit's first call marker.
    // The later prepared-image read must expose the corrupt stored cell.
    initial begin
        if ($test$plusargs("stackdrop_cell_fault")) begin
            wait(bus_commit && write_enable && address == 16'hc0ee);
            do @(negedge clk_sys);
            while (!(dut.raw_write && dut.raw_store == n2m_memory_pkg::STORE_WRAM && dut.raw_offset == 15'h0100));
            if (dut.raw_wdata !== 8'd0) $fatal(1, "STACKDROP_FAULT_SOURCE");
            $display("STACKDROP_CELL_MUTATION expected=0 actual=1 dot=%0d", dot_count);
            force dut.raw_wdata = 8'd1;
            @(posedge clk_sys);
            @(negedge clk_sys);
            release dut.raw_wdata;
        end
    end

    initial begin
        if ($test$plusargs("progress_fault")) begin
            wait(dot_count >= 64'd50000);
            @(negedge clk_sys);
            force dut.gb_tick = 1'b0;
        end
    end

    // Corrupt the actual timer read route; the independent DIV expectation stays1.
    initial begin
        if ($test$plusargs("timer_read_fault")) begin
            @(negedge clk_sys);
            force dut.timer_rdata = 8'd0;
        end
    end

    // Mutate the first byte at the actual Intel OAM pair-write boundary.
    initial begin
        if ($test$plusargs("dma_byte_fault")) begin
            do @(negedge clk_sys);
            while (!(dut.oam_request.write_enable == 2'b01 && dut.oam_request.pair == 0));
            if (dut.oam_request.data[7:0] !== 8'ha5) $fatal(1, "DMA239_FAULT_SOURCE");
            force dut.oam_request.data = 16'd0;
            @(posedge clk_sys);
            @(negedge clk_sys);
            release dut.oam_request.data;
        end
    end

    // Original ROM byte at0200 is DI/F3. Mutate only the actual storage write.
    initial begin
        if ($test$plusargs("image_fault")) begin
            do @(negedge clk_sys);
            while (!(!reset_sys && dut.rom_write && dut.rom_address == 15'h0200));
            if (dut.rom_write_data !== 8'hf3) $fatal(1, "V05_IMAGE_FAULT_SOURCE");
            wave_enable = 1;
            $display("V05_IMAGE_MUTATION address=0200 expected=f3 actual=00");
            force dut.rom_write_data = 8'h00;
            @(posedge clk_sys);
            @(negedge clk_sys);
            release dut.rom_write_data;
            wave_enable = 0;
        end
    end

    initial begin
        wave_enable = 0;
        clk_sys = 0;
        clk_pix = 0;
        reset_sys = 1;
        reset_pix = 1;
        uart_rx = 1;
        physical_commit = 0;
        physical_buttons = 0;
        record_event = 0;
        pixel_event = 0;
        input_event = 0;
        write_event = 0;
        bus_event = 0;
        dma_event = 0;
        oam_store_event = 0;
        if ($test$plusargs("pixel_fault")) begin
            wait(source_display_eligible && source_x == 0 && source_y == 0);
            force dut.source_shade = 2'd0;
        end
    end
    initial begin
        if ($test$plusargs("springtrail_pixel_fault")) begin
            wait(source_display_eligible && source_y == 0 && source_x == 0);
            @(negedge clk_sys);
            force dut.source_shade = 2'd1;
        end
    end
endmodule
