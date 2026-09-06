"""Edit distance for rule A2.

`levenshtein` is the plain textbook distance (kept for tooling and tests);
`bounded_distance` is what the matcher uses: it answers "is the distance at
most k, and if so what is it" and gives up as early as the band allows.
"""
from __future__ import annotations


def levenshtein(a: str, b: str) -> int:
    """Unit-cost Levenshtein distance, two-row dynamic programme."""
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def bounded_distance(a: str, b: str, k: int) -> int | None:
    """Return the Levenshtein distance of ``a`` and ``b`` if it is <= k, else None.

    Only the diagonal band of width 2k+1 is evaluated and the scan stops as soon
    as every cell of a row exceeds k.
    """
    if abs(len(a) - len(b)) > k:
        return None
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    n = len(b)
    inf = k + 1
    prev = list(range(n + 1))
    for i in range(1, len(a) + 1):
        lo = max(1, i - k)
        hi = min(n, i + k)
        cur = [inf] * (n + 1)
        if lo == 1:
            cur[0] = i if i <= k else inf
        ca = a[i - 1]
        best = inf
        for j in range(lo, hi + 1):
            v = prev[j] + 1
            left = cur[j - 1] + 1
            if left < v:
                v = left
            diag = prev[j - 1] + (ca != b[j - 1])
            if diag < v:
                v = diag
            cur[j] = v
            if v < best:
                best = v
        if best > k:
            return None
        prev = cur
    d = prev[n]
    return d if d <= k else None
