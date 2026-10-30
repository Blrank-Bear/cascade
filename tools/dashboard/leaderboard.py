"""Leaderboard from public receipts: one row per participant (uid/hotkey).

Combines the receipts index (every settled round's king/challenger result) with the
latest full receipt (participants, commit blocks, on-chain weights).
"""
from __future__ import annotations


def challenger_stats(rounds: list[dict]) -> dict[str, dict]:
    """Per challenger hotkey: duels, best gap vs king, dethrones, last duel block."""
    out: dict[str, dict] = {}
    for r in rounds:
        hk = r.get("chal_hotkey")
        if not hk or r.get("chal_geomean") is None or not r.get("king_geomean"):
            continue
        s = out.setdefault(hk, {"duels": 0, "dethrones": 0, "best_gap": None, "last_block": None, "last_gap": None})
        gap = 1 - r["chal_geomean"] / r["king_geomean"]
        s["duels"] += 1
        s["dethrones"] += bool(r.get("dethroned"))
        s["best_gap"] = gap if s["best_gap"] is None else max(s["best_gap"], gap)
        s["last_block"], s["last_gap"] = r.get("epoch_start_block"), gap
    return out


def reward_counts(rounds: list[dict]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for r in rounds:
        for uid in r.get("reward_uids") or []:
            counts[uid] = counts.get(uid, 0) + 1
    return counts


def king_rounds(rounds: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in rounds:
        hk = r.get("king_hotkey")
        if hk:
            counts[hk] = counts.get(hk, 0) + 1
    return counts


def participant_row(p: dict, weights: list, chal: dict, rewards: dict, kings: dict,
                    king_hotkey: str | None, mine: set[str]) -> dict:
    uid, hk = p.get("uid"), p.get("hotkey")
    c = chal.get(hk, {})
    w = weights[uid] if isinstance(uid, int) and uid < len(weights) else None
    return {"uid": uid, "hotkey": hk, "weight": w, "commit_block": p.get("commit_block"),
            "gen_ref": p.get("gen_ref"), "is_king": hk == king_hotkey, "is_mine": hk in mine,
            "duels": c.get("duels", 0), "dethrones": c.get("dethrones", 0), "best_gap": c.get("best_gap"),
            "last_gap": c.get("last_gap"), "last_duel_block": c.get("last_block"),
            "rewarded_rounds": rewards.get(uid, 0), "king_rounds": kings.get(hk, 0)}


def leaderboard(index_rows: list[dict], receipt: dict, mine: set[str]) -> dict:
    """Rows sorted by on-chain weight, then best gap vs king."""
    weights = receipt.get("weights") or []
    king = next((e.get("hotkey") for e in receipt.get("entry_scores", []) if e.get("role") == "king"), None)
    chal, rewards, kings = challenger_stats(index_rows), reward_counts(index_rows), king_rounds(index_rows)
    rows = [participant_row(p, weights, chal, rewards, kings, king, mine) for p in receipt.get("participants", [])]
    rows.sort(key=lambda r: (-(r["weight"] or 0), -(r["best_gap"] if r["best_gap"] is not None else -9)))
    return {"round_block": receipt.get("epoch_start_block"), "n_participants": len(rows),
            "n_weighted": sum(1 for r in rows if (r["weight"] or 0) > 0), "rows": rows}


def all_rounds(index: dict) -> list[dict]:
    """Every scored row in the index (keeps duplicates per block: one per validator)."""
    return [r for r in index.get("rounds", []) if r.get("status") == "scored"]
