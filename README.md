# Klubliga

Klubliga is a small web app for running the yearly tennis club league. Members
sign up, enter one or more competitions, get placed into groups, play their
matches whenever it suits them and type in the results themselves. The app
keeps the standings up to date and, once the group phase is over, schedules the
semi-finals and finals automatically.

It is built to be used on a phone at the courts: few pages, big buttons, no
app store, no password.

---

## The words we use

| Term           | Meaning |
|----------------|---------|
| **Season**     | One year of the league. The season is always the current calendar year; a new season starts by itself on January 1st. Old seasons stay viewable. |
| **Tournament** | One of the five competitions of a season: **Men's Singles**, **Women's Singles**, **Men's Doubles**, **Women's Doubles**, **Mixed Doubles**. |
| **Entry**      | Your participation in one tournament – either just you (singles) or you and a partner (doubles). You can have several entries per season, but only one per tournament. |
| **Group**      | Each tournament is played in one or two groups (*Group A*, *Group B*). Everybody in a group plays everybody else once. |
| **Match**      | One game between two entries. (We say *match* because in tennis a *game* is a part of a set.) |

You never pick a tournament directly: the app works it out from who is playing.
You alone → singles of your sex. You plus a partner → men's, women's or mixed
doubles.

---

## Getting started

### Signing up

1. Open the app and enter your email address.
2. If you are new, fill in first name, last name and sex (needed to put you in
   the right tournaments).
3. You receive an email with a **6-digit login code** and a **login link**.
   Type in the code or tap the link – you are in.

There are no passwords. Your device stays logged in for a year.

### Logging in on another device

Enter your email address on the new device. You get a fresh login code by
email; enter it on that device. Codes are valid for 30 minutes and can be used
once.

---

## The home page

Everything you need during the season is on the home page:

- **Season status** – whether entries are still open, whether the league has
  started, and whether the group phase is over.
- **My entries** – the tournaments you take part in, with your partner, your
  group and your status:
  - *Registered* – the league has not started yet.
  - *Group A / Group B* – you have been placed and can play.
  - *Waiting for admission* – you entered after the start; the organiser will
    add you to a group if possible.
  - You can **withdraw** an entry as long as the knockout stage of that
    tournament has not begun. Either partner of a doubles entry may do so.
- **New entry** – choose *Singles* or *Doubles* (with a partner from the list
  of members). The app shows which tournament this will be.
- **My groups** – the current standings of each group you play in.
- **My matches** – all your matches, open ones first. Tap a match to see the
  opponents' email addresses (to arrange a date) and to enter the result.

### Entering a result

Either side of a match may enter the score, set by set, from their own
perspective: the page always shows both names, so just fill in the games each
side won. The default format is **best of three sets, with a match tie-break
(first to 10) instead of a third set**. The organiser may change the format.

You can correct a result as long as the next round of that tournament has not
produced a result yet. After that, only the organiser can change it.

---

## The matches table

The **Matches** page shows one tournament at a time (choose it at the top):

1. The **group standings**.
2. The **knockout stage** (semi-finals and final), as far as it is known.
3. A list of **all matches**, which you can filter by group / stage, by
   open / finished, by player name, or limit to your own matches.

Use the season selector to look back at earlier years.

### How the standings are ranked

1. Number of matches won
2. Set difference
3. Game difference (a match tie-break counts as one game)
4. If exactly two entries are still level: the winner of their direct match
5. Alphabetical

A **walkover** counts as a win in straight sets, 6:0 each. Matches that the
organiser marks as **not played** do not count for anybody. Matches of an entry
that withdrew are struck out and do not count either.

### Knockout stage

- **One group:** the group winner and the runner-up play the **final**.
- **Two groups:** semi-finals *Winner A vs. Runner-up B* and *Winner B vs.
  Runner-up A*, then the final between the two semi-final winners.

The knockout matches appear in the players' match lists automatically as soon
as everything they depend on is decided – no need to wait for the organiser.

---

## For the organiser (admin)

Admins see two more pages, **Groups** and **Settings**, and extra buttons on the
**Matches** page.

### Before the start

1. Members create their entries.
2. On **Groups**, split each tournament into one or two groups – randomly with
   one click, or by hand by choosing a group for each entry. The page suggests
   one or two groups depending on the number of entries (configurable).
3. On **Settings**, check the match format and press **Start league**.

Group assignments are stable: adding, moving or removing an entry never
reshuffles the others. The match lists are updated automatically after every
change – new pairings are added, open matches that no longer make sense are
removed, already played ones are kept for the record.

### During the season

- **Late entries** show up on the Groups page as *waiting for admission*. Put
  them into a group and their matches are created right away.
- **Remove** an entry on the Groups page (same effect as a withdrawal).
- On the **Matches** page you can edit any result, record a **walkover** for
  either side, or mark a group match as **not played**.

### Closing the group phase

A group is finished when every one of its matches has a result or is marked as
not played. If you know that the remaining matches will not happen, close the
group phase:

- for **one group** (button under its standings),
- for **one tournament** (button at the top of the Matches page), or
- for **all tournaments** (on the Settings page).

Closing marks all open group matches as *not played*. The knockout matches are
then created automatically.

### Settings

| Setting | Default |
|---------|---------|
| League name (shown in the title bar) | Klubliga |
| Sets per match (best of 1, 3 or 5) | 3 |
| Games per set | 6 |
| Deciding set played as a match tie-break | yes |
| Points in the match tie-break | 10 |
| Suggest two groups from this many entries on | 8 |

Settings belong to a season. A new season starts with the settings of the
previous one.

---

## Running the app

Requirements: [uv](https://docs.astral.sh/uv/). Everything else (Python,
Django) is installed by uv. Data is stored in an SQLite file (`db.sqlite3`).

```bash
uv sync                                  # install dependencies
uv run manage.py migrate                 # create / update the database
uv run manage.py createsuperuser         # first admin (the password is never used)
uv run manage.py runserver               # http://127.0.0.1:8000/
```

During development, login emails are printed to the console instead of being
sent.

Useful commands:

```bash
uv run manage.py setadmin someone@example.com   # make an existing member admin
uv run manage.py setadmin someone@example.com --remove
uv run manage.py demo                    # fill the current season with demo data
uv run manage.py test                    # run the test suite
```

The same tasks are available as `just dev` and `just test` (see below).

The Django admin (raw database access for admins) is at `/django-admin/`.

### Configuration

Configuration is done through environment variables:

| Variable | Purpose | Default |
|----------|---------|---------|
| `DJANGO_SECRET_KEY` | Secret key – **must** be set in production | insecure dev key |
| `DJANGO_DEBUG` | `1` for development | `1` |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated host names | `localhost,127.0.0.1` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma-separated origins, e.g. `https://liga.example.org` | – |
| `DJANGO_TIME_ZONE` | Time zone (decides when a new season begins) | `Europe/Berlin` |
| `DJANGO_DB_PATH` | Location of the SQLite file | `./db.sqlite3` |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` | SMTP server. Without `EMAIL_HOST`, mails go to the console. | – |
| `DEFAULT_FROM_EMAIL` | Sender address of login mails | `klubliga@localhost` |

### Production

Deployment uses [just](https://just.systems/). Static files are collected,
compressed and served by the app itself via WhiteNoise; the app runs under
gunicorn.

```bash
cp .env.example .env      # then fill in secret key, host name, SMTP …
just deploy               # uv sync, migrate, collectstatic, deployment checks
just serve                # gunicorn on HOST:PORT (default 127.0.0.1:8000)
just up                   # both in one go
```

`just deploy` refuses to run unless `DJANGO_DEBUG=0`, and its checks fail if no
SMTP server (`EMAIL_HOST`) is configured, because nobody could log in.

In production the session and CSRF cookies are HTTPS-only, so put a reverse
proxy (e.g. Caddy or nginx) in front that terminates HTTPS, redirects HTTP to
HTTPS and forwards to gunicorn with the `X-Forwarded-Proto` header set. Static
files need no extra proxy configuration. To keep the app running, start
`just serve` from a systemd service in the project directory.

Other recipes: `just dev` (development server), `just test`, `just` (list).

More technical details are in [docs/SPECIFICATION.md](docs/SPECIFICATION.md).
