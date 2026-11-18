from collections.abc import Iterable
from dataclasses import dataclass

from encoding.field import interpolate


@dataclass(frozen=True)
class ColumnCandidate:
    points: tuple[tuple[int, int], ...]

    def values_at(self, coordinates: Iterable[int]) -> tuple[int, ...]:
        return tuple(interpolate(self.points, coordinate) for coordinate in coordinates)


def fit_column(trusted_points: Iterable[tuple[int, int]]) -> ColumnCandidate:
    points = tuple(trusted_points)
    if len(points) != 3 or len({slot for slot, _ in points}) != 3:
        raise ValueError('a column candidate requires three distinct trusted slots')
    return ColumnCandidate(points)
