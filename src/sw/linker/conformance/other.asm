; Original definitions and targets resolved independently by RGBLINK.
ByteLow EQU -128
ByteHigh EQU 255
WordLow EQU -32768
WordHigh EQU 65535
HighMem EQU $ff80
BitZero EQU 0
BitSeven EQU 7
VectorFirst EQU 0
VectorLast EQU 56
EXPORT ByteLow
EXPORT ByteHigh
EXPORT WordLow
EXPORT WordHigh
EXPORT HighMem
EXPORT BitZero
EXPORT BitSeven
EXPORT VectorFirst
EXPORT VectorLast
SECTION "other", ROM
Partner: RET
EXPORT Partner
SECTION "near", ROM
TargetForward: NOP
TargetBackward: NOP
EXPORT TargetForward
EXPORT TargetBackward
