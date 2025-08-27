#!/usr/bin/env python3
"""
CLI Match-3 Candy Game

Features:
- Board generation with no initial matches
- Swap adjacent candies; only valid if it creates a match
- Match detection (horizontal/vertical 3+)
- Clearing, gravity drop, and refill with cascades
- Scoring with chain multipliers and match-length bonuses
- Move counter and game-over detection
- Hints (find a valid move) and shuffle when stuck
- Configurable via CLI args: rows, cols, candy types, moves, seed, colors

Usage examples:
  python candy_game.py --rows 8 --cols 8 --moves 25 --seed 42
  python candy_game.py -r 7 -c 7 -m 20 --colors

Controls during the game:
  swap r1 c1 r2 c2   Perform a swap if valid (0-indexed)
  h | hint           Show a hint (one valid move)
  s | shuffle        Shuffle the board (costs 1 move)
  q | quit           Quit the game early

Note: Coordinates are 0-indexed. Example: swap 2 3 2 4
"""

from __future__ import annotations

import argparse
import random
import sys
from typing import Iterable, List, Optional, Sequence, Tuple


class Ansi:
    """Minimal ANSI color helper. Toggle via enable flag."""

    def __init__(self, enable: bool) -> None:
        self.enable = enable

    def color(self, code: str, text: str) -> str:
        if not self.enable:
            return text
        return f"\033[{code}m{text}\033[0m"

    def bold(self, text: str) -> str:
        return self.color("1", text)

    def dim(self, text: str) -> str:
        return self.color("2", text)

    def fg(self, color_code: int, text: str) -> str:
        return self.color(str(30 + color_code), text)


class CandySet:
    """Represents available candy symbols and their colored renderings."""

    DEFAULT_EMOJIS = [
        "🍒", "🍋", "🍇", "🍏", "🍬", "🍪", "🍫",
    ]

    DEFAULT_ASCII = [
        "A", "B", "C", "D", "E", "F", "G",
    ]

    def __init__(self, num_types: int, use_emoji: bool, ansi: Ansi) -> None:
        base = self.DEFAULT_EMOJIS if use_emoji else self.DEFAULT_ASCII
        if num_types < 3:
            raise ValueError("At least 3 candy types required")
        if num_types > len(base):
            raise ValueError(f"Max candy types is {len(base)} for the selected set")
        self.symbols: List[str] = base[:num_types]
        self.ansi = ansi

    def render(self, symbol: str) -> str:
        # Map to distinct colors for readability (wrap if needed)
        palette = [1, 2, 3, 4, 5, 6, 7]  # red..white (basic 8-color minus black)
        idx = self.symbols.index(symbol)
        color_code = palette[idx % len(palette)]
        return self.ansi.fg(color_code, symbol)


Coordinate = Tuple[int, int]


class Board:
    """Game board with swap, match detection, clearing, gravity, and refill."""

    def __init__(self, rows: int, cols: int, candy_set: CandySet, rng: random.Random) -> None:
        if rows < 3 or cols < 3:
            raise ValueError("Board must be at least 3x3")
        self.rows = rows
        self.cols = cols
        self.candy_set = candy_set
        self.rng = rng
        self.grid: List[List[str]] = [["" for _ in range(cols)] for _ in range(rows)]
        self._generate_without_initial_matches()

    def _random_candy(self) -> str:
        return self.rng.choice(self.candy_set.symbols)

    def _generate_without_initial_matches(self) -> None:
        for r in range(self.rows):
            for c in range(self.cols):
                while True:
                    self.grid[r][c] = self._random_candy()
                    if not self._creates_immediate_match(r, c):
                        break

    def _creates_immediate_match(self, r: int, c: int) -> bool:
        symbol = self.grid[r][c]
        # Check left two
        if c >= 2 and self.grid[r][c - 1] == symbol and self.grid[r][c - 2] == symbol:
            return True
        # Check up two
        if r >= 2 and self.grid[r - 1][c] == symbol and self.grid[r - 2][c] == symbol:
            return True
        return False

    def in_bounds(self, r: int, c: int) -> bool:
        return 0 <= r < self.rows and 0 <= c < self.cols

    def _adjacent(self, a: Coordinate, b: Coordinate) -> bool:
        (r1, c1), (r2, c2) = a, b
        return abs(r1 - r2) + abs(c1 - c2) == 1

    def render(self) -> str:
        lines: List[str] = []
        header = "   " + " ".join(f"{c:2d}" for c in range(self.cols))
        lines.append(header)
        for r in range(self.rows):
            row_symbols = [self.candy_set.render(self.grid[r][c]) for c in range(self.cols)]
            lines.append(f"{r:2d} " + " ".join(f"{s:2s}" for s in row_symbols))
        return "\n".join(lines)

    def find_matches(self) -> List[List[Coordinate]]:
        """Return a list of match groups (each a list of coordinates)."""
        matches: List[List[Coordinate]] = []

        # Horizontal matches
        for r in range(self.rows):
            c = 0
            while c < self.cols:
                start = c
                while c + 1 < self.cols and self.grid[r][c + 1] == self.grid[r][start]:
                    c += 1
                length = c - start + 1
                if length >= 3 and self.grid[r][start] != "":
                    matches.append([(r, cc) for cc in range(start, c + 1)])
                c += 1

        # Vertical matches
        for c in range(self.cols):
            r = 0
            while r < self.rows:
                start = r
                while r + 1 < self.rows and self.grid[r + 1][c] == self.grid[start][c]:
                    r += 1
                length = r - start + 1
                if length >= 3 and self.grid[start][c] != "":
                    matches.append([(rr, c) for rr in range(start, r + 1)])
                r += 1

        # Merge overlapping groups into unique sets
        unique: List[List[Coordinate]] = []
        seen: set[Coordinate] = set()
        for group in matches:
            new_group: List[Coordinate] = []
            for coord in group:
                if coord not in seen:
                    seen.add(coord)
                    new_group.append(coord)
            if new_group:
                unique.append(new_group)
        return unique

    def has_any_valid_move(self) -> bool:
        return self.find_any_valid_move() is not None

    def find_any_valid_move(self) -> Optional[Tuple[Coordinate, Coordinate]]:
        """Find any adjacent swap that yields a match."""
        for r in range(self.rows):
            for c in range(self.cols):
                here = (r, c)
                for dr, dc in [(0, 1), (1, 0)]:
                    nr, nc = r + dr, c + dc
                    if not self.in_bounds(nr, nc):
                        continue
                    there = (nr, nc)
                    if self._swap_creates_match(here, there):
                        return here, there
        return None

    def _swap_creates_match(self, a: Coordinate, b: Coordinate) -> bool:
        if not self._adjacent(a, b):
            return False
        (r1, c1), (r2, c2) = a, b
        self.grid[r1][c1], self.grid[r2][c2] = self.grid[r2][c2], self.grid[r1][c1]
        created = bool(self.find_matches())
        self.grid[r1][c1], self.grid[r2][c2] = self.grid[r2][c2], self.grid[r1][c1]
        return created

    def try_swap_and_resolve(self, a: Coordinate, b: Coordinate) -> Tuple[bool, int, int]:
        """Attempt the swap.

        Returns (performed, score_gained, chains_triggered).
        If swap is invalid (no match), returns (False, 0, 0).
        """
        if not self._adjacent(a, b):
            return False, 0, 0
        if not self._swap_creates_match(a, b):
            return False, 0, 0

        (r1, c1), (r2, c2) = a, b
        self.grid[r1][c1], self.grid[r2][c2] = self.grid[r2][c2], self.grid[r1][c1]

        total_score = 0
        chains = 0
        while True:
            groups = self.find_matches()
            if not groups:
                break
            chains += 1
            gained = self._clear_groups_and_score(groups, chain_index=chains)
            total_score += gained
            self._apply_gravity()
            self._refill()

        return True, total_score, chains

    def _clear_groups_and_score(self, groups: List[List[Coordinate]], chain_index: int) -> int:
        """Clear matched groups and compute score with chain multiplier.

        Scoring rules:
        - Base points per candy: 10
        - Bonus per extra beyond 3 in a group: +5 each
        - Chain multiplier: x(chain_index)
        """
        base_per_candy = 10
        bonus_per_extra = 5
        cells_to_clear: set[Coordinate] = set()
        score = 0
        for group in groups:
            length = len(group)
            group_score = base_per_candy * length + max(0, length - 3) * bonus_per_extra
            score += group_score
            for cell in group:
                cells_to_clear.add(cell)

        for (r, c) in cells_to_clear:
            self.grid[r][c] = ""

        return score * chain_index

    def _apply_gravity(self) -> None:
        for c in range(self.cols):
            write_row = self.rows - 1
            for r in range(self.rows - 1, -1, -1):
                if self.grid[r][c] != "":
                    self.grid[write_row][c] = self.grid[r][c]
                    if write_row != r:
                        self.grid[r][c] = ""
                    write_row -= 1
            for r in range(write_row, -1, -1):
                self.grid[r][c] = ""

    def _refill(self) -> None:
        for r in range(self.rows):
            for c in range(self.cols):
                if self.grid[r][c] == "":
                    self.grid[r][c] = self._random_candy()

    def shuffle(self, max_attempts: int = 100) -> bool:
        """Shuffle the board while preserving candy counts; ensure a valid move exists."""
        flat: List[str] = [self.grid[r][c] for r in range(self.rows) for c in range(self.cols)]
        for _ in range(max_attempts):
            self.rng.shuffle(flat)
            idx = 0
            for r in range(self.rows):
                for c in range(self.cols):
                    self.grid[r][c] = flat[idx]
                    idx += 1
            # Avoid immediate matches blow-up; shuffling can create matches, which is fine.
            if self.has_any_valid_move():
                return True
        return False


class Game:
    """High-level game loop and state."""

    def __init__(
        self,
        rows: int,
        cols: int,
        num_types: int,
        moves: int,
        seed: Optional[int],
        use_colors: bool,
        use_emoji: bool,
    ) -> None:
        self.ansi = Ansi(enable=use_colors)
        self.rng = random.Random(seed)
        self.candy_set = CandySet(num_types=num_types, use_emoji=use_emoji, ansi=self.ansi)
        self.board = Board(rows=rows, cols=cols, candy_set=self.candy_set, rng=self.rng)
        self.remaining_moves = moves
        self.score = 0

    def print_header(self) -> None:
        print(self.ansi.bold("Match-3 Candy Game"))
        print(f"Moves: {self.remaining_moves}    Score: {self.score}")
        print(self.board.render())

    def prompt(self) -> None:
        print()
        print("Commands:")
        print("  swap r1 c1 r2 c2   perform a swap (0-indexed)")
        print("  h | hint           show a hint")
        print("  s | shuffle        shuffle the board (costs 1 move)")
        print("  q | quit           quit the game")

    def run(self) -> None:
        while self.remaining_moves > 0:
            if not self.board.has_any_valid_move():
                print(self.ansi.bold("No available moves. Shuffling... (costs no move)"))
                if not self.board.shuffle():
                    print("Unable to generate a valid shuffle. Ending game.")
                    break
            self.print_header()
            self.prompt()
            try:
                line = input(self.ansi.dim("> "))
            except EOFError:
                print()
                break
            line = line.strip()
            if not line:
                continue
            if line.lower() in {"q", "quit"}:
                print("Goodbye!")
                return
            if line.lower() in {"h", "hint"}:
                hint = self.board.find_any_valid_move()
                if hint is None:
                    print("No valid moves found.")
                else:
                    (r1, c1), (r2, c2) = hint
                    print(f"Hint: swap ({r1},{c1}) <-> ({r2},{c2})")
                continue
            if line.lower() in {"s", "shuffle"}:
                if self.remaining_moves <= 0:
                    print("No moves left to shuffle.")
                    continue
                if self.board.shuffle():
                    self.remaining_moves -= 1
                    print("Shuffled the board.")
                else:
                    print("Shuffle failed to produce valid moves. Try again.")
                continue

            if line.lower().startswith("swap "):
                parts = line.split()
                if len(parts) != 5:
                    print("Usage: swap r1 c1 r2 c2")
                    continue
                try:
                    r1, c1, r2, c2 = map(int, parts[1:])
                except ValueError:
                    print("Coordinates must be integers.")
                    continue
                if not (self.board.in_bounds(r1, c1) and self.board.in_bounds(r2, c2)):
                    print("Coordinates out of bounds.")
                    continue
                performed, gained, chains = self.board.try_swap_and_resolve((r1, c1), (r2, c2))
                if performed:
                    self.remaining_moves -= 1
                    self.score += gained
                    print(f"Valid swap. Chains: {chains}, Gained: {gained}, Total: {self.score}")
                else:
                    print("Invalid swap (no match). Try a different pair.")
                continue

            print("Unrecognized command. Try 'swap', 'hint', 'shuffle', or 'quit'.")

        print()
        print(self.ansi.bold("Game Over"))
        print(f"Final Score: {self.score}")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CLI Match-3 Candy Game")
    parser.add_argument("--rows", "-r", type=int, default=8, help="Number of rows (>=3)")
    parser.add_argument("--cols", "-c", type=int, default=8, help="Number of cols (>=3)")
    parser.add_argument("--types", "-t", type=int, default=6, help="Number of candy types (3-7)")
    parser.add_argument("--moves", "-m", type=int, default=25, help="Number of moves")
    parser.add_argument("--seed", "-s", type=int, default=None, help="Random seed")
    parser.add_argument("--colors", dest="colors", action="store_true", help="Enable ANSI colors")
    parser.add_argument("--no-colors", dest="colors", action="store_false", help="Disable ANSI colors")
    parser.set_defaults(colors=True)
    parser.add_argument("--emoji", dest="emoji", action="store_true", help="Use emoji candies")
    parser.add_argument("--ascii", dest="emoji", action="store_false", help="Use ASCII candies")
    parser.set_defaults(emoji=True)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        game = Game(
            rows=args.rows,
            cols=args.cols,
            num_types=args.types,
            moves=args.moves,
            seed=args.seed,
            use_colors=args.colors,
            use_emoji=args.emoji,
        )
    except Exception as exc:  # Guard against invalid arguments
        print(f"Error: {exc}")
        return 2
    game.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

