# Garmin -> AI notes

Pulls your own Garmin data (workouts plus sleep, HRV, resting HR, body battery,
stress, steps) into `garmin/`, as plain-English notes an AI coach can read.
Read-only: nothing is ever written back to your Garmin account.

Built on [python-garminconnect](https://github.com/cyberjunky/python-garminconnect) by cyberjunky.

## It already runs by itself

A Windows task called **Garmin morning sync** runs every day at 6:00 AM and
writes to `garmin/`. Your PC has to be on; if it was asleep at 6:00, the task
runs as soon as it wakes.

- See what happened: open `sync.log`
- Run it right now: double-click `run_sync.cmd`
- Change or remove the schedule: Start menu -> Task Scheduler -> Task Scheduler
  Library -> "Garmin morning sync"

## Das Dashboard

Vier Tabs:

- **Heute** -- Tagesform, Kacheln, was diese Woche zaehlt.
- **Koerper** -- HRV, Ruhepuls, Schlafphasen, Rhythmus, Stress, Alltagsbewegung.
- **Sport** -- pro Sportart: Staerken, Schwaechen, Verbesserungen, Verlauf, HF-Zonen
  und jede einzelne Einheit zum Aufklappen (Vergleich zu deinem Schnitt).
- **Ziel** -- Wettkampf eintragen (Sportart, Distanz, Zielzeit, Datum). Prognose aus
  deiner Puls-Tempo-Kurve, Machbarkeit, Trainingstempos, Wochenplan, Fortschritt.
  Das Ziel wird im Artifact gespeichert (db-Capability), lokal im Browser.

Jede Analyse endet mit einer konkreten Empfehlung.

- **Am PC:** `dashboard.html` doppelklicken -- funktioniert offline, wird bei jeder
  Synchronisierung neu gebaut.
- **Am Handy:** https://claude.ai/artifact/Cn5eBNaMmbE7AdtNu8ibgc
  (zeigt den Stand der letzten Veroeffentlichung, nicht live).

Selbst neu bauen: `py make_dashboard.py` (liest `garmin/data.json`, schreibt
`dashboard.html` fuer lokal und `dashboard_artifact.html` zum Veroeffentlichen).
Das Aussehen steckt in `dashboard_template.html`.

## Running it by hand

Open PowerShell in this folder, then:

```powershell
py sync_garmin.py --days 3               # pull 3 days into garmin/
py sync_garmin.py --days 30              # backfill a month
py sync_garmin.py --days 3 --dry-run     # just print, write nothing
```

## What you get

```text
garmin/
  daily/2026-09-16.md      one wellness note per day
  activities/...md         one note per workout
  data.json                the full store, updated each run
```

## If it stops working

Garmin has no public API, so the login is unofficial and can break when Garmin
changes it. Fix:

```powershell
py -m pip install -U garminconnect
py sync_garmin.py --login
```

`--login` must be run in a real terminal window -- the script refuses anywhere
your password can't be hidden as you type.

## Notes

- Sleep and HRV only appear for nights you actually wore the watch.
- Training readiness stays blank unless your watch computes it (newer
  Forerunner / Fenix / Venu models only). Everything else fills in regardless.
- Your login token lives in `C:\Users\User\.garminconnect` and is good for about
  a year. It is a credential: never post it, commit it, or paste it into a chat.
- These notes are plain text. If this folder ever ends up in OneDrive or
  Dropbox, they sync to that cloud too.
