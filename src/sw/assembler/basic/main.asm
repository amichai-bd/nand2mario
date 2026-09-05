; Original assembler/object fixture; not an executable cartridge.
INCLUDE "constants.asm"
SECTION "code", ROM
Entry: LD A, MessageByte
    LDH [GB_IO_START], A
    LD HL, SP-128
    BIT 7, [HL]
    CALL ExternalRoutine
    JR Entry
    STOP
    DB "text;data", 0
    DW Buffer
EXPORT Entry
IMPORT ExternalRoutine
SECTION "scratch", RAM
Buffer: DS BufferSize
