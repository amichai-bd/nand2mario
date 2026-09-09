SECTION "render",ROM
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

Prepare:
LD HL,Board
LD DE,Image
LD B,96
PrepareBoard:
LD A,[HL+]
ADD A,A
LD [DE],A
INC DE
DEC B
JR NZ,PrepareBoard
LD A,[Status]
CP A,1
JR NZ,PrepareNext
CALL Shape
LD D,H
LD E,L
LD A,4
LD [Saved],A
PrepareActive:
LD A,[DE]
INC DE
CALL Address
LD H,$C2
LD [HL],3
LD A,[Saved]
DEC A
LD [Saved],A
JR NZ,PrepareActive
PrepareNext:
LD HL,Image+96
LD B,16
XOR A,A
PreviewClear:
LD [HL+],A
DEC B
JR NZ,PreviewClear
; Look up the next shape's rotation-zero table without altering game state.
LD A,[Piece]
INC A
CP A,7
JR C,PreviewIndex
XOR A,A
PreviewIndex:
SWAP A
LD E,A
LD D,0
LD HL,Shapes
ADD HL,DE
LD D,H
LD E,L
LD B,4
PreviewCell:
LD A,[DE]
INC DE
LD C,A
AND A,$F0
SRL A
SRL A
LD L,A
LD A,C
AND A,$0F
ADD A,L
ADD A,96
LD L,A
LD H,$C2
LD [HL],3
DEC B
JR NZ,PreviewCell
LD HL,Score
LD DE,Image+112
LD B,4
PrepareScore:
LD A,[HL+]
ADD A,10
LD [DE],A
INC DE
DEC B
JR NZ,PrepareScore
LD A,[Status]
ADD A,4
LD [DE],A
INC DE
LD A,[Rotation]
ADD A,10
LD [DE],A
RET

; Eight writes per row are unrolled to leave time for JOYP and preview/HUD.
CopyEight:
LD A,[HL+]
LD [DE],A
INC DE
LD A,[HL+]
LD [DE],A
INC DE
LD A,[HL+]
LD [DE],A
INC DE
LD A,[HL+]
LD [DE],A
INC DE
CopyFour:
LD A,[HL+]
LD [DE],A
INC DE
LD A,[HL+]
LD [DE],A
INC DE
LD A,[HL+]
LD [DE],A
INC DE
LD A,[HL+]
LD [DE],A
INC DE
RET

Render:
LD HL,Image
LD DE,$9866
LD B,12
RenderRow:
CALL CopyEight
LD A,E
ADD A,24
LD E,A
JR NC,RenderCarry
INC D
RenderCarry:
DEC B
JR NZ,RenderRow
LD DE,$988F
LD B,4
RenderPreview:
CALL CopyFour
LD A,E
ADD A,28
LD E,A
JR NC,PreviewCarry
INC D
PreviewCarry:
DEC B
JR NZ,RenderPreview
LD DE,$9A08
CALL CopyFour
LD A,[HL+]
LD [$9844],A
LD A,[HL]
LD [$9864],A
RET
