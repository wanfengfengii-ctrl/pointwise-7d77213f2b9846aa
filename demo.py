import json
from pathlib import Path
from tempfile import TemporaryDirectory

from archive.bundle import open_bundle
from archive.catalog import ArchiveCatalog
from archive.export import export
from archive.publication import seal
from encoding.encode import encode
from encoding.payload import Fragment
from receipt.intake import receive
from receipt.ledger import ReceiptLedger
from review.recovery import recover
from review.report import RecoveredReport
from source.revisions import record
from source.store import RevisionStore


def main() -> None:
    sample_path = Path(__file__).resolve().parent / 'samples' / 'linear_day.json'
    sample = json.loads(sample_path.read_text(encoding='utf-8'))
    with TemporaryDirectory(prefix='hydrology-demo-') as directory:
        root = Path(directory)
        store = RevisionStore(root / 'source.sqlite3')
        ledger = ReceiptLedger(root / 'receipt.sqlite3')
        catalog = ArchiveCatalog(root / 'archive.sqlite3')
        for database in (store, ledger, catalog):
            database.initialize()

        revision_id = record(store, sample['day_key'], sample['revision_label'], sample['rows'])
        encoded = encode(store, revision_id)
        mirror = {fragment.slot: fragment for fragment in encoded.fragments}
        change = sample['changed_value']
        changed_slot = change['slot']
        changed_values = list(mirror[changed_slot].values)
        changed_values[change['column']] = change['value']
        mirror[changed_slot] = Fragment(changed_slot, changed_values)
        batch_id = receive(ledger, encoded.layout, (mirror[slot] for slot in sample['arrivals']))
        receipt = seal(ledger, catalog, batch_id)
        mirror.clear()

        reopened = ArchiveCatalog(catalog.path)
        reopened.initialize()
        raw = export(reopened, receipt.bundle_id)
        bundle = open_bundle(raw)
        report = recover(raw)
        if not isinstance(report, RecoveredReport):
            raise AssertionError(f'expected a recovered report, received {report.status}')
        received = [[fragment.slot, list(fragment.values)] for fragment in bundle.fragments]
        downstream = {
            'status': report.status,
            'rows': [list(row) for row in report.rows],
            'bad_slots': list(report.bad_slots),
            'binding_matches': (
                report.bundle_id == bundle.bundle_id == receipt.bundle_id
                and bundle.layout.revision_id == revision_id
                and bundle.layout.day_key == sample['day_key']
            ),
        }
        if received != sample['expected_received'] or downstream != sample['expected_report']:
            raise AssertionError(f'demo evidence or recovery disagrees with the hand-worked sample: {received!r}, {downstream!r}')
        scenario = {
            'case_id': 'v4',
            'input': {key: sample[key] for key in ('day_key', 'revision_label', 'rows', 'arrivals', 'changed_value')},
            'expected': sample['expected_received'],
            'actual': received,
            'downstream_expected': sample['expected_report'],
            'downstream_actual': downstream,
            'code_paths': ['encoding/encode.py', 'receipt/intake.py', 'archive/publication.py',
                           'archive/export.py', 'archive/bundle.py', 'review/recovery.py'],
            'oracle': 'Use 10+x and 20+2x at the named slots, omit slot 1, and compare the real slot 3 edit with the two unaltered formulas.',
        }
        print('POINTWISE_SCENARIO ' + json.dumps(scenario, ensure_ascii=False, sort_keys=True, separators=(',', ':')))


if __name__ == '__main__':
    main()
