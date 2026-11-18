from dataclasses import dataclass


Rows = tuple[tuple[int, ...], ...]


class RevisionConflictError(ValueError):
    def __init__(self, key: 'RevisionKey') -> None:
        self.key = key
        super().__init__(f'conflicting observations for {key.day_key!r} / {key.label!r}')


@dataclass(frozen=True)
class RevisionKey:
    day_key: str
    label: str

    def __post_init__(self) -> None:
        for name, value in (('day key', self.day_key), ('revision label', self.label)):
            if type(value) is not str or not value.strip():
                raise ValueError(f'{name} must be a nonblank string')
            try:
                value.encode('utf-8')
            except UnicodeError as error:
                raise ValueError(f'{name} must be valid UTF-8 text') from error


@dataclass(frozen=True)
class RevisionSnapshot:
    revision_id: str
    key: RevisionKey
    rows: Rows
