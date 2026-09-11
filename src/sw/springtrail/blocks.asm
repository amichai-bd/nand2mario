; Original interactive block layer over the immutable terrain world.
; No routine here writes VRAM outside the LCD-off startup copy.
SECTION "blocks",ROM
; column, row, kind (0 item, 1 brick, 2 hidden), content (0 none, 1 coin,
; 2 mushroom, 3 star). Every block covers two columns and rows 10 and 11.
BlockTable:
DB 8,10,0,2
DB 18,10,1,0
DB 40,10,0,1
DB 64,10,2,3

; B = column, C = row. A = the covering block index with HL at its entry,
; or $FF when the cell is outside the table.
FindBlockCell:
LD HL,BlockTable
LD D,0
FindBlockNext:
LD A,[HL]
LD E,A
LD A,B
SUB A,E
CP A,2
JR NC,FindBlockStep
INC HL
LD A,[HL]
LD E,A
DEC HL
LD A,C
SUB A,E
CP A,2
JR C,FindBlockFound
FindBlockStep:
LD A,L
ADD A,4
LD L,A
LD A,H
ADC A,0
LD H,A
INC D
LD A,D
CP A,4
JR C,FindBlockNext
LD A,$FF
RET
FindBlockFound:
LD A,D
RET

; HL points at a collision cell. A=1 when the cell blocks movement.
; Terrain value 11 is never overridden, so the block layer only adds or
; removes solidity in rows 10 and 11. HL is preserved; BC and DE are not.
CellSolid:
LD A,[HL]
CP A,$0B
JR Z,CellSolidYes
LD A,H
SUB A,HIGH(CollisionMap)
CP A,10
JR C,CellSolidNo
CP A,12
JR NC,CellSolidNo
PUSH HL
LD C,A
LD A,L
LD B,A
CALL FindBlockCell
CP A,$FF
JR Z,CellSolidNoPop
LD C,A
LD B,0
PUSH HL
LD HL,BlockState
ADD HL,BC
LD A,[HL]
POP HL
LD C,A
INC HL
INC HL
LD A,[HL]
CP A,2
JR Z,CellSolidHidden
; An item or brick cell is solid until it is broken.
LD A,C
CP A,2
JR Z,CellSolidNoPop
JR CellSolidYesPop
CellSolidHidden:
LD A,C
OR A,A
JR NZ,CellSolidYesPop
; An intact hidden block exists only for the ascending head scan.
LD A,[ScanUp]
OR A,A
JR Z,CellSolidNoPop
CellSolidYesPop:
POP HL
CellSolidYes:
LD A,1
RET
CellSolidNoPop:
POP HL
CellSolidNo:
XOR A,A
RET

; The release effect rises one pixel per update and then clears.
BlockTimers:
LD A,[EffectTimer]
OR A,A
RET Z
DEC A
LD [EffectTimer],A
LD HL,EffectY
LD A,[HL]
SUB A,16
LD [HL+],A
LD A,[HL]
SBC A,0
LD [HL],A
LD A,[EffectTimer]
OR A,A
RET NZ
XOR A,A
LD [EffectTile],A
RET

; One head hit per update, consumed before every other contact.
ResolveBlockHit:
LD A,[HitValid]
OR A,A
RET Z
XOR A,A
LD [HitValid],A
LD A,[HitColumn]
LD B,A
LD A,[HitRow]
LD C,A
CALL FindBlockCell
CP A,$FF
RET Z
LD [BlockIndex],A
LD C,A
LD B,0
PUSH HL
LD HL,BlockState
ADD HL,BC
LD A,[HL]
POP HL
OR A,A
RET NZ
; HL is the entry of an intact block; only an intact block responds.
LD A,[HL+]
LD [EffectColumn],A
LD A,[HL+]
LD [EffectRow],A
LD A,[HL+]
LD C,A
LD A,[HL]
LD B,A
LD A,C
CP A,1
JR Z,ResolveBrick
LD A,B
CP A,1
JR Z,ResolveCoin
CP A,2
JR Z,ResolveMushroom
LD A,1
CALL SetBlockState
LD A,136
CALL BlockEffect
JP GrantStar
ResolveMushroom:
LD A,1
CALL SetBlockState
LD A,132
CALL BlockEffect
JP PowerUp
ResolveCoin:
LD A,1
CALL SetBlockState
LD A,128
CALL BlockEffect
LD A,[Coins]
INC A
RET Z
LD [Coins],A
RET
ResolveBrick:
; A brick breaks only while the player is large or thrower.
LD A,[PowerState]
OR A,A
RET Z
LD A,2
CALL SetBlockState
LD A,124
JP BlockEffect

; A = the new state stored at BlockIndex.
SetBlockState:
LD C,A
LD A,[BlockIndex]
LD L,A
LD H,0
LD DE,BlockState
ADD HL,DE
LD [HL],C
; Mark the block's two display columns so the next update republishes them.
LD A,[EffectColumn]
INC A
LD [BlockDirty],A
RET

; A = effect tile base; the effect starts at the block's top-left world pixel.
BlockEffect:
LD [EffectTile],A
LD A,[EffectColumn]
CALL BlockPixel
LD A,L
LD [EffectX],A
LD A,H
LD [EffectX+1],A
LD A,[EffectRow]
CALL BlockPixel
LD A,L
LD [EffectY],A
LD A,H
LD [EffectY+1],A
LD A,16
LD [EffectTimer],A
RET

; Tile index A to its top-left sixteenth-pixel coordinate in HL.
BlockPixel:
LD L,A
LD H,0
ADD HL,HL
ADD HL,HL
ADD HL,HL
ADD HL,HL
ADD HL,HL
ADD HL,HL
ADD HL,HL
RET

; C = block index. A = its tile base, 0 when it shows the blank background.
BlockAppearance:
LD B,0
LD HL,BlockState
ADD HL,BC
LD A,[HL]
LD E,A
LD HL,BlockTable+2
ADD HL,BC
ADD HL,BC
ADD HL,BC
ADD HL,BC
LD A,[HL]
LD D,A
LD A,E
CP A,2
JR Z,BlockBlank
LD A,D
OR A,A
JR Z,BlockItemTile
CP A,1
JR Z,BlockBrickTile
LD A,E
OR A,A
JR Z,BlockBlank
LD A,120
RET
BlockBrickTile:
LD A,116
RET
BlockItemTile:
LD A,E
OR A,A
LD A,108
RET Z
LD A,112
RET
BlockBlank:
XOR A,A
RET

; Overwrite the decoded column cache rows 8 and 9, which are world rows 10
; and 11, with the block layer's current appearance.
BlockOverride:
LD A,[DecodeBase]
LD E,A
LD A,[DecodeBase+1]
LD D,A
LD HL,BlockTable
LD C,0
BlockOverrideNext:
LD A,[HL]
LD B,A
LD A,[DecodeIndex]
SUB A,B
CP A,2
JR NC,BlockOverrideStep
LD [BlockSub],A
PUSH HL
PUSH DE
CALL BlockAppearance
POP DE
POP HL
OR A,A
JR Z,BlockOverrideStep
LD B,A
LD A,[BlockSub]
ADD A,B
PUSH HL
LD HL,8
ADD HL,DE
LD [HL],A
ADD A,2
INC L
LD [HL],A
POP HL
BlockOverrideStep:
LD A,L
ADD A,4
LD L,A
LD A,H
ADC A,0
LD H,A
INC C
LD A,C
CP A,4
JR C,BlockOverrideNext
RET

; Approved terrain atlas tiles 10..33 and 38..45 to free VRAM tiles 108..139,
; with the LCD off. Four eight-tile groups share the existing copy loop and
; DE runs on from 108 through 139.
InitBlockArt:
LD DE,$86C0
LD HL,TerrainTiles+$00A0
LD B,128
CALL MotionTileCopy
LD HL,TerrainTiles+$0120
LD B,128
CALL MotionTileCopy
LD HL,TerrainTiles+$01A0
LD B,128
CALL MotionTileCopy
LD HL,TerrainTiles+$0260
LD B,128
JP MotionTileCopy

; DE = next OAM slot; the four approved tiles form one 16 by 16 object.
ComposeEffect:
LD A,[EffectTile]
LD [SceneTile],A
XOR A,A
LD [PieceX],A
LD [PieceY],A
LD [PieceFlags],A
CALL EmitPiece
LD A,8
LD [PieceX],A
LD A,[EffectTile]
INC A
LD [SceneTile],A
CALL EmitPiece
XOR A,A
LD [PieceX],A
LD A,8
LD [PieceY],A
LD A,[EffectTile]
ADD A,2
LD [SceneTile],A
CALL EmitPiece
LD A,8
LD [PieceX],A
LD A,[EffectTile]
ADD A,3
LD [SceneTile],A
JP EmitPiece

SECTION "block_assets",ROM
TerrainTiles:
ASSET "Terrain"
