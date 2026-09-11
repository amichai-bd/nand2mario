; Original game flow. No routine writes VRAM or changes the LCD clock.
SECTION "interactions",ROM
; A reset clears the lives and the stage; a stage entry keeps both.
InitGame:
XOR A,A
LD [StageIndex],A
LD [PendingLife],A
LD A,2
LD [Lives],A
EnterStage:
LD A,[Buttons]
PUSH AF
CALL InitPlayer
XOR A,A
LD [Score],A
LD [Collected],A
LD [GameTimer],A
LD [GameTimer+1],A
LD HL,StageEnemyStart
CALL StageWordHL
LD A,E
LD [EnemyX],A
LD A,D
LD [EnemyX+1],A
LD A,8
LD [EnemyVX],A
LD HL,PowerState
LD B,38
XOR A,A
InitPowerLoop:
LD [HL+],A
DEC B
JR NZ,InitPowerLoop
INC A
LD [EnemyAlive],A
LD [GameMode],A
LD [NewLevel],A
CALL ResetStageTimer
POP AF
LD [Buttons],A
LD [Previous],A
LD [GamePrevious],A
RET

UpdateGame:
LD A,[GamePrevious]
CPL
LD B,A
LD A,[Buttons]
AND A,B
LD [Pressed],A
LD A,[Buttons]
LD [GamePrevious],A
LD A,[GameMode]
CP A,3
JP Z,PausedInput
CP A,2
JP Z,RetryInput
CP A,5
JP Z,RetryInput
CP A,4
JP Z,ClearInput
CP A,6
JP Z,OverInput
OR A,A
JR Z,StartInput
LD A,[Pressed]
AND A,$80
JR Z,UpdateWorld
LD A,3
LD [GameMode],A
JR RememberIdle
PausedInput:
LD A,[Pressed]
AND A,$40
JP NZ,InitGame
LD A,[Pressed]
AND A,$80
JR Z,RememberIdle
LD A,1
LD [GameMode],A
RememberIdle:
; Sampling during pause prevents a held A from becoming a queued jump.
LD A,[Buttons]
LD [Previous],A
RET
; A transition consumes its own A edge, so one held press never crosses two.
RetryInput:
LD A,[Pressed]
AND A,$80
RET Z
LD A,$FF
LD [PendingLife],A
CALL UpdateLives
OR A,A
RET Z
JP EnterStage
ClearInput:
LD A,[Pressed]
AND A,$80
RET Z
LD A,[StageIndex]
CP A,2
JP NC,InitGame
INC A
LD [StageIndex],A
JP EnterStage
OverInput:
LD A,[Pressed]
AND A,$80
RET Z
JP InitGame
StartInput:
LD A,[Pressed]
AND A,$80
RET Z
LD A,1
LD [GameMode],A

UpdateWorld:
CALL PowerTimers
CALL BlockTimers
CALL CheckTimeUp
OR A,A
JP NZ,RememberIdle
CALL TickTimer
CALL PowerInput
CALL StepPlayer
CALL ResolveBlockHit
LD A,[EnemyAlive]
OR A,A
CALL NZ,StepEnemy
CALL StepShot
LD HL,GameTimer
INC [HL]
JR NZ,CheckDeath
INC HL
INC [HL]
CheckDeath:
LD A,[Fell]
OR A,A
JR NZ,EnterRetry
LD A,[EnemyAlive]
OR A,A
JR Z,CollectItems
LD A,[EnemyX]
LD [ObjectX],A
LD A,[EnemyX+1]
LD [ObjectX+1],A
LD A,$80
LD [ObjectY],A
LD [ObjectHeight],A
LD A,7
LD [ObjectY+1],A
XOR A,A
LD [ObjectHeight+1],A
CALL OverlapObject
OR A,A
JR Z,CollectItems
CALL EnemyContact
OR A,A
JR Z,CollectItems
EnterRetry:
LD A,2
LD [GameMode],A
RET

CollectItems:
LD HL,StageItems
CALL StageWordHL
LD B,4
CollectNext:
LD A,[DE]
INC DE
LD [ObjectMask],A
LD C,A
LD A,[Collected]
AND A,C
JR NZ,SkipItem
LD A,[DE]
INC DE
LD [ObjectX],A
LD A,[DE]
INC DE
LD [ObjectX+1],A
LD A,[DE]
INC DE
LD [ObjectY],A
LD A,[DE]
INC DE
LD [ObjectY+1],A
PUSH BC
PUSH DE
CALL OverlapObject
OR A,A
JR Z,ItemDone
LD A,[ObjectMask]
LD B,A
LD A,[Collected]
OR A,B
LD [Collected],A
LD HL,Score
INC [HL]
ItemDone:
POP DE
POP BC
JR ItemAdvance
SkipItem:
INC DE
INC DE
INC DE
INC DE
ItemAdvance:
DEC B
JR NZ,CollectNext
; The goal is checked only after death and once-only collection.
CALL StageGoalBox
XOR A,A
LD [ObjectHeight],A
LD A,1
LD [ObjectHeight+1],A
CALL OverlapObject
OR A,A
RET Z
LD A,4
LD [GameMode],A
RET

StepEnemy:
LD A,[EnemyVX]
LD E,A
LD D,0
BIT 7,E
JR Z,EnemyDelta
DEC D
EnemyDelta:
LD A,[EnemyX]
LD L,A
LD A,[EnemyX+1]
LD H,A
ADD HL,DE
PUSH HL
LD HL,StageEnemyHi
CALL StageWordHL
POP HL
LD A,H
CP A,D
JR C,EnemyLeftTest
JR NZ,EnemyRight
LD A,L
CP A,E
JR C,EnemyLeftTest
EnemyRight:
LD H,D
LD L,E
LD A,$F8
LD [EnemyVX],A
JR SaveEnemy
EnemyLeftTest:
PUSH HL
LD HL,StageEnemyLo
CALL StageWordHL
POP HL
LD A,H
CP A,D
JR C,EnemyLeft
JR NZ,SaveEnemy
LD A,L
CP A,E
JR Z,EnemyLeft
JR NC,SaveEnemy
EnemyLeft:
LD H,D
LD L,E
LD A,8
LD [EnemyVX],A
SaveEnemy:
LD A,L
LD [EnemyX],A
LD A,H
LD [EnemyX+1],A
RET

; Half-open fixed-point AABB against the contact box. All objects are eight pixels wide.
OverlapObject:
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
JR C,NoOverlap
JR Z,NoOverlap
LD H,D
LD L,E
LD DE,128
ADD HL,DE
LD A,[PlayerX]
LD E,A
LD A,[PlayerX+1]
LD D,A
CALL CompareSigned
JR C,NoOverlap
JR Z,NoOverlap
LD A,[PlayerY]
LD L,A
LD A,[PlayerY+1]
LD H,A
LD DE,256
ADD HL,DE
LD A,[ObjectY]
LD E,A
LD A,[ObjectY+1]
LD D,A
CALL CompareSigned
JR C,NoOverlap
JR Z,NoOverlap
LD H,D
LD L,E
LD A,[ObjectHeight]
LD E,A
LD A,[ObjectHeight+1]
LD D,A
ADD HL,DE
LD A,[PlayerY]
LD E,A
LD A,[PlayerY+1]
LD D,A
CALL ContactTop
CALL CompareSigned
JR C,NoOverlap
JR Z,NoOverlap
LD A,1
RET
NoOverlap:
XOR A,A
RET

; Signed HL versus DE; carry means less, zero means equal.
CompareSigned:
LD A,H
XOR A,$80
LD B,A
LD A,D
XOR A,$80
LD C,A
LD A,B
CP A,C
RET NZ
LD A,L
CP A,E
RET
