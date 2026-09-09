SECTION "rules",ROM
; Tables encode four cells as y*16+x, with four orientations per piece.
Shape:
LD A,[Piece]
SWAP A
LD E,A
LD A,[Rotation]
ADD A,A
ADD A,A
ADD A,E
LD E,A
LD D,0
LD HL,Shapes
ADD HL,DE
RET

; Return a board pointer for packed cell A. Carry rejects any board edge.
Address:
LD [Cell],A
AND A,$0F
LD B,A
LD A,[PosX]
ADD A,B
CP A,8
JR NC,AddressBad
LD C,A
LD A,[Cell]
SWAP A
AND A,$0F
LD B,A
LD A,[PosY]
ADD A,B
CP A,12
JR NC,AddressBad
ADD A,A
ADD A,A
ADD A,A
ADD A,C
LD L,A
LD H,$C1
AND A,A
RET
AddressBad:
SCF
RET

Valid:
PUSH BC
PUSH DE
PUSH HL
CALL Shape
LD D,H
LD E,L
LD A,4
LD [Saved],A
ValidLoop:
LD A,[DE]
INC DE
CALL Address
JR C,ValidEnd
LD A,[HL]
OR A,A
JR NZ,ValidBad
LD A,[Saved]
DEC A
LD [Saved],A
JR NZ,ValidLoop
AND A,A
JR ValidEnd
ValidBad:
SCF
ValidEnd:
POP HL
POP DE
POP BC
RET

Spawn:
XOR A,A
LD [Rotation],A
LD [PosY],A
LD [Gravity],A
LD A,2
LD [PosX],A
CALL Valid
RET NC
LD A,2
LD [Status],A
RET

NewGame:
LD HL,Board
LD B,96
XOR A,A
NewClear:
LD [HL+],A
DEC B
JR NZ,NewClear
LD [Piece],A
LD HL,Score
LD [HL+],A
LD [HL+],A
LD [HL+],A
LD [HL],A
INC A
LD [Status],A
JP Spawn

Update:
LD A,[Buttons]
LD B,A
LD A,[Previous]
CPL
AND A,B
LD [Edges],A
LD A,B
LD [Previous],A
LD A,[Status]
CP A,1
JR Z,Move
LD A,[Edges]
AND A,$80
RET Z
JP NewGame
Move:
LD A,[Buttons]
AND A,3
CP A,3
JR Z,Rotate
LD A,[Edges]
AND A,3
CP A,1
JR Z,MoveRight
CP A,2
JR NZ,Rotate
LD HL,PosX
DEC [HL]
CALL Valid
JR NC,Rotate
INC [HL]
JR Rotate
MoveRight:
LD HL,PosX
INC [HL]
CALL Valid
JR NC,Rotate
DEC [HL]
Rotate:
LD A,[Edges]
AND A,$10
JR Z,Drop
LD A,[Rotation]
INC A
AND A,3
LD [Rotation],A
CALL Valid
JR NC,Drop
LD A,[Rotation]
DEC A
AND A,3
LD [Rotation],A
Drop:
LD A,[Edges]
AND A,$20
JR Z,Soft
HardLoop:
LD HL,PosY
INC [HL]
CALL Valid
JR NC,HardLoop
DEC [HL]
JP Lock
Soft:
LD A,[Edges]
AND A,8
JR NZ,Fall
LD HL,Gravity
INC [HL]
LD A,[HL]
CP A,60
RET NZ
Fall:
XOR A,A
LD [Gravity],A
LD HL,PosY
INC [HL]
CALL Valid
RET NC
DEC [HL]
JP Lock

Lock:
CALL Shape
LD D,H
LD E,L
LD A,4
LD [Saved],A
LockLoop:
LD A,[DE]
INC DE
CALL Address
LD [HL],1
LD A,[Saved]
DEC A
LD [Saved],A
JR NZ,LockLoop
CALL ClearRows
LD A,[Piece]
INC A
CP A,7
JR C,NextPiece
XOR A,A
NextPiece:
LD [Piece],A
JP Spawn

; Compact surviving rows downwards; every source row is examined once.
ClearRows:
XOR A,A
LD [Rows],A
LD A,11
LD [SourceRow],A
LD [TargetRow],A
RowLoop:
LD A,[SourceRow]
ADD A,A
ADD A,A
ADD A,A
LD L,A
LD H,$C1
PUSH HL
LD B,8
LD C,1
RowCheck:
LD A,[HL+]
AND A,C
LD C,A
DEC B
JR NZ,RowCheck
POP HL
LD A,C
OR A,A
JR Z,KeepRow
LD A,[Rows]
INC A
LD [Rows],A
JR RowNext
KeepRow:
LD A,[TargetRow]
ADD A,A
ADD A,A
ADD A,A
LD E,A
LD D,$C1
LD B,8
RowCopy:
LD A,[HL+]
LD [DE],A
INC DE
DEC B
JR NZ,RowCopy
LD A,[TargetRow]
DEC A
LD [TargetRow],A
RowNext:
LD A,[SourceRow]
DEC A
LD [SourceRow],A
CP A,$FF
JR NZ,RowLoop
LD A,[TargetRow]
INC A
JR Z,AddScore
ADD A,A
ADD A,A
ADD A,A
LD B,A
LD HL,Board
XOR A,A
TopClear:
LD [HL+],A
DEC B
JR NZ,TopClear
AddScore:
LD A,[Rows]
OR A,A
RET Z
LD B,A
ScoreLoop:
LD HL,Score+1
INC [HL]
LD A,[HL]
CP A,10
JR C,ScoreNext
LD [HL],0
DEC HL
INC [HL]
LD A,[HL]
CP A,10
JR C,ScoreNext
LD A,9
LD [HL+],A
LD [HL+],A
LD [HL+],A
LD [HL],A
RET
ScoreNext:
DEC B
JR NZ,ScoreLoop
RET

