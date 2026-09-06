# Immutable source-frame snapshots

Planned implementation under [#93](https://github.com/amichai-bd/nand2mario/issues/93).
The [shared snapshot contract](../interfaces/MAS_interfaces.md#immutable-frame-snapshot)
owns byte order, immutable readback, reset persistence and the permitted
convenience-frame omission during copy. The [Intel memory boundary](../common/MAS_memory_primitives.md)
owns primitive parameters and read timing. UART framing remains its own owner.

## Boundary

All signals use clk_sys. Global reset reset_sys invalidates all state and masks
accesses. Core reset clears only assembly/latest availability and cancels an
unpublished copy; the published host snapshot and reads survive.

The producer inputs are the existing frame bridge observe_valid, observe_complete,
observe_abort, observe_index, observe_shade, observe_epoch, observe_sequence and
observe_dot. This is a tap of the every-frame observer, with no feedback to VGA,
the producer or emulated time. The index is sequential 0 through23039. Abort
wins over pixels and completion and drops only unpublished partial assembly.

| Host signal | Meaning |
|---|---|
| snapshot_request / snapshot_ready | The caller holds request until ready; one request is accepted at that edge; at most one copy is outstanding. |
| snapshot_done / snapshot_ok | One-edge completion. Success publishes the new host bank and metadata. Failure means NO_FRAME or core-reset cancellation and preserves the old host snapshot. |
| snapshot_valid / snapshot_metadata | Published validity and generated snapshot_t, including size5760. Metadata changes only on successful completion or global reset. |
| frame_read / frame_address[12:0] | Byte request from the published host snapshot. The caller requires snapshot_valid and address less than5760. |
| frame_valid / frame_data[7:0] | After the request edge, data is available with valid. No additional output stage. The bank is the pre-edge published bank even on replacement publication. |

A request with no current-epoch complete frame completes unsuccessfully, without
starting memory reads. If a completion and snapshot request share an edge, the
request uses the previously published latest frame. Core reset wins over copy
completion and new acquisition. An outstanding copy canceled by core reset emits
one done/ok0 response, including when reset remains asserted for several edges.
Global reset discards transport completion along with all validity.

## Storage and ownership

Four explicit single-clock 5760x8 Intel stores hold two assembly/latest banks and
two host banks. Four shades pack into each byte with the earliest pixel in bits1:0.
Only the assembly bank receives producer writes. Final-byte storage and latest
publication occur on the same edge. A snapshot copies the pre-edge latest bank
and pins it until completion or cancellation. While pinned, assembly may finish
but cannot replace that latest bank; such convenience completions are omitted.
Every-frame observation upstream remains intact. Subsequent full frames remain
eligible once copying ends; partial data is never published.

The copy reads the pinned bank through port B and writes the unpublished host
bank through port A on the following system edge. Copy indexes and valid travel
with the primitive response. The final host write atomically selects that host
bank and its captured metadata. The prior host bank supports delayed reads during
copy. A read on publication captures the old bank selection with its request;
later requests see the new bank. There is no active read/write cross-port collision.

Core reset cancels outstanding copy requests/writes and invalidates assembly and
latest metadata. It does not reset the host primitive, published metadata or a
host read response. Global reset masks requests and invalidates metadata without
clearing primitive arrays. No read can expose uninitialized storage.

## Verification and implementation status

RTL and actual runtime evidence remain pending. Independent fixtures must check
all bytes from original source patterns, delayed reads during new frames, no-frame
preservation, replacement and reset edges, abort, concurrent real VGA ownership
and every-frame observation. Actual DUT overwrite and response-latency mutations
must fail, as must a named ownership assertion. An early constrained MAX10 fit
must account for all four real Intel stores and their ports before extensive
fixture execution. Primitive arrays are never initialized or inspected privately.
