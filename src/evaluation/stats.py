"""
stats.py — Paired statistical tests between two systems.

With ~50 hand-labelled questions and paired per-question scores, a Wilcoxon
signed-rank test on the per-question deltas detects modest effects without
the normality assumption of a paired t-test. Both are exposed; report
Wilcoxon as the primary and the paired t-test as a sanity check.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

# Bootstrap config. n is modest (~50), so report an effect + CI, not p alone
# (see TODO §2 / BAB IV caveat). Seeded for reproducibility.
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 20260701


@dataclass
class PairedTestResult:
    metric: str
    n: int
    mean_baseline: float
    mean_graph: float
    mean_delta: float          # graph - baseline
    median_delta: float
    ci_low: float              # 2.5th pct of bootstrapped mean_delta
    ci_high: float             # 97.5th pct of bootstrapped mean_delta
    wilcoxon_stat: float
    wilcoxon_p: float
    t_stat: float
    t_p: float
    wins_graph: int            # questions where graph > baseline
    wins_baseline: int
    ties: int


def _bootstrap_ci(
    deltas: list[float],
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[float, float]:
    """Percentile 95% CI on the mean of paired per-question deltas.

    Resamples the n deltas with replacement `resamples` times (paired
    bootstrap: each resample keeps question pairing intact), takes the mean of
    each, and returns the 2.5/97.5 percentiles. Degenerate inputs return a
    point CI so callers don't special-case NaN.
    """
    n = len(deltas)
    if n == 0:
        return float("nan"), float("nan")
    if all(d == deltas[0] for d in deltas):  # no variation -> point mass
        return deltas[0], deltas[0]

    rng = random.Random(seed)
    means = []
    for _ in range(resamples):
        s = sum(deltas[rng.randrange(n)] for _ in range(n))
        means.append(s / n)
    means.sort()
    lo = means[max(0, int(math.floor(0.025 * resamples)) - 1)]
    hi = means[min(resamples - 1, int(math.ceil(0.975 * resamples)) - 1)]
    return lo, hi


def _safe_pairs(a: list[float], b: list[float]) -> tuple[list[float], list[float]]:
    pairs = [(x, y) for x, y in zip(a, b) if not (math.isnan(x) or math.isnan(y))]
    if not pairs:
        return [], []
    xs, ys = zip(*pairs)
    return list(xs), list(ys)


def paired_test(
    metric: str,
    baseline_scores: list[float],
    graph_scores: list[float],
) -> PairedTestResult:
    """
    `baseline_scores` and `graph_scores` must be aligned per-question. NaNs
    in either side drop the pair. Returns NaN test stats when the test is
    degenerate (all deltas zero, n<1, etc.).
    """
    try:
        from scipy import stats as sp_stats
    except ImportError as e:
        raise ImportError("paired_test requires scipy. Install with: pip install scipy") from e

    a, b = _safe_pairs(baseline_scores, graph_scores)
    n = len(a)
    if n == 0:
        nan = float("nan")
        return PairedTestResult(metric, 0, nan, nan, nan, nan, nan, nan, nan, nan, nan, nan, 0, 0, 0)

    deltas = [bi - ai for ai, bi in zip(a, b)]
    mean_b = sum(a) / n
    mean_g = sum(b) / n
    mean_d = sum(deltas) / n
    median_d = sorted(deltas)[n // 2] if n % 2 == 1 else 0.5 * (sorted(deltas)[n // 2 - 1] + sorted(deltas)[n // 2])
    ci_low, ci_high = _bootstrap_ci(deltas)

    wins_graph = sum(1 for d in deltas if d > 0)
    wins_baseline = sum(1 for d in deltas if d < 0)
    ties = sum(1 for d in deltas if d == 0)

    if all(d == 0 for d in deltas):
        w_stat, w_p, t_stat, t_p = float("nan"), 1.0, float("nan"), 1.0
    else:
        try:
            w_res = sp_stats.wilcoxon(a, b, zero_method="wilcox", alternative="two-sided")
            w_stat, w_p = float(w_res.statistic), float(w_res.pvalue)
        except ValueError:
            w_stat, w_p = float("nan"), float("nan")
        t_res = sp_stats.ttest_rel(b, a)  # graph - baseline
        t_stat, t_p = float(t_res.statistic), float(t_res.pvalue)

    return PairedTestResult(
        metric=metric, n=n,
        mean_baseline=mean_b, mean_graph=mean_g,
        mean_delta=mean_d, median_delta=median_d,
        ci_low=ci_low, ci_high=ci_high,
        wilcoxon_stat=w_stat, wilcoxon_p=w_p,
        t_stat=t_stat, t_p=t_p,
        wins_graph=wins_graph, wins_baseline=wins_baseline, ties=ties,
    )
