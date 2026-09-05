# Independent relocation comparison

Original sources cover imported byte/word endpoints, LDH, unresolved bit/restart
constraints, absolute/LOW/HIGH addresses, a forward and backward branch at
+127/-128, and allocation-only RAM. The separately retained RGBDS spelling
changes only IMPORT omission, DEF EQU and explicit section placement. It never
reads the project opcode table or computes oracle relocations. RGBLINK selects
both linked bytes and public label addresses.
