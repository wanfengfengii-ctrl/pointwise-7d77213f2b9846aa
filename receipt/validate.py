from collections.abc import Iterable, Iterator

from encoding.layout import Layout, validate_layout
from encoding.payload import Fragment, FragmentError, freeze_slot_payload
from receipt.slots import ReceivedSlots, SlotConflictError, collect_slots


class ReceiveValidationError(ValueError):
    pass


def _validated_fragments(layout: Layout, fragments: Iterable[Fragment]) -> Iterator[Fragment]:
    for fragment in fragments:
        if not isinstance(fragment, Fragment):
            raise FragmentError('delivery entries must be Fragment objects')
        yield freeze_slot_payload(layout, fragment.slot, fragment.values)


def validate_delivery(layout: Layout, fragments: Iterable[Fragment]) -> ReceivedSlots:
    try:
        validate_layout(layout)
    except ValueError as error:
        raise ReceiveValidationError(str(error)) from error
    try:
        delivery = iter(fragments)
    except TypeError as error:
        raise ReceiveValidationError('delivery must be an iterable of fragments') from error
    try:
        return collect_slots(_validated_fragments(layout, delivery))
    except (FragmentError, SlotConflictError) as error:
        raise ReceiveValidationError(str(error)) from error
