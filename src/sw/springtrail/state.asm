; Ordinary WRAM operands: signed little-endian sixteenth-pixel values.
PlayerX EQU $C010
PlayerY EQU $C012
VelocityX EQU $C014
VelocityY EQU $C016
Grounded EQU $C018
Buttons EQU $C019
Previous EQU $C01A
Camera EQU $C01B
Fell EQU $C01D
Column EQU $C020
Row EQU $C021
LastCell EQU $C022
OldCameraTile EQU $C023
GamePrevious EQU $C024
EnemyX EQU $C026
EnemyVX EQU $C028
Score EQU $C029
GameTimer EQU $C02A
Collected EQU $C02C
Pressed EQU $C02D
NewLevel EQU $C02E
ObjectX EQU $C034
ObjectY EQU $C036
ObjectHeight EQU $C038
ObjectMask EQU $C03A
GameMode EQU $C000
MapRestoreColumn EQU $C02F
SceneHidden EQU $C03B
SceneTile EQU $C03C
SceneX EQU $C03D
SceneBuffer EQU $C100
TitleCleared EQU $C030

; Rendering operands only; game collision and movement never read these.
CourierFacing EQU $C040
CourierPose EQU $C041
SceneBaseX EQU $C042
SceneBaseY EQU $C044
PieceX EQU $C046
PieceY EQU $C047
PieceFlags EQU $C048
PieceCount EQU $C049
PieceHidden EQU $C04A
SceneY EQU $C04B

; Publication/interrupt ownership; not gameplay state.
FramePending EQU $C050
PublishedCamera EQU $C051
PreparedColumn EQU $C052
PreparedColumns EQU $C053
ColumnCache EQU $C200
HUDCache EQU $C220

; Original motion state. Scene preparation reads pose/facing without advancing it.
MoveCounter EQU $C060
MoveDirection EQU $C061
MoveSpeed EQU $C062
MovePhase EQU $C063
AnimationCounter EQU $C064
MotionPose EQU $C065
JumpState EQU $C066
JumpIndex EQU $C067
SavedJumpIndex EQU $C068
MotionFacing EQU $C069

; Original contact/power state. Scene preparation reads it without advancing it.
PowerState EQU $C06A
PowerPhase EQU $C06B
PowerTimer EQU $C06C
Invincible EQU $C06D
ThrowTimer EQU $C06E
EnemyAlive EQU $C06F
Crouch EQU $C070
ShotX EQU $C071
ShotY EQU $C073
ShotVX EQU $C075
ShotVY EQU $C076
ShotTTL EQU $C077

; Original block layer. C078..C083 persist; C084..C08F are per-update scratch.
BlockState EQU $C078
Coins EQU $C07C
EffectTile EQU $C07D
EffectX EQU $C07E
EffectY EQU $C080
EffectTimer EQU $C082
BlockDirty EQU $C083
HitValid EQU $C084
HitColumn EQU $C085
HitRow EQU $C086
ScanUp EQU $C087
BlockIndex EQU $C088
EffectColumn EQU $C089
EffectRow EQU $C08A
DecodeIndex EQU $C08B
DecodeBase EQU $C08C
BlockSub EQU $C08E
DirtyPublish EQU $C08F

; Original progression state. Lives and StageIndex survive a death and a stage
; change; only a reset clears them. ProgressCache is the prepared HUD row1.
Lives EQU $C090
PendingLife EQU $C091
TimerSub EQU $C092
TimerLow EQU $C093
TimerHigh EQU $C094
Expiring EQU $C095
StageIndex EQU $C096
ProgressCache EQU $C097

; Four fixed entity owners; progression cache ends at C09C.
CurlX EQU $C300
CurlY EQU $C302
CurlState EQU $C304
CurlTimer EQU $C305
MovingX EQU $C310
MovingY EQU $C312
MovingState EQU $C314
MovingVX EQU $C316
FallingX EQU $C320
FallingY EQU $C322
FallingState EQU $C324
FallingTimer EQU $C325
PatrolFrame EQU $C330
StompTimer EQU $C331
EntityRider EQU $C332
EntityDetached EQU $C338
EntitySlot EQU $C339
EntityOldX EQU $C33A
EntityOldY EQU $C33C
EntityOldMovingX EQU $C33E
EntityOldMovingY EQU $C340
EntityOldFallingX EQU $C342
EntityOldFallingY EQU $C344
EntityCandidateX EQU $C346
EntityCandidateY EQU $C348
EntityTemp EQU $C34A

; Reserved bytes are zero and observable in the current host profile.
CurlVX EQU $C306
CurlReserved EQU $C307
MovingTimer EQU $C315
MovingReserved EQU $C317
FallingVX EQU $C326
FallingReserved EQU $C327
EntityReserved EQU $C333
