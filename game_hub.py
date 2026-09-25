#!/usr/bin/env python3
from __future__ import annotations

import math
import random
import time


BLACK = (0, 0, 0, 255)
BG = (3, 7, 12, 255)
PANEL = (8, 20, 27, 255)
CYAN = (18, 238, 242, 255)
CYAN_DIM = (8, 88, 96, 255)
WHITE = (240, 255, 255, 255)
MAGENTA = (255, 65, 175, 255)
YELLOW = (255, 214, 70, 255)
GREEN = (85, 245, 150, 255)
RED = (255, 82, 82, 255)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def dim(
    color: tuple[int, int, int, int],
    strength: float,
) -> tuple[int, int, int, int]:
    s = clamp(strength, 0.0, 1.0)
    return (
        int(color[0] * s),
        int(color[1] * s),
        int(color[2] * s),
        255,
    )


class GameHub:
    """Small touch-first games that run directly on the native Desk Buddy UI.

    These games are original phone-side implementations. They do not depend on
    camera input, OpenCV, a browser, or network access.
    """

    def __init__(self) -> None:
        self.active = False
        self.mode = "menu"
        self.caption_text = ""
        self.caption_until = 0.0

        self.touch_down_x = 0.0
        self.touch_down_y = 0.0
        self.pending_action = ""

        self.ttt_board = [""] * 9
        self.ttt_done = False
        self.ttt_result = ""

        self.pong_ball_x = 0.50
        self.pong_ball_y = 0.52
        self.pong_vx = 0.31
        self.pong_vy = 0.42
        self.pong_user_x = 0.50
        self.pong_buddy_x = 0.50
        self.pong_user_score = 0
        self.pong_buddy_score = 0
        self.pong_last = time.monotonic()

        self.snake: list[tuple[int, int]] = []
        self.snake_direction = (1, 0)
        self.snake_next_direction = (1, 0)
        self.snake_food = (10, 10)
        self.snake_last_step = time.monotonic()
        self.snake_done = False
        self.snake_score = 0

    def _say(self, text: str, seconds: float = 3.4) -> None:
        self.caption_text = text
        self.caption_until = time.monotonic() + seconds

    def caption(self, now: float | None = None) -> str:
        current = time.monotonic() if now is None else now
        if current > self.caption_until:
            return ""
        return self.caption_text

    def consume_action(self) -> str:
        action = self.pending_action
        self.pending_action = ""
        return action

    def status_label(self) -> str:
        labels = {
            "menu": "GAME HUB",
            "tic": "TIC TAC TOE",
            "pong": "PONG",
            "snake": "SNAKE",
        }
        return labels.get(self.mode, "GAME HUB")

    def open(self) -> None:
        self.active = True
        self.mode = "menu"
        self._say(
            "Game Hub: top-left Tic-Tac-Toe, top-right Pong, "
            "bottom-left Snake, bottom-right OLED show.",
            6.0,
        )

    def close(self) -> None:
        self.active = False
        self.mode = "menu"
        self._say("", 0.0)

    def _back_or_exit(self) -> None:
        if self.mode == "menu":
            self.close()
        else:
            self.mode = "menu"
            self._say(
                "Game Hub: choose another game.",
                3.0,
            )

    def _start_tic(self) -> None:
        self.mode = "tic"
        self.ttt_board = [""] * 9
        self.ttt_done = False
        self.ttt_result = ""
        self._say(
            "Tic-Tac-Toe. You are X. Tap a square.",
            4.0,
        )

    def _reset_pong_ball(self, toward_user: bool | None = None) -> None:
        self.pong_ball_x = 0.50
        self.pong_ball_y = 0.52

        direction = (
            random.choice([-1, 1])
            if toward_user is None
            else (1 if toward_user else -1)
        )

        self.pong_vx = random.choice([-1, 1]) * random.uniform(0.24, 0.35)
        self.pong_vy = direction * random.uniform(0.37, 0.48)

    def _start_pong(self) -> None:
        self.mode = "pong"
        self.pong_user_x = 0.50
        self.pong_buddy_x = 0.50
        self.pong_user_score = 0
        self.pong_buddy_score = 0
        self.pong_last = time.monotonic()
        self._reset_pong_ball()
        self._say(
            "Pong. Drag the lower paddle. First to five.",
            4.0,
        )

    def _new_food(self) -> None:
        occupied = set(self.snake)
        choices = [
            (x, y)
            for y in range(4, 22)
            for x in range(1, 15)
            if (x, y) not in occupied
        ]
        if choices:
            self.snake_food = random.choice(choices)

    def _start_snake(self) -> None:
        self.mode = "snake"
        self.snake = [
            (7, 13),
            (6, 13),
            (5, 13),
        ]
        self.snake_direction = (1, 0)
        self.snake_next_direction = (1, 0)
        self.snake_last_step = time.monotonic()
        self.snake_done = False
        self.snake_score = 0
        self._new_food()
        self._say(
            "Snake. Swipe up, down, left or right.",
            4.0,
        )

    def handle_touch(
        self,
        action: str,
        nx: float,
        ny: float,
    ) -> str | None:
        nx = clamp(nx, 0.0, 1.0)
        ny = clamp(ny, 0.0, 1.0)

        if action == "down":
            self.touch_down_x = nx
            self.touch_down_y = ny

            if self.mode == "pong":
                self.pong_user_x = nx

            return None

        if action == "move":
            if self.mode == "pong":
                self.pong_user_x = nx
            return None

        if action != "up":
            return None

        # Universal back / exit corner.
        if nx <= 0.16 and ny <= 0.11:
            self._back_or_exit()
            return None

        if self.mode == "menu":
            if ny < 0.53:
                if nx < 0.50:
                    self._start_tic()
                else:
                    self._start_pong()
            else:
                if nx < 0.50:
                    self._start_snake()
                else:
                    self._say(
                        "Playing your OLED animation.",
                        3.0,
                    )
                    self.pending_action = "oled_show"
                    return "oled_show"
            return None

        if self.mode == "tic":
            self._handle_tic_tap(nx, ny)
            return None

        if self.mode == "pong":
            self.pong_user_x = nx
            return None

        if self.mode == "snake":
            dx = nx - self.touch_down_x
            dy = ny - self.touch_down_y

            if abs(dx) < 0.035 and abs(dy) < 0.035:
                if self.snake_done:
                    self._start_snake()
                return None

            if abs(dx) > abs(dy):
                direction = (1, 0) if dx > 0 else (-1, 0)
            else:
                direction = (0, 1) if dy > 0 else (0, -1)

            current = self.snake_direction
            if (
                direction[0] != -current[0]
                or direction[1] != -current[1]
            ):
                self.snake_next_direction = direction

        return None

    @staticmethod
    def _ttt_winner(board: list[str]) -> str:
        lines = (
            (0, 1, 2),
            (3, 4, 5),
            (6, 7, 8),
            (0, 3, 6),
            (1, 4, 7),
            (2, 5, 8),
            (0, 4, 8),
            (2, 4, 6),
        )

        for a, b, c in lines:
            if board[a] and board[a] == board[b] == board[c]:
                return board[a]

        if all(board):
            return "draw"

        return ""

    def _ttt_score(self, board: list[str], buddy_turn: bool) -> int:
        winner = self._ttt_winner(board)

        if winner == "O":
            return 10
        if winner == "X":
            return -10
        if winner == "draw":
            return 0

        if buddy_turn:
            best = -99
            for index, value in enumerate(board):
                if value:
                    continue
                board[index] = "O"
                best = max(
                    best,
                    self._ttt_score(board, False),
                )
                board[index] = ""
            return best

        best = 99
        for index, value in enumerate(board):
            if value:
                continue
            board[index] = "X"
            best = min(
                best,
                self._ttt_score(board, True),
            )
            board[index] = ""
        return best

    def _buddy_tic_move(self) -> None:
        candidates: list[tuple[int, int]] = []

        for index, value in enumerate(self.ttt_board):
            if value:
                continue

            self.ttt_board[index] = "O"
            score = self._ttt_score(
                self.ttt_board,
                False,
            )
            self.ttt_board[index] = ""
            candidates.append((score, index))

        if not candidates:
            return

        best_score = max(score for score, _ in candidates)
        best_moves = [
            index
            for score, index in candidates
            if score == best_score
        ]
        self.ttt_board[random.choice(best_moves)] = "O"

    def _finish_tic_if_needed(self) -> bool:
        winner = self._ttt_winner(
            self.ttt_board,
        )

        if not winner:
            return False

        self.ttt_done = True
        self.ttt_result = winner

        if winner == "X":
            self._say(
                "You won. I will pretend this was intentional.",
                4.5,
            )
        elif winner == "O":
            self._say(
                "Desk Buddy wins. Tiny machine, enormous ego.",
                4.5,
            )
        else:
            self._say(
                "Draw. Humanity survives another round.",
                4.5,
            )

        return True

    def _handle_tic_tap(self, nx: float, ny: float) -> None:
        if self.ttt_done:
            self._start_tic()
            return

        left = 0.12
        right = 0.88
        top = 0.22
        bottom = 0.80

        if not (
            left <= nx <= right
            and top <= ny <= bottom
        ):
            return

        column = min(
            2,
            int(
                (nx - left)
                / ((right - left) / 3.0)
            ),
        )
        row = min(
            2,
            int(
                (ny - top)
                / ((bottom - top) / 3.0)
            ),
        )
        index = row * 3 + column

        if self.ttt_board[index]:
            return

        self.ttt_board[index] = "X"

        if self._finish_tic_if_needed():
            return

        self._buddy_tic_move()
        self._finish_tic_if_needed()

    def _update_pong(self, now: float) -> None:
        dt = clamp(
            now - self.pong_last,
            0.0,
            0.055,
        )
        self.pong_last = now

        # Buddy paddle is deliberately beatable. It tracks the ball but has a
        # finite maximum speed and a tiny center bias.
        target = (
            self.pong_ball_x * 0.94
            + 0.50 * 0.06
        )
        delta = target - self.pong_buddy_x
        max_step = 0.34 * dt
        self.pong_buddy_x += clamp(
            delta,
            -max_step,
            max_step,
        )
        self.pong_buddy_x = clamp(
            self.pong_buddy_x,
            0.13,
            0.87,
        )

        self.pong_user_x = clamp(
            self.pong_user_x,
            0.13,
            0.87,
        )

        self.pong_ball_x += self.pong_vx * dt
        self.pong_ball_y += self.pong_vy * dt

        if self.pong_ball_x <= 0.055:
            self.pong_ball_x = 0.055
            self.pong_vx = abs(self.pong_vx)

        elif self.pong_ball_x >= 0.945:
            self.pong_ball_x = 0.945
            self.pong_vx = -abs(self.pong_vx)

        paddle_half = 0.115

        # Buddy paddle, top.
        if (
            self.pong_vy < 0
            and 0.115 <= self.pong_ball_y <= 0.145
            and abs(
                self.pong_ball_x
                - self.pong_buddy_x
            )
            <= paddle_half + 0.035
        ):
            offset = (
                self.pong_ball_x
                - self.pong_buddy_x
            ) / paddle_half
            self.pong_vy = abs(self.pong_vy) * 1.015
            self.pong_vx += offset * 0.13
            self.pong_ball_y = 0.146

        # User paddle, bottom.
        if (
            self.pong_vy > 0
            and 0.855 <= self.pong_ball_y <= 0.895
            and abs(
                self.pong_ball_x
                - self.pong_user_x
            )
            <= paddle_half + 0.035
        ):
            offset = (
                self.pong_ball_x
                - self.pong_user_x
            ) / paddle_half
            self.pong_vy = -abs(self.pong_vy) * 1.015
            self.pong_vx += offset * 0.13
            self.pong_ball_y = 0.854

        self.pong_vx = clamp(
            self.pong_vx,
            -0.55,
            0.55,
        )
        self.pong_vy = clamp(
            self.pong_vy,
            -0.64,
            0.64,
        )

        if self.pong_ball_y < 0.02:
            self.pong_user_score += 1
            self._say(
                f"You score. {self.pong_user_score} to {self.pong_buddy_score}.",
                2.5,
            )
            self._reset_pong_ball(False)

        elif self.pong_ball_y > 0.98:
            self.pong_buddy_score += 1
            self._say(
                f"I score. {self.pong_buddy_score} to {self.pong_user_score}.",
                2.5,
            )
            self._reset_pong_ball(True)

        if (
            self.pong_user_score >= 5
            or self.pong_buddy_score >= 5
        ):
            if self.pong_user_score > self.pong_buddy_score:
                self._say(
                    "You win Pong. Annoyingly competent.",
                    4.0,
                )
            else:
                self._say(
                    "Desk Buddy wins Pong.",
                    4.0,
                )

            self.pong_user_score = 0
            self.pong_buddy_score = 0
            self._reset_pong_ball()

    def _update_snake(self, now: float) -> None:
        if self.snake_done:
            return

        if now - self.snake_last_step < 0.145:
            return

        self.snake_last_step = now
        self.snake_direction = self.snake_next_direction

        if not self.snake:
            return

        head_x, head_y = self.snake[0]
        dx, dy = self.snake_direction
        new_head = (
            head_x + dx,
            head_y + dy,
        )

        if (
            new_head[0] < 1
            or new_head[0] >= 15
            or new_head[1] < 4
            or new_head[1] >= 22
            or new_head in self.snake
        ):
            self.snake_done = True
            self._say(
                f"Snake over. Score {self.snake_score}. Tap to restart.",
                4.5,
            )
            return

        self.snake.insert(
            0,
            new_head,
        )

        if new_head == self.snake_food:
            self.snake_score += 1
            self._new_food()
        else:
            self.snake.pop()

    def update(self, now: float) -> None:
        if not self.active:
            return

        if self.mode == "pong":
            self._update_pong(now)

        elif self.mode == "snake":
            self._update_snake(now)

    def _background(self, canvas) -> None:
        canvas.clear()
        canvas.rect(
            0,
            0,
            canvas.width,
            canvas.height,
            BG,
        )

        # Subtle circuit grid, inspired by the hardware/PCB personality of a
        # desk robot without copying another project's artwork.
        step = max(
            24,
            canvas.width // 10,
        )
        grid = dim(CYAN, 0.045)

        for x in range(
            0,
            canvas.width,
            step,
        ):
            canvas.line(
                x,
                0,
                x,
                canvas.height,
                grid,
                1,
            )

        for y in range(
            0,
            canvas.height,
            step,
        ):
            canvas.line(
                0,
                y,
                canvas.width,
                y,
                grid,
                1,
            )

    def _draw_back(self, canvas) -> None:
        size = max(
            13,
            canvas.width // 18,
        )
        x = max(
            9,
            canvas.width // 30,
        )
        y = max(
            13,
            canvas.height // 38,
        )
        color = dim(CYAN, 0.70)

        canvas.line(
            x + size,
            y,
            x,
            y + size,
            color,
            2,
        )
        canvas.line(
            x,
            y + size,
            x + size,
            y + size * 2,
            color,
            2,
        )

    def _draw_menu_icon_tic(self, canvas, x, y, w, h) -> None:
        color = dim(CYAN, 0.70)
        left = x + w * 0.24
        top = y + h * 0.25
        size = min(
            w * 0.52,
            h * 0.52,
        )

        for i in (1, 2):
            xx = left + size * i / 3.0
            yy = top + size * i / 3.0
            canvas.line(
                xx,
                top,
                xx,
                top + size,
                color,
                2,
            )
            canvas.line(
                left,
                yy,
                left + size,
                yy,
                color,
                2,
            )

        # X and O marks.
        cell = size / 3.0
        canvas.line(
            left + cell * 0.18,
            top + cell * 0.18,
            left + cell * 0.82,
            top + cell * 0.82,
            WHITE,
            2,
        )
        canvas.line(
            left + cell * 0.82,
            top + cell * 0.18,
            left + cell * 0.18,
            top + cell * 0.82,
            WHITE,
            2,
        )
        canvas.circle(
            left + cell * 2.50,
            top + cell * 1.50,
            cell * 0.27,
            MAGENTA,
        )
        canvas.circle(
            left + cell * 2.50,
            top + cell * 1.50,
            cell * 0.18,
            PANEL,
        )

    def _draw_menu_icon_pong(self, canvas, x, y, w, h) -> None:
        color = dim(CYAN, 0.65)
        left = x + w * 0.24
        right = x + w * 0.76
        top = y + h * 0.25
        bottom = y + h * 0.75

        canvas.rounded_rect(
            left - 4,
            top,
            8,
            h * 0.26,
            3,
            color,
        )
        canvas.rounded_rect(
            right - 4,
            bottom - h * 0.26,
            8,
            h * 0.26,
            3,
            color,
        )
        canvas.circle(
            x + w * 0.53,
            y + h * 0.50,
            max(5, w * 0.045),
            WHITE,
        )

    def _draw_menu_icon_snake(self, canvas, x, y, w, h) -> None:
        cell = min(
            w,
            h,
        ) * 0.10
        points = [
            (0.28, 0.58),
            (0.38, 0.58),
            (0.48, 0.58),
            (0.58, 0.58),
            (0.58, 0.48),
            (0.58, 0.38),
            (0.68, 0.38),
        ]

        for index, (px, py) in enumerate(points):
            canvas.rounded_rect(
                x + w * px - cell / 2,
                y + h * py - cell / 2,
                cell,
                cell,
                cell * 0.25,
                CYAN if index == 0 else dim(CYAN, 0.48),
            )

        canvas.circle(
            x + w * 0.76,
            y + h * 0.30,
            cell * 0.42,
            YELLOW,
        )

    def _draw_menu_icon_show(self, canvas, x, y, w, h) -> None:
        cx = x + w * 0.50
        cy = y + h * 0.50
        radius = min(w, h) * 0.24

        canvas.circle(
            cx,
            cy,
            radius,
            dim(CYAN, 0.22),
        )
        canvas.polygon(
            [
                (
                    cx - radius * 0.30,
                    cy - radius * 0.48,
                ),
                (
                    cx - radius * 0.30,
                    cy + radius * 0.48,
                ),
                (
                    cx + radius * 0.58,
                    cy,
                ),
            ],
            WHITE,
        )

    def _draw_menu(self, canvas) -> None:
        self._background(canvas)
        self._draw_back(canvas)

        margin_x = canvas.width * 0.08
        top = canvas.height * 0.15
        bottom = canvas.height * 0.88
        gap = max(
            9,
            canvas.width * 0.035,
        )

        card_w = (
            canvas.width
            - margin_x * 2
            - gap
        ) / 2.0
        card_h = (
            bottom
            - top
            - gap
        ) / 2.0

        cards = [
            (
                margin_x,
                top,
                self._draw_menu_icon_tic,
            ),
            (
                margin_x + card_w + gap,
                top,
                self._draw_menu_icon_pong,
            ),
            (
                margin_x,
                top + card_h + gap,
                self._draw_menu_icon_snake,
            ),
            (
                margin_x + card_w + gap,
                top + card_h + gap,
                self._draw_menu_icon_show,
            ),
        ]

        for index, (x, y, icon) in enumerate(cards):
            canvas.rounded_rect(
                x,
                y,
                card_w,
                card_h,
                max(
                    10,
                    canvas.width * 0.035,
                ),
                PANEL,
            )
            canvas.rounded_rect(
                x + 2,
                y + 2,
                card_w - 4,
                card_h - 4,
                max(
                    8,
                    canvas.width * 0.030,
                ),
                dim(
                    CYAN if index < 3 else MAGENTA,
                    0.08,
                ),
            )
            icon(
                canvas,
                x,
                y,
                card_w,
                card_h,
            )

    def _draw_tic(self, canvas) -> None:
        self._background(canvas)
        self._draw_back(canvas)

        left = canvas.width * 0.12
        right = canvas.width * 0.88
        top = canvas.height * 0.22
        bottom = canvas.height * 0.80
        board_w = right - left
        board_h = bottom - top
        cell_w = board_w / 3.0
        cell_h = board_h / 3.0

        line_color = dim(CYAN, 0.55)

        for i in (1, 2):
            canvas.line(
                left + cell_w * i,
                top,
                left + cell_w * i,
                bottom,
                line_color,
                3,
            )
            canvas.line(
                left,
                top + cell_h * i,
                right,
                top + cell_h * i,
                line_color,
                3,
            )

        for index, mark in enumerate(self.ttt_board):
            if not mark:
                continue

            row = index // 3
            column = index % 3
            cx = left + cell_w * (
                column + 0.5
            )
            cy = top + cell_h * (
                row + 0.5
            )
            radius = min(
                cell_w,
                cell_h,
            ) * 0.24

            if mark == "X":
                canvas.line(
                    cx - radius,
                    cy - radius,
                    cx + radius,
                    cy + radius,
                    WHITE,
                    4,
                )
                canvas.line(
                    cx + radius,
                    cy - radius,
                    cx - radius,
                    cy + radius,
                    WHITE,
                    4,
                )

            else:
                canvas.circle(
                    cx,
                    cy,
                    radius,
                    MAGENTA,
                )
                canvas.circle(
                    cx,
                    cy,
                    max(
                        1,
                        radius - 5,
                    ),
                    BG,
                )

    def _draw_pong(self, canvas) -> None:
        self._background(canvas)
        self._draw_back(canvas)

        for index in range(12):
            y = canvas.height * (
                0.12
                + index * 0.07
            )
            canvas.rect(
                canvas.width * 0.495,
                y,
                max(
                    2,
                    canvas.width * 0.01,
                ),
                max(
                    5,
                    canvas.height * 0.025,
                ),
                dim(CYAN, 0.18),
            )

        paddle_w = canvas.width * 0.23
        paddle_h = max(
            7,
            canvas.height * 0.012,
        )

        canvas.rounded_rect(
            canvas.width * self.pong_buddy_x
            - paddle_w / 2,
            canvas.height * 0.115,
            paddle_w,
            paddle_h,
            paddle_h / 2,
            MAGENTA,
        )
        canvas.rounded_rect(
            canvas.width * self.pong_user_x
            - paddle_w / 2,
            canvas.height * 0.875,
            paddle_w,
            paddle_h,
            paddle_h / 2,
            CYAN,
        )

        canvas.circle(
            canvas.width * self.pong_ball_x,
            canvas.height * self.pong_ball_y,
            max(
                5,
                canvas.width * 0.022,
            ),
            WHITE,
        )

        # Scores as tiny dots. Five dots fit cleanly without needing a font.
        for index in range(5):
            color = (
                MAGENTA
                if index < self.pong_buddy_score
                else dim(MAGENTA, 0.12)
            )
            canvas.circle(
                canvas.width * (
                    0.33
                    + index * 0.042
                ),
                canvas.height * 0.055,
                4,
                color,
            )

            color = (
                CYAN
                if index < self.pong_user_score
                else dim(CYAN, 0.12)
            )
            canvas.circle(
                canvas.width * (
                    0.33
                    + index * 0.042
                ),
                canvas.height * 0.945,
                4,
                color,
            )

    def _draw_snake(self, canvas) -> None:
        self._background(canvas)
        self._draw_back(canvas)

        cols = 16
        rows = 24
        cell_w = canvas.width / cols
        cell_h = canvas.height / rows

        for x, y in self.snake:
            color = (
                WHITE
                if (x, y) == self.snake[0]
                else CYAN
            )
            canvas.rounded_rect(
                x * cell_w + 2,
                y * cell_h + 2,
                max(
                    2,
                    cell_w - 4,
                ),
                max(
                    2,
                    cell_h - 4,
                ),
                3,
                color,
            )

        food_x, food_y = self.snake_food
        canvas.circle(
            (food_x + 0.5) * cell_w,
            (food_y + 0.5) * cell_h,
            min(
                cell_w,
                cell_h,
            ) * 0.30,
            YELLOW,
        )

        for index in range(
            min(
                10,
                self.snake_score,
            )
        ):
            canvas.circle(
                canvas.width * (
                    0.56
                    + index * 0.028
                ),
                canvas.height * 0.055,
                3,
                GREEN,
            )

        if self.snake_done:
            # Central pulse icon, caption carries the human-readable result.
            cx = canvas.width * 0.50
            cy = canvas.height * 0.50
            r = canvas.width * 0.10
            canvas.circle(
                cx,
                cy,
                r,
                dim(RED, 0.22),
            )
            canvas.line(
                cx - r * 0.45,
                cy - r * 0.45,
                cx + r * 0.45,
                cy + r * 0.45,
                RED,
                4,
            )
            canvas.line(
                cx + r * 0.45,
                cy - r * 0.45,
                cx - r * 0.45,
                cy + r * 0.45,
                RED,
                4,
            )

    def draw(self, canvas, now: float) -> None:
        if not self.active:
            return

        self.update(now)

        if self.mode == "menu":
            self._draw_menu(canvas)
        elif self.mode == "tic":
            self._draw_tic(canvas)
        elif self.mode == "pong":
            self._draw_pong(canvas)
        elif self.mode == "snake":
            self._draw_snake(canvas)



def run_self_test() -> None:
    """Deterministic smoke test for the non-rendering game logic."""

    # Tic-Tac-Toe: Buddy must block an immediate X win.
    hub = GameHub()
    hub.ttt_board = [
        "X", "X", "",
        "O", "", "",
        "", "O", "",
    ]
    hub._buddy_tic_move()
    assert hub.ttt_board[2] == "O", "Tic-Tac-Toe AI failed to block"

    # Menu: bottom-right tile must emit the OLED action.
    hub = GameHub()
    hub.open()
    hub.handle_touch("down", 0.75, 0.75)
    hub.handle_touch("up", 0.75, 0.75)
    assert hub.consume_action() == "oled_show", "OLED menu action failed"

    # Pong: several seconds of simulation must stay inside numeric bounds.
    hub = GameHub()
    hub._start_pong()
    now = hub.pong_last
    for _ in range(240):
        now += 1.0 / 30.0
        hub.pong_user_x = hub.pong_ball_x
        hub._update_pong(now)
        assert 0.0 <= hub.pong_ball_x <= 1.0, "Pong ball escaped X bounds"
        assert -0.56 <= hub.pong_vx <= 0.56, "Pong X velocity invalid"
        assert -0.65 <= hub.pong_vy <= 0.65, "Pong Y velocity invalid"

    # Snake: food directly ahead must grow the snake and increase score.
    hub = GameHub()
    hub._start_snake()
    head_x, head_y = hub.snake[0]
    hub.snake_food = (head_x + 1, head_y)
    hub.snake_last_step = 0.0
    hub._update_snake(10.0)
    assert hub.snake_score == 1, "Snake did not score on food"
    assert len(hub.snake) == 4, "Snake did not grow"

    print("Game Hub self-test: PASS")


if __name__ == "__main__":
    import sys

    if "--self-test" in sys.argv:
        run_self_test()
