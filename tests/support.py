import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from archive.catalog import ArchiveCatalog
from encoding.encode import EncodedRevision, encode
from encoding.payload import Fragment
from receipt.ledger import ReceiptLedger
from source.revisions import record
from source.store import RevisionStore


DAY = 'river-north/2026-06-12'
LINEAR = ((10, 20), (11, 22), (12, 24))
ZERO = ((0, 0), (0, 0), (0, 0))


class LocalMirror:
    def __init__(self, encoded: EncodedRevision) -> None:
        self._fragments: tuple[Fragment, ...] | None = encoded.fragments

    def handoff(self, *, omit=(), edits=None) -> tuple[Fragment, ...]:
        if self._fragments is None:
            raise RuntimeError('mirror is offline')
        changes = {} if edits is None else edits
        fragments = []
        for fragment in reversed(self._fragments):
            if fragment.slot in omit:
                continue
            values = tuple(changes.get((fragment.slot, column), value) for column, value in enumerate(fragment.values))
            fragments.append(Fragment(fragment.slot, values))
        return tuple(fragments)

    def close(self) -> None:
        self._fragments = None


class LakeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        directory = TemporaryDirectory(prefix='hydrology-tests-')
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.store = RevisionStore(root / 'source.sqlite3')
        self.ledger = ReceiptLedger(root / 'receipt.sqlite3')
        self.catalog = ArchiveCatalog(root / 'archive.sqlite3')
        for database in (self.store, self.ledger, self.catalog):
            database.initialize()

    def encode_day(self, rows=LINEAR, *, label='r1', day=DAY) -> EncodedRevision:
        revision_id = record(self.store, day, label, rows)
        return encode(self.store, revision_id)
