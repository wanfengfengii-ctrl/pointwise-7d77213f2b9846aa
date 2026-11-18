from collections.abc import Iterable

from encoding.layout import Layout
from encoding.payload import Fragment
from receipt.ledger import ReceiptLedger
from receipt.validate import validate_delivery


def receive(ledger: ReceiptLedger, layout: Layout, fragments: Iterable[Fragment]) -> str:
    received = validate_delivery(layout, fragments)
    return ledger.record_batch(layout, received)
