import json
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from source.schema import RevisionConflictError, RevisionKey, RevisionSnapshot, Rows


class RevisionStore:
    def __init__(self, path: str | Path) -> None:
        self.path = path

    def initialize(self) -> None:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('''
                CREATE TABLE IF NOT EXISTS revisions (
                    revision_id TEXT PRIMARY KEY,
                    day_key TEXT NOT NULL,
                    label TEXT NOT NULL,
                    observations TEXT NOT NULL,
                    UNIQUE (day_key, label)
                )
            ''')

    def register_snapshot(self, key: RevisionKey, rows: Rows) -> str:
        observations = json.dumps(rows, separators=(',', ':'))
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            existing = connection.execute(
                'SELECT revision_id, observations FROM revisions WHERE day_key = ? AND label = ?',
                (key.day_key, key.label),
            ).fetchone()
            if existing is not None:
                revision_id, saved_observations = existing
                if saved_observations != observations:
                    raise RevisionConflictError(key)
                return revision_id

            revision_id = f'rev-{uuid4().hex}'
            connection.execute(
                'INSERT INTO revisions (revision_id, day_key, label, observations) VALUES (?, ?, ?, ?)',
                (revision_id, key.day_key, key.label, observations),
            )
        return revision_id

    def find_by_id(self, revision_id: str) -> RevisionSnapshot | None:
        with closing(sqlite3.connect(self.path)) as connection:
            entry = connection.execute(
                'SELECT day_key, label, observations FROM revisions WHERE revision_id = ?',
                (revision_id,),
            ).fetchone()
        if entry is None:
            return None
        day_key, label, observations = entry
        rows = tuple(tuple(row) for row in json.loads(observations))
        return RevisionSnapshot(revision_id, RevisionKey(day_key, label), rows)
