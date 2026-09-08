#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "Core/gb.h"
#include "Core/memory.h"
#include "Core/display.h"
#include "n2m_profile.h"
static uint32_t pixels[160*144];
static uint32_t encode(GB_gameboy_t *gb,uint8_t r,uint8_t g,uint8_t b) { return (r<<16)|(g<<8)|b; }
static unsigned ticks, step, frame;
bool n2m_pixel_observation_enabled(void) { return true; }
static void visible_frame(GB_gameboy_t *gb, GB_vblank_type_t type) {
    printf("frame index=%u type=%u native_ticks8mhz=%u skip=%u\n",frame,type,ticks+gb->cycles_since_run,gb->frame_skip_state);
    for (unsigned y=0;y<144;y++) for (unsigned x=0;x<160;x++)
        printf("visible frame=%u x=%u y=%u rgb=%06x\n",frame,x,y,pixels[y*160+x]);
    frame++;
}
static int closing_step = -1;
static unsigned closing_tick;
void n2m_observe_advance(GB_gameboy_t *gb) {
    unsigned now=ticks+gb->cycles_since_run;
    if (closing_step<0 || now<closing_tick) return;
    if (now!=closing_tick) { fprintf(stderr,"closing fetch boundary overshot\n"); exit(5); }
    for (unsigned p=0;p<4;p++) for(unsigned key=0;key<GB_KEY_MAX;key++)
        if(gb->keys[p][key]) { fprintf(stderr,"unsupported input change\n"); exit(5); }
    printf("closing step=%d native_dot=%u ie=%02x if=%02x buttons=0\n",closing_step,now/2,gb->interrupt_enable,gb->io_registers[GB_IO_IF]);
    closing_step=-1;
}
void n2m_observe_fetch_boundary(GB_gameboy_t *gb, unsigned kind) {
    if (closing_step>=0) { fprintf(stderr,"overlapping fetch observations\n"); exit(5); }
    if(step || kind==2) {
        closing_step=kind==2 ? (int)step : (int)step-1;
        closing_tick=ticks+gb->cycles_since_run+gb->pending_cycles*2;
    }
    printf("fetch step=%u kind=%u native_dot=%u pending=%u\n",step,kind,(ticks+gb->cycles_since_run)/2,gb->pending_cycles);
}
void n2m_observe_pixel(GB_gameboy_t *gb, unsigned x, unsigned y, uint32_t rgb) {
    printf("pixel native_ticks8mhz=%u pending_display_ticks8mhz=%d x=%u y=%u rgb=%06x skip=%u\n", ticks+gb->cycles_since_run,gb->display_cycles,x,y,rgb,gb->frame_skip_state);
}
static uint8_t read_observer(GB_gameboy_t *gb, uint16_t address, uint8_t value) {
    printf("read step=%u dot=%u address=%04x data=%02x\n",step,(ticks+gb->cycles_since_run)/2,address,value);
    return value;
}
static bool write_observer(GB_gameboy_t *gb, uint16_t address, uint8_t value) {
    printf("write dot=%u address=%04x data=%02x\n", (ticks + gb->cycles_since_run)/2, address, value);
    return true;
}
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    GB_gameboy_t gb;
    extern bool n2m_direct_profile(GB_gameboy_t *, const char *);
    if (!n2m_direct_profile(&gb,argv[1])) return 3;
    GB_set_rgb_encode_callback(&gb,encode);
    GB_set_pixels_output(&gb,pixels);
    GB_set_vblank_callback(&gb,visible_frame);
    GB_set_palette(&gb,&GB_PALETTE_GREY);
    printf("profile joyp=%02x sc=%02x div=%u stat=%02x pending=%u dma=%02x\n",GB_read_memory(&gb,0xFF00),GB_read_memory(&gb,0xFF02),gb.div_counter,GB_read_memory(&gb,0xFF41),gb.pending_cycles,gb.dma_current_dest);
    GB_set_write_memory_callback(&gb, write_observer);
    GB_set_read_memory_callback(&gb, read_observer);
    /* Native observations remain unprojected; this is not an ABI comparison. */
    for (step = 0; step < PROBE_EVENT_BOUND; step++) {
        unsigned before = gb.pc;
        ticks += GB_run(&gb);
        printf("event=%u before=%04x after=%04x dot=%u af=%04x bc=%04x de=%04x hl=%04x sp=%04x ime=%u delay=%u halt=%u stop=%u bug=%u ie=%02x if=%02x\n", step, before, gb.pc, ticks/2, gb.af, gb.bc, gb.de, gb.hl, gb.sp, gb.ime, gb.ime_toggle, gb.halted, gb.stopped, gb.halt_bug, gb.interrupt_enable, gb.io_registers[GB_IO_IF]);
        if (gb.halted) break;
    }
    if (!gb.halted) { fprintf(stderr,"native event bound reached before HALT\n"); return 4; }
    /* Continue authoritative HALT/peripheral service without idle retirements. */
    while (ticks/2 < PROBE_DOT_BOUND) {
        step++;
        ticks += GB_run(&gb);
        if (!gb.halted) { fprintf(stderr,"unexpected HALT exit\n"); return 4; }
    }
    GB_free(&gb);
    return 0;
}
