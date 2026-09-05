; Separate object forces RGBLINK to resolve the call relocation.
SECTION "helper", ROM0[$0220]
Helper::
    push af
    ld a, LOW(Tail)
    pop af
    ret
