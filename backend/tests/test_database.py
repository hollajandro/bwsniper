from types import SimpleNamespace

import app.db.database as database


class FakeConnection:
    def __init__(self, versions):
        self._versions = versions

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, _query):
        return [(version,) for version in self._versions]


class FakeEngine:
    def __init__(self, versions):
        self._versions = versions

    def connect(self):
        return FakeConnection(self._versions)


class FakeAlembicConfig:
    def __init__(self, path):
        self.path = path
        self.options = {}

    def set_main_option(self, key, value):
        self.options[key] = value


class FakeScriptDirectory:
    def __init__(self, heads):
        self._heads = heads

    def get_heads(self):
        return self._heads

    @classmethod
    def from_config(cls, _config):
        return cls(["head-1"])


def make_inspector(has_table):
    return lambda _conn: SimpleNamespace(has_table=lambda _name: has_table)


def test_get_alembic_revision_state_reports_current_schema():
    state, detail = database._get_alembic_revision_state(
        db_engine=FakeEngine(["head-1"]),
        inspector_factory=make_inspector(True),
        alembic_config_cls=FakeAlembicConfig,
        script_directory_cls=FakeScriptDirectory,
    )

    assert state == "current"
    assert detail is None


def test_get_alembic_revision_state_reports_missing_version_table():
    state, detail = database._get_alembic_revision_state(
        db_engine=FakeEngine(["head-1"]),
        inspector_factory=make_inspector(False),
        alembic_config_cls=FakeAlembicConfig,
        script_directory_cls=FakeScriptDirectory,
    )

    assert state == "missing"
    assert detail is None


def test_log_non_sqlite_migration_status_stays_quiet_when_schema_is_current(
    monkeypatch,
    caplog,
):
    monkeypatch.setattr(
        database,
        "_get_alembic_revision_state",
        lambda: ("current", None),
    )

    with caplog.at_level("WARNING"):
        database._log_non_sqlite_migration_status()

    assert caplog.records == []


def test_log_non_sqlite_migration_status_warns_when_schema_is_outdated(
    monkeypatch,
    caplog,
):
    monkeypatch.setattr(
        database,
        "_get_alembic_revision_state",
        lambda: (
            "outdated",
            "Database revision(s) ['old'] do not match Alembic head(s) ['new'].",
        ),
    )

    with caplog.at_level("WARNING"):
        database._log_non_sqlite_migration_status()

    assert "behind the current Alembic revision" in caplog.text
