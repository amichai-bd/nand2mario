INCLUDE "state.asm"
SECTION "code",ROM
Start:
DI
LD SP,$DFFE
XOR A,A
LDH [$FF40],A
LDH [$FF0F],A
LD [$FFFF],A
; The title page lives in the map rows and columns the play view never shows.
LD A,128
LDH [$FF42],A
LD A,160
LDH [$FF43],A
XOR A,A
LD HL,$C000
LD BC,$0300
ClearMemory:
LD [HL+],A
DEC BC
LD A,B
OR A,C
JR Z,MemoryReady
XOR A,A
JR ClearMemory
MemoryReady:
LD DE,Tiles
LD HL,$8000
LD BC,1648
CopyTiles:
LD A,[DE]
INC DE
LD [HL+],A
DEC BC
LD A,B
OR A,C
JR NZ,CopyTiles
LD DE,Map
LD HL,$9800
LD BC,1024
CopyMap:
LD A,[DE]
INC DE
LD [HL+],A
DEC BC
LD A,B
OR A,C
JR NZ,CopyMap
CALL Prepare
CALL Render
LD A,$E4
LDH [$FF47],A
LD A,1
LD [$FFFF],A
LD A,$91
LDH [$FF40],A
; Decide before HALT, in visible time, whether the LCD still shows the title
; page after the game has started; the scroll then changes in the VBlank that
; copies the first playing image, after the unchanged 4472-dot copy bracket.
Frame:
XOR A,A
LDH [$FF0F],A
LD A,[Page]
OR A,A
JR NZ,FrameWait
LD A,[Status]
OR A,A
JR NZ,FrameScroll
FrameWait:
HALT
CALL ReadButtons
CALL Render
FrameUpdate:
CALL Update
CALL Prepare
JR Frame
FrameScroll:
HALT
CALL ReadButtons
CALL Render
XOR A,A
LDH [$FF42],A
LDH [$FF43],A
INC A
LD [Page],A
JR FrameUpdate
EXPORT Start
INCLUDE "rules.asm"
INCLUDE "render.asm"
INCLUDE "tables.asm"

