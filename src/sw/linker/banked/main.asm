; Original deterministic MBC1 linker fixture. No external program source.
; Bank 0: selects bank 2 through BANK1 ($2000-$3FFF) and reads the signature
; word the bank-2 unit exports at the switched window.
IMPORT Signature
SECTION "code", ROM
Start: LD A,2
LD HL,$2000
LD [HL],A
LD HL,Signature
LD A,[HL]
Loop: JR Loop
EXPORT Start
SECTION "work", RAM
Buffer: DS 8
