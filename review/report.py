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


@dataclass(frozen=True)
class JointRecoveredReport:
    bundle_id: str
    original_bundle_id: str
    supplement_batch_id: str
    rows: tuple[tuple[int, ...], ...]
    bad_slots: tuple[int, ...]
    disagreements: tuple[tuple[str, int, tuple[int, ...]], ...]
    status: Literal['recovered'] = field(default='recovered', init=False)


@dataclass(frozen=True)
class JointUnrecoverableReport:
    bundle_id: str
    original_bundle_id: str
    supplement_batch_id: str
    status: Literal['unrecoverable'] = field(default='unrecoverable', init=False)


@dataclass(frozen=True)
class JointAmbiguousReport:
    bundle_id: str
    original_bundle_id: str
    supplement_batch_id: str
    status: Literal['ambiguous'] = field(default='ambiguous', init=False)


def joint_recovered_report(
    bundle_id: str,
    original_bundle_id: str,
    supplement_batch_id: str,
    rows: Sequence[Sequence[int]],
    bad_slots: Iterable[int],
    disagreements: Iterable[tuple[str, int, Sequence[int]]],
) -> JointRecoveredReport:
    return JointRecoveredReport(
        bundle_id,
        original_bundle_id,
        supplement_batch_id,
        tuple(tuple(row) for row in rows),
        tuple(sorted(set(bad_slots))),
        tuple((source, slot, tuple(values)) for source, slot, values in disagreements),
    )


def joint_unrecoverable_report(
    bundle_id: str, original_bundle_id: str, supplement_batch_id: str,
) -> JointUnrecoverableReport:
    return JointUnrecoverableReport(bundle_id, original_bundle_id, supplement_batch_id)


def joint_ambiguous_report(
    bundle_id: str, original_bundle_id: str, supplement_batch_id: str,
) -> JointAmbiguousReport:
    return JointAmbiguousReport(bundle_id, original_bundle_id, supplement_batch_id)
