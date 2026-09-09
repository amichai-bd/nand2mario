; Original Springtrail foundation. VBlank owns title-to-world VRAM changes.
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
LD [$C000],A
LD DE,Tiles
LD HL,$8000
LD BC,$0100
CopyTiles:
LD A,[DE]
INC DE
LD [HL+],A
DEC BC
LD A,B
OR A,C
JR NZ,CopyTiles
LD DE,TitleMap
LD HL,$9800
LD BC,$0240
CopyMap:
LD A,[DE]
INC DE
LD [HL+],A
DEC BC
LD A,B
OR A,C
JR NZ,CopyMap
LD A,$E4
LDH [$FF47],A
LD A,$01
LD [$FFFF],A
LD A,$91
LDH [$FF40],A
WaitFrame:
XOR A,A
LDH [$FF0F],A
HALT
LD A,$10
LDH [$FF00],A
LDH A,[$FF00]
AND A,$08
JR NZ,WaitFrame
LD A,[$C000]
OR A,A
JR NZ,WaitFrame
; Erase the two eleven-character title rows within this VBlank.
LD HL,$98A4
LD B,$0B
ClearName:
XOR A,A
LD [HL+],A
DEC B
JR NZ,ClearName
LD HL,$98E4
LD B,$0B
ClearPrompt:
XOR A,A
LD [HL+],A
DEC B
JR NZ,ClearPrompt
LD A,$01
LD [$C000],A
JR WaitFrame
EXPORT Start
SECTION "assets",ROM
Tiles:
ASSET "Tiles"
TitleMap:
INCLUDE "map.asm"
