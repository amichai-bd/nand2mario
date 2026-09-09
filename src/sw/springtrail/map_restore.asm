; Static initial map remains visible while prepared pairs restore the ring.
SECTION "map_restore",ROM
BeginMapRestore:
XOR A,A
LD [MapRestoreColumn],A
LD [OldCameraTile],A
LDH A,[$FF40]
AND A,$F7
LDH [$FF40],A
RET
RestoreMapPair:
CALL PublishColumns
LD A,[MapRestoreColumn]
ADD A,2
LD [MapRestoreColumn],A
CP A,32
RET NZ
LDH A,[$FF40]
OR A,$08
LDH [$FF40],A
RET
