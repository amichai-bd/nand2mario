; Original on-board game menu for the loader profile. Contract:
; wiki/src/sw/menu/SPEC.md; hardware registers from
; wiki/src/rtl/cartridge/MAS_loader_profile.md. The low 16 KiB holds this
; code, the font, the grey plate art and the boot splash badge; the upper
; 16 KiB is the banked window into SDRAM.
; Loader profile registers (CPU addresses fixed by the contract; the
; generated table owns the status and result values).
LOADER_BANK EQU 8192
LOADER_SELECT EQU 24576
LOADER_STATUS EQU GB_CART_RAM_START
LOADER_RESULT EQU GB_CART_RAM_START + 2
LOADER_INDEX EQU GB_CART_RAM_START + 3
CATALOGUE_BANK EQU LIBRARY_CATALOGUE_ADDRESS / LIBRARY_WINDOW_BYTES
ENTRY_TITLE EQU 8
; Font atlas order: A-Z, 0-9, dash, blank, cursor arrow.
TILE_DIGIT EQU 26
TILE_DASH EQU 36
TILE_BLANK EQU 37
FONT_TILES EQU 39
FONT_BYTES EQU FONT_TILES * 16
; The bank: the font, the same 39 glyphs on a mid-grey page, the six authored
; grey cells and the two pointer phases. Adding TILE_GREY to a font tile moves
; it onto the grey page. The font uses only shade 0 and shade 3, so the grey
; copy is the font's low plane with the high plane set.
TILE_GREY EQU FONT_TILES
GREY_ROWS EQU FONT_TILES * 8
TILE_CAP_LEFT EQU 78
TILE_CAP_RIGHT EQU 79
TILE_FADE32 EQU 80
TILE_FADE21 EQU 81
GREY_ART_TILES EQU 6
GREY_ART_BYTES EQU GREY_ART_TILES * 16
; The two pointer phases are object tiles; no map cell ever names them.
TILE_POINTER EQU 84
POINTER_BYTES EQU 32
; The boot splash badge, four cells by two.
TILE_BADGE EQU 86
BADGE_COLUMNS EQU 4
BADGE_BYTES EQU 128
; Frame layout in 8x8 map cells.
MAP EQU GB_VIEW_MAP0_START
MAP_ROWS EQU 32
; The background map is 32 rows: the splash fills the 18 rows the screen shows
; at SCY 0 and the list follows it, so the list's last four rows wrap over the
; splash's own top rows. The settled view is SCY 144, at which the visible
; rows are the list alone.
LIST_MAP_ROW EQU 18
LIST_MAP EQU MAP + LIST_MAP_ROW * 32
SETTLED_SCY EQU LIST_MAP_ROW * 8
; The splash art, from the approved design sheet.
SPLASH_BADGE_ROW EQU 4
SPLASH_BADGE_COLUMN EQU 8
SPLASH_TITLE_ROW EQU 8
SPLASH_TITLE_COLUMN EQU 4
SPLASH_HINT_ROW EQU 10
SPLASH_HINT_COLUMN EQU 3
SPLASH_HINT_BYTES EQU 13
HEADER_COLUMN EQU 4
SLOT_ROW EQU 1
NUMBER_COLUMN EQU 1
TITLE_COLUMN EQU 4
STATUS_ROW EQU 17
; The list's bottom plate, wrapped into the map's fourth row.
STATUS_MAP_ROW EQU LIST_MAP_ROW + STATUS_ROW - MAP_ROWS
TITLE_BYTES EQU 16
; The header and bottom plates: a grey cap in each outer column and 18 cells
; between them, filled with a dithered gradient behind the grey text.
PLATE_COLUMN EQU 1
PLATE_CELLS EQU 18
; The pad byte of the status rows, the cell that stays plate fill.
PLATE_PAD EQU 35
; The cursor is object 0: X is fixed at the left edge and Y follows the slot.
OAM_CURSOR EQU GB_OAM_START
OAM_BYTES EQU 160
CURSOR_X EQU 8
CURSOR_Y EQU 16 + SLOT_ROW * 8
; The nudge phase is bit 4 of the frame counter, so each phase holds 16
; frames and the frame number alone decides it.
PHASE_BIT EQU 16
; Header byte $0143 is the CGB flag when the title is 15 bytes long; the
; menu draws these two values in the last title cell as blank.
CGB_FLAG EQU $80
CGB_ONLY EQU $C0
; The six status rows, built once as tiles so a redraw is a flat copy.
STATUS_ROWS EQU 6
STATUS_ROW_BLANK EQU 0
STATUS_ROW_NOT_READY EQU 1
STATUS_ROW_WORD EQU 2
STATUS_CELLS EQU STATUS_ROWS * PLATE_CELLS
NO_DIGITS EQU 255
KEY_NOT_READY EQU 254
KEY_NONE EQU 255

SECTION "vars",RAM
Cursor:
DS 1
Previous:
DS 1
Pressed:
DS 1
Pending:
DS 1
BankDone:
DS 1
ShownCursor:
DS 1
ShownKey:
DS 1
ShownIndex:
DS 1
FrameCount:
DS 1
ShownPhase:
DS 1
StatusCells:
DS STATUS_CELLS

SECTION "code",ROM
Start:
DI
LD SP,$DFFE
XOR A,A
LDH [GB_REG_LCDC],A
LDH [GB_REG_SCY],A
LDH [GB_REG_SCX],A
LDH [GB_REG_IF],A
LD [GB_REG_IE],A
LD [Cursor],A
LD [Previous],A
LD [Pressed],A
LD [Pending],A
LD [BankDone],A
LD [ShownCursor],A
LD [FrameCount],A
LD [ShownPhase],A
LD A,KEY_NONE
LD [ShownKey],A
LD [ShownIndex],A
LD A,$E4
LDH [GB_REG_BGP],A
LDH [GB_REG_OBP0],A
; The list sits below the splash in the map, so the settled view is SCY 144.
LD A,SETTLED_SCY
LDH [GB_REG_SCY],A
; Font tiles into VRAM while the LCD is off.
LD DE,Font
LD HL,GB_VIEW_TILES_START
LD BC,FONT_BYTES
CopyFont:
LD A,[DE]
INC DE
LD [HL+],A
DEC BC
LD A,B
OR A,C
JR NZ,CopyFont
; The grey bank: the same glyph mask on a mid-grey page. Shade 0 becomes 2 and
; shade 3 stays, so every row keeps its low plane and sets its high plane.
LD DE,Font
LD HL,GB_VIEW_TILES_START + TILE_GREY * 16
LD BC,GREY_ROWS
CopyGreyFont:
LD A,[DE]
INC DE
INC DE
LD [HL+],A
LD A,$FF
LD [HL+],A
DEC BC
LD A,B
OR A,C
JR NZ,CopyGreyFont
; The six authored grey cells, then the two pointer phases.
LD DE,GreyArt
LD HL,GB_VIEW_TILES_START + TILE_CAP_LEFT * 16
LD B,GREY_ART_BYTES
CopyGreyArt:
LD A,[DE]
INC DE
LD [HL+],A
DEC B
JR NZ,CopyGreyArt
LD DE,Pointer
LD B,POINTER_BYTES
CopyPointer:
LD A,[DE]
INC DE
LD [HL+],A
DEC B
JR NZ,CopyPointer
LD DE,Splash
LD B,BADGE_BYTES
CopyBadge:
LD A,[DE]
INC DE
LD [HL+],A
DEC B
JR NZ,CopyBadge
; Every object but the cursor stays off screen, so clear the table.
LD HL,OAM_CURSOR
LD B,OAM_BYTES
XOR A,A
ClearObjects:
LD [HL+],A
DEC B
JR NZ,ClearObjects
; Blank background map.
LD HL,MAP
LD BC,1024
LD D,TILE_BLANK
ClearMap:
LD A,D
LD [HL+],A
DEC BC
LD A,B
OR A,C
JR NZ,ClearMap
; The boot splash: the badge and its two lines above the list, drawn while the
; LCD is off. The list rides SCY below them.
LD HL,MAP + SPLASH_BADGE_ROW * 32 + SPLASH_BADGE_COLUMN
LD A,TILE_BADGE
LD B,BADGE_COLUMNS
BadgeTop:
LD [HL+],A
INC A
DEC B
JR NZ,BadgeTop
LD HL,MAP + (SPLASH_BADGE_ROW + 1) * 32 + SPLASH_BADGE_COLUMN
LD B,BADGE_COLUMNS
BadgeBottom:
LD [HL+],A
INC A
DEC B
JR NZ,BadgeBottom
LD HL,Header
LD DE,MAP + SPLASH_TITLE_ROW * 32 + SPLASH_TITLE_COLUMN
LD B,12
LD C,0
CALL DrawText
LD HL,SplashHint
LD DE,MAP + SPLASH_HINT_ROW * 32 + SPLASH_HINT_COLUMN
LD B,SPLASH_HINT_BYTES
LD C,0
CALL DrawText
; Header plate: a grey cap in each outer column, the 3-to-2 gradient between
; them and the title on the grey page.
LD HL,LIST_MAP
LD A,TILE_CAP_LEFT
LD [HL+],A
LD A,TILE_FADE32
LD B,PLATE_CELLS
HeaderPlate:
LD [HL+],A
DEC B
JR NZ,HeaderPlate
LD A,TILE_CAP_RIGHT
LD [HL],A
LD HL,Header
LD DE,LIST_MAP + HEADER_COLUMN
LD B,12
LD C,TILE_GREY
CALL DrawText
; Bottom plate caps; ShowStatus fills the 18 cells between them.
LD A,TILE_CAP_LEFT
LD [MAP + STATUS_MAP_ROW * 32],A
LD A,TILE_CAP_RIGHT
LD [MAP + STATUS_MAP_ROW * 32 + PLATE_COLUMN + PLATE_CELLS],A
; The six status rows as grey cells, once, while the LCD is off.
LD HL,StatusText
LD DE,StatusCells
LD B,STATUS_CELLS
CALL DrawPlateText
; The sixteen slot numbers.
LD DE,LIST_MAP + SLOT_ROW * 32 + NUMBER_COLUMN
LD C,0
Numbers:
LD A,C
PUSH BC
LD C,TILE_DIGIT
CALL DrawDigits
POP BC
LD A,E
ADD A,30
LD E,A
LD A,D
ADC A,0
AND A,MAP_ROWS * 32 / 256 - 1
OR A,HIGH(MAP)
LD D,A
INC C
LD A,C
CP A,LIBRARY_SLOTS
JR NZ,Numbers
; With the SDRAM ready, fill the window and draw every title before the
; LCD turns on; otherwise the frame loop retries and draws one row per frame.
LD A,[LOADER_STATUS]
AND A,LIBRARY_STATUS_SDRAM_READY
JR Z,EnableLCD
CALL CommitBank
WaitWindow:
LD A,[LOADER_STATUS]
AND A,LIBRARY_STATUS_WINDOW_READY
JR Z,WaitWindow
DrawAll:
LD A,[Pending]
CALL DrawSlot
LD A,[Pending]
INC A
LD [Pending],A
CP A,LIBRARY_SLOTS
JR NZ,DrawAll
EnableLCD:
; The cursor object: X at the left edge, Y on slot 0, phase 0.
LD A,CURSOR_Y
LD [OAM_CURSOR],A
LD A,CURSOR_X
LD [OAM_CURSOR + 1],A
LD A,TILE_POINTER
LD [OAM_CURSOR + 2],A
CALL ShowStatus
; Background and objects on.
LD A,$93
LDH [GB_REG_LCDC],A
; One sampled update per frame, all map and object writes inside VBlank.
Frame:
CALL WaitVBlank
CALL ReadButtons
CALL Navigate
CALL Catalogue
CALL ShowCursor
CALL ShowStatus
; One loop iteration per displayed frame, and an iteration's writes appear in
; the frame it numbers, so the counter names that frame and bit 4 of it is
; that frame's nudge phase. It advances after the writes, not before.
LD A,[FrameCount]
INC A
LD [FrameCount],A
JR Frame

WaitVBlank:
LDH A,[GB_REG_LY]
CP A,144
JR NC,WaitVBlank
WaitLine:
LDH A,[GB_REG_LY]
CP A,144
JR NZ,WaitLine
RET

; Both JOYP rows, settled at least 24 dots after each row select; Pressed
; holds the released-to-pressed edges in the generated BUTTON_* bit order.
ReadButtons:
LD A,$20
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
CPL
AND A,$0F
LD B,A
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
CPL
AND A,$0F
SWAP A
OR A,B
LD B,A
LD A,[Previous]
CPL
AND A,B
LD [Pressed],A
LD A,B
LD [Previous],A
LD A,PROFILE_JOYP_SELECT
LDH [GB_REG_JOYP],A
RET

; Down, then Up, clamped to slots 0..15; A commits the cursor to the select
; register once every title row is listed. An accepted select swaps the
; image and this code never resumes; a refused one leaves its result and
; index for ShowStatus.
Navigate:
LD A,[Pressed]
BIT 3,A
JR Z,NotDown
LD A,[Cursor]
CP A,LIBRARY_SLOTS - 1
JR Z,NotDown
INC A
LD [Cursor],A
NotDown:
LD A,[Pressed]
BIT 2,A
JR Z,NotUp
LD A,[Cursor]
OR A,A
JR Z,NotUp
DEC A
LD [Cursor],A
NotUp:
LD A,[Pressed]
BIT 4,A
RET Z
LD A,[Pending]
CP A,LIBRARY_SLOTS
RET NZ
LD A,[Cursor]
LD [LOADER_SELECT],A
WaitCopy:
LD A,[LOADER_STATUS]
BIT 7,A
JR NZ,WaitCopy
RET

; Delayed catalogue path: commit the bank once the SDRAM is ready, then draw
; one title row per frame once the window holds bank 34. The window is read
; only here and at boot; nothing after a selection depends on window_ready.
; The cursor is an object, so no row is ever drawn in a second bank and the
; order against ShowCursor no longer matters.
Catalogue:
LD A,[BankDone]
OR A,A
JR NZ,Rows
LD A,[LOADER_STATUS]
AND A,LIBRARY_STATUS_SDRAM_READY
RET Z
JP CommitBank
Rows:
LD A,[Pending]
CP A,LIBRARY_SLOTS
RET Z
LD A,[LOADER_STATUS]
AND A,LIBRARY_STATUS_WINDOW_READY
RET Z
LD A,[Pending]
CALL DrawSlot
LD A,[Pending]
INC A
LD [Pending],A
RET

CommitBank:
LD A,CATALOGUE_BANK
LD [LOADER_BANK],A
LD A,1
LD [BankDone],A
RET

; A = slot. Its catalogue entry is at window offset slot * 32; a valid entry
; draws its 16 title bytes, any other entry a blank title. The 16th byte is
; header $0143: the CGB flag values draw blank, any other byte follows
; CharTile.
DrawSlot:
LD C,A
LD L,A
LD H,0
ADD HL,HL
ADD HL,HL
ADD HL,HL
ADD HL,HL
ADD HL,HL
LD A,H
ADD A,HIGH(GB_ROM1_START)
LD H,A
PUSH HL
LD A,C
ADD A,LIST_MAP_ROW + SLOT_ROW
LD L,A
LD H,0
ADD HL,HL
ADD HL,HL
ADD HL,HL
ADD HL,HL
ADD HL,HL
LD BC,MAP + TITLE_COLUMN
ADD HL,BC
LD A,H
AND A,MAP_ROWS * 32 / 256 - 1
OR A,HIGH(MAP)
LD H,A
LD D,H
LD E,L
POP HL
LD A,[HL]
CP A,LIBRARY_CATALOGUE_VALID
JR NZ,BlankTitle
LD A,L
ADD A,ENTRY_TITLE
LD L,A
LD B,TITLE_BYTES - 1
LD C,0
CALL DrawText
LD A,[HL]
CP A,CGB_FLAG
JR Z,FlagBlank
CP A,CGB_ONLY
JR Z,FlagBlank
CALL CharTile
LD [DE],A
RET
FlagBlank:
LD A,TILE_BLANK
LD [DE],A
RET
BlankTitle:
LD B,TITLE_BYTES
LD A,TILE_BLANK
BlankLoop:
LD [DE],A
INC DE
DEC B
JR NZ,BlankLoop
RET

; HL = ASCII bytes, DE = cells, B = count, C = bank offset (0 or TILE_GREY).
; C survives the loop, so a caller can reuse it for a trailing cell.
DrawText:
LD A,[HL+]
CALL CharTile
ADD A,C
LD [DE],A
INC DE
DEC B
JR NZ,DrawText
RET

; HL = ASCII bytes, DE = cells, B = count: the same as DrawText on the grey
; page, except that the pad byte writes the plate's gradient fill instead of a
; glyph, so the text sits on the plate and never on a grey block.
DrawPlateText:
LD A,[HL+]
CP A,PLATE_PAD
JR Z,PlateFill
CALL CharTile
ADD A,TILE_GREY
JR PlateWrite
PlateFill:
LD A,TILE_FADE21
PlateWrite:
LD [DE],A
INC DE
DEC B
JR NZ,DrawPlateText
RET

; A = byte -> font tile: letters, digits, dash; zero and space blank; any
; other byte the dash so a foreign title stays visible.
CharTile:
OR A,A
JR Z,CharBlank
CP A,32
JR Z,CharBlank
CP A,45
JR Z,CharDash
CP A,48
JR C,CharDash
CP A,58
JR C,CharDigit
CP A,65
JR C,CharDash
CP A,91
JR NC,CharDash
SUB A,65
RET
CharDigit:
SUB A,48 - TILE_DIGIT
RET
CharDash:
LD A,TILE_DASH
RET
CharBlank:
LD A,TILE_BLANK
RET

; A = value 0..99 as two digit tiles at DE, C = the bank's digit tile; DE
; advances by two and B and C are clobbered.
DrawDigits:
LD B,C
Tens:
CP A,10
JR C,Units
SUB A,10
INC B
JR Tens
Units:
ADD A,C
LD C,A
LD A,B
LD [DE],A
INC DE
LD A,C
LD [DE],A
INC DE
RET

; The cursor object. Its Y follows the slot and its tile is the nudge phase,
; so a move is one byte and a phase change is one byte; the map never changes.
ShowCursor:
LD A,[ShownCursor]
LD B,A
LD A,[Cursor]
CP A,B
JR Z,SamePlace
LD [ShownCursor],A
ADD A,A
ADD A,A
ADD A,A
ADD A,CURSOR_Y
LD [OAM_CURSOR],A
SamePlace:
LD A,[FrameCount]
AND A,PHASE_BIT
LD B,A
LD A,[ShownPhase]
CP A,B
RET Z
LD A,B
LD [ShownPhase],A
OR A,A
LD A,TILE_POINTER
JR Z,PhaseWrite
INC A
PhaseWrite:
LD [OAM_CURSOR + 2],A
RET

; Status row from the status bytes: the prebuilt grey row for the current
; key copied into the 18 plate cells, then the index digits where that row
; carries them. Redrawn only when the shown key or index changes.
ShowStatus:
LD A,[LOADER_STATUS]
AND A,LIBRARY_STATUS_SDRAM_READY
LD B,KEY_NOT_READY
JR Z,StatusKey
LD A,[LOADER_RESULT]
LD B,A
StatusKey:
LD A,[LOADER_INDEX]
LD C,A
LD A,[ShownKey]
CP A,B
JR NZ,StatusChanged
LD A,[ShownIndex]
CP A,C
RET Z
StatusChanged:
LD A,B
LD [ShownKey],A
LD A,C
LD [ShownIndex],A
LD A,B
CP A,KEY_NOT_READY
LD A,STATUS_ROW_NOT_READY
JR Z,StatusRow
LD A,B
CP A,LIBRARY_RESULT_INVALID_SLOT
LD A,STATUS_ROW_BLANK
JR C,StatusRow
LD A,B
CP A,LIBRARY_RESULT_NOT_READY + 1
JR C,StatusWord
LD A,LIBRARY_RESULT_NOT_READY + 1
StatusWord:
SUB A,LIBRARY_RESULT_INVALID_SLOT - STATUS_ROW_WORD
; A = status row; its cells are at StatusCells + A * PLATE_CELLS.
StatusRow:
PUSH AF
LD L,A
LD H,0
ADD HL,HL
LD D,H
LD E,L
ADD HL,HL
ADD HL,HL
ADD HL,HL
ADD HL,DE
LD DE,StatusCells
ADD HL,DE
LD DE,MAP + STATUS_MAP_ROW * 32 + PLATE_COLUMN
LD B,PLATE_CELLS
CopyStatus:
LD A,[HL+]
LD [DE],A
INC DE
DEC B
JR NZ,CopyStatus
POP AF
; The row's digit column, or NO_DIGITS when it carries no index.
LD HL,StatusDigits
ADD A,L
LD L,A
LD A,0
ADC A,H
LD H,A
LD A,[HL]
CP A,NO_DIGITS
RET Z
LD E,A
LD D,0
LD HL,MAP + STATUS_MAP_ROW * 32 + PLATE_COLUMN
ADD HL,DE
LD D,H
LD E,L
LD A,C
CP A,LIBRARY_CATALOGUE_ENTRIES
JR NC,IndexUnknown
LD C,TILE_DIGIT + TILE_GREY
JP DrawDigits
IndexUnknown:
LD A,TILE_DASH + TILE_GREY
LD [DE],A
INC DE
LD [DE],A
RET

Header:
DB "GAME LIBRARY"
SplashHint:
DB "SELECT A GAME"
; The six status rows, each already centred in the plate's 18 cells exactly as
; the contract states. A pad byte keeps the plate's gradient fill; the zeros
; are placeholders the index digits overwrite.
StatusText:
DB "##################"
DB "####NOT READY#####"
DB "#SLOT 00 INVALID##"
DB "#SLOT 00 BAD CRC##"
DB "SLOT 00 NOT READY#"
DB "##SLOT 00 ERROR###"
StatusDigits:
DB NO_DIGITS
DB NO_DIGITS
DB 6
DB 6
DB 5
DB 7
EXPORT Start

SECTION "assets",ROM
Font:
ASSET "Font"
GreyArt:
ASSET "GreyArt"
Pointer:
ASSET "Pointer"
Splash:
ASSET "Splash"
