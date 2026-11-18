import sqlite3
from collections.abc import Callable
from contextlib import closing

from archive.catalog import ArchiveCatalog, CatalogEntry, SealReceipt


class SealCommitError(RuntimeError):
    pass


def commit_publication(
    catalog: ArchiveCatalog,
    entry: CatalogEntry,
    receipt: SealReceipt,
    before_commit: Callable[[], None] | None = None,
) -> SealReceipt:
    try:
        with closing(catalog.connect()) as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            existing = catalog.find_by_batch(entry.batch_id, connection=connection)
            if existing is not None:
                return existing
            catalog.stage_publication(connection, entry, receipt)
            if before_commit is not None:
                try:
                    before_commit()
                except Exception as error:
                    raise SealCommitError(f'publication stopped before commit: {error}') from error
    except sqlite3.Error as error:
        raise SealCommitError(f'could not publish batch {entry.batch_id!r}: {error}') from error
    return receipt
