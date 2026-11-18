from contextlib import closing

from archive.bundle import open_bundle
from archive.catalog import ArchiveCatalog
from archive.commit import SealCommitError
from archive.export import ArchiveReadError, export
from archive.publication import seal
from receipt.intake import receive
from receipt.ledger import ReceiptLedger, UnknownBatchError
from review.recovery import recover
from source.history import get_revision
from source.store import RevisionStore
from support import LINEAR, LakeTestCase, LocalMirror


class ArchiveTests(LakeTestCase):
    def test_v6_new_revision_does_not_change_fixed_old_package(self):
        old = self.encode_day()
        mirror = LocalMirror(old)
        batch_id = receive(self.ledger, old.layout, mirror.handoff(omit=(1,)))
        receipt = seal(self.ledger, self.catalog, batch_id)
        first_export = export(self.catalog, receipt.bundle_id)
        newer = self.encode_day(((20, 40), (21, 42), (22, 44)), label='corrected')
        self.assertNotEqual(newer.layout.revision_id, old.layout.revision_id)
        mirror.close()
        with self.assertRaisesRegex(RuntimeError, 'offline'):
            mirror.handoff()

        raw = export(ArchiveCatalog(self.catalog.path), receipt.bundle_id)
        self.assertEqual(raw, first_export)
        bundle = open_bundle(raw)
        self.assertEqual(bundle.layout, old.layout)
        self.assertEqual(bundle.directory, (0, 2, 3, 4, 5))
        self.assertEqual(tuple(fragment.values for fragment in bundle.fragments), (
            (10, 20), (12, 24), (13, 26), (14, 28), (15, 30),
        ))
        report = recover(raw)
        self.assertEqual((report.bundle_id, report.rows, report.bad_slots), (receipt.bundle_id, LINEAR, ()))

    def test_v6_after_new_seal_both_snapshots_survive_reinitialization(self):
        corrected_rows = ((20, 40), (21, 42), (22, 44))
        revision_pairs = ((self.encode_day(), LINEAR), (self.encode_day(corrected_rows, label='r2'), corrected_rows))
        saved = []
        for encoded, expected_rows in revision_pairs:
            mirror = LocalMirror(encoded)
            batch_id = receive(self.ledger, encoded.layout, mirror.handoff())
            receipt = seal(self.ledger, self.catalog, batch_id)
            saved.append((encoded, expected_rows, receipt, export(self.catalog, receipt.bundle_id)))
            mirror.close()

        store = RevisionStore(self.store.path)
        ledger = ReceiptLedger(self.ledger.path)
        catalog = ArchiveCatalog(self.catalog.path)
        for database in (store, ledger, catalog):
            database.initialize()
            database.initialize()

        self.assertEqual(set(catalog.bundle_ids()), {receipt.bundle_id for _, _, receipt, _ in saved})
        for encoded, expected_rows, receipt, original_bytes in saved:
            with self.subTest(revision=encoded.layout.revision_id):
                self.assertEqual(get_revision(store, encoded.layout.revision_id).rows, expected_rows)
                self.assertEqual(ledger.get_batch(receipt.batch_id).received.fragments, encoded.fragments)
                self.assertEqual(catalog.find_by_batch(receipt.batch_id), receipt)
                raw = export(catalog, receipt.bundle_id)
                self.assertEqual(raw, original_bytes)
                self.assertEqual(open_bundle(raw).layout, encoded.layout)
                self.assertEqual(open_bundle(raw).fragments, encoded.fragments)
                report = recover(raw)
                self.assertEqual((report.bundle_id, report.rows, report.bad_slots), (receipt.bundle_id, expected_rows, ()))

    def test_v8_reopen_after_rollback_and_retry_once(self):
        encoded = self.encode_day()
        old_batch = receive(self.ledger, encoded.layout, encoded.fragments)
        old = seal(self.ledger, self.catalog, old_batch)
        old_bytes = export(self.catalog, old.bundle_id)
        new_batch = receive(self.ledger, encoded.layout, encoded.fragments[1:])
        observations = []

        def fail_before_commit():
            observer = ArchiveCatalog(self.catalog.path)
            observations.append((observer.bundle_ids(), observer.find_by_batch(new_batch)))
            raise OSError('write failed before commit')

        with self.assertRaisesRegex(SealCommitError, 'write failed before commit'):
            seal(self.ledger, self.catalog, new_batch, before_commit=fail_before_commit)
        self.assertEqual(observations, [((old.bundle_id,), None)])

        reopened = ArchiveCatalog(self.catalog.path)
        self.assertEqual(reopened.bundle_ids(), (old.bundle_id,))
        self.assertIsNone(reopened.find_by_batch(new_batch))
        self.assertEqual(export(reopened, old.bundle_id), old_bytes)
        with closing(reopened.connect()) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM bundle_payloads').fetchone()[0], 1)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM seal_receipts').fetchone()[0], 1)

        reopened_ledger = ReceiptLedger(self.ledger.path)
        retry = seal(reopened_ledger, reopened, new_batch)
        self.assertEqual(retry.batch_id, new_batch)
        self.assertEqual(reopened.find_by_batch(new_batch), retry)
        self.assertEqual(seal(reopened_ledger, reopened, new_batch), retry)
        self.assertEqual(set(reopened.bundle_ids()), {old.bundle_id, retry.bundle_id})
        self.assertEqual(open_bundle(export(reopened, retry.bundle_id)).directory, (1, 2, 3, 4, 5))
        self.assertEqual(export(reopened, old.bundle_id), old_bytes)

    def test_v8_unknown_batch_and_bundle_have_no_result(self):
        with self.assertRaises(UnknownBatchError):
            seal(self.ledger, self.catalog, 'unknown-batch')
        with self.assertRaises(ArchiveReadError):
            export(self.catalog, 'unknown-bundle')
        self.assertEqual(self.catalog.bundle_ids(), ())

    def test_export_rejects_saved_package_with_different_identity(self):
        encoded = self.encode_day()
        first_batch = receive(self.ledger, encoded.layout, encoded.fragments)
        second_batch = receive(self.ledger, encoded.layout, encoded.fragments[1:])
        first = seal(self.ledger, self.catalog, first_batch)
        second = seal(self.ledger, self.catalog, second_batch)
        other_bytes = export(self.catalog, second.bundle_id)
        with closing(self.catalog.connect()) as connection, connection:
            connection.execute(
                'UPDATE bundle_payloads SET bundle_bytes = ? WHERE bundle_id = ?', (other_bytes, first.bundle_id),
            )
        with self.assertRaisesRegex(ArchiveReadError, 'identity mismatch'):
            export(self.catalog, first.bundle_id)
        self.assertEqual(export(self.catalog, second.bundle_id), other_bytes)
