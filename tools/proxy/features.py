"""Scale-free per-series features for comparing a synthetic corpus with the eval pool.

Every feature is one small function of a clean 1-D float64 array (NaNs removed,
length >= MIN_LENGTH). `series_features` returns them in FEATURE_NAMES order.
"""
from __future__ import annotations

import numpy as np

MIN_LENGTH = 64
SEASONAL_LAGS = (7, 12, 24, 48, 60, 96, 168, 288, 365, 672, 1440)
EPS = 1e-12


# ── preparation ────────────────────────────────────────────────────────────

def clean_series(x) -> np.ndarray:
    a = np.asarray(x, dtype=np.float64).ravel()
    return a[np.isfinite(a)]


def zscore(a: np.ndarray) -> np.ndarray:
    sd = a.std()
    return (a - a.mean()) / sd if sd > EPS else a - a.mean()


def acf_at(z: np.ndarray, lag: int) -> float:
    if lag <= 0 or lag >= z.size - 1:
        return 0.0
    return float(np.dot(z[:-lag], z[lag:]) / z.size)


# ── features ───────────────────────────────────────────────────────────────

def f_acf1_level(a: np.ndarray) -> float:
    return acf_at(zscore(a), 1)


def f_acf1_diff(a: np.ndarray) -> float:
    return acf_at(zscore(np.diff(a)), 1)


def f_seasonal_acf(a: np.ndarray) -> float:
    z = zscore(np.diff(a))
    lags = [lag for lag in SEASONAL_LAGS if lag < z.size // 2]
    return max((acf_at(z, lag) for lag in lags), default=0.0)


def f_spectral_entropy(a: np.ndarray) -> float:
    p = np.abs(np.fft.rfft(zscore(a)))[1:] ** 2
    total = p.sum()
    if total <= EPS or p.size < 2:
        return 0.0
    p = p / total
    return float(-(p * np.log(p + EPS)).sum() / np.log(p.size))


def f_flat_frac(a: np.ndarray) -> float:
    return float(np.mean(np.diff(a) == 0.0))


def f_zero_frac(a: np.ndarray) -> float:
    return float(np.mean(a == 0.0))


def f_int_frac(a: np.ndarray) -> float:
    return float(np.mean(np.abs(a - np.round(a)) < 1e-9))


def f_nonneg(a: np.ndarray) -> float:
    return float(a.min() >= 0.0)


def f_trend_r2(a: np.ndarray) -> float:
    t = zscore(np.arange(a.size, dtype=np.float64))
    return float(np.dot(t, zscore(a)) / a.size) ** 2


def f_diff_skew(a: np.ndarray) -> float:
    z = zscore(np.diff(a))
    return float(np.clip(np.mean(z ** 3), -20.0, 20.0))


def f_diff_log_kurt(a: np.ndarray) -> float:
    z = zscore(np.diff(a))
    return float(np.log1p(max(np.mean(z ** 4), 0.0)))


def f_log_spike(a: np.ndarray) -> float:
    return float(np.log1p(np.abs(zscore(np.diff(a))).max()))


def f_log_unique_ratio(a: np.ndarray) -> float:
    return float(np.log10(np.unique(a).size / a.size))


def f_log_var_ratio16(a: np.ndarray) -> float:
    d1 = np.diff(a)
    d16 = a[16:] - a[:-16]
    v1 = d1.var()
    return float(np.log((d16.var() + EPS) / (16.0 * v1 + EPS))) if v1 > EPS else 0.0


def f_log_tail_head_std(a: np.ndarray) -> float:
    k = max(a.size // 10, 8)
    return float(np.log((a[-k:].std() + EPS) / (a[:k].std() + EPS)))


def f_log_cv(a: np.ndarray) -> float:
    return float(np.clip(np.log10((a.std() + EPS) / (abs(a.mean()) + EPS)), -6.0, 6.0))


FEATURES = (
    ("acf1_level", f_acf1_level),
    ("acf1_diff", f_acf1_diff),
    ("seasonal_acf", f_seasonal_acf),
    ("spectral_entropy", f_spectral_entropy),
    ("flat_frac", f_flat_frac),
    ("zero_frac", f_zero_frac),
    ("int_frac", f_int_frac),
    ("nonneg", f_nonneg),
    ("trend_r2", f_trend_r2),
    ("diff_skew", f_diff_skew),
    ("diff_log_kurt", f_diff_log_kurt),
    ("log_spike", f_log_spike),
    ("log_unique_ratio", f_log_unique_ratio),
    ("log_var_ratio16", f_log_var_ratio16),
    ("log_tail_head_std", f_log_tail_head_std),
    ("log_cv", f_log_cv),
)
FEATURE_NAMES = tuple(name for name, _ in FEATURES)


def series_features(x) -> np.ndarray | None:
    a = clean_series(x)
    if a.size < MIN_LENGTH or a.std() <= EPS:
        return None
    return np.asarray([fn(a) for _, fn in FEATURES], dtype=np.float64)
