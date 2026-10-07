# Klubliga – Technical Specification

This document turns the original brief (`base-spec.md`) into a concrete design.
It covers the architecture, the domain model and its rules, the user
interface, the design decisions with their reasons, and the development plan.

## 1. Goals and constraints

- **Small and server-rendered.** Idiomatic Django with Django templates, plain
  HTML/CSS and a little vanilla JavaScript. No JS framework, no CSS framework.
  Where client-side behaviour is really needed, a native Web Component is used.
- **No extra packages.** The only runtime dependency is Django. Tests use
  Django's own test runner.
- **Tooling:** `uv` for Python and dependencies, the usual `manage.py`
  commands, SQLite as the database.
- **Mobile first.** Single-column layout that widens gracefully on desktop.
- **Password-less.** Users are identified by email and log in with one-time
  codes sent by email.
- **Seasons are automatic.** The season is the current calendar year in the
  configured time zone. Nothing has to be set up for a new year; all data of
  past seasons is kept and can be browsed.

## 2. Terminology

The brief asks for a better word than *team*, which sounds odd for a single
player. We use:

| Term | Definition |
|------|------------|
| Season | A calendar year. |
| Tournament | One of five competitions per season, defined by format and sex: `MS` men's singles, `WS` women's singles, `MD` men's doubles, `WD` women's doubles, `XD` mixed doubles. |
| Entry | One or two players taking part in one tournament of one season. Replaces *team*. |
| Group | A round-robin group (`A` or `B`) inside a tournament. |
| Match | A contest between two entries (the brief's *game*; in tennis a game is part of a set, so *match* avoids confusion). |
| Stage | `group`, `semi` (semi-final) or `final`. |

These words are used consistently in code, UI and documentation.

## 3. Architecture

```
klubliga/
├── pyproject.toml          uv project, single dependency: Django
├── manage.py
├── config/                 project package: settings, root urls, wsgi/asgi
├── accounts/               users and password-less login
│   ├── models.py           User (email-based), LoginToken
│   ├── services.py         token creation, verification, email sending
│   ├── views.py / forms.py login, register, code entry, link confirm, logout
│   └── management/commands/setadmin.py
├── league/                 the actual league
│   ├── models.py           Season, Group, Entry, Match (+ Tournament choices)
│   ├── scoring.py          pure functions: validate and evaluate scores
│   ├── standings.py        pure functions: group tables and ranking
│   ├── services.py         all state changes (entries, groups, results, KO)
│   ├── forms.py / views.py home, match, matches table, groups, settings
│   ├── context_processors.py   season + league name for the title bar
│   ├── templates/league/   page templates and partials
│   ├── static/league/      app.css, app.js (Web Component + small helpers)
│   └── management/commands/demo.py
└── docs/SPECIFICATION.md
```

### Layering

1. **Models** hold data and small derived properties only.
2. **`scoring` / `standings`** are pure Python (no database access) and
   therefore easy to unit test.
3. **`services`** is the only place that changes league state. Every function
   that changes groups, entries or results ends by calling
   `sync_tournament()`, which brings the derived data (group matches and
   knockout matches) in line. This single "reconcile" entry point keeps the
   match tables correct after *any* change.
4. **Views** check permissions, validate forms and call services. Templates
   only render.

### Configuration

`config/settings.py` reads environment variables (secret key, debug, hosts,
time zone, database path, SMTP). No settings package is needed. Without
`EMAIL_HOST` the console email backend is used.

## 4. Data model

```
User ──< Entry >── User (partner, optional)
          │
Season ──< Group ──< Entry
   │
   └────< Match >── Entry (entry1, entry2, winner)
             └──── Group (only for group matches)
```

### User (`accounts.User`)

Custom user model based on `AbstractUser` without `username`.

| Field | Notes |
|-------|-------|
| `email` | unique, login identifier (stored lower-case) |
| `first_name`, `last_name` | required |
| `sex` | `M` / `F` |
| `is_staff` | admin of the league (also gives access to the Django admin) |
| `last_login` | non-null means the email address has been confirmed |

Passwords are never set (unusable password). Only users who have logged in at
least once (confirmed email) can be chosen as a doubles partner.

### LoginToken (`accounts.LoginToken`)

| Field | Notes |
|-------|-------|
| `user` | FK |
| `code_hash` | SHA-256 of the 6-digit code |
| `link_hash` | SHA-256 of the random link token (URL-safe, 32 bytes) |
| `created_at`, `expires_at` | validity 30 minutes |
| `used_at` | set on successful use (single use) |
| `attempts` | wrong code entries; the token dies after 5 |

Only the newest token of a user is valid; requesting a new one invalidates
the older ones. A new code can be requested at most once per minute.

### Season (`league.Season`)

One row per year, created on first access (`Season.current()`), copying the
settings of the most recent earlier season.

| Field | Default | Notes |
|-------|---------|-------|
| `year` | – | unique |
| `name` | `Klubliga` | league name in the title bar |
| `best_of` | 3 | 1, 3 or 5 sets |
| `games_per_set` | 6 | |
| `deciding_match_tiebreak` | True | the deciding set is a match tie-break |
| `match_tiebreak_points` | 10 | |
| `two_groups_from` | 8 | suggestion threshold for the group split |
| `started_at` | null | set by "Start league" |

### Group (`league.Group`)

`season`, `tournament` (`MS/WS/MD/WD/XD`), `name` (`A`/`B`); unique together.
Groups are created on demand when the admin assigns an entry to them. A
tournament "has two groups" when both groups contain at least one active entry.

### Entry (`league.Entry`)

| Field | Notes |
|-------|-------|
| `season`, `tournament` | tournament is derived at creation, see below |
| `player1`, `player2` | `player2` empty for singles |
| `group` | null = not yet placed |
| `created_at`, `created_by` | |
| `withdrawn_at` | soft delete; set by a player or the admin |

**Tournament derivation** (the "implicit" definition from the brief):
singles → `MS`/`WS` by the player's sex; doubles → `MD` if both male,
`WD` if both female, otherwise `XD`.

**Rule:** a player can be in at most one *active* entry per tournament and
season (checked in the service layer).

**Status** (computed): `withdrawn`, `placed` (has a group), `registered`
(no group, league not started), `waiting` (no group, league started → needs
admission by the admin).

### Match (`league.Match`)

| Field | Notes |
|-------|-------|
| `season`, `tournament`, `stage` | stage: `group`, `semi`, `final` |
| `group` | only for group matches |
| `slot` | knockout position: semi 1 / semi 2 / final 1 |
| `entry1`, `entry2` | group matches store the lower entry id as `entry1` |
| `status` | `pending`, `played`, `walkover`, `cancelled` |
| `score` | text such as `6:4 3:6 10:8`, from `entry1`'s perspective |
| `winner` | FK to the winning entry (played and walkover) |
| `reported_by`, `reported_at` | audit |

A match is **resolved** when its status is not `pending`. A match is
**decided** when it has a winner (played or walkover).

A group match **counts** (for standings and completeness) when both entries
are active and both are still in the match's group. Matches that do not count
any more but already have a result are kept and shown struck through.

## 5. Domain rules

### 5.1 Scoring (`league/scoring.py`)

`ScoringRules(best_of, games_per_set, deciding_match_tiebreak,
match_tiebreak_points)`; `sets_to_win = best_of // 2 + 1`.

A regular set with `g = games_per_set` is valid when the winner has

- `g` games and the loser at most `g − 2`, or
- `g + 1` games and the loser `g − 1` or `g` (the latter = tie-break).

A match tie-break (`p = match_tiebreak_points`) is valid when the winner has at
least `p` points and leads by at least two, and – if the winner has more than
`p` – by exactly two.

A full score is valid when the sets are valid, no set follows after one side
reached `sets_to_win`, and one side did reach it. The deciding set is the set
played at `sets_to_win − 1 : sets_to_win − 1` (only for `best_of > 1`).

Evaluation returns the winning side, sets won and games won per side. A match
tie-break counts as one set and as one game (1:0) for the winner. A walkover
counts as `sets_to_win : 0` sets and `g : 0` games per set.

### 5.2 Standings (`league/standings.py`)

For every active entry of a group: played, won, lost, sets for/against, games
for/against, computed from the counting matches that are decided.

Ranking:
1. wins (desc), 2. set difference, 3. game difference,
4. head-to-head if exactly two entries are tied on 1–3,
5. entry name (alphabetical, for a stable order).

### 5.3 Group matches

`sync_group(group)` makes the stored matches match the group composition:

- every pair of active entries gets exactly one match (created if missing);
- pending matches whose pair no longer belongs to the group are deleted;
- resolved matches are never deleted (history).

Because matches are looked up by `(group, entry1, entry2)`, moving an entry
back into a group revives its old matches instead of duplicating them.

### 5.4 Group completeness and closing

A group is **complete** when it has at least two active entries and every
counting match is resolved. Closing the group phase (group, tournament or
everything) sets all pending counting group matches to `cancelled`
("not played"). There is no separate "closed" flag: completeness is derived
from the matches, so a group can never be "closed" and "incomplete" at the
same time.

### 5.5 Knockout stage

`sync_knockout(season, tournament)` computes the desired pairings:

- exactly one non-empty group, complete, ≥ 2 entries →
  final: 1st vs 2nd;
- two non-empty groups, both complete, each ≥ 2 entries →
  semi 1: A1 vs B2, semi 2: B1 vs A2; final once both semis are decided:
  winner semi 1 vs winner semi 2.

For each slot (semi 1, semi 2, final):

- desired pairing and no match → create it;
- desired pairing differs from a pending match → update its entries;
- no desired pairing and a pending match exists → delete it;
- matches with a result are never changed or deleted.

Knockout matches only exist once both opponents are known; the matches page
shows placeholders ("Winner A – Runner-up B") for the rest.

### 5.6 Locks and permissions

| Action | Who | Condition |
|--------|-----|-----------|
| Create entry | any user | for themselves (+ confirmed partner) |
| Withdraw entry | either player, admin | entry not yet in a knockout match |
| Enter / edit result | participants | league started, match counts / is a KO match, status `pending` or `played`, not locked |
| Edit result, walkover, not played | admin | always ("not played" only for group matches) |
| Assign / move / remove entries, random split | admin | random split only while the tournament has no results |
| Settings, start league, close group phases | admin | |

A match is **locked** for players when the following stage already has a
decided match: group matches are locked once a semi-final or final of the
tournament is decided, semi-finals once the final is decided.

### 5.7 Random split

Shuffles all active entries of the tournament and deals them alternately into
the requested number of groups (1 or 2), so that group sizes differ by at most
one. Suggested number: 2 if the tournament has at least `two_groups_from`
entries, otherwise 1.

## 6. Pages and URLs

| URL | Page | Access |
|-----|------|--------|
| `/login/` | email form | public |
| `/register/` | registration form | public |
| `/login/code/` | enter the emailed code | public |
| `/login/link/<token>/` | confirm button for the emailed link (POST logs in; protects against mail scanners that pre-open links) | public |
| `/logout/` | POST | user |
| `/` | home: season status, my entries, new entry, my groups, my matches | user |
| `/entries/<id>/withdraw/` | POST | player/admin |
| `/matches/` | matches table: tournament tabs, season selector, standings, knockout, filtered match list | user |
| `/matches/<id>/` | match detail and result form (admin: status options) | user |
| `/matches/close/` | POST: close group phase of a group / tournament / all | admin |
| `/groups/` | group configuration per tournament | admin |
| `/settings/` | season settings and start | admin |
| `/django-admin/` | Django admin (login redirects to our login) | admin |

### UI notes

- Header: league name, season year, user name; navigation Home · Matches ·
  (Groups · Settings) · Logout.
- One stylesheet with CSS custom properties, light/dark via
  `prefers-color-scheme`, system fonts, touch-sized controls.
- `app.js` provides
  - `<score-input>` – Web Component around the set inputs: shows the deciding
    set only when the sets are level, labels it as match tie-break and tells
    the user who has won;
  - `data-confirm` on buttons for confirmation dialogs;
  - `data-autosubmit` on filter forms.
  Every page works without JavaScript.

## 7. Design decisions

| Decision | Reason |
|----------|--------|
| One-time codes instead of a permanent "magic string" | A permanent secret sent by email is effectively a password in plain text. A fresh code per login fulfils the same flow (email + string on a new device) and is safer. Long-lived sessions (1 year) mean users rarely need a code. |
| Link opens a confirm page, POST logs in | Mail security scanners open links; a GET login would burn the single-use token. |
| Settings stored on `Season` | Each season keeps the rules it was played with; history stays correct when rules change. Copying the previous season's settings keeps "no setup needed". |
| `Season.current()` creates rows lazily | The year is fully automatic as required. |
| Tournament stored on `Entry` and `Match` | It is derived once from sex and format (still "implicit" for the user) but stored for simple, indexed queries. |
| Soft-withdraw instead of delete | Results of the season stay reviewable. |
| Reconcile function (`sync_tournament`) instead of event-specific updates | One idempotent function after every change is simpler and more robust than special cases for add / move / withdraw / result. |
| Completeness derived, no "closed" flag | Fewer states, no contradictions. |
| Knockout matches created only with both opponents known | A match always has two real entries; placeholders are a view concern. |
| Score as text plus `winner` FK | Readable, easy to validate in pure Python; the winner FK makes queries simple. Set/game numbers are recomputed when needed (tiny data volume). |
| Two apps (`accounts`, `league`) | Clear split between identity and league logic, idiomatic Django. |
| No i18n in the first version | English UI keeps the code small; texts are concentrated in templates and can be wrapped for translation later. |

## 8. Testing strategy

Django's test runner (`uv run manage.py test`), no extra packages.

- `league/tests/test_scoring.py` – valid/invalid sets, tie-breaks, match
  tie-break, too many / too few sets, other formats (best of 1/5, short sets).
- `league/tests/test_standings.py` – ranking order, head-to-head, walkovers,
  non-counting matches.
- `league/tests/test_models.py` – season creation and copying, tournament
  derivation, entry status, match properties.
- `league/tests/test_services.py` – entry creation rules, withdrawal, group
  sync (add/move/withdraw/revive), random split, results and locks, closing,
  knockout for one and two groups including updates.
- `league/tests/test_views.py` – access control, all pages render, main form
  flows.
- `accounts/tests.py` – user manager, token lifecycle (expiry, attempts,
  single use, newest-only, rate limit), registration and login flows, email
  content.

## 9. Development plan

Each step ends with a commit.

1. **Docs** – README (users) and this specification.
2. **Scaffold** – `uv init`, Django dependency, project `config`, apps,
   settings from environment, base template and stylesheet.
3. **Accounts** – user model, login tokens, login/register/code/link views,
   email templates, `setadmin` command, Django admin login redirect.
4. **League models** – Season, Group, Entry, Match, migrations, admin.
5. **Domain logic** – `scoring`, `standings`, `services`.
6. **Home page** – status, entries, new entry form, withdraw, my groups,
   my matches; match detail and result form with `<score-input>`.
7. **Matches table** – tournament tabs, season selector, standings,
   knockout view, filters, admin actions (close group/tournament).
8. **Admin pages** – Groups configuration and Settings.
9. **Demo data** – `demo` management command.
10. **Tests** – full unit and view test suite, fixes found by it.
11. **Final review** – documentation updated to match the result.
