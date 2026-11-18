import hashlib
import hmac
import json


def canonical_bundle_body(body: dict) -> bytes:
    return json.dumps(body, ensure_ascii=True, allow_nan=False, separators=(',', ':'), sort_keys=True).encode('utf-8')


def bundle_digest(body: dict) -> str:
    return hashlib.sha256(canonical_bundle_body(body)).hexdigest()


def verify_bundle_digest(body: dict, digest: object) -> bool:
    if type(digest) is not str or len(digest) != 64:
        return False
    return hmac.compare_digest(bundle_digest(body).encode('ascii'), digest.encode('utf-8'))
