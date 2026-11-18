from dataclasses import dataclass


SLOT_COORDINATES = (0, 1, 2, 3, 4, 5)
SOURCE_SLOTS = SLOT_COORDINATES[:3]


@dataclass(frozen=True)
class Layout:
    day_key: str
    revision_id: str
    width: int
    coordinates: tuple[int, ...] = SLOT_COORDINATES


def validate_layout(layout: Layout) -> Layout:
    if not isinstance(layout, Layout):
        raise ValueError('a fixed layout is required')
    for identifier in (layout.day_key, layout.revision_id):
        if type(identifier) is not str or not identifier.strip():
            raise ValueError('layout requires a day key and a revision id')
        identifier.encode('utf-8')
    if type(layout.width) is not int or layout.width < 0:
        raise ValueError('layout width must be a nonnegative integer')
    if (
        type(layout.coordinates) is not tuple
        or any(type(slot) is not int for slot in layout.coordinates)
        or layout.coordinates != SLOT_COORDINATES
    ):
        raise ValueError('layout coordinates must be slots 0–5 in order')
    return layout


def make_layout(day_key: str, revision_id: str, width: int) -> Layout:
    return validate_layout(Layout(day_key, revision_id, width))


def layout_document(layout: Layout) -> dict:
    return {
        'day_key': layout.day_key,
        'revision_id': layout.revision_id,
        'width': layout.width,
        'coordinates': list(layout.coordinates),
    }


def layout_from_document(document: object) -> Layout:
    if type(document) is not dict or set(document) != {'day_key', 'revision_id', 'width', 'coordinates'}:
        raise ValueError('invalid layout fields')
    coordinates = document['coordinates']
    if type(coordinates) is not list:
        raise ValueError('layout coordinates must be an array')
    return validate_layout(Layout(document['day_key'], document['revision_id'], document['width'], tuple(coordinates)))
