`timescale 1ns/1ps
`default_nettype none
// Composed proof that serial, audio-register and wave-RAM accesses are served
// by owners instead of faulting the CPU port. The owner selection repeats the
// v0.5 system composition; the CPU port, decoder and stores are the real ones.
module tb_audio_service;
    logic clk_sys, reset_sys, core_reset, init_done;
    logic request_valid, write_enable, bus_commit, response_valid, contract_fault, gb_tick;
    logic [15:0] address;
    logic [7:0] write_data, read_data;
    logic storage_read, storage_write, storage_valid;
    n2m_memory_pkg::memory_store_t storage_store;
    logic [14:0] storage_offset;
    logic [7:0] storage_wdata, storage_rdata;
    logic owner_prepare, owner_commit, owner_write, owner_valid, owner_service;
    logic [15:0] owner_address;
    logic [7:0] owner_wdata, owner_rdata;
    n2m_memory_pkg::memory_destination_t destination;
    logic [7:0] serial_rdata, apu_rdata;
    logic apu_valid, apu_audio_io;
    logic wave_read, wave_write, wave_valid;
    logic [3:0] wave_address;
    logic [7:0] wave_wdata, wave_rdata;
    logic [7:0] host_rdata, unused_vram;
    logic [15:0] unused_oam;
    logic host_valid, unused_vram_valid, unused_oam_valid;
    integer index, pass, settle, register_reads, register_writes, wave_reads, wave_writes, serial_cases;
    bit mask_corrupt, wave_corrupt, drop_service;

    n2m_memory_cpu_port dut (
        .clk_sys, .reset_sys, .core_reset, .init_done, .request_valid, .address,
        .write_enable, .write_data, .bus_commit, .read_data, .response_valid, .contract_fault,
        .storage_read, .storage_write, .storage_store, .storage_offset, .storage_wdata,
        .storage_rdata, .storage_valid, .owner_prepare, .owner_commit,
        .owner_destination(destination), .owner_address, .owner_write, .owner_wdata,
        .owner_rdata, .owner_valid, .owner_service_available(owner_service)
    );
    n2m_memory_stores stores (.oam_request('0), .oam_response(),
        .clk_sys, .reset_sys, .core_reset, .init_done,
        .access_read(storage_read), .access_write(storage_write), .access_store(storage_store),
        .access_address(storage_offset), .access_wdata(storage_wdata),
        .access_rdata(storage_rdata), .access_valid(storage_valid),
        .host_read(1'b0), .host_write(1'b0), .host_offset(32'd0), .host_wdata(8'd0),
        .host_rdata(host_rdata), .host_valid(host_valid),
        .ppu_vram_read(1'b0), .ppu_vram_address(13'd0), .ppu_vram_rdata(unused_vram),
        .ppu_vram_valid(unused_vram_valid),
        .ppu_oam_read(1'b0), .ppu_oam_pair(7'd0), .ppu_oam_rdata(unused_oam),
        .ppu_oam_valid(unused_oam_valid),
        .wave_read, .wave_write, .wave_address, .wave_wdata, .wave_rdata, .wave_valid
    ,
        .core_paused(1'b0), .oam_sequence_active(1'b0), .peek_ready(), .peek_read(1'b0), .peek_select(8'd0), .peek_offset(13'd0),
        .peek_rdata(), .peek_valid());
    n2m_serial u_serial (
        .clk_sys, .reset_sys, .core_reset, .gb_tick,
        .io_commit(owner_commit && destination == n2m_memory_pkg::MEMORY_SERIAL),
        .io_write(owner_write), .io_address(owner_address), .io_wdata(owner_wdata),
        .io_selected(), .io_rdata(serial_rdata)
    );
    n2m_apu u_apu (
        .clk_sys, .reset_sys, .core_reset, .gb_tick,
        .io_prepare(owner_prepare && apu_audio_io), .io_commit(owner_commit && apu_audio_io),
        .io_write(owner_write), .io_address(owner_address), .io_wdata(owner_wdata),
        .io_selected(), .io_rdata(apu_rdata), .io_valid(apu_valid),
        .wave_read, .wave_write, .wave_address, .wave_wdata, .wave_rdata, .wave_valid
    );
    assign apu_audio_io = destination == n2m_memory_pkg::MEMORY_APU
        || destination == n2m_memory_pkg::MEMORY_WAVE;
    // The same owner selection the v0.5 system performs, without other owners.
    always_comb begin
        owner_service = 1;
        owner_valid = 1;
        owner_rdata = 0;
        case (destination)
            n2m_memory_pkg::MEMORY_SERIAL: owner_rdata = serial_rdata;
            n2m_memory_pkg::MEMORY_APU, n2m_memory_pkg::MEMORY_WAVE: begin
                owner_rdata = apu_rdata;
                owner_valid = apu_valid;
            end
            default: begin owner_service = 0; owner_valid = 0; end
        endcase
        if (drop_service && destination == n2m_memory_pkg::MEMORY_SERIAL) owner_service = 0;
    end

    // Independent restatement of the pinned SameBoy read-back masks with the
    // APU powered off; FF15 and FF1F are unassigned I/O and return FF.
    function automatic logic [7:0] expected_audio(input logic [15:0] target);
        case (target)
            16'hff10: expected_audio = 8'h80;
            16'hff11: expected_audio = 8'h3f;
            16'hff12: expected_audio = 8'h00;
            16'hff13: expected_audio = 8'hff;
            16'hff14: expected_audio = 8'hbf;
            16'hff16: expected_audio = 8'h3f;
            16'hff17: expected_audio = 8'h00;
            16'hff18: expected_audio = 8'hff;
            16'hff19: expected_audio = 8'hbf;
            16'hff1a: expected_audio = 8'h7f;
            16'hff1b: expected_audio = 8'hff;
            16'hff1c: expected_audio = 8'h9f;
            16'hff1d: expected_audio = 8'hff;
            16'hff1e: expected_audio = 8'hbf;
            16'hff20: expected_audio = 8'hff;
            16'hff21: expected_audio = 8'h00;
            16'hff22: expected_audio = 8'h00;
            16'hff23: expected_audio = 8'hbf;
            16'hff24: expected_audio = 8'h00;
            16'hff25: expected_audio = 8'h00;
            16'hff26: expected_audio = 8'h70;
            default: expected_audio = 8'hff;
        endcase
    endfunction

    function automatic logic [7:0] wave_pattern(input integer offset, input integer round);
        wave_pattern = round == 0 ? 8'((offset << 4) | (15 - offset))
            : 8'(((15 - offset) << 4) | offset);
    endfunction

    task automatic edge_cycle;
        #4;
        clk_sys = 1;
        #1;
        clk_sys = 0;
        #1;
        if (contract_fault) $fatal(1, "AUDIO_CONTRACT_FAULT address=%04h", address);
    endtask

    task automatic initialize;
        index = 0;
        while (!init_done && index < 8193) begin
            edge_cycle();
            index = index + 1;
        end
        if (!init_done) $fatal(1, "AUDIO_INIT_BOUND");
    endtask

    task automatic read_byte(input logic [15:0] target, input logic [7:0] expected);
        address = target; write_enable = 0; request_valid = 1; bus_commit = 0;
        if (mask_corrupt && target == 16'hff26) force u_apu.io_rdata = 8'h71;
        #1;
        settle = 0;
        while (!response_valid && settle < 8) begin
            edge_cycle();
            settle = settle + 1;
        end
        if (!response_valid) $fatal(1, "AUDIO_NO_RESPONSE address=%04h", target);
        if (read_data !== expected)
            $fatal(1, "AUDIO_READ address=%04h expected=%02h actual=%02h", target, expected, read_data);
        bus_commit = 1; gb_tick = 1;
        edge_cycle();
        bus_commit = 0; gb_tick = 0; request_valid = 0;
        edge_cycle();
    endtask

    task automatic write_byte(input logic [15:0] target, input logic [7:0] value);
        address = target; write_data = value; write_enable = 1; request_valid = 1; bus_commit = 0;
        if (wave_corrupt && target == 16'hff30) force u_apu.wave_wdata = 8'h00;
        edge_cycle();
        bus_commit = 1; gb_tick = 1;
        edge_cycle();
        bus_commit = 0; gb_tick = 0; request_valid = 0; write_enable = 0;
        edge_cycle();
        if (wave_corrupt && target == 16'hff30) release u_apu.wave_wdata;
    endtask

    initial begin
        clk_sys = 0; reset_sys = 1; core_reset = 0;
        request_valid = 0; write_enable = 0; bus_commit = 0; gb_tick = 0;
        address = 16'hff10; write_data = 0;
        register_reads = 0; register_writes = 0; wave_reads = 0; wave_writes = 0; serial_cases = 0;
        mask_corrupt = $test$plusargs("mask_corrupt");
        wave_corrupt = $test$plusargs("wave_corrupt");
        drop_service = $test$plusargs("drop_service");
        $dumpfile("audio-service.vcd");
        $dumpvars(0, clk_sys, reset_sys, core_reset, init_done, request_valid, address,
            write_enable, write_data, bus_commit, read_data, response_valid, contract_fault,
            destination, owner_prepare, owner_commit, owner_service, owner_valid, owner_rdata,
            wave_read, wave_write, wave_address, wave_wdata, wave_rdata, wave_valid);
        edge_cycle();
        reset_sys = 0;
        initialize();
        // Serial first: a bare LD (SC),A is the access that used to fault.
        write_byte(16'hff01, 8'ha5); serial_cases = serial_cases + 1;
        read_byte(16'hff01, 8'ha5); serial_cases = serial_cases + 1;
        write_byte(16'hff02, 8'h81); serial_cases = serial_cases + 1;
        read_byte(16'hff02, 8'hff); serial_cases = serial_cases + 1;
        write_byte(16'hff02, 8'h00); serial_cases = serial_cases + 1;
        read_byte(16'hff02, 8'h7e); serial_cases = serial_cases + 1;
        read_byte(16'hff01, 8'ha5); serial_cases = serial_cases + 1;
        // Every audio register reads its mask, before and after ignored writes.
        for (pass = 0; pass < 3; pass = pass + 1) begin
            if (pass > 0) begin
                for (index = 16'hff10; index <= 16'hff26; index = index + 1) begin
                    write_byte(16'(index), pass == 1 ? 8'h00 : 8'hff);
                    register_writes = register_writes + 1;
                end
            end
            for (index = 16'hff10; index <= 16'hff26; index = index + 1) begin
                read_byte(16'(index), expected_audio(16'(index)));
                register_reads = register_reads + 1;
            end
        end
        // Wave RAM is plain storage: cleared to the RAM fill, then rewritable.
        for (index = 0; index < 16; index = index + 1) begin
            read_byte(16'(16'hff30 + index), 8'h00);
            wave_reads = wave_reads + 1;
        end
        for (pass = 0; pass < 2; pass = pass + 1) begin
            for (index = 0; index < 16; index = index + 1) begin
                write_byte(16'(16'hff30 + index), wave_pattern(index, pass));
                wave_writes = wave_writes + 1;
            end
            for (index = 0; index < 16; index = index + 1) begin
                read_byte(16'(16'hff30 + index), wave_pattern(index, pass));
                wave_reads = wave_reads + 1;
            end
        end
        if (contract_fault) $fatal(1, "AUDIO_CONTRACT_FAULT_FINAL");
        $display("PASS audio service register_reads=%0d register_writes=%0d wave_reads=%0d wave_writes=%0d serial_cases=%0d",
            register_reads, register_writes, wave_reads, wave_writes, serial_cases);
        $finish;
    end
    initial begin
        #2000000;
        $fatal(1, "AUDIO_SERVICE_TIMEOUT");
    end
endmodule
