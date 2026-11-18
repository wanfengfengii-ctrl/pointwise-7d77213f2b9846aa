import hashlib
import json

from archive.bundle import BundleError, open_bundle
from archive.export import export
from archive.publication import seal
from receipt.intake import receive
from review.recovery import recover
from review.report import RecoveredReport, UnrecoverableReport
from support import LINEAR, ZERO, LakeTestCase, LocalMirror


class RecoveryTests(LakeTestCase):
    def _sealed_evidence(self, rows=LINEAR, *, omit=(), edits=None):
        encoded = self.encode_day(rows)
        mirror = LocalMirror(encoded)
        batch_id = receive(self.ledger, encoded.layout, mirror.handoff(omit=omit, edits=edits))
        receipt = seal(self.ledger, self.catalog, batch_id)
        mirror.close()
        return receipt, export(self.catalog, receipt.bundle_id)

    def assertRecovered(self, raw, bundle_id, rows, bad_slots):
        report = recover(raw)
        self.assertIsInstance(report, RecoveredReport)
        self.assertEqual(report.status, 'recovered')
        self.assertEqual((report.bundle_id, report.rows, report.bad_slots), (bundle_id, rows, bad_slots))

    def assertUnrecoverable(self, raw, bundle_id):
        report = recover(raw)
        self.assertIsInstance(report, UnrecoverableReport)
        self.assertEqual((report.status, report.bundle_id), ('unrecoverable', bundle_id))
        self.assertFalse(hasattr(report, 'rows'))
        self.assertFalse(hasattr(report, 'bad_slots'))

    def test_v3_full_clean_package_from_unordered_delivery(self):
        receipt, raw = self._sealed_evidence()
        self.assertEqual(open_bundle(raw).directory, (0, 1, 2, 3, 4, 5))
        self.assertRecovered(raw, receipt.bundle_id, LINEAR, ())

    def test_v3_zero_width_package_and_missing_budget(self):
        empty_rows = ((), (), ())
        receipt, raw = self._sealed_evidence(empty_rows)
        self.assertEqual(open_bundle(raw).directory, (0, 1, 2, 3, 4, 5))
        self.assertRecovered(raw, receipt.bundle_id, empty_rows, ())
        receipt, raw = self._sealed_evidence(empty_rows, omit=(1,))
        self.assertEqual(open_bundle(raw).directory, (0, 2, 3, 4, 5))
        self.assertRecovered(raw, receipt.bundle_id, empty_rows, ())
        receipt, raw = self._sealed_evidence(empty_rows, omit=(1, 3))
        self.assertUnrecoverable(raw, receipt.bundle_id)

    def test_v4_missing_slot_and_wrong_value_in_parity_slot(self):
        receipt, raw = self._sealed_evidence(omit=(1,), edits={(3, 0): 14})
        bundle = open_bundle(raw)
        self.assertEqual(bundle.directory, (0, 2, 3, 4, 5))
        self.assertEqual(tuple((fragment.slot, fragment.values) for fragment in bundle.fragments), (
            (0, (10, 20)), (2, (12, 24)), (3, (14, 26)), (4, (14, 28)), (5, (15, 30)),
        ))
        self.assertRecovered(raw, receipt.bundle_id, LINEAR, (3,))

    def test_v4_missing_only_preserves_original_coordinates(self):
        receipt, raw = self._sealed_evidence(omit=(1,))
        bundle = open_bundle(raw)
        self.assertEqual(bundle.directory, (0, 2, 3, 4, 5))
        self.assertEqual(tuple((fragment.slot, fragment.values) for fragment in bundle.fragments), (
            (0, (10, 20)), (2, (12, 24)), (3, (13, 26)), (4, (14, 28)), (5, (15, 30)),
        ))
        self.assertRecovered(raw, receipt.bundle_id, LINEAR, ())

    def test_v5_disjoint_column_faults_exceed_shared_slot_budget(self):
        receipt, raw = self._sealed_evidence(ZERO, edits={(1, 0): 1, (2, 1): 1})
        bundle = open_bundle(raw)
        self.assertEqual(bundle.directory, (0, 1, 2, 3, 4, 5))
        self.assertEqual(tuple(fragment.values for fragment in bundle.fragments), (
            (0, 0), (1, 0), (0, 1), (0, 0), (0, 0), (0, 0),
        ))
        self.assertUnrecoverable(raw, receipt.bundle_id)

    def test_v5_two_columns_wrong_at_same_slot_use_one_fault(self):
        receipt, raw = self._sealed_evidence(ZERO, edits={(2, 0): 1, (2, 1): 3})
        self.assertEqual(open_bundle(raw).fragments[2].values, (1, 3))
        self.assertRecovered(raw, receipt.bundle_id, ZERO, (2,))

    def test_v5_two_missing_slots_can_be_archived(self):
        receipt, raw = self._sealed_evidence(omit=(1, 4))
        self.assertEqual(open_bundle(raw).directory, (0, 2, 3, 5))
        self.assertUnrecoverable(raw, receipt.bundle_id)

    def test_v9_truncated_bundle_is_a_bundle_error(self):
        _, raw = self._sealed_evidence()
        with self.assertRaises(BundleError):
            recover(raw[:-1])

    def test_v9_same_length_payload_change_fails_digest(self):
        _, raw = self._sealed_evidence()
        self.assertEqual(raw.count(b'[5,[15,30]]'), 1)
        tampered = raw.replace(b'[5,[15,30]]', b'[5,[16,30]]')
        self.assertEqual(len(tampered), len(raw))
        with self.assertRaisesRegex(BundleError, 'digest mismatch'):
            recover(tampered)

    def test_v9_directory_content_mismatch_with_valid_digest(self):
        _, raw = self._sealed_evidence()
        envelope = json.loads(raw)
        envelope['body']['directory'].pop()
        canonical = json.dumps(envelope['body'], sort_keys=True, separators=(',', ':')).encode('utf-8')
        envelope['sha256'] = hashlib.sha256(canonical).hexdigest()
        with self.assertRaisesRegex(BundleError, 'directory and fragments disagree'):
            recover(json.dumps(envelope).encode('utf-8'))
