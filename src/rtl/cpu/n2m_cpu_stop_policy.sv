`default_nettype none

// DMG entry only. Oscillator restart and its analog uncertainty are separate.
module n2m_cpu_stop_policy (
    input var logic selected_active,
    input var logic enabled_pending,
    input var logic execute,
    output n2m_cpu_pkg::cpu_stop_action_t action,
    output logic padding,
    output logic divider_reset
);
    import n2m_cpu_pkg::*;

    always_comb begin
        padding = !enabled_pending;
        if (selected_active) action = enabled_pending ? STOP_CONTINUE : STOP_HALT;
        else action = STOP_OSCILLATOR;
        divider_reset = execute && !selected_active;
    end
endmodule
