; Complete 8x8 scene in the aligned shadow page; publisher remains shared.
SECTION "scene",ROM
PrepareScene:
LD DE,SceneBuffer
CALL SelectCourier
LD A,[PlayerX]
LD [ObjectX],A
LD A,[PlayerX+1]
LD [ObjectX+1],A
LD A,[PlayerY]
LD [ObjectY],A
LD A,[PlayerY+1]
LD [ObjectY+1],A
CALL PowerHidden
LD [SceneHidden],A
CALL ScenePosition
; Center approved 16-wide artwork on the existing 8-wide collision box.
LD A,[SceneBaseX]
SUB A,4
LD [SceneBaseX],A
LD A,[SceneBaseX+1]
SBC A,0
LD [SceneBaseX+1],A
CALL ComposeCourier
CALL ComposePatrol
LD A,0
CALL StageItemBox
LD A,[Collected]
AND A,1
LD [SceneHidden],A
LD A,18
LD [SceneTile],A
CALL AppendScene
LD A,1
CALL StageItemBox
LD A,[Collected]
AND A,2
LD [SceneHidden],A
LD A,18
LD [SceneTile],A
CALL AppendScene
LD A,2
CALL StageItemBox
LD A,[Collected]
AND A,4
LD [SceneHidden],A
LD A,18
LD [SceneTile],A
CALL AppendScene
LD A,3
CALL StageItemBox
LD A,[Collected]
AND A,8
LD [SceneHidden],A
LD A,18
LD [SceneTile],A
CALL AppendScene
CALL StageGoalBox
XOR A,A
LD [SceneHidden],A
LD A,20
LD [SceneTile],A
CALL AppendScene
; One live shot follows the goal as a single approved 8x8 piece.
LD A,[ShotTTL]
OR A,A
JR Z,SceneEffect
LD A,[ShotX]
LD [ObjectX],A
LD A,[ShotX+1]
LD [ObjectX+1],A
LD A,[ShotY]
LD [ObjectY],A
LD A,[ShotY+1]
LD [ObjectY+1],A
XOR A,A
LD [SceneHidden],A
LD [PieceX],A
LD [PieceY],A
LD [PieceFlags],A
LD A,107
LD [SceneTile],A
CALL ScenePosition
CALL EmitPiece
; One 16 by 16 release effect follows the shot while it is live.
SceneEffect:
LD A,[EffectTile]
OR A,A
JR Z,SceneTail
LD A,[EffectX]
LD [ObjectX],A
LD A,[EffectX+1]
LD [ObjectX+1],A
LD A,[EffectY]
LD [ObjectY],A
LD A,[EffectY+1]
LD [ObjectY+1],A
XOR A,A
LD [SceneHidden],A
CALL ScenePosition
CALL ComposeEffect
; Remaining OAM bytes are inactive; mode/score now belong to the BG HUD.
SceneTail:
CALL ComposeOtherEntities
LD A,E
CP A,$A0
RET Z
XOR A,A
ClearSceneByte:
LD [DE],A
INC DE
LD A,E
CP A,$A0
JR Z,SceneComplete
XOR A,A
JR ClearSceneByte
SceneComplete:
RET

AppendScene:
CALL ScenePosition
JP EmitPair

ScenePosition:
; Signed Q4 floor and full-width camera subtraction, before OAM wrapping.
LD A,[ObjectX]
LD L,A
LD A,[ObjectX+1]
LD H,A
CALL PixelFloor
LD A,[Camera]
LD C,A
LD A,[Camera+1]
LD B,A
LD A,L
SUB A,C
LD [SceneBaseX],A
LD A,H
SBC A,B
LD [SceneBaseX+1],A
LD A,[ObjectY]
LD L,A
LD A,[ObjectY+1]
LD H,A
CALL PixelFloor
LD A,L
LD [SceneBaseY],A
LD A,H
LD [SceneBaseY+1],A
RET

INCLUDE "oam_dma.asm"
INCLUDE "courier.asm"
