INCLUDE "state.asm"
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
LD HL,$C000
LD BC,$0300
ClearMemory:
LD [HL+],A
DEC BC
LD A,B
OR A,C
JR Z,MemoryReady
XOR A,A
JR ClearMemory
MemoryReady:
LD DE,Tiles
LD HL,$8000
LD BC,320
CopyTiles:
LD A,[DE]
INC DE
LD [HL+],A
DEC BC
LD A,B
OR A,C
JR NZ,CopyTiles
LD DE,Map
LD HL,$9800
LD BC,1024
CopyMap:
LD A,[DE]
INC DE
LD [HL+],A
DEC BC
LD A,B
OR A,C
JR NZ,CopyMap
CALL Prepare
CALL Render
LD A,$E4
LDH [$FF47],A
LD A,1
LD [$FFFF],A
LD A,$91
LDH [$FF40],A
Frame:
XOR A,A
LDH [$FF0F],A
HALT
CALL ReadButtons
CALL Render
CALL Update
CALL Prepare
JR Frame
EXPORT Start
INCLUDE "rules.asm"
INCLUDE "render.asm"
INCLUDE "tables.asm"

