; Original fixed-slot entities. All updates run outside the publication window.
SECTION "entities",ROM
InitEntities:
LD HL,CurlX
LD B,80
XOR A,A
EntityClear:
LD [HL+],A
DEC B
JR NZ,EntityClear
LD HL,EntityCurlStarts
CALL StageWordHL
LD A,E
LD [CurlX],A
LD A,D
LD [CurlX+1],A
LD A,$80
LD [CurlY],A
LD A,7
LD [CurlY+1],A
LD [MovingY+1],A
LD [FallingY+1],A
LD HL,EntityMovingStarts
CALL StageWordHL
LD A,E
LD [MovingX],A
LD A,D
LD [MovingX+1],A
LD A,1
LD [MovingState],A
LD A,16
LD [MovingVX],A
LD HL,EntityFallingStarts
CALL StageWordHL
LD A,E
LD [FallingX],A
LD A,D
LD [FallingX+1],A
RET
EntityCurlStarts:
DW 5248,5632,5248
EntityMovingStarts:
DW 2816,2304,1792
EntityFallingStarts:
DW 5888,5120,5888

; Explicit fixed-slot initialization. No live owner can be overwritten.
; A=slot0..3; returns A=1 accepted, A=0 refused. Ordinary offscreen motion
; never calls this path; stage entry initializes all owners together.
SpawnEntity:
CP A,4
JP NC,SpawnRefused
OR A,A
JP Z,SpawnPatrol
CP A,1
JP Z,SpawnCurl
CP A,2
JP Z,SpawnMoving
LD A,[FallingState]
CP A,3
JP NZ,SpawnRefused
LD HL,FallingX
CALL EntityClearRecord
LD HL,EntityFallingStarts
CALL StageWordHL
LD A,E
LD [FallingX],A
LD A,D
LD [FallingX+1],A
LD A,7
LD [FallingY+1],A
JP SpawnAccepted
SpawnMoving:
LD A,[MovingState]
CP A,3
JP NZ,SpawnRefused
LD HL,MovingX
CALL EntityClearRecord
LD HL,EntityMovingStarts
CALL StageWordHL
LD A,E
LD [MovingX],A
LD A,D
LD [MovingX+1],A
LD A,7
LD [MovingY+1],A
LD A,1
LD [MovingState],A
LD A,16
LD [MovingVX],A
JP SpawnAccepted
SpawnCurl:
LD A,[CurlState]
CP A,2
JP NZ,SpawnRefused
LD HL,CurlX
CALL EntityClearRecord
LD HL,EntityCurlStarts
CALL StageWordHL
LD A,E
LD [CurlX],A
LD A,D
LD [CurlX+1],A
LD A,$80
LD [CurlY],A
LD A,7
LD [CurlY+1],A
JP SpawnAccepted
SpawnPatrol:
LD A,[EnemyAlive]
OR A,A
JP NZ,SpawnRefused
LD A,[StompTimer]
OR A,A
JP NZ,SpawnRefused
LD HL,StageEnemyStart
CALL StageWordHL
LD A,E
LD [EnemyX],A
LD A,D
LD [EnemyX+1],A
LD A,8
LD [EnemyVX],A
XOR A,A
LD [PatrolFrame],A
LD A,1
LD [EnemyAlive],A
SpawnAccepted:
LD A,1
RET
SpawnRefused:
XOR A,A
RET
EntityClearRecord:
LD B,16
XOR A,A
EntityClearOne:
LD [HL+],A
DEC B
JP NZ,EntityClearOne
RET

; Counts are update counters, never display or wall-clock counters.
EntityAnimation:
LD A,[PatrolFrame]
INC A
AND A,15
LD [PatrolFrame],A
LD A,[StompTimer]
OR A,A
RET Z
DEC A
LD [StompTimer],A
RET

StepMoving:
LD A,[MovingState]
CP A,1
RET NZ
LD A,[MovingVX]
LD E,A
LD D,0
BIT 7,E
JR Z,MovingPositive
DEC D
MovingPositive:
LD A,[MovingX]
LD L,A
LD A,[MovingX+1]
LD H,A
ADD HL,DE
PUSH HL
LD HL,EntityMovingStarts
CALL StageWordHL
POP HL
CALL CompareSigned
JR C,MovingAtLeft
JR Z,MovingAtLeft
PUSH HL
LD HL,512
ADD HL,DE
LD D,H
LD E,L
POP HL
CALL CompareSigned
JR C,MovingSave
LD A,$F0
LD [MovingVX],A
JR MovingClamp
MovingAtLeft:
LD A,16
LD [MovingVX],A
MovingClamp:
LD H,D
LD L,E
MovingSave:
LD A,L
LD [MovingX],A
LD A,H
LD [MovingX+1],A
RET

StepFalling:
LD A,[FallingState]
CP A,1
JR NZ,FallingMoveTest
LD HL,FallingTimer
DEC [HL]
RET NZ
LD A,2
LD [FallingState],A
FallingMoveTest:
CP A,2
RET NZ
LD A,[FallingY]
ADD A,32
LD [FallingY],A
LD A,[FallingY+1]
ADC A,0
LD [FallingY+1],A
CP A,9
RET C
LD A,3
LD [FallingState],A
RET

StepCurl:
LD A,[CurlState]
CP A,2
RET Z
CP A,1
JR NZ,CurlDormant
LD HL,CurlTimer
DEC [HL]
RET NZ
XOR A,A
LD [CurlState],A
LD A,32
LD [CurlTimer],A
RET
CurlDormant:
LD A,[CurlTimer]
OR A,A
JR Z,CurlDistance
DEC A
LD [CurlTimer],A
RET
CurlDistance:
LD A,[PlayerX]
LD L,A
LD A,[PlayerX+1]
LD H,A
LD A,[CurlX]
LD E,A
LD A,[CurlX+1]
LD D,A
LD A,L
SUB A,E
LD L,A
LD A,H
SBC A,D
LD H,A
BIT 7,H
JR Z,CurlAbsolute
XOR A,A
SUB A,L
LD L,A
SBC A,A
SUB A,H
LD H,A
CurlAbsolute:
LD DE,512
CALL CompareSigned
JR Z,CurlActivate
RET NC
CurlActivate:
LD A,1
LD [CurlState],A
LD A,32
LD [CurlTimer],A
RET

; Snapshot before any platform moves. The old bottom is the landing witness.
EntityBefore:
LD HL,PlayerX
LD DE,EntityOldX
LD B,4
EntitySnapshotPlayer:
LD A,[HL+]
LD [DE],A
INC DE
DEC B
JR NZ,EntitySnapshotPlayer
LD HL,MovingX
LD DE,EntityOldMovingX
LD B,4
EntitySnapshotMoving:
LD A,[HL+]
LD [DE],A
INC DE
DEC B
JR NZ,EntitySnapshotMoving
LD HL,FallingX
LD DE,EntityOldFallingX
LD B,4
EntitySnapshotFalling:
LD A,[HL+]
LD [DE],A
INC DE
DEC B
JR NZ,EntitySnapshotFalling
XOR A,A
LD [EntityDetached],A
LD [EntityRider],A
LD A,[Grounded]
OR A,A
JR Z,EntityBeforeMove
LD A,[JumpState]
OR A,A
CALL Z,EntitySupport
EntityBeforeMove:
CALL EntityAnimation
CALL StepMoving
CALL StepFalling
LD A,[Previous]
CPL
LD B,A
LD A,[Buttons]
AND A,B
AND A,16
JR NZ,EntityJumpOff
LD A,[EntityRider]
OR A,A
RET Z
JP EntityCarry
EntityJumpOff:
XOR A,A
LD [EntityRider],A
RET

; A=1 moving,2 falling. Return A=1 and the current Q4 box, or A=0 absent.
EntityPlatformBox:
LD [EntitySlot],A
CP A,1
JR NZ,EntityLoadFall
LD A,[MovingState]
CP A,1
LD A,0
JR NZ,EntityMovingFlag
INC A
EntityMovingFlag:
LD HL,MovingX
JR EntityLoadBox
EntityLoadFall:
LD A,[FallingState]
CP A,3
LD A,0
JR Z,EntityFallingFlag
INC A
EntityFallingFlag:
LD HL,FallingX
EntityLoadBox:
PUSH AF
LD A,[HL+]
LD [ObjectX],A
LD A,[HL+]
LD [ObjectX+1],A
LD A,[HL+]
LD [ObjectY],A
LD A,[HL]
LD [ObjectY+1],A
POP AF
RET
EntityNoBox:
XOR A,A
RET

; Horizontal half-open player8/platform24 overlap; no tile or sprite wrapping.
EntityOverlapX:
LD A,[PlayerX]
LD L,A
LD A,[PlayerX+1]
LD H,A
LD DE,128
ADD HL,DE
LD A,[ObjectX]
LD E,A
LD A,[ObjectX+1]
LD D,A
CALL CompareSigned
JP C,EntityNoBox
JP Z,EntityNoBox
LD H,D
LD L,E
LD DE,384
ADD HL,DE
LD A,[PlayerX]
LD E,A
LD A,[PlayerX+1]
LD D,A
CALL CompareSigned
JP C,EntityNoBox
JP Z,EntityNoBox
LD A,1
RET

EntitySupport:
LD A,1
CALL EntitySupportOne
OR A,A
RET NZ
LD A,2
EntitySupportOne:
LD B,A
LD A,[EntityDetached]
CP A,B
JP Z,EntityNoBox
LD A,B
CALL EntityPlatformBox
OR A,A
RET Z
CALL EntityOverlapX
OR A,A
RET Z
LD A,[PlayerY]
LD L,A
LD A,[PlayerY+1]
LD H,A
LD DE,256
ADD HL,DE
LD A,[ObjectY]
CP A,L
JP NZ,EntityNoBox
LD A,[ObjectY+1]
CP A,H
JP NZ,EntityNoBox
LD A,[EntitySlot]
LD [EntityRider],A
LD A,1
RET

EntityLanding:
XOR A,A
LD [EntityRider],A
LD A,[JumpState]
CP A,1
RET Z
LD A,[VelocityY+1]
BIT 7,A
RET NZ
LD A,1
CALL EntityLandOne
OR A,A
JR NZ,EntityLanded
LD A,2
CALL EntityLandOne
OR A,A
RET Z
EntityLanded:
LD A,[ObjectY]
LD [PlayerY],A
LD A,[ObjectY+1]
DEC A
LD [PlayerY+1],A
XOR A,A
LD [VelocityY],A
LD [VelocityY+1],A
LD [JumpState],A
LD [JumpIndex],A
LD [SavedJumpIndex],A
LD [Fell],A
INC A
LD [Grounded],A
LD A,[EntitySlot]
LD [EntityRider],A
CP A,2
JR NZ,EntityCamera
LD A,[FallingState]
OR A,A
JR NZ,EntityCamera
INC A
LD [FallingState],A
LD A,16
LD [FallingTimer],A
EntityCamera:
JP MoveCamera

EntityLandOne:
LD B,A
LD A,[EntityDetached]
CP A,B
JP Z,EntityNoLand
LD A,B
CALL EntityPlatformBox
OR A,A
RET Z
CALL EntityOverlapX
OR A,A
RET Z
LD A,[EntitySlot]
CP A,1
LD HL,EntityOldMovingY
JR Z,EntityOldTop
LD HL,EntityOldFallingY
EntityOldTop:
LD A,[HL+]
LD E,A
LD D,[HL]
LD A,[EntityOldY]
LD L,A
LD A,[EntityOldY+1]
INC A
LD H,A
CALL CompareSigned
JR C,EntityCrossNew
JP NZ,EntityNoLand
EntityCrossNew:
LD A,[PlayerY]
LD L,A
LD A,[PlayerY+1]
INC A
LD H,A
LD A,[ObjectY]
LD E,A
LD A,[ObjectY+1]
LD D,A
CALL CompareSigned
JP C,EntityNoLand
LD A,1
RET
EntityNoLand:
XOR A,A
RET

EntityCarry:
CALL EntityPlatformBox
OR A,A
JR Z,EntityDetach
LD A,[EntitySlot]
CP A,1
LD HL,EntityOldMovingX
JR Z,EntityCarryOld
LD HL,EntityOldFallingX
EntityCarryOld:
LD A,[HL+]
LD C,A
LD A,[HL+]
LD B,A
LD A,[ObjectX]
SUB A,C
LD C,A
LD A,[ObjectX+1]
SBC A,B
LD B,A
LD A,[PlayerX]
ADD A,C
LD [EntityCandidateX],A
LD A,[PlayerX+1]
ADC A,B
LD [EntityCandidateX+1],A
LD A,[HL+]
LD C,A
LD A,[HL]
LD B,A
LD A,[ObjectY]
SUB A,C
LD C,A
LD A,[ObjectY+1]
SBC A,B
LD B,A
LD A,[PlayerY]
ADD A,C
LD [EntityCandidateY],A
LD A,[PlayerY+1]
ADC A,B
LD [EntityCandidateY+1],A
CALL EntityCarryClear
OR A,A
JR Z,EntityDetach
LD HL,EntityCandidateX
LD DE,PlayerX
LD B,4
EntityCommitCarry:
LD A,[HL+]
LD [DE],A
INC DE
DEC B
JR NZ,EntityCommitCarry
RET
EntityDetach:
LD A,[EntitySlot]
LD [EntityDetached],A
XOR A,A
LD [EntityRider],A
RET

EntityCarryClear:
XOR A,A
LD [ScanUp],A
LD A,[EntityCandidateX+1]
BIT 7,A
JP NZ,EntityNoLand
LD H,A
LD A,[EntityCandidateX]
LD L,A
PUSH HL
CALL StageXLimit
LD D,H
LD E,L
POP HL
CALL CompareSigned
JR C,EntityCarryRows
JP NZ,EntityNoLand
EntityCarryRows:
LD A,[EntityCandidateY]
LD L,A
LD A,[EntityCandidateY+1]
LD H,A
PUSH HL
CALL TileIndex
LD [Row],A
POP HL
LD DE,255
ADD HL,DE
CALL TileIndex
LD [EntityTemp],A
EntityCarryRow:
LD A,[Row]
CP A,18
JR NC,EntityNextCarryRow
LD A,[EntityCandidateX]
LD L,A
LD A,[EntityCandidateX+1]
LD H,A
PUSH HL
CALL TileIndex
LD [Column],A
POP HL
LD DE,127
ADD HL,DE
CALL TileIndex
LD [LastCell],A
EntityCarryCell:
CALL CollisionPointer
CALL CellSolid
OR A,A
JP NZ,EntityNoLand
LD A,[LastCell]
LD B,A
LD A,[Column]
CP A,B
JR Z,EntityNextCarryRow
INC A
LD [Column],A
JR EntityCarryCell
EntityNextCarryRow:
LD A,[EntityTemp]
LD B,A
LD A,[Row]
CP A,B
JR Z,EntityCarryGood
INC A
LD [Row],A
JR EntityCarryRow
EntityCarryGood:
LD A,1
RET

SECTION "entity_helpers",ROM
; Only LCD-off startup copies approved source pixels. DE remains contiguous.
InitEntityArt:
LD DE,$8950
LD HL,EnemyTiles
LD B,176
CALL MotionTileCopy
LD HL,EnemyTiles+304
LD B,224
JP MotionTileCopy

; Active CURL uses existing side-hit protection, never the stomp branch.
CurlContact:
LD A,[CurlState]
CP A,1
JR NZ,EntityContactNone
LD HL,CurlX
LD A,[HL+]
LD [ObjectX],A
LD A,[HL+]
LD [ObjectX+1],A
LD A,[HL+]
LD [ObjectY],A
LD A,[HL]
LD [ObjectY+1],A
LD A,128
LD [ObjectHeight],A
XOR A,A
LD [ObjectHeight+1],A
CALL OverlapObject
OR A,A
RET Z
LD A,[Invincible]
OR A,A
JP Z,SideHit
LD A,2
LD [CurlState],A
XOR A,A
LD [CurlTimer],A
RET
EntityContactNone:
XOR A,A
RET

ComposePatrol:
LD A,[EnemyX]
LD [ObjectX],A
LD A,[EnemyX+1]
LD [ObjectX+1],A
LD A,128
LD [ObjectY],A
LD A,7
LD [ObjectY+1],A
CALL EntityCenter
XOR A,A
LD [PieceFlags],A
LD [SceneHidden],A
LD A,[EnemyVX]
BIT 7,A
JR Z,PatrolFacing
LD A,32
LD [PieceFlags],A
PatrolFacing:
LD A,[EnemyAlive]
OR A,A
JR Z,PatrolDeadPose
LD A,[PatrolFrame]
BIT 3,A
LD HL,EntityWalk1
JR Z,EntityQuad
LD HL,EntityWalk2
JR EntityQuad
PatrolDeadPose:
LD A,[StompTimer]
OR A,A
JR Z,PatrolHidden
CP A,9
LD HL,EntityStomp1
JR NC,EntityQuad
LD HL,EntityStomp2
JR EntityQuad
PatrolHidden:
LD A,1
LD [SceneHidden],A
LD HL,EntityWalk1
JR EntityQuad

EntityCenter:
CALL ScenePosition
LD A,[SceneBaseX]
SUB A,4
LD [SceneBaseX],A
LD A,[SceneBaseX+1]
SBC A,0
LD [SceneBaseX+1],A
LD A,[SceneBaseY]
SUB A,8
LD [SceneBaseY],A
LD A,[SceneBaseY+1]
SBC A,0
LD [SceneBaseY+1],A
RET

EntityQuad:
LD A,4
LD [PieceCount],A
EntityQuadPiece:
LD A,[PieceCount]
DEC A
XOR A,3
PUSH AF
AND A,2
RLCA
RLCA
LD [PieceY],A
POP AF
AND A,1
RLCA
RLCA
RLCA
LD B,A
LD A,[PieceFlags]
BIT 5,A
LD A,B
JR Z,EntityQuadX
XOR A,8
EntityQuadX:
LD [PieceX],A
LD A,[HL+]
LD [SceneTile],A
PUSH HL
CALL EmitPiece
POP HL
LD A,[PieceCount]
DEC A
LD [PieceCount],A
JR NZ,EntityQuadPiece
RET

ComposeOtherEntities:
LD HL,CurlX
LD A,[HL+]
LD [ObjectX],A
LD A,[HL+]
LD [ObjectX+1],A
LD A,[HL+]
LD [ObjectY],A
LD A,[HL]
LD [ObjectY+1],A
CALL EntityCenter
XOR A,A
LD [SceneHidden],A
LD [PieceFlags],A
LD A,[CurlState]
CP A,2
JR NZ,CurlDrawState
LD A,1
LD [SceneHidden],A
LD A,2
CurlDrawState:
CP A,1
LD HL,EntityCurlDormant
JR NZ,CurlDraw
LD HL,EntityCurlActive
CurlDraw:
CALL EntityQuad
LD A,1
CALL EntityPlatformBox
XOR A,1
LD [SceneHidden],A
CALL ScenePosition
LD HL,EntitySolid
CALL EntityThree
LD A,2
CALL EntityPlatformBox
XOR A,1
LD [SceneHidden],A
CALL ScenePosition
LD HL,EntitySolid
LD A,[FallingState]
OR A,A
JR Z,EntityThree
LD A,[FallingTimer]
CP A,9
LD HL,EntityCrack1
JR NC,EntityThree
LD HL,EntityCrack2
EntityThree:
XOR A,A
LD [PieceX],A
LD [PieceY],A
LD [PieceFlags],A
LD A,3
LD [PieceCount],A
EntityThreePiece:
LD A,[HL+]
LD [SceneTile],A
PUSH HL
CALL EmitPiece
POP HL
LD A,[PieceX]
ADD A,8
LD [PieceX],A
LD A,[PieceCount]
DEC A
LD [PieceCount],A
JR NZ,EntityThreePiece
RET

EntityWalk1:
DB 149,150,151,152
EntityWalk2:
DB 149,150,153,154
EntityStomp1:
DB 155,155,156,157
EntityStomp2:
DB 155,155,158,159
EntityCurlDormant:
DB 160,161,162,163
EntityCurlActive:
DB 164,165,166,167
EntitySolid:
DB 168,169,170
EntityCrack1:
DB 168,171,170
EntityCrack2:
DB 172,173,170

SECTION "entity_assets",ROM
EnemyTiles:
ASSET "Enemies"
