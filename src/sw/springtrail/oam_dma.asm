; Shared game/fixture publisher. Caller owns the complete C100-C19F image.
InitSceneDMA:
LD HL,SceneDMACode
LD DE,$FF80
LD B,9
CopySceneDMA:
LD A,[HL+]
LD [DE],A
INC DE
DEC B
JR NZ,CopySceneDMA
RET

PublishScene:
LD A,$C1
CALL $FF80
RET

; Executed at FF80. CALL has already pushed its return before FF46 starts.
; Forty 20-dot loop iterations keep every fetch in HRAM beyond all 160 bytes.
SceneDMACode:
LDH [$FF46],A
LD B,40
SceneDMAWait:
NOP
DEC B
JR NZ,SceneDMAWait
RET
