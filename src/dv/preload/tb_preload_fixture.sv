`timescale 1ns/1ps
`default_nettype none
// Preload boundary check for the builder's prepared fixture files. The stage
// prepares preload-rom.mif, preload-presence.mif and preload-crc.hex in the
// run directory; this testbench reads them back the way a simulation does
// (paths relative to the run directory), rebuilds the image from the MIF and
// requires the CRC hex, entry stub and title of the original integration image.
// No product RTL is instantiated: this proves the file pipeline, not memory.
module tb_preload_fixture;
    localparam int unsigned BYTES = 32768;
    logic [7:0] image [0:BYTES-1];
    logic [31:0] crc_word [0:0];
    bit loaded [0:BYTES-1];
    integer fd, matched, address, value, count;
    logic [31:0] crc, entry;
    string line;
    string title;
    integer index, bit_index;
    initial begin
        count = 0;
        for (index = 0; index < BYTES; index = index + 1) loaded[index] = 1'b0;
        // The ROM MIF: "AAAA : DD;" lines between a header and END.
        fd = $fopen("preload-rom.mif", "r");
        if (fd == 0) $fatal(1, "PRELOAD_FIXTURE_OPEN preload-rom.mif");
        while (!$feof(fd)) begin
            if ($fgets(line, fd) == 0) break;
            matched = $sscanf(line, "%h : %h;", address, value);
            if (matched != 2) continue;
            if (address < 0 || address >= BYTES) $fatal(1, "PRELOAD_FIXTURE_ADDRESS %0d", address);
            if (loaded[address]) $fatal(1, "PRELOAD_FIXTURE_DUPLICATE %04x", address);
            image[address] = value[7:0];
            loaded[address] = 1'b1;
            count = count + 1;
        end
        $fclose(fd);
        if (count != BYTES) $fatal(1, "PRELOAD_FIXTURE_COUNT expected=%0d actual=%0d", BYTES, count);
        // The presence MIF must exist beside it; its single range row is fixed text.
        fd = $fopen("preload-presence.mif", "r");
        if (fd == 0) $fatal(1, "PRELOAD_FIXTURE_OPEN preload-presence.mif");
        matched = 0;
        while (!$feof(fd)) begin
            if ($fgets(line, fd) == 0) break;
            if (line == "[0000..7FFF] : 1;\n") matched = matched + 1;
        end
        $fclose(fd);
        if (matched != 1) $fatal(1, "PRELOAD_FIXTURE_PRESENCE rows=%0d", matched);
        // CRC-32 (IEEE, reflected) over the rebuilt image must equal the hex file
        // the loader reads through $readmemh under SIM_PRELOAD.
        $readmemh("preload-crc.hex", crc_word);
        crc = 32'hffff_ffff;
        for (index = 0; index < BYTES; index = index + 1) begin
            crc = crc ^ {24'd0, image[index]};
            for (bit_index = 0; bit_index < 8; bit_index = bit_index + 1)
                crc = crc[0] ? (crc >> 1) ^ 32'hedb8_8320 : crc >> 1;
        end
        crc = ~crc;
        if (crc !== crc_word[0]) $fatal(1, "PRELOAD_FIXTURE_CRC expected=%08x actual=%08x", crc_word[0], crc);
        // Original integration image: NOP; JP 0200 entry stub and packaged title.
        entry = 32'd0;
        for (index = 'h100; index < 'h104; index = index + 1) entry = {entry[23:0], image[index]};
        if (entry != 32'h00c3_0002) $fatal(1, "PRELOAD_FIXTURE_ENTRY %08x", entry);
        title = "";
        for (index = 'h134; index < 'h13d; index = index + 1) title = {title, string'(image[index])};
        if (title != "N2M SMOKE") $fatal(1, "PRELOAD_FIXTURE_TITLE %s", title);
        $display("PASS preload-fixture bytes=%0d entry=0200 crc=%08x", count, crc);
        $finish;
    end
endmodule
