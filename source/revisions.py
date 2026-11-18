from collections.abc import Sequence

from source.observations import freeze_observations
from source.schema import RevisionKey
from source.store import RevisionStore


def record(store: RevisionStore, day_key: str, label: str, rows: Sequence[Sequence[int]]) -> str:
    key = RevisionKey(day_key, label)
    frozen_rows = freeze_observations(rows)
    return store.register_snapshot(key, frozen_rows)
