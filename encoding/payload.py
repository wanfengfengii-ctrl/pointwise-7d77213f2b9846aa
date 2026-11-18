from collections.abc import Sequence
from dataclasses import dataclass

from encoding.field import FIELD_MODULUS
from encoding.layout import Layout


class FragmentError(ValueError):
    pass


@dataclass(frozen=True)
class Fragment:
    slot: int
    values: Sequence[int]


def freeze_slot_payload(layout: Layout, slot: int, values: Sequence[int]) -> Fragment:
    if type(slot) is not int or slot not in layout.coordinates:
        raise FragmentError(f'unknown slot {slot!r}')
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        raise FragmentError(f'slot {slot} values must be an ordered sequence')
    frozen = tuple(values)
    if len(frozen) != layout.width:
        raise FragmentError(f'slot {slot} has width {len(frozen)}, expected {layout.width}')
    for column, value in enumerate(frozen):
        if type(value) is not int or not 0 <= value < FIELD_MODULUS:
            raise FragmentError(f'slot {slot} column {column} requires an integer in 0–256')
    return Fragment(slot, frozen)
