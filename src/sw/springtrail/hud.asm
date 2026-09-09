; Approved font selection and prepared BG HUD, with real split interrupts.
SECTION "hud",ROM
InitHUD:
LD HL,FontPointers
LD DE,$84A0
LD B,20
FontNext:
PUSH BC
LD A,[HL+]
LD C,A
LD A,[HL+]
LD B,A
PUSH HL
LD H,B
LD L,C
LD B,16
FontCopy:
LD A,[HL+]
LD [DE],A
INC DE
DEC B
JR NZ,FontCopy
POP HL
POP BC
DEC B
JR NZ,FontNext
LD HL,$9C00
LD B,64
XOR A,A
ClearSecondHUD:
LD [HL+],A
DEC B
JR NZ,ClearSecondHUD
; Static score label is identical in both maps.
LD HL,ScoreLabel
LD DE,$980C
CALL PublishLabel
LD HL,ScoreLabel
LD DE,$9C0C
CALL PublishLabel
RET
PublishLabel:
LD B,5
PublishLabelByte:
LD A,[HL+]
LD [DE],A
INC DE
DEC B
JR NZ,PublishLabelByte
RET
PrepareHUD:
LD A,[GameMode]
LD L,A
LD H,0
ADD HL,HL
LD BC,ModePointers
ADD HL,BC
LD A,[HL+]
LD C,A
LD A,[HL]
LD H,A
LD L,C
LD DE,HUDCache
LD B,6
PrepareHUDByte:
LD A,[HL+]
LD [DE],A
INC DE
DEC B
JR NZ,PrepareHUDByte
LD A,[Score]
ADD A,74
LD [DE],A
RET
PublishHUD:
LD HL,HUDCache
LD DE,$9801
CALL PublishHUDMap
LD HL,HUDCache
LD DE,$9C01
PublishHUDMap:
LD B,6
PublishHUDByte:
LD A,[HL+]
LD [DE],A
INC DE
DEC B
JR NZ,PublishHUDByte
LD E,$12
LD A,[HL]
LD [DE],A
RET
FontPointers:
DW CoreTiles+1312
DW CoreTiles+1328
DW CoreTiles+1344
DW CoreTiles+1360
DW CoreTiles+1376
DW CoreTiles+896
DW CoreTiles+928
DW CoreTiles+944
DW CoreTiles+960
DW CoreTiles+1024
DW CoreTiles+1072
DW CoreTiles+1104
DW CoreTiles+1120
DW CoreTiles+1136
DW CoreTiles+1168
DW CoreTiles+1184
DW CoreTiles+1200
DW CoreTiles+1216
DW CoreTiles+1248
DW CoreTiles+1280
ScoreLabel:
DB 89,80,86,88,82
ModePointers:
DW HUDMode0
DW HUDMode1
DW HUDMode2
DW HUDMode3
DW HUDMode4
HUDMode0:
DB 90,83,90,84,82,0
HUDMode1:
DB 87,84,79,93,0,0
HUDMode2:
DB 88,82,90,88,93,0
HUDMode3:
DB 87,79,91,89,82,81
HUDMode4:
DB 92,86,85,0,0,0

SECTION "irq",ROM
VBlankIRQ:
PUSH AF
XOR A,A
LDH [$FF43],A
LDH [$FF42],A
LDH A,[$FF40]
AND A,$FD
LDH [$FF40],A
LD A,1
LD [FramePending],A
POP AF
RETI
StatIRQ:
PUSH AF
StatWaitHBlank:
LDH A,[$FF41]
AND A,3
JR NZ,StatWaitHBlank
LD A,[PublishedCamera]
LDH [$FF43],A
LDH A,[$FF40]
OR A,2
LDH [$FF40],A
POP AF
RETI
SECTION "vb_vector",ROM
JP VBlankIRQ
SECTION "stat_vector",ROM
JP StatIRQ
SECTION "core_assets",ROM
CoreTiles:
ASSET "Core"
