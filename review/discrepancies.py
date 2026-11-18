from collections.abc import Iterable, Sequence


def column_disagreements(prediction: Sequence[int], received: Iterable[tuple[int, int]]) -> tuple[int, ...]:
    return tuple(slot for slot, value in received if prediction[slot] != value)
