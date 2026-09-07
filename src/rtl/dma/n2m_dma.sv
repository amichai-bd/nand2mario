`timescale 1ns/1ps
`default_nettype none
`include "src/rtl/common/macros.svh"

// CPU policy and prepared reads surround the existing memory CPU dispatcher.
// Peripheral I/O remains with its separate owners, including pre-T3 IE/IF.
module n2m_dma (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic core_reset,
    input var logic init_done,
    input var logic gb_tick,
    input var logic [1:0] cpu_phase,
    input var logic cpu_halted,
    input var logic cpu_stopped,
    input var logic request_valid,
    input var n2m_cpu_pkg::cpu_bus_plan_t bus_plan,
    input var logic bus_commit,
    input var n2m_cpu_pkg::cpu_address_effect_t address_effect,
    input var logic address_effect_resolved,
    input var logic address_effect_sample,
    output logic [7:0] read_data,
    output logic response_valid,
    output logic fault,
    output logic peripheral_prepare,
    output logic peripheral_commit,
    output n2m_memory_pkg::memory_destination_t peripheral_destination,
    output logic [15:0] peripheral_address,
    output logic peripheral_write,
    output logic [7:0] peripheral_wdata,
    input var logic [7:0] peripheral_rdata,
    input var logic peripheral_valid,
    input var logic peripheral_available,
    input var logic vram_cpu_allow,
    input var logic oam_cpu_allow,
    input var logic ppu_vram_request,
    input var logic [12:0] ppu_vram_address,
    output logic [7:0] ppu_vram_data,
    output logic ppu_vram_valid,
    input var logic [1:0] ppu_oam_phase,
    input var logic [5:0] ppu_scan_index,
    input var logic [6:0] ppu_oam_pair,
    output logic [15:0] ppu_oam_data,
    output logic ppu_oam_valid,
    output logic dma_active,
    output logic access_read,
    output logic access_write,
    output n2m_memory_pkg::memory_store_t access_store,
    output logic [14:0] access_address,
    output logic [7:0] access_wdata,
    input var logic [7:0] access_rdata,
    input var logic access_valid,
    output logic raw_vram_read,
    output logic [12:0] raw_vram_address,
    input var logic [7:0] raw_vram_data,
    input var logic raw_vram_valid,
    output logic raw_oam_read,
    output logic [6:0] raw_oam_pair,
    input var logic [15:0] raw_oam_data,
    input var logic raw_oam_valid
);
    import n2m_memory_pkg::*;
    import n2m_oam_pkg::*;
    logic reset, t4, engine_fault, service_fault, port_fault, observation_fault;
    logic engine_source_request, engine_source_valid, engine_write;
    logic [15:0] engine_source_address, held_pair;
    logic [7:0] engine_source_data, engine_offset, engine_data, page;
    logic [7:0] transfer_byte;
    logic direct_read, direct_write, owner_prepare, owner_commit, owner_write;
    logic [14:0] direct_offset;
    memory_store_t direct_store;
    memory_destination_t owner_destination;
    logic [15:0] owner_address;
    logic [7:0] direct_wdata, owner_wdata, owner_rdata;
    logic owner_valid, owner_available, local_owner, local_memory, local_allowed;
    logic [7:0] port_rdata, cache_data;
    logic port_valid, cache_valid, service_read, service_write;
    logic main_conflict, vram_conflict, conflict, ram_feedback, redirect_write;
    memory_store_t service_cpu_store;
    logic [14:0] service_cpu_offset;
    logic [7:0] dispatch_rdata;
    logic dispatch_valid;
    oam_effect_t effect_kind;
    logic [4:0] effect_row;
    logic invalid_observation;
    logic oam_dma_response_q, oam_request_q;
    logic pair_pending, forward_pair;
    logic [6:0] pending_pair;
    logic [15:0] held_response_q;
    assign reset=reset_sys || core_reset;
    assign t4=gb_tick && cpu_phase==2'd3;
    assign fault=engine_fault || service_fault || port_fault || observation_fault;
    `DFF_ARST_VAL(observation_fault, observation_fault || invalid_observation, clk_sys, reset, 1'b0)
    n2m_oam_qualify qualify (.clk_sys(clk_sys), .reset(reset),
        .effect_sample(address_effect_sample), .effect_resolved(address_effect_resolved),
        .address_effect(address_effect), .bus_commit(bus_commit), .bus_plan(bus_plan),
        .ppu_oam_phase(ppu_oam_phase), .ppu_scan_index(ppu_scan_index),
        .kind(effect_kind), .row_index(effect_row), .invalid_observation(invalid_observation));
    n2m_dma_engine engine (.clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset),
        .gb_tick(gb_tick && !fault && !invalid_observation), .cpu_phase(cpu_phase),
        .progress_enable(!cpu_halted && !cpu_stopped),
        .ff46_write(owner_commit && owner_destination==MEMORY_DMA && owner_write && !invalid_observation),
        .ff46_wdata(owner_wdata), .source_data(engine_source_data), .source_valid(engine_source_valid),
        .ff46_rdata(page), .source_request(engine_source_request), .source_address(engine_source_address),
        .write_valid(engine_write), .write_offset(engine_offset), .write_data(engine_data),
        .active(dma_active), .fault(engine_fault));
    assign main_conflict=dma_active && engine_source_address[15:13]!=3'b100 &&
        bus_plan.address<16'hfe00 && bus_plan.address[15:13]!=3'b100;
    assign vram_conflict=dma_active && engine_source_address[15:13]==3'b100 &&
        bus_plan.address[15:13]==3'b100;
    assign conflict=main_conflict || vram_conflict;
    assign ram_feedback=main_conflict && engine_source_address>=16'ha000 &&
        bus_commit && bus_plan.write_enable;
    assign transfer_byte=ram_feedback ? engine_data & bus_plan.write_data : engine_data;
    assign redirect_write=vram_conflict && bus_commit && bus_plan.write_enable && vram_cpu_allow;
    assign local_owner=owner_destination==MEMORY_DMA || owner_destination==MEMORY_OAM ||
        owner_destination==MEMORY_VRAM || owner_destination==MEMORY_UNUSABLE;
    assign local_memory=owner_destination==MEMORY_OAM || owner_destination==MEMORY_VRAM;
    assign local_allowed=owner_destination==MEMORY_VRAM ? vram_cpu_allow : (oam_cpu_allow && !dma_active);
    assign peripheral_prepare=owner_prepare && !local_owner;
    assign peripheral_commit=owner_commit && !local_owner && !invalid_observation;
    assign peripheral_destination=owner_destination;
    assign peripheral_address=owner_address;
    assign peripheral_write=owner_write;
    assign peripheral_wdata=owner_wdata;
    assign owner_available=local_owner || peripheral_available;
    always_comb begin
        owner_rdata=peripheral_rdata; owner_valid=peripheral_valid;
        if(owner_destination==MEMORY_DMA) begin owner_rdata=page; owner_valid=1; end
        else if(owner_destination==MEMORY_UNUSABLE) begin
            owner_rdata=oam_cpu_allow && !dma_active ? 8'h00 : 8'hff; owner_valid=1;
        end else if(local_memory) begin
            owner_rdata=local_allowed ? cache_data : 8'hff;
            owner_valid=!local_allowed || cache_valid;
            if(vram_conflict) begin owner_rdata=engine_source_data; owner_valid=engine_source_valid; end
        end
    end
    assign dispatch_rdata=conflict ? engine_source_data : cache_data;
    assign dispatch_valid=conflict ? engine_source_valid : cache_valid;
    n2m_memory_cpu_port cpu_port (.clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset),
        .init_done(init_done && !fault), .request_valid(request_valid), .address(bus_plan.address),
        .write_enable(bus_plan.write_enable), .write_data(bus_plan.write_data), .bus_commit(bus_commit),
        .read_data(port_rdata), .response_valid(port_valid), .contract_fault(port_fault),
        .storage_read(direct_read), .storage_write(direct_write), .storage_store(direct_store),
        .storage_offset(direct_offset), .storage_wdata(direct_wdata), .storage_rdata(dispatch_rdata),
        .storage_valid(dispatch_valid), .owner_prepare(owner_prepare), .owner_commit(owner_commit),
        .owner_destination(owner_destination), .owner_address(owner_address), .owner_write(owner_write),
        .owner_wdata(owner_wdata), .owner_rdata(owner_rdata), .owner_valid(owner_valid),
        .owner_service_available(owner_available));
    // Absent-cart fixed reads also share the external main bus during DMA.
    assign read_data=conflict ? engine_source_data : port_rdata;
    assign response_valid=port_valid && (!conflict || engine_source_valid) && !fault;
    assign service_read=!conflict && (direct_read ||
        (owner_prepare && local_memory && local_allowed && !owner_write));
    assign service_write=!fault && ((!conflict && direct_write) ||
        (!conflict && owner_commit && local_memory && local_allowed && owner_write) || redirect_write);
    assign service_cpu_store=redirect_write ? STORE_VRAM : direct_store;
    assign service_cpu_offset=redirect_write ? {2'd0,engine_source_address[12:0]} : direct_offset;
    n2m_dma_service service (.clk_sys(clk_sys), .reset(reset), .init_done(init_done && !fault && !invalid_observation),
        .t4(t4 && !engine_fault && !port_fault), .scan_active(ppu_oam_phase==2'd1), .scan_row(effect_row),
        .effect_kind(effect_kind), .dma_write(engine_write), .dma_offset(engine_offset), .dma_byte(transfer_byte),
        .dma_source_request(engine_source_request), .dma_source_address(engine_source_address),
        .dma_source_data(engine_source_data), .dma_source_valid(engine_source_valid), .dma_held_pair(held_pair),
        .dma_pair_pending(pair_pending), .dma_pending_pair(pending_pair),
        .cpu_read(service_read), .cpu_write(service_write), .cpu_store(service_cpu_store),
        .cpu_offset(service_cpu_offset), .cpu_address(bus_plan.address), .cpu_wdata(bus_plan.write_data),
        .cpu_rdata(cache_data), .cpu_valid(cache_valid), .access_read(access_read), .access_write(access_write),
        .access_store(access_store), .access_address(access_address), .access_wdata(access_wdata),
        .access_rdata(access_rdata), .access_valid(access_valid), .fault(service_fault));
    assign raw_vram_read=ppu_vram_request && !reset && !fault &&
        !(access_write && access_store==STORE_VRAM && access_address[12:0]==ppu_vram_address);
    assign raw_vram_address=ppu_vram_address;
    assign ppu_vram_data=raw_vram_data;
    assign ppu_vram_valid=raw_vram_valid && !reset && !fault;
    assign raw_oam_read=ppu_oam_phase!=0 && !dma_active && !reset && !fault &&
        !(access_write && access_store==STORE_OAM && access_address[7:1]==ppu_oam_pair);
    assign raw_oam_pair=ppu_oam_pair;
    // Register selection with the request, including the physical commit edge.
    // After DMA ends only the still-pending destination pair is forwarded.
    assign forward_pair=dma_active || (pair_pending && pending_pair==ppu_oam_pair);
    `DFF_ARST_VAL(oam_dma_response_q, forward_pair, clk_sys, reset, 1'b0)
    `DFF_ARST_VAL(oam_request_q, ppu_oam_phase!=0, clk_sys, reset, 1'b0)
    `DFF_ARST_VAL(held_response_q, held_pair, clk_sys, reset, 16'd0)
    assign ppu_oam_data=oam_dma_response_q ? held_response_q : raw_oam_data;
    assign ppu_oam_valid=!reset && !fault && oam_request_q &&
        (oam_dma_response_q || raw_oam_valid);
endmodule
