import json
from pathlib import Path
from tempfile import TemporaryDirectory

from archive.bundle import open_bundle
from archive.catalog import ArchiveCatalog
from archive.export import export
from archive.publication import seal
from encoding.encode import encode
from encoding.payload import Fragment
from receipt.intake import receive
from receipt.ledger import ReceiptLedger
from review.recovery import recover
from source.revisions import record
from source.store import RevisionStore


def load_cases():
    path = Path(__file__).resolve().parent / "samples" / "joint_evidence.json"
    return json.loads(path.read_text(encoding="utf-8"))


def stage_case(root, case):
    store = RevisionStore(root / "source.sqlite3")
    ledger = ReceiptLedger(root / "receipt.sqlite3")
    catalog = ArchiveCatalog(root / "archive.sqlite3")
    for database in (store, ledger, catalog):
        database.initialize()

    revision_id = record(store, "river-north/2026-06-12", case["case"], case["rows"])
    layout = encode(store, revision_id).layout
    original_batch = receive(ledger, layout, (Fragment(*entry) for entry in case["original"]))
    original = seal(ledger, catalog, original_batch)
    supplement = receive(ledger, layout, (Fragment(*entry) for entry in case["supplement"]))
    return ledger, catalog, original, supplement


def main():
    with TemporaryDirectory(prefix="hydrology-joint-inputs-") as directory:
        root = Path(directory)
        for case in load_cases():
            ledger, catalog, original, supplement = stage_case(root, case)
            ordinary_supplement = seal(ledger, catalog, supplement)
            raw = [export(catalog, receipt.bundle_id) for receipt in (original, ordinary_supplement)]
            readings = [
                [[fragment.slot, list(fragment.values)] for fragment in open_bundle(item).fragments]
                for item in raw
            ]
            expected = [sorted(case[role]) for role in ("original", "supplement")]
            statuses = [recover(item).status for item in raw]
            if readings != expected or statuses != case["v1_statuses"]:
                raise AssertionError((case["case"], readings, statuses))
            print(json.dumps({"case": case["case"], "v1_statuses": statuses, "received": readings}))


if __name__ == "__main__":
    main()
