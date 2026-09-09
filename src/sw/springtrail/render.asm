; Write one entering world column and one 8x16 courier during VBlank.
SECTION "render",ROM
RenderPlayer:
LD A,[Camera]
LD L,A
LD A,[Camera+1]
LD H,A
SRL H
RR L
SRL H
RR L
SRL H
RR L
LD A,[OldCameraTile]
CP A,L
JR Z,ScrollRegister
LD B,A
LD A,L
LD [OldCameraTile],A
CP A,B
JR C,EnteringColumn
ADD A,20
EnteringColumn:
CP A,96
JR NC,ScrollRegister
LD [Column],A
LD L,A
LD H,0
LD DE,WorldMap
ADD HL,DE
LD A,[Column]
AND A,31
LD E,A
LD D,$98
LD B,18
ColumnLoop:
LD A,[HL]
LD [DE],A
; Stride the literal row-major map without repeating collision lookup work.
LD A,B
LD BC,96
ADD HL,BC
LD B,A
LD A,E
ADD A,32
LD E,A
JR NC,ColumnNext
INC D
ColumnNext:
DEC B
JR NZ,ColumnLoop
ScrollRegister:
LD A,[Camera]
LDH [$FF43],A
LD A,[Fell]
OR A,A
JR NZ,HidePlayer
LD A,[PlayerY]
LD L,A
LD A,[PlayerY+1]
LD H,A
CALL PixelFloor
LD A,L
ADD A,16
LD [$FE00],A
JR PlayerHorizontal
HidePlayer:
XOR A,A
LD [$FE00],A
PlayerHorizontal:
LD A,[PlayerX]
LD L,A
LD A,[PlayerX+1]
LD H,A
CALL PixelFloor
LD A,[Camera]
LD E,A
LD A,[Camera+1]
LD D,A
LD A,L
SUB A,E
LD L,A
LD A,H
SBC A,D
LD H,A
LD A,L
ADD A,8
LD [$FE01],A
LD A,12
LD [$FE02],A
XOR A,A
LD [$FE03],A
RET

ReadButtons:
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
LD [Buttons],A
RET
