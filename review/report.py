from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal

from encoding.layout import SOURCE_SLOTS


@dataclass(frozen=True)
class RecoveredReport:
    bundle_id: str
    rows: tuple[tuple[int, ...], ...]
    bad_slots: tuple[int, ...]
    status: Literal['recovered'] = field(default='recovered', init=False)


@dataclass(frozen=True)
class UnrecoverableReport:
    bundle_id: str
    status: Literal['unrecoverable'] = field(default='unrecoverable', init=False)


def recovered_report(
    bundle_id: str, columns: Sequence[Sequence[int]], bad_slots: Iterable[int],
) -> RecoveredReport:
    rows = tuple(tuple(column[slot] for column in columns) for slot in SOURCE_SLOTS)
    return RecoveredReport(bundle_id, rows, tuple(sorted(set(bad_slots))))


def unrecoverable_report(bundle_id: str) -> UnrecoverableReport:
    return UnrecoverableReport(bundle_id)
