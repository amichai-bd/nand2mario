; One sampled update per frame; publish the previous prepared scene in VBlank.
SECTION "code",ROM
Start:
DI
LD SP,$DFFE
XOR A,A
LDH [$FF40],A
LDH [$FF0F],A
LD [$FFFF],A
CALL InitSceneDMA
XOR A,A
LDH [$FF42],A
LDH [$FF43],A
LD [Buttons],A
CALL InitGame
XOR A,A
LD [GameMode],A
LD [NewLevel],A
LD [TitleCleared],A
LD [OldCameraTile],A
LD A,32
LD [MapRestoreColumn],A
LD HL,$FE00
LD B,160
XOR A,A
ClearObjects:
LD [HL+],A
DEC B
JR NZ,ClearObjects
LD DE,Tiles
LD HL,$8000
LD BC,$04A0
CopyTiles:
LD A,[DE]
INC DE
LD [HL+],A
DEC BC
LD A,B
OR A,C
JR NZ,CopyTiles
LD DE,TitleMap
LD HL,$9800
LD BC,$0240
CopyMap:
LD A,[DE]
INC DE
LD [HL+],A
DEC BC
LD A,B
OR A,C
JR NZ,CopyMap
LD A,$E4
LDH [$FF47],A
LDH [$FF48],A
CALL InitHUD
CALL PrepareScene
CALL PrepareHUD
CALL PrepareMap
CALL PublishHUD
CALL PublishScene
XOR A,A
LD [FramePending],A
LD [PublishedCamera],A
LDH [$FF0F],A
LD A,15
LDH [$FF45],A
LD A,$40
LDH [$FF41],A
LD A,3
LD [$FFFF],A
LD A,$91
LDH [$FF40],A
EI
WaitFrame:
; DI closes the token-check/HALT race; EI takes effect after HALT.
DI
LD A,[FramePending]
OR A,A
JR NZ,ConsumeFrame
EI
HALT
JR WaitFrame
ConsumeFrame:
XOR A,A
LD [FramePending],A
EI
CALL ReadButtons
; Game variables and SceneBuffer still describe the preceding prepared scene.
LD A,[GameMode]
OR A,A
JR Z,PublishFrame
LD A,[NewLevel]
OR A,A
JR Z,ContinueMap
XOR A,A
LD [NewLevel],A
LD A,[TitleCleared]
OR A,A
JR NZ,RestartMap
CALL ClearTitle
LD A,1
LD [TitleCleared],A
RestartMap:
CALL BeginMapRestore
ContinueMap:
LD A,[MapRestoreColumn]
CP A,32
JR NC,StreamFrame
CALL RestoreMapPair
JR PublishFrame
StreamFrame:
CALL StreamMap
PublishFrame:
LD A,[Camera]
LD [PublishedCamera],A
CALL PublishHUD
; No interrupt entry or stack access may overlap OAM bus ownership.
DI
CALL PublishScene
EI
; Only the specified line15 STAT split writes display registers during visible time.
WaitVisible:
LDH A,[$FF44]
CP A,144
JR NC,WaitVisible
LD A,[GameMode]
OR A,A
JR NZ,UpdateActive
CALL UpdateGame
LD A,[GameMode]
OR A,A
JR Z,PrepareFrame
LD A,1
LD [NewLevel],A
JR PrepareFrame
UpdateActive:
CALL UpdateGame
PrepareFrame:
CALL PrepareScene
CALL PrepareHUD
CALL PrepareMap
JP WaitFrame

ClearTitle:
; These rows disappear with the published transition out of title.
LD HL,$98A4
LD B,$0B
ClearName:
XOR A,A
LD [HL+],A
DEC B
JR NZ,ClearName
LD HL,$98E4
LD B,$0B
ClearPrompt:
XOR A,A
LD [HL+],A
DEC B
JR NZ,ClearPrompt
RET
EXPORT Start
SECTION "assets",ROM
Tiles:
ASSET "Tiles"
CourierTiles:
ASSET "Courier"
TitleMap:
INCLUDE "map.asm"
INCLUDE "movement.asm"
INCLUDE "render.asm"
INCLUDE "world.asm"
INCLUDE "collision.asm"
INCLUDE "interactions.asm"
INCLUDE "map_restore.asm"
INCLUDE "scene.asm"
INCLUDE "stream.asm"
INCLUDE "hud.asm"
INCLUDE "columns.asm"
