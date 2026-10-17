"""Rates, error bars and the comparison with the FCC filing.

Rates are events per satellite per year of OBSERVED time: the sum, over satellites,
of the gaps in which a step could have been detected (see detect.gap_steps). A
satellite we saw for 3 days counts for 3 days, not for the whole window.

Error bars:
- bootstrap over satellites (resample whole satellites with replacement), which
  respects that one satellite's events are not independent of each other;
- exact Poisson (Garwood) intervals for small counts such as false alarms;
- Wilson intervals for recall fractions.
All intervals are 95%.
"""
import math

import numpy as np

Z95 = 1.959963984540054


def _poisson_cdf(k, mu):
    """P(X <= k) for X ~ Poisson(mu), summed in log space (no underflow for big mu)."""
    if mu <= 0:
        return 1.0
    logs = [-mu + i * math.log(mu) - math.lgamma(i + 1) for i in range(k + 1)]
    top = max(logs)
    return min(1.0, math.exp(top) * sum(math.exp(x - top) for x in logs))


def poisson_interval(k, conf=0.95):
    """Exact (Garwood) interval for a Poisson mean given k observed events."""
    alpha = 1.0 - conf

    def solve(target, k_eff, lo, hi):
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if _poisson_cdf(k_eff, mid) > target:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)

    hi_bound = max(10.0, k * 3.0 + 20.0)
    lower = 0.0 if k == 0 else solve(1.0 - alpha / 2.0, k - 1, 0.0, hi_bound)
    upper = solve(alpha / 2.0, k, 0.0, hi_bound)
    return lower, upper


def wilson(successes, n):
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    p = successes / n
    den = 1.0 + Z95 ** 2 / n
    centre = (p + Z95 ** 2 / (2 * n)) / den
    half = Z95 * math.sqrt(p * (1 - p) / n + Z95 ** 2 / (4 * n * n)) / den
    return p, max(0.0, centre - half), min(1.0, centre + half)


def rate_per_year(count, exposure_days):
    return count / (exposure_days / 365.25) if exposure_days > 0 else float("nan")


def bootstrap_rate(counts, exposures, rng, n_boot=2000):
    """95% interval of sum(counts)/sum(exposure) per year, resampling satellites."""
    counts = np.asarray(counts, float)
    exposures = np.asarray(exposures, float)
    n = len(counts)
    if n == 0 or exposures.sum() <= 0:
        return float("nan"), float("nan")
    idx = rng.integers(0, n, size=(n_boot, n))
    rates = counts[idx].sum(axis=1) / (exposures[idx].sum(axis=1) / 365.25)
    return float(np.quantile(rates, 0.025)), float(np.quantile(rates, 0.975))


def false_alarm(count, exposure_days):
    """(rate, 95% upper bound) per object-year from a passive control group."""
    _, up = poisson_interval(count)
    return rate_per_year(count, exposure_days), rate_per_year(up, exposure_days)
