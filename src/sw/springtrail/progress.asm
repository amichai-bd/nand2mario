; Original lives, countdown timer and three-stage progression.
; Every rule and constant here is frozen in wiki PROGRESS.md.
SECTION "progress",ROM

; Stage-indexed tables. One table per bound keeps each value in one place.
StageBases:
DB 0,96,176
StageColumnsTable:
DB 96,80,80
StageTimerHighTable:
DB 4,3,2
StageCameraMax:
DW $0260,$01E0,$01E0
StageXMax:
DW $2F80,$2780,$2780
StageGoalX:
DW $2E00,$2600,$2600
StageEnemyStart:
DW $1000,$1000,$1200
StageEnemyLo:
DW $0F00,$0F00,$1100
StageEnemyHi:
DW $1280,$1280,$1480
StageItems:
DW Items0,Items1,Items2
Items0:
DB 1,$00,$06,$80,$05
DB 2,$80,$10,$80,$04
DB 4,$00,$1D,$80,$05
DB 8,$00,$29,$00,$05
Items1:
DB 1,$00,$05,$00,$05
DB 2,$00,$10,$80,$04
DB 4,$00,$1B,$00,$04
DB 8,$00,$24,$80,$05
Items2:
DB 1,$00,$04,$80,$05
DB 2,$00,$0D,$00,$05
DB 4,$00,$14,$80,$04
DB 8,$00,$1C,$00,$04

; HL points at a three-byte table; A becomes its entry for the current stage.
; Only A and HL change, so callers may hold a column or a pointer in BC or DE.
StageByteHL:
LD A,[StageIndex]
ADD A,L
LD L,A
LD A,0
ADC A,H
LD H,A
LD A,[HL]
RET

; HL points at a three-word table; DE becomes its entry for the current stage.
StageWordHL:
LD A,[StageIndex]
ADD A,A
ADD A,L
LD L,A
LD A,0
ADC A,H
LD H,A
LD A,[HL+]
LD E,A
LD A,[HL]
LD D,A
RET

StageBaseColumn:
LD HL,StageBases
JR StageByteHL

StageColumnCount:
LD HL,StageColumnsTable
JR StageByteHL

; HL becomes the stage's inclusive player x limit in sixteenth pixels.
StageXLimit:
LD HL,StageXMax
CALL StageWordHL
LD H,D
LD L,E
RET

; DE becomes the stage's inclusive camera limit; HL is preserved.
StageCameraLimit:
PUSH HL
LD HL,StageCameraMax
CALL StageWordHL
POP HL
RET

; A selects one of the four stage item boxes into ObjectX/ObjectY. DE is kept
; because scene preparation holds the shadow-page write pointer there.
StageItemBox:
PUSH DE
LD C,A
LD HL,StageItems
CALL StageWordHL
LD A,C
LD L,A
LD H,0
ADD HL,HL
ADD HL,HL
LD A,C
ADD A,L
LD L,A
LD A,0
ADC A,H
LD H,A
ADD HL,DE
INC HL
LD A,[HL+]
LD [ObjectX],A
LD A,[HL+]
LD [ObjectX+1],A
LD A,[HL+]
LD [ObjectY],A
LD A,[HL]
LD [ObjectY+1],A
POP DE
RET

; The stage goal box top-left; its height belongs to each caller.
StageGoalBox:
PUSH DE
LD HL,StageGoalX
CALL StageWordHL
LD A,E
LD [ObjectX],A
LD A,D
LD [ObjectX+1],A
XOR A,A
LD [ObjectY],A
LD A,7
LD [ObjectY+1],A
POP DE
RET

; Stage entry timer: forty PLAY updates per unit and the stage start value.
ResetStageTimer:
LD A,40
LD [TimerSub],A
XOR A,A
LD [TimerLow],A
LD [Expiring],A
LD HL,StageTimerHighTable
CALL StageByteHL
LD [TimerHigh],A
RET

; One PLAY update of the countdown. A full unit passes every forty updates;
; the packed BCD value never underflows and the grade is recomputed after it.
TickTimer:
LD A,[TimerSub]
DEC A
LD [TimerSub],A
RET NZ
LD A,40
LD [TimerSub],A
LD A,[TimerLow]
LD B,A
LD A,[TimerHigh]
OR A,B
RET Z
LD A,[TimerLow]
SUB A,1
DAA
LD [TimerLow],A
JR NC,GradeTimer
LD A,[TimerHigh]
SUB A,1
DAA
LD [TimerHigh],A
GradeTimer:
LD A,[TimerHigh]
OR A,A
JR NZ,GradeNormal
LD A,[TimerLow]
OR A,A
JR Z,GradeZero
CP A,$50
JR NC,GradeLow
LD A,2
JR SaveGrade
GradeLow:
LD A,1
JR SaveGrade
GradeZero:
LD A,3
JR SaveGrade
GradeNormal:
XOR A,A
SaveGrade:
LD [Expiring],A
RET

; The grade is raised on one update and consumed on the next, so an expired
; timer ends the update before input, motion and every contact class.
CheckTimeUp:
LD A,[Expiring]
CP A,3
JR Z,EnterTimeUp
XOR A,A
RET
EnterTimeUp:
LD A,$FF
LD [Expiring],A
LD A,5
LD [GameMode],A
LD A,1
RET

; Apply one pending life request. A returns 1 when play may continue and 0
; when the removal ended the game. The request is always cleared.
UpdateLives:
LD A,[PendingLife]
OR A,A
JR Z,LivesUnchanged
CP A,$FF
JR Z,LoseLife
LD A,[Lives]
CP A,$99
JR Z,LivesApplied
ADD A,1
DAA
LD [Lives],A
JR LivesApplied
LoseLife:
LD A,[Lives]
OR A,A
JR Z,NoLivesLeft
SUB A,1
DAA
LD [Lives],A
LivesApplied:
XOR A,A
LD [PendingLife],A
LivesUnchanged:
LD A,1
RET
NoLivesLeft:
XOR A,A
LD [PendingLife],A
LD A,6
LD [GameMode],A
XOR A,A
RET

; Approved core glyph for one decimal digit; 74..78 then 140..144.
GlyphDigit:
CP A,5
JR C,GlyphLow
ADD A,135
RET
GlyphLow:
ADD A,74
RET

; Row1 values prepared during visible time, published with the row0 cache.
PrepareProgress:
LD HL,ProgressCache
LD A,[Lives]
SWAP A
AND A,$0F
CALL GlyphDigit
LD [HL+],A
LD A,[Lives]
AND A,$0F
CALL GlyphDigit
LD [HL+],A
LD A,[TimerHigh]
AND A,$0F
CALL GlyphDigit
LD [HL+],A
LD A,[TimerLow]
SWAP A
AND A,$0F
CALL GlyphDigit
LD [HL+],A
LD A,[TimerLow]
AND A,$0F
CALL GlyphDigit
LD [HL+],A
LD A,[StageIndex]
INC A
CALL GlyphDigit
LD [HL],A
RET

PublishProgress:
LD HL,ProgressCache
LD DE,$9822
CALL PublishProgressMap
LD HL,ProgressCache
LD DE,$9C22
PublishProgressMap:
LD A,[HL+]
LD [DE],A
INC DE
LD A,[HL+]
LD [DE],A
LD A,E
ADD A,10
LD E,A
LD A,[HL+]
LD [DE],A
INC DE
LD A,[HL+]
LD [DE],A
INC DE
LD A,[HL+]
LD [DE],A
LD A,E
ADD A,3
LD E,A
LD A,[HL]
LD [DE],A
RET

; Nine approved core tiles after the block terrain copies at 108..139, then
; the static icons; the block layer merged first and owns that range.
InitProgressArt:
LD HL,ProgressPointers
LD DE,$88C0
LD B,9
ProgressNext:
PUSH BC
LD A,[HL+]
LD C,A
LD A,[HL+]
LD B,A
PUSH HL
LD H,B
LD L,C
LD B,16
ProgressCopy:
LD A,[HL+]
LD [DE],A
INC DE
DEC B
JR NZ,ProgressCopy
POP HL
POP BC
DEC B
JR NZ,ProgressNext
LD A,147
LD [$9821],A
LD [$9C21],A
LD A,148
LD [$982C],A
LD [$9C2C],A
RET
ProgressPointers:
DW CoreTiles+1392
DW CoreTiles+1408
DW CoreTiles+1424
DW CoreTiles+1440
DW CoreTiles+1456
DW CoreTiles+1088
DW CoreTiles+1232
DW CoreTiles+832
DW CoreTiles+848
EXPORT UpdateLives
EXPORT TickTimer
