`timescale 1ns/1ps
package n2m_controls_pkg;
    typedef enum logic [1:0] {
        AXIS_CENTER, AXIS_NEGATIVE, AXIS_POSITIVE
    } axis_state_t;
    typedef enum logic [2:0] {
        PAIR_IDLE, PAIR_WAIT_X,
        PAIR_REQUEST_Y, PAIR_WAIT_Y, PAIR_DRAIN, PAIR_FAULT
    } pair_state_t;

    // Thresholds are build-time calibration, not an adaptive recentering that
    // could mistake a held direction for the joystick's center.
    function automatic axis_state_t classify_axis(
        input logic [11:0] sample,
        input axis_state_t previous,
        input int unsigned minimum,
        input int unsigned center,
        input int unsigned maximum
    );
        int unsigned negative_enter;
        int unsigned negative_leave;
        int unsigned positive_enter;
        int unsigned positive_leave;
        negative_enter = center - (center - minimum) / 3;
        negative_leave = center - (center - minimum) / 4;
        positive_enter = center + (maximum - center) / 3;
        positive_leave = center + (maximum - center) / 4;
        if (sample <= negative_enter) return AXIS_NEGATIVE;
        if (sample >= positive_enter) return AXIS_POSITIVE;
        if (previous == AXIS_NEGATIVE && sample < negative_leave) return AXIS_NEGATIVE;
        if (previous == AXIS_POSITIVE && sample > positive_leave) return AXIS_POSITIVE;
        return AXIS_CENTER;
    endfunction
endpackage
