"""Edit distance for rule A2."""
from __future__ import annotations


def levenshtein(a: str, b: str) -> int:
    """Unit-cost Levenshtein distance (full dynamic-programming matrix)."""
    rows, cols = len(a) + 1, len(b) + 1
    matrix = [[0] * cols for _ in range(rows)]
    for i in range(rows):
        matrix[i][0] = i
    for j in range(cols):
        matrix[0][j] = j
    for i in range(1, rows):
        for j in range(1, cols):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            matrix[i][j] = min(
                matrix[i - 1][j] + 1,  # deletion
                matrix[i][j - 1] + 1,  # insertion
                matrix[i - 1][j - 1] + cost,  # substitution
            )
    return matrix[rows - 1][cols - 1]
