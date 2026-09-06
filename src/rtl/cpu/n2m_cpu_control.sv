`default_nettype none
`include "src/rtl/common/macros.svh"

// Pipeline and architectural state. The separate power-policy owner supplies
// STOP's model-dependent decision; this internal interface is not a host ABI.
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
    input var logic [7:0] buttons,
    input var logic [7:0] read_data,
    input var logic response_valid,
    input var logic [1:0] stop_action,
    input var logic stop_padding,
    input var logic wake_request,
    output logic request_valid,
    output logic [15:0] address,
    output logic [7:0] write_data,
    output logic write_enable,
    output n2m_cpu_pkg::access_kind_t access_kind,
    output logic bus_commit,
    output logic [4:0] irq_ack,
    output logic halted,
    output logic stopped,
    output logic locked,
    output logic initialized,
    output logic fault,
    output logic ime_observe,
    output logic ime_delay_observe,
    output logic stop_execute,
    output logic retirement_valid,
    output n2m_interfaces_pkg::retirement_t retirement
);
    import n2m_cpu_pkg::*;
    import n2m_interfaces_pkg::*;

    cpu_control_t control;
    cpu_control_t control_next;
    cpu_registers_t registers;
    cpu_registers_t registers_next;
    cpu_registers_t execute_registers;
    logic [15:0] execute_pc;
    logic [15:0] execute_temporary;
    logic [15:0] execute_address;
    logic [7:0] execute_write_data;
    logic execute_write;
    access_kind_t execute_kind;
    logic execute_finish;
    logic execute_prefix;
    logic execute_halt;
    logic execute_stop;
    logic execute_illegal;
    logic execute_ei;
    logic execute_di;
    logic execute_reti;
    logic active;
    logic [1:0] phase;
    logic [15:0] plan_address;
    logic [7:0] plan_write_data;
    logic plan_write;
    access_kind_t plan_kind;
    logic cycle_end;
    logic bus_fault;
    logic event_valid;
    logic event_interrupt;
    logic [15:0] event_pc_before;
    logic [15:0] event_pc_after;
    logic [23:0] event_fetched;
    logic [1:0] event_length;
    logic event_halted;
    logic event_stopped;
    logic [4:0] dispatch;
    logic [4:0] selected_irq;
    logic [15:0] selected_vector;
    logic pending_irq;

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

    assign fault = bus_fault || control.profile_fault;
    assign initialized = control.initialized;
    assign active = initialized && !fault && (control.mode == MODE_FETCH || control.mode == MODE_EXECUTE || control.mode == MODE_INTERRUPT);
    assign halted = control.mode == MODE_HALT;
    assign stopped = control.mode == MODE_STOP;
    assign locked = control.mode == MODE_LOCK;
    assign ime_observe = control.ime;
    assign ime_delay_observe = control.ime_delay;
    assign pending_irq = |control.irq_snapshot;
    assign dispatch = control.irq_snapshot;
    assign stop_execute = control.mode == MODE_EXECUTE && execute_stop && cycle_end;

    cpu_address_effect_t execute_address_effect;

    n2m_cpu_execute execute (
        .registers(registers), .opcode(control.opcode), .cb_bank(control.cb_bank),
        .step(control.step), .pc(control.pc), .temporary(control.temporary),
        .data_in(read_data), .registers_next(execute_registers), .pc_next(execute_pc),
        .temporary_next(execute_temporary), .address(execute_address),
        .write_data(execute_write_data), .write_enable(execute_write),
        .access_kind(execute_kind), .finish(execute_finish), .prefix(execute_prefix),
        .halt_request(execute_halt), .stop_request(execute_stop), .illegal(execute_illegal),
        .enable_interrupts(execute_ei), .disable_interrupts(execute_di),
        .return_interrupt(execute_reti), .address_effect(execute_address_effect)
    );

    always_comb begin
        plan_address = control.pc;
        plan_write_data = 0;
        plan_write = 0;
        plan_kind = ACCESS_IDLE;
        if (control.mode == MODE_FETCH) plan_kind = ACCESS_OPCODE;
        else if (control.mode == MODE_EXECUTE) begin
            plan_address = execute_address;
            plan_write_data = execute_write_data;
            plan_write = execute_write;
            plan_kind = execute_kind;
        end else if (control.mode == MODE_INTERRUPT) begin
            if (control.step == 2 || control.step == 3) begin
                plan_address = registers.sp;
                plan_write = 1;
                plan_write_data = control.step == 2 ? control.irq_pc[15:8] : control.irq_pc[7:0];
                plan_kind = ACCESS_STACK;
            end else if (control.step == 4) plan_kind = ACCESS_OPCODE;
        end
    end

    n2m_cpu_bus bus (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset),
        .gb_tick(gb_tick), .active(active), .plan_address(plan_address),
        .plan_write_data(plan_write_data), .plan_write(plan_write), .plan_kind(plan_kind),
        .response_valid(response_valid), .phase(phase), .request_valid(request_valid),
        .address(address), .write_data(write_data), .write_enable(write_enable),
        .access_kind(access_kind), .commit(bus_commit), .cycle_end(cycle_end), .fault(bus_fault)
    );

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
        event_valid = 0;
        event_interrupt = 0;
        event_pc_before = control.instruction_pc;
        event_pc_after = control.pc;
        event_fetched = control.fetched;
        event_length = control.length;
        event_halted = halted;
        event_stopped = stopped;
        irq_ack = 0;
        // PHI closes the enabled-request latch at T3 rising. Recognition and
        // low-stack vector selection consume this frozen M-cycle snapshot.
        if (gb_tick && phase == 2) control_next.irq_snapshot = ie[4:0] & iflags;
        // Inactive wake is accepted only at a complete M-cycle boundary.
        if (control.mode == MODE_HALT && pending_irq && gb_tick && phase == 3) begin
            control_next.mode = control.ime ? MODE_INTERRUPT : MODE_FETCH;
            control_next.step = 0;
            control_next.irq_pc = control.pc;
        end
        if (control.mode == MODE_STOP && wake_request && phase == 0)
            control_next.mode = MODE_FETCH;
        if (cycle_end) begin
            case (control.mode)
                MODE_FETCH: begin
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
                    registers_next = execute_registers;
                    control_next.pc = execute_pc;
                    control_next.temporary = execute_temporary;
                    control_next.step = control.step + 3'd1;
                    if (execute_kind == ACCESS_OPERAND) begin
                        case (control.length)
                            1: control_next.fetched[15:8] = read_data;
                            2: control_next.fetched[23:16] = read_data;
                            default: begin end
                        endcase
                        control_next.length = control.length + 2'd1;
                    end
                    if (execute_prefix) begin
                        control_next.opcode = read_data;
                        control_next.cb_bank = 1;
                        control_next.step = 0;
                    end
                    if (execute_illegal) control_next.mode = MODE_LOCK;
                    if (execute_finish) begin
                        event_valid = 1;
                        event_pc_after = execute_pc;
                        control_next.step = 0;
                        control_next.cb_bank = 0;
                        control_next.ime = control.ime || control.ime_delay || execute_reti;
                        control_next.ime_delay = 0;
                        if (execute_di) control_next.ime = 0;
                        else if (execute_ei && !control_next.ime) control_next.ime_delay = 1;
                        control_next.opcode = read_data;
                        control_next.fetched = {16'b0, read_data};
                        control_next.length = 1;
                        control_next.instruction_pc = execute_pc;
                        control_next.pc = execute_pc + 16'd1;
                        control_next.halt_bug = 0;
                        if (execute_halt) begin
                            control_next.pc = execute_pc;
                            if (pending_irq) begin
                                if (control_next.ime) begin
                                    // A request recognized while HALT executes
                                    // with IME set returns to this HALT. This also
                                    // covers delayed EI maturation; late arrivals
                                    // after the T3 snapshot instead enter sleep.
                                    event_pc_after = control.instruction_pc;
                                    control_next.pc = control.instruction_pc + 16'd1;
                                end else control_next.halt_bug = 1;
                            end else begin
                                control_next.mode = MODE_HALT;
                                event_halted = 1;
                            end
                        end
                        if (execute_stop) begin
                            if (stop_padding) begin
                                event_fetched[15:8] = read_data;
                                event_length = 2;
                                event_pc_after = execute_pc + 16'd1;
                            end
                            if (stop_action != 0) begin
                                control_next.pc = event_pc_after;
                                control_next.mode = stop_action == 1 ? MODE_HALT : MODE_STOP;
                                event_halted = stop_action == 1;
                                event_stopped = stop_action == 2;
                            end
                        end
                        if (control_next.ime && pending_irq && !event_stopped) begin
                            control_next.mode = MODE_INTERRUPT;
                            control_next.irq_pc = event_pc_after;
                            event_halted = 0;
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
                        event_valid = 1;
                        event_interrupt = 1;
                        event_pc_before = control.irq_pc;
                        event_pc_after = control.pc;
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
            event_valid = 0;
            irq_ack = 0;
        end
    end

    `DFF_ARST_VAL(control, control_next, clk_sys, reset_sys, profile_control())
    `DFF_ARST_VAL(registers, registers_next, clk_sys, reset_sys, profile_registers())

    n2m_cpu_retire observer (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset),
        .event_valid(event_valid), .event_interrupt(event_interrupt),
        .registers_after(registers_next), .pc_before(event_pc_before), .pc_after(event_pc_after),
        .fetched_bytes(event_fetched), .fetched_length(event_length),
        .ime_after(control_next.ime), .ime_delay_after(control_next.ime_delay),
        .halted_after(event_halted), .stopped_after(event_stopped), .halt_bug_after(control_next.halt_bug),
        .epoch(epoch), .dot_after(dot_before + 64'd1), .ie(ie), .iflags(iflags), .buttons(buttons),
        .retirement_valid(retirement_valid), .retirement(retirement)
    );

    `N2M_ASSERT(CPU_PROFILE_ID, clk_sys, reset_sys,
        core_reset |-> profile_id == PROFILE_DIRECT_ID)
    `N2M_ASSERT(CPU_IRQ_ACK_ONEHOT, clk_sys, reset_sys || core_reset, $onehot0(irq_ack))
    `N2M_ASSERT(CPU_IDU_KNOWN_PAGE, clk_sys, reset_sys || core_reset,
        !execute_address_effect.valid || !execute_address_effect.write_effect ||
        execute_address_effect.known_mask[15:8] == 8'hff)
    `N2M_ASSERT(CPU_IDU_MASKED_BITS, clk_sys, reset_sys || core_reset,
        (execute_address_effect.address & ~execute_address_effect.known_mask) == 0)
    `N2M_ASSERT(CPU_F_LOW_ZERO, clk_sys, reset_sys || core_reset, registers.f[3:0] == 0)
endmodule
