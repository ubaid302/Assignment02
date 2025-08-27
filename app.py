#!/usr/bin/env python3
from __future__ import annotations

import os
import random
from typing import Any, Dict, Optional, Tuple

from flask import Flask, jsonify, render_template, request, session

from candy_game import Board, CandySet


app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key")


# In-memory RNG store keyed by a per-session id to ensure refill randomness persists across requests
_RNGS: Dict[str, random.Random] = {}


def _get_or_create_session_id() -> str:
    sid = session.get("_sid")
    if not sid:
        sid = os.urandom(16).hex()
        session["_sid"] = sid
    return sid


def _get_rng(seed: Optional[int] = None) -> random.Random:
    sid = _get_or_create_session_id()
    if sid not in _RNGS:
        _RNGS[sid] = random.Random(seed)
    return _RNGS[sid]


def _serialize_state(board: Board, score: int, remaining_moves: int, emoji: bool, types: int) -> Dict[str, Any]:
    return {
        "rows": board.rows,
        "cols": board.cols,
        "grid": board.grid,
        "score": score,
        "remaining_moves": remaining_moves,
        "emoji": emoji,
        "types": types,
    }


def _ensure_game_state() -> Optional[Dict[str, Any]]:
    state = session.get("game_state")
    return state


def _build_board_from_state(state: Dict[str, Any]) -> Tuple[Board, CandySet, random.Random]:
    rows = int(state["rows"])  # type: ignore[call-arg]
    cols = int(state["cols"])  # type: ignore[call-arg]
    types_count = int(state.get("types", 6))
    emoji = bool(state.get("emoji", True))
    rng = _get_rng()
    candy_set = CandySet(num_types=types_count, use_emoji=emoji, ansi=None)  # type: ignore[arg-type]
    # CandySet expects an Ansi, but it only uses ansi for rendering. Provide a dummy with same API.
    # We pass None and avoid calling render in server-side logic.
    board = Board(rows=rows, cols=cols, candy_set=candy_set, rng=rng)
    # Overwrite generated grid with saved grid
    saved_grid = state.get("grid")
    if saved_grid:
        board.grid = [[cell for cell in row] for row in saved_grid]
    return board, candy_set, rng


@app.route("/")
def index() -> Any:
    return render_template("index.html")


@app.post("/api/new")
def api_new() -> Any:
    data = request.get_json(silent=True) or {}
    rows = int(data.get("rows", 8))
    cols = int(data.get("cols", 8))
    types_count = int(data.get("types", 6))
    moves = int(data.get("moves", 25))
    seed = data.get("seed")
    emoji = bool(data.get("emoji", True))

    rng = _get_rng(seed)
    # Provide a dummy ansi for CandySet; render is only used by CLI
    class _DummyAnsi:
        def __init__(self) -> None:
            pass
        def fg(self, *_: Any, **__: Any) -> str:
            return ""
        def color(self, *_: Any, **__: Any) -> str:
            return ""
        def bold(self, text: str) -> str:
            return text
        def dim(self, text: str) -> str:
            return text

    candy_set = CandySet(num_types=types_count, use_emoji=emoji, ansi=_DummyAnsi())
    board = Board(rows=rows, cols=cols, candy_set=candy_set, rng=rng)
    if not board.has_any_valid_move():
        board.shuffle()

    state = _serialize_state(board, score=0, remaining_moves=moves, emoji=emoji, types=types_count)
    session["game_state"] = state
    return jsonify({"ok": True, "state": state})


@app.get("/api/state")
def api_state() -> Any:
    state = _ensure_game_state()
    if not state:
        return jsonify({"ok": False, "error": "no_state"}), 404
    return jsonify({"ok": True, "state": state})


@app.post("/api/swap")
def api_swap() -> Any:
    state = _ensure_game_state()
    if not state:
        return jsonify({"ok": False, "error": "no_state"}), 404
    data = request.get_json(silent=True) or {}
    try:
        r1 = int(data["r1"])  # type: ignore[index]
        c1 = int(data["c1"])  # type: ignore[index]
        r2 = int(data["r2"])  # type: ignore[index]
        c2 = int(data["c2"])  # type: ignore[index]
    except Exception:
        return jsonify({"ok": False, "error": "bad_args"}), 400

    board, candy_set, rng = _build_board_from_state(state)
    if state["remaining_moves"] <= 0:
        return jsonify({"ok": False, "error": "no_moves", "state": state}), 400

    performed, gained, chains = board.try_swap_and_resolve((r1, c1), (r2, c2))
    if not performed:
        return jsonify({"ok": False, "error": "invalid_swap", "state": state})

    state["remaining_moves"] = int(state["remaining_moves"]) - 1
    state["score"] = int(state["score"]) + int(gained)
    state["grid"] = board.grid

    shuffled = False
    if not board.has_any_valid_move():
        if board.shuffle():
            shuffled = True
            state["grid"] = board.grid

    session["game_state"] = state
    return jsonify({
        "ok": True,
        "state": state,
        "gained": gained,
        "chains": chains,
        "shuffled": shuffled,
    })


@app.get("/api/hint")
def api_hint() -> Any:
    state = _ensure_game_state()
    if not state:
        return jsonify({"ok": False, "error": "no_state"}), 404
    board, _, _ = _build_board_from_state(state)
    hint = board.find_any_valid_move()
    if not hint:
        return jsonify({"ok": True, "hint": None})
    (r1, c1), (r2, c2) = hint
    return jsonify({"ok": True, "hint": {"r1": r1, "c1": c1, "r2": r2, "c2": c2}})


@app.post("/api/shuffle")
def api_shuffle() -> Any:
    state = _ensure_game_state()
    if not state:
        return jsonify({"ok": False, "error": "no_state"}), 404
    if state["remaining_moves"] <= 0:
        return jsonify({"ok": False, "error": "no_moves", "state": state}), 400
    board, _, _ = _build_board_from_state(state)
    if board.shuffle():
        state["remaining_moves"] = int(state["remaining_moves"]) - 1
        state["grid"] = board.grid
        session["game_state"] = state
        return jsonify({"ok": True, "state": state})
    return jsonify({"ok": False, "error": "shuffle_failed"}), 400


def main() -> int:
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

