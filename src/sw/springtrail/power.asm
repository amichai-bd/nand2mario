; Original contact/power rules. No routine writes VRAM or reads DUT results.
SECTION "power",ROM
; Timers advance before input, motion and contact each PLAY update.
PowerTimers:
LD A,[PowerTimer]
OR A,A
JR Z,PowerInvincible
DEC A
LD [PowerTimer],A
JR NZ,PowerInvincible
LD A,[PowerPhase]
CP A,2
JR NZ,PowerPhaseClear
; HURT ends into the SAFE window; GROW and SAFE end into normal.
LD A,3
LD [PowerPhase],A
LD A,96
LD [PowerTimer],A
JR PowerInvincible
PowerPhaseClear:
XOR A,A
LD [PowerPhase],A
PowerInvincible:
LD A,[Invincible]
OR A,A
JR Z,PowerThrowTimer
DEC A
LD [Invincible],A
PowerThrowTimer:
LD A,[ThrowTimer]
OR A,A
RET Z
DEC A
LD [ThrowTimer],A
RET

; Crouch is decided before motion and masks Left/Right for this update.
PowerInput:
XOR A,A
LD [Crouch],A
LD A,[PowerState]
OR A,A
JR Z,PowerThrow
LD A,[JumpState]
OR A,A
JR NZ,PowerThrow
LD A,[Grounded]
OR A,A
JR Z,PowerThrow
LD A,[Buttons]
BIT 3,A
JR Z,PowerThrow
AND A,$FC
LD [Buttons],A
LD A,1
LD [Crouch],A
RET
PowerThrow:
LD A,[PowerState]
CP A,2
RET NZ
LD A,[ShotTTL]
OR A,A
RET NZ
LD A,[Pressed]
BIT 5,A
RET Z
LD A,[PlayerX]
LD [ShotX],A
LD A,[PlayerX+1]
LD [ShotX+1],A
LD A,[PlayerY]
ADD A,64
LD [ShotY],A
LD A,[PlayerY+1]
ADC A,0
LD [ShotY+1],A
LD A,[MotionFacing]
OR A,A
LD A,32
JR Z,PowerShotRight
LD A,$E0
PowerShotRight:
LD [ShotVX],A
LD A,32
LD [ShotVY],A
LD A,64
LD [ShotTTL],A
LD A,8
LD [ThrowTimer],A
RET

; Each shot axis moves separately; a solid leading tile cancels and reverses.
StepShot:
LD A,[ShotTTL]
OR A,A
RET Z
LD A,[ShotVX]
CALL ShotDelta
LD A,[ShotX]
LD L,A
LD A,[ShotX+1]
LD H,A
ADD HL,DE
PUSH HL
BIT 7,D
JR NZ,ShotXLead
LD DE,$007F
ADD HL,DE
ShotXLead:
CALL TileIndex
LD [Column],A
LD A,[ShotY]
LD L,A
LD A,[ShotY+1]
LD H,A
CALL ShotSpan
CALL ShotSolid
POP HL
OR A,A
JR Z,ShotSaveX
LD A,[ShotVX]
CPL
INC A
LD [ShotVX],A
JR ShotYAxis
ShotSaveX:
LD A,L
LD [ShotX],A
LD A,H
LD [ShotX+1],A
ShotYAxis:
LD A,[ShotVY]
CALL ShotDelta
LD A,[ShotY]
LD L,A
LD A,[ShotY+1]
LD H,A
ADD HL,DE
PUSH HL
BIT 7,D
JR NZ,ShotYLead
LD DE,$007F
ADD HL,DE
ShotYLead:
CALL TileIndex
LD [Row],A
LD A,[ShotX]
LD L,A
LD A,[ShotX+1]
LD H,A
PUSH HL
CALL TileIndex
LD [Column],A
POP HL
LD DE,$007F
ADD HL,DE
CALL TileIndex
LD [LastCell],A
CALL ShotSolidColumns
POP HL
OR A,A
JR Z,ShotSaveY
LD A,[ShotVY]
CPL
INC A
LD [ShotVY],A
JR ShotBounds
ShotSaveY:
LD A,L
LD [ShotY],A
LD A,H
LD [ShotY+1],A
ShotBounds:
LD A,[ShotX+1]
BIT 7,A
JR NZ,ShotRemove
CP A,$2F
JR C,ShotBoundsY
JR NZ,ShotRemove
LD A,[ShotX]
CP A,$80
JR NC,ShotRemove
ShotBoundsY:
LD A,[ShotY+1]
BIT 7,A
JR NZ,ShotRemove
CP A,$09
JR NC,ShotRemove
LD A,[ShotTTL]
DEC A
LD [ShotTTL],A
JR Z,ShotRemove
LD A,[EnemyAlive]
OR A,A
RET Z
; 8x8 half-open overlap: (shot - enemy + 128) must lie in 1..255.
LD A,[ShotX]
LD L,A
LD A,[ShotX+1]
LD H,A
LD A,[EnemyX]
LD E,A
LD A,[EnemyX+1]
LD D,A
CALL ShotOffset
RET NZ
LD A,[ShotY]
LD L,A
LD A,[ShotY+1]
LD H,A
LD DE,$0780
CALL ShotOffset
RET NZ
XOR A,A
LD [EnemyAlive],A
; A removed shot clears all seven bytes so state stays literal.
ShotRemove:
XOR A,A
LD HL,ShotX
LD B,7
ShotClear:
LD [HL+],A
DEC B
JR NZ,ShotClear
RET

; Signed byte velocity in A to DE.
ShotDelta:
LD E,A
LD D,0
BIT 7,E
RET Z
DEC D
RET

; HL = shot edge coordinate; store its tile index in Row and HL+7px in LastCell.
ShotSpan:
PUSH HL
CALL TileIndex
LD [Row],A
POP HL
LD DE,$007F
ADD HL,DE
CALL TileIndex
LD [LastCell],A
RET

; Zero flag set when HL-DE+128 lies in 1..255, meaning the boxes overlap.
ShotOffset:
LD A,L
SUB A,E
LD L,A
LD A,H
SBC A,D
LD H,A
LD DE,128
ADD HL,DE
LD A,H
OR A,A
RET NZ
LD A,L
OR A,A
JR NZ,ShotOffsetHit
INC A
RET
ShotOffsetHit:
XOR A,A
RET

; A=1 when any collision cell in Column at rows Row..LastCell is solid.
ShotSolid:
LD A,[Row]
CP A,18
JR NC,ShotSolidNext
CALL CollisionPointer
LD A,[HL]
CP A,$0B
JR Z,ShotSolidYes
ShotSolidNext:
LD A,[LastCell]
LD B,A
LD A,[Row]
CP A,B
JR Z,ShotSolidNo
INC A
LD [Row],A
JR ShotSolid
ShotSolidYes:
LD A,1
RET
ShotSolidNo:
XOR A,A
RET

; A=1 when any cell in Row at columns Column..LastCell is solid.
ShotSolidColumns:
LD A,[Row]
CP A,18
JR NC,ShotSolidNo
CALL CollisionPointer
ShotSolidColumn:
LD A,[HL]
CP A,$0B
JR Z,ShotSolidYes
LD A,[LastCell]
LD B,A
LD A,[Column]
CP A,B
JR Z,ShotSolidNo
INC A
LD [Column],A
INC L
JR ShotSolidColumn

; Called with the enemy alive and its box overlapping the contact box.
; A=1 requests retry.
EnemyContact:
LD A,[Invincible]
OR A,A
JR NZ,EnemyDies
; Stomp: floor((y+256)/16) - 120 <= 4, so y < $06D0 while overlapping.
LD A,[PlayerY+1]
CP A,$06
JR C,StompEnemy
JR NZ,SideHit
LD A,[PlayerY]
CP A,$D0
JR NC,SideHit
StompEnemy:
XOR A,A
LD [Grounded],A
LD [SavedJumpIndex],A
INC A
LD [JumpState],A
LD A,13
LD [JumpIndex],A
LD A,4
LD [MotionPose],A
EnemyDies:
XOR A,A
LD [EnemyAlive],A
RET
SideHit:
LD A,[PowerPhase]
CP A,2
JR NC,ContactIgnored
LD A,[PowerState]
OR A,A
JR Z,ContactFatal
XOR A,A
LD [PowerState],A
LD [ThrowTimer],A
LD A,2
LD [PowerPhase],A
LD A,32
LD [PowerTimer],A
ContactIgnored:
XOR A,A
RET
ContactFatal:
LD A,1
RET

; DE = contact box top: 2 pixels above the terrain box when large and standing.
ContactTop:
LD A,[PowerState]
OR A,A
RET Z
LD A,[Crouch]
OR A,A
RET NZ
LD A,E
SUB A,32
LD E,A
LD A,D
SBC A,0
LD D,A
RET

; Entry points for #303 pickups; the small path always restarts GROW.
PowerUp:
LD A,[PowerState]
OR A,A
JR NZ,PowerUpLarge
INC A
LD [PowerState],A
LD [PowerPhase],A
LD A,32
LD [PowerTimer],A
RET
PowerUpLarge:
CP A,1
RET NZ
LD A,2
LD [PowerState],A
RET
GrantStar:
LD A,248
LD [Invincible],A
RET

; Displayed pose index for scene preparation; state is never advanced here.
SelectPowerPose:
LD A,[GameMode]
OR A,A
RET Z
LD A,[PowerState]
OR A,A
LD B,0
JR Z,PoseSizeKnown
LD B,6
PoseSizeKnown:
LD A,[GameMode]
CP A,2
JR NZ,PoseNotRetry
LD A,5
ADD A,B
RET
PoseNotRetry:
LD A,[PowerPhase]
CP A,2
JR NZ,PoseNotHurt
LD A,[PowerTimer]
DEC A
AND A,4
LD A,14
RET Z
LD A,15
RET
PoseNotHurt:
LD A,[ThrowTimer]
OR A,A
LD A,17
RET NZ
LD A,[Crouch]
OR A,A
LD A,16
RET NZ
LD A,[PowerPhase]
CP A,1
JR NZ,PoseSized
LD A,[PowerTimer]
DEC A
AND A,4
LD B,6
JR Z,PoseSized
LD B,0
PoseSized:
LD A,[MotionPose]
CP A,5
JR NZ,PoseAddSize
LD A,B
OR A,A
LD A,12
RET Z
LD A,13
RET
PoseAddSize:
ADD A,B
RET

; A=1 hides the player: fallen, SAFE blink or invincibility blink.
PowerHidden:
LD A,[Fell]
OR A,A
RET NZ
LD A,[PowerPhase]
CP A,3
JR NZ,HiddenStar
LD A,[PowerTimer]
DEC A
AND A,4
JR NZ,HiddenYes
HiddenStar:
LD A,[Invincible]
OR A,A
RET Z
DEC A
AND A,4
RET Z
HiddenYes:
LD A,1
RET
EXPORT PowerUp
EXPORT GrantStar
