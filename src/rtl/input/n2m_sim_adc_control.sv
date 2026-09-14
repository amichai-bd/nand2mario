`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// Simulation double for the installed altera_modular_adc_control core selected
// by n2m_adc_backend under the predefined VERILATOR macro. Quartus never sees
// it. Contract: wiki/src/fpga-controls.md.
//
// The double replays the builder's two-column stimulus files, one per channel
// (<FILE_PREFIX><channel><FILE_SUFFIX>, rows of "time voltage"), through the
// vendor command/response handshake in clk. A command is accepted only while
// the PLL is locked and no conversion is outstanding. The response arrives
// CONVERSION_ADC_CYCLES rising edges of clk_in_pll_c0 later, tagged with the
// accepted channel, carrying the next row's voltage as a truncated twelve-bit
// code against the encoded reference. Rows repeat cyclically per channel. Lock
// loss or reset abandons the outstanding conversion without a response.
module n2m_sim_adc_control #(
    parameter integer REFERENCE_VOLTAGE_SIM = 49648,
    parameter string FILE_PREFIX = "adc_ch",
    parameter string FILE_SUFFIX = ".txt",
    parameter integer CONVERSION_ADC_CYCLES = 80,
    parameter integer MAX_ROWS = 256
) (
    input var logic clk,
    input var logic rst_n,
    input var logic clk_in_pll_c0,
    input var logic clk_in_pll_locked,
    input var logic cmd_valid,
    input var logic [4:0] cmd_channel,
    input var logic cmd_sop,
    input var logic cmd_eop,
    input var logic sync_ready,
    output logic cmd_ready,
    output logic rsp_valid,
    output logic [4:0] rsp_channel,
    output logic [11:0] rsp_data,
    output logic rsp_sop,
    output logic rsp_eop,
    output logic sync_valid
);
    localparam integer CHANNELS = 17;
    // The installed generator encodes the reference as (Vref / 3.3) * 65536.
    localparam real REFERENCE_VOLTS = REFERENCE_VOLTAGE_SIM * 3.3 / 65536.0;
    logic reset;
    logic accept;
    logic adc_edge;
    logic done;
    logic busy;
    logic busy_next;
    logic c0_sample;
    logic [4:0] channel_q;
    logic [31:0] adc_count;
    logic [31:0] adc_count_next;
    logic unused_ok;
    real voltage [0:CHANNELS-1][0:MAX_ROWS-1];
    integer rows [0:CHANNELS-1];
    integer next_row [0:CHANNELS-1];

    assign reset = !rst_n;
    assign unused_ok = cmd_sop && cmd_eop && sync_ready;
    assign cmd_ready = rst_n && clk_in_pll_locked && !busy;
    assign accept = cmd_valid && cmd_ready;
    assign adc_edge = clk_in_pll_c0 && !c0_sample;
    assign done = busy && clk_in_pll_locked && adc_edge && adc_count == 32'(CONVERSION_ADC_CYCLES - 1);
    assign busy_next = accept || (busy && clk_in_pll_locked && !done);
    assign adc_count_next = accept ? 32'd0 : (busy && adc_edge ? adc_count + 32'd1 : adc_count);
    assign rsp_sop = rsp_valid;
    assign rsp_eop = rsp_valid;
    assign sync_valid = 1'b0;

    `DFF_RST(c0_sample, clk_in_pll_c0, clk, reset)
    `DFF_RST(busy, busy_next, clk, reset)
    `DFF_RST_EN(channel_q, cmd_channel, clk, accept, reset, 5'd0)
    `DFF_RST(adc_count, adc_count_next, clk, reset)
    `DFF_RST(rsp_valid, done, clk, reset)
    `DFF_RST_EN(rsp_channel, channel_q, clk, done, reset, 5'd0)
    `DFF_RST_EN(rsp_data, code_of(channel_q), clk, done, reset, 12'd0)

    // Integer truncation of (Vin / Vref) * 4096, clamped to the twelve-bit range.
    function automatic logic [11:0] code_of(input logic [4:0] channel);
        real scaled;
        integer code;
        scaled = voltage[channel][next_row[channel]] / REFERENCE_VOLTS * 4096.0;
        code = $rtoi(scaled);
        if (code < 0) code = 0;
        if (code > 4095) code = 4095;
        return 12'(code);
    endfunction

    always_ff @(posedge clk) begin
        if (done) next_row[channel_q] <= (next_row[channel_q] + 1) % rows[channel_q];
    end

    // Stimulus files are read 1 ps after time zero, so a testbench may generate
    // them at time zero; the vendor also reads its files before the first edge.
    integer channel, fd, count, row;
    real time_column, value;
    string name;
    initial begin
        for (channel = 0; channel < CHANNELS; channel = channel + 1) begin
            rows[channel] = 0;
            next_row[channel] = 0;
        end
        #1ps;
        for (channel = 0; channel < CHANNELS; channel = channel + 1) begin
            name = $sformatf("%s%0d%s", FILE_PREFIX, channel, FILE_SUFFIX);
            fd = $fopen(name, "r");
            if (fd == 0) $fatal(1, "N2M_SIM_ADC_STIMULUS_MISSING file=%s", name);
            row = 0;
            count = $fscanf(fd, "%f %f", time_column, value);
            while (count == 2 && row < MAX_ROWS) begin
                voltage[channel][row] = value;
                row = row + 1;
                count = $fscanf(fd, "%f %f", time_column, value);
            end
            $fclose(fd);
            if (row == 0) $fatal(1, "N2M_SIM_ADC_STIMULUS_EMPTY file=%s", name);
            rows[channel] = row;
        end
        $display("N2M_SIM_ADC stimulus channels=%0d reference_volts=%f conversion_adc_cycles=%0d",
            CHANNELS, REFERENCE_VOLTS, CONVERSION_ADC_CYCLES);
    end

    `N2M_ASSERT(SIM_ADC_CHANNEL_RANGE, clk, reset, !cmd_valid || int'(cmd_channel) < CHANNELS)
    `N2M_ASSERT_NO_RST(SIM_ADC_CONFIGURATION, clk,
        REFERENCE_VOLTAGE_SIM > 0 && CONVERSION_ADC_CYCLES > 0 && MAX_ROWS > 0)
endmodule
