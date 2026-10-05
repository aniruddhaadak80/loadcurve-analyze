"""Dense linear algebra for the DC network model.

Deliberately hand-rolled rather than pulled from NumPy or SciPy. Two reasons, both
correctness reasons rather than taste:

1. A study result must be bit-reproducible on any machine that runs the engine. A dense
   LU with partial pivoting uses only ``+ - * /``, which IEEE-754 specifies exactly, so the
   same model yields the same flows everywhere.
2. The engine runs as a subprocess per call. Every transitive dependency is startup latency
   on a path that is invoked from a CLI and from an MCP tool call.
"""

from __future__ import annotations

from typing import Final

from .protocol import EngineError

#: Relative pivot tolerance. Below this the matrix is treated as singular, which for a
#: network model means the branch set does not span a connected graph.
PIVOT_EPS: Final[float] = 1e-12


def identity(size: int) -> list[list[float]]:
    return [[1.0 if row == col else 0.0 for col in range(size)] for row in range(size)]


def zeros(rows: int, cols: int) -> list[list[float]]:
    return [[0.0] * cols for _ in range(rows)]


def matvec(matrix: list[list[float]], vector: list[float]) -> list[float]:
    return [sum(coefficient * value for coefficient, value in zip(row, vector, strict=True)) for row in matrix]


def solve(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    """Solve ``matrix @ x = rhs`` by Gaussian elimination with partial pivoting.

    Raises ``SINGULAR_MATRIX`` rather than returning garbage, because a singular admittance
    matrix is a modelling error an operator must see, not a zero the solver swallows.
    """
    size = len(rhs)
    if len(matrix) != size:
        raise EngineError(
            "SHAPE_MISMATCH", f"matrix has {len(matrix)} rows but rhs has {size} entries"
        )
    for candidate in matrix:
        if len(candidate) != size:
            raise EngineError("SHAPE_MISMATCH", "matrix is not square")

    # A dense (size + 1) x size tableau: the extra column is the right-hand side. Keeping the
    # elimination loop uniform over columns removes the separate augmented-vector update,
    # which is the part that would otherwise be easy to get subtly out of step.
    work: list[list[float]] = []
    for index, source in enumerate(matrix):
        tableau_row: list[float] = list(source)
        tableau_row.append(rhs[index])
        work.append(tableau_row)

    for column in range(size):
        pivot_row = max(range(column, size), key=lambda r: abs(work[r][column]))
        if abs(work[pivot_row][column]) < PIVOT_EPS:
            raise EngineError(
                "SINGULAR_MATRIX",
                f"admittance matrix is singular at column {column}; the in-service branch set "
                "does not form a connected network",
            )
        if pivot_row != column:
            work[column], work[pivot_row] = work[pivot_row], work[column]

        pivot = work[column][column]
        for target in range(column + 1, size):
            factor = work[target][column] / pivot
            if factor == 0.0:
                continue
            work[target] = [
                value - factor * pivot_value
                for value, pivot_value in zip(work[target], work[column], strict=True)
            ]

    solution: list[float] = [0.0] * size
    for target in reversed(range(size)):
        row_values = work[target]
        known = sum(
            row_values[column] * solution[column] for column in range(target + 1, size)
        )
        solution[target] = (row_values[size] - known) / row_values[target]
    return solution


def invert(matrix: list[list[float]]) -> list[list[float]]:
    """The full inverse, by solving against each unit vector in turn."""
    size = len(matrix)
    columns: list[list[float]] = []
    for index in range(size):
        unit = [0.0] * size
        unit[index] = 1.0
        columns.append(solve(matrix, unit))
    return [[columns[col][row] for col in range(size)] for row in range(size)]
