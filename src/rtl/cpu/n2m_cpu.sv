`default_nettype none
`include "src/rtl/common/macros.svh"

// CPU composition boundary. The approved DMG STOP entry is implemented;
// oscillator wake retains its explicit unresolved policy seam.
module n2m_cpu (
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
    input var logic joyp_selected_active,
    // Qualified stable-clock restart pulse from the power owner, before T1.
    input var logic wake_request,
    output logic request_valid,
    output logic [15:0] address,
    output logic [7:0] write_data,
    output logic write_enable,
    output n2m_cpu_pkg::access_kind_t access_kind,
    output logic bus_commit,
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
    output logic stop_execute,
    output logic divider_reset_request,
    output logic instruction_complete,
    output logic retirement_valid,
    output n2m_interfaces_pkg::retirement_t retirement
);
    n2m_cpu_pkg::cpu_execute_request_t execute_request;
    n2m_cpu_pkg::cpu_execute_result_t execute_result;
    n2m_cpu_pkg::cpu_bus_plan_t bus_plan;
    n2m_cpu_pkg::cpu_retire_capture_t retire_capture;
    n2m_cpu_pkg::cpu_stop_action_t stop_action;
    logic stop_padding;
    logic active;
    logic complete_enable;
    logic pending_irq;
    logic [1:0] phase;
    logic cycle_end;
    logic bus_fault;

    // Pre-A completion lets STEP stop this T enable; B still publishes the
    // complete retirement record while the timebase is paused.
    assign instruction_complete = retire_capture.valid && !retire_capture.is_interrupt &&
        initialized && !fault && !reset_sys && !core_reset;

    n2m_cpu_control u_control (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset), .gb_tick(gb_tick),
        .profile_id(profile_id), .epoch(epoch), .dot_before(dot_before), .ie(ie), .iflags(iflags),
        .read_data(read_data), .joyp_selected_active(joyp_selected_active), .wake_request(wake_request),
        .phase(phase), .cycle_end(cycle_end), .bus_fault(bus_fault), .execute_result(execute_result),
        .stop_action(stop_action), .stop_padding(stop_padding), .divider_reset_request(divider_reset_request),
        .execute_request(execute_request), .bus_plan(bus_plan), .retire_capture(retire_capture),
        .active(active), .complete_enable(complete_enable), .pending_irq(pending_irq),
        .address_effect(address_effect), .address_effect_resolved(address_effect_resolved),
        .address_effect_sample(address_effect_sample), .address_effect_phase(address_effect_phase),
        .irq_ack(irq_ack), .halted(halted), .stopped(stopped), .locked(locked), .initialized(initialized),
        .fault(fault), .ime_observe(ime_observe), .ime_delay_observe(ime_delay_observe), .stop_execute(stop_execute)
    );

    n2m_cpu_execute u_execute (.request(execute_request), .result(execute_result));

    n2m_cpu_bus u_bus (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset), .gb_tick(gb_tick),
        .active(active), .complete_enable(complete_enable), .plan(bus_plan), .response_valid(response_valid),
        .phase(phase), .request_valid(request_valid), .address(address), .write_data(write_data),
        .write_enable(write_enable), .access_kind(access_kind), .commit(bus_commit),
        .cycle_end(cycle_end), .fault(bus_fault)
    );

    n2m_cpu_retire u_retire (
        .clk_sys(clk_sys), .reset_sys(reset_sys), .core_reset(core_reset), .capture(retire_capture),
        .ie(ie), .iflags(iflags), .buttons(buttons), .retirement_valid(retirement_valid), .retirement(retirement)
    );

    n2m_cpu_stop_policy u_stop_policy (
        .selected_active(joyp_selected_active), .enabled_pending(pending_irq), .execute(stop_execute),
        .action(stop_action), .padding(stop_padding), .divider_reset(divider_reset_request)
    );
endmodule
