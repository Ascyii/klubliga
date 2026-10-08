# Code Review

Reviewed revision: `9b6cdfb` (2026-10-08). Scope: the whole codebase
(`accounts`, `league`, `config`, templates, `app.js`, `justfile`).
Only real defects are listed. Cosmetics, style and missing features are out
of scope. The test suite passes (109 tests); every finding marked
*reproduced* was confirmed against a scratch database built with
`manage.py demo`.

## Major

### M1. Changing the rules mid-season silently rewrites existing standings

`league/standings.py:46`, `league/scoring.py:93`, `league/scoring.py:120-126`,
`league/templates/league/settings.html:52`

Stored scores are re-evaluated with the season's *current* rules each time the
standings are computed. `summarize()` uses `rules.is_tiebreak_set(index)` to
decide whether a set is a match tie-break (counted as 1 game) or a regular
set (counted as its games). `walkover_outcome()` uses the current
`games_per_set` and `best_of`.

If the admin changes `deciding_match_tiebreak`, `best_of` or `games_per_set`
after results exist, every earlier result is counted again under the new
rules. *Reproduced:* switching off `deciding_match_tiebreak` changed a
team's games from `19:26` to `28:31`, because the old `5:10` match tie-break
now counts as 15 games. Game difference is a ranking criterion, so the
change can reorder a group. `sync_knockout()` then re-pairs pending
semi-finals or finals.

The settings page says *"Changes apply to results entered from now on"*.
That statement is false for standings and knockout qualification.

### M2. Players can withdraw entries from past seasons and change archived results

`league/views.py:87-99`, `league/services.py:53-61`

`can_withdraw()` requires `entry.season.is_current`, but only the templates
use it to hide the button. The `withdraw` view and `withdraw_entry()` check
only that the entry is active and not in a knockout match. Any player of a
past-season entry (one that did not reach the knockout stage) can send the
POST and withdraw it. Its resolved group matches then stop counting, and
`sync_tournament()` runs on the archived tournament.

*Reproduced:* after a past-season withdrawal, the group leader's wins went
from 2 to 1 and the entry disappeared from the table. The brief requires
that scores at the end of a season stay as they were for later review.

### M3. Editing matches or entries in the Django admin bypasses validation and synchronisation, and can break public pages

`league/admin.py:17-32`, `league/standings.py:46`

`MatchAdmin` and `EntryAdmin` allow free editing of `score`, `status`,
`winner`, `entry1/2`, `group` and `withdrawn_at`. These writes skip
`services`:

- No score validation. A score that `parse_score()` cannot read (e.g.
  `6:4 6:3 ret.`) raises an unhandled `ScoreError` while standings are
  computed. *Reproduced:* `/matches/` returns HTTP 500 for every user, and
  so does the home page of every member of that group.
- `score` and `winner` can contradict each other, and the status may be
  `played` with no winner.
- `sync_tournament()` does not run. Group matches and knockout pairings are
  left stale after a group change, a withdrawal or a result change.

The Django admin is reachable for every league admin (`setadmin` grants
`is_staff`), so a single typo is enough.

## Minor

### m1. Open redirect in the Django-admin login hook

`accounts/admin.py:12-15`

For an authenticated staff user, `admin_login` redirects to `?next=` without
`url_has_allowed_host_and_scheme`. *Reproduced:*
`/django-admin/login/?next=https://evil.example/` returns a 302 to
`https://evil.example/`. This only affects staff users who follow a crafted
link.

### m2. Withdrawals after a decided knockout match make tables and bracket disagree

`league/services.py:53-61` (compare `assign_groups`, `league/services.py:92`)

`assign_groups()` blocks group changes once the knockout stage has a result.
`withdraw_entry()` blocks only entries that are themselves in a knockout
match. If a group entry outside the knockout withdraws after a semi-final or
final is decided, its group results stop counting and the group table is
recomputed. The decided knockout matches keep the old qualifiers. The table
can then show a semi-finalist outside the top two, and the history is
changed after the fact.

### m3. Duplicate active entries are possible through a double submit

`league/services.py:29-42`, `league/models.py:156-158`

The rule "at most one active entry per player, tournament and season" is
enforced only by an `exists()` check followed by `create()`. There is no
database constraint and no lock. Two concurrent POSTs (a double tap on
*Enter*, or both partners registering the same pair at the same time) both
pass the check and create two entries. Each entry then gets its own set of
group matches.

### m4. Registration sends email to any address without a global limit

`accounts/views.py:58-76`, `accounts/services.py:21-41`

Anyone can register any email address. This creates a user and sends a mail
from the club's SMTP account. The only throttle is one mail per address per
minute. There is no limit per client or in total, so the endpoint can send
mail in bulk to third-party addresses. That risks getting the club's sender
blocklisted.

### m5. Strangers can overwrite unconfirmed accounts

`accounts/views.py:63-69`

Re-registering with the address of any unconfirmed user (`last_login IS NULL`)
replaces that user's first name, last name and sex. The code assumes the same
person is correcting a typo, but no proof of ownership is required. This also
applies to accounts the admin created in the Django admin, or promoted with
`setadmin`, before their first login. Sex determines the tournament of new
entries.

### m6. A missing production secret falls back to a public key

`config/settings.py:16-19`, `justfile:28-38`

With `DJANGO_DEBUG=0` and no `DJANGO_SECRET_KEY`, the app runs with the
hard-coded `django-insecure-…` key from the repository. `just deploy` runs
`check --deploy`, but that check only warns (`security.W009`), so the
deployment continues. `DEBUG` also defaults to on: `just serve` started
without a `.env` file runs in debug mode, with tracebacks shown to visitors.
