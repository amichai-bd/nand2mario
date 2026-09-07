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
ObjectTile:
LD A,$FF
LD [HL+],A
XOR A,A
LD [HL+],A
DEC B
JR NZ,ObjectTile
LD A,$01
LD [$9908],A
LD A,$20
LDH [$FF00],A
LD A,$E4
LDH [$FF47],A
LD A,$91
LDH [$FF40],A
Poll:
LDH A,[$FF00]
AND A,$03
CP A,$02
JR Z,MoveRight
CP A,$01
JR Z,MoveLeft
LD A,$E4
LDH [$FF47],A
JR Poll
MoveRight:
LD A,$F8
LDH [$FF43],A
JR Pressed
MoveLeft:
XOR A,A
LDH [$FF43],A
Pressed:
LD A,$EC
LDH [$FF47],A
JR Poll
EXPORT Start
