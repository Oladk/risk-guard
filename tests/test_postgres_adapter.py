"""Tests des adaptateurs Postgres (parties pures — pas de vraie base PG requise)."""

from src import db as DB


def test_is_postgres_false_by_default(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert DB.is_postgres() is False


def test_is_postgres_true_for_pg_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host/db")
    assert DB.is_postgres() is True


def test_adapt_ddl_sqlite_unchanged(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert "AUTOINCREMENT" in DB._adapt_ddl("id INTEGER PRIMARY KEY AUTOINCREMENT")


def test_adapt_ddl_postgres_serial(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    out = DB._adapt_ddl("id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT")
    assert "SERIAL PRIMARY KEY" in out
    assert "AUTOINCREMENT" not in out


def test_pgconn_translates_placeholders():
    calls = []

    class FakeRaw:
        def execute(self, sql, params=()):
            calls.append((sql, params))
            return "cursor"

    c = DB._PgConn(FakeRaw())
    c.execute("SELECT * FROM t WHERE a=? AND b=?", (1, 2))
    assert calls[0][0] == "SELECT * FROM t WHERE a=%s AND b=%s"
    assert calls[0][1] == (1, 2)


def test_pgconn_executescript_splits_statements():
    calls = []

    class FakeRaw:
        def execute(self, sql, params=()):
            calls.append(sql.strip())

    c = DB._PgConn(FakeRaw())
    c.executescript("CREATE TABLE a (x INT);\nCREATE TABLE b (y INT);\n")
    assert len([s for s in calls if s]) == 2
