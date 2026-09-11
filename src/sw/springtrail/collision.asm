; The page-aligned collision table now lives with its literal source in
; world.asm, where CollisionMap and WorldMap label the same 18x256 rows.
; This file remains the collision unit so every include and fixture input
; keeps naming it; it contributes no bytes and declares no section.
