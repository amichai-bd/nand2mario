; Original deterministic linker fixture. No external program source.
IMPORT Other
SECTION "code", ROM
Start: LD HL,Other
JR After
DB $ff
After: CALL Other
EXPORT Start
SECTION "work", RAM
Buffer: DS 16
