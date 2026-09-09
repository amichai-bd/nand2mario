; Software-only movement. The same linked bytes serve the game and CPU unit ROM.
INCLUDE "state.asm"
SECTION "movement",ROM
InitPlayer:
LD DE,InitialPlayer
LD HL,PlayerX
LD B,$0E
InitLoop:
LD A,[DE]
INC DE
LD [HL+],A
DEC B
JR NZ,InitLoop
RET
InitialPlayer:
DB $80,$01,$00,$07,0,0,0,0,1,0,0,0,0,0

StepPlayer:
LD A,[Fell]
OR A,A
JP NZ,RememberButtons
; Horizontal intent has no inertia. Both directions cancel.
LD HL,0
LD A,[Buttons]
AND A,$03
CP A,$01
JR Z,GoRight
CP A,$02
JR Z,GoLeft
JR SaveVX
GoRight:
LD HL,$0010
LD A,[Buttons]
AND A,$20
JR Z,SaveVX
LD HL,$0020
JR SaveVX
GoLeft:
LD HL,$FFF0
LD A,[Buttons]
AND A,$20
JR Z,SaveVX
LD HL,$FFE0
SaveVX:
LD A,L
LD [VelocityX],A
LD A,H
LD [VelocityX+1],A
; A is an edge, not a queued held jump.
LD A,[Buttons]
AND A,$10
JR Z,Gravity
LD A,[Previous]
AND A,$10
JR NZ,Gravity
LD A,[Grounded]
OR A,A
JR Z,Gravity
LD A,$AC
LD [VelocityY],A
LD A,$FF
LD [VelocityY+1],A
Gravity:
LD A,[VelocityY]
LD L,A
LD A,[VelocityY+1]
LD H,A
LD DE,$0004
ADD HL,DE
BIT 7,H
JR NZ,SaveVY
LD A,H
OR A,A
JR NZ,CapFall
LD A,L
CP A,$40
JR C,SaveVY
CapFall:
LD HL,$0040
SaveVY:
LD A,L
LD [VelocityY],A
LD A,H
LD [VelocityY+1],A
; Horizontal candidate, then world and tile boundaries.
LD A,[PlayerX]
LD L,A
LD A,[PlayerX+1]
LD H,A
LD A,[VelocityX]
LD E,A
LD A,[VelocityX+1]
LD D,A
ADD HL,DE
BIT 7,H
JR NZ,LeftBound
LD A,H
CP A,$2F
JR C,SaveCandidateX
JR NZ,RightBound
LD A,L
CP A,$81
JR C,SaveCandidateX
RightBound:
LD HL,$2F80
JR StopAtBound
LeftBound:
LD HL,0
StopAtBound:
XOR A,A
LD [VelocityX],A
LD [VelocityX+1],A
SaveCandidateX:
LD A,L
LD [PlayerX],A
LD A,H
LD [PlayerX+1],A
LD A,[VelocityX]
LD B,A
LD A,[VelocityX+1]
OR A,B
JP Z,Vertical
LD A,[VelocityX+1]
BIT 7,A
JR NZ,XLeading
LD DE,$007F
ADD HL,DE
XLeading:
CALL TileIndex
LD [Column],A
LD A,[PlayerY]
LD L,A
LD A,[PlayerY+1]
LD H,A
PUSH HL
CALL TileIndex
LD [Row],A
POP HL
LD DE,$00FF
ADD HL,DE
CALL TileIndex
LD [LastCell],A
CALL CollisionPointer
XCells:
LD A,[Row]
CP A,18
JR NC,XEmpty
LD A,[HL]
CP A,$0B
JR Z,BlockX
XEmpty:
LD A,[LastCell]
LD B,A
LD A,[Row]
CP A,B
JR Z,Vertical
INC A
LD [Row],A
INC H
JR XCells
BlockX:
LD A,[VelocityX+1]
BIT 7,A
LD A,[Column]
JR NZ,BlockLeft
DEC A
JR XBoundary
BlockLeft:
INC A
XBoundary:
CALL TileBoundary
LD A,L
LD [PlayerX],A
LD A,H
LD [PlayerX+1],A
XOR A,A
LD [VelocityX],A
LD [VelocityX+1],A
Vertical:
XOR A,A
LD [Grounded],A
LD A,[PlayerY]
LD L,A
LD A,[PlayerY+1]
LD H,A
LD A,[VelocityY]
LD E,A
LD A,[VelocityY+1]
LD D,A
ADD HL,DE
LD A,L
LD [PlayerY],A
LD A,H
LD [PlayerY+1],A
LD A,D
OR A,E
JP Z,FinishMove
BIT 7,D
JR NZ,YLeading
LD DE,$00FF
ADD HL,DE
YLeading:
CALL TileIndex
LD [Row],A
LD A,[PlayerX]
LD L,A
LD A,[PlayerX+1]
LD H,A
PUSH HL
CALL TileIndex
LD [Column],A
POP HL
LD DE,$007F
ADD HL,DE
CALL TileIndex
LD [LastCell],A
LD A,[Row]
CP A,18
JP NC,FinishMove
CALL CollisionPointer
YCells:
LD A,[HL]
CP A,$0B
JR Z,BlockY
LD A,[LastCell]
LD B,A
LD A,[Column]
CP A,B
JR Z,FinishMove
INC A
LD [Column],A
INC L
JR YCells
BlockY:
LD A,[VelocityY+1]
BIT 7,A
LD A,[Row]
JR NZ,BlockHead
DEC A
DEC A
PUSH AF
LD A,1
LD [Grounded],A
POP AF
JR YBoundary
BlockHead:
INC A
YBoundary:
CALL TileBoundary
LD A,L
LD [PlayerY],A
LD A,H
LD [PlayerY+1],A
XOR A,A
LD [VelocityY],A
LD [VelocityY+1],A
FinishMove:
LD A,[PlayerY+1]
BIT 7,A
JR NZ,MoveCamera
CP A,$09
JR C,MoveCamera
LD A,1
LD [Fell],A
MoveCamera:
LD A,[PlayerX]
LD L,A
LD A,[PlayerX+1]
LD H,A
CALL PixelFloor
LD DE,$FFB8
ADD HL,DE
BIT 7,H
JR NZ,CameraLeft
LD A,H
CP A,$02
JR C,SaveCamera
JR NZ,CameraRight
LD A,L
CP A,$61
JR C,SaveCamera
CameraRight:
LD HL,$0260
JR SaveCamera
CameraLeft:
LD HL,0
SaveCamera:
LD A,L
LD [Camera],A
LD A,H
LD [Camera+1],A
RememberButtons:
LD A,[Buttons]
LD [Previous],A
RET

; Floor a sixteenth-pixel coordinate to its signed eight-pixel tile index.
TileIndex:
LD A,H
ADD A,A
LD B,A
LD A,L
AND A,$80
RLCA
OR A,B
RET
; Tile coordinate A to signed fixed-point HL; rows -1..17 fit this conversion.
TileBoundary:
LD B,A
AND A,1
RRCA
LD L,A
LD A,B
SRA A
LD H,A
RET
PixelFloor:
SRA H
RR L
SRA H
RR L
SRA H
RR L
SRA H
RR L
RET
; Page-aligned rows keep collision scans cheap enough for normal VBlank.
; X is clamped before either scan, so its box stays in columns0..95.
; Callers reject out-of-world rows before reading. X scans advance H; Y scans L.
CollisionPointer:
LD A,[Row]
ADD A,HIGH(CollisionMap)
LD H,A
LD A,[Column]
LD L,A
RET
EXPORT InitPlayer
EXPORT StepPlayer
