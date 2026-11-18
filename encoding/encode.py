from dataclasses import dataclass

from encoding.field import interpolate
from encoding.layout import SOURCE_SLOTS, Layout, make_layout
from encoding.payload import Fragment, freeze_slot_payload
from source.history import get_revision
from source.store import RevisionStore


@dataclass(frozen=True)
class EncodedRevision:
    layout: Layout
    fragments: tuple[Fragment, ...]


def encode(store: RevisionStore, revision_id: str) -> EncodedRevision:
    snapshot = get_revision(store, revision_id)
    layout = make_layout(snapshot.key.day_key, snapshot.revision_id, len(snapshot.rows[0]))
    column_samples = tuple(
        tuple((slot, snapshot.rows[slot][column]) for slot in SOURCE_SLOTS)
        for column in range(layout.width)
    )

    fragments = []
    for slot in layout.coordinates:
        if slot in SOURCE_SLOTS:
            values = snapshot.rows[slot]
        else:
            values = tuple(interpolate(samples, slot) for samples in column_samples)
        fragments.append(freeze_slot_payload(layout, slot, values))
    return EncodedRevision(layout, tuple(fragments))
