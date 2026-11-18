import sqlite3

from archive.bundle import BundleError, open_bundle
from archive.catalog import ArchiveCatalog


class ArchiveReadError(LookupError):
    pass


def export(catalog: ArchiveCatalog, bundle_id: str) -> bytes:
    try:
        entry = catalog.read_by_bundle(bundle_id)
        if entry is None:
            raise ArchiveReadError(f'unknown bundle id {bundle_id!r}')
        bundle = open_bundle(entry.bundle_bytes)
    except (sqlite3.Error, BundleError) as error:
        raise ArchiveReadError(f'could not read bundle {bundle_id!r}: {error}') from error
    if (bundle.bundle_id, bundle.layout.day_key, bundle.layout.revision_id) != (
        bundle_id, entry.day_key, entry.revision_id,
    ):
        raise ArchiveReadError(f'catalog identity mismatch for bundle {bundle_id!r}')
    return entry.bundle_bytes
