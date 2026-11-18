from dataclasses import replace

from archive.publication import seal
from encoding.payload import Fragment
from receipt.intake import receive
from receipt.validate import ReceiveValidationError
from support import ZERO, LakeTestCase


class ReceiptTests(LakeTestCase):
    def test_v7_conflicting_slot_rejects_whole_delivery(self):
        encoded = self.encode_day()
        with self.assertRaisesRegex(ReceiveValidationError, 'slot 2'):
            receive(self.ledger, encoded.layout, [encoded.fragments[2], Fragment(2, (0, 0))])
        self.assertEqual(self.ledger.batch_ids(), ())
        self.assertEqual(self.catalog.bundle_ids(), ())

    def test_v7_late_conflict_leaves_no_partial_batch(self):
        encoded = self.encode_day()
        valid = tuple(encoded.fragments[slot] for slot in (0, 2, 3))
        delivery = iter((*valid, Fragment(2, (99, 24))))
        with self.assertRaisesRegex(ReceiveValidationError, 'slot 2'):
            receive(self.ledger, encoded.layout, delivery)
        self.assertEqual(self.ledger.batch_ids(), ())
        self.assertEqual(self.catalog.bundle_ids(), ())

        batch_id = receive(self.ledger, encoded.layout, (*valid, valid[1]))
        self.assertEqual(self.ledger.batch_ids(), (batch_id,))
        self.assertEqual(self.ledger.get_batch(batch_id).received.fragments, valid)
        self.assertEqual(seal(self.ledger, self.catalog, batch_id).batch_id, batch_id)

    def test_v7_bad_slots_payloads_and_layouts_are_rejected(self):
        encoded = self.encode_day()
        bad_fragments = (
            Fragment(6, (0, 0)), Fragment(True, (0, 0)), Fragment(2, (0,)),
            Fragment(2, (0, 257)), Fragment(2, (-1, 0)), Fragment(2, (False, 0)),
            Fragment(2, (None, 0)), Fragment(2, (0.0, 0)), Fragment(2, '00'),
            Fragment(2, None), (2, (0, 0)),
        )
        for fragment in bad_fragments:
            with self.subTest(fragment=fragment), self.assertRaises(ReceiveValidationError):
                receive(self.ledger, encoded.layout, (encoded.fragments[0], fragment))
        for layout in (replace(encoded.layout, width=-1), replace(encoded.layout, coordinates=(0, 1, 2, 3, 4, 6))):
            with self.subTest(layout=layout), self.assertRaises(ReceiveValidationError):
                receive(self.ledger, layout, encoded.fragments)
        self.assertEqual(self.ledger.batch_ids(), ())

    def test_v7_reordered_replay_distinguishes_zero_from_absence(self):
        encoded = self.encode_day(ZERO)
        first = [encoded.fragments[slot] for slot in (0, 3, 2)]
        replay = [encoded.fragments[slot] for slot in (2, 0, 3, 0)]
        batch_id = receive(self.ledger, encoded.layout, first)
        self.assertEqual(receive(self.ledger, encoded.layout, replay), batch_id)
        self.assertEqual(self.ledger.batch_ids(), (batch_id,))
        batch = self.ledger.get_batch(batch_id)
        self.assertEqual(batch.received.coordinates, (0, 2, 3))
        self.assertEqual(tuple(fragment.values for fragment in batch.received.fragments), ((0, 0),) * 3)

        with_zero_at_one = receive(self.ledger, encoded.layout, (*first, encoded.fragments[1]))
        self.assertNotEqual(batch_id, with_zero_at_one)
        self.assertEqual(self.ledger.get_batch(with_zero_at_one).received.coordinates, (0, 1, 2, 3))
        self.assertEqual(set(self.ledger.batch_ids()), {batch_id, with_zero_at_one})
