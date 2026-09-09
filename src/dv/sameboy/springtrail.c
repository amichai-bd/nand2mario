/* Original public-framebuffer runner; the pinned Core is unmodified. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "Core/gb.h"
#include "Core/display.h"
#include "Core/joypad.h"
#include "Core/memory.h"
#include "n2m_profile.h"

static uint32_t pixels[160 * 144];
static uint64_t ticks;
static unsigned frames, normal_frames, applied;
static uint8_t buttons;
static FILE *images;
static const char *fault;
static uint32_t encode(GB_gameboy_t *gb, uint8_t r, uint8_t g, uint8_t b)
{ (void)gb; return (r << 16) | (g << 8) | b; }

static void visible_frame(GB_gameboy_t *gb, GB_vblank_type_t type)
{
    uint8_t shades[160 * 144];
    for (unsigned i = 0; i < sizeof(shades); i++) {
        switch (pixels[i]) {
            case 0xffffff: shades[i] = 0; break;
            case 0xaaaaaa: shades[i] = 1; break;
            case 0x555555: shades[i] = 2; break;
            case 0: shades[i] = 3; break;
            default: fprintf(stderr, "unknown grayscale pixel\n"); exit(4);
        }
    }
    if (!strcmp(fault, "frame") && frames == 0) shades[0] ^= 1;
    if (fwrite(shades, 1, sizeof(shades), images) != sizeof(shades)) exit(5);
    printf("{\"kind\":\"frame\",\"index\":%u,\"type\":%u,\"dot\":%llu,\"mode\":%u",
           frames++, type, (unsigned long long)((ticks + gb->cycles_since_run) / 2),
           GB_read_memory(gb, 0xc000));
    if (PROBE_BUTTONS) printf(",\"buttons\":%u", GB_read_memory(gb, 0xc019));
    puts("}");
    if (type == GB_VBLANK_TYPE_NORMAL_FRAME) normal_frames++;
}

int main(int argc, char **argv)
{
    if (argc != 4) return 2;
    extern bool n2m_direct_profile(GB_gameboy_t *, const char *);
    GB_gameboy_t gb;
    fault = argv[3];
    images = fopen(argv[2], "wb");
    if (!images || !n2m_direct_profile(&gb, argv[1])) return 3;
    GB_set_rgb_encode_callback(&gb, encode);
    GB_set_pixels_output(&gb, pixels);
    GB_set_vblank_callback(&gb, visible_frame);
    GB_set_palette(&gb, &GB_PALETTE_GREY);
    const unsigned input_dots[] = {INPUT_DOT_0, INPUT_DOT_1};
    const uint8_t masks[] = {INPUT_MASK_0, INPUT_MASK_1};
    while (normal_frames < PROBE_FRAME_COUNT && ticks / 2 < PROBE_DOT_BOUND) {
        if (!strcmp(fault, "progress") && ticks / 2 >= 100000) break;
        if (applied < 2 && ticks / 2 >= input_dots[applied]) {
            buttons = masks[applied];
            if (!strcmp(fault, "input")) buttons = 0;
            for (unsigned key = 0; key < GB_KEY_MAX; key++)
                GB_set_key_state(&gb, key, (buttons >> key) & 1);
            printf("{\"kind\":\"input\",\"index\":%u,\"dot\":%llu,\"buttons\":%u}\n",
                   applied++, (unsigned long long)(ticks / 2), buttons);
        }
        ticks += GB_run(&gb);
    }
    if (fclose(images)) return 6;
    printf("{\"kind\":\"end\",\"frames\":%u,\"normal_frames\":%u,\"inputs\":%u,\"dot\":%llu}\n",
           frames, normal_frames, applied, (unsigned long long)(ticks / 2));
    GB_free(&gb);
    return 0;
}
