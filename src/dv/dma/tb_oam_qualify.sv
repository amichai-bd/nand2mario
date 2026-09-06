`timescale 1ns/1ps
`default_nettype none
module tb_oam_qualify;
    import n2m_cpu_pkg::*;
    import n2m_oam_pkg::*;
    logic clk_sys, reset, effect_sample, effect_resolved;
    cpu_address_effect_t address_effect;
    cpu_bus_plan_t bus_plan;
    logic bus_commit;
    logic [1:0] ppu_oam_phase;
    logic [5:0] ppu_scan_index;
    oam_effect_t kind;
    logic [4:0] row_index;
    logic invalid_observation;
    logic [1:0] expected_kind;
    logic expected_read, expected_write;
    integer ordinary_mode, idu_mode, ordinary_address, idu_address, phase_index, scan_index;
    integer checked, kinds_seen[4];
    bit bad_mask, corrupt;
    n2m_oam_qualify dut (.*);
    always #5 clk_sys=~clk_sys;
    function automatic logic[15:0] address_at(input integer index);
        case(index)
            0:address_at=16'hfe00;1:address_at=16'hfe9f;
            2:address_at=16'hfea0;3:address_at=16'hfeff;
            4:address_at=16'hfdff;default:address_at=16'hff00;
        endcase
    endfunction
    function automatic logic[5:0] scan_at(input integer index);
        case(index)
            0:scan_at=0;1:scan_at=2;2:scan_at=8;3:scan_at=36;
            4:scan_at=38;5:scan_at=40;default:scan_at=63;
        endcase
    endfunction
    task automatic check_case;
        #1;
        if(invalid_observation || kind!==expected_kind || row_index!==ppu_scan_index[5:1])
            $fatal(1,"OAM_QUALIFIER_ORACLE case=%0d expected=%0d actual=%0d row=%0d phase=%0d ordinary=%04x idu=%04x mask=%04x",
                checked,expected_kind,kind,row_index,ppu_oam_phase,bus_plan.address,address_effect.address,address_effect.known_mask);
        checked=checked+1;kinds_seen[expected_kind]=kinds_seen[expected_kind]+1;
        @(negedge clk_sys);
    endtask
    initial begin
        clk_sys=0;reset=1;effect_sample=0;effect_resolved=1;address_effect='0;bus_plan='0;
        bus_commit=0;ppu_oam_phase=0;ppu_scan_index=0;expected_kind=0;
        expected_read=0;expected_write=0;checked=0;
        for(scan_index=0;scan_index<4;scan_index=scan_index+1)kinds_seen[scan_index]=0;
        bad_mask=$test$plusargs("BAD_MASK");corrupt=$test$plusargs("CORRUPT_CLASS");
        $dumpfile("oam-qualify.vcd");
        $dumpvars(0,clk_sys,reset,effect_sample,effect_resolved,address_effect,bus_plan,bus_commit,
            ppu_oam_phase,ppu_scan_index,kind,row_index,invalid_observation,expected_kind,checked);
        repeat(3)@(negedge clk_sys);reset=0;
        if(bad_mask)begin
            effect_sample=1;address_effect.valid=1;address_effect.write_effect=1;
            address_effect.address=16'hfe00;address_effect.known_mask=16'h00ff;
            repeat(2)@(negedge clk_sys);$fatal(1,"OAM_QUALIFIER_MASK_NOT_REJECTED");
        end
        if(corrupt)force dut.kind=OAM_WRITE;
        // Literal address-list membership is independent of DUT address slicing.
        for(ordinary_mode=0;ordinary_mode<3;ordinary_mode=ordinary_mode+1)
        for(idu_mode=0;idu_mode<3;idu_mode=idu_mode+1)
        for(ordinary_address=0;ordinary_address<6;ordinary_address=ordinary_address+1)
        for(idu_address=0;idu_address<6;idu_address=idu_address+1)
        for(phase_index=0;phase_index<3;phase_index=phase_index+1)
        for(scan_index=0;scan_index<7;scan_index=scan_index+1)begin
            effect_sample=1;bus_commit=ordinary_mode!=0;
            bus_plan='0;bus_plan.address=address_at(ordinary_address);bus_plan.write_enable=ordinary_mode==2;
            address_effect='0;address_effect.valid=idu_mode!=0;address_effect.write_effect=idu_mode!=0;
            if(idu_mode!=0)begin
                address_effect.address=address_at(idu_address);
                address_effect.known_mask=idu_mode==1 ? 16'hffff:16'hff00;
                if(idu_mode==2)address_effect.address[7:0]=8'hxx;
            end
            ppu_oam_phase=2'(phase_index);ppu_scan_index=scan_at(scan_index);
            expected_read=ordinary_mode==1 && ordinary_address<4;
            expected_write=(ordinary_mode==2 && ordinary_address<4) || (idu_mode!=0 && idu_address<4);
            expected_kind=0;
            if(phase_index==1 && scan_index<5)begin
                if(expected_read && expected_write)expected_kind=3;
                else if(expected_read)expected_kind=1;
                else if(expected_write)expected_kind=2;
            end
            check_case();
        end
        // Prepared IDU data alone has no sampled effect.
        bus_commit=0;effect_sample=0;address_effect={1'b1,16'hfe00,16'hffff,1'b1};
        ppu_oam_phase=1;expected_kind=0;
        for(scan_index=0;scan_index<7;scan_index=scan_index+1)begin ppu_scan_index=scan_at(scan_index);check_case();end
        if(checked!=6811 || kinds_seen[1]==0 || kinds_seen[2]==0 || kinds_seen[3]==0)$fatal(1,"OAM_QUALIFIER_TOTAL");
        $display("PASS OAM qualifier cases=6811 full/high-mask addresses scan exclusions");$finish;
    end
    initial begin #1000000;$fatal(1,"OAM_QUALIFIER_WATCHDOG");end
endmodule
