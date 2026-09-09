# DMG joypad

Implementation: [JOYP owner](../../../../src/rtl/joypad/n2m_joypad.sv).
The matrix, register updates and selected-line event transport are implemented.
The independent test plan covers the agreed event and IF boundary.

## Authority

The [generated interface](../interfaces/MAS_interfaces.md) owns button bit values,
FF00 and direct-profile reset state. The [source record](references.md) separates
documented digital reads/events from physical filtering evidence. No external
RTL or emulator source is imported.

## Register and matrix

JOYP writes retain only bits5:4. Bits7:6 read high; bits3:0 are read-only.
The generated direct profile releases all eight buttons and writes select30,
so JOYP readsFF. These are direct-profile values, not boot-ROM defaults.

Host masks are active high: bits0..7 are Right, Left, Up, Down, A, B, Select,
Start. Read bits0..3 pair Right/A, Left/B, Up/Select and Down/Start.
A zero select bit enables its row: bit4 directions, bit5 actions. Both selected
rows combine pressed buttons; neither selected readsF. Preserve simultaneous
and opposite directions. Reading or writing ignored bits has no other effect.
The selected-active output is the reduction of these four active-low lines,
not a reduction of unselected physical buttons.

## Clock and update boundary

All digital state belongs to clk_sys. reset_sys asserts asynchronously; core
reset restores the generated profile and cancels request bookkeeping. A CPU
select write takes effect only on the existing committed T4 A edge. Reads are
side-effect free and provide the pre-edge value to prepared CPU service.

INPUT replaces all eight bits atomically. The host owner schedules it between
completed dots while running and immediately without a dot while paused. CPU
HALT/STOP does not prevent updates. Existing interface priority is reset, host
input latch, then emulated effects. This owner must not add a private input queue,
new host ABI or discarded update policy. `input_commit` accepts `input_buttons` at the system edge; it does not depend on
gb_tick or CPU mode. A coincident select write and INPUT atomically update their
separate fields, then the combinational matrix reflects both new values. Event
transport compares the old matrix with that final combined matrix.

## Interrupt and wake boundary

Pan Docs describes a request when any selected read bit changes high to low.
A release alone does not request; a held line does not repeat; a different row
button sharing an already low line does not create another falling edge.
Selecting a held button can produce a line fall. IE/IME do not mask the source.
The existing IF owner stores requests and owns write/ack collision priority.

The approved digital model detects each selected-line fall without an uncertain
physical filter delay. `request_event` registers the OR of those falls at the
update edge A and remains available through the following system edge B.
The IF owner consumes it on `source_event[4]`, with its JOYP `source_level[4]`
tied low. Adjacent high cycles are distinct accepted events, not a held level.
The IF owner applies its existing write/ack priority at B. Neither IE nor IME
filters this source. Reset cancels a pending event. No queue or ready handshake
is added, and physical switch filtering is not modeled.

CPU STOP entry consumes selected-active. The enclosing power owner retains an
eligible `request_event` and qualifies stable clocks before asserting
CPU wake_request. Raw button activity must not drive that qualified input.
The [approved CPU restart model](../cpu/MAS_cpu.md#qualified-stop-wake) uses
ordinary deterministic interrupt priority/stack behavior after qualification;
JOYP does not choose another restart policy or oscillator delay.

## Finite acceptance

The [test plan](../../../../src/dv/joypad/README.md) covers all256 masks x4 row
selections, all ignored write bits, reset, release/repress/held/simultaneous
changes, select changes, host pause and HALT/STOP updates. Directed phase tests
must verify actual IF storage and distinguish selected-active/raw event from
qualified CPU wake. Actual row, lost-event and duplicate-event faults and a
local named assertion must fail nonzero. Retain explicit public waves, source
pins, hashes, logs and literal expected/actual traces.

The event interface uses the approved IF A/B projection. It provides raw wake
intent, not oscillator qualification or a second CPU power policy.


`n2m_joypad` forwards exact-address selection and side-effect-free read data,
buttons_observe and selected_active. The memory owner forwards io_commit only
for this selected owner; an off-boundary commit is a named contract violation.
`joypad_state_t` owns the button byte and two writable select bits. Shared async
register macros apply global/core reset with immediate profile observation;
no IF state or qualified CPU wake output exists in this owner.
