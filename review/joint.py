import itertools

from archive.bundle import BundleError, JointBundle, open_bundle
from encoding.field import interpolate
from encoding.layout import SOURCE_SLOTS, Layout
from review.report import (
    JointAmbiguousReport,
    JointRecoveredReport,
    JointUnrecoverableReport,
    joint_ambiguous_report,
    joint_recovered_report,
    joint_unrecoverable_report,
)


Vectors = dict[int, tuple[tuple[str, tuple[int, ...]], ...]]


def _received_vectors(bundle: JointBundle) -> Vectors:
    collected: dict[int, list[tuple[int, str, tuple[int, ...]]]] = {}
    for order, (source, fragments) in enumerate(
        (('original', bundle.original), ('supplement', bundle.supplement))
    ):
        for fragment in fragments:
            collected.setdefault(fragment.slot, []).append((order, source, fragment.values))
    return {
        slot: tuple((source, values) for _, source, values in sorted(entries, key=lambda item: item[0]))
        for slot, entries in collected.items()
    }


def _candidate_columns(layout: Layout, received: Vectors):
    slots = sorted(received)
    if len(slots) < 3:
        return
    seen = set()
    for combination in itertools.combinations(slots, 3):
        for selection in itertools.product(*(received[slot] for slot in combination)):
            columns = []
            for column in range(layout.width):
                points = tuple(
                    (slot, values[column]) for slot, (_, values) in zip(combination, selection)
                )
                columns.append(tuple(interpolate(points, coordinate) for coordinate in layout.coordinates))
            rows = tuple(tuple(columns[column][slot] for column in range(layout.width)) for slot in SOURCE_SLOTS)
            if rows in seen:
                continue
            seen.add(rows)
            yield rows, tuple(columns)


def _evaluate(layout: Layout, received: Vectors, columns: tuple[tuple[int, ...], ...]):
    if sum(1 for slot in layout.coordinates if slot not in received) > 1:
        return None
    bad_slots = []
    original_disagreements = []
    supplement_disagreements = []
    for slot in layout.coordinates:
        vectors = received.get(slot, ())
        if not vectors:
            continue
        prediction = tuple(column[slot] for column in columns)
        if not any(values == prediction for _, values in vectors):
            bad_slots.append(slot)
            if len(bad_slots) > 1:
                return None
        for source, values in vectors:
            if values == prediction:
                continue
            entry = (source, slot, values)
            if source == 'original':
                original_disagreements.append(entry)
            else:
                supplement_disagreements.append(entry)
    return tuple(bad_slots), tuple(original_disagreements + supplement_disagreements)


def recover_joint(raw: bytes) -> JointRecoveredReport | JointUnrecoverableReport | JointAmbiguousReport:
    bundle = open_bundle(raw)
    if not isinstance(bundle, JointBundle):
        raise BundleError('joint recovery requires a joint bundle')
    received = _received_vectors(bundle)
    interpretations = []
    for rows, columns in _candidate_columns(bundle.layout, received):
        outcome = _evaluate(bundle.layout, received, columns)
        if outcome is None:
            continue
        interpretations.append((rows, outcome))
        if len(interpretations) > 1:
            return joint_ambiguous_report(
                bundle.bundle_id, bundle.original_bundle_id, bundle.supplement_batch_id,
            )
    if not interpretations:
        return joint_unrecoverable_report(
            bundle.bundle_id, bundle.original_bundle_id, bundle.supplement_batch_id,
        )
    rows, (bad_slots, disagreements) = interpretations[0]
    return joint_recovered_report(
        bundle.bundle_id,
        bundle.original_bundle_id,
        bundle.supplement_batch_id,
        rows,
        bad_slots,
        disagreements,
    )
