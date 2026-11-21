"""ROI P0 — minimal read-only profile activity collector.

Reads a Hermes profile's ``state.db`` strictly read-only and returns the
billing-relevant facts ROI needs (tokens by bucket, route metadata,
schema version) without touching the store:

* Open pattern: ``sqlite3.connect(path + "?mode=ro", uri=True)`` — any write
  attempt fails with ``sqlite3.OperationalError`` (proven by test).
* Profile routing: explicit ``(hermes_root, profile_name)`` — the process's
  own ``HERMES_HOME`` is never consulted (issue #18594 fallback trap).
* Timezone: day bucketing is the machine-local calendar day of
  ``started_at`` (same rule as hermes-activity and ``/api/analytics/usage``).
* No raw user content is ever selected — only counters and route metadata.

Scope note: this is the P0 smoke collector. P1 adds the typed 5-bucket
normalization (cache/reasoning semantics) on top of ``iter_sessions``.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

# ---------------------------------------------------------------------------
# Profile resolution
# ---------------------------------------------------------------------------

#: Identity markers that make a ``profiles/<name>`` directory a real profile
#: (mirrors ``hermes_constants._PROFILE_IDENTITY_MARKERS``).
PROFILE_IDENTITY_MARKERS = ("config.yaml", ".env", "SOUL.md", "profile.yaml", "auth.json", "state.db")

#: Columns the collector refuses to run without.
REQUIRED_SESSION_COLUMNS = (
    "id", "source", "model", "parent_session_id", "started_at",
    "input_tokens", "output_tokens", "cache_read_tokens",
    "cache_write_tokens", "reasoning_tokens", "billing_provider", "billing_base_url",
)

#: Optional columns probed and degraded to 0/None when absent.
OPTIONAL_SESSION_COLUMNS = (
    "billing_mode", "estimated_cost_usd", "actual_cost_usd", "cost_status",
    "cost_source", "pricing_version", "api_call_count", "message_count",
    "tool_call_count", "ended_at", "last_activity_at", "profile_name",
)


class ProfileNotFoundError(FileNotFoundError):
    """The named profile directory does not exist or is not a live profile."""


class SchemaError(RuntimeError):
    """state.db is missing required columns or an expected table."""


def _valid_profile_name(name: str) -> bool:
    """No traversal, no hidden, non-empty — mirrors the core profile-id grammar."""
    return bool(name) and not name.startswith(".") and "/" not in name and "\\" not in name and "\x00" not in name


def resolve_profile_home(hermes_root: str | Path, profile_name: str) -> Path:
    """Resolve ``(hermes_root, profile_name)`` to a profile home directory.

    - ``profile_name == "default"`` → ``hermes_root`` itself.
    - otherwise → ``hermes_root/profiles/<name>``; must exist and carry at
      least one identity marker. Never derives anything from the process
      environment.
    """
    root = Path(hermes_root).expanduser()
    name = (profile_name or "").strip()
    if name == "default":
        if not root.is_dir():
            raise ProfileNotFoundError(f"hermes root not found: {root}")
        return root
    if not _valid_profile_name(name):
        raise ProfileNotFoundError(f"invalid profile name: {profile_name!r}")
    home = root / "profiles" / name
    if not home.is_dir():
        raise ProfileNotFoundError(f"profile not found: {home}")
    if not any((home / marker).exists() for marker in PROFILE_IDENTITY_MARKERS):
        raise ProfileNotFoundError(f"directory is not a live Hermes profile (no identity markers): {home}")
    return home


def db_path(hermes_root: str | Path, profile_name: str) -> Path:
    """Absolute ``state.db`` path for a profile (file need not exist yet).
    Raises ProfileNotFoundError when the profile is missing/invalid."""
    return resolve_profile_home(hermes_root, profile_name) / "state.db"


# ---------------------------------------------------------------------------
# Read-only connection
# ---------------------------------------------------------------------------

def open_read_only(state_db: str | Path) -> sqlite3.Connection:
    """Open *state_db* in ``mode=ro`` URI mode.

    Any write attempt through this connection raises
    ``sqlite3.OperationalError("attempt to write a readonly database")``.
    Raises FileNotFoundError (not sqlite3.OperationalError) when the file is
    absent, so callers can map it to the friendly empty state.
    """
    path = Path(state_db).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"state.db not found: {path}")
    return sqlite3.connect(str(path.resolve().as_uri()) + "?mode=ro", uri=True, timeout=5)


# ---------------------------------------------------------------------------
# Row shapes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Route:
    """The billing route a session was accounted under (its own row, never
    inherited from a parent)."""
    provider: Optional[str]
    base_url: Optional[str]
    model: Optional[str]

    def is_local_candidate(self) -> bool:
        """Loopback base_url or provider-less local server shapes. A model name
        NEVER counts as evidence."""
        url = (self.base_url or "").lower()
        if not url:
            return False
        host = url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
        return host in ("127.0.0.1", "localhost", "::1", "0.0.0.0") or host.endswith(".local")


@dataclass(frozen=True)
class SessionRow:
    id: str
    source: Optional[str]
    started_at: float
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    reasoning_tokens: int
    is_child: bool
    route: Route
    api_call_count: int = 0


@dataclass
class DaySummary:
    day: str
    sessions: int = 0
    subagent_sessions: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    local_tokens: int = 0
    unknown_route_tokens: int = 0


@dataclass
class Summary:
    profile_name: str  # "all" for a machine-global aggregate
    schema_version: Optional[str]
    since: Optional[float]
    until: Optional[float]
    days: list[DaySummary] = field(default_factory=list)
    total_sessions: int = 0
    total_subagent_sessions: int = 0
    local_candidate_sessions: int = 0
    unknown_route_sessions: int = 0
    # Audit notes: things a reviewer must know without re-running the probe.
    audit_notes: list[str] = field(default_factory=list)
    # Profiles folded into this aggregate ([profile_name] for a single scope,
    # the included list for a global scope).
    profiles: Optional[list[str]] = None

    def __post_init__(self):
        if self.profiles is None:
            self.profiles = [self.profile_name]

    @property
    def totals(self) -> dict[str, int]:
        def s(key: str) -> int:
            return sum(getattr(d, key) for d in self.days)
        return {
            "sessions": self.total_sessions,
            "subagent_sessions": self.total_subagent_sessions,
            "input_tokens": s("input_tokens"),
            "output_tokens": s("output_tokens"),
            "cache_read_tokens": s("cache_read_tokens"),
            "cache_write_tokens": s("cache_write_tokens"),
            "reasoning_tokens": s("reasoning_tokens"),
            "local_tokens": s("local_tokens"),
            "unknown_route_tokens": s("unknown_route_tokens"),
        }


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def _schema_version(conn: sqlite3.Connection) -> Optional[str]:
    try:
        row = conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1").fetchone()
        return str(row[0]) if row else None
    except sqlite3.OperationalError:
        return None


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    except sqlite3.OperationalError:
        return set()


def _probe_schema(conn: sqlite3.Connection, audit: list[str]) -> None:
    missing = [c for c in REQUIRED_SESSION_COLUMNS if c not in _table_columns(conn, "sessions")]
    if missing:
        raise SchemaError(f"state.db is missing required sessions columns: {', '.join(missing)}")
    absent = [c for c in OPTIONAL_SESSION_COLUMNS if c not in _table_columns(conn, "sessions")]
    if absent:
        audit.append(f"optional columns absent (degraded to 0/NULL): {', '.join(absent)}")
    if not _table_columns(conn, "session_model_usage"):
        audit.append("session_model_usage absent: per-model pricing unavailable (session-level only)")


def iter_sessions(
    conn: sqlite3.Connection,
    since: Optional[float] = None,
    until: Optional[float] = None,
) -> Iterator[SessionRow]:
    """Yield session rows in range. Range is inclusive-lower/exclusive-upper
    (``started_at >= since AND started_at < until``) — Activity's rule."""
    where, params = [], []
    if since is not None:
        where.append("started_at >= ?")
        params.append(since)
    if until is not None:
        where.append("started_at < ?")
        params.append(until)
    sql = (
        "SELECT id, source, model, parent_session_id, started_at,"
        " COALESCE(input_tokens,0), COALESCE(output_tokens,0),"
        " COALESCE(cache_read_tokens,0), COALESCE(cache_write_tokens,0),"
        " COALESCE(reasoning_tokens,0),"
        " billing_provider, billing_base_url,"
        " COALESCE(api_call_count,0)"
        " FROM sessions"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    cur = conn.execute(sql, params)
    for r in cur:
        yield SessionRow(
            id=str(r[0]),
            source=r[1],
            started_at=float(r[4]),
            input_tokens=int(r[5]),
            output_tokens=int(r[6]),
            cache_read_tokens=int(r[7]),
            cache_write_tokens=int(r[8]),
            reasoning_tokens=int(r[9]),
            is_child=r[3] is not None,
            route=Route(provider=r[10], base_url=r[11], model=r[2]),
            api_call_count=int(r[12]),
        )


def _day(started_at: float) -> str:
    """Local-timezone calendar day of an absolute epoch timestamp."""
    return datetime.fromtimestamp(started_at).strftime("%Y-%m-%d")


def _merge_day(tgt: DaySummary, src: DaySummary) -> None:
    tgt.sessions += src.sessions
    tgt.subagent_sessions += src.subagent_sessions
    tgt.input_tokens += src.input_tokens
    tgt.output_tokens += src.output_tokens
    tgt.cache_read_tokens += src.cache_read_tokens
    tgt.cache_write_tokens += src.cache_write_tokens
    tgt.reasoning_tokens += src.reasoning_tokens
    tgt.local_tokens += src.local_tokens
    tgt.unknown_route_tokens += src.unknown_route_tokens


def _accumulate(
    conn: sqlite3.Connection,
    since: Optional[float],
    until: Optional[float],
    local_model_allowlist: tuple[str, ...],
) -> tuple[dict[str, DaySummary], dict[str, int]]:
    """Bucket one open store's in-range sessions by local day.

    ``local`` = loopback candidate OR model in the user-ticked allowlist.
    A model name alone is a user declaration, never an inference.
    Returns (days, counts) where counts = sessions/children/local/unknown.
    """
    days: dict[str, DaySummary] = {}
    counts = {"sessions": 0, "children": 0, "local": 0, "unknown": 0}
    allow = set(local_model_allowlist)
    for row in iter_sessions(conn, since, until):
        day_key = _day(row.started_at)
        day = days.get(day_key)
        if day is None:
            day = DaySummary(day=day_key)
            days[day_key] = day
        day.sessions += 1
        day.input_tokens += row.input_tokens
        day.output_tokens += row.output_tokens
        day.cache_read_tokens += row.cache_read_tokens
        day.cache_write_tokens += row.cache_write_tokens
        day.reasoning_tokens += row.reasoning_tokens
        if row.is_child:
            day.subagent_sessions += 1
        bucket = row.input_tokens + row.output_tokens + row.cache_read_tokens + row.cache_write_tokens
        if row.route.provider in (None, "") and row.route.base_url in (None, ""):
            day.unknown_route_tokens += bucket
            counts["unknown"] += 1
        elif row.route.is_local_candidate() or (row.route.model or "") in allow:
            day.local_tokens += bucket
            counts["local"] += 1
        counts["sessions"] += 1
        if row.is_child:
            counts["children"] += 1
    return days, counts


def summarize(
    hermes_root: str | Path,
    profile_name: str,
    since: Optional[float] = None,
    until: Optional[float] = None,
    local_model_allowlist: tuple[str, ...] = (),
) -> Summary:
    """Read-only aggregate over one profile's sessions.

    ``since``/``until`` are absolute unix epochs; omit both for full history.
    ``local_model_allowlist`` adds user-asserted local models (names alone are
    a user declaration, not an inference — the route check is primary).
    """
    path = db_path(hermes_root, profile_name)
    audit: list[str] = []
    conn = open_read_only(path)
    try:
        _probe_schema(conn, audit)
        version = _schema_version(conn)
        days, counts = _accumulate(conn, since, until, local_model_allowlist)
        if not days:
            audit.append("no sessions in range (empty state, not an error)")
        return Summary(
            profile_name=profile_name,
            schema_version=version,
            since=since,
            until=until,
            days=sorted(days.values(), key=lambda d: d.day),
            total_sessions=counts["sessions"],
            total_subagent_sessions=counts["children"],
            local_candidate_sessions=counts["local"],
            unknown_route_sessions=counts["unknown"],
            audit_notes=audit,
            profiles=[profile_name],
        )
    finally:
        conn.close()


def iter_profiles(hermes_root: str | Path) -> list[str]:
    """Every local profile that currently has a ``state.db``, default first.

    Only profiles carrying a live identity marker (see
    ``PROFILE_IDENTITY_MARKERS``) and a present store are listed; a live
    profile without a store yet is skipped (nothing to read), and remote
    profiles are out of scope for a read-only local aggregate.
    """
    root = Path(hermes_root).expanduser()
    out: list[str] = []
    if root.is_dir() and (root / "state.db").is_file():
        out.append("default")
    profs = root / "profiles"
    if profs.is_dir():
        for home in sorted(profs.iterdir()):
            if not home.is_dir() or not home.name or home.name.startswith("."):
                continue
            if not any((home / marker).exists() for marker in PROFILE_IDENTITY_MARKERS):
                continue
            if (home / "state.db").is_file():
                out.append(home.name)
    return out


def summarize_global(
    hermes_root: str | Path,
    since: Optional[float] = None,
    until: Optional[float] = None,
    local_model_allowlist: tuple[str, ...] = (),
) -> Summary:
    """Read-only machine-global aggregate across every local profile store.

    This is ROI's primary scope: the page never follows the active profile
    tab. ``profile_name`` is ``"all"``; ``profiles`` lists the stores folded
    in. Per-profile audit notes are prefixed with the profile name.
    """
    audit: list[str] = []
    days: dict[str, DaySummary] = {}
    counts = {"sessions": 0, "children": 0, "local": 0, "unknown": 0}
    versions: set[str] = set()
    profiles: list[str] = []
    for name in iter_profiles(hermes_root):
        conn = open_read_only(db_path(hermes_root, name))
        try:
            p_audit: list[str] = []
            _probe_schema(conn, p_audit)
            v = _schema_version(conn)
            if v:
                versions.add(v)
            d, c = _accumulate(conn, since, until, local_model_allowlist)
            for k in counts:
                counts[k] += c[k]
            for day in d.values():
                tgt = days.get(day.day)
                if tgt is None:
                    days[day.day] = day
                else:
                    _merge_day(tgt, day)
            profiles.append(name)
            audit.extend(f"[{name}] {note}" for note in p_audit)
        finally:
            conn.close()
    if not profiles:
        audit.append("no local profiles with a session store found")
    elif not days:
        audit.append("no sessions in range across any profile (empty state, not an error)")
    numeric = [int(v) for v in versions if v.isdigit()]
    return Summary(
        profile_name="all",
        schema_version=str(max(numeric)) if numeric else (max(versions) if versions else None),
        since=since,
        until=until,
        days=sorted(days.values(), key=lambda d: d.day),
        total_sessions=counts["sessions"],
        total_subagent_sessions=counts["children"],
        local_candidate_sessions=counts["local"],
        unknown_route_sessions=counts["unknown"],
        audit_notes=audit,
        profiles=profiles,
    )


# ---------------------------------------------------------------------------
# Self-test (smoke, no pytest dependency)
# ---------------------------------------------------------------------------

def _selftest() -> int:
    """Build a synthetic WAL-mode state.db in a temp dir, then read it through
    the collector exactly as a profile's store would be read."""
    import json
    import tempfile

    failures: list[str] = []

    with tempfile.TemporaryDirectory(prefix="roi-selftest-") as tmp:
        root = Path(tmp) / ".hermes"
        (root / "profiles" / "demo").mkdir(parents=True)
        (root / "profiles" / "demo" / "config.yaml").write_text("profile: demo\n")
        (root / "config.yaml").write_text("profile: default\n")

        state = root / "profiles" / "demo" / "state.db"
        conn = sqlite3.connect(str(state))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(
            """
            CREATE TABLE schema_version (version TEXT);
            INSERT INTO schema_version VALUES ('32');
            CREATE TABLE sessions (
              id TEXT PRIMARY KEY, source TEXT, model TEXT, parent_session_id TEXT,
              started_at REAL, ended_at REAL, input_tokens INTEGER DEFAULT 0,
              output_tokens INTEGER DEFAULT 0, cache_read_tokens INTEGER DEFAULT 0,
              cache_write_tokens INTEGER DEFAULT 0, reasoning_tokens INTEGER DEFAULT 0,
              billing_provider TEXT, billing_base_url TEXT, billing_mode TEXT,
              estimated_cost_usd REAL, actual_cost_usd REAL, cost_status TEXT,
              api_call_count INTEGER DEFAULT 0
            );
            CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, content TEXT);
            """
        )
        # Local-timezone midnight anchor: keeps all in-range fixture rows on
        # one local calendar day regardless of the machine's UTC offset.
        from datetime import datetime as _dt
        now = (_dt.now().astimezone()
               .replace(hour=0, minute=0, second=0, microsecond=0)).timestamp()
        fixtures = [
            # root local session, loopback route
            ("s-root-local", "gui", "m-local", None, now, 1000, 500, 300, 0, 0, "custom", "http://127.0.0.1:8000/v1", 12),
            # subagent child, same route — counted exactly once, never into parent
            ("s-child", "subagent", "m-local", "s-root-local", now + 60, 100, 50, 0, 0, 0, "custom", "http://127.0.0.1:8000/v1", 2),
            # cloud session
            ("s-cloud", "cli", "gpt-x", None, now + 7200, 2000, 800, 100, 0, 200, "openai", "https://api.openai.com/v1", 30),
            # unknown route (NULL/NULL) — never priced
            ("s-unknown", "cron", "m-old", None, now + 14400, 700, 200, 0, 0, 0, None, None, 5),
            # out-of-range session (before `since`)
            ("s-old", "gui", "m-local", None, now - 86400 * 45, 50, 10, 0, 0, 0, "custom", "http://127.0.0.1:8000/v1", 1),
        ]
        conn.executemany(
            "INSERT INTO sessions (id, source, model, parent_session_id, started_at,"
            " input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, reasoning_tokens,"
            " billing_provider, billing_base_url, api_call_count) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            fixtures,
        )
        # raw user content must never be selectable through the collector
        conn.execute("INSERT INTO messages (session_id, content) VALUES ('s-root-local', 'SECRET USER TEXT')")
        conn.commit()
        conn.close()

        # --- 1. missing db -> FileNotFoundError, friendly ---
        try:
            open_read_only(root / "profiles" / "demo" / "missing.db")
            failures.append("missing db did not raise FileNotFoundError")
        except FileNotFoundError:
            pass

        # --- 2. cross-profile read: process HERMES_HOME pointed elsewhere ---
        import os
        os.environ["HERMES_HOME"] = str(root / "profiles" / "demo")  # deliberately set
        summary = summarize(root, "demo", since=now, until=now + 86400)
        os.environ.pop("HERMES_HOME", None)

        t = summary.totals
        if t["sessions"] != 4:
            failures.append(f"expected 4 sessions in range, got {t['sessions']}")
        if t["subagent_sessions"] != 1:
            failures.append(f"expected 1 subagent, got {t['subagent_sessions']}")
        if t["input_tokens"] != 1000 + 100 + 2000 + 700:
            failures.append(f"input mismatch: {t['input_tokens']}")
        if t["output_tokens"] != 500 + 50 + 800 + 200:
            failures.append(f"output mismatch: {t['output_tokens']}")
        if t["cache_read_tokens"] != 300 + 100:
            failures.append(f"cache_read mismatch: {t['cache_read_tokens']}")
        if t["reasoning_tokens"] != 200:
            failures.append(f"reasoning mismatch: {t['reasoning_tokens']}")
        # local = loopback rows only (1000+500+300 + 100+50) = 1950; unknown route 900; cloud 2900
        if t["local_tokens"] != 1950:
            failures.append(f"local_tokens mismatch: {t['local_tokens']}")
        if t["unknown_route_tokens"] != 900:
            failures.append(f"unknown_route_tokens mismatch: {t['unknown_route_tokens']}")
        if summary.schema_version != "32":
            failures.append(f"schema_version mismatch: {summary.schema_version!r}")
        if len(summary.days) != 1:
            failures.append(f"expected 1 day bucket, got {len(summary.days)}")

        # --- 3. read-only guarantee: write through collector connection fails ---
        conn2 = open_read_only(state)
        try:
            conn2.execute("INSERT INTO sessions (id) VALUES ('x')")
            failures.append("WRITE SUCCEEDED through a mode=ro connection!")
        except sqlite3.OperationalError:
            pass
        conn2.close()

        # --- 4. collector never touches messages (content leak check) ---
        import re
        source = Path(__file__).read_text(encoding="utf-8")
        if re.search(r"\bFROM\s+messages\b", source):
            failures.append("collector selects from messages table")

        # --- 5. range is inclusive-lower / exclusive-upper ---
        summary2 = summarize(root, "demo", since=now, until=now + 61)
        if summary2.total_sessions != 2:  # root + child only
            failures.append(f"range boundary: expected 2, got {summary2.total_sessions}")

        # --- 6. live WAL store: a second writer must not block the reader ---
        # Window covers only the 4 recent fixtures; s-old (45 days back) is out.
        writer = sqlite3.connect(str(state))
        conn3 = open_read_only(state)
        try:
            writer.execute("BEGIN")
            writer.execute("UPDATE sessions SET input_tokens = input_tokens + 1 WHERE id = 's-cloud'")
            counts = list(iter_sessions(conn3, since=now - 86400, until=now + 86400 * 2))
            if len(counts) != 4:
                failures.append(f"WAL concurrent read: expected 4 rows, got {len(counts)}")
            writer.rollback()
        finally:
            writer.close()
            conn3.close()

    out = {"failures": failures, "ok": not failures}
    print(json.dumps(out, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
