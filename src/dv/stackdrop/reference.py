"""Independent integer rules for the original Stackdrop contract."""
from dataclasses import dataclass, field

SHAPES = (
    ((0, 1), (1, 1), (2, 1), (3, 1)),
    ((1, 0), (2, 0), (1, 1), (2, 1)),
    ((1, 0), (0, 1), (1, 1), (2, 1)),
    ((2, 0), (0, 1), (1, 1), (2, 1)),
    ((0, 0), (0, 1), (1, 1), (2, 1)),
    ((1, 0), (2, 0), (0, 1), (1, 1)),
    ((0, 0), (1, 0), (1, 1), (2, 1)),
)


def cells(piece, rotation):
    points = SHAPES[piece]
    if piece != 1:
        edge = 3 if piece == 0 else 2
        for _ in range(rotation % 4):
            points = tuple((edge-y, x) for x, y in points)
    return points


@dataclass
class Game:
    board: list = field(default_factory=lambda: [0]*96)
    piece: int = 0
    rotation: int = 0
    x: int = 2
    y: int = 0
    score: int = 0
    status: int = 0
    previous: int = 0
    gravity: int = 0

    def valid(self, x, y, rotation):
        return all(0 <= x+dx < 8 and 0 <= y+dy < 12
                   and not self.board[(y+dy)*8+x+dx]
                   for dx, dy in cells(self.piece, rotation))

    def spawn(self):
        self.x, self.y, self.rotation, self.gravity = 2, 0, 0, 0
        if not self.valid(2, 0, 0):
            self.status = 2

    def lock(self):
        for dx, dy in cells(self.piece, self.rotation):
            self.board[(self.y+dy)*8+self.x+dx] = 1
        rows = [self.board[i:i+8] for i in range(0, 96, 8)]
        kept = [row for row in rows if not all(row)]
        count = 12-len(kept)
        self.board = [0]*(8*count)+[v for row in kept for v in row]
        self.score = min(9999, self.score+100*count)
        self.piece = (self.piece+1) % 7
        self.spawn()

    def update(self, buttons):
        edges = buttons & ~self.previous
        self.previous = buttons
        if self.status != 1:
            if edges & 128:
                self.board = [0]*96
                self.piece, self.score, self.status = 0, 0, 1
                self.spawn()
            return
        horizontal = edges & 3
        if buttons & 3 != 3 and horizontal in (1, 2):
            x = self.x+(1 if horizontal == 1 else -1)
            if self.valid(x, self.y, self.rotation):
                self.x = x
        if edges & 16 and self.valid(self.x, self.y, (self.rotation+1) % 4):
            self.rotation = (self.rotation+1) % 4
        if edges & 32:
            while self.valid(self.x, self.y+1, self.rotation):
                self.y += 1
            self.lock()
            return
        self.gravity += 1
        if edges & 8 or self.gravity == 60:
            self.gravity = 0
            if self.valid(self.x, self.y+1, self.rotation):
                self.y += 1
            else:
                self.lock()
