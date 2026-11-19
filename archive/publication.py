from collections.abc import Callable
from uuid import uuid4

from archive.bundle import FixedBundle, encode_bundle, encode_joint_bundle, open_bundle
from archive.catalog import (
    ArchiveCatalog,
    CatalogEntry,
    JointCatalogEntry,
    JointSealReceipt,
    SealReceipt,
)
from archive.commit import commit_joint, commit_publication
from archive.export import export
from encoding.layout import Layout
from encoding.payload import Fragment
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


def _sealed_original(catalog: ArchiveCatalog, original_bundle_id: str) -> tuple[Layout, tuple[Fragment, ...]]:
    raw = export(catalog, original_bundle_id)
    bundle = open_bundle(raw)
    if not isinstance(bundle, FixedBundle):
        raise ValueError(f'original bundle {original_bundle_id!r} is not a V1 package')
    return bundle.layout, bundle.fragments


def seal_joint(
    ledger: ReceiptLedger,
    catalog: ArchiveCatalog,
    original_bundle_id: str,
    supplement_batch_id: str,
    before_commit: Callable[[], None] | None = None,
) -> JointSealReceipt:
    existing = catalog.find_joint(original_bundle_id, supplement_batch_id)
    if existing is not None:
        return existing

    original_layout, original_fragments = _sealed_original(catalog, original_bundle_id)
    supplement = ledger.get_batch(supplement_batch_id)
    if supplement.layout != original_layout:
        raise ValueError('original and supplement layouts disagree')

    layout = original_layout
    bundle_id = f'bundle-{uuid4().hex}'
    bundle_bytes = encode_joint_bundle(
        bundle_id,
        layout,
        original_bundle_id,
        supplement.batch_id,
        original_fragments,
        supplement.received.fragments,
    )
    entry = JointCatalogEntry(
        bundle_id,
        original_bundle_id,
        supplement.batch_id,
        layout.day_key,
        layout.revision_id,
        bundle_bytes,
    )
    receipt = JointSealReceipt(
        original_bundle_id,
        supplement.batch_id,
        bundle_id,
        f'seal-{uuid4().hex}',
    )
    return commit_joint(catalog, entry, receipt, before_commit)
