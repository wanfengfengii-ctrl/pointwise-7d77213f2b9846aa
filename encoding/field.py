from collections.abc import Iterable


FIELD_MODULUS = 257


def field_inverse(value: int) -> int:
    return pow(value % FIELD_MODULUS, -1, FIELD_MODULUS)


def interpolate(points: Iterable[tuple[int, int]], coordinate: int) -> int:
    samples = tuple(points)
    origins = {origin % FIELD_MODULUS for origin, _ in samples}
    if not samples or len(origins) != len(samples):
        raise ValueError('interpolation requires nonempty points with distinct field coordinates')

    result = 0
    for index, (origin, value) in enumerate(samples):
        numerator = 1
        denominator = 1
        for other_index, (other_origin, _) in enumerate(samples):
            if index != other_index:
                numerator = numerator * (coordinate - other_origin) % FIELD_MODULUS
                denominator = denominator * (origin - other_origin) % FIELD_MODULUS
        result = (result + value * numerator * field_inverse(denominator)) % FIELD_MODULUS
    return result
