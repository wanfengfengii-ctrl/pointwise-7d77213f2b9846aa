import json

from encoding.layout import Layout, layout_document
from receipt.slots import ReceivedSlots


def canonical_batch_key(layout: Layout, received: ReceivedSlots) -> str:
    evidence = {
        'layout': layout_document(layout),
        'fragments': [[fragment.slot, list(fragment.values)] for fragment in received.fragments],
    }
    return json.dumps(evidence, ensure_ascii=True, separators=(',', ':'), sort_keys=True)
