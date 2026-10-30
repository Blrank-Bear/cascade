"""Screening-only speed patch for upstream's MoEFFN collapsed-router path.

Upstream `MoEFFN.forward` falls back to a Python loop over experts when the router is
collapsed (`cap * E > 2 * N * K`), calling `expert_single`, which does `weight[expert]`.
Each `weight[expert]` backward materialises a zero-filled gradient of the whole
(E, d, h) tensor and adds into it, once per expert: about 90% of GPU time on a 4090
(see notes/V2_EVAL_FACTS.md).

This patch makes each forward split the expert weights once with `unbind(0)`; the
backward then assembles all expert gradients in one stack. The matmuls are identical
and every expert slice still receives exactly one gradient contribution, so results
are unchanged. It never touches upstream files: `apply()` patches the class in-process.
Used only by our duel/grid tooling (`duel_fast.py`); validators run upstream code as-is.
"""
from __future__ import annotations

_APPLIED = False


def _views(layer, kind: str):
    cache = layer.__dict__.get("_fast_moe_views")
    return cache[kind] if cache else None


def _patched_forward(orig_forward):
    def forward(self, x, seq_len):
        self.__dict__["_fast_moe_views"] = {"w_in": self.w_in.unbind(0), "w_out": self.w_out.unbind(0)}
        try:
            return orig_forward(self, x, seq_len)
        finally:
            self.__dict__.pop("_fast_moe_views", None)
    return forward


def _patched_single(orig_single):
    def expert_single(self, x, expert, kind):
        views = _views(self, kind)
        if views is None:
            return orig_single(self, x, expert, kind)
        return x @ views[expert].to(x.dtype)
    return expert_single


def apply() -> None:
    global _APPLIED
    if _APPLIED:
        return
    from cascade.trainer.pyramid_model import MoEFFN
    MoEFFN.forward = _patched_forward(MoEFFN.forward)
    MoEFFN.expert_single = _patched_single(MoEFFN.expert_single)
    _APPLIED = True
