from source.schema import RevisionSnapshot
from source.store import RevisionStore


class UnknownRevisionError(LookupError):
    pass


def get_revision(store: RevisionStore, revision_id: str) -> RevisionSnapshot:
    snapshot = store.find_by_id(revision_id)
    if snapshot is None:
        raise UnknownRevisionError(revision_id)
    return snapshot
