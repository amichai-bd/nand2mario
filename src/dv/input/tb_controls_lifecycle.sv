`timescale 1ns/1ps
module tb_controls_lifecycle;
    logic clk;
    logic reset;
    logic available;
    logic gb_tick;
    logic [3:0] buttons_n;
    logic command_valid;
    logic [4:0] command_channel;
    logic command_ready;
    logic response_valid;
    logic [4:0] response_channel;
    logic [11:0] response_data;
    logic physical_commit;
    logic [7:0] physical_buttons;
    logic [7:0] observed;
    logic fresh;
    logic fault;
    logic [7:0] expected;
    n2m_input_pkg::input_write_t host_write;
    n2m_input_pkg::input_update_t update;
    integer checks;
    integer scenario;
    integer method;
    integer button;
    integer i;
    bit sticky;
    bit unsolicited;
    bit corrupt;
    n2m_physical_controls #(.BUTTON_CYCLES(3), .INTERVAL_CYCLES(4), .LIMIT_CYCLES(32)) dut (
        .clk_sys(clk), .reset_sys(reset), .gb_tick(gb_tick), .buttons_n(buttons_n),
        .adc_available(available), .command_valid(command_valid), .command_channel(command_channel),
        .command_ready(command_ready), .response_valid(response_valid), .response_channel(response_channel),
        .response_data(response_data), .physical_commit(physical_commit), .physical_buttons(physical_buttons),
        .adc_fresh(fresh), .adc_fault(fault)
    );
    n2m_input u_input (
        .clk_sys(clk), .reset_sys(reset), .core_reset(1'b0), .gb_tick(gb_tick), .host_write(host_write),
        .physical_commit(physical_commit), .physical_buttons(physical_buttons),
        .host_buttons(), .physical_observe(observed), .source_observe(), .effective_buttons(), .effective_update(update)
    );
    initial begin clk = 1'b0; forever #10 clk = !clk; end
    task automatic step;
        @(posedge clk); #1; @(negedge clk);
    endtask
    task automatic check(input logic [7:0] value);
        expected = value;
        if (observed !== value) $fatal(1,"CONTROLS_LIFECYCLE scenario=%0d method=%0d check=%0d expected=%02h actual=%02h", scenario,method,checks,value,observed);
        checks = checks + 1;
    endtask
    task automatic restart;
        reset = 1'b1; available = 1'b1; command_ready = 1'b0; response_valid = 1'b0;
        buttons_n = 4'hF; gb_tick = 1'b0; step(); reset = 1'b0; step();
        if (fault || fresh) $fatal(1,"CONTROLS_RESTART");
        check(8'h00);
    endtask
    task automatic accept(input logic [4:0] channel);
        integer wait_count;
        wait_count = 0;
        while (!command_valid && wait_count < 8) begin step(); wait_count = wait_count + 1; end
        if (!command_valid || command_channel !== channel) $fatal(1,"CONTROLS_COMMAND expected=%0d actual=%0d",channel,command_channel);
        command_ready = 1'b1; step(); command_ready = 1'b0;
    endtask
    task automatic respond(input logic [4:0] channel, input logic [11:0] data);
        response_channel = channel; response_data = data; response_valid = 1'b1;
        step(); response_valid = 1'b0; #1;
    endtask
    task automatic pair(input logic [11:0] x, input logic [11:0] y, input logic [7:0] mask);
        accept(5'd1); respond(5'd1,x); accept(5'd2); respond(5'd2,y); check(mask);
        if (!fresh || fault) $fatal(1,"CONTROLS_PAIR_FRESH");
    endtask
    task automatic hold_buttons;
        buttons_n = 4'h0; repeat (5) step(); check(8'hF0);
    endtask
    initial begin
        reset=1'b1; available=1'b1; gb_tick=1'b0; buttons_n=4'hF; command_ready=1'b0;
        response_valid=1'b0; response_channel=5'd0; response_data=12'd0; host_write='0;
        checks=0; scenario=0; method=0; expected=8'h00;
        sticky=$test$plusargs("STICKY"); unsolicited=$test$plusargs("UNSOLICITED"); corrupt=$test$plusargs("CORRUPT_RECOVERY");
        $dumpfile("waves.vcd");
        $dumpvars(0,clk,reset,available,gb_tick,buttons_n,command_valid,command_channel,command_ready,
            response_valid,response_channel,response_data,physical_commit,physical_buttons,observed,fresh,fault,expected,scenario,method);
        @(negedge clk); restart();
        if (unsolicited) begin
            respond(5'd1,12'd0); $fatal(1,"CONTROLS_EXPECTED_UNSOLICITED_ASSERT");
        end
        if (sticky) begin
            pair(12'd0,12'd2703,8'h0A);
            accept(5'd1); respond(5'd2,12'd0); step();
            if (!fault || fresh || command_valid) $fatal(1,"CONTROLS_STICKY_FAULT");
            check(8'h00); hold_buttons();
            available=1'b0; repeat(5) step(); available=1'b1; repeat(40) step();
            if (!fault || fresh || command_valid) $fatal(1,"CONTROLS_FAULT_LOST_ON_ADC_RESET");
            check(8'hF0); buttons_n=4'hF; repeat(5) step(); check(8'h00);
            restart(); pair(12'd2703,12'd0,8'h05);
            $display("PASS controls sticky fault checks=%0d",checks); $finish;
        end
        // Every independent button has a sampled bounce and exact press/release
        // thresholds after two synchronizer clocks and three stable samples.
        for (button=0;button<4;button=button+1) begin
            buttons_n=4'hF^(4'b1<<button); step(); buttons_n=4'hF; repeat(5) step(); check(8'h00);
            buttons_n=4'hF^(4'b1<<button); repeat(4) step(); check(8'h00); step();
            case(button)
                0: check(8'h10);
                1: check(8'h20);
                2: check(8'h80);
                3: check(8'h40);
            endcase
            buttons_n=4'hF; repeat(4) step();
            case(button)
                0: check(8'h10);
                1: check(8'h20);
                2: check(8'h80);
                3: check(8'h40);
            endcase
            step(); check(8'h00);
        end
        pair(12'd903,12'd1801,8'h00);
        pair(12'd902,12'd1802,8'h0A);
        pair(12'd1013,12'd1690,8'h0A);
        pair(12'd1014,12'd1689,8'h00);
        pair(12'd1801,12'd903,8'h00);
        pair(12'd1802,12'd902,8'h05);
        pair(12'd1690,12'd1013,8'h05);
        pair(12'd1689,12'd1014,8'h00);
        for (i=0;i<8;i=i+1) pair(12'd4095,12'd4095,8'h09);
        // Reset/ADC cancellation from idle, X wait, Y request, Y wait, drain.
        for (method=0;method<2;method=method+1) begin
            for (scenario=0;scenario<5;scenario=scenario+1) begin
                restart(); hold_buttons();
                if (scenario>0) accept(5'd1);
                if (scenario==2 || scenario==3) respond(5'd1,12'd0);
                if (scenario==3) accept(5'd2);
                if (scenario==4) repeat(32) step();
                if (method==0) begin
                    reset=1'b1; step(); reset=1'b0; step(); check(8'h00);
                    repeat(5) step(); check(8'hF0);
                end else begin
                    available=1'b0; step();
                    if (fresh || command_valid) $fatal(1,"CONTROLS_CANCEL");
                    check(8'hF0); repeat(3) step(); available=1'b1;
                end
                if (corrupt && scenario==3 && method==1) force physical_buttons=8'hF0;
                pair(12'd2703,12'd0,8'hF5);
            end
        end
        // Y response on its absolute deadline loses; stale X cannot revive.
        restart(); hold_buttons(); accept(5'd1); respond(5'd1,12'd0); accept(5'd2);
        repeat(29) step(); respond(5'd2,12'd2703); check(8'hF0);
        if (fresh) $fatal(1,"CONTROLS_DEADLINE_RESPONSE");
        pair(12'd2703,12'd0,8'hF5);
        // Prior pair freshness expires while a replacement X is outstanding.
        accept(5'd1); repeat(32) step(); check(8'hF0);
        if (fresh || command_valid) $fatal(1,"CONTROLS_STALE_DRAIN");
        buttons_n=4'hF; repeat(5) step(); check(8'h00);
        respond(5'd1,12'd0); pair(12'd2703,12'd0,8'h05);
        // Missing Y leaves drain indefinitely while buttons remain live.
        accept(5'd1); respond(5'd1,12'd0); accept(5'd2); repeat(40) step(); check(8'h00);
        if (fresh || command_valid) $fatal(1,"CONTROLS_MISSING_Y");
        hold_buttons(); repeat(40) step(); check(8'hF0);
        respond(5'd2,12'd2703); check(8'hF0);
        pair(12'd0,12'd2703,8'hFA);
        $display("PASS controls lifecycle checks=%0d reset-cases=10",checks); $finish;
    end
    initial begin #1000000; $fatal(1,"CONTROLS_LIFECYCLE_WATCHDOG"); end
endmodule
