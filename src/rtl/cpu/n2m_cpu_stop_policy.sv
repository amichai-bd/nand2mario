`default_nettype none

// DMG entry only. Oscillator restart and its analog uncertainty are separate.
module n2m_cpu_stop_policy (
    input var logic selected_active,
    input var logic enabled_pending,
    input var logic execute,
    output logic [1:0] action,
    output logic padding,
    output logic divider_reset
);
    always_comb begin
        padding = !enabled_pending;
        if (selected_active) action = enabled_pending ? 2'd0 : 2'd1;
        else action = 2'd2;
        divider_reset = execute && !selected_active;
    end
endmodule
