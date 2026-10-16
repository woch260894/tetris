"""俄罗斯方块。

运行（在项目目录下）：
    .\\venv\\Scripts\\python tetris.py
"""

from __future__ import annotations

import random
import sys
from dataclasses import dataclass

import pygame

COLS = 10
ROWS = 20
CELL = 32
SIDEBAR = 180
MARGIN = 16
WIDTH = MARGIN * 2 + COLS * CELL + SIDEBAR
HEIGHT = MARGIN * 2 + ROWS * CELL
FPS = 60

# 七种方块，坐标相对旋转中心
SHAPES: dict[str, list[tuple[int, int]]] = {
    "I": [(-1, 0), (0, 0), (1, 0), (2, 0)],
    "O": [(0, 0), (1, 0), (0, 1), (1, 1)],
    "T": [(-1, 0), (0, 0), (1, 0), (0, 1)],
    "S": [(-1, 1), (0, 1), (0, 0), (1, 0)],
    "Z": [(-1, 0), (0, 0), (0, 1), (1, 1)],
    "J": [(-1, 0), (0, 0), (1, 0), (-1, 1)],
    "L": [(-1, 0), (0, 0), (1, 0), (1, 1)],
}

COLORS = {
    "I": (80, 220, 230),
    "O": (240, 210, 70),
    "T": (180, 90, 220),
    "S": (90, 210, 110),
    "Z": (230, 80, 90),
    "J": (80, 120, 230),
    "L": (240, 150, 60),
}

LINE_SCORES = {1: 100, 2: 300, 3: 500, 4: 800}
# SRS 墙踢（顺时针 / 逆时针的偏移尝试）
KICKS = [(0, 0), (-1, 0), (1, 0), (0, -1), (-1, -1), (1, -1)]


@dataclass
class Piece:
    kind: str
    x: int
    y: int
    cells: list[tuple[int, int]]

    def blocks(self) -> list[tuple[int, int]]:
        return [(self.x + cx, self.y + cy) for cx, cy in self.cells]


def rotate_cells(cells: list[tuple[int, int]], direction: int) -> list[tuple[int, int]]:
    if direction > 0:
        return [(-cy, cx) for cx, cy in cells]
    return [(cy, -cx) for cx, cy in cells]


class Game:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.board: list[list[str | None]] = [[None] * COLS for _ in range(ROWS)]
        self.bag: list[str] = []
        self.next_kind = self._draw()
        self.piece = self._spawn(self._draw())
        self.score = 0
        self.lines = 0
        self.level = 1
        self.game_over = False
        self.paused = False
        self.drop_timer = 0.0
        self.lock_delay = 0.0
        self.clear_flash: list[int] = []
        self.flash_timer = 0.0

    def _draw(self) -> str:
        if not self.bag:
            self.bag = list(SHAPES)
            random.shuffle(self.bag)
        return self.bag.pop()

    def _spawn(self, kind: str) -> Piece:
        return Piece(kind, COLS // 2 - 1, 0, list(SHAPES[kind]))

    def drop_interval(self) -> float:
        return max(0.08, 0.8 - (self.level - 1) * 0.07)

    def fits(self, piece: Piece, cells: list[tuple[int, int]] | None = None) -> bool:
        for x, y in piece.blocks() if cells is None else [
            (piece.x + cx, piece.y + cy) for cx, cy in cells
        ]:
            if x < 0 or x >= COLS or y >= ROWS:
                return False
            if y >= 0 and self.board[y][x] is not None:
                return False
        return True

    def move(self, dx: int, dy: int) -> bool:
        if self.game_over or self.paused:
            return False
        trial = Piece(self.piece.kind, self.piece.x + dx, self.piece.y + dy, self.piece.cells)
        if self.fits(trial):
            self.piece = trial
            self.lock_delay = 0.0
            return True
        return False

    def rotate(self, direction: int) -> bool:
        if self.game_over or self.paused or self.piece.kind == "O":
            return False
        spun = rotate_cells(self.piece.cells, direction)
        for kx, ky in KICKS:
            trial = Piece(self.piece.kind, self.piece.x + kx, self.piece.y + ky, spun)
            if self.fits(trial):
                self.piece = trial
                self.lock_delay = 0.0
                return True
        return False

    def hard_drop(self) -> None:
        if self.game_over or self.paused:
            return
        distance = 0
        while self.move(0, 1):
            distance += 1
        self.score += distance * 2
        self.lock()

    def ghost_y(self) -> int:
        y = self.piece.y
        while True:
            trial = Piece(self.piece.kind, self.piece.x, y + 1, self.piece.cells)
            if not self.fits(trial):
                return y
            y += 1

    def lock(self) -> None:
        for x, y in self.piece.blocks():
            if y < 0:
                self.game_over = True
                return
            self.board[y][x] = self.piece.kind
        full = [y for y in range(ROWS) if all(self.board[y])]
        if full:
            self.clear_flash = full
            self.flash_timer = 0.12
            return
        self._spawn_next()

    def _apply_clears(self) -> None:
        count = len(self.clear_flash)
        for y in sorted(self.clear_flash):
            del self.board[y]
            self.board.insert(0, [None] * COLS)
        self.lines += count
        self.score += LINE_SCORES.get(count, 0) * self.level
        self.level = self.lines // 10 + 1
        self.clear_flash = []
        self._spawn_next()

    def _spawn_next(self) -> None:
        self.piece = self._spawn(self.next_kind)
        self.next_kind = self._draw()
        if not self.fits(self.piece):
            self.game_over = True

    def tick(self, dt: float) -> None:
        if self.game_over or self.paused:
            return
        if self.clear_flash:
            self.flash_timer -= dt
            if self.flash_timer <= 0:
                self._apply_clears()
            return
        self.drop_timer += dt
        if self.drop_timer >= self.drop_interval():
            self.drop_timer = 0.0
            if not self.move(0, 1):
                self.lock_delay += self.drop_interval()
                if self.lock_delay >= 0.45:
                    self.lock()


def draw_cell(
    surface: pygame.Surface,
    x: int,
    y: int,
    color: tuple[int, int, int],
    origin: tuple[int, int],
    alpha: int = 255,
) -> None:
    rect = pygame.Rect(origin[0] + x * CELL, origin[1] + y * CELL, CELL - 1, CELL - 1)
    if alpha < 255:
        overlay = pygame.Surface((CELL - 1, CELL - 1), pygame.SRCALPHA)
        overlay.fill((*color, alpha))
        surface.blit(overlay, rect.topleft)
        return
    pygame.draw.rect(surface, color, rect, border_radius=4)
    highlight = tuple(min(255, c + 40) for c in color)
    pygame.draw.rect(surface, highlight, rect, width=2, border_radius=4)


def draw(screen: pygame.Surface, game: Game, font: pygame.font.Font, small: pygame.font.Font) -> None:
    screen.fill((18, 20, 28))
    origin = (MARGIN, MARGIN)
    board_rect = pygame.Rect(origin[0] - 4, origin[1] - 4, COLS * CELL + 7, ROWS * CELL + 7)
    pygame.draw.rect(screen, (32, 36, 48), board_rect, border_radius=6)

    for y in range(ROWS):
        for x in range(COLS):
            kind = game.board[y][x]
            if kind and y not in game.clear_flash:
                draw_cell(screen, x, y, COLORS[kind], origin)
            else:
                cell = pygame.Rect(origin[0] + x * CELL, origin[1] + y * CELL, CELL - 1, CELL - 1)
                pygame.draw.rect(screen, (24, 27, 36), cell, border_radius=3)

    if not game.game_over and not game.clear_flash:
        gy = game.ghost_y()
        for x, y in Piece(game.piece.kind, game.piece.x, gy, game.piece.cells).blocks():
            if y >= 0:
                draw_cell(screen, x, y, COLORS[game.piece.kind], origin, alpha=70)
        for x, y in game.piece.blocks():
            if y >= 0:
                draw_cell(screen, x, y, COLORS[game.piece.kind], origin)

    panel_x = MARGIN + COLS * CELL + 28
    title = font.render("俄罗斯方块", True, (240, 240, 245))
    screen.blit(title, (panel_x, MARGIN))

    screen.blit(small.render("下一块", True, (180, 186, 200)), (panel_x, 78))
    preview_origin = (panel_x + 8, 112)
    for cx, cy in SHAPES[game.next_kind]:
        draw_cell(screen, cx + 1, cy + 1, COLORS[game.next_kind], preview_origin)

    stats = [
        ("分数", str(game.score)),
        ("消行", str(game.lines)),
        ("等级", str(game.level)),
    ]
    for i, (label, value) in enumerate(stats):
        y = 230 + i * 56
        screen.blit(small.render(label, True, (160, 166, 180)), (panel_x, y))
        screen.blit(font.render(value, True, (245, 245, 250)), (panel_x, y + 18))

    help_lines = ["← → 移动", "↑ 旋转", "↓ 软降", "空格 硬降", "P 暂停", "R 重开"]
    for i, line in enumerate(help_lines):
        screen.blit(small.render(line, True, (130, 136, 150)), (panel_x, HEIGHT - 150 + i * 20))

    if game.paused or game.game_over:
        shade = pygame.Surface((COLS * CELL, ROWS * CELL), pygame.SRCALPHA)
        shade.fill((10, 12, 18, 170))
        screen.blit(shade, origin)
        text = "暂停" if game.paused else "游戏结束"
        label = font.render(text, True, (255, 255, 255))
        hint = small.render("按 R 重新开始", True, (210, 214, 224))
        screen.blit(label, label.get_rect(center=(origin[0] + COLS * CELL // 2, origin[1] + ROWS * CELL // 2 - 12)))
        screen.blit(hint, hint.get_rect(center=(origin[0] + COLS * CELL // 2, origin[1] + ROWS * CELL // 2 + 22)))


def main() -> None:
    pygame.init()
    pygame.display.set_caption("俄罗斯方块")
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("microsoftyahei", 28)
    small = pygame.font.SysFont("microsoftyahei", 16)
    game = Game()
    soft_drop = False

    while True:
        dt = clock.tick(FPS) / 1000
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit(0)
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    sys.exit(0)
                if event.key == pygame.K_r:
                    game.reset()
                elif event.key == pygame.K_p:
                    if not game.game_over:
                        game.paused = not game.paused
                elif event.key in (pygame.K_LEFT, pygame.K_a):
                    game.move(-1, 0)
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    game.move(1, 0)
                elif event.key in (pygame.K_UP, pygame.K_w, pygame.K_x):
                    game.rotate(1)
                elif event.key in (pygame.K_z,):
                    game.rotate(-1)
                elif event.key == pygame.K_DOWN:
                    soft_drop = True
                elif event.key == pygame.K_SPACE:
                    game.hard_drop()
            elif event.type == pygame.KEYUP and event.key == pygame.K_DOWN:
                soft_drop = False

        if soft_drop and not game.paused and not game.game_over:
            if game.move(0, 1):
                game.score += 1
                game.drop_timer = 0.0

        game.tick(dt)
        draw(screen, game, font, small)
        pygame.display.flip()


if __name__ == "__main__":
    main()
