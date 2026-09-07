`timescale 1ns/1ps
`default_nettype none
module tb_oam_corrupt;
    import n2m_oam_pkg::*;
    logic clk_sys, reset;
    logic [4:0] row_index;
    oam_effect_t kind;
    logic [63:0] current_row, previous_row, older_row;
    logic [63:0] current_result, previous_result, older_result;
    logic [2:0] write_mask;
    logic invalid_row;
    logic [15:0] reference_rows [3][4];
    logic [15:0] input_rows [3][4];
    logic [63:0] expected_rows [3];
    logic [63:0] changed_result;
    logic [2:0] expected_mask;
    logic a, b, c, d;
    integer row, operation, position, combination, r, w, bit_index;
    integer count, trace;
    bit output_fault, mask_fault;
    n2m_oam_corrupt dut (.*);

    // Independent sequential row oracle. Count set bits for write-majority;
    // retain both stages of read+IDU instead of reducing to equal rows.
    task automatic reference_transform;
        for (r=0; r<3; r=r+1)
            for (w=0; w<4; w=w+1) reference_rows[r][w]=input_rows[r][w];
        expected_mask=0;
        if (row>0 && row<20 && operation!=0) begin
            if (operation==3 && row>=4 && row<=18) begin
                for (bit_index=0; bit_index<16; bit_index=bit_index+1) begin
                    a=reference_rows[0][0][bit_index];
                    b=reference_rows[1][0][bit_index];
                    c=reference_rows[2][0][bit_index];
                    d=reference_rows[1][2][bit_index];
                    reference_rows[1][0][bit_index]=(b && (a || c || d)) || (a && c && d);
                end
                for (w=0; w<4; w=w+1) begin
                    reference_rows[0][w]=reference_rows[1][w];
                    reference_rows[2][w]=reference_rows[1][w];
                end
                expected_mask=7;
            end else expected_mask=1;
            for (bit_index=0; bit_index<16; bit_index=bit_index+1) begin
                a=reference_rows[2][0][bit_index];
                b=reference_rows[1][0][bit_index];
                c=reference_rows[1][2][bit_index];
                reference_rows[2][0][bit_index]=operation==2
                    ? (int'(a)+int'(b)+int'(c)>=2) : b || (a && c);
            end
            for (w=1; w<4; w=w+1) reference_rows[2][w]=reference_rows[1][w];
        end
        for (r=0; r<3; r=r+1)
            for (w=0; w<4; w=w+1) expected_rows[r][16*w +: 16]=reference_rows[r][w];
    endtask

    task automatic check_case;
        row_index=5'(row);
        kind=oam_effect_t'(operation);
        for (r=0; r<3; r=r+1)
            for (w=0; w<4; w=w+1)
                input_rows[r][w]=16'(16'h1234*(r+1)+16'h2311*w+16'h0137*row);
        input_rows[0][0][position]=1'(combination);
        input_rows[1][0][position]=1'(combination>>1);
        input_rows[2][0][position]=1'(combination>>2);
        input_rows[1][2][position]=1'(combination>>3);
        for (w=0; w<4; w=w+1) begin
            older_row[16*w +: 16]=input_rows[0][w];
            previous_row[16*w +: 16]=input_rows[1][w];
            current_row[16*w +: 16]=input_rows[2][w];
        end
        reference_transform();
        #2;
        if (output_fault && row==4 && operation==3 && position==0 && combination==0) begin
            changed_result=current_result ^ 64'h0000000000010000;
            force dut.current_result=changed_result;
        end
        if (mask_fault && row==20 && operation==0) force dut.write_mask=3'b001;
        #2;
        clk_sys=1;
        #2;
        $fdisplay(trace,"%0d,%0d,%0d,%0d,%016h,%016h,%016h,%016h,%016h,%016h,%01h,%016h,%016h,%016h,%01h,%0d",
            row,operation,position,combination,older_row,previous_row,current_row,
            expected_rows[0],expected_rows[1],expected_rows[2],expected_mask,
            older_result,previous_result,current_result,write_mask,invalid_row);
        if ({older_result,previous_result,current_result,write_mask,invalid_row} !==
            {expected_rows[0],expected_rows[1],expected_rows[2],expected_mask,(row>19)})
            $fatal(1,"OAM_CORRUPTION_RESULT row=%0d kind=%0d bit=%0d pattern=%0d expected=%016h/%016h/%016h/%h actual=%016h/%016h/%016h/%h",
                row,operation,position,combination,expected_rows[0],expected_rows[1],expected_rows[2],expected_mask,
                older_result,previous_result,current_result,write_mask);
        clk_sys=0;
        count=count+1;
    endtask

    initial begin
        clk_sys=0; reset=1; row_index=0; kind=OAM_NONE;
        current_row=0; previous_row=0; older_row=0; count=0;
        output_fault=$test$plusargs("output-fault");
        mask_fault=$test$plusargs("mask-fault");
        trace=$fopen("corruption.csv","w");
        if (!trace) $fatal(1,"OAM_CORRUPTION_TRACE");
        $dumpfile("waves/oam-corrupt.vcd");
        $dumpvars(0,clk_sys,reset,row_index,kind,current_row,previous_row,older_row,
            current_result,previous_result,older_result,write_mask,invalid_row);
        #2; reset=0;
        for (row=0; row<20; row=row+1)
            for (operation=0; operation<4; operation=operation+1)
                for (position=0; position<16; position=position+1)
                    for (combination=0; combination<16; combination=combination+1) check_case();
        position=0; combination=0;
        for (row=20; row<32; row=row+1)
            for (operation=0; operation<4; operation=operation+1) check_case();
        $fclose(trace);
        if (count!=20528) $fatal(1,"OAM_CORRUPTION_COUNT");
        $display("PASS OAM corruption truth=20480 invalid=48");
        $finish;
    end
    initial begin
        #1000000;
        $fatal(1,"OAM_CORRUPTION_TIMEOUT");
    end
endmodule
