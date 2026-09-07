; Original v0.5 program. Each input bit controls one tile at map row eight.
SECTION "code",ROM
Start:
DI
LD SP,$DFFE
XOR A,A
LDH [$FF40],A
LDH [$FF0F],A
LD [$FFFF],A
LDH [$FF42],A
LDH [$FF43],A
LD HL,$9800
LD BC,$0400
ClearMap:
XOR A,A
LD [HL+],A
DEC BC
LD A,B
OR A,C
JR NZ,ClearMap
LD HL,$8000
LD B,$10
ClearTile:
XOR A,A
LD [HL+],A
DEC B
JR NZ,ClearTile
LD B,$08
MarkedTile:
LD A,$FF
LD [HL+],A
XOR A,A
LD [HL+],A
DEC B
JR NZ,MarkedTile
LD A,$01
LD [$9800],A
LD [$FFFF],A
LD A,$E4
LDH [$FF47],A
LD A,$91
LDH [$FF40],A
Sleep:
XOR A,A
LDH [$FF0F],A
HALT
; IME stays clear: VBlank wakes HALT without an interrupt stack transaction.
LD A,$20
LDH [$FF00],A
LDH A,[$FF00]
CPL
AND A,$0F
LD B,A
LD A,$10
LDH [$FF00],A
LDH A,[$FF00]
CPL
AND A,$0F
SWAP A
OR A,B
LD C,A
LD HL,$9900
LD B,$08
Cells:
LD E,A
AND A,$01
LD [HL+],A
LD A,E
RRCA
DEC B
JR NZ,Cells
JR Sleep
EXPORT Start
