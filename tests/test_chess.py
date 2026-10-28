"""Chess rules (verified with perft), notation, draw rules and the engine."""

from __future__ import annotations

import pytest

from apps.chess.logic import (
    PST,
    START_FEN,
    Move,
    Position,
    SearchStats,
    best_move,
    evaluate,
    square,
)
from core.base_app import AppContext


def perft(pos: Position, depth: int) -> int:
    if depth == 0:
        return 1
    total = 0
    for move in pos.legal_moves():
        pos.push(move)
        total += perft(pos, depth - 1)
        pos.pop()
    return total


# Reference node counts from the Chess Programming Wiki "Perft Results" page.
@pytest.mark.parametrize(
    ("fen", "depth", "nodes"),
    [
        (START_FEN, 1, 20),
        (START_FEN, 2, 400),
        (START_FEN, 3, 8902),
        ("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1", 1, 48),
        ("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1", 2, 2039),
        ("8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1", 3, 2812),
        ("r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1", 2, 264),
        ("rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8", 2, 1486),
    ],
    ids=["start-1", "start-2", "start-3", "kiwipete-1", "kiwipete-2", "pos3", "pos4", "pos5"],
)
def test_perft(fen: str, depth: int, nodes: int) -> None:
    pos = Position.from_fen(fen)
    before = pos.fen()
    assert perft(pos, depth) == nodes
    assert pos.fen() == before  # push/pop restored everything


def play(pos: Position, *ucis: str) -> Position:
    for u in ucis:
        move = Move.from_uci(u)
        assert move in pos.legal_moves(), u
        pos.push(move)
    return pos


def test_fen_round_trip() -> None:
    fen = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"
    assert Position.from_fen(fen).fen() == fen


def test_castling_moves_the_rook_and_clears_rights() -> None:
    pos = Position.from_fen("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    pos.push(Move.from_uci("e1g1"))
    assert pos.board[square("f1")] == "R" and pos.board[square("h1")] == "."
    assert pos.castling == "kq"
    pos.push(Move.from_uci("e8c8"))
    assert pos.board[square("d8")] == "r" and pos.castling == ""
    pos.pop()
    pos.pop()
    assert pos.fen() == "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"


def test_cannot_castle_through_check() -> None:
    pos = Position.from_fen("4k3/8/8/8/8/8/5r2/R3K2R w KQ - 0 1")
    ucis = {m.uci for m in pos.legal_moves()}
    assert "e1g1" not in ucis  # f1 is attacked
    assert "e1c1" in ucis


def test_en_passant() -> None:
    pos = play(Position.from_fen(), "e2e4", "a7a6", "e4e5", "d7d5")
    assert pos.ep == square("d6")
    pos.push(Move.from_uci("e5d6"))
    assert pos.board[square("d5")] == "." and pos.board[square("d6")] == "P"
    pos.pop()
    assert pos.board[square("d5")] == "p"


def test_promotion_choices() -> None:
    pos = Position.from_fen("8/P7/8/8/8/8/8/k6K w - - 0 1")
    promos = sorted(m.promotion for m in pos.legal_moves() if m.start == square("a7"))
    assert promos == ["b", "n", "q", "r"]
    pos.push(Move.from_uci("a7a8n"))
    assert pos.board[square("a8")] == "N"


def test_checkmate_and_stalemate() -> None:
    mate = play(Position.from_fen(), "f2f3", "e7e5", "g2g4", "d8h4")
    assert mate.outcome() == ("checkmate", "b")
    stalemate = Position.from_fen("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
    assert stalemate.outcome() == ("stalemate", None)


@pytest.mark.parametrize(
    ("fen", "draw"),
    [
        ("8/8/4k3/8/8/4K3/8/8 w - - 0 1", True),
        ("8/8/4k3/8/8/4KB2/8/8 w - - 0 1", True),
        ("8/8/4k3/8/8/4KN2/8/8 w - - 0 1", True),
        ("8/8/3bk3/8/8/4KB2/8/8 w - - 0 1", False),  # bishops on different colours
        ("8/8/4k1b1/8/8/4KB2/8/8 w - - 0 1", True),  # same colour
        ("8/8/4k3/8/8/4KR2/8/8 w - - 0 1", False),
    ],
)
def test_insufficient_material(fen: str, draw: bool) -> None:
    assert Position.from_fen(fen).insufficient_material() is draw


def test_fifty_moves_and_repetition() -> None:
    assert Position.from_fen("8/8/4k3/8/8/4KR2/8/8 w - - 100 80").outcome() == (
        "fifty-move rule",
        None,
    )
    pos = Position.from_fen()
    for _ in range(2):
        play(pos, "g1f3", "g8f6", "f3g1", "f6g8")
    assert pos.outcome() == ("threefold repetition", None)


@pytest.mark.parametrize(
    ("fen", "uci", "san"),
    [
        (START_FEN, "g1f3", "Nf3"),
        (START_FEN, "e2e4", "e4"),
        ("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", "e1g1", "O-O"),
        ("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", "e1c1", "O-O-O"),
        ("4k3/8/8/8/8/8/8/R4RK1 w - - 0 1", "a1d1", "Rad1"),  # file disambiguation
        ("4k3/R7/8/8/8/8/8/R3K3 w Q - 0 1", "a1a4", "R1a4"),  # rank disambiguation
        ("7k/P7/8/8/8/8/8/K7 w - - 0 1", "a7a8q", "a8=Q+"),
        ("6k1/5ppp/8/8/8/8/8/K3R3 w - - 0 1", "e1e8", "Re8#"),
        ("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1", "e5d6", "exd6"),
    ],
)
def test_san(fen: str, uci: str, san: str) -> None:
    assert Position.from_fen(fen).san(Move.from_uci(uci)) == san


def test_piece_square_tables() -> None:
    assert all(len(t) == 64 for t in PST.values())
    assert evaluate(Position.from_fen()) == 0  # symmetric start


def test_engine_takes_free_material_and_finds_mate() -> None:
    hanging = Position.from_fen("4k3/8/8/3q4/8/8/8/3QK3 w - - 0 1")
    assert best_move(hanging, max_depth=2) == Move.from_uci("d1d5")
    mate_in_one = Position.from_fen("6k1/5ppp/8/8/8/8/8/K3R3 w - - 0 1")
    assert best_move(mate_in_one, max_depth=2) == Move.from_uci("e1e8")
    # Black must not allow a back-rank mate next move.
    defend = Position.from_fen("6k1/5ppp/8/8/8/1q6/8/K3R3 b - - 0 1")
    reply = best_move(defend, max_depth=3)
    assert reply is not None
    defend.push(reply)
    for move in defend.legal_moves():
        defend.push(move)
        assert defend.outcome() != ("checkmate", "w"), move.uci
        defend.pop()


def test_engine_respects_time_and_leaves_position_alone() -> None:
    pos = Position.from_fen()
    before = pos.fen()
    stats = SearchStats()
    move = best_move(pos, max_depth=8, time_limit=0.3, stats=stats)
    assert move in pos.legal_moves() and pos.fen() == before
    assert stats.depth >= 1


def test_app_select_and_move(app_context: AppContext) -> None:
    from apps.chess.app import ChessApp

    app = ChessApp(app_context)
    app.on_enter()
    app.vs_cpu = False
    app._new_game()
    app._click_square(square("e2"))
    assert {m.end for m in app.targets} == {square("e3"), square("e4")}
    app._click_square(square("e4"))
    assert app.pos.board[square("e4")] == "P" and app.sans == ["e4"]
