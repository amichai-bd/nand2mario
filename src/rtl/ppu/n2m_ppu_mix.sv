`timescale 1ns/1ps
`default_nettype none
// Copyright (c) 2015 Till Harbaum <till@harbaum.org>
// SPDX-License-Identifier: GPL-3.0-or-later
// Derived from MiSTer video.v; exact source/hash and changes: upstream.json.
// This file is free software under GPL version 3 or later, without warranty.
// See GPL-3.0.txt and THIRD_PARTY.md. Project adaptation: pure DMG mixer,
// explicit disabled-BG priority, named logic-only ports, no platform state.
module n2m_ppu_mix (
    input logic background_enable, object_enable,
    input logic [1:0] background_color, object_color,
    input logic object_behind_background, object_palette_select,
    input logic [7:0] background_palette, object_palette0, object_palette1,
    output logic [1:0] shade
);
    logic [1:0] effective_background;
    logic [7:0] selected_object_palette;
    always_comb begin
        effective_background = background_enable ? background_color : 2'd0;
        selected_object_palette = object_palette_select ? object_palette1 : object_palette0;
        shade = background_palette[{effective_background, 1'b0} +: 2];
        // The object input is already the winning nontransparent object.
        // Its BG-priority flag must not select a different losing object.
        if (object_enable && object_color != 2'd0 &&
            (!object_behind_background || effective_background == 2'd0))
            shade = selected_object_palette[{object_color, 1'b0} +: 2];
    end
endmodule
