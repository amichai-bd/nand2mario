; Original on-board game menu for the loader profile. Contract:
; wiki/src/sw/menu/SPEC.md; hardware registers from
; wiki/src/rtl/cartridge/MAS_loader_profile.md. The low 16 KiB holds this
; code, the font and the plate art; the upper 16 KiB is the banked window
; into SDRAM.
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
TILE_ARROW EQU 38
FONT_TILES EQU 39
FONT_BYTES EQU FONT_TILES * 16
; The plated list bank: the font, its inverse (every shade 3 - shade, which is
; the complement of both bit planes), the nudged arrow, the two plate caps and
; the inverse nudged arrow. Adding TILE_INVERSE to a font tile inverts it;
; adding TILE_UNINVERSE takes it back.
TILE_INVERSE EQU FONT_TILES
TILE_UNINVERSE EQU 256 - TILE_INVERSE
TILE_NUDGE EQU 78
TILE_PLATE_LEFT EQU 79
TILE_PLATE_RIGHT EQU 80
TILE_NUDGE_INVERSE EQU 81
DESIGN_TILES EQU 3
DESIGN_BYTES EQU DESIGN_TILES * 16
; Frame layout in 8x8 map cells.
MAP EQU GB_VIEW_MAP0_START
HEADER_COLUMN EQU 4
SLOT_ROW EQU 1
NUMBER_COLUMN EQU 1
TITLE_COLUMN EQU 4
STATUS_ROW EQU 17
TITLE_BYTES EQU 16
; The header and status plates: a cap in each outer column and 18 cells
; between them. A selected slot inverts its cells 1..19; column 0 is the arrow.
PLATE_COLUMN EQU 1
PLATE_CELLS EQU 18
BAR_CELLS EQU 19
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
TitleOffset:
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
LD [TitleOffset],A
LD A,KEY_NONE
LD [ShownKey],A
LD [ShownIndex],A
LD A,$E4
LDH [GB_REG_BGP],A
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
; The inverse bank is the same 39 tiles with both bit planes complemented.
LD DE,Font
LD HL,GB_VIEW_TILES_START + TILE_INVERSE * 16
LD BC,FONT_BYTES
CopyInverseFont:
LD A,[DE]
INC DE
CPL
LD [HL+],A
DEC BC
LD A,B
OR A,C
JR NZ,CopyInverseFont
; The three authored tiles, then the inverse of the nudged arrow.
LD DE,Design
LD HL,GB_VIEW_TILES_START + TILE_NUDGE * 16
LD BC,DESIGN_BYTES
CopyDesign:
LD A,[DE]
INC DE
LD [HL+],A
DEC BC
LD A,B
OR A,C
JR NZ,CopyDesign
LD DE,Design
LD BC,16
CopyInverseNudge:
LD A,[DE]
INC DE
CPL
LD [HL+],A
DEC BC
LD A,B
OR A,C
JR NZ,CopyInverseNudge
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
; Header plate: a cap in each outer column, inverse cells between, the title
; in the inverse bank.
LD HL,MAP
LD A,TILE_PLATE_LEFT
LD [HL+],A
LD A,TILE_BLANK + TILE_INVERSE
LD B,PLATE_CELLS
HeaderPlate:
LD [HL+],A
DEC B
JR NZ,HeaderPlate
LD A,TILE_PLATE_RIGHT
LD [HL],A
LD HL,Header
LD DE,MAP + HEADER_COLUMN
LD B,12
LD C,TILE_INVERSE
CALL DrawText
; Status plate caps; ShowStatus fills the 18 cells between them.
LD A,TILE_PLATE_LEFT
LD [MAP + STATUS_ROW * 32],A
LD A,TILE_PLATE_RIGHT
LD [MAP + STATUS_ROW * 32 + PLATE_COLUMN + PLATE_CELLS],A
; The six status rows as inverse tiles, once, while the LCD is off.
LD HL,StatusText
LD DE,StatusCells
LD B,STATUS_CELLS
LD C,TILE_INVERSE
CALL DrawText
; The sixteen slot numbers.
LD DE,MAP + SLOT_ROW * 32 + NUMBER_COLUMN
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
CALL DrawBar
CALL ShowStatus
LD A,$91
LDH [GB_REG_LCDC],A
; One sampled update per frame, all map writes inside VBlank.
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
; A row drawn under the selection bar is drawn in the inverse bank, which
; costs one M-cycle a cell instead of a second pass over the row. The row the
; bar is on right now is ShownCursor, not Cursor: Navigate has already moved
; Cursor this frame and ShowCursor only moves the bar after this call, so
; comparing against Cursor would draw a row in the wrong bank and let
; ShowCursor invert it a second time or unwind it past zero.
LD A,[Pending]
LD B,A
LD A,[ShownCursor]
CP A,B
LD A,0
JR NZ,PendingOffset
LD A,TILE_INVERSE
PendingOffset:
LD [TitleOffset],A
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
INC A
LD L,A
LD H,0
ADD HL,HL
ADD HL,HL
ADD HL,HL
ADD HL,HL
ADD HL,HL
LD BC,MAP + TITLE_COLUMN
ADD HL,BC
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
LD A,[TitleOffset]
LD C,A
CALL DrawText
LD A,[HL]
CP A,CGB_FLAG
JR Z,FlagBlank
CP A,CGB_ONLY
JR Z,FlagBlank
CALL CharTile
ADD A,C
LD [DE],A
RET
FlagBlank:
LD A,TILE_BLANK
ADD A,C
LD [DE],A
RET
BlankTitle:
LD B,TITLE_BYTES
LD A,[TitleOffset]
ADD A,TILE_BLANK
BlankLoop:
LD [DE],A
INC DE
DEC B
JR NZ,BlankLoop
RET

; HL = ASCII bytes, DE = cells, B = count, C = bank offset (0 or TILE_INVERSE).
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

; HL = first cell, B = count, C = TILE_INVERSE or TILE_UNINVERSE: move a run
; of cells between the font bank and its inverse.
InvertRun:
LD A,[HL]
ADD A,C
LD [HL+],A
DEC B
JR NZ,InvertRun
RET

; The selection bar: cells 1..19 of the cursor's row inverted, column 0 the
; arrow in its current nudge phase.
DrawBar:
LD A,[Cursor]
CALL CursorCell
INC HL
LD B,BAR_CELLS
LD C,TILE_INVERSE
CALL InvertRun
JR DrawArrow

; Move the bar only when the cursor changed; otherwise only the nudge phase
; can change, and then only column 0.
ShowCursor:
LD A,[ShownCursor]
LD B,A
LD A,[Cursor]
CP A,B
JR Z,SamePlace
LD [ShownCursor],A
LD A,B
CALL CursorCell
LD A,TILE_BLANK
LD [HL+],A
LD B,BAR_CELLS
LD C,TILE_UNINVERSE
CALL InvertRun
JR DrawBar
SamePlace:
LD A,[FrameCount]
AND A,PHASE_BIT
LD B,A
LD A,[ShownPhase]
CP A,B
RET Z
DrawArrow:
LD A,[Cursor]
CALL CursorCell
LD A,[FrameCount]
AND A,PHASE_BIT
LD [ShownPhase],A
LD A,TILE_ARROW + TILE_INVERSE
JR Z,ArrowWrite
LD A,TILE_NUDGE_INVERSE
ArrowWrite:
LD [HL],A
RET

; A = slot -> HL = its map row, column 0.
CursorCell:
LD L,A
LD H,0
ADD HL,HL
ADD HL,HL
ADD HL,HL
ADD HL,HL
ADD HL,HL
LD BC,MAP + SLOT_ROW * 32
ADD HL,BC
RET

; Status row from the status bytes: the prebuilt inverse row for the current
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
LD DE,MAP + STATUS_ROW * 32 + PLATE_COLUMN
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
LD HL,MAP + STATUS_ROW * 32 + PLATE_COLUMN
ADD HL,DE
LD D,H
LD E,L
LD A,C
CP A,LIBRARY_CATALOGUE_ENTRIES
JR NC,IndexUnknown
LD C,TILE_DIGIT + TILE_INVERSE
JP DrawDigits
IndexUnknown:
LD A,TILE_DASH + TILE_INVERSE
LD [DE],A
INC DE
LD [DE],A
RET

Header:
DB "GAME LIBRARY"
; The six status rows, each already centred in the plate's 18 cells exactly as
; the contract states; the zeros are placeholders the index digits overwrite.
StatusText:
DB "                  "
DB "    NOT READY     "
DB " SLOT 00 INVALID  "
DB " SLOT 00 BAD CRC  "
DB "SLOT 00 NOT READY "
DB "  SLOT 00 ERROR   "
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
Design:
ASSET "Plate"
