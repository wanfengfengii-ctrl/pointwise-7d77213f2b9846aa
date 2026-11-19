import json
from collections.abc import Iterable
from dataclasses import dataclass

from archive.integrity import bundle_digest, canonical_bundle_body, verify_bundle_digest
from encoding.layout import Layout, layout_document, layout_from_document, validate_layout
from encoding.payload import Fragment, freeze_slot_payload


BUNDLE_VERSION = 1
JOINT_BUNDLE_VERSION = 2


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


@dataclass(frozen=True)
class JointBundle:
    bundle_id: str
    layout: Layout
    original_bundle_id: str
    supplement_batch_id: str
    original: tuple[Fragment, ...]
    supplement: tuple[Fragment, ...]

    @property
    def original_directory(self) -> tuple[int, ...]:
        return tuple(fragment.slot for fragment in self.original)

    @property
    def supplement_directory(self) -> tuple[int, ...]:
        return tuple(fragment.slot for fragment in self.supplement)


def _validate_bundle_id(bundle_id: object) -> None:
    if type(bundle_id) is not str or not bundle_id.strip():
        raise BundleError('a nonblank bundle id is required')
    bundle_id.encode('utf-8')


def _validate_source_id(source_id: object, name: str) -> None:
    if type(source_id) is not str or not source_id.strip():
        raise BundleError(f'a nonblank {name} is required')
    source_id.encode('utf-8')


def _fragment_records(layout: Layout, fragments: Iterable[Fragment]) -> tuple[list[int], list[list]]:
    by_slot = {}
    for fragment in fragments:
        if not isinstance(fragment, Fragment):
            raise BundleError('bundle entries must be Fragment objects')
        checked = freeze_slot_payload(layout, fragment.slot, fragment.values)
        if checked.slot in by_slot:
            raise BundleError(f'duplicate bundle slot {checked.slot}')
        by_slot[checked.slot] = checked.values
    directory = sorted(by_slot)
    return directory, [[slot, list(by_slot[slot])] for slot in directory]


def encode_bundle(bundle_id: str, layout: Layout, fragments: Iterable[Fragment]) -> bytes:
    try:
        _validate_bundle_id(bundle_id)
        validate_layout(layout)
        directory, records = _fragment_records(layout, fragments)
        body = {
            'version': BUNDLE_VERSION,
            'bundle_id': bundle_id,
            'layout': layout_document(layout),
            'directory': directory,
            'fragments': records,
        }
        return canonical_bundle_body({'body': body, 'sha256': bundle_digest(body)})
    except BundleError:
        raise
    except (TypeError, ValueError) as error:
        raise BundleError(f'invalid bundle evidence: {error}') from error


def encode_joint_bundle(
    bundle_id: str,
    layout: Layout,
    original_bundle_id: str,
    supplement_batch_id: str,
    original: Iterable[Fragment],
    supplement: Iterable[Fragment],
) -> bytes:
    try:
        _validate_bundle_id(bundle_id)
        _validate_source_id(original_bundle_id, 'original bundle id')
        _validate_source_id(supplement_batch_id, 'supplement batch id')
        validate_layout(layout)
        original_directory, original_records = _fragment_records(layout, original)
        supplement_directory, supplement_records = _fragment_records(layout, supplement)
        body = {
            'version': JOINT_BUNDLE_VERSION,
            'bundle_id': bundle_id,
            'layout': layout_document(layout),
            'original_bundle_id': original_bundle_id,
            'supplement_batch_id': supplement_batch_id,
            'original': {'directory': original_directory, 'fragments': original_records},
            'supplement': {'directory': supplement_directory, 'fragments': supplement_records},
        }
        return canonical_bundle_body({'body': body, 'sha256': bundle_digest(body)})
    except BundleError:
        raise
    except (TypeError, ValueError) as error:
        raise BundleError(f'invalid joint bundle evidence: {error}') from error


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


def _read_source(document: object, layout: Layout) -> tuple[Fragment, ...]:
    if type(document) is not dict or set(document) != {'directory', 'fragments'}:
        raise BundleError('invalid joint source evidence')
    directory = document['directory']
    if type(directory) is not list or any(type(slot) is not int for slot in directory):
        raise BundleError('invalid slot directory')
    if directory != sorted(set(directory)):
        raise BundleError('slot directory must be unique and in ascending order')
    records = document['fragments']
    if type(records) is not list:
        raise BundleError('source fragments must be an array')
    fragments = []
    for record in records:
        if type(record) is not list or len(record) != 2 or type(record[1]) is not list:
            raise BundleError('each fragment requires a slot and an array of values')
        fragments.append(freeze_slot_payload(layout, record[0], record[1]))
    if directory != [fragment.slot for fragment in fragments]:
        raise BundleError('slot directory and fragments disagree')
    return tuple(fragments)


def _read_joint_body(body: dict) -> JointBundle:
    expected = {
        'version', 'bundle_id', 'layout', 'original_bundle_id',
        'supplement_batch_id', 'original', 'supplement',
    }
    if set(body) != expected:
        raise BundleError('invalid joint bundle fields')
    if type(body['version']) is not int or body['version'] != JOINT_BUNDLE_VERSION:
        raise BundleError('unsupported joint bundle version')
    bundle_id = body['bundle_id']
    _validate_bundle_id(bundle_id)
    original_bundle_id = body['original_bundle_id']
    _validate_source_id(original_bundle_id, 'original bundle id')
    supplement_batch_id = body['supplement_batch_id']
    _validate_source_id(supplement_batch_id, 'supplement batch id')
    layout = layout_from_document(body['layout'])
    original = _read_source(body['original'], layout)
    supplement = _read_source(body['supplement'], layout)
    return JointBundle(bundle_id, layout, original_bundle_id, supplement_batch_id, original, supplement)


def open_bundle(raw: bytes) -> FixedBundle | JointBundle:
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
        version = body.get('version')
        if type(version) is int and version == JOINT_BUNDLE_VERSION:
            return _read_joint_body(body)
        return _read_body(body)
    except BundleError:
        raise
    except (ValueError, RecursionError) as error:
        raise BundleError(f'invalid bundle: {error}') from error
