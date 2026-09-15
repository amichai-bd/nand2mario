; Original on-board game menu for the loader profile. Contract:
; wiki/src/sw/menu/SPEC.md; hardware registers from
; wiki/src/rtl/cartridge/MAS_loader_profile.md. The low 16 KiB holds this
; code and the font; the upper 16 KiB is the banked window into SDRAM.
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
FONT_BYTES EQU 39 * 16
; Frame layout in 8x8 map cells.
MAP EQU GB_VIEW_MAP0_START
HEADER_COLUMN EQU 4
SLOT_ROW EQU 1
NUMBER_COLUMN EQU 1
TITLE_COLUMN EQU 4
STATUS_ROW EQU 17
TITLE_BYTES EQU 16
STATUS_BYTES EQU 20
WORD_BYTES EQU 12
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
; Header and the sixteen slot numbers.
LD HL,Header
LD DE,MAP + HEADER_COLUMN
LD B,12
CALL DrawText
LD DE,MAP + SLOT_ROW * 32 + NUMBER_COLUMN
LD C,0
Numbers:
LD A,C
PUSH BC
CALL DrawNumber
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
LD A,TILE_ARROW
LD [MAP + SLOT_ROW * 32],A
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
; draws its 16 title bytes, any other entry a blank title.
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
LD B,TITLE_BYTES
JP DrawText
BlankTitle:
LD B,TITLE_BYTES
LD A,TILE_BLANK
BlankLoop:
LD [DE],A
INC DE
DEC B
JR NZ,BlankLoop
RET

; HL = ASCII bytes, DE = map cells, B = count.
DrawText:
LD A,[HL+]
CALL CharTile
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

; A = value 0..99 as two digit tiles at DE; DE advances by two.
DrawNumber:
LD C,TILE_DIGIT
Tens:
CP A,10
JR C,Units
SUB A,10
INC C
JR Tens
Units:
ADD A,TILE_DIGIT
LD B,A
LD A,C
LD [DE],A
INC DE
LD A,B
LD [DE],A
INC DE
RET

; Move the arrow only when the cursor changed: two map writes.
ShowCursor:
LD A,[ShownCursor]
LD B,A
LD A,[Cursor]
CP A,B
RET Z
LD [ShownCursor],A
PUSH AF
LD A,B
CALL CursorCell
LD A,TILE_BLANK
LD [HL],A
POP AF
CALL CursorCell
LD A,TILE_ARROW
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

; Status row from the status bytes: NOT READY while the SDRAM is not ready,
; else SLOT nn and the word for a result of INVALID_SLOT or above, else
; blank. Redrawn only when the shown key or index changes.
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
LD DE,MAP + STATUS_ROW * 32
LD A,B
CP A,KEY_NOT_READY
JR NZ,StatusResult
LD HL,NotReadyText
LD B,STATUS_BYTES
JP DrawText
StatusResult:
CP A,LIBRARY_RESULT_INVALID_SLOT
JR C,StatusClear
LD HL,SlotText
LD B,5
CALL DrawText
LD A,C
CP A,LIBRARY_CATALOGUE_ENTRIES
JR NC,IndexUnknown
PUSH BC
CALL DrawNumber
POP BC
JR StatusWord
IndexUnknown:
LD A,TILE_DASH
LD [DE],A
INC DE
LD [DE],A
INC DE
StatusWord:
LD A,TILE_BLANK
LD [DE],A
INC DE
LD A,[ShownKey]
CP A,LIBRARY_RESULT_NOT_READY + 1
JR C,KnownWord
LD A,LIBRARY_RESULT_NOT_READY + 1
KnownWord:
SUB A,LIBRARY_RESULT_INVALID_SLOT
LD L,A
LD H,0
ADD HL,HL
ADD HL,HL
LD B,H
LD C,L
ADD HL,HL
ADD HL,BC
LD BC,Words
ADD HL,BC
LD B,WORD_BYTES
JP DrawText
StatusClear:
LD B,STATUS_BYTES
LD A,TILE_BLANK
ClearStatus:
LD [DE],A
INC DE
DEC B
JR NZ,ClearStatus
RET

Header:
DB "GAME LIBRARY"
SlotText:
DB "SLOT "
NotReadyText:
DB "NOT READY           "
Words:
DB "INVALID     "
DB "BAD CRC     "
DB "NOT READY   "
DB "ERROR       "
EXPORT Start

SECTION "assets",ROM
Font:
ASSET "Font"
