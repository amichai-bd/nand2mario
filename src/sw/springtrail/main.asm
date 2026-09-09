; Original Springtrail game. One movement/render update per VBlank.
SECTION "code",ROM
Start:
DI
LD SP,$DFFE
XOR A,A
LDH [$FF40],A
LDH [$FF0F],A
LD [$FFFF],A
LDH [$FF42],A
LDH [$FF43],A
LD [$C000],A
LD [OldCameraTile],A
CALL InitPlayer
LD HL,$FE00
LD B,160
XOR A,A
ClearObjects:
LD [HL+],A
DEC B
JR NZ,ClearObjects
LD DE,Tiles
LD HL,$8000
LD BC,$02A0
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
CALL RenderPlayer
LD A,$01
LD [$FFFF],A
LD A,$97
LDH [$FF40],A
WaitFrame:
XOR A,A
LDH [$FF0F],A
HALT
CALL ReadButtons
LD A,[$C000]
OR A,A
JR Z,TitleInput
CP A,2
JR Z,WaitFrame
JR PlayFrame
TitleInput:
LD A,[Buttons]
AND A,$80
JR Z,WaitFrame
; Erase the two eleven-character title rows within this VBlank.
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
LD A,$01
LD [$C000],A
PlayFrame:
CALL StepPlayer
CALL RenderPlayer
LD A,[Fell]
OR A,A
JR Z,WaitFrame
LD A,2
LD [$C000],A
JR WaitFrame
EXPORT Start
SECTION "assets",ROM
Tiles:
ASSET "Tiles"
TitleMap:
INCLUDE "map.asm"
INCLUDE "movement.asm"
INCLUDE "render.asm"
INCLUDE "world.asm"
INCLUDE "collision.asm"
INCLUDE "interactions.asm"
INCLUDE "map_restore.asm"
INCLUDE "scene.asm"
