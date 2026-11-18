from archive.bundle import open_bundle
from encoding.layout import SOURCE_SLOTS
from review.candidates import fit_column
from review.discrepancies import column_disagreements
from review.report import RecoveredReport, UnrecoverableReport, recovered_report, unrecoverable_report


def recover(raw: bytes) -> RecoveredReport | UnrecoverableReport:
    bundle = open_bundle(raw)
    coordinates = bundle.layout.coordinates
    observed = {fragment.slot: fragment.values for fragment in bundle.fragments}
    if len(coordinates) - len(observed) > 1:
        return unrecoverable_report(bundle.bundle_id)

    for excluded in (None, *observed):
        trusted = tuple(slot for slot in observed if slot != excluded)[:len(SOURCE_SLOTS)]
        columns = []
        bad_slots = set()
        for column in range(bundle.layout.width):
            candidate = fit_column((slot, observed[slot][column]) for slot in trusted)
            values = candidate.values_at(coordinates)
            actual = ((slot, row[column]) for slot, row in observed.items())
            bad_slots.update(column_disagreements(values, actual))
            if len(bad_slots) > 1:
                break
            columns.append(values)
        else:
            # Two admissible candidates share at least three agreeing received coordinates.
            return recovered_report(bundle.bundle_id, columns, bad_slots)
    return unrecoverable_report(bundle.bundle_id)
