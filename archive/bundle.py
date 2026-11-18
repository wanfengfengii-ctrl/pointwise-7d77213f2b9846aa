import json
from collections.abc import Iterable
from dataclasses import dataclass

from archive.integrity import bundle_digest, canonical_bundle_body, verify_bundle_digest
from encoding.layout import Layout, layout_document, layout_from_document, validate_layout
from encoding.payload import Fragment, freeze_slot_payload


BUNDLE_VERSION = 1


class BundleError(ValueError):
    pass


@dataclass(frozen=True)
class FixedBundle:
    bundle_id: str
    layout: Layout
    fragments: tuple[Fragment, ...]

    @property
    def directory(self) -> tuple[int, ...]:
        return tuple(fragment.slot for fragment in self.fragments)


def _validate_bundle_id(bundle_id: object) -> None:
    if type(bundle_id) is not str or not bundle_id.strip():
        raise BundleError('a nonblank bundle id is required')
    bundle_id.encode('utf-8')


def encode_bundle(bundle_id: str, layout: Layout, fragments: Iterable[Fragment]) -> bytes:
    try:
        _validate_bundle_id(bundle_id)
        validate_layout(layout)
        by_slot = {}
        for fragment in fragments:
            if not isinstance(fragment, Fragment):
                raise BundleError('bundle entries must be Fragment objects')
            checked = freeze_slot_payload(layout, fragment.slot, fragment.values)
            if checked.slot in by_slot:
                raise BundleError(f'duplicate bundle slot {checked.slot}')
            by_slot[checked.slot] = checked.values
        directory = sorted(by_slot)
        body = {
            'version': BUNDLE_VERSION,
            'bundle_id': bundle_id,
            'layout': layout_document(layout),
            'directory': directory,
            'fragments': [[slot, list(by_slot[slot])] for slot in directory],
        }
        return canonical_bundle_body({'body': body, 'sha256': bundle_digest(body)})
    except BundleError:
        raise
    except (TypeError, ValueError) as error:
        raise BundleError(f'invalid bundle evidence: {error}') from error


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise BundleError(f'duplicate JSON field {key!r}')
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise BundleError(f'invalid JSON constant {value!r}')


def _read_body(body: dict) -> FixedBundle:
    if set(body) != {'version', 'bundle_id', 'layout', 'directory', 'fragments'}:
        raise BundleError('invalid bundle fields')
    if type(body['version']) is not int or body['version'] != BUNDLE_VERSION:
        raise BundleError('unsupported bundle version')
    bundle_id = body['bundle_id']
    _validate_bundle_id(bundle_id)
    layout = layout_from_document(body['layout'])
    directory = body['directory']
    if type(directory) is not list or any(type(slot) is not int for slot in directory):
        raise BundleError('invalid slot directory')
    if directory != sorted(set(directory)):
        raise BundleError('slot directory must be unique and in ascending order')

    records = body['fragments']
    if type(records) is not list:
        raise BundleError('bundle fragments must be an array')
    fragments = []
    for record in records:
        if type(record) is not list or len(record) != 2 or type(record[1]) is not list:
            raise BundleError('each bundle fragment requires a slot and an array of values')
        fragments.append(freeze_slot_payload(layout, record[0], record[1]))
    if directory != [fragment.slot for fragment in fragments]:
        raise BundleError('slot directory and fragments disagree')
    return FixedBundle(bundle_id, layout, tuple(fragments))


def open_bundle(raw: bytes) -> FixedBundle:
    if type(raw) is not bytes:
        raise BundleError('bundle input must be bytes')
    try:
        envelope = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
        if type(envelope) is not dict or set(envelope) != {'body', 'sha256'}:
            raise BundleError('invalid bundle envelope')
        body = envelope['body']
        if type(body) is not dict:
            raise BundleError('bundle body must be an object')
        if not verify_bundle_digest(body, envelope['sha256']):
            raise BundleError('bundle digest mismatch')
        return _read_body(body)
    except BundleError:
        raise
    except (ValueError, RecursionError) as error:
        raise BundleError(f'invalid bundle: {error}') from error
