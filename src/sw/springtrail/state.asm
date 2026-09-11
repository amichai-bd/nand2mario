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
