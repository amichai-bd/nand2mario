; Approved pose placement. No gameplay state is modified here.
SECTION "courier",ROM
SelectCourier:
LD A,[MotionFacing]
LD [CourierFacing],A
CALL SelectPowerPose
LD [CourierPose],A
RET

InitMotionArt:
; Approved core tiles to free VRAM tiles94..107, LCD off: skid16..19, then
; 21..26 (hurt head, crouch), 43..45 (large skid, throw arm) and54 (shot).
LD HL,CoreTiles+$0100
LD DE,$85E0
LD B,64
CALL MotionTileCopy
LD HL,CoreTiles+$0150
LD B,96
CALL MotionTileCopy
LD HL,CoreTiles+$02B0
LD B,48
CALL MotionTileCopy
LD HL,CoreTiles+$0360
LD B,16
JP MotionTileCopy
MotionTileCopy:
LD A,[HL+]
LD [DE],A
INC DE
DEC B
JR NZ,MotionTileCopy
RET

; DE=next OAM slot; signed SceneBaseX/Y are small-pose top-left pixels.
; CourierPose=0..17, CourierFacing=0 or20. Six-piece poses are large and
; share the same feet, so their top-left is eight pixels higher.
ComposeCourier:
LD A,[CourierPose]
ADD A,A
LD C,A
LD B,0
LD HL,CourierPointers
ADD HL,BC
LD A,[HL+]
LD C,A
LD A,[HL]
LD H,A
LD L,C
LD A,[HL+]
LD [PieceCount],A
CP A,6
JR NZ,CourierPiece
LD A,[SceneBaseY]
SUB A,8
LD [SceneBaseY],A
LD A,[SceneBaseY+1]
SBC A,0
LD [SceneBaseY+1],A
CourierPiece:
LD A,[HL+]
LD B,A
LD A,[CourierFacing]
OR A,A
LD A,B
JR Z,CourierPieceX
LD A,8
SUB A,B
CourierPieceX:
LD [PieceX],A
LD A,[HL+]
LD [PieceY],A
LD A,[HL+]
ADD A,42
LD [SceneTile],A
LD A,[HL+]
LD B,A
LD A,[CourierFacing]
XOR A,B
LD [PieceFlags],A
PUSH HL
CALL EmitPiece
POP HL
LD A,[PieceCount]
DEC A
LD [PieceCount],A
JR NZ,CourierPiece
RET

; Two original adjacent tiles replace one old 8x16 entry without pixel changes.
EmitPair:
XOR A,A
LD [PieceX],A
LD [PieceY],A
LD [PieceFlags],A
CALL EmitPiece
LD A,8
LD [PieceY],A
LD A,[SceneTile]
INC A
LD [SceneTile],A
JP EmitPiece

EmitPiece:
LD A,[SceneHidden]
LD [PieceHidden],A
LD A,[SceneBaseX]
LD L,A
LD A,[SceneBaseX+1]
LD H,A
LD A,[PieceX]
LD C,A
LD B,0
ADD HL,BC
LD A,H
OR A,A
JR Z,PieceXPositive
CP A,$FF
JR NZ,PieceXHidden
LD A,L
CP A,249
JR C,PieceXHidden
JR PieceXReady
PieceXPositive:
LD A,L
CP A,160
JR C,PieceXReady
PieceXHidden:
LD A,1
LD [PieceHidden],A
PieceXReady:
LD A,L
ADD A,8
LD [SceneX],A
LD A,[SceneBaseY]
LD L,A
LD A,[SceneBaseY+1]
LD H,A
LD A,[PieceY]
LD C,A
LD B,0
ADD HL,BC
LD A,H
OR A,A
JR Z,PieceYPositive
CP A,$FF
JR NZ,PieceYHidden
LD A,L
CP A,249
JR C,PieceYHidden
JR PieceYReady
PieceYPositive:
LD A,L
CP A,144
JR C,PieceYReady
PieceYHidden:
LD A,1
LD [PieceHidden],A
PieceYReady:
LD A,L
ADD A,16
LD [SceneY],A
LD A,[PieceHidden]
OR A,A
LD A,0
JR NZ,PieceStore
LD A,[SceneY]
PieceStore:
LD [DE],A
INC DE
LD A,[SceneX]
LD [DE],A
INC DE
LD A,[SceneTile]
LD [DE],A
INC DE
LD A,[PieceFlags]
LD [DE],A
INC DE
RET

; Exact approved local IDs and offsets; tests compare all records to poses.json.
CourierPointers:
DW Courier_small_STAND
DW Courier_small_WALK1
DW Courier_small_WALK2
DW Courier_small_WALK3
DW Courier_small_JUMP
DW Courier_small_RETRY
DW Courier_large_STAND
DW Courier_large_WALK1
DW Courier_large_WALK2
DW Courier_large_WALK3
DW Courier_large_JUMP
DW Courier_large_RETRY
DW Courier_small_SKID
DW Courier_large_SKID
DW Courier_small_HURT
DW Courier_large_HURT
DW Courier_large_CROUCH
DW Courier_large_THROW
Courier_small_STAND:
DB 4
DB 0,0,0,0
DB 8,0,1,0
DB 0,8,2,0
DB 8,8,3,0
Courier_small_WALK1:
DB 4
DB 0,0,0,0
DB 8,0,1,0
DB 0,8,4,0
DB 8,8,5,0
Courier_small_WALK2:
DB 4
DB 0,0,0,0
DB 8,0,1,0
DB 0,8,6,0
DB 8,8,7,0
Courier_small_WALK3:
DB 4
DB 0,0,0,0
DB 8,0,1,0
DB 0,8,8,0
DB 8,8,9,0
Courier_small_JUMP:
DB 4
DB 0,0,0,0
DB 8,0,1,0
DB 0,8,10,0
DB 8,8,11,0
Courier_small_RETRY:
DB 4
DB 0,0,12,0
DB 8,0,13,0
DB 0,8,14,0
DB 8,8,15,0
Courier_large_STAND:
DB 6
DB 0,0,0,0
DB 8,0,1,0
DB 0,8,16,0
DB 8,8,17,0
DB 0,16,18,0
DB 8,16,19,0
Courier_large_WALK1:
DB 6
DB 0,0,0,0
DB 8,0,1,0
DB 0,8,20,0
DB 8,8,17,0
DB 0,16,21,0
DB 8,16,22,0
Courier_large_WALK2:
DB 6
DB 0,0,0,0
DB 8,0,1,0
DB 0,8,16,0
DB 8,8,17,0
DB 0,16,23,0
DB 8,16,24,0
Courier_large_WALK3:
DB 6
DB 0,0,0,0
DB 8,0,1,0
DB 0,8,16,0
DB 8,8,25,0
DB 0,16,26,0
DB 8,16,27,0
Courier_large_JUMP:
DB 6
DB 0,0,0,0
DB 8,0,1,0
DB 0,8,28,0
DB 8,8,29,0
DB 0,16,30,0
DB 8,16,31,0
Courier_large_RETRY:
DB 6
DB 0,0,12,0
DB 8,0,13,0
DB 0,8,28,0
DB 8,8,29,0
DB 0,16,18,0
DB 8,16,19,0

Courier_small_SKID:
DB 4
DB 0,0,52,0
DB 8,0,53,0
DB 0,8,54,0
DB 8,8,55,0

; Approved core maps; tile fields are VRAM ids minus42, so56..65 are the
; core copies at VRAM98..107. Crouch omits its blank top row.
Courier_large_SKID:
DB 6
DB 0,0,52,0
DB 8,0,53,0
DB 0,8,16,0
DB 8,8,25,0
DB 0,16,62,0
DB 8,16,63,0
Courier_small_HURT:
DB 4
DB 0,0,56,0
DB 8,0,57,0
DB 0,8,14,0
DB 8,8,15,0
Courier_large_HURT:
DB 6
DB 0,0,56,0
DB 8,0,57,0
DB 0,8,28,0
DB 8,8,29,0
DB 0,16,18,0
DB 8,16,19,0
Courier_large_CROUCH:
DB 4
DB 0,0,58,0
DB 8,0,59,0
DB 0,8,60,0
DB 8,8,61,0
Courier_large_THROW:
DB 6
DB 0,0,0,0
DB 8,0,1,0
DB 0,8,16,0
DB 8,8,64,0
DB 0,16,18,0
DB 8,16,19,0
