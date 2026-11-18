from collections.abc import Callable
from uuid import uuid4

from archive.bundle import encode_bundle
from archive.catalog import ArchiveCatalog, CatalogEntry, SealReceipt
from archive.commit import commit_publication
from receipt.ledger import ReceiptLedger


def seal(
    ledger: ReceiptLedger,
    catalog: ArchiveCatalog,
    batch_id: str,
    before_commit: Callable[[], None] | None = None,
) -> SealReceipt:
    batch = ledger.get_batch(batch_id)
    layout = batch.layout
    bundle_id = f'bundle-{uuid4().hex}'
    bundle_bytes = encode_bundle(bundle_id, layout, batch.received.fragments)
    entry = CatalogEntry(bundle_id, batch.batch_id, layout.day_key, layout.revision_id, bundle_bytes)
    receipt = SealReceipt(batch.batch_id, bundle_id, f'seal-{uuid4().hex}')
    return commit_publication(catalog, entry, receipt, before_commit)
