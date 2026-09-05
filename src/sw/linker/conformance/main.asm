; Original relocation fixture: independent of opcode tables and linker output.
IMPORT Partner
IMPORT ByteLow
IMPORT ByteHigh
IMPORT WordLow
IMPORT WordHigh
IMPORT HighMem
IMPORT BitZero
IMPORT BitSeven
IMPORT VectorFirst
IMPORT VectorLast
IMPORT TargetForward
IMPORT TargetBackward
SECTION "code", ROM
Start: LD A,ByteLow
LD B,ByteHigh
LD BC,WordLow
LD DE,WordHigh
LDH A,[HighMem]
BIT BitSeven,A
RES BitZero,B
RST VectorFirst
RST VectorLast
DW Partner
DB LOW(Partner),HIGH(Partner)
CALL Partner
EXPORT Start
SECTION "forward", ROM
BranchForward: JR TargetForward
EXPORT BranchForward
SECTION "backward", ROM
BranchBackward: JR TargetBackward
EXPORT BranchBackward
SECTION "work", RAM
RamBuffer: DS 16
EXPORT RamBuffer
