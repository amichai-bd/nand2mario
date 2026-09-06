`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// Bounded transaction operands/results only; authoritative bytes stay in RAM.
module n2m_dma_service (
    input var logic clk_sys,
    input var logic reset,
    input var logic init_done,
    input var logic t4,
    input var logic scan_active,
    input var logic [4:0] scan_row,
    input var n2m_oam_pkg::oam_effect_t effect_kind,
    input var logic dma_write,
    input var logic [7:0] dma_offset,
    input var logic [7:0] dma_byte,
    input var logic dma_source_request,
    input var logic [15:0] dma_source_address,
    output logic [7:0] dma_source_data,
    output logic dma_source_valid,
    output logic [15:0] dma_held_pair,
    output logic dma_pair_pending,
    output logic [6:0] dma_pending_pair,
    input var logic cpu_read,
    input var logic cpu_write,
    input var n2m_memory_pkg::memory_store_t cpu_store,
    input var logic [14:0] cpu_offset,
    input var logic [15:0] cpu_address,
    input var logic [7:0] cpu_wdata,
    output logic [7:0] cpu_rdata,
    output logic cpu_valid,
    output logic access_read,
    output logic access_write,
    output n2m_memory_pkg::memory_store_t access_store,
    output logic [14:0] access_address,
    output logic [7:0] access_wdata,
    input var logic [7:0] access_rdata,
    input var logic access_valid,
    output logic fault
);
    import n2m_memory_pkg::*;
    import n2m_oam_pkg::*;
    logic [5:0] slot_q, slot_next;
    logic [4:0] job_row_q, operand_row_q;
    logic job_prefetch_q, operand_valid_q;
    logic [63:0] previous_q, previous_next;
    logic [15:0] current_q, current_next, older_q, older_next;
    logic [63:0] overlay_previous, overlay_current, overlay_older;
    logic [63:0] result_current, result_previous, result_older;
    logic [2:0][63:0] rows_q;
    logic [2:0] mask_q, result_mask;
    logic invalid_row, uncovered_q;
    logic [7:0] dma_offset_q, dma_byte_q;
    logic [7:0] other_q, other_offset_q;
    logic other_valid_q;
    logic [7:0] source_q;
    logic [15:0] source_address_q;
    logic source_valid_q;
    logic [7:0] cpu_data_q;
    logic [15:0] cpu_address_q;
    logic cpu_valid_q;
    logic [15:0] held_q, held_next;
    logic pair_pending_q, pair_pending_next, pair_committed;
    logic [2:0] grant_kind, response_kind_q;
    logic [3:0] grant_index, response_index_q;
    logic [15:0] grant_address, response_address_q;
    logic [4:0] response_row_q;
    logic missing_operands, missing_other, missing_raw, service_fault, accept;
    memory_destination_t source_destination;
    memory_store_t source_store;
    logic [14:0] source_offset;
    integer word_byte, selected_row;
    localparam logic [2:0] READ_NONE=0, READ_OPERAND=1, READ_SOURCE=2,
        READ_OTHER=3, READ_CPU=4;
    n2m_memory_decode source_decode (.address(dma_source_address),
        .destination(source_destination), .store(source_store), .offset(source_offset));
    assign accept = t4 && init_done && !reset && !fault;
    assign missing_operands = accept && scan_active && scan_row != 0 &&
        effect_kind != OAM_NONE && (!operand_valid_q || operand_row_q != scan_row);
    assign missing_other = accept && dma_write &&
        (!other_valid_q || other_offset_q != dma_offset);
    assign missing_raw = response_kind_q != READ_NONE && !access_valid;
    assign service_fault = missing_operands || missing_other || missing_raw ||
        (accept && slot_q != 0 && slot_q < 6'd43);
    `DFF_ARST_VAL(fault, fault || service_fault, clk_sys, reset, 1'b0)
    always_comb begin
        overlay_previous=previous_q;
        overlay_current={48'd0,current_q};
        overlay_older={48'd0,older_q};
        if (dma_write) begin
            if (dma_offset[7:3] == scan_row)
                overlay_current[8*int'(dma_offset[2:0]) +: 8]=dma_byte;
            if (scan_row>0 && dma_offset[7:3] == scan_row-5'd1)
                overlay_previous[8*int'(dma_offset[2:0]) +: 8]=dma_byte;
            if (scan_row>1 && dma_offset[7:3] == scan_row-5'd2)
                overlay_older[8*int'(dma_offset[2:0]) +: 8]=dma_byte;
        end
    end
    n2m_oam_corrupt transform (.clk_sys(clk_sys), .reset(reset),
        .row_index(scan_row), .kind(scan_active ? effect_kind : OAM_NONE),
        .current_row(overlay_current), .previous_row(overlay_previous), .older_row(overlay_older),
        .current_result(result_current), .previous_result(result_previous),
        .older_result(result_older), .write_mask(result_mask), .invalid_row(invalid_row));
    always_comb begin
        held_next=held_q;
        if (dma_write) begin
            held_next=dma_offset[0] ? {dma_byte,other_q} : {other_q,dma_byte};
            if (result_mask[0] && dma_offset[7:3]==scan_row)
                held_next=result_current[16*int'(dma_offset[2:1]) +: 16];
            if (result_mask[1] && dma_offset[7:3]==scan_row-5'd1)
                held_next=result_previous[16*int'(dma_offset[2:1]) +: 16];
            if (result_mask[2] && dma_offset[7:3]==scan_row-5'd2)
                held_next=result_older[16*int'(dma_offset[2:1]) +: 16];
        end
    end
    `DFF_RST_EN(held_q, held_next, clk_sys, accept && !service_fault, reset, 16'd0)
    assign dma_held_pair=held_q;
    // Keep the accepted pair available until both physical bytes are current.
    // A covered corruption writes low then high; an uncovered DMA writes one byte.
    assign pair_committed=access_write && access_store==STORE_OAM &&
        access_address[7:1]==dma_offset_q[7:1] &&
        (uncovered_q || access_address[0]);
    always_comb begin
        pair_pending_next=pair_pending_q;
        if (pair_committed) pair_pending_next=0;
        if (accept && !service_fault && dma_write) pair_pending_next=1;
        if (!init_done || fault || service_fault) pair_pending_next=0;
    end
    `DFF_ARST_VAL(pair_pending_q, pair_pending_next, clk_sys, reset, 1'b0)
    assign dma_pair_pending=pair_pending_q && init_done && !reset && !fault;
    assign dma_pending_pair=dma_offset_q[7:1];
    always_comb begin
        slot_next=slot_q;
        if (slot_q != 0) slot_next=slot_q==6'd46 ? 6'd0 : slot_q+6'd1;
        if (accept && !service_fault) slot_next=6'd1;
    end
    `DFF_ARST_VAL(slot_q, slot_next, clk_sys, reset, 6'd0)
    `DFF_RST_EN(job_row_q, scan_row, clk_sys, accept, reset, 5'd0)
    `DFF_RST_EN(job_prefetch_q, scan_active && scan_row<19, clk_sys, accept, reset, 1'b0)
    `DFF_RST_EN(rows_q, {result_older,result_previous,result_current}, clk_sys,
        accept && !service_fault, reset, 192'd0)
    `DFF_RST_EN(mask_q, result_mask, clk_sys, accept && !service_fault, reset, 3'd0)
    `DFF_RST_EN(dma_offset_q, dma_offset, clk_sys, accept, reset, 8'd0)
    `DFF_RST_EN(dma_byte_q, dma_byte, clk_sys, accept, reset, 8'd0)
    `DFF_RST_EN(uncovered_q, dma_write &&
        !(result_mask[0] && dma_offset[7:3]==scan_row) &&
        !(result_mask[1] && dma_offset[7:3]==scan_row-5'd1) &&
        !(result_mask[2] && dma_offset[7:3]==scan_row-5'd2),
        clk_sys, accept && !service_fault, reset, 1'b0)

    always_comb begin
        access_read=0; access_write=0; access_store=STORE_OAM;
        access_address=0; access_wdata=0;
        grant_kind=READ_NONE; grant_index=0; grant_address=0;
        word_byte=0; selected_row=0;
        if (slot_q>=1 && slot_q<=24) begin
            selected_row=(int'(slot_q)-1)/8;
            word_byte=(int'(slot_q)-1)%8;
            if (selected_row==0) begin
                case (word_byte)
                    0: word_byte=4;
                    1: word_byte=5;
                    2: word_byte=0;
                    3: word_byte=1;
                    4: word_byte=2;
                    5: word_byte=3;
                    default: begin end
                endcase
            end
            access_write=mask_q[selected_row];
            access_address=15'(8*(int'(job_row_q)-selected_row)+word_byte);
            access_wdata=rows_q[selected_row][8*word_byte +: 8];
        end else if (slot_q==25) begin
            access_write=uncovered_q;
            access_address={7'd0,dma_offset_q}; access_wdata=dma_byte_q;
        end else if (slot_q>=26 && slot_q<=37 && job_prefetch_q) begin
            access_read=1; grant_kind=READ_OPERAND; grant_index=4'(slot_q-26);
            if(slot_q<=33) access_address=15'(8*int'(job_row_q)+int'(slot_q)-26);
            else if(slot_q<=35) access_address=15'(8*(int'(job_row_q)-1)+int'(slot_q)-34);
            else access_address=15'(8*(int'(job_row_q)+1)+int'(slot_q)-36);
            // Row1 has no older operand; avoid an address below the OAM store.
            if (job_row_q==0 && slot_q>=34 && slot_q<=35) access_read=0;
        end else if(slot_q==39 && dma_source_request) begin
            access_read=source_destination!=MEMORY_ABSENT_CART;
            access_store=source_store; access_address=source_offset;
            grant_kind=READ_SOURCE; grant_address=dma_source_address;
        end else if(slot_q==41 && dma_source_request) begin
            access_read=1; access_address={7'd0,dma_source_address[7:0]^8'd1};
            grant_kind=READ_OTHER; grant_address={8'd0,dma_source_address[7:0]};
        end else if(slot_q==0 || slot_q>=43) begin
            access_read=cpu_read; access_store=cpu_store; access_address=cpu_offset;
            grant_kind=READ_CPU; grant_address=cpu_address;
        end
        if(cpu_write) begin
            access_read=0; access_write=1; access_store=cpu_store;
            access_address=cpu_offset; access_wdata=cpu_wdata; grant_kind=READ_NONE;
        end
        if(reset || !init_done || fault || service_fault) begin
            access_read=0; access_write=0; grant_kind=READ_NONE;
        end
    end
    `DFF_ARST_VAL(response_kind_q, access_read ? grant_kind : READ_NONE, clk_sys, reset, READ_NONE)
    `DFF_EN(response_index_q, grant_index, clk_sys, access_read)
    `DFF_EN(response_address_q, grant_address, clk_sys, access_read)
    `DFF_EN(response_row_q, job_row_q+5'd1, clk_sys, access_read && grant_kind==READ_OPERAND)
    always_comb begin
        previous_next=previous_q; older_next=older_q; current_next=current_q;
        if(accept) older_next=0;
        if(access_valid && response_kind_q==READ_OPERAND) begin
            if(response_index_q<8) previous_next[8*int'(response_index_q) +: 8]=access_rdata;
            else if(response_index_q<10) older_next[8*(int'(response_index_q)-8) +: 8]=access_rdata;
            else current_next[8*(int'(response_index_q)-10) +: 8]=access_rdata;
        end
    end
    `DFF_ARST_VAL(previous_q, previous_next, clk_sys, reset, 64'd0)
    `DFF_ARST_VAL(older_q, older_next, clk_sys, reset, 16'd0)
    `DFF_ARST_VAL(current_q, current_next, clk_sys, reset, 16'd0)
    `DFF_RST_EN(operand_row_q, response_row_q, clk_sys,
        access_valid && response_kind_q==READ_OPERAND && response_index_q==11, reset, 5'd0)
    `DFF_ARST_VAL(operand_valid_q, accept ? 1'b0 : operand_valid_q ||
        (access_valid && response_kind_q==READ_OPERAND && response_index_q==11), clk_sys, reset, 1'b0)
    `DFF_RST_EN(source_q, source_destination==MEMORY_ABSENT_CART ? 8'hff : access_rdata,
        clk_sys, (slot_q==39 && dma_source_request && source_destination==MEMORY_ABSENT_CART) ||
        (access_valid && response_kind_q==READ_SOURCE), reset, 8'd0)
    `DFF_RST_EN(source_address_q, dma_source_address, clk_sys,
        slot_q==39 && dma_source_request, reset, 16'd0)
    `DFF_ARST_VAL(source_valid_q, accept ? 1'b0 : source_valid_q ||
        (slot_q==39 && dma_source_request && source_destination==MEMORY_ABSENT_CART) ||
        (access_valid && response_kind_q==READ_SOURCE), clk_sys, reset, 1'b0)
    assign dma_source_data=source_q;
    assign dma_source_valid=!reset && !fault && source_valid_q && source_address_q==dma_source_address;
    `DFF_RST_EN(other_q, access_rdata, clk_sys, access_valid && response_kind_q==READ_OTHER, reset, 8'd0)
    `DFF_RST_EN(other_offset_q, response_address_q[7:0], clk_sys,
        access_valid && response_kind_q==READ_OTHER, reset, 8'd0)
    `DFF_ARST_VAL(other_valid_q, accept ? 1'b0 : other_valid_q ||
        (access_valid && response_kind_q==READ_OTHER), clk_sys, reset, 1'b0)
    `DFF_RST_EN(cpu_data_q, access_rdata, clk_sys, access_valid && response_kind_q==READ_CPU, reset, 8'd0)
    `DFF_RST_EN(cpu_address_q, response_address_q, clk_sys,
        access_valid && response_kind_q==READ_CPU, reset, 16'd0)
    `DFF_ARST_VAL(cpu_valid_q, accept ? 1'b0 : cpu_valid_q ||
        (access_valid && response_kind_q==READ_CPU), clk_sys, reset, 1'b0)
    assign cpu_rdata=cpu_data_q;
    assign cpu_valid=!reset && !fault && cpu_valid_q && cpu_address_q==cpu_address;
    `N2M_ASSERT(DMA_RAW_SERVICE, clk_sys, reset, !missing_raw)
    `N2M_ASSERT(DMA_OPERAND_SERVICE, clk_sys, reset, !missing_operands)
    `N2M_ASSERT(DMA_PAIR_SERVICE, clk_sys, reset, !missing_other)
    `N2M_ASSERT(DMA_JOB_DEADLINE, clk_sys, reset, !(accept && slot_q!=0 && slot_q<43))
    `N2M_ASSERT(DMA_CPU_WRITE_SLOT, clk_sys, reset, !cpu_write || t4)
endmodule
