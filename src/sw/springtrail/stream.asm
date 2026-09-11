; Prepare immutable caches during visible time, publish only during VBlank.
SECTION "stream",ROM
PrepareMap:
XOR A,A
LD [PreparedColumns],A
LD A,[GameMode]
OR A,A
RET Z
LD A,[NewLevel]
OR A,A
JR Z,PrepareExistingMap
XOR A,A
JR PrepareRestore
PrepareExistingMap:
LD A,[MapRestoreColumn]
CP A,32
JR NC,PrepareEntering
PrepareRestore:
LD [PreparedColumn],A
LD DE,ColumnCache
CALL DecodeColumn
LD A,[PreparedColumn]
INC A
LD DE,ColumnCache+16
CALL DecodeColumn
LD A,2
LD [PreparedColumns],A
RET
PrepareEntering:
; A changed block republishes its own pair first; the entering column keeps
; OldCameraTile and follows on the next update.
LD A,[BlockDirty]
OR A,A
JR Z,PrepareCamera
DEC A
LD [PreparedColumn],A
LD DE,ColumnCache
CALL DecodeColumn
LD A,[PreparedColumn]
INC A
LD DE,ColumnCache+16
CALL DecodeColumn
LD A,2
LD [PreparedColumns],A
LD [DirtyPublish],A
XOR A,A
LD [BlockDirty],A
RET
PrepareCamera:
LD A,[Camera]
LD L,A
LD A,[Camera+1]
LD H,A
SRL H
RR L
SRL H
RR L
SRL H
RR L
LD A,[OldCameraTile]
CP A,L
RET Z
LD B,A
LD A,L
CP A,B
JR C,PrepareLeftColumn
ADD A,20
PrepareLeftColumn:
LD B,A
CALL StageColumnCount
CP A,B
RET Z
RET C
LD A,B
LD [PreparedColumn],A
LD DE,ColumnCache
CALL DecodeColumn
LD A,1
LD [PreparedColumns],A
RET

DecodeColumn:
; Build validation proves index0..255, complete16 rows and bounded run counts.
; The block layer overwrites rows 10 and 11 of the completed cache. It is keyed
; on the page column, so its stage-0 table matches nothing on the other stages.
LD B,A
CALL StageBaseColumn
ADD A,B
LD [DecodeIndex],A
LD A,E
LD [DecodeBase],A
LD A,D
LD [DecodeBase+1],A
LD A,[DecodeIndex]
LD L,A
LD H,0
ADD HL,HL
LD BC,ColumnPointers
ADD HL,BC
LD A,[HL+]
LD C,A
LD A,[HL]
LD H,A
LD L,C
DecodeRun:
LD A,[HL+]
OR A,A
JP Z,BlockOverride
LD B,A
LD A,[HL+]
DecodeRepeat:
LD [DE],A
INC DE
DEC B
JR NZ,DecodeRepeat
JR DecodeRun

StreamMap:
LD A,[PreparedColumns]
OR A,A
JR Z,RememberCameraTile
CALL PublishColumns
LD A,[DirtyPublish]
OR A,A
JR Z,RememberCameraTile
XOR A,A
LD [DirtyPublish],A
RET
RememberCameraTile:
LD A,[Camera]
LD L,A
LD A,[Camera+1]
LD H,A
SRL H
RR L
SRL H
RR L
SRL H
RR L
LD A,L
LD [OldCameraTile],A
RET

PublishColumns:
LD A,[PreparedColumns]
OR A,A
RET Z
LD HL,ColumnCache
LD A,[PreparedColumn]
CALL PublishColumn
LD A,[PreparedColumns]
CP A,2
RET NZ
LD A,[PreparedColumn]
INC A
; HL already points at the second completed cache.
PublishColumn:
AND A,31
ADD A,$40
LD E,A
LD D,$9C
; Fixed row2..17; destination carry follows rows7 and15.
LD A,[HL+]
LD [DE],A
LD A,E
ADD A,32
LD E,A
LD A,[HL+]
LD [DE],A
LD A,E
ADD A,32
LD E,A
LD A,[HL+]
LD [DE],A
LD A,E
ADD A,32
LD E,A
LD A,[HL+]
LD [DE],A
LD A,E
ADD A,32
LD E,A
LD A,[HL+]
LD [DE],A
LD A,E
ADD A,32
LD E,A
LD A,[HL+]
LD [DE],A
LD A,E
ADD A,32
LD E,A
INC D
LD A,[HL+]
LD [DE],A
LD A,E
ADD A,32
LD E,A
LD A,[HL+]
LD [DE],A
LD A,E
ADD A,32
LD E,A
LD A,[HL+]
LD [DE],A
LD A,E
ADD A,32
LD E,A
LD A,[HL+]
LD [DE],A
LD A,E
ADD A,32
LD E,A
LD A,[HL+]
LD [DE],A
LD A,E
ADD A,32
LD E,A
LD A,[HL+]
LD [DE],A
LD A,E
ADD A,32
LD E,A
LD A,[HL+]
LD [DE],A
LD A,E
ADD A,32
LD E,A
LD A,[HL+]
LD [DE],A
LD A,E
ADD A,32
LD E,A
INC D
LD A,[HL+]
LD [DE],A
LD A,E
ADD A,32
LD E,A
LD A,[HL+]
LD [DE],A
RET
