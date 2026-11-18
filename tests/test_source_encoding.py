from encoding.encode import encode
from encoding.layout import SLOT_COORDINATES
from source.history import UnknownRevisionError, get_revision
from source.observations import ObservationError
from source.revisions import record
from source.schema import RevisionConflictError
from support import DAY, LINEAR, LakeTestCase


class SourceEncodingTests(LakeTestCase):
    def test_v1_linear_encoding_preserves_source_slots(self):
        revision_id = record(self.store, DAY, 'r1', LINEAR)
        encoded = encode(self.store, revision_id)
        self.assertEqual(encoded.layout.revision_id, revision_id)
        self.assertEqual(encoded.layout.day_key, DAY)
        self.assertEqual(encoded.layout.width, 2)
        self.assertEqual(encoded.layout.coordinates, SLOT_COORDINATES)
        self.assertEqual(tuple((fragment.slot, fragment.values) for fragment in encoded.fragments), (
            (0, (10, 20)), (1, (11, 22)), (2, (12, 24)),
            (3, (13, 26)), (4, (14, 28)), (5, (15, 30)),
        ))

    def test_v1_quadratic_wrap_preserves_column_order(self):
        encoded = self.encode_day(((256, 10), (2, 13), (7, 16)))
        # Independent formulas: 256 + 2x + x² modulo 257, and 10 + 3x.
        self.assertEqual(tuple(fragment.values for fragment in encoded.fragments), (
            (256, 10), (2, 13), (7, 16), (14, 19), (23, 22), (34, 25),
        ))

    def test_v1_unknown_revision_has_no_encoding(self):
        with self.assertRaises(UnknownRevisionError):
            encode(self.store, 'unknown')

    def test_v2_conflicting_report_keeps_original_snapshot(self):
        revision_id = record(self.store, DAY, 'r1', LINEAR)
        with self.assertRaises(RevisionConflictError):
            record(self.store, DAY, 'r1', ((30, 40), (31, 42), (32, 44)))
        self.assertEqual(get_revision(self.store, revision_id).rows, LINEAR)
        self.assertEqual(encode(self.store, revision_id).fragments[5].values, (15, 30))

    def test_v2_identical_replay_and_input_copy(self):
        submitted = [list(row) for row in LINEAR]
        revision_id = record(self.store, DAY, 'r1', submitted)
        submitted[0][0] = 99
        self.assertEqual(record(self.store, DAY, 'r1', LINEAR), revision_id)
        self.assertEqual(get_revision(self.store, revision_id).rows, LINEAR)

    def test_v2_same_label_on_another_day_is_a_separate_revision(self):
        other_day = 'river-north/2026-06-13'
        other_rows = ((40, 1), (41, 2), (42, 3))
        first = record(self.store, DAY, 'r1', LINEAR)
        second = record(self.store, other_day, 'r1', other_rows)
        self.assertNotEqual(first, second)
        self.assertEqual(get_revision(self.store, first).rows, LINEAR)
        second_snapshot = get_revision(self.store, second)
        self.assertEqual(second_snapshot.key.day_key, other_day)
        self.assertEqual(second_snapshot.rows, other_rows)
        self.assertEqual(encode(self.store, second).fragments[5].values, (45, 6))

    def test_invalid_observations_do_not_register_a_snapshot(self):
        invalid_rows = (
            ((0,), (0,)), ((0,), (0, 1), (0,)), ((True,), (0,), (0,)),
            ((None,), (0,), (0,)), ((0.0,), (0,), (0,)), ((257,), (0,), (0,)),
            ((-1,), (0,), (0,)), ('0', (0,), (0,)),
        )
        for rows in invalid_rows:
            with self.subTest(rows=rows), self.assertRaises(ObservationError):
                record(self.store, DAY, 'r1', rows)
        with self.assertRaises(ValueError):
            record(self.store, ' ', 'r1', LINEAR)
        revision_id = record(self.store, DAY, 'r1', LINEAR)
        self.assertEqual(get_revision(self.store, revision_id).rows, LINEAR)
