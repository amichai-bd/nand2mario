`timescale 1ns/1ps
`default_nettype none
module tb_memory_decode;
    logic [15:0] address;
    n2m_memory_pkg::memory_destination_t destination, expected_destination;
    n2m_memory_pkg::memory_store_t store, expected_store;
    logic [14:0] offset, expected_offset;
    integer index;
    bit alias_fault;
    n2m_memory_decode dut (.*);

    // Literal DMG address oracle is independent of generated constants and
    // DUT range comparisons. No read-value or peripheral-service claim here.
    task automatic expect_address(input integer value);
        expected_destination = n2m_memory_pkg::MEMORY_UNUSED_IO;
        expected_store = n2m_memory_pkg::STORE_ROM;
        expected_offset = 0;
        case (value / 8192)
            0, 1, 2, 3: begin
                expected_destination = n2m_memory_pkg::MEMORY_DIRECT;
                expected_offset = 15'(value);
            end
            4: begin
                expected_destination = n2m_memory_pkg::MEMORY_VRAM;
                expected_store = n2m_memory_pkg::STORE_VRAM;
                expected_offset = 15'(value - 32768);
            end
            5: expected_destination = n2m_memory_pkg::MEMORY_ABSENT_CART;
            6, 7: begin
                if (value < 'hFE00) begin
                    expected_destination = n2m_memory_pkg::MEMORY_DIRECT;
                    expected_store = n2m_memory_pkg::STORE_WRAM;
                    expected_offset = 15'(value % 8192);
                end else if (value < 'hFEA0) begin
                    expected_destination = n2m_memory_pkg::MEMORY_OAM;
                    expected_store = n2m_memory_pkg::STORE_OAM;
                    expected_offset = 15'(value - 'hFE00);
                end else if (value < 'hFF00) expected_destination = n2m_memory_pkg::MEMORY_UNUSABLE;
                else if (value >= 'hFF80 && value < 'hFFFF) begin
                    expected_destination = n2m_memory_pkg::MEMORY_DIRECT;
                    expected_store = n2m_memory_pkg::STORE_HRAM;
                    expected_offset = 15'(value - 'hFF80);
                end else if (value >= 'hFF30 && value <= 'hFF3F) begin
                    expected_destination = n2m_memory_pkg::MEMORY_WAVE;
                    expected_store = n2m_memory_pkg::STORE_WAVE;
                    expected_offset = 15'(value - 'hFF30);
                end else begin
                    case (value)
                        'hFF00: expected_destination = n2m_memory_pkg::MEMORY_JOYP;
                        'hFF01, 'hFF02: expected_destination = n2m_memory_pkg::MEMORY_SERIAL;
                        'hFF04, 'hFF05, 'hFF06, 'hFF07: expected_destination = n2m_memory_pkg::MEMORY_TIMER;
                        'hFF0F, 'hFFFF: expected_destination = n2m_memory_pkg::MEMORY_IRQ;
                        'hFF10, 'hFF11, 'hFF12, 'hFF13, 'hFF14,
                        'hFF16, 'hFF17, 'hFF18, 'hFF19,
                        'hFF1A, 'hFF1B, 'hFF1C, 'hFF1D, 'hFF1E,
                        'hFF20, 'hFF21, 'hFF22, 'hFF23, 'hFF24, 'hFF25, 'hFF26:
                            expected_destination = n2m_memory_pkg::MEMORY_APU;
                        'hFF40, 'hFF41, 'hFF42, 'hFF43, 'hFF44, 'hFF45,
                        'hFF47, 'hFF48, 'hFF49, 'hFF4A, 'hFF4B: expected_destination = n2m_memory_pkg::MEMORY_PPU;
                        'hFF46: expected_destination = n2m_memory_pkg::MEMORY_DMA;
                        'hFF50: expected_destination = n2m_memory_pkg::MEMORY_BOOT;
                        default: begin end
                    endcase
                end
            end
            default: $fatal(1, "MEMORY_DECODE_ORACLE_RANGE");
        endcase
    endtask

    initial begin
        $dumpfile("waves.vcd");
        $dumpvars(0, address, destination, store, offset,
                  expected_destination, expected_store, expected_offset);
        alias_fault = $test$plusargs("alias_fault");
        address = 0;
        for (index = 0; index < 65536; index = index + 1) begin
            address = 16'(index);
            expect_address(index);
            #1;
            if (alias_fault && index == 'hE123) force dut.offset = 15'h1234;
            #1;
            if (destination !== expected_destination || store !== expected_store || offset !== expected_offset)
                $fatal(1, "MEMORY_DECODE_MISMATCH address=%04h destination=%0d store=%0d offset=%04h", address, destination, store, offset);
        end
        $display("PASS memory decode addresses=65536 echo=7680");
        $finish;
    end
    initial begin
        #200000;
        $fatal(1, "MEMORY_DECODE_WATCHDOG");
    end
endmodule
