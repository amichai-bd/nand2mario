; Original nand2mario oracle fixture. No external test sources.
SECTION "entry", ROM0[$0200]
Entry::
    ld a, $42
    ld bc, $1234
    ld [hl+], a
    bit 3, a
    jr nz, .next
    nop
.next:
    call Helper
    jp Tail
SECTION "tail", ROM0[$0240]
Tail::
    xor a
    ret
