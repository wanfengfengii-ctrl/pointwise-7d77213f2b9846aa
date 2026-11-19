import sqlite3

from archive.bundle import BundleError, JointBundle, open_bundle
from archive.catalog import ArchiveCatalog


class ArchiveReadError(LookupError):
    pass


def _entry_for(catalog: ArchiveCatalog, bundle_id: str):
    entry = catalog.read_by_bundle(bundle_id)
    if entry is not None:
        return entry, False
    entry = catalog.read_joint_by_bundle(bundle_id)
    if entry is not None:
        return entry, True
    return None, False


def export(catalog: ArchiveCatalog, bundle_id: str) -> bytes:
    try:
        entry, is_joint_entry = _entry_for(catalog, bundle_id)
        if entry is None:
            raise ArchiveReadError(f'unknown bundle id {bundle_id!r}')
        bundle = open_bundle(entry.bundle_bytes)
    except (sqlite3.Error, BundleError) as error:
        raise ArchiveReadError(f'could not read bundle {bundle_id!r}: {error}') from error
    if (bundle.bundle_id, bundle.layout.day_key, bundle.layout.revision_id) != (
        bundle_id, entry.day_key, entry.revision_id,
    ):
        raise ArchiveReadError(f'catalog identity mismatch for bundle {bundle_id!r}')
    if is_joint_entry:
        if not isinstance(bundle, JointBundle):
            raise ArchiveReadError(f'catalog identity mismatch for bundle {bundle_id!r}')
        if (bundle.original_bundle_id, bundle.supplement_batch_id) != (
            entry.original_bundle_id, entry.supplement_batch_id,
        ):
            raise ArchiveReadError(f'catalog identity mismatch for bundle {bundle_id!r}')
    elif isinstance(bundle, JointBundle):
        raise ArchiveReadError(f'catalog identity mismatch for bundle {bundle_id!r}')
    return entry.bundle_bytes
