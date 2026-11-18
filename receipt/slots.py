from collections.abc import Iterable
from dataclasses import dataclass

from encoding.payload import Fragment


class SlotConflictError(ValueError):
    def __init__(self, slot: int) -> None:
        self.slot = slot
        super().__init__(f'conflicting values for slot {slot}')


@dataclass(frozen=True)
class ReceivedSlots:
    fragments: tuple[Fragment, ...]

    @property
    def coordinates(self) -> tuple[int, ...]:
        return tuple(fragment.slot for fragment in self.fragments)


def collect_slots(fragments: Iterable[Fragment]) -> ReceivedSlots:
    by_slot: dict[int, Fragment] = {}
    for fragment in fragments:
        previous = by_slot.get(fragment.slot)
        if previous is not None and previous.values != fragment.values:
            raise SlotConflictError(fragment.slot)
        by_slot[fragment.slot] = fragment
    return ReceivedSlots(tuple(by_slot[slot] for slot in sorted(by_slot)))
