`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// Simulation double for the vendor altsyncram instance selected by
// n2m_intel_ram under the predefined VERILATOR macro. Quartus never sees it.
// Contract: wiki/src/rtl/common/MAS_memory_primitives.md.
//
// Port A reads or writes on clock0; port B reads on clock0 (single clock) or
// clock1 (dual clock). Each port captures its request at the rising edge and
// its output holds the captured word until the next enabled request, which
// gives one request edge of latency with an unregistered output stage.
module n2m_sim_dual_port_ram #(
    parameter integer DEPTH = 1024,
    parameter integer DATA_BITS = 8,
    parameter integer ADDRESS_BITS = $clog2(DEPTH),
    parameter integer LANES = 1,
    parameter bit DUAL_CLOCK = 0,
    parameter string INIT_FILE = "UNUSED"
) (
    input var logic clock0,
    input var logic clock1,
    input var logic [ADDRESS_BITS-1:0] address_a,
    input var logic [DATA_BITS-1:0] data_a,
    input var logic wren_a,
    input var logic rden_a,
    input var logic [LANES-1:0] byteena_a,
    output logic [DATA_BITS-1:0] q_a,
    input var logic [ADDRESS_BITS-1:0] address_b,
    input var logic rden_b,
    output logic [DATA_BITS-1:0] q_b
);
    // A lane is eight bits for byte-enabled shapes and the whole word for the
    // one- and two-bit shapes, whose single lane the wrapper always enables.
    localparam integer LANE_BITS = DATA_BITS / LANES;
    logic [DATA_BITS-1:0] words [0:DEPTH-1];
    logic read_clock_b;
    logic collision_b;
    assign read_clock_b = DUAL_CLOCK ? clock1 : clock0;

    // There is no X here. Data the vendor leaves undefined is drawn from the
    // run's seeded random stream, so an uninitialized or forbidden read fails
    // by mismatch instead of passing by accident.
    function automatic logic [DATA_BITS-1:0] unspecified();
        return DATA_BITS'($urandom);
    endfunction

    // NEW_DATA_NO_NBE_READ: a same-port read during write returns the written
    // lanes as new data and leaves the masked lanes undefined.
    function automatic logic [DATA_BITS-1:0] same_port_word(
        input logic [DATA_BITS-1:0] data, input logic [LANES-1:0] enable);
        logic [DATA_BITS-1:0] result;
        integer lane;
        result = unspecified();
        for (lane = 0; lane < LANES; lane = lane + 1)
            if (enable[lane]) result[lane*LANE_BITS +: LANE_BITS] = data[lane*LANE_BITS +: LANE_BITS];
        return result;
    endfunction

    function automatic logic [DATA_BITS-1:0] merged_word(
        input logic [DATA_BITS-1:0] old, input logic [DATA_BITS-1:0] data, input logic [LANES-1:0] enable);
        logic [DATA_BITS-1:0] result;
        integer lane;
        result = old;
        for (lane = 0; lane < LANES; lane = lane + 1)
            if (enable[lane]) result[lane*LANE_BITS +: LANE_BITS] = data[lane*LANE_BITS +: LANE_BITS];
        return result;
    endfunction

    // Port A: enabled lanes update the addressed word; an enabled read captures
    // the addressed word, or the new-data word on a same-port write.
    always_ff @(posedge clock0) begin
        if (int'(address_a) < DEPTH) begin
            if (wren_a) words[address_a] <= merged_word(words[address_a], data_a, byteena_a);
            if (rden_a) q_a <= wren_a ? same_port_word(data_a, byteena_a) : words[address_a];
        end
    end

    // Port B: the nonblocking A write leaves this same-edge read with OLD_DATA in
    // single-clock mode. In dual-clock mode a read of a word A is writing has no
    // defined device result (DONT_CARE), so it returns unspecified data.
    assign collision_b = DUAL_CLOCK && wren_a && address_a == address_b;
    always_ff @(posedge read_clock_b) begin
        if (rden_b && int'(address_b) < DEPTH)
            q_b <= collision_b ? unspecified() : words[address_b];
    end

    // Power-up: every word takes a seeded random value (power_up_uninitialized).
    // A preload replaces that fill 1 ps after time zero, so a testbench may
    // generate the file at time zero; no consumer clocks a request before then.
    // Reset never touches the array; the wrapper only masks requests.
    integer fill_index;
    initial begin
        for (fill_index = 0; fill_index < DEPTH; fill_index = fill_index + 1)
            words[fill_index] = unspecified();
        if (INIT_FILE != "UNUSED") begin
            #1ps;
            if (INIT_FILE.len() > 4 && INIT_FILE.substr(INIT_FILE.len() - 4, INIT_FILE.len() - 1) == ".mif")
                load_mif(INIT_FILE);
            else
                $readmemh(INIT_FILE, words);
        end
    end

    // Intel MIF as written by tools/n2m/preload.py: DEPTH/WIDTH/radix header,
    // then "address : value;" or "[first..last] : value;" rows until END.
    function automatic string trimmed(input string text);
        integer first, last;
        first = 0;
        last = text.len() - 1;
        while (first <= last && (text[first] == " " || text[first] == "\t" || text[first] == "\n" || text[first] == "\r"))
            first = first + 1;
        while (last >= first && (text[last] == " " || text[last] == "\t" || text[last] == "\n" || text[last] == "\r"))
            last = last - 1;
        return last < first ? "" : text.substr(first, last);
    endfunction

    function automatic integer radix_of(input string setting, input string line);
        if (line.substr(0, setting.len() - 1) != setting) return 0;
        if (line.substr(line.len() - 4, line.len() - 1) == "HEX;") return 16;
        if (line.substr(line.len() - 4, line.len() - 1) == "BIN;") return 2;
        if (line.substr(line.len() - 4, line.len() - 1) == "OCT;") return 8;
        if (line.substr(line.len() - 4, line.len() - 1) == "DEC;" || line.substr(line.len() - 4, line.len() - 1) == "UNS;") return 10;
        $fatal(1, "N2M_SIM_RAM_MIF_RADIX file=%s line=%s", INIT_FILE, line);
    endfunction

    function automatic longint parse_number(input string token, input integer radix);
        longint value;
        integer index, digit;
        byte character;
        value = 0;
        if (token.len() == 0) $fatal(1, "N2M_SIM_RAM_MIF_EMPTY_NUMBER file=%s", INIT_FILE);
        for (index = 0; index < token.len(); index = index + 1) begin
            character = token[index];
            if (character >= "0" && character <= "9") digit = int'(character) - int'("0");
            else if (character >= "a" && character <= "f") digit = int'(character) - int'("a") + 10;
            else if (character >= "A" && character <= "F") digit = int'(character) - int'("A") + 10;
            else digit = radix;
            if (digit >= radix) $fatal(1, "N2M_SIM_RAM_MIF_DIGIT file=%s token=%s", INIT_FILE, token);
            value = value * longint'(radix) + longint'(digit);
        end
        return value;
    endfunction

    function automatic integer header_value(input string setting, input string line);
        integer equals, index;
        if (line.substr(0, setting.len() - 1) != setting) return -1;
        equals = -1;
        for (index = 0; index < line.len(); index = index + 1) if (line[index] == "=" && equals < 0) equals = index;
        if (equals < 0 || line[line.len() - 1] != ";") $fatal(1, "N2M_SIM_RAM_MIF_HEADER file=%s line=%s", INIT_FILE, line);
        return int'(parse_number(trimmed(line.substr(equals + 1, line.len() - 2)), 10));
    endfunction

    task automatic load_mif(input string name);
        integer fd, address_radix, data_radix, radix, colon, dots, count;
        integer first, last, index;
        logic [DATA_BITS-1:0] value;
        string line, left, right;
        bit content;
        fd = $fopen(name, "r");
        if (fd == 0) $fatal(1, "N2M_SIM_RAM_INIT_FILE_MISSING file=%s", name);
        address_radix = 16;
        data_radix = 16;
        content = 0;
        count = 0;
        while ($fgets(line, fd) != 0) begin
            line = trimmed(line);
            if (line.len() == 0 || line.substr(0, 1) == "--") continue;
            if (!content) begin
                if (line == "CONTENT BEGIN") content = 1;
                else if (header_value("DEPTH", line) >= 0 && header_value("DEPTH", line) != DEPTH)
                    $fatal(1, "N2M_SIM_RAM_MIF_DEPTH file=%s expected=%0d actual=%0d", name, DEPTH, header_value("DEPTH", line));
                else if (header_value("WIDTH", line) >= 0 && header_value("WIDTH", line) != DATA_BITS)
                    $fatal(1, "N2M_SIM_RAM_MIF_WIDTH file=%s expected=%0d actual=%0d", name, DATA_BITS, header_value("WIDTH", line));
                else if (radix_of("ADDRESS_RADIX", line) != 0) address_radix = radix_of("ADDRESS_RADIX", line);
                else if (radix_of("DATA_RADIX", line) != 0) data_radix = radix_of("DATA_RADIX", line);
                continue;
            end
            if (line == "END;") break;
            colon = -1;
            for (dots = 0; dots < line.len(); dots = dots + 1) if (line[dots] == ":" && colon < 0) colon = dots;
            if (colon < 1 || line[line.len() - 1] != ";")
                $fatal(1, "N2M_SIM_RAM_MIF_ROW file=%s line=%s", name, line);
            left = trimmed(line.substr(0, colon - 1));
            right = trimmed(line.substr(colon + 1, line.len() - 2));
            if (left[0] == "[") begin
                dots = -1;
                for (colon = 0; colon < left.len(); colon = colon + 1) if (left[colon] == "." && dots < 0) dots = colon;
                if (dots < 2 || left[left.len() - 1] != "]" || left[dots + 1] != ".")
                    $fatal(1, "N2M_SIM_RAM_MIF_RANGE file=%s line=%s", name, line);
                first = int'(parse_number(trimmed(left.substr(1, dots - 1)), address_radix));
                last = int'(parse_number(trimmed(left.substr(dots + 2, left.len() - 2)), address_radix));
            end else begin
                first = int'(parse_number(left, address_radix));
                last = first;
            end
            radix = data_radix;
            value = DATA_BITS'(parse_number(right, radix));
            if (first > last || last >= DEPTH)
                $fatal(1, "N2M_SIM_RAM_MIF_ADDRESS file=%s line=%s depth=%0d", name, line, DEPTH);
            for (index = first; index <= last; index = index + 1) begin
                words[index] = value;
                count = count + 1;
            end
        end
        $fclose(fd);
        if (!content) $fatal(1, "N2M_SIM_RAM_MIF_CONTENT file=%s", name);
        $display("N2M_SIM_RAM preload file=%s words=%0d depth=%0d width=%0d", name, count, DEPTH, DATA_BITS);
    endtask

    `N2M_ASSERT_NO_RST(SIM_RAM_CONFIGURATION, clock0,
        DEPTH > 1 && DEPTH <= (2 ** ADDRESS_BITS) && LANES > 0 && DATA_BITS <= 32 &&
        DATA_BITS % LANES == 0 && (LANES == 1 || LANE_BITS == 8))
endmodule
