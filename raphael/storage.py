"""SQLite repository for explicitly saved preferences; never stores chat text."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import threading

from .contracts import Profile


class ProfileStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._database = sqlite3.connect(self.path, timeout=5, check_same_thread=False)
        self._database.execute('PRAGMA secure_delete=ON')
        self._cached = None
        self._revision = None
        try: self._initialize()
        except BaseException:
            self._database.close()
            raise

    def _initialize(self):
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                raise RuntimeError("This preferences database needs a newer Raphael version.")
            if version == 0:
                db.execute("CREATE TABLE profile (id INTEGER PRIMARY KEY CHECK(id=1), name TEXT NOT NULL)")
                db.execute("INSERT INTO profile VALUES(1, '')")
                db.execute("CREATE TABLE notes (position INTEGER PRIMARY KEY, body TEXT NOT NULL)")
                db.execute("PRAGMA user_version=1")

    @contextmanager
    def _connect(self):
        with self._lock:
            db = self._database
            with db:
                yield db

    def get(self) -> Profile:
        with self._connect() as db:
            revision = db.execute('PRAGMA data_version').fetchone()[0]
            if self._cached is not None and revision == self._revision:
                return self._cached
            # A read transaction keeps the name and notes from the same revision.
            db.execute("BEGIN")
            name = db.execute("SELECT name FROM profile WHERE id=1").fetchone()[0]
            notes = tuple(row[0] for row in db.execute("SELECT body FROM notes ORDER BY position"))
            self._cached, self._revision = Profile(name, notes), revision
            return self._cached

    def save(self, profile: Profile) -> Profile:
        with self._connect() as db:
            db.execute("UPDATE profile SET name=? WHERE id=1", (profile.name,))
            db.execute("DELETE FROM notes")
            db.executemany("INSERT INTO notes(position, body) VALUES(?, ?)", enumerate(profile.notes))
            self._cached = None
        return profile

    def close(self):
        with self._lock:
            self._cached = None
            self._database.close()

    def __del__(self):
        # Compatibility for short-lived repository callers; Application closes explicitly.
        if hasattr(self, '_database'): self._database.close()
