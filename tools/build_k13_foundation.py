"""Assemble the refactored k13 foundation: our atomic c268 stream (generator_c251 prefix, c268 constants)
plus the king's v2 layers with the serial base generate rebuilt from our chunk helpers."""
import re
from pathlib import Path

old = Path("generator_c251/generator.py").read_text(encoding="utf-8").split("\n")
king = Path("reference/kings/2026-11-04-716765dcf2f6/generator.py").read_text(encoding="utf-8").split("\n")

cut_old = next(i for i, l in enumerate(old) if l.startswith("# ═══════════════ v2 pack:"))
prefix = old[:cut_old]
while prefix and prefix[-1] == "":
    prefix.pop()
restore = {
    "_PRODUCER_WORKERS = 1  # v2 child: one core; >1 only adds threads and memory arenas": "_PRODUCER_WORKERS = 3",
    "_C91_CHILD_BUDGET = 1_562_500_000  # v2 child: 50e9 points / 32 children": "_C91_CHILD_BUDGET = 13_320_000_000",
    "_YZ_CHILD_BUDGET = 1_562_500_000  # v2 child: 50e9 points / 32 children": "_YZ_CHILD_BUDGET = 13_320_000_000",
    "_C215LP_STREAM_POINTS = 1_562_500_000  # v2 child: 50e9 points / 32 children": "_C215LP_STREAM_POINTS = 39960000000 // 3",
}
hits = 0
for i, l in enumerate(prefix):
    if l in restore:
        prefix[i] = restore[l]
        hits += 1
assert hits == 4, hits
# the king drops the "# cascade era ..." first line
if prefix[0].startswith("# cascade era"):
    prefix = prefix[1:]

k0 = next(i for i, l in enumerate(king) if l.startswith("# ═══════════════ K0: v2 Lane A port"))
tail = king[k0:]
s = next(i for i, l in enumerate(tail) if l.startswith("def _k0_serial_base_generate"))
e = next(i for i, l in enumerate(tail) if l.startswith("_K0_THREADED_BASE_GENERATE"))
serial = '''def _k0_serial_base_generate(self, n_series: int) -> Iterator[np.ndarray]:
    """_BaseGenerator.generate without the producer thread: the same chunks, yielded inline."""
    if n_series <= 0:
        return
    rng = np.random.default_rng(self._seed)
    target_points = self._target_points(n_series)
    produced = 0
    emitted_points = 0
    chunk_index = 0
    while produced < n_series:
        chunk, take, chunk_points = self._produce_chunk(
            rng, chunk_index, produced, emitted_points, n_series, target_points)
        yield from _checked_chunk_rows(chunk, take)
        produced += take
        emitted_points += chunk_points
        chunk_index += 1

'''.split("\n")
tail = tail[:s] + serial + tail[e:]
out = prefix + ["", ""] + tail
Path("generator/generator.py").write_text("\n".join(out), encoding="utf-8")
print(len(prefix), len(tail), len(out))
