; Original exit-register demo for the game library. Contract:
; wiki/src/rtl/cartridge/MAS_loader_profile.md#game-exit-register. The
; screen is one solid bar on map row eight over a blank background, so a
; host snapshot has a fixed reference; while Start is held the program
; writes LIBRARY_GAME_EXIT_VALUE to the exit register once per frame and the
; loader returns the console to the menu. Every other button is ignored.
EXIT_REGISTER EQU 24576
BAR_ROW EQU GB_VIEW_MAP0_START + 8 * 32

SECTION "code",ROM
Start:
DI
LD SP,$DFFE
XOR A,A
LDH [GB_REG_LCDC],A
LDH [GB_REG_IF],A
LD [GB_REG_IE],A
LDH [GB_REG_SCY],A
LDH [GB_REG_SCX],A
LD HL,GB_VIEW_MAP0_START
LD BC,$0400
ClearMap:
XOR A,A
LD [HL+],A
DEC BC
LD A,B
OR A,C
JR NZ,ClearMap
; Tile 0 is blank (color 0) and tile 1 solid (color 3).
LD HL,GB_VIEW_TILES_START
LD B,$10
BlankTile:
XOR A,A
LD [HL+],A
DEC B
JR NZ,BlankTile
LD B,$10
SolidTile:
LD A,$FF
LD [HL+],A
DEC B
JR NZ,SolidTile
LD HL,BAR_ROW
LD B,20
Bar:
LD A,$01
LD [HL+],A
DEC B
JR NZ,Bar
LD A,$01
LD [GB_REG_IE],A
LD A,$E4
LDH [GB_REG_BGP],A
LD A,$91
LDH [GB_REG_LCDC],A
Sleep:
XOR A,A
LDH [GB_REG_IF],A
HALT
; IME stays clear: VBlank wakes HALT without an interrupt stack transaction.
; The NOP absorbs the DMG halt bug: a VBlank that sets IF between the clear
; above and HALT makes the CPU fetch the next byte twice, so that byte must be
; harmless; without it the doubled $3E would turn `LD A,n` into STOP.
NOP
; Button row: P15 low, settled eight machine cycles, bit 3 low is Start.
LD A,$10
LDH [GB_REG_JOYP],A
NOP
NOP
NOP
NOP
NOP
NOP
NOP
NOP
LDH A,[GB_REG_JOYP]
LD B,A
LD A,PROFILE_JOYP_SELECT
LDH [GB_REG_JOYP],A
BIT 3,B
JR NZ,Sleep
LD A,LIBRARY_GAME_EXIT_VALUE
LD [EXIT_REGISTER],A
JR Sleep
EXPORT Start
