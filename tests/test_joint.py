import hashlib
import json
from contextlib import closing
from pathlib import Path

from archive.bundle import BundleError, JointBundle, open_bundle
from archive.catalog import ArchiveCatalog
from archive.commit import SealCommitError
from archive.export import ArchiveReadError, export
from archive.publication import seal, seal_joint
from encoding.encode import encode
from encoding.payload import Fragment
from receipt.intake import receive
from receipt.ledger import ReceiptLedger, UnknownBatchError
from review.recovery import recover, recover_joint
from source.revisions import record
from support import LINEAR, LakeTestCase, LocalMirror


SAMPLES = Path(__file__).resolve().parent.parent / 'samples' / 'joint_evidence.json'


def _joint_cases():
    return json.loads(SAMPLES.read_text(encoding='utf-8'))


def _joint_case(name):
    for case in _joint_cases():
        if case['case'] == name:
            return case
    raise KeyError(name)


class JointSampleTests(LakeTestCase):
    def _joint_from_case(self, case):
        revision_id = record(self.store, 'river-north/2026-06-12', case['case'], case['rows'])
        layout = encode(self.store, revision_id).layout
        original_batch = receive(self.ledger, layout, (Fragment(*entry) for entry in case['original']))
        original = seal(self.ledger, self.catalog, original_batch)
        supplement_batch = receive(self.ledger, layout, (Fragment(*entry) for entry in case['supplement']))
        joint = seal_joint(self.ledger, self.catalog, original.bundle_id, supplement_batch)
        return original, supplement_batch, joint, export(self.catalog, joint.bundle_id)

    def test_samples_match_expected_joint_report(self):
        for case in _joint_cases():
            with self.subTest(case=case['case']):
                original, supplement_batch, joint, raw = self._joint_from_case(case)
                bundle = open_bundle(raw)
                self.assertIsInstance(bundle, JointBundle)
                self.assertEqual(bundle.bundle_id, joint.bundle_id)
                self.assertEqual(bundle.original_bundle_id, original.bundle_id)
                self.assertEqual(bundle.supplement_batch_id, supplement_batch)
                report = recover_joint(raw)
                self.assertEqual(report.status, case['expected']['status'])
                self.assertEqual((report.bundle_id, report.original_bundle_id, report.supplement_batch_id),
                                 (joint.bundle_id, original.bundle_id, supplement_batch))
                if case['expected']['status'] == 'recovered':
                    self.assertEqual([list(row) for row in report.rows], case['expected']['rows'])
                    self.assertEqual(list(report.bad_slots), case['expected']['bad_slots'])
                    self.assertEqual(
                        [[source, slot, list(values)] for source, slot, values in report.disagreements],
                        case['expected']['disagreements'],
                    )
                else:
                    for attribute in ('rows', 'bad_slots', 'disagreements'):
                        self.assertFalse(hasattr(report, attribute))

    def test_complement_bundle_keeps_both_sources_and_origins(self):
        case = _joint_case('complement')
        original, supplement_batch, joint, raw = self._joint_from_case(case)
        bundle = open_bundle(raw)
        self.assertEqual(bundle.original_directory, (0, 1, 2, 3))
        self.assertEqual(bundle.supplement_directory, (2, 3, 4, 5))
        self.assertEqual(
            tuple((fragment.slot, fragment.values) for fragment in bundle.original),
            tuple((slot, tuple(values)) for slot, values in sorted(case['original'])),
        )
        self.assertEqual(
            tuple((fragment.slot, fragment.values) for fragment in bundle.supplement),
            tuple((slot, tuple(values)) for slot, values in sorted(case['supplement'])),
        )
        self.assertEqual(open_bundle(raw).layout.coordinates, (0, 1, 2, 3, 4, 5))

    def test_same_values_from_both_sources_are_both_retained(self):
        encoded = self.encode_day()
        batch_id = receive(self.ledger, encoded.layout, encoded.fragments)
        original = seal(self.ledger, self.catalog, batch_id)
        joint = seal_joint(self.ledger, self.catalog, original.bundle_id, batch_id)
        raw = export(self.catalog, joint.bundle_id)
        bundle = open_bundle(raw)
        self.assertEqual(bundle.original, bundle.supplement)
        self.assertEqual(bundle.original_directory, (0, 1, 2, 3, 4, 5))
        report = recover_joint(raw)
        self.assertEqual(report.status, 'recovered')
        self.assertEqual(report.rows, LINEAR)
        self.assertEqual(report.bad_slots, ())
        self.assertEqual(report.disagreements, ())


class JointSealingTests(LakeTestCase):
    def _ordinary(self, encoded, *, omit=(), edits=None):
        mirror = LocalMirror(encoded)
        batch_id = receive(self.ledger, encoded.layout, mirror.handoff(omit=omit, edits=edits))
        receipt = seal(self.ledger, self.catalog, batch_id)
        return batch_id, receipt

    def test_replay_returns_first_receipt_and_bytes(self):
        batch_id, receipt = self._ordinary(self.encode_day(), omit=(1,))
        first = seal_joint(self.ledger, self.catalog, receipt.bundle_id, batch_id)
        first_bytes = export(self.catalog, first.bundle_id)
        again = seal_joint(self.ledger, self.catalog, receipt.bundle_id, batch_id)
        self.assertEqual(again, first)
        self.assertEqual(export(self.catalog, again.bundle_id), first_bytes)
        self.assertEqual(len(self.catalog.joint_bundle_ids()), 1)
        self.assertEqual(self.catalog.find_joint(receipt.bundle_id, batch_id), first)

    def test_reopen_archive_keeps_joint_bundle_and_old_ordinary_queries(self):
        batch_id, receipt = self._ordinary(self.encode_day(), omit=(1,))
        joint = seal_joint(self.ledger, self.catalog, receipt.bundle_id, batch_id)
        raw = export(self.catalog, joint.bundle_id)
        ordinary_bytes = export(self.catalog, receipt.bundle_id)

        reopened = ArchiveCatalog(self.catalog.path)
        reopened.initialize()
        ledger = ReceiptLedger(self.ledger.path)
        ledger.initialize()
        self.assertIn(joint.bundle_id, reopened.bundle_ids())
        self.assertIn(receipt.bundle_id, reopened.bundle_ids())
        self.assertEqual(export(reopened, joint.bundle_id), raw)
        self.assertEqual(export(reopened, receipt.bundle_id), ordinary_bytes)
        self.assertEqual(reopened.find_by_batch(batch_id), receipt)
        self.assertEqual(seal(ledger, reopened, batch_id), receipt)
        self.assertEqual(seal_joint(ledger, reopened, receipt.bundle_id, batch_id), joint)
        self.assertEqual(open_bundle(export(reopened, receipt.bundle_id)).directory, (0, 2, 3, 4, 5))
        self.assertEqual(recover(export(reopened, receipt.bundle_id)).rows, LINEAR)

    def test_supplement_can_also_be_sealed_ordinarily(self):
        encoded = self.encode_day()
        supplement_batch = receive(self.ledger, encoded.layout, encoded.fragments[1:])
        ordinary_supplement = seal(self.ledger, self.catalog, supplement_batch)
        original_batch = receive(self.ledger, encoded.layout, encoded.fragments)
        original = seal(self.ledger, self.catalog, original_batch)
        joint = seal_joint(self.ledger, self.catalog, original.bundle_id, supplement_batch)
        self.assertEqual(self.catalog.find_by_batch(supplement_batch), ordinary_supplement)
        self.assertEqual(recover(export(self.catalog, ordinary_supplement.bundle_id)).rows, LINEAR)
        report = recover_joint(export(self.catalog, joint.bundle_id))
        self.assertEqual(report.status, 'recovered')
        self.assertNotEqual(joint.bundle_id, ordinary_supplement.bundle_id)

    def test_v1_recovery_rejects_a_joint_bundle(self):
        batch_id, receipt = self._ordinary(self.encode_day())
        joint = seal_joint(self.ledger, self.catalog, receipt.bundle_id, batch_id)
        with self.assertRaises(BundleError):
            recover(export(self.catalog, joint.bundle_id))

    def test_same_supplement_with_another_original_makes_another_bundle(self):
        _, first = self._ordinary(self.encode_day(), omit=(1,))
        _, second = self._ordinary(self.encode_day(), omit=(1, 4))
        supplement_encoded = self.encode_day()
        supplement_batch = receive(self.ledger, supplement_encoded.layout, supplement_encoded.fragments)
        first_joint = seal_joint(self.ledger, self.catalog, first.bundle_id, supplement_batch)
        second_joint = seal_joint(self.ledger, self.catalog, second.bundle_id, supplement_batch)
        self.assertNotEqual(first_joint.bundle_id, second_joint.bundle_id)
        first_bundle = open_bundle(export(self.catalog, first_joint.bundle_id))
        second_bundle = open_bundle(export(self.catalog, second_joint.bundle_id))
        self.assertEqual(first_bundle.supplement, second_bundle.supplement)
        self.assertNotEqual(first_bundle.original, second_bundle.original)
        self.assertEqual(set(self.catalog.joint_bundle_ids()),
                         {first_joint.bundle_id, second_joint.bundle_id})

    def test_unknown_sources_and_wrong_kinds_leave_no_result(self):
        batch_id, receipt = self._ordinary(self.encode_day())
        with self.assertRaises(ArchiveReadError):
            seal_joint(self.ledger, self.catalog, 'unknown-bundle', batch_id)
        with self.assertRaises(UnknownBatchError):
            seal_joint(self.ledger, self.catalog, receipt.bundle_id, 'unknown-batch')
        joint = seal_joint(self.ledger, self.catalog, receipt.bundle_id, batch_id)
        with self.assertRaises(ValueError):
            seal_joint(self.ledger, self.catalog, joint.bundle_id, batch_id)
        self.assertEqual(self.catalog.joint_bundle_ids(), (joint.bundle_id,))

    def test_layout_mismatch_is_rejected_without_result(self):
        _, receipt = self._ordinary(self.encode_day())
        other = self.encode_day(((1, 2, 3), (4, 5, 6), (7, 8, 9)), label='wide')
        other_batch = receive(self.ledger, other.layout, other.fragments)
        with self.assertRaises(ValueError):
            seal_joint(self.ledger, self.catalog, receipt.bundle_id, other_batch)
        self.assertEqual(self.catalog.joint_bundle_ids(), ())
        self.assertEqual(self.catalog.bundle_ids(), (receipt.bundle_id,))

    def test_same_width_on_another_day_is_still_a_layout_mismatch(self):
        _, receipt = self._ordinary(self.encode_day())
        other_revision = record(self.store, 'river-north/2026-06-13', 'r1', LINEAR)
        other = encode(self.store, other_revision)
        other_batch = receive(self.ledger, other.layout, other.fragments)
        with self.assertRaises(ValueError):
            seal_joint(self.ledger, self.catalog, receipt.bundle_id, other_batch)
        self.assertEqual(self.catalog.joint_bundle_ids(), ())

    def test_replay_does_not_call_before_commit(self):
        batch_id, receipt = self._ordinary(self.encode_day())
        joint = seal_joint(self.ledger, self.catalog, receipt.bundle_id, batch_id)

        def unexpected_hook():
            raise AssertionError('replay must not run the commit hook')

        self.assertEqual(
            seal_joint(self.ledger, self.catalog, receipt.bundle_id, batch_id, before_commit=unexpected_hook),
            joint,
        )

    def test_failed_commit_rolls_back_and_retry_succeeds(self):
        batch_id, receipt = self._ordinary(self.encode_day(), omit=(1,))
        observations = []

        def fail_before_commit():
            observer = ArchiveCatalog(self.catalog.path)
            observations.append((observer.joint_bundle_ids(), observer.find_joint(receipt.bundle_id, batch_id)))
            raise OSError('joint write failed before commit')

        with self.assertRaisesRegex(SealCommitError, 'joint write failed before commit'):
            seal_joint(self.ledger, self.catalog, receipt.bundle_id, batch_id, before_commit=fail_before_commit)
        self.assertEqual(observations, [((), None)])

        reopened = ArchiveCatalog(self.catalog.path)
        self.assertEqual(reopened.joint_bundle_ids(), ())
        self.assertIsNone(reopened.find_joint(receipt.bundle_id, batch_id))
        with closing(reopened.connect()) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM joint_directory').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM joint_receipts').fetchone()[0], 0)
        retry = seal_joint(ReceiptLedger(self.ledger.path), reopened, receipt.bundle_id, batch_id)
        retry_bytes = export(reopened, retry.bundle_id)
        self.assertEqual(seal_joint(ReceiptLedger(self.ledger.path), reopened, receipt.bundle_id, batch_id), retry)
        self.assertEqual(export(reopened, retry.bundle_id), retry_bytes)
        self.assertEqual(reopened.joint_bundle_ids(), (retry.bundle_id,))


class JointRecoverySemanticsTests(LakeTestCase):
    def _joint(self, rows, original, supplement):
        revision_id = record(self.store, 'river-north/2026-06-12', 'joint', rows)
        layout = encode(self.store, revision_id).layout
        original_batch = receive(self.ledger, layout, (Fragment(*entry) for entry in original))
        original_receipt = seal(self.ledger, self.catalog, original_batch)
        supplement_batch = receive(self.ledger, layout, (Fragment(*entry) for entry in supplement))
        joint = seal_joint(self.ledger, self.catalog, original_receipt.bundle_id, supplement_batch)
        return recover_joint(export(self.catalog, joint.bundle_id))

    def test_two_bad_slots_are_unrecoverable_even_though_receivable(self):
        full = [[slot, [0]] for slot in range(6)]
        original = [list(entry) for entry in full]
        original[4][1] = [99]
        original[5][1] = [99]
        supplement = [list(entry) for entry in full]
        supplement[4][1] = [99]
        supplement[5][1] = [99]
        report = self._joint([[0], [0], [0]], original, supplement)
        self.assertEqual(report.status, 'unrecoverable')
        self.assertFalse(hasattr(report, 'bad_slots'))

    def test_bad_slot_counts_physical_slots_not_source_vectors(self):
        full = [[slot, [0]] for slot in range(6)]
        original = [list(entry) for entry in full]
        original[4][1] = [99]
        supplement = [list(entry) for entry in full]
        supplement[4][1] = [99]
        report = self._joint([[0], [0], [0]], original, supplement)
        self.assertEqual(report.status, 'recovered')
        self.assertEqual(report.bad_slots, (4,))
        self.assertEqual(report.disagreements, (
            ('original', 4, (99,)),
            ('supplement', 4, (99,)),
        ))

    def test_disagreements_are_per_source_and_ordered(self):
        full = [[slot, [0]] for slot in range(6)]
        original = [list(entry) for entry in full]
        original[1][1] = [7]
        supplement = [list(entry) for entry in full]
        supplement[2][1] = [8]
        supplement[5][1] = [9]
        report = self._joint([[0], [0], [0]], original, supplement)
        self.assertEqual(report.status, 'recovered')
        self.assertEqual(report.bad_slots, ())
        self.assertEqual(report.disagreements, (
            ('original', 1, (7,)),
            ('supplement', 2, (8,)),
            ('supplement', 5, (9,)),
        ))

    def test_missing_slot_carries_no_disagreement(self):
        report = self._joint(
            [[10], [11], [12]],
            [[0, [10]], [1, [11]], [2, [12]], [3, [13]], [4, [14]]],
            [[0, [10]], [2, [12]], [3, [13]], [4, [14]], [5, [15]]],
        )
        self.assertEqual(report.status, 'recovered')
        self.assertEqual(report.rows, ((10,), (11,), (12,)))
        self.assertEqual(report.bad_slots, ())
        self.assertEqual(report.disagreements, ())

    def test_two_missing_slots_across_shifts_are_unrecoverable(self):
        report = self._joint(
            [[10], [11], [12]],
            [[0, [10]], [1, [11]], [2, [12]], [3, [13]]],
            [[0, [10]], [1, [11]], [2, [12]], [3, [13]]],
        )
        self.assertEqual(report.status, 'unrecoverable')

    def test_zero_width_joint_counts_missing_physical_slots(self):
        full = [[slot, []] for slot in range(6)]
        report = self._joint([[], [], []], full, [list(entry) for entry in full])
        self.assertEqual(report.status, 'recovered')
        self.assertEqual(report.rows, ((), (), ()))
        self.assertEqual(report.bad_slots, ())
        self.assertEqual(report.disagreements, ())

        partial = [list(entry) for entry in full[:5]]
        report = self._joint([[], [], []], partial, [list(entry) for entry in full])
        self.assertEqual(report.status, 'recovered')

    def test_zero_width_two_common_missing_is_unrecoverable(self):
        report = self._joint(
            [[], [], []],
            [[2, []], [0, []], [1, []]],
            [[1, []], [2, []], [3, []]],
        )
        self.assertEqual(report.status, 'unrecoverable')

    def test_received_vector_supports_candidate_even_if_other_source_differs(self):
        report = self._joint(
            [[5], [6], [7]],
            [[0, [5]], [1, [6]], [2, [7]], [3, [8]], [4, [9]], [5, [10]]],
            [[0, [5]], [1, [6]], [2, [7]], [3, [8]], [4, [9]], [5, [11]]],
        )
        self.assertEqual(report.status, 'recovered')
        self.assertEqual(report.rows, ((5,), (6,), (7,)))
        self.assertEqual(report.bad_slots, ())
        self.assertEqual(report.disagreements, (('supplement', 5, (11,)),))


class JointBundleValidationTests(LakeTestCase):
    def _joint_raw(self):
        encoded = self.encode_day()
        batch_id = receive(self.ledger, encoded.layout, encoded.fragments)
        receipt = seal(self.ledger, self.catalog, batch_id)
        joint = seal_joint(self.ledger, self.catalog, receipt.bundle_id, batch_id)
        return joint, export(self.catalog, joint.bundle_id)

    @staticmethod
    def _redigest(envelope):
        body = envelope['body']
        canonical = json.dumps(body, sort_keys=True, separators=(',', ':')).encode('utf-8')
        envelope['sha256'] = hashlib.sha256(canonical).hexdigest()
        return json.dumps(envelope, sort_keys=True, separators=(',', ':')).encode('utf-8')

    def test_reject_v1_bundle_and_non_bytes(self):
        encoded = self.encode_day()
        batch_id = receive(self.ledger, encoded.layout, encoded.fragments)
        receipt = seal(self.ledger, self.catalog, batch_id)
        with self.assertRaises(BundleError):
            recover_joint(export(self.catalog, receipt.bundle_id))
        with self.assertRaises(BundleError):
            recover_joint('not bytes')

    def test_directory_mismatch_with_valid_digest_is_rejected(self):
        _, raw = self._joint_raw()
        envelope = json.loads(raw)
        envelope['body']['supplement']['directory'].pop()
        with self.assertRaisesRegex(BundleError, 'directory and fragments disagree'):
            recover_joint(self._redigest(envelope))

    def test_unsorted_or_duplicate_directories_are_rejected(self):
        _, raw = self._joint_raw()
        envelope = json.loads(raw)
        fragments = envelope['body']['original']['fragments']
        envelope['body']['original']['fragments'] = list(reversed(fragments))
        with self.assertRaisesRegex(BundleError, 'directory and fragments disagree'):
            recover_joint(self._redigest(envelope))

        envelope = json.loads(raw)
        envelope['body']['original']['directory'] = [0, 0, 1, 2, 3, 4, 5]
        with self.assertRaisesRegex(BundleError, 'unique and in ascending order'):
            recover_joint(self._redigest(envelope))

    def test_bad_values_and_missing_fields_are_rejected(self):
        _, raw = self._joint_raw()
        envelope = json.loads(raw)
        envelope['body']['supplement']['fragments'][0][1][0] = 257
        with self.assertRaises(BundleError):
            recover_joint(self._redigest(envelope))

        envelope = json.loads(raw)
        envelope['body']['original']['fragments'][0][1].pop()
        with self.assertRaises(BundleError):
            recover_joint(self._redigest(envelope))

        envelope = json.loads(raw)
        del envelope['body']['original_bundle_id']
        with self.assertRaisesRegex(BundleError, 'invalid joint bundle fields'):
            recover_joint(self._redigest(envelope))

    def test_tampered_payload_with_stale_digest_is_rejected(self):
        _, raw = self._joint_raw()
        tampered = raw.replace(b'[5,[15,30]]', b'[5,[16,30]]')
        self.assertEqual(len(tampered), len(raw))
        with self.assertRaisesRegex(BundleError, 'digest mismatch'):
            recover_joint(tampered)

    def test_layout_mismatch_inside_bundle_is_rejected(self):
        _, raw = self._joint_raw()
        envelope = json.loads(raw)
        envelope['body']['layout']['coordinates'] = [0, 1, 2, 3, 4, 5, 6]
        with self.assertRaises(BundleError):
            recover_joint(self._redigest(envelope))

    def test_catalog_identity_mismatch_is_rejected_on_export(self):
        joint, _ = self._joint_raw()
        other = seal(self.ledger, self.catalog, joint.supplement_batch_id)
        other_bytes = export(self.catalog, other.bundle_id)
        with closing(self.catalog.connect()) as connection, connection:
            connection.execute(
                'UPDATE bundle_payloads SET bundle_bytes = ? WHERE bundle_id = ?',
                (other_bytes, joint.bundle_id),
            )
        with self.assertRaisesRegex(ArchiveReadError, 'identity mismatch'):
            export(self.catalog, joint.bundle_id)

    def test_joint_payload_under_ordinary_catalog_row_is_rejected(self):
        joint, _ = self._joint_raw()
        encoded = self.encode_day(label='ordinary')
        batch_id = receive(self.ledger, encoded.layout, encoded.fragments)
        ordinary = seal(self.ledger, self.catalog, batch_id)
        joint_bytes = export(self.catalog, joint.bundle_id)
        with closing(self.catalog.connect()) as connection, connection:
            connection.execute(
                'UPDATE bundle_payloads SET bundle_bytes = ? WHERE bundle_id = ?',
                (joint_bytes, ordinary.bundle_id),
            )
        with self.assertRaisesRegex(ArchiveReadError, 'identity mismatch'):
            export(self.catalog, ordinary.bundle_id)
