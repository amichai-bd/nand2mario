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
LD HL,MoveCounter
LD B,10
XOR A,A
InitMotionLoop:
LD [HL+],A
DEC B
JR NZ,InitMotionLoop
INC A
LD [AnimationCounter],A
RET
InitialPlayer:
DB $80,$01,$00,$07,0,0,0,0,1,0,0,0,0,0

StepPlayer:
; Scans default to descending; only the head scan sets ScanUp.
XOR A,A
LD [ScanUp],A
LD [HitValid],A
LD A,[Fell]
OR A,A
JP NZ,RememberButtons
CALL SelectMotion
CALL HorizontalMotion
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
PUSH HL
CALL StageXLimit
LD D,H
LD E,L
POP HL
LD A,H
CP A,D
JR C,SaveCandidateX
JR NZ,RightBound
LD A,L
CP A,E
JR C,SaveCandidateX
JR Z,SaveCandidateX
RightBound:
CALL StageXLimit
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
CALL CellSolid
OR A,A
JR NZ,BlockX
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
CALL VerticalMotion
; A supported stationary player keeps contact without a synthetic gravity step.
LD A,[JumpState]
OR A,A
JP Z,FinishMove
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
JR NZ,YAscending
LD DE,$00FF
ADD HL,DE
JR YLeading
YAscending:
LD A,1
LD [ScanUp],A
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
CALL CellSolid
OR A,A
JR NZ,BlockY
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
JR NZ,BlockHead
XOR A,A
LD [JumpState],A
LD [JumpIndex],A
LD [SavedJumpIndex],A
INC A
LD [Grounded],A
LD A,[Row]
DEC A
DEC A
JR YBoundary
BlockHead:
; Record the cell so the block layer can resolve one head hit per update.
LD A,L
LD [HitColumn],A
LD A,H
SUB A,HIGH(CollisionMap)
LD [HitRow],A
LD A,1
LD [HitValid],A
LD A,2
LD [JumpState],A
XOR A,A
LD [JumpIndex],A
LD [SavedJumpIndex],A
LD A,[Row]
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
CALL StageCameraLimit
LD A,H
CP A,D
JR C,SaveCamera
JR NZ,CameraRight
LD A,L
CP A,E
JR C,SaveCamera
JR Z,SaveCamera
CameraRight:
LD H,D
LD L,E
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

; Original implementation of the approved reference-informed update order.
SelectMotion:
LD A,[Buttons]
BIT 5,A
JR Z,MotionReleaseB
LD A,[JumpState]
OR A,A
JR NZ,MotionJumpEdge
LD A,[MoveCounter]
CP A,3
LD A,2
JR C,MotionSpeed
LD A,4
MotionSpeed:
LD [MoveSpeed],A
JR MotionJumpEdge
MotionReleaseB:
LD A,[MoveSpeed]
CP A,4
JR NZ,MotionJumpEdge
LD A,2
LD [MoveSpeed],A
MotionJumpEdge:
LD A,[Buttons]
BIT 4,A
JR Z,MotionBEdge
LD A,[Previous]
BIT 4,A
JR NZ,MotionBEdge
LD A,[JumpState]
OR A,A
JR NZ,MotionBEdge
LD A,[Grounded]
OR A,A
JR Z,MotionBEdge
XOR A,A
LD [Grounded],A
LD [SavedJumpIndex],A
LD [JumpIndex],A
LD A,[MoveSpeed]
CP A,4
JR Z,MotionStartJump
LD A,2
LD [MoveSpeed],A
LD [JumpIndex],A
MotionStartJump:
LD A,1
LD [JumpState],A
LD A,4
LD [MotionPose],A
LD A,48
LD [MoveCounter],A
MotionBEdge:
LD A,[Buttons]
BIT 5,A
JR Z,MotionAnimate
LD A,[Previous]
BIT 5,A
JR NZ,MotionAnimate
LD A,[MoveCounter]
CP A,6
JR NZ,MotionAnimate
XOR A,A
LD [MoveCounter],A
MotionAnimate:
LD A,[Grounded]
OR A,A
RET Z
LD A,[AnimationCounter]
AND A,3
RET NZ
LD A,[MotionPose]
CP A,3
JR C,MotionAdvancePose
XOR A,A
MotionAdvancePose:
INC A
LD [MotionPose],A
RET

HorizontalMotion:
XOR A,A
LD [VelocityX],A
LD [VelocityX+1],A
LD A,[MoveDirection]
CP A,3
JR NZ,MotionIntent
LD A,[MoveCounter]
OR A,A
JR Z,MotionClearReverse
DEC A
LD [MoveCounter],A
RET
MotionClearReverse:
XOR A,A
LD [MoveDirection],A
JP MotionStand
MotionIntent:
LD A,[MoveCounter]
CP A,6
JR NZ,MotionButtons
LD A,[MoveSpeed]
OR A,A
JR NZ,MotionButtons
LD A,2
LD [MoveSpeed],A
MotionButtons:
LD A,[Buttons]
BIT 0,A
LD B,1
JR NZ,MotionDirection
BIT 1,A
LD B,2
JR NZ,MotionDirection
LD A,[MoveCounter]
OR A,A
JR Z,MotionStop
DEC A
LD [MoveCounter],A
XOR A,A
LD [MoveSpeed],A
LD A,[MoveDirection]
OR A,A
RET Z
LD B,A
JR MotionDirection
MotionStop:
XOR A,A
LD [MoveDirection],A
JP MotionStand
MotionDirection:
LD A,[MoveDirection]
OR A,A
JR Z,MotionAcceptDirection
CP A,B
JR Z,MotionAcceptDirection
LD A,3
LD [MoveDirection],A
LD A,8
LD [MoveCounter],A
LD A,[JumpState]
OR A,A
RET NZ
LD A,5
LD [MotionPose],A
LD A,1
LD [AnimationCounter],A
RET
MotionAcceptDirection:
XOR A,A
BIT 1,B
JR Z,MotionFacingSaved
LD A,$20
MotionFacingSaved:
LD [MotionFacing],A
LD A,[Buttons]
AND A,B
JR Z,MotionDisplacement
LD A,[MoveCounter]
CP A,6
JR Z,MotionDisplacement
INC A
LD [MoveCounter],A
LD A,B
LD [MoveDirection],A
MotionDisplacement:
LD A,[MovePhase]
XOR A,1
LD [MovePhase],A
LD C,A
LD A,[MoveSpeed]
OR A,A
LD A,C
JR Z,MotionDistance
LD A,[MoveSpeed]
CP A,2
LD A,1
JR Z,MotionDistance
ADD A,C
MotionDistance:
SWAP A
LD L,A
LD H,0
BIT 1,B
JR Z,MotionRightVelocity
XOR A,A
SUB A,L
LD L,A
SBC A,A
LD H,A
LD A,[AnimationCounter]
DEC A
JR MotionAnimationSaved
MotionRightVelocity:
LD A,[AnimationCounter]
INC A
MotionAnimationSaved:
LD [AnimationCounter],A
LD A,L
LD [VelocityX],A
LD A,H
LD [VelocityX+1],A
RET
MotionStand:
LD A,[JumpState]
OR A,A
RET NZ
LD [MotionPose],A
LD [MoveSpeed],A
INC A
LD [AnimationCounter],A
RET

VerticalMotion:
LD A,[JumpState]
CP A,1
JR NZ,MotionRestoreIndex
LD A,[Buttons]
BIT 4,A
JR NZ,MotionRestoreIndex
LD A,[JumpIndex]
CP A,15
JR NC,MotionRestoreIndex
OR A,A
JR Z,MotionSaveRelease
DEC A
MotionSaveRelease:
LD [SavedJumpIndex],A
LD A,15
LD [JumpIndex],A
MotionRestoreIndex:
LD A,[JumpState]
CP A,1
JR Z,MotionTryRestore
CP A,2
JR NZ,MotionCheckSupport
MotionTryRestore:
LD A,[JumpIndex]
CP A,15
JR NC,MotionCheckSupport
LD A,[SavedJumpIndex]
OR A,A
JR Z,MotionCheckSupport
LD [JumpIndex],A
XOR A,A
LD [SavedJumpIndex],A
MotionCheckSupport:
LD A,[JumpState]
OR A,A
JR NZ,MotionVerticalStep
CALL EntitySupport
OR A,A
JR NZ,MotionKeepSupport
CALL MotionSupport
OR A,A
JR Z,MotionStartFall
MotionKeepSupport:
LD [Grounded],A
XOR A,A
LD [VelocityY],A
LD [VelocityY+1],A
RET
MotionStartFall:
LD A,3
LD [JumpState],A
LD A,4
LD [MotionPose],A
MotionVerticalStep:
LD A,[JumpState]
CP A,3
JR Z,MotionTerminalFall
CP A,1
JR NZ,MotionDescending
LD A,[JumpIndex]
CP A,26
JR NC,MotionApex
CALL MotionProfile
SWAP A
LD C,A
LD HL,JumpIndex
INC [HL]
LD L,C
XOR A,A
SUB A,L
LD L,A
SBC A,A
LD H,A
JR MotionSaveVertical
MotionApex:
LD A,25
LD [JumpIndex],A
LD A,2
LD [JumpState],A
MotionDescending:
LD A,[JumpIndex]
CALL MotionProfile
SWAP A
LD C,A
LD A,[JumpIndex]
OR A,A
JR Z,MotionExhausted
DEC A
LD [JumpIndex],A
JR MotionDownMagnitude
MotionExhausted:
LD A,3
LD [JumpState],A
MotionDownMagnitude:
LD L,C
LD H,0
JR MotionSaveVertical
MotionTerminalFall:
LD HL,$0040
MotionSaveVertical:
LD A,L
LD [VelocityY],A
LD A,H
LD [VelocityY+1],A
RET

; Original piecewise evaluator; no imported displacement table.
MotionProfile:
CP A,2
JR NC,MotionProfile3
LD A,4
RET
MotionProfile3:
CP A,4
JR NC,MotionProfile2
LD A,3
RET
MotionProfile2:
CP A,13
JR NC,MotionProfile1
LD A,2
RET
MotionProfile1:
CP A,20
JR NC,MotionProfileTail
LD A,1
RET
MotionProfileTail:
CP A,21
JR Z,MotionTailOne
CP A,23
JR Z,MotionTailOne
XOR A,A
RET
MotionTailOne:
LD A,1
RET

; Full-width support probe at the existing half-open box's lower boundary.
MotionSupport:
LD A,[PlayerY]
AND A,$7F
JR NZ,MotionUnsupported
LD A,[PlayerY]
LD L,A
LD A,[PlayerY+1]
LD H,A
LD DE,$0100
ADD HL,DE
CALL TileIndex
CP A,18
JR NC,MotionUnsupported
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
CALL CollisionPointer
MotionSupportCells:
CALL CellSolid
OR A,A
JR NZ,MotionSupported
LD A,[Column]
LD B,A
LD A,[LastCell]
CP A,B
JR Z,MotionUnsupported
INC B
LD A,B
LD [Column],A
INC L
JR MotionSupportCells
MotionUnsupported:
XOR A,A
RET
MotionSupported:
LD A,1
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
; X is clamped before either scan, so its box stays inside the stage, and
; the stage base keeps every index inside the one256-column page.
; Callers reject out-of-world rows before reading. X scans advance H; Y scans L.
CollisionPointer:
CALL StageBaseColumn
LD B,A
LD A,[Column]
ADD A,B
LD L,A
LD A,[Row]
ADD A,HIGH(CollisionMap)
LD H,A
RET
EXPORT InitPlayer
EXPORT StepPlayer
