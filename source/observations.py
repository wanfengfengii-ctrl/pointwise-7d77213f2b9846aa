from collections.abc import Sequence


class ObservationError(ValueError):
    pass


def freeze_observations(rows: Sequence[Sequence[int]]) -> tuple[tuple[int, ...], ...]:
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        raise ObservationError('observations must be an ordered sequence of three rows')
    if len(rows) != 3:
        raise ObservationError('observations require three rows')

    frozen = []
    for slot, row in enumerate(rows):
        if not isinstance(row, Sequence) or isinstance(row, (str, bytes, bytearray)):
            raise ObservationError(f'observation row {slot} must be an ordered sequence')
        values = tuple(row)
        if frozen and len(values) != len(frozen[0]):
            raise ObservationError(f'observation row {slot} has inconsistent width')
        for column, value in enumerate(values):
            if type(value) is not int or not 0 <= value <= 256:
                raise ObservationError(f'observation row {slot} column {column} requires an integer in 0–256')
        frozen.append(values)
    return tuple(frozen)
