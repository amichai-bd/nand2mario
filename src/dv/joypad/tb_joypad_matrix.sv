`timescale 1ns/1ps
`default_nettype none

module tb_joypad_matrix;
    logic [7:0] buttons;
    logic [1:0] select_bits;
    logic [7:0] read_data;
    logic selected_active;
    logic [7:0] expected;
    integer mask, selection, cases, trace;
    bit corrupt;
    n2m_joypad_matrix dut (.*);
    initial begin
        buttons=0; select_bits=3; cases=0;
        corrupt=$test$plusargs("corrupt");
        trace=$fopen("matrix.csv","w");
        if(!trace) $fatal(1,"JOY_MATRIX_TRACE");
        $fdisplay(trace,"case,buttons,select,expected,actual,active");
        $dumpfile("waves/joypad-matrix.vcd");
        $dumpvars(0,buttons,select_bits,read_data,selected_active);
        for(mask=0;mask<256;mask=mask+1) begin
            for(selection=0;selection<4;selection=selection+1) begin
                buttons=8'(mask); select_bits=2'(selection);
                // Literal host bit positions, independent of product constants.
                case(selection)
                    0: expected=8'hc0 | (8'h0f & ~8'((mask & 15) | (mask >> 4)));
                    1: expected=8'hd0 | (8'h0f & ~8'(mask >> 4));
                    2: expected=8'he0 | (8'h0f & ~8'(mask));
                    3: expected=8'hff;
                    default: expected=0;
                endcase
                if(corrupt && cases==6) force dut.read_data=8'hed;
                #1;
                $fdisplay(trace,"%0d,%02h,%0d,%02h,%02h,%0d",cases,buttons,selection,expected,read_data,selected_active);
                if(read_data!==expected || selected_active!==(expected[3:0]!=4'hf))
                    $fatal(1,"JOY_MATRIX case=%0d expected=%02h actual=%02h",cases,expected,read_data);
                cases=cases+1;
            end
        end
        if(cases!=1024) $fatal(1,"JOY_MATRIX_COUNT");
        $fclose(trace); $display("PASS JOYP matrix cases=1024"); $finish;
    end
    initial begin
        #100000;
        $fatal(1,"JOY_MATRIX_TIMEOUT");
    end
endmodule
