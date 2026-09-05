# Frame bridge test plan

The [VGA MAS](../../../wiki/src/rtl/vga/MAS_vga.md) defines module ports and
links the authoritative geometry/ownership/reset contract. The original fixture
uses asymmetric shades computed from source epoch, sequence, row and column.
No ROM or external test assets are used.

The source driver provides complete frames and independently counts accepted
pixels. A passive observer checks every pixel, index, epoch, sequence and
completion before selection. The raster checker derives coordinates from elapsed
pixel edges and computes geometry and shade independently. A completed-frame
ledger rejects display of partial, nonexistent or modified frames. Separate
ownership assertions observe RAM write and mailbox state; they do not supply
the pixel oracle's expected values.

Required schedules: fast frames with pending-offer discards, slow frames with
repeated scanout, delayed acknowledgements from a stopped pixel clock, host pause,
partial-frame core reset, global reset with an outstanding offer, and raw lock
loss. Continue driving the source while presentation is stopped. Require nonzero
discard/repeat coverage, all three bank IDs and multiple complete raster frames.
Check asynchronous black/inactive output masking while the pixel clock is stopped.

Mutations force writer reuse of an immutable bank and a display bank change
during active video. Each must terminate with the corresponding ownership/swap
diagnostic and a nonzero Questa exit. A source protocol mutation checks partial
frame rejection. Watchdogs run from independent simulation time. Wave output is
bounded to control signals, without dumping complete RAM arrays.

Actual simulation, nominal/upper Quartus fit, RAM inference and bundle/output
timing records are pending. Physical monitor acceptance is outside #80.
