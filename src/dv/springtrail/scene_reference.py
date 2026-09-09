"""Independent ordinary OAM layout for the interaction scene."""

def image(game):
    p = game.player
    objects = [(p.x//16, p.y//16, 12, p.fell),
               (game.enemy_x//16, 120, 16, False)]
    objects += [(x, y, 18, bool(game.collected & (1 << i)))
                for i, (x, y) in enumerate(((96, 88), (264, 72), (464, 88), (656, 80)))]
    objects += [(736, 112, 20, False)]
    data = bytearray()
    for x, y, tile, hidden in objects:
        screen_x = x - p.camera
        visible = not hidden and -7 <= screen_x < 160 and -15 <= y < 144
        data.extend(((y + 16) & 255 if visible else 0, (screen_x + 8) & 255, tile, 0))
    data.extend((16, 152, 22 + game.score*2, 0, 16, 80, 32 + game.mode*2, 0))
    return bytes(data)
