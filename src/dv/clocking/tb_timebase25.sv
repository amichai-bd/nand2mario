`timescale 1ns/1ps
module tb_timebase25;
    logic clk_sys, reset_sys, core_reset, pause_request, gb_tick, paused;
    logic [18:0] bad_sum;
    longint unsigned edges, ticks, previous_dot, previous_machine;
    integer gaps5, gaps6, gaps23, gaps24;
    bit running, carry;
    assign bad_sum = u_tick.phase + 19'd65537;
    always #20 clk_sys = !clk_sys;
    n2m_timebase u_tick (.*);

    // Absolute cumulative rate, independent of the DUT's phase recurrence.
    always @(posedge clk_sys) begin
        if (reset_sys || core_reset) begin
            edges=0; ticks=0; previous_dot=0; previous_machine=0; running=0;
            if (gb_tick !== 0) $fatal(1,"TIMEBASE25_RESET");
        end else begin
            carry=running && ((edges+1)*4194304/25000000 != edges*4194304/25000000);
            if (gb_tick !== carry) $fatal(1,"TIMEBASE25_RATE edge=%0d expected=%0b actual=%0b",edges+1,carry,gb_tick);
            if (running) edges++;
            if (carry) begin
                ticks++;
                if (previous_dot != 0) begin
                    case (edges-previous_dot)
                        5: gaps5++;
                        6: gaps6++;
                        default: $fatal(1,"TIMEBASE25_DOT_BUDGET");
                    endcase
                end
                previous_dot=edges;
                if ((ticks%4)==0) begin
                    if (previous_machine != 0) begin
                        case (edges-previous_machine)
                            23: gaps23++;
                            24: gaps24++;
                            default: $fatal(1,"TIMEBASE25_MACHINE_BUDGET");
                        endcase
                    end
                    previous_machine=edges;
                end
                if (edges != (ticks*25000000+4194303)/4194304)
                    $fatal(1,"TIMEBASE25_JITTER");
            end
            if (!running && !pause_request) running=1;
            else if (running && pause_request && carry) running=0;
            #1;
            if (paused !== !running) $fatal(1,"TIMEBASE25_PAUSE");
        end
    end

    initial begin
        clk_sys=0; reset_sys=1; core_reset=0; pause_request=1;
        gaps5=0; gaps6=0; gaps23=0; gaps24=0;
        $dumpfile("timebase25.vcd"); $dumpvars(0,tb_timebase25);
        if ($test$plusargs("bad_numerator")) force u_tick.sum=bad_sum;
        repeat(4) @(negedge clk_sys);
        reset_sys=0; pause_request=0;
        repeat(16) @(negedge clk_sys); $dumpoff;
        repeat(781250) @(negedge clk_sys); $dumpon;
        if (ticks<131072 || gaps5==0 || gaps6==0 || gaps23==0 || gaps24==0)
            $fatal(1,"TIMEBASE25_COVERAGE");
        pause_request=1; repeat(20) @(negedge clk_sys);
        if (!paused) $fatal(1,"TIMEBASE25_PAUSE_TIMEOUT");
        repeat(20) @(negedge clk_sys);
        pause_request=0; repeat(50) @(negedge clk_sys);
        core_reset=1; pause_request=1; repeat(3) @(negedge clk_sys);
        core_reset=0; pause_request=0; repeat(50) @(negedge clk_sys);
        $display("PASS TIMEBASE25 exact-rate shortest-dot=5 shortest-machine=23 pause reset");
        $finish;
    end
    initial begin #40000000; $fatal(1,"TIMEBASE25_WATCHDOG"); end
endmodule
