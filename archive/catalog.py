import sqlite3
from contextlib import closing, nullcontext
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CatalogEntry:
    bundle_id: str
    batch_id: str
    day_key: str
    revision_id: str
    bundle_bytes: bytes


@dataclass(frozen=True)
class SealReceipt:
    batch_id: str
    bundle_id: str
    receipt_id: str


@dataclass(frozen=True)
class JointCatalogEntry:
    bundle_id: str
    original_bundle_id: str
    supplement_batch_id: str
    day_key: str
    revision_id: str
    bundle_bytes: bytes


@dataclass(frozen=True)
class JointSealReceipt:
    original_bundle_id: str
    supplement_batch_id: str
    bundle_id: str
    receipt_id: str


class ArchiveCatalog:
    def __init__(self, path: str | Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        try:
            connection.execute('PRAGMA foreign_keys = ON')
        except sqlite3.Error:
            connection.close()
            raise
        return connection

    def initialize(self) -> None:
        with closing(self.connect()) as connection, connection:
            connection.execute('BEGIN')
            connection.execute('''
                CREATE TABLE IF NOT EXISTS bundle_payloads (
                    bundle_id TEXT PRIMARY KEY,
                    bundle_bytes BLOB NOT NULL
                )
            ''')
            connection.execute('''
                CREATE TABLE IF NOT EXISTS archive_directory (
                    bundle_id TEXT PRIMARY KEY REFERENCES bundle_payloads (bundle_id),
                    batch_id TEXT NOT NULL UNIQUE,
                    day_key TEXT NOT NULL,
                    revision_id TEXT NOT NULL
                )
            ''')
            connection.execute('''
                CREATE TABLE IF NOT EXISTS seal_receipts (
                    receipt_id TEXT PRIMARY KEY,
                    bundle_id TEXT NOT NULL UNIQUE REFERENCES archive_directory (bundle_id)
                )
            ''')
            connection.execute('''
                CREATE TABLE IF NOT EXISTS joint_directory (
                    bundle_id TEXT PRIMARY KEY REFERENCES bundle_payloads (bundle_id),
                    original_bundle_id TEXT NOT NULL,
                    supplement_batch_id TEXT NOT NULL,
                    day_key TEXT NOT NULL,
                    revision_id TEXT NOT NULL,
                    UNIQUE (original_bundle_id, supplement_batch_id)
                )
            ''')
            connection.execute('''
                CREATE TABLE IF NOT EXISTS joint_receipts (
                    receipt_id TEXT PRIMARY KEY,
                    bundle_id TEXT NOT NULL UNIQUE REFERENCES joint_directory (bundle_id)
                )
            ''')

    def find_by_batch(self, batch_id: str, *, connection: sqlite3.Connection | None = None) -> SealReceipt | None:
        session = closing(self.connect()) if connection is None else nullcontext(connection)
        with session as active:
            row = active.execute('''
                SELECT directory.batch_id, directory.bundle_id, receipts.receipt_id
                FROM archive_directory AS directory
                JOIN seal_receipts AS receipts USING (bundle_id)
                WHERE directory.batch_id = ?
            ''', (batch_id,)).fetchone()
        return None if row is None else SealReceipt(*row)

    def read_by_bundle(self, bundle_id: str) -> CatalogEntry | None:
        with closing(self.connect()) as connection:
            row = connection.execute('''
                SELECT directory.bundle_id, directory.batch_id, directory.day_key,
                       directory.revision_id, payload.bundle_bytes
                FROM archive_directory AS directory
                JOIN bundle_payloads AS payload USING (bundle_id)
                JOIN seal_receipts AS receipts USING (bundle_id)
                WHERE directory.bundle_id = ?
            ''', (bundle_id,)).fetchone()
        return None if row is None else CatalogEntry(*row)

    def find_joint(
        self,
        original_bundle_id: str,
        supplement_batch_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> JointSealReceipt | None:
        session = closing(self.connect()) if connection is None else nullcontext(connection)
        with session as active:
            row = active.execute('''
                SELECT directory.original_bundle_id, directory.supplement_batch_id,
                       directory.bundle_id, receipts.receipt_id
                FROM joint_directory AS directory
                JOIN joint_receipts AS receipts USING (bundle_id)
                WHERE directory.original_bundle_id = ? AND directory.supplement_batch_id = ?
            ''', (original_bundle_id, supplement_batch_id)).fetchone()
        return None if row is None else JointSealReceipt(*row)

    def read_joint_by_bundle(self, bundle_id: str) -> JointCatalogEntry | None:
        with closing(self.connect()) as connection:
            row = connection.execute('''
                SELECT directory.bundle_id, directory.original_bundle_id,
                       directory.supplement_batch_id, directory.day_key,
                       directory.revision_id, payload.bundle_bytes
                FROM joint_directory AS directory
                JOIN bundle_payloads AS payload USING (bundle_id)
                JOIN joint_receipts AS receipts USING (bundle_id)
                WHERE directory.bundle_id = ?
            ''', (bundle_id,)).fetchone()
        return None if row is None else JointCatalogEntry(*row)

    def stage_publication(self, connection: sqlite3.Connection, entry: CatalogEntry, receipt: SealReceipt) -> None:
        if (entry.bundle_id, entry.batch_id) != (receipt.bundle_id, receipt.batch_id):
            raise ValueError('receipt identifies a different publication')
        connection.execute(
            'INSERT INTO bundle_payloads (bundle_id, bundle_bytes) VALUES (?, ?)',
            (entry.bundle_id, entry.bundle_bytes),
        )
        connection.execute('''
            INSERT INTO archive_directory (bundle_id, batch_id, day_key, revision_id) VALUES (?, ?, ?, ?)
        ''', (entry.bundle_id, entry.batch_id, entry.day_key, entry.revision_id))
        connection.execute(
            'INSERT INTO seal_receipts (receipt_id, bundle_id) VALUES (?, ?)',
            (receipt.receipt_id, receipt.bundle_id),
        )

    def stage_joint(self, connection: sqlite3.Connection, entry: JointCatalogEntry, receipt: JointSealReceipt) -> None:
        if (entry.bundle_id, entry.original_bundle_id, entry.supplement_batch_id) != (
            receipt.bundle_id, receipt.original_bundle_id, receipt.supplement_batch_id,
        ):
            raise ValueError('receipt identifies a different joint publication')
        connection.execute(
            'INSERT INTO bundle_payloads (bundle_id, bundle_bytes) VALUES (?, ?)',
            (entry.bundle_id, entry.bundle_bytes),
        )
        connection.execute('''
            INSERT INTO joint_directory
                (bundle_id, original_bundle_id, supplement_batch_id, day_key, revision_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            entry.bundle_id, entry.original_bundle_id, entry.supplement_batch_id,
            entry.day_key, entry.revision_id,
        ))
        connection.execute(
            'INSERT INTO joint_receipts (receipt_id, bundle_id) VALUES (?, ?)',
            (receipt.receipt_id, receipt.bundle_id),
        )

    def bundle_ids(self) -> tuple[str, ...]:
        with closing(self.connect()) as connection:
            rows = connection.execute('''
                SELECT bundle_id FROM archive_directory
                UNION
                SELECT bundle_id FROM joint_directory
                ORDER BY bundle_id
            ''')
            return tuple(row[0] for row in rows)

    def joint_bundle_ids(self) -> tuple[str, ...]:
        with closing(self.connect()) as connection:
            rows = connection.execute('SELECT bundle_id FROM joint_directory ORDER BY bundle_id')
            return tuple(row[0] for row in rows)
