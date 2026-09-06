`default_nettype none
`include "src/rtl/common/macros.svh"

// Single owner of architectural steering. Temporal bus and recorder state
// belong to their separate modules in the composition wrapper.
module n2m_cpu_control (
    input var logic clk_sys,
    input var logic reset_sys,
    input var logic core_reset,
    input var logic gb_tick,
    input var logic [7:0] profile_id,
    input var logic [31:0] epoch,
    input var logic [63:0] dot_before,
    input var logic [7:0] ie,
    input var logic [4:0] iflags,
    input var logic [7:0] read_data,
    input var logic joyp_selected_active,
    input var logic wake_request,
    input var logic [1:0] phase,
    input var logic cycle_end,
    input var logic bus_fault,
    input var n2m_cpu_pkg::cpu_execute_result_t execute_result,
    input var n2m_cpu_pkg::cpu_stop_action_t stop_action,
    input var logic stop_padding,
    input var logic divider_reset_request,
    output n2m_cpu_pkg::cpu_execute_request_t execute_request,
    output n2m_cpu_pkg::cpu_bus_plan_t bus_plan,
    output n2m_cpu_pkg::cpu_retire_capture_t retire_capture,
    output logic active,
    output logic complete_enable,
    output logic pending_irq,
    output n2m_cpu_pkg::cpu_address_effect_t address_effect,
    output logic address_effect_resolved,
    output logic address_effect_sample,
    output logic [1:0] address_effect_phase,
    output logic [4:0] irq_ack,
    output logic halted,
    output logic stopped,
    output logic locked,
    output logic initialized,
    output logic fault,
    output logic ime_observe,
    output logic ime_delay_observe,
    output logic stop_execute
);
    import n2m_cpu_pkg::*;
    import n2m_interfaces_pkg::*;

    cpu_control_t control;
    cpu_control_t control_next;
    cpu_registers_t registers;
    cpu_registers_t registers_next;
    logic [4:0] dispatch;
    logic [4:0] selected_irq;
    logic [15:0] selected_vector;
    logic hold_address_effect;

    function automatic cpu_registers_t profile_registers;
        cpu_registers_t r;
        r.a = PROFILE_A;
        r.f = PROFILE_F;
        r.b = PROFILE_B;
        r.c = PROFILE_C;
        r.d = PROFILE_D;
        r.e = PROFILE_E;
        r.h = PROFILE_H;
        r.l = PROFILE_L;
        r.sp = PROFILE_SP;
        return r;
    endfunction

    function automatic cpu_control_t profile_control;
        cpu_control_t c;
        c = '0;
        c.mode = PROFILE_CPU_STOP[0] ? MODE_STOP : (PROFILE_CPU_HALT[0] ? MODE_HALT : MODE_FETCH);
        c.pc = PROFILE_PC;
        c.instruction_pc = PROFILE_PC;
        c.ime = PROFILE_IME[0];
        c.ime_delay = PROFILE_IME_DELAY[0];
        c.halt_bug = PROFILE_HALT_BUG[0];
        return c;
    endfunction

    always_comb begin
        execute_request.registers = registers;
        execute_request.opcode = control.opcode;
        execute_request.cb_bank = control.cb_bank;
        execute_request.step = control.step;
        execute_request.pc = control.pc;
        execute_request.temporary = control.temporary;
        execute_request.data = read_data;
    end

    assign fault = bus_fault || control.profile_fault;
    assign initialized = control.initialized;
    assign active = initialized && !fault && (control.mode == MODE_FETCH || control.mode == MODE_EXECUTE || control.mode == MODE_INTERRUPT || control.mode == MODE_HALT);
    assign complete_enable = control.mode != MODE_HALT || pending_irq;
    assign halted = control.mode == MODE_HALT;
    assign stopped = control.mode == MODE_STOP;
    assign locked = control.mode == MODE_LOCK;
    assign ime_observe = control.ime;
    assign ime_delay_observe = control.ime_delay;
    assign pending_irq = |control.irq_snapshot;
    assign dispatch = control.irq_snapshot;
    assign stop_execute = control.mode == MODE_EXECUTE && execute_result.stop_request && cycle_end;

    assign address_effect_phase = phase;
    assign address_effect_sample = gb_tick && phase == 3 && initialized &&
        !fault && !reset_sys && !core_reset && (!active || cycle_end);
    assign hold_address_effect = initialized && !fault &&
        (phase != 0 || gb_tick) && !(gb_tick && phase == 3);

    // Incomplete source mappings are visible to the future consumer. They
    // never masquerade as resolved cycles without an additional effect.
    always_comb begin
        address_effect = '0;
        address_effect_resolved = 1;
        if (control.mode == MODE_FETCH || control.mode == MODE_HALT) begin
            address_effect_resolved = !control.observation_resume;
            address_effect.valid = !control.observation_resume;
            address_effect.address = control.observation_resume ? 16'b0 : control.pc;
        end else if (control.mode == MODE_EXECUTE) begin
            address_effect = execute_result.address_effect;
            if (execute_result.finish && !execute_result.halt_request && !execute_result.stop_request) begin
                address_effect.valid = 1;
                address_effect.address = execute_result.pc_after;
            end
            if (execute_result.stop_request) begin
                // Completed STOP drives its pre-fetch PC through the IDU.
                // Retirement length does not determine this additional effect.
                address_effect.valid = 1;
                address_effect.address = control.pc;
            end
        end else if (control.mode == MODE_INTERRUPT) begin
            if (control.step == 0) begin
                address_effect_resolved = !control.observation_resume;
                address_effect.valid = !control.observation_resume;
                address_effect.address = control.observation_resume ? 16'b0 : control.pc;
            end
            else if (control.step == 1 || control.step == 2) begin
                address_effect.valid = 1;
                address_effect.address = registers.sp;
            end else if (control.step == 4) begin
                address_effect.valid = 1;
                address_effect.address = control.pc;
            end
        end else if (control.mode == MODE_STOP)
            address_effect_resolved = 0;
        if (address_effect.valid) begin
            if (address_effect.known_mask == 0) address_effect.known_mask = 16'hffff;
            address_effect.write_effect = 1;
        end
        if (!initialized || fault || reset_sys || core_reset) begin
            address_effect = '0;
            address_effect_resolved = 0;
        end
    end

    always_comb begin
        bus_plan.address = control.pc;
        bus_plan.write_data = 0;
        bus_plan.write_enable = 0;
        bus_plan.access_kind = ACCESS_IDLE;
        if (control.mode == MODE_FETCH || control.mode == MODE_HALT) bus_plan.access_kind = ACCESS_OPCODE;
        else if (control.mode == MODE_EXECUTE) begin
            bus_plan.address = execute_result.plan.address;
            bus_plan.write_data = execute_result.plan.write_data;
            bus_plan.write_enable = execute_result.plan.write_enable;
            bus_plan.access_kind = execute_result.plan.access_kind;
        end else if (control.mode == MODE_INTERRUPT) begin
            if (control.step == 2 || control.step == 3) begin
                bus_plan.address = registers.sp;
                bus_plan.write_enable = 1;
                bus_plan.write_data = control.step == 2 ? control.irq_pc[15:8] : control.irq_pc[7:0];
                bus_plan.access_kind = ACCESS_STACK;
            end else if (control.step == 4) bus_plan.access_kind = ACCESS_OPCODE;
        end
    end

    always_comb begin
        selected_irq = 0;
        selected_vector = 0;
        if (dispatch[0]) begin selected_irq = 5'b00001; selected_vector = VECTOR_VBLANK; end
        else if (dispatch[1]) begin selected_irq = 5'b00010; selected_vector = VECTOR_STAT; end
        else if (dispatch[2]) begin selected_irq = 5'b00100; selected_vector = VECTOR_TIMER; end
        else if (dispatch[3]) begin selected_irq = 5'b01000; selected_vector = VECTOR_SERIAL; end
        else if (dispatch[4]) begin selected_irq = 5'b10000; selected_vector = VECTOR_JOYPAD; end
    end

    always_comb begin
        control_next = control;
        registers_next = registers;
        retire_capture = '0;
        retire_capture.valid = 0;
        retire_capture.is_interrupt = 0;
        retire_capture.pc_before = control.instruction_pc;
        retire_capture.pc_after = control.pc;
        retire_capture.fetched_bytes = control.fetched;
        retire_capture.fetched_length = control.length;
        retire_capture.halted_after = halted;
        retire_capture.stopped_after = stopped;
        irq_ack = 0;
        // PHI closes the enabled-request latch at T3 rising. Recognition and
        // low-stack vector selection consume this frozen M-cycle snapshot.
        if (gb_tick && phase == 2) control_next.irq_snapshot = ie[4:0] & iflags;
        // The power owner has already latched the selected-line wake and
        // qualified stable clocks. Accept before T1; the mode transition
        // retains a one-edge pulse even while host pause withholds ticks.
        // Approved digital restart uses ordinary fetch/IRQ behavior even when
        // IME-enabled requests arrived during oscillator restart.
        if (control.mode == MODE_STOP && wake_request && phase == 0 && !gb_tick) begin
            control_next.mode = MODE_FETCH;
            control_next.observation_resume = 0;
        end
        if (cycle_end) begin
            case (control.mode)
                // HALT continuously prepares this read, but only its frozen
                // pending request enables completion. Wake captures fresh data
                // at this T4; it never reuses the discarded pre-sleep byte.
                MODE_FETCH, MODE_HALT: begin
                    control_next.observation_resume = control.observation_resume && control.ime && pending_irq;
                    control_next.opcode = read_data;
                    control_next.fetched = {16'b0, read_data};
                    control_next.length = 1;
                    control_next.instruction_pc = control.pc;
                    control_next.pc = control.pc + 16'd1;
                    control_next.step = 0;
                    control_next.cb_bank = 0;
                    control_next.halt_bug = 0;
                    control_next.mode = MODE_EXECUTE;
                    if (control.ime && pending_irq) begin
                        control_next.mode = MODE_INTERRUPT;
                        control_next.irq_pc = control.pc;
                    end
                end
                MODE_EXECUTE: begin
                    registers_next = execute_result.registers_after;
                    control_next.pc = execute_result.pc_after;
                    control_next.temporary = execute_result.temporary_after;
                    control_next.step = control.step + 3'd1;
                    if (execute_result.plan.access_kind == ACCESS_OPERAND) begin
                        case (control.length)
                            1: control_next.fetched[15:8] = read_data;
                            2: control_next.fetched[23:16] = read_data;
                            default: begin end
                        endcase
                        control_next.length = control.length + 2'd1;
                    end
                    if (execute_result.prefix) begin
                        control_next.opcode = read_data;
                        control_next.cb_bank = 1;
                        control_next.step = 0;
                    end
                    if (execute_result.illegal) control_next.mode = MODE_LOCK;
                    if (execute_result.finish) begin
                        retire_capture.valid = 1;
                        retire_capture.pc_after = execute_result.pc_after;
                        control_next.step = 0;
                        control_next.cb_bank = 0;
                        control_next.ime = control.ime || control.ime_delay || execute_result.return_interrupt;
                        control_next.ime_delay = 0;
                        if (execute_result.disable_interrupts) control_next.ime = 0;
                        else if (execute_result.enable_interrupts && !control_next.ime) control_next.ime_delay = 1;
                        control_next.opcode = read_data;
                        control_next.fetched = {16'b0, read_data};
                        control_next.length = 1;
                        control_next.instruction_pc = execute_result.pc_after;
                        control_next.pc = execute_result.pc_after + 16'd1;
                        control_next.halt_bug = 0;
                        if (execute_result.halt_request) begin
                            control_next.pc = execute_result.pc_after;
                            if (pending_irq) begin
                                if (control_next.ime) begin
                                    // A request recognized while HALT executes
                                    // with IME set returns to this HALT. This also
                                    // covers delayed EI maturation; late arrivals
                                    // after the T3 snapshot instead enter sleep.
                                    retire_capture.pc_after = control.instruction_pc;
                                    control_next.pc = control.instruction_pc + 16'd1;
                                end else control_next.halt_bug = 1;
                            end else begin
                                control_next.mode = MODE_HALT;
                                retire_capture.halted_after = 1;
                            end
                        end
                        if (execute_result.stop_request) begin
                            if (stop_padding) begin
                                retire_capture.fetched_bytes[15:8] = read_data;
                                retire_capture.fetched_length = 2;
                                retire_capture.pc_after = execute_result.pc_after + 16'd1;
                            end
                            if (stop_action != STOP_CONTINUE) begin
                                control_next.observation_resume = stop_action == STOP_OSCILLATOR;
                                control_next.pc = retire_capture.pc_after;
                                control_next.mode = stop_action == STOP_HALT ? MODE_HALT : MODE_STOP;
                                retire_capture.halted_after = stop_action == STOP_HALT;
                                retire_capture.stopped_after = stop_action == STOP_OSCILLATOR;
                            end
                        end
                        if (control_next.ime && pending_irq && !retire_capture.stopped_after) begin
                            control_next.mode = MODE_INTERRUPT;
                            control_next.irq_pc = retire_capture.pc_after;
                            retire_capture.halted_after = 0;
                            control_next.halt_bug = 0;
                        end
                    end
                end
                MODE_INTERRUPT: begin
                    control_next.step = control.step + 3'd1;
                    control_next.ime = 0;
                    control_next.ime_delay = 0;
                    control_next.halt_bug = 0;
                    if (control.step == 0) control_next.pc = control.irq_pc;
                    if (control.step == 1 || control.step == 2)
                        registers_next.sp = registers.sp - 16'd1;
                    if (control.step == 3) begin
                        control_next.pc = selected_vector;
                        irq_ack = selected_irq;
                    end
                    if (control.step == 4) begin
                        control_next.observation_resume = 0;
                        retire_capture.valid = 1;
                        retire_capture.is_interrupt = 1;
                        retire_capture.pc_before = control.irq_pc;
                        retire_capture.pc_after = control.pc;
                        control_next.mode = MODE_EXECUTE;
                        control_next.step = 0;
                        control_next.cb_bank = 0;
                        control_next.instruction_pc = control.pc;
                        control_next.pc = control.pc + 16'd1;
                        control_next.opcode = read_data;
                        control_next.fetched = {16'b0, read_data};
                        control_next.length = 1;
                    end
                end
                default: begin end
            endcase
        end
        if (core_reset) begin
            control_next = profile_control();
            control_next.initialized = profile_id == PROFILE_DIRECT_ID;
            control_next.profile_fault = profile_id != PROFILE_DIRECT_ID;
            registers_next = profile_registers();
            retire_capture.valid = 0;
            irq_ack = 0;
        end
        retire_capture.registers_after = registers_next;
        retire_capture.ime_after = control_next.ime;
        retire_capture.ime_delay_after = control_next.ime_delay;
        retire_capture.halt_bug_after = control_next.halt_bug;
        retire_capture.epoch = epoch;
        retire_capture.dot_after = dot_before + 64'd1;
    end

    `DFF_ARST_VAL(control, control_next, clk_sys, reset_sys, profile_control())
    `DFF_ARST_VAL(registers, registers_next, clk_sys, reset_sys, profile_registers())

    `N2M_ASSERT(CPU_STOP_WAKE_BOUNDARY, clk_sys, reset_sys || core_reset,
        (stopped && wake_request) |-> (phase == 0 && !gb_tick))
    `N2M_ASSERT_KNOWN(CPU_STOP_WAKE_KNOWN, clk_sys, reset_sys || core_reset, wake_request)
    `N2M_ASSERT(CPU_STOP_DIVIDER_EDGE, clk_sys, reset_sys,
        !divider_reset_request || (stop_execute && gb_tick && phase == 3 && !core_reset))
    `N2M_ASSERT_KNOWN(CPU_STOP_SELECTED_KNOWN, clk_sys, reset_sys || core_reset,
        joyp_selected_active)
    `N2M_ASSERT(CPU_PROFILE_ID, clk_sys, reset_sys,
        core_reset |-> profile_id == PROFILE_DIRECT_ID)
    `N2M_ASSERT(CPU_IRQ_ACK_ONEHOT, clk_sys, reset_sys || core_reset, $onehot0(irq_ack))
    `N2M_ASSERT_STABLE_WHEN(CPU_IDU_PLAN_STABLE, clk_sys, reset_sys || core_reset,
        hold_address_effect, {address_effect_resolved, address_effect})
    `N2M_ASSERT(CPU_IDU_OUTPUT_PAGE, clk_sys, reset_sys || core_reset,
        !address_effect.valid || !address_effect.write_effect || address_effect.known_mask[15:8] == 8'hff)
    `N2M_ASSERT(CPU_IDU_KNOWN_PAGE, clk_sys, reset_sys || core_reset,
        !execute_result.address_effect.valid || !execute_result.address_effect.write_effect ||
        execute_result.address_effect.known_mask[15:8] == 8'hff)
    `N2M_ASSERT(CPU_IDU_MASKED_BITS, clk_sys, reset_sys || core_reset,
        (execute_result.address_effect.address & ~execute_result.address_effect.known_mask) == 0)
    `N2M_ASSERT(CPU_F_LOW_ZERO, clk_sys, reset_sys || core_reset, registers.f[3:0] == 0)
endmodule
