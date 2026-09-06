`timescale 1ns/1ps
`default_nettype none
module tb_dma_engine;
    logic clk_sys, reset_sys, core_reset, gb_tick, progress_enable;
    logic [1:0] cpu_phase;
    logic ff46_write, source_valid;
    logic [7:0] ff46_wdata, source_data, ff46_rdata;
    logic source_request, write_valid, active, fault;
    logic [15:0] source_address;
    logic [7:0] write_offset, write_data;
    logic [7:0] expected_offset, expected_data;
    logic expected_write;
    integer page, offset, phase, checks, writes, trace;
    bit corrupt_data, corrupt_time, missing;
    n2m_dma_engine dut (.*);
    always #5 clk_sys = ~clk_sys;
    function automatic logic [7:0] pattern(input logic [15:0] address);
        pattern = address[15:8] ^ {address[3:0],address[7:4]} ^ 8'h69;
    endfunction
    always_comb source_data = pattern(source_address);
    task automatic reset_engine(input bit global_reset);
        @(negedge clk_sys);
        reset_sys=global_reset; core_reset=!global_reset;
        gb_tick=0; ff46_write=0;
        #1;
        if (active || source_request || write_valid || fault || ff46_rdata!==8'h00)
            $fatal(1,"DMA_RESET_CANCEL");
        @(negedge clk_sys); reset_sys=0; core_reset=0;
    endtask
    // Expected coordinates are supplied by the fixture's literal schedule;
    // neither transfer offsets nor DUT active state drive the expected oracle.
    task automatic machine_cycle(input bit commit, input logic [7:0] value,
        input bit expected_active, input bit emit, input logic [7:0] destination,
        input logic [7:0] expected_page);
        logic [7:0] physical_page;
        logic [15:0] expected_address;
        physical_page=expected_page>=8'he0 ? expected_page-8'h20 : expected_page;
        expected_address={physical_page,destination};
        expected_offset=destination; expected_data=pattern(expected_address);
        for (phase=0;phase<4;phase=phase+1) begin
            @(negedge clk_sys);
            cpu_phase=2'(phase); gb_tick=1;
            ff46_write=commit && phase==3; ff46_wdata=value;
            expected_write=emit && phase==3;
            #1;
            if (corrupt_data && writes==7 && expected_write) force dut.write_data=8'h00;
            if (corrupt_time && writes==7 && phase==2) force dut.write_valid=1'b1;
            #1;
            if (write_valid!==expected_write)
                $fatal(1,"DMA_ENGINE_TIME phase=%0d expected=%0b actual=%0b",phase,expected_write,write_valid);
            if (active!==expected_active || source_request!==expected_active)
                $fatal(1,"DMA_ENGINE_ACTIVE phase=%0d expected=%0b actual=%0b",phase,expected_active,active);
            if (expected_active && source_address!==expected_address)
                $fatal(1,"DMA_ENGINE_ADDRESS expected=%04x actual=%04x",expected_address,source_address);
            if (expected_write) begin
                if (write_offset!==destination || write_data!==expected_data)
                    $fatal(1,"DMA_ENGINE_BYTE expected_offset=%0d actual=%0d expected=%02x actual=%02x",destination,write_offset,expected_data,write_data);
                writes=writes+1;
            end
            $fdisplay(trace,"%0d,%0d,%0d,%04x,%04x,%0d,%0d,%02x,%02x",checks,phase,expected_active,expected_address,source_address,expected_write,write_valid,expected_data,write_data);
            checks=checks+1;
            @(posedge clk_sys); #1;
        end
        @(negedge clk_sys); gb_tick=0; ff46_write=0;
    endtask
    initial begin
        clk_sys=0; reset_sys=1; core_reset=0; gb_tick=0; cpu_phase=0;
        progress_enable=1; ff46_write=0; ff46_wdata=0; source_valid=1;
        expected_write=0; expected_offset=0; expected_data=0; checks=0; writes=0;
        corrupt_data=$test$plusargs("CORRUPT_DATA");
        corrupt_time=$test$plusargs("CORRUPT_TIME");
        missing=$test$plusargs("MISSING_SOURCE");
        trace=$fopen("dma-engine.csv","w");
        $dumpfile("dma-engine.vcd");
        $dumpvars(0,clk_sys,reset_sys,core_reset,gb_tick,cpu_phase,progress_enable,
            ff46_write,ff46_wdata,ff46_rdata,source_request,source_address,
            source_valid,source_data,write_valid,write_offset,write_data,
            active,fault,expected_write,expected_offset,expected_data);
        reset_engine(1);
        for (page=0;page<256;page=page+1) begin
            machine_cycle(1,8'(page),0,0,0,0); // M0
            if (ff46_rdata!==8'(page)) $fatal(1,"DMA_FF46_READBACK");
            machine_cycle(0,0,0,0,0,0); // M1
            if (missing) begin
                source_valid=0;
                machine_cycle(0,0,1,0,0,8'(page));
                $fatal(1,"DMA_MISSING_ASSERT_NOT_REACHED");
            end
            for (offset=0;offset<160;offset=offset+1)
                machine_cycle(0,0,1,1,8'(offset),8'(page));
            machine_cycle(0,0,0,0,0,0);
        end
        reset_engine(0);
        machine_cycle(1,8'hc0,0,0,0,0);
        machine_cycle(0,0,0,0,0,0);
        for(offset=0;offset<20;offset=offset+1)
            machine_cycle(0,0,1,1,8'(offset),8'hc0);
        machine_cycle(1,8'hd0,1,1,20,8'hc0); // M0 old prepared byte
        machine_cycle(0,0,1,1,21,8'hd0); // M1 live new page, old offset
        machine_cycle(1,8'hc1,1,1,0,8'hd0); // new M0
        machine_cycle(1,8'hd1,1,1,1,8'hc1); // old trigger matures, new retained
        machine_cycle(0,0,1,1,0,8'hd1); // consecutive trigger matures
        for(offset=0;offset<159;offset=offset+1)
            machine_cycle(0,0,1,1,8'(offset),8'hd1);
        machine_cycle(1,8'hc2,1,1,159,8'hd1); // terminal starts pending
        machine_cycle(0,0,0,0,0,0);
        for(offset=0;offset<159;offset=offset+1)
            machine_cycle(offset==158,8'hd2,1,1,8'(offset),8'hc2);
        machine_cycle(0,0,1,1,159,8'hd2); // mature reset beats terminal
        machine_cycle(0,0,1,1,0,8'hd2);
        // Withheld progress retains prepared data and state at each public phase.
        progress_enable=0;
        repeat(3) machine_cycle(0,0,1,0,1,8'hd2);
        progress_enable=1;
        machine_cycle(0,0,1,1,1,8'hd2);
        reset_engine(0);
        for(offset=0;offset<4;offset=offset+1) begin
            machine_cycle(1,8'hc0,0,0,0,0);
            @(negedge clk_sys); cpu_phase=2'(offset);
            reset_engine(offset[0]); // pending trigger canceled at each phase
            machine_cycle(0,0,0,0,0,0);
            machine_cycle(1,8'hc0,0,0,0,0);
            machine_cycle(0,0,0,0,0,0);
            @(negedge clk_sys); cpu_phase=2'(offset);
            reset_engine(!offset[0]); // active request canceled at each phase
            machine_cycle(0,0,0,0,0,0);
        end
        $fclose(trace);
        $display("PASS DMA engine pages=256 bytes=%0d observations=%0d",writes,checks);
        $finish;
    end
    initial begin #10000000; $fatal(1,"DMA_ENGINE_WATCHDOG"); end
endmodule
