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
; The other entry fields the footer reads (cfg/interfaces.json
; catalogue_entry): the profile ID and the 24-bit image length.
ENTRY_PROFILE EQU 1
ENTRY_LENGTH EQU 2
ENTRY_LENGTH_HIGH EQU 24
; The tagline table shares the catalogue region and its window bank: one
; record every LIBRARY_TAGLINE_BYTES, LIBRARY_TAGLINE_CHARS characters then
; zeros, right behind the entries.
TAGLINE_OFFSET EQU LIBRARY_TAGLINE_ADDRESS - LIBRARY_CATALOGUE_ADDRESS
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
STAR_BYTES EQU 64
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
; The splash schedule, the same constants as src/dv/menu/reference.py: four
; BGP steps held FADE_HOLD frames each, then an SCY ramp of SLIDE_STEP a
; frame up to the settled view. The frame number alone decides every write,
; and the last slide frame is the menu's own first frame.
SCREEN_ROWS EQU 18
FADE_STEPS EQU 4
FADE_HOLD EQU 2
FADE_FRAMES EQU FADE_STEPS * FADE_HOLD
SLIDE_STEP EQU 16
SLIDE_FRAMES EQU SETTLED_SCY / SLIDE_STEP
SETTLED_FRAME EQU FADE_FRAMES + SLIDE_FRAMES - 1
; The list's last rows wrap over the splash's own top rows, so the slide
; draws them: the last three slot rows and then the bottom plate. Everything
; above them is drawn at boot, with the LCD off.
WRAPPED_ROWS EQU LIST_MAP_ROW + SCREEN_ROWS - MAP_ROWS
BOOT_SLOTS EQU LIBRARY_SLOTS - WRAPPED_ROWS + 1
; The four rows are built as cells at boot, with the LCD off, so a slide frame
; costs a flat copy and a skip frame stays well inside its VBlank.
SCREEN_COLUMNS EQU 20
SPLASH_ROW_CELLS EQU WRAPPED_ROWS * SCREEN_COLUMNS
; A skip draws at most this many of those rows in one VBlank, the same
; constant as SKIP_ROWS in src/dv/menu/reference.py.
SKIP_ROWS EQU 2
HEADER_COLUMN EQU 4
SLOT_ROW EQU 1
NUMBER_COLUMN EQU 1
TITLE_COLUMN EQU 4
STATUS_ROW EQU 17
TITLE_BYTES EQU 16
; The delayed catalogue path draws half a title row in the frame that also
; changes the nudge phase, and the rest in the next one.
TITLE_HALF EQU TITLE_BYTES / 2
; The star field. The list always leaves two columns blank - column 0, the
; page the cursor object draws on, and column 3, between the slot number and
; the title - and a cell of them carries a star where the rule fires on its
; map coordinates. The field is part of the list's own map: it wraps with the
; 32 rows and rides the list's SCY, because DMG has one background layer and
; the composite layout spends it on the list. No title cell is ever a star,
; so the field does not depend on the catalogue and the slot-row draw path
; never evaluates the rule.
TILE_STAR EQU 94
STAR_TILES EQU 4
STAR_MASK EQU 3
STAR_COLUMN_A EQU 0
STAR_COLUMN_B EQU 3
; The rows the rule may touch are the sixteen slot rows: map rows 19..31 and
; the WRAPPED_SLOTS rows the list wraps into 0..2. The header, the splash's
; own rows and the page row the plate left carry none.
STAR_ROW_FIRST EQU LIST_MAP_ROW + SLOT_ROW
WRAPPED_SLOTS EQU LIBRARY_SLOTS + STAR_ROW_FIRST - MAP_ROWS
; Room for the stars the rule finds, well above the eight it draws today.
STAR_SLOTS EQU 16
STAR_ENTRY EQU 3
; The footer's two cells, on the grey page like the font: the cartridge badge
; the upper footer row draws and the separator dot no cell names yet. Both use
; shade 0 and shade 3 only, so the grey copy is derived like the font's.
TILE_CART EQU 98
TILE_DOT EQU 99
FOOTER_ART_ROWS EQU 16
; The press-A badge, two phases on the grey page: dim, then ink. The authored
; cells use shade 1 and shade 3 on shade 0, so the grey copy keeps every row's
; low plane and sets the high plane wherever the low plane is clear, which
; moves shade 0 to 2 and leaves 1 and 3 where they are.
TILE_PULSE EQU 100
PULSE_ART_ROWS EQU 16
; The header and bottom plates: a grey cap in each outer column and 18 cells
; between them, filled with a dithered gradient behind the grey text.
PLATE_COLUMN EQU 1
PLATE_CELLS EQU 18
; The pad byte of the status rows, the cell that stays plate fill.
PLATE_PAD EQU 35
; The window carries the bottom plate alone. It is opaque from its top left
; corner to the bottom right of the screen, so it cannot be a band: at WY 128
; it takes the last two screen rows and the background shows the header and
; fifteen slot rows. Its own map is the second one, which LCDC bit 6 selects.
WMAP EQU GB_VIEW_MAP1_START
FOOTER_ROW EQU 0
WINDOW_STATUS_ROW EQU 1
WINDOW_X EQU 7
WINDOW_Y EQU 128
; The information footer. The upper window row carries the cartridge badge and
; then FOOTER_TEXT_CELLS cells of the selected entry's profile and size, the
; size in three digit cells at FOOTER_DIGIT_COLUMN. The lower row is the status
; row: it carries the entry's tagline whenever no message is on it.
FOOTER_BADGE_COLUMN EQU 1
; The press-A badge sits in the plate cell before the cartridge badge and
; pulses on the nudge phase. The footer's own rows never write that cell.
PULSE_COLUMN EQU 0
FOOTER_TEXT_COLUMN EQU 2
FOOTER_TEXT_CELLS EQU 16
FOOTER_DIGIT_COLUMN EQU 8
FOOTER_DIGITS EQU 3
FOOTER_PLATE EQU WMAP + FOOTER_ROW * 32 + PLATE_COLUMN
FOOTER_TEXT EQU FOOTER_PLATE + FOOTER_TEXT_COLUMN
STATUS_TEXT_CELLS EQU WMAP + WINDOW_STATUS_ROW * 32 + PLATE_COLUMN
; The profile words the footer knows; the word after them is the dashes an
; unknown profile ID draws.
FOOTER_PROFILES EQU 3
; The size field holds three digits, so a length of a thousand kibibytes and
; over draws dashes, as one that is not whole kibibytes does.
KIBIBYTE_DIGITS EQU 1000
NO_SLOT EQU 255
; Background and objects while the splash runs; the window joins them on the
; settled frame, with the cursor.
LCDC_LIST EQU $93
LCDC_SETTLED EQU $F3
; The cursor is object 0: X is fixed at the left edge and Y follows the slot.
OAM_CURSOR EQU GB_OAM_START
OAM_BYTES EQU 160
CURSOR_X EQU 8
CURSOR_Y EQU 16 + SLOT_ROW * 8
; The scroll ramp. The window hides the sixteenth slot row at the settled
; SCY, so a cursor on the last slot scrolls the list up one row, the header
; with it, SCROLL_STEP pixels a frame; leaving that slot ramps back the same
; way. The target is a function of the cursor alone, and the pointer rides
; the list. src/dv/menu/reference.py holds the same two constants.
SCROLLED_SCY EQU SETTLED_SCY + 8
SCROLL_STEP EQU 2
SCROLL_SLOT EQU LIBRARY_SLOTS - 1
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
Half:
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
SplashOn:
DS 1
SplashNumber:
DS 1
SplashRows:
DS 1
SplashSkip:
DS 1
BootSlots:
DS 1
BootDraw:
DS 1
StarCount:
DS 1
StarPtr:
DS 2
StarTable:
DS STAR_SLOTS * STAR_ENTRY
SplashRowCells:
DS SPLASH_ROW_CELLS
StatusCells:
DS STATUS_CELLS
ShownFooterA:
DS 1
ShownFooterB:
DS 1
PlateDrawn:
DS 1
Scroll:
DS 1
ScrollTarget:
DS 1

; Every byte of a plate row maps through this table to the cell it draws: the
; grey page for a glyph, the plate's own gradient fill for the pad byte and the
; dash for anything the font cannot draw. It is built at boot from CharTile, so
; one rule owns the mapping, and its page alignment makes a lookup one LD L,A.
SECTION "table",RAM
PlateTiles:
DS 256

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
LD [Half],A
LD [ShownCursor],A
LD [FrameCount],A
LD [ShownPhase],A
LD [SplashOn],A
LD [SplashNumber],A
LD [SplashRows],A
LD [SplashSkip],A
LD A,KEY_NONE
LD [ShownKey],A
LD [ShownIndex],A
; The list starts settled and unscrolled whichever way it boots: the splash
; ends on the settled SCY and the cursor starts on slot 0.
LD A,SETTLED_SCY
LD [Scroll],A
LD [ScrollTarget],A
LD A,$E4
LDH [GB_REG_OBP0],A
; The boot splash owns BGP and SCY: it starts on the blank page at SCY 0 and
; ends on the identity palette at the settled 144, where the visible rows are
; the list alone. Two conditions arm it, and both are read once here.
; The catalogue must list at boot: a menu that must wait for the SDRAM starts
; settled and draws every row here as before. BootDraw keeps that answer,
; because it alone decides whether the titles are drawn at boot.
LD A,[LOADER_STATUS]
AND A,LIBRARY_STATUS_SDRAM_READY
LD [BootDraw],A
JR Z,BootSettled
; And this must be the first boot since reset. The loader keeps the last
; selected index, which is $FF only until the first selection, so a menu that
; has been here before - a return from a game, or a reboot after any select,
; refused or not - starts settled and the list is there at once.
LD A,[LOADER_INDEX]
INC A
JR NZ,BootSettled
LD A,1
LD [SplashOn],A
LD A,[FadeSteps]
LDH [GB_REG_BGP],A
XOR A,A
LDH [GB_REG_SCY],A
LD A,BOOT_SLOTS
JR BootRows
BootSettled:
LD A,$E4
LDH [GB_REG_BGP],A
LD A,SETTLED_SCY
LDH [GB_REG_SCY],A
LD A,LIBRARY_SLOTS
BootRows:
LD [BootSlots],A
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
LD DE,Stars
LD B,STAR_BYTES
CopyStars:
LD A,[DE]
INC DE
LD [HL+],A
DEC B
JR NZ,CopyStars
; The footer's two cells on the grey page, derived like the font: they use
; shade 0 and shade 3 only, so the copy keeps the low plane and sets the high.
LD DE,Footer
LD HL,GB_VIEW_TILES_START + TILE_CART * 16
LD B,FOOTER_ART_ROWS
CopyFooterArt:
LD A,[DE]
INC DE
INC DE
LD [HL+],A
LD A,$FF
LD [HL+],A
DEC B
JR NZ,CopyFooterArt
; The press-A badge's two phases on the grey page. The dim phase uses shade 1,
; so the font's derivation would not do: the high plane is set only where the
; low plane is clear, which moves shade 0 to 2 and keeps 1 and 3.
LD DE,Pulse
LD B,PULSE_ART_ROWS
CopyPulseArt:
LD A,[DE]
INC DE
LD [HL+],A
CPL
LD C,A
LD A,[DE]
INC DE
OR A,C
LD [HL+],A
DEC B
JR NZ,CopyPulseArt
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
; The star field, before any row is drawn over it: the slot rows' two blank
; columns, wherever the rule fires. Nothing the list draws touches those
; columns again, so a star stays until the twinkle rewrites it.
CALL PaintStars
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
; The plate cell table, from the same CharTile rule the list draws with, so a
; footer row inside VBlank is one page-aligned lookup a cell.
LD HL,PlateTiles
LD C,0
BuildPlateTiles:
LD A,C
CP A,PLATE_PAD
JR Z,PlateTilePad
CALL CharTile
ADD A,TILE_GREY
JR PlateTileWrite
PlateTilePad:
LD A,TILE_FADE21
PlateTileWrite:
LD [HL+],A
INC C
JR NZ,BuildPlateTiles
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
LD A,[BootSlots]
CP A,C
JR NZ,Numbers
; With the SDRAM ready, fill the window and draw every title before the
; LCD turns on; otherwise the frame loop retries and draws one row per frame.
; The rows drawn here and the rows the slide draws always account for all
; sixteen, because BootSlots came from the same read as BootDraw.
LD A,[BootDraw]
OR A,A
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
LD B,A
LD A,[BootSlots]
CP A,B
JR NZ,DrawAll
; The four rows the slide draws, built as cells while the LCD is off: the
; last three slot rows, then the bottom plate around the blank status row.
; A settled boot has drawn them into the map already and needs none of this.
LD A,[SplashOn]
OR A,A
JR Z,BootListed
LD HL,SplashRowCells
LD C,BOOT_SLOTS
BuildSlotRow:
PUSH HL
LD D,H
LD E,L
PUSH BC
LD A,C
SUB A,BOOT_SLOTS
LD B,STAR_COLUMN_A
CALL StarRowCell
POP BC
LD [DE],A
INC DE
LD A,C
PUSH BC
LD C,TILE_DIGIT
CALL DrawDigits
POP BC
PUSH BC
LD A,C
SUB A,BOOT_SLOTS
LD B,STAR_COLUMN_B
CALL StarRowCell
POP BC
LD [DE],A
INC DE
LD A,C
PUSH BC
CALL DrawTitleAt
POP BC
POP HL
LD A,SCREEN_COLUMNS
ADD A,L
LD L,A
LD A,0
ADC A,H
LD H,A
INC C
LD A,C
CP A,LIBRARY_SLOTS
JR NZ,BuildSlotRow
; The bottom plate rides the window now, so the last row the slide copies is
; the page the plate left behind it.
LD B,SCREEN_COLUMNS
LD A,TILE_BLANK
BuildBlank:
LD [HL+],A
DEC B
JR NZ,BuildBlank
; Every title row is read now, so a select is live as soon as the list is.
BootListed:
LD A,LIBRARY_SLOTS
LD [Pending],A
EnableLCD:
; The window and its plate, built with the LCD off. WX and WY can be set here
; because nothing draws the window until LCDC bit 5 goes on.
CALL WindowPlate
; The footer of the boot cursor's slot, both rows, with the LCD off, so the
; first displayed frame writes nothing. Each call draws at most one row, and a
; boot that listed no catalogue draws neither.
LD A,NO_SLOT
LD [ShownFooterA],A
LD [ShownFooterB],A
LD A,[BootDraw]
OR A,A
JR Z,FooterBooted
XOR A,A
LD [PlateDrawn],A
CALL ShowFooter
CALL ShowFooter
FooterBooted:
LD A,WINDOW_X
LDH [GB_REG_WX],A
LD A,WINDOW_Y
LDH [GB_REG_WY],A
; The cursor object: X at the left edge, phase 0. Its Y stays 0, off screen,
; while the splash runs; the settled frame brings it on, and the window comes
; on with it, so the splash shows neither the cursor nor the plate.
LD A,CURSOR_X
LD [OAM_CURSOR + 1],A
LD A,TILE_POINTER
LD [OAM_CURSOR + 2],A
LD A,[SplashOn]
OR A,A
LD A,LCDC_LIST
JR NZ,LCDOn
CALL RevealCursor
LD A,LCDC_SETTLED
LCDOn:
LDH [GB_REG_LCDC],A
; One sampled update per frame, all map and object writes inside VBlank.
; While the splash runs it owns the frame: no navigation, no catalogue row and
; no status redraw, so the press that skips it never reaches the list.
Frame:
CALL WaitVBlank
CALL ReadButtons
LD A,[SplashOn]
OR A,A
JR Z,ListFrame
CALL SplashStep
LD A,[SplashOn]
OR A,A
JR NZ,Frame
JR Advance
ListFrame:
CALL Navigate
CALL ShowCursor
CALL ShowStatus
; Catalogue draws one title row while the list is short and calls the footer
; once it is whole, so no frame ever draws both.
CALL Catalogue
; One loop iteration per displayed frame, and an iteration's writes appear in
; the frame it numbers, so the counter names that frame and bit 4 of it is
; that frame's nudge phase. It advances after the writes, not before. The
; settled frame of the splash is the menu's own frame 0, so the counter
; starts there.
Advance:
LD A,[FrameCount]
INC A
LD [FrameCount],A
JR Frame

; One displayed frame of the boot splash, numbered by SplashNumber: the fade
; writes BGP, the slide writes SCY and draws at most one wrapped list row, and
; the last slide frame settles. A button edge latches SplashSkip; from then on
; each frame draws up to SKIP_ROWS wrapped rows and takes the schedule's own
; number for the rows drawn, ending on the settled frame, so a skip is two
; frames and every one of them is a frame of the same schedule. The edge is consumed
; here, and a held button raises no further edge, so the list never acts on it.
SplashStep:
LD A,[Pressed]
OR A,A
JR Z,SplashScheduled
LD A,1
LD [SplashSkip],A
SplashScheduled:
LD A,[SplashSkip]
OR A,A
JR Z,SplashFrame
; The skip: at most SKIP_ROWS wrapped rows this VBlank, then the schedule's
; own frame for the rows now drawn, so no VBlank carries more than half the
; map, the map finishes in two frames and every frame shown is a frame of the
; same schedule. The last of them is the settled frame.
LD A,[SplashRows]
CP A,WRAPPED_ROWS
JR NC,SkipSettled
LD B,SKIP_ROWS
SkipRows:
PUSH BC
PUSH AF
CALL DrawWrapped
POP AF
POP BC
INC A
CP A,WRAPPED_ROWS
JR NC,SkipDone
DEC B
JR NZ,SkipRows
SkipDone:
LD [SplashRows],A
CP A,WRAPPED_ROWS
JR NC,SkipSettled
ADD A,FADE_FRAMES - 1
JR SkipTo
SkipSettled:
LD A,SETTLED_FRAME
SkipTo:
LD [SplashNumber],A
SplashFrame:
LD A,[SplashNumber]
CP A,FADE_FRAMES
JR NC,SplashSlide
; The fade: the step this frame's hold puts it in, straight into BGP.
LD B,0
FadeStep:
CP A,FADE_HOLD
JR C,FadeFound
SUB A,FADE_HOLD
INC B
JR FadeStep
FadeFound:
LD A,B
LD HL,FadeSteps
ADD A,L
LD L,A
LD A,0
ADC A,H
LD H,A
LD A,[HL]
LDH [GB_REG_BGP],A
JR SplashNext
; The slide: the identity palette, whatever step a skip left the fade on, and
; SCY at SLIDE_STEP a frame. The frame that first counts a wrapped row draws it, after its splash row has left the top of the screen and before
; the list row it carries reaches the bottom.
SplashSlide:
PUSH AF
LD A,[FadeSteps + FADE_STEPS - 1]
LDH [GB_REG_BGP],A
POP AF
SUB A,FADE_FRAMES - 1
LD D,A
LD B,A
LD C,SLIDE_STEP
XOR A,A
SlideScroll:
ADD A,C
DEC B
JR NZ,SlideScroll
LDH [GB_REG_SCY],A
LD A,[SplashRows]
CP A,WRAPPED_ROWS
JR NC,SplashNext
CP A,D
JR NC,SplashNext
PUSH AF
CALL DrawWrapped
POP AF
INC A
LD [SplashRows],A
SplashNext:
LD A,[SplashNumber]
CP A,SETTLED_FRAME
JR Z,SplashSettle
INC A
LD [SplashNumber],A
RET
; The settled frame: the list is whole, the cursor comes on screen and the
; frame counter starts its count of menu frames here.
SplashSettle:
XOR A,A
LD [SplashOn],A
LD [FrameCount],A
LD [ShownPhase],A
; The window joins the background and the objects here, so the bottom plate
; and the cursor appear together on the settled frame.
LD A,LCDC_SETTLED
LDH [GB_REG_LCDC],A

; The cursor object's Y byte: column 0 of the selected slot's row.
RevealCursor:
LD A,[Cursor]
; A = slot: the object's Y for that slot's row on screen. The row rides the
; scroll ramp, so the pointer is lifted by however far the list has scrolled
; past the settled view; at rest that is nothing.
PointerY:
ADD A,A
ADD A,A
ADD A,A
ADD A,CURSOR_Y
LD B,A
LD A,[Scroll]
SUB A,SETTLED_SCY
LD C,A
LD A,B
SUB A,C
LD [OAM_CURSOR],A
RET

; One step of the scroll ramp: SCY moves SCROLL_STEP toward the target the
; cursor names and the pointer follows its row. Called only when the two
; differ, and only once the list is whole, from the branch the footer hangs
; off, so a frame that draws a title row pays nothing for it.
ScrollStep:
JR C,ScrollDown
SUB A,SCROLL_STEP
JR ScrollWrite
ScrollDown:
ADD A,SCROLL_STEP
ScrollWrite:
LD [Scroll],A
LDH [GB_REG_SCY],A
LD A,[Cursor]
JP PointerY

; A = the wrapped list row, 0..WRAPPED_ROWS-1: its twenty prebuilt cells into
; map row A, the row the splash leaves blank until the slide has carried it
; off the top of the screen.
DrawWrapped:
LD L,A
LD H,0
LD B,H
LD C,L
ADD HL,HL
ADD HL,HL
PUSH HL
ADD HL,HL
ADD HL,HL
POP DE
ADD HL,DE
LD DE,SplashRowCells
ADD HL,DE
LD D,H
LD E,L
LD A,C
ADD A,A
ADD A,A
ADD A,A
ADD A,A
ADD A,A
LD L,A
LD H,HIGH(MAP)
; The twenty cells, unrolled: a skip copies four rows inside one VBlank, and
; the loop's counter and branch would cost more than the copy itself.
LD A,[DE]
INC DE
LD [HL+],A
LD A,[DE]
INC DE
LD [HL+],A
LD A,[DE]
INC DE
LD [HL+],A
LD A,[DE]
INC DE
LD [HL+],A
LD A,[DE]
INC DE
LD [HL+],A
LD A,[DE]
INC DE
LD [HL+],A
LD A,[DE]
INC DE
LD [HL+],A
LD A,[DE]
INC DE
LD [HL+],A
LD A,[DE]
INC DE
LD [HL+],A
LD A,[DE]
INC DE
LD [HL+],A
LD A,[DE]
INC DE
LD [HL+],A
LD A,[DE]
INC DE
LD [HL+],A
LD A,[DE]
INC DE
LD [HL+],A
LD A,[DE]
INC DE
LD [HL+],A
LD A,[DE]
INC DE
LD [HL+],A
LD A,[DE]
INC DE
LD [HL+],A
LD A,[DE]
INC DE
LD [HL+],A
LD A,[DE]
INC DE
LD [HL+],A
LD A,[DE]
INC DE
LD [HL+],A
LD A,[DE]
INC DE
LD [HL+],A
RET

; The cell a map row and column carry: a star where the rule fires, the page
; everywhere else. A = map row, B = column; A returns the tile. The rule is
; ((3 * column + 5 * row) XOR (row >> 2)) AND STAR_MASK, and a star's own tile
; is the one its row, column and nudge phase name, so the field twinkles
; without moving.
StarRowCell:
PUSH DE
LD H,A
LD L,B
ADD A,A
ADD A,A
ADD A,H
LD D,A
LD A,L
ADD A,A
ADD A,L
ADD A,D
LD D,A
LD A,H
SRL A
SRL A
XOR A,D
AND A,STAR_MASK
JR Z,StarCellHit
LD A,TILE_BLANK
POP DE
RET
StarCellHit:
LD A,H
ADD A,L
AND A,STAR_MASK
ADD A,TILE_STAR
POP DE
RET

; The star field, painted into the map while the LCD is off, and the short
; list a twinkle rewrites from. Only the sixteen slot rows can carry a star:
; map rows STAR_ROW_FIRST..MAP_ROWS-1 and the WRAPPED_SLOTS rows the list
; wraps into the map's own top.
PaintStars:
XOR A,A
LD [StarCount],A
LD HL,StarTable
LD A,L
LD [StarPtr],A
LD A,H
LD [StarPtr + 1],A
LD C,0
PaintStarRow:
LD A,C
CP A,WRAPPED_SLOTS
JR C,PaintStarRowOk
CP A,STAR_ROW_FIRST
JR C,PaintStarNext
PaintStarRowOk:
LD B,STAR_COLUMN_A
CALL PaintStarCell
LD B,STAR_COLUMN_B
CALL PaintStarCell
PaintStarNext:
INC C
LD A,C
CP A,MAP_ROWS
JR NZ,PaintStarRow
RET

; C = map row, B = column: paint that cell and remember it, if it is a star.
PaintStarCell:
PUSH BC
LD A,C
CALL StarRowCell
CP A,TILE_BLANK
JR Z,PaintStarDone
PUSH AF
LD L,C
LD H,0
ADD HL,HL
ADD HL,HL
ADD HL,HL
ADD HL,HL
ADD HL,HL
LD A,L
ADD A,B
LD L,A
LD A,H
ADD A,HIGH(MAP)
LD H,A
LD D,H
LD E,L
; A star in a row the list wraps into the map's own top waits for the slide
; to carry that row in: the splash draws those rows blank, and the cells the
; slide copies carry the star themselves. The cell still joins the table, so
; the twinkle rewrites the whole field once the list has settled.
LD A,C
CP A,WRAPPED_SLOTS
JR NC,PaintStarNow
LD A,[SplashOn]
OR A,A
JR NZ,PaintStarWait
PaintStarNow:
POP AF
LD [HL],A
JR PaintStarBase
PaintStarWait:
POP AF
PaintStarBase:
SUB A,TILE_STAR
LD C,A
LD A,[StarCount]
CP A,STAR_SLOTS
JR NC,PaintStarDone
INC A
LD [StarCount],A
LD A,[StarPtr]
LD L,A
LD A,[StarPtr + 1]
LD H,A
LD A,E
LD [HL+],A
LD A,D
LD [HL+],A
LD A,C
LD [HL+],A
LD A,L
LD [StarPtr],A
LD A,H
LD [StarPtr + 1],A
PaintStarDone:
POP BC
RET

; The twinkle: every star cell takes the tile its base and the nudge phase
; name, so the field changes with the same frame-counter bit that nudges the
; cursor and follows from the frame number alone. A = the phase, 0 or 1.
PaintTwinkle:
LD C,A
LD A,[StarCount]
OR A,A
RET Z
LD B,A
LD HL,StarTable
TwinkleCell:
LD A,[HL+]
LD E,A
LD A,[HL+]
LD D,A
LD A,[HL+]
ADD A,C
AND A,STAR_MASK
ADD A,TILE_STAR
LD [DE],A
DEC B
JR NZ,TwinkleCell
RET

; The window's own map, blanked with the LCD off, and the bottom plate it
; carries: the footer row's fill above the status row. The window itself
; stays off until the settled frame, so the splash never shows the plate.
WindowPlate:
LD HL,WMAP
LD BC,1024
LD D,TILE_BLANK
ClearWindowMap:
LD A,D
LD [HL+],A
DEC BC
LD A,B
OR A,C
JR NZ,ClearWindowMap
LD HL,WMAP + FOOTER_ROW * 32
LD A,TILE_CAP_LEFT
LD [HL+],A
LD A,TILE_FADE21
LD B,PLATE_CELLS
FooterFill:
LD [HL+],A
DEC B
JR NZ,FooterFill
LD A,TILE_CAP_RIGHT
LD [HL],A
JP StatusPlate

; The bottom plate: its two caps and the status row between them.
StatusPlate:
LD A,TILE_CAP_LEFT
LD [WMAP + WINDOW_STATUS_ROW * 32],A
LD A,TILE_CAP_RIGHT
LD [STATUS_TEXT_CELLS + PLATE_CELLS],A
JP ShowStatus

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
; The list is whole, so this frame may draw a footer row. The footer hangs off
; this branch so that a frame which draws a title row costs what it always
; did: a JR not taken costs what the RET it replaced did.
JR Z,FooterHook
LD A,[LOADER_STATUS]
AND A,LIBRARY_STATUS_WINDOW_READY
RET Z
; The frame that changes the nudge phase rewrites the pointer's tile and the
; eight star cells, 194 M-cycles on top of the row, and the widest row is over
; a thousand of VBlank's 1140. So that frame draws the first half of the row
; and the next frame draws the rest, the cap the splash skip puts on wrapped
; rows. The phase is untouched: it still follows the frame counter alone.
; The phase changes on every frame whose counter is a multiple of PHASE_BIT
; but the first, and that first one cannot draw a row: the bank is committed
; no earlier than the frame the counter numbers 0, and a row no earlier than
; the frame after it. So the low bits alone decide, which keeps this test to
; nine M-cycles of the row's own frame.
LD A,[Half]
OR A,A
JR NZ,FinishRow
LD A,[FrameCount]
AND A,PHASE_BIT - 1
JR NZ,WholeRow
LD A,1
LD [Half],A
LD A,[Pending]
JP DrawFirstHalf
FinishRow:
XOR A,A
LD [Half],A
LD A,[Pending]
CALL DrawSecondHalf
JR RowDrawn
WholeRow:
LD A,[Pending]
CALL DrawSlot
RowDrawn:
LD A,[Pending]
INC A
LD [Pending],A
RET

; The list is whole: the scroll ramp steps when SCY is not where the cursor
; wants it, then the footer draws at most one row.
FooterHook:
LD A,[ScrollTarget]
LD B,A
LD A,[Scroll]
CP A,B
CALL NZ,ScrollStep
JP ShowFooter

CommitBank:
LD A,CATALOGUE_BANK
LD [LOADER_BANK],A
LD A,1
LD [BankDone],A
RET

; A = slot. Its catalogue entry is at window offset slot * 32; a valid entry
; draws its 16 title bytes, any other entry a blank title. The 16th byte is
; header $0143: the CGB flag values draw blank, any other byte follows
; CharTile. The address arithmetic is inline rather than a call to RowCells
; and EntryCells below, which draw the halves: this is the menu's most
; expensive frame and each call costs it 10 of the 16 M-cycles it has to
; spare.
DrawSlot:
PUSH AF
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
POP AF
; A = slot, DE = its sixteen title cells: wherever the caller wants them. The
; entry address is inline here, not EntryAt's call, because this is the
; delayed catalogue row's own path and its frame is the menu's peak.
DrawTitleAt:
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
LD A,[HL]
CP A,LIBRARY_CATALOGUE_VALID
JR NZ,BlankTitle
LD A,L
ADD A,ENTRY_TITLE
LD L,A
LD B,TITLE_BYTES - 1
LD C,0
CALL DrawText
TitleFlagCell:
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
BlankCells:
LD A,TILE_BLANK
BlankLoop:
LD [DE],A
INC DE
DEC B
JR NZ,BlankLoop
RET

; A = slot -> DE = the slot's sixteen title cells in the map, A kept.
RowCells:
PUSH AF
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
POP AF
RET

; A = slot -> HL = its catalogue entry in the window.
EntryCells:
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
RET

; A = slot: the first TITLE_HALF cells of its title row. The frame that
; changes the nudge phase draws this much and no more.
DrawFirstHalf:
CALL RowCells
CALL EntryCells
LD A,[HL]
CP A,LIBRARY_CATALOGUE_VALID
LD B,TITLE_HALF
JR NZ,BlankCells
LD A,L
ADD A,ENTRY_TITLE
LD L,A
LD C,0
JP DrawText

; A = slot: the cells the frame before it left, TITLE_HALF..15, the last of
; them under the CGB flag rule. A map row is 32 cells aligned and the title
; starts at column TITLE_COLUMN, so the half cannot cross a page.
DrawSecondHalf:
CALL RowCells
PUSH AF
LD A,E
ADD A,TITLE_HALF
LD E,A
POP AF
CALL EntryCells
LD A,[HL]
CP A,LIBRARY_CATALOGUE_VALID
LD B,TITLE_BYTES - TITLE_HALF
JR NZ,BlankCells
LD A,L
ADD A,ENTRY_TITLE + TITLE_HALF
LD L,A
LD B,TITLE_BYTES - TITLE_HALF - 1
LD C,0
CALL DrawText
JP TitleFlagCell

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
; The last slot is the one the window hides at rest, so it alone asks for
; the scrolled view; the ramp itself runs from FooterHook once the list is
; whole. The pointer moves now, at the scroll the list has.
CP A,SCROLL_SLOT
LD B,SETTLED_SCY
JR NZ,ScrollWanted
LD B,SCROLLED_SCY
ScrollWanted:
LD A,B
LD [ScrollTarget],A
LD A,[Cursor]
CALL PointerY
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
; The twinkle rewrites eight cells, so the footer waits for the next frame.
LD A,1
LD [PlateDrawn],A
; The press-A badge pulses on the same bit, once the footer has drawn it.
; While the catalogue is still listing there is no footer and no badge, so
; the delayed path's twinkle frame pays only for this test.
LD A,[ShownFooterA]
CP A,NO_SLOT
CALL NZ,DrawPulse
; The same bit twinkles the star field, so the page and the cursor change
; together and both follow from the frame number alone.
LD A,[ShownPhase]
OR A,A
LD A,0
JR Z,TwinklePhase
LD A,1
TwinklePhase:
JP PaintTwinkle

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
; The message owns the lower row, so the tagline is drawn again once it goes.
LD A,1
LD [PlateDrawn],A
LD A,NO_SLOT
LD [ShownFooterB],A
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
LD DE,STATUS_TEXT_CELLS
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
LD HL,STATUS_TEXT_CELLS
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

; The information footer, at most one plate row a frame. The upper row follows
; the cursor as soon as it moves and the lower row follows in the next frame,
; and a frame that has already drawn the status row or the star twinkle leaves
; both to the one after it, so no VBlank writes two plate rows. Only Catalogue
; calls this, and only once the list is whole, so a frame that draws a title
; row draws no footer row and pays nothing for the choice.
ShowFooter:
LD A,[PlateDrawn]
OR A,A
JR NZ,FooterDone
LD A,[Cursor]
LD B,A
LD A,[ShownFooterA]
CP A,B
JR Z,FooterLower
CALL FooterRowA
JR FooterDone
FooterLower:
; A status message owns the lower row while it is shown.
LD A,[ShownKey]
CP A,LIBRARY_RESULT_INVALID_SLOT
JR NC,FooterDone
LD A,[ShownFooterB]
CP A,B
JR Z,FooterDone
CALL FooterRowB
FooterDone:
XOR A,A
LD [PlateDrawn],A
RET

; B = slot. The upper row's text cells: the entry's profile word and size, or
; the empty-slot line. The badge beside them was written with the LCD off.
FooterRowA:
LD A,B
LD [ShownFooterA],A
; The badge belongs to the footer, not to the plate: a window that carries no
; footer carries no badge either, so this row writes it.
LD A,TILE_CART
LD [FOOTER_PLATE + FOOTER_BADGE_COLUMN],A
; The press-A badge comes with it, in the phase the frame is in; from here on
; the phase change keeps it pulsing.
CALL DrawPulse
LD A,B
CALL EntryAt
LD A,[HL]
CP A,LIBRARY_CATALOGUE_VALID
JR Z,FooterEntry
LD BC,FooterEmpty
JP FooterLine
FooterEntry:
PUSH HL
LD A,L
ADD A,ENTRY_PROFILE
LD L,A
LD A,[HL]
; The word of the profile ID, or the dashes of one the menu does not know.
DEC A
CP A,FOOTER_PROFILES
JR C,FooterProfile
LD A,FOOTER_PROFILES
FooterProfile:
LD L,A
LD H,0
ADD HL,HL
ADD HL,HL
ADD HL,HL
ADD HL,HL
LD BC,FooterProfiles
ADD HL,BC
LD B,H
LD C,L
CALL FooterLine
POP HL
; The size: whole kibibytes of the 24-bit length.
LD A,L
ADD A,ENTRY_LENGTH
LD L,A
LD A,[HL+]
LD E,A
LD A,[HL]
LD D,A
LD A,L
ADD A,ENTRY_LENGTH_HIGH - ENTRY_LENGTH - 1
LD L,A
LD A,[HL]
LD C,A
; A length that is not whole kibibytes has no size to show.
LD A,E
OR A,A
JR NZ,FooterNoSize
LD A,D
AND A,3
JR NZ,FooterNoSize
; kb = length >> 10: the high byte moved up six places, then bits 15:10.
LD L,C
LD H,0
ADD HL,HL
ADD HL,HL
ADD HL,HL
ADD HL,HL
ADD HL,HL
ADD HL,HL
SRL D
SRL D
LD A,D
OR A,L
LD L,A
LD DE,FOOTER_TEXT + FOOTER_DIGIT_COLUMN
LD A,H
CP A,HIGH(KIBIBYTE_DIGITS)
JR C,FooterNumber
JR NZ,FooterDashes
LD A,L
CP A,LOW(KIBIBYTE_DIGITS)
JR C,FooterNumber
JR FooterDashes
FooterNoSize:
LD DE,FOOTER_TEXT + FOOTER_DIGIT_COLUMN
; A part kibibyte, or more kibibytes than three digits hold, draws dashes
; rather than a wrong number.
FooterDashes:
LD A,TILE_DASH + TILE_GREY
LD B,FOOTER_DIGITS
FooterDash:
LD [DE],A
INC DE
DEC B
JR NZ,FooterDash
RET

; HL = kibibytes under KIBIBYTE_DIGITS, DE = the three digit cells: the number
; on the grey page, with blanks before its first digit.
FooterNumber:
LD B,TILE_BLANK + TILE_GREY
LD C,255
FooterHundreds:
INC C
LD A,L
SUB A,100
LD L,A
LD A,H
SBC A,0
LD H,A
JR NC,FooterHundreds
LD A,L
ADD A,100
LD L,A
LD A,C
CALL FooterDigit
LD C,255
FooterTens:
INC C
LD A,L
SUB A,10
LD L,A
JR NC,FooterTens
LD A,L
ADD A,10
LD L,A
LD A,C
CALL FooterDigit
LD A,L
ADD A,TILE_DIGIT + TILE_GREY
LD [DE],A
RET

; A = digit. A zero before the first digit draws B, the blank; from the first
; digit on B is the zero glyph, so an inner zero prints.
FooterDigit:
OR A,A
JR NZ,FooterDigitInk
LD A,B
JR FooterDigitWrite
FooterDigitInk:
ADD A,TILE_DIGIT + TILE_GREY
LD B,TILE_DIGIT + TILE_GREY
FooterDigitWrite:
LD [DE],A
INC DE
RET

; BC = FOOTER_TEXT_CELLS characters, drawn into the upper row's text cells
; through the plate table. The pad byte keeps the plate's own fill.
FooterLine:
LD DE,FOOTER_TEXT
LD H,HIGH(PlateTiles)
FooterLineCell:
LD A,[BC]
INC BC
LD L,A
LD A,[HL]
LD [DE],A
INC DE
LD A,E
CP A,LOW(FOOTER_TEXT + FOOTER_TEXT_CELLS)
JR NZ,FooterLineCell
RET

; B = slot. The lower row: the entry's tagline centred in the plate's cells,
; the plate's own fill on either side. A record is LIBRARY_TAGLINE_CHARS
; characters then zeros, so both scans below stop inside it, and an all-zero
; record leaves the plate alone.
FooterRowB:
LD A,B
LD [ShownFooterB],A
CALL TaglineAt
LD B,H
LD C,L
LD D,0
FooterCount:
LD A,[HL+]
OR A,A
JR Z,FooterCounted
INC D
LD A,D
CP A,LIBRARY_TAGLINE_CHARS
JR NZ,FooterCount
FooterCounted:
LD A,PLATE_CELLS
SUB A,D
SRL A
LD E,A
LD HL,STATUS_TEXT_CELLS
OR A,A
JR Z,FooterGlyphs
LD A,TILE_FADE21
FooterLead:
LD [HL+],A
DEC E
JR NZ,FooterLead
FooterGlyphs:
LD A,D
OR A,A
JR Z,FooterTail
LD D,H
LD E,L
LD H,HIGH(PlateTiles)
FooterGlyph:
LD A,[BC]
OR A,A
JR Z,FooterGlyphsDone
INC BC
LD L,A
LD A,[HL]
LD [DE],A
INC DE
LD A,E
CP A,LOW(STATUS_TEXT_CELLS + PLATE_CELLS)
JR NZ,FooterGlyph
FooterGlyphsDone:
LD H,D
LD L,E
FooterTail:
LD A,L
CP A,LOW(STATUS_TEXT_CELLS + PLATE_CELLS)
RET Z
LD A,TILE_FADE21
LD [HL+],A
JR FooterTail

; The press-A badge in the nudge phase the frame is in: the dim cell on phase
; 0, the ink cell on phase 1. Only A and the flags are touched, so FooterRowA
; keeps its slot in B across the call.
DrawPulse:
LD A,[ShownPhase]
OR A,A
LD A,TILE_PULSE
JR Z,PulseWrite
INC A
PulseWrite:
LD [FOOTER_PLATE + PULSE_COLUMN],A
RET

; A = slot -> HL = its catalogue entry in the window bank.
EntryAt:
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
RET

; A = slot -> HL = its tagline record: TAGLINE_OFFSET behind the entries, at a
; LIBRARY_TAGLINE_BYTES stride, in the same window bank.
TaglineAt:
LD L,A
LD H,0
ADD HL,HL
ADD HL,HL
ADD HL,HL
LD D,H
LD E,L
ADD HL,HL
ADD HL,DE
LD DE,GB_ROM1_START + TAGLINE_OFFSET
ADD HL,DE
RET

; The four fade steps: the page first, then the ink, then the mid shades,
; ending on the identity palette. src/dv/menu/reference.py holds the same four.
FadeSteps:
DB $00,$40,$90,$E4
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
; The upper footer row's sixteen characters, one line per profile ID and then
; the dashes of an unknown one: the profile word, the size's three digit cells
; and ' KB'. The pad byte keeps the plate's gradient fill, as the status rows
; do, and the zeros are placeholders the size digits overwrite.
FooterProfiles:
DB "DIRECT  000 KB##"
DB "LOADER  000 KB##"
DB "MBC1    000 KB##"
DB "------  000 KB##"
FooterEmpty:
DB "EMPTY SLOT######"
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
Stars:
ASSET "Stars"
Footer:
ASSET "Footer"
Pulse:
ASSET "Pulse"
