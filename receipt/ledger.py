import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from encoding.layout import Layout, layout_from_document
from encoding.payload import freeze_slot_payload
from receipt.identity import canonical_batch_key
from receipt.slots import ReceivedSlots


class UnknownBatchError(LookupError):
    pass


@dataclass(frozen=True)
class ReceiptBatch:
    batch_id: str
    layout: Layout
    received: ReceivedSlots


class ReceiptLedger:
    def __init__(self, path: str | Path) -> None:
        self.path = path

    def initialize(self) -> None:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('''
                CREATE TABLE IF NOT EXISTS receipt_batches (
                    batch_id TEXT PRIMARY KEY,
                    evidence_key TEXT NOT NULL UNIQUE
                )
            ''')

    def record_batch(self, layout: Layout, received: ReceivedSlots) -> str:
        evidence = canonical_batch_key(layout, received)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            existing = connection.execute(
                'SELECT batch_id FROM receipt_batches WHERE evidence_key = ?', (evidence,),
            ).fetchone()
            if existing is not None:
                return existing[0]

            batch_id = f'batch-{uuid4().hex}'
            connection.execute(
                'INSERT INTO receipt_batches (batch_id, evidence_key) VALUES (?, ?)',
                (batch_id, evidence),
            )
        return batch_id

    def get_batch(self, batch_id: str) -> ReceiptBatch:
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute(
                'SELECT evidence_key FROM receipt_batches WHERE batch_id = ?', (batch_id,),
            ).fetchone()
        if row is None:
            raise UnknownBatchError(batch_id)
        evidence = json.loads(row[0])
        layout = layout_from_document(evidence['layout'])
        fragments = tuple(
            freeze_slot_payload(layout, slot, values) for slot, values in evidence['fragments']
        )
        return ReceiptBatch(batch_id, layout, ReceivedSlots(fragments))

    def batch_ids(self) -> tuple[str, ...]:
        with closing(sqlite3.connect(self.path)) as connection:
            return tuple(row[0] for row in connection.execute('SELECT batch_id FROM receipt_batches ORDER BY batch_id'))
