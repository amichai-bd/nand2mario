`default_nettype none
`include "src/rtl/common/macros.svh"
module n2m_timer (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic core_reset,
    input var logic gb_tick,
    input var logic divider_reset_request,
    input var logic io_commit,
    input var logic io_write,
    input var logic [15:0] io_address,
    input var logic [7:0] io_wdata,
    output logic io_selected,
    output logic [7:0] io_rdata,
    output n2m_timer_pkg::timer_request_t interrupt_request,
    output logic [7:0] div_observe,
    output logic [7:0] tima_observe,
    output logic [7:0] tma_observe,
    output logic [7:0] tac_observe
);
    n2m_timer_pkg::timer_state_t state_q, state_next;
    n2m_timer_pkg::timer_request_t request_q, request_next;
    logic reset, write_div, write_tima, write_tma, write_tac;
    logic old_signal, advanced_signal, final_signal, falling;
    logic [15:0] advanced_divider;
    logic reloading;
    function automatic logic timer_signal(input logic [15:0] divider, input logic [2:0] tac);
        logic selected;
        selected = 0;
        case (tac[1:0])
            0: selected = divider[9];
            1: selected = divider[3];
            2: selected = divider[5];
            3: selected = divider[7];
        endcase
        return tac[2] && selected;
    endfunction
    function automatic n2m_timer_pkg::timer_state_t reset_state();
        n2m_timer_pkg::timer_state_t value;
        value = '0;
        value.divider = {n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL,n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL};
        value.tima = n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL;
        value.tma = n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL;
        value.tac = n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL[2:0];
        return value;
    endfunction
    assign reset = reset_sys || core_reset;
    assign io_selected = io_address >= n2m_interfaces_pkg::GB_REG_DIV && io_address <= n2m_interfaces_pkg::GB_REG_TAC;
    assign write_div = io_commit && io_write && io_address == n2m_interfaces_pkg::GB_REG_DIV;
    assign write_tima = io_commit && io_write && io_address == n2m_interfaces_pkg::GB_REG_TIMA;
    assign write_tma = io_commit && io_write && io_address == n2m_interfaces_pkg::GB_REG_TMA;
    assign write_tac = io_commit && io_write && io_address == n2m_interfaces_pkg::GB_REG_TAC;
    always_comb begin
        state_next = state_q;
        request_next = '0;
        advanced_divider = state_q.divider + 16'd1;
        old_signal = timer_signal(state_q.divider,state_q.tac);
        advanced_signal = timer_signal(advanced_divider,state_q.tac);
        final_signal = advanced_signal;
        falling = 0;
        reloading = state_q.reload_delay == 1 || state_q.reload_hold != 0;
        if (gb_tick) begin
            state_next.divider = advanced_divider;
            if (divider_reset_request || write_div) state_next.divider = 0;
            if (write_tac) state_next.tac = io_wdata[2:0];
            if (write_tma) state_next.tma = io_wdata;
            final_signal = timer_signal(state_next.divider,state_next.tac);
            falling = (old_signal && !advanced_signal) || (advanced_signal && !final_signal);
            if (state_q.reload_delay != 0) state_next.reload_delay = state_q.reload_delay - 3'd1;
            if (state_q.reload_hold != 0) state_next.reload_hold = state_q.reload_hold - 2'd1;
            if (reloading) begin
                state_next.tima = state_next.tma;
                if (state_q.reload_delay == 1) begin
                    state_next.reload_hold = 3;
                    request_next.request = 1;
                end
            end else if (write_tima) begin
                state_next.tima = io_wdata;
                state_next.reload_delay = 0;
            end else if (state_q.reload_delay == 0 && falling) begin
                state_next.tima = state_q.tima + 8'd1;
                if (state_q.tima == 8'hFF) state_next.reload_delay = 4;
            end
        end
    end
    `DFF_ARST_VAL(state_q,state_next,clk_sys,reset,reset_state())
    `DFF_ARST_VAL(request_q,request_next,clk_sys,reset,'0)
    assign interrupt_request = reset ? n2m_timer_pkg::timer_request_t'('0) : request_q;
    // Host observations. Pure reads of the same committed state the CPU port
    // reports; no write, commit or divider reset is derived from them.
    assign div_observe = reset ? n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL : state_q.divider[15:8];
    assign tima_observe = reset ? n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL : state_q.tima;
    assign tma_observe = reset ? n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL : state_q.tma;
    assign tac_observe = {5'b0, reset ? n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL[2:0] : state_q.tac};
    always_comb begin
        io_rdata = 0;
        case (io_address)
            n2m_interfaces_pkg::GB_REG_DIV: io_rdata = reset ? n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL : state_q.divider[15:8];
            n2m_interfaces_pkg::GB_REG_TIMA: io_rdata = reset ? n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL : state_q.tima;
            n2m_interfaces_pkg::GB_REG_TMA: io_rdata = reset ? n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL : state_q.tma;
            n2m_interfaces_pkg::GB_REG_TAC: io_rdata = {5'b11111,reset ? n2m_interfaces_pkg::PROFILE_PERIPHERAL_FILL[2:0] : state_q.tac};
            default: begin end
        endcase
    end
    `N2M_ASSERT(TIMER_COMMIT_BOUNDARY,clk_sys,reset,!io_commit || (gb_tick && io_selected))
    `N2M_ASSERT(TIMER_STOP_BOUNDARY,clk_sys,reset,!divider_reset_request || gb_tick)
    `N2M_ASSERT(TIMER_RELOAD_RANGE,clk_sys,reset,state_q.reload_delay <= 4)
    `N2M_ASSERT_KNOWN(TIMER_CONTROLS,clk_sys,reset,{gb_tick,divider_reset_request,io_commit,io_write})
    `N2M_ASSERT(TIMER_WRITE_KNOWN,clk_sys,reset,!(io_commit && io_write) || !$isunknown({io_address,io_wdata}))
    `N2M_ASSERT_STABLE_WHEN(TIMER_PAUSED_STATE,clk_sys,reset,!gb_tick,state_q)
endmodule
