# Software toolchain

The [PRD](PRD.md) owns scope, implementation status, and release acceptance.

## Implemented oracle

`python tools/build.py sw oracle --tag <tag> --json` provisions the pinned
unmodified upstream RGBASM/RGBLINK prebuilt release for Windows or Linux x86_64
and checks the original fixture in `src/sw/oracle/`. Add `--offline` to forbid
downloads and require the same tag's verified cached inputs. Other host platforms
and arbitrary installed executables are unsupported. This command does not
implement the planned project assembler, linker or cartridge packager below.

The [manifest](../../../tools/n2m/dependencies.json) owns the source/version,
archive and notice hashes. The [provenance](../../../tools/sw/THIRD_PARTY.md)
records license and upstream prebuilt installation limits. Provisioning checks
all downloaded hashes before use, and compares installed executable bytes with
the verified archive on every call. A corrupt archive, notice or executable,
missing previously installed tool, unavailable download or wrong reported
version fails. Online mode does not silently repair corruption. Choose a fresh
tag after inspecting a failed cache; offline cache misses fail without fetching.

The builder's exclusive tag lock protects installation. The cache lives at
`workdir/builds/<tag>/sw/oracle/cache/`; every invocation creates an immutable
`runs/<id>/` containing exact commands, raw exit results, logs, object files,
linked bytes, map, symbols, copied expectations, a complete cache snapshot and a
hashed result. Immutable artifact hashes name the snapshot, so a later cache or
pin failure cannot invalidate earlier attempt evidence. The stage
`result.json` and builder manifest point to the latest attempt. Reusing a tag
verifies the cache and reruns the oracle; it never reuses a previous PASS result.
Each executable call has a 60-second timeout. Nonzero exits, warnings and timeouts
fail and retain available diagnostics. No tool invocation uses a shell.

The two original assembly files exercise immediate and CB-prefixed encoding,
relative branching, fixed section placement, cross-object CALL relocation and
LOW(symbol). RGBASM owns encoding and RGBLINK owns relocation. The checker uses
independently authored literal region bytes, total size, fill byte and selected
symbol addresses from `expected.json`; it compares the whole output, including
padding. It does not read project opcode tables, encode instructions or resolve
relocations. These samples establish the oracle path, not exhaustive instruction
or CPU coverage. #85 owns exhaustive assembler conformance.

`--expected <file>` selects an explicit expectation JSON for independent and
negative checks. Changing an expected byte must return failure with the offset
and expected/actual bytes. It does not alter assembly or link inputs. The fixture
runs at `$0200` and contains no Nintendo logo or borrowed program content.

Host tests cover cache hits/misses, corrupted downloads/notices/executables,
missing tools, wrong versions, timeout/raw failure, byte/symbol mismatches and
space-containing paths. Retained actual upstream runs prove positive and changed
expectation outcomes; hosted Builder CI also runs the actual pinned Linux oracle.
The source and cache hashes connect this evidence to the reviewed implementation.

## Inputs and ownership

Plan `python tools/build.py sw build <target> --tag <tag> --json` using the
[builder's](../n2m/SPEC.md) workspace, locking, failure, and cache rules.
Target definitions beside original sources under `src/sw/` name an ordered
assembly-input list, declared assets, link layout, entry symbol, title, version
byte, and profile `dmg-direct-v1`. Implementation must commit a versioned target
schema before execution. Paths are target-relative; reject absolute paths,
parent traversal, symlink escapes, duplicate resolved sources and output overlap.

Hardware registers, memory regions, vectors, runtime reset/entry state and host
constants come from generated exports of
[#30](https://github.com/amichai-bd/nand2mario/issues/30). Import its assembly
constants as explicit fingerprinted inputs. This page owns cartridge file
construction, not a duplicate hardware address map. Privately selected ROMs are
runtime inputs under the [source policy](../provenance.md), never assembly assets.
The builder supplies #30's canonical generated assembly prelude as a separately
allowlisted input before target sources, even when its path is outside the target
tree. Targets select its schema/profile identity, not an arbitrary external path.
Normal `INCLUDE` confinement still applies; do not copy generated constants into
each target to bypass it. Prelude definitions cannot be redefined by a target.

## Assembly language

Use UTF-8 without BOM, LF or CRLF. Identifiers are case-sensitive ASCII
`[A-Za-z_][A-Za-z0-9_]*`. Mnemonics, registers and directives are case-insensitive
reserved words. A semicolon starts a comment outside strings. One statement per
line; a `name:` label may precede it. Blank lines are allowed. Strings appear in
quoted names/paths and `DB`; escapes are `\\`, `\"`, `\n`, `\r`, `\t`, `\xHH`.
`DB` strings must decode to ASCII bytes; other characters or invalid escapes fail.

Support every documented original SM83 encoding, including all CB forms, using
the pinned [instruction reference][isa]. Require explicit accumulator operands
for `ADD`, `ADC`, `SUB`, `SBC`, `AND`, `OR`, `XOR`, `CP`; use `JP HL` and
`[HL+]`/`[HL-]`. `CPL`, `DAA` and accumulator rotates are operandless. `STOP`
is operandless and emits its zero padding byte. Reject omitted-accumulator and
`[HLI]`/`[HLD]` aliases, undocumented/Z80 instructions, invalid operands and
automatic jump expansion. `LDH` immediates are full high-memory addresses,
validated against #30's generated region, not truncated offsets.

Literals are decimal, `$` hex, or `%` binary, without separators. Parentheses
group expressions. Precedence, strongest first: unary `+ - ~`, `* /`, binary
`+ -`, `<< >>`, `&`, `^`, `|`; binary operators associate left. Use exact integers,
division truncated toward zero and arithmetic right shift. Division by zero
and shift counts outside 0..63 fail. `@` means the current statement address.
`LOW(expr)`/`HIGH(expr)` accept 0..65535 and extract bytes; no silent truncation.

Raw byte data/immediates accept -128..255; word data and non-address 16-bit
immediates accept -32768..65535. Encode modulo
width only after checking. Address operands require 0..65535; signed instruction
offsets require -128..127; bit indices require 0..7 and restart vectors must be
legal SM83 vectors. `JR target` always names an address: displacement is
`target - (instruction_address + 2)`, checked at link time without wraparound.

| Statement | Rule |
|---|---|
| `SECTION "name", ROM` | Begin a unique relocatable byte section |
| `SECTION "name", RAM` | Begin a unique allocation-only section |
| `name EQU expr` | Immutable symbol; forward references allowed, cycles fail |
| `EXPORT name` / `IMPORT name` | Publish a definition / declare an external reference |
| `DB item,...` / `DW expr,...` | ROM bytes/strings or little-endian words |
| `DS count` | RAM allocation; assembly-time nonnegative integer count |
| `INCLUDE "path"` | Text relative to including file, confined to target tree |
| `ASSET "name"` | Insert a declared generated asset's bytes into ROM |

Emission/allocation needs a section. RAM forbids emitted bytes/instructions;
ROM forbids `DS`. Empty sections own no bytes. Reopening sections fails.
Include cycles fail with the chain; repeated noncyclic includes repeat text.
No macros, conditional assembly, mutable symbols, implicit globals, binary
inclusion, relaxation, or general RGBDS source compatibility is promised.

## Objects and linking

Emit a versioned UTF-8 JSON object per translation unit: source hashes, ordered
sections with bytes/RAM size, definitions/exports/imports, expression trees,
relocations with kind/section/offset/range, and source spans. Byte arrays contain
integers 0..255. Commit exact object/layout schemas and fixtures before shipping
their producer and consumer. Reject unknown schema versions/fields, invalid
offsets, overlapping relocations, inconsistent lengths and missing sections.
Never evaluate serialized expressions as Python code.

Relocations are `U8`, `U16LE`, `ADDR16LE`, `REL8`, `HIGH8`, `LOW8`, with the range
rules above; signed immediates carry signed ranges. Bit/vector/LDH constraints
survive unresolved expressions. Resolve labels after placement. Unknown,
ambiguous, cyclic or unimported cross-unit references fail. Every import must
resolve; exports are globally unique, other symbols remain unit-local.

Layout assigns every section to a generated #30 region and fixed address or
floating placement with power-of-two alignment (default 1). Fixed addresses
must satisfy alignment. Place fixed sections first, then floating sections in
target-input and declaration order at the lowest aligned free address. Reject
duplicate/unassigned sections, overlap, absent regions, exhaustion, overflow
and boundary crossing. RAM allocations emit no ROM bytes or initialization.

The profile contains two contiguous 16 KiB ROM banks, no mapper/cartridge RAM.
Require #30's CPU-to-file mapping to match that size and contiguity. Sections
cannot straddle banks. Reserve the header and generated interrupt/restart
vectors before placement; only explicitly named vector sections may occupy
vector reservations. The packager alone owns the header and entry stub.
Unfilled ROM bytes are `$FF`; program instructions initialize RAM.

Diagnostics carry stable code/stage, target-relative file, one-based line/column,
cause and affected symbol/section. Include stacks and both duplicate definition
sites. Distinguish syntax, unsupported instruction, range, undefined/cyclic
symbol, overlap/exhaustion, malformed object, schema mismatch and private-path
errors. Sort by input order/span. Failure exits 1, preserves logs, and publishes
no new successful ROM or latest pointer; stale successful outputs are invalid
for the failed request and must not be returned as its result.

## Packaging and entry

Use the pinned [cartridge file format][header]. The packager owns offsets
`$0100..$014F`: the four-byte entry is NOP then JP to the explicit entry symbol
at an emitted instruction boundary in a ROM section outside reservations.
No guessed entry default or entry into emitted data.

`dmg-direct-v1` deliberately zeroes the 48-byte logo field, copies no Nintendo
logo/boot asset and does not use Nintendo's stock boot ROM. #30 owns the explicit
CPU/peripheral reset state and direct-entry transition; the independent
reference starts from that identical state without preinitialized program
results. This is the original `v0.5` program's profile; it does not modify the
private `v0.9` image or its charter acceptance. Incompatible boot profiles fail.

Title is 1..15 uppercase ASCII letters/digits/spaces, zero-padded to 16 bytes.
New licensee bytes, SGB flag, cartridge type, ROM-size code, RAM-size code and
old licensee byte are zero; destination is 1; version is an explicit byte.
Reject incompatible metadata. Header checksum starts at zero: subtract each
byte of `$0134..$014C` and one modulo 256, store at `$014D`. Global checksum sums
all bytes except `$014E/$014F` modulo 65536 and is stored big-endian there.
Compute after placement/padding/header generation. Validate size, reservations,
metadata, checksums, entry and profile before publication. Never silently repair
user-supplied ROMs.

## Original assets

Accept UTF-8 JSON objects with exactly `schema_version: 1`, `width`, `height`,
and `pixels`: positive dimensions divisible by 8 and exactly height rows of
width integer shades 0..3. Reject booleans, floats, ragged rows, unknown fields
and undeclared assets. Record original authorship beside each declaration.
No PNG decoding, inferred palette or commercial image extraction is needed.

Emit tiles in row-major tile order, each 8 by 8. Each row emits low plane then
high plane; x=0 is bit 7. Preserve duplicates; no implicit flip, deduplication,
remap or alignment. Output size is `width * height / 4` bytes. Tilemaps and
palette programming are explicit program data/code using #30 exports.
An independent decoder must round-trip every emitted pixel to its input shade.

## Artifacts and independent conformance

Publish under the builder's tagged software directory: ROM, objects, versioned
JSON map/symbols/listing, diagnostics and stage records. Maps identify sections,
address ranges, source units and file offsets (null for RAM); symbols give
resolved value/address and visibility; listings give source span, final address,
bytes and relocation disposition. Sort maps by address/name, symbols by qualified
name; retain listing source order. JSON has sorted keys, two-space indent, LF
and a final newline. The exact schemas ship with their owning implementation.

ROM/object/map/symbol/listing bytes must match across fresh tags and checkout
paths: target-relative paths only, no timestamps/random values/host text.
Separate stage records retain commit, actual tool versions, hashes and commands.
Fingerprint all source/include/asset/layout/generated #30 inputs, schemas,
implementation and options; validate output hashes before cache reuse. Changed
includes, corrupt objects, stale headers and missing ROMs must rebuild or fail.

The [dependency manifest](../../../tools/n2m/dependencies.json) pins the external
RGBASM/RGBLINK oracle; [provenance](../../../tools/sw/THIRD_PARTY.md) records permitted
use. Independently authored instruction fixtures feed both toolchains; compare
linked bytes and selected symbols before packaging. The oracle adapter may only
normalize the explicit spelling choices above and translate section placement;
it must not use our opcode tables or resolve relocations for the oracle. Missing
or mismatched oracle fails conformance. Compare packaging with a separate
checksum/header implementation, without RGBFIX logo insertion.

Cover every legal opcode form, register/condition/CB combination and numeric
endpoints; signed limits and rejected neighbors; forward/cross-unit symbols;
branches at placement boundaries; forbidden forms, cycles, overlap, overflow,
malformed objects and corrupt caches. Deliberate encoding/relocation/checksum
mutations must fail for their expected diagnostic. Track every unimplemented
form; a subset pass or ROM hash alone proves neither full conformance nor CPU
semantics. The original program must then pass all charter run/pixel/retirement/
input checks with our build, including identical clean-build bytes.

Loading consumes immutable ROM/manifest, validates profile/length and follows
#30's versioned load/readback/start protocol without editing the image. Transport
retries/device selection belong to the host contract; software build opens no
device. Full load/readback and runtime validation remain required end-to-end
evidence. Physical transmission follows the
[current authorization](../../agents/bootstrap-plan.md#verification-and-hardware-authorization).

## Delivery order

Implementation issues below own executable schemas/tools/tests. The spec leads
implementation until they close. C-like compilation, mapper breadth, commercial
assets and physical loader execution remain outside this contract.

1. [Oracle provisioning #84](https://github.com/amichai-bd/nand2mario/issues/84)
   establishes independent executable evidence.
2. [Assembler #85](https://github.com/amichai-bd/nand2mario/issues/85) owns complete
   forms and object schema; uses #84 and generated #30 constants.
3. [Linker/packager #86](https://github.com/amichai-bd/nand2mario/issues/86) uses
   #85/#30 and owns layout, final artifacts and software stage integration.
4. [Assets #87](https://github.com/amichai-bd/nand2mario/issues/87) integrates with
   the #85/#86 software interface and can prepare independent fixtures earlier.
5. [Original program #88](https://github.com/amichai-bd/nand2mario/issues/88)
   consumes these tools and the required hardware/loader/verification deliveries
   to prove the full `v0.5` acceptance. Root schedules those dependencies.

[isa]: https://github.com/gbdev/rgbds/blob/307846b03ea89ee57bf75f179d5f8051175ac60d/man/gbz80.7
[header]: https://github.com/gbdev/pandocs/blob/fe246067b695b5404a4a6a47efb4fd6d921ececb/src/The_Cartridge_Header.md
