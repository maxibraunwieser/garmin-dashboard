#!/usr/bin/env python3
"""
sync_garmin.py -- pull your own Garmin data into plain-text notes your AI can read.

Read-only. Nothing is ever written back to your Garmin account.

Built on the open-source python-garminconnect library by cyberjunky:
https://github.com/cyberjunky/python-garminconnect

Usage
-----
  python sync_garmin.py --login                 one-time login (hidden password prompt)
  python sync_garmin.py --days 3 --dry-run      test: print the last 3 days
  python sync_garmin.py --days 3                write ./garmin/ notes
  python sync_garmin.py --export-ci-token       only if you use GitHub Actions

Security
--------
  * The password is typed once into a hidden prompt and is never stored, never
    placed in an environment variable, and never printed.
  * The script refuses to run --login where the password cannot be hidden.
  * The login token is saved privately on this machine and never printed.
"""

import argparse
import base64
import getpass
import json
import os
import re
import stat
import sys
import warnings
from datetime import date, datetime, timedelta

TOKEN_DIR = os.path.join(os.path.expanduser("~"), ".garminconnect")
CI_TOKEN_FILE = "garmin-ci-token.txt"


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def dig(obj, *keys, default=None):
    """Walk nested dicts/lists safely: dig(d, 'a', 'b') -> d['a']['b'] or default."""
    cur = obj
    for key in keys:
        if isinstance(cur, dict):
            cur = cur.get(key)
        elif isinstance(cur, list) and isinstance(key, int) and len(cur) > key:
            cur = cur[key]
        else:
            return default
        if cur is None:
            return default
    return cur


def slug(text, limit=40):
    text = re.sub(r"[^a-zA-Z0-9]+", "-", (text or "activity").strip().lower())
    return text.strip("-")[:limit] or "activity"


def hhmm(seconds):
    if not seconds:
        return None
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return "{}:{:02d}:{:02d}".format(h, m, s) if h else "{}:{:02d}".format(m, s)


def pace_per_km(distance_m, duration_s):
    if not distance_m or not duration_s or distance_m < 100:
        return None
    secs = duration_s / (distance_m / 1000.0)
    return "{}:{:02d}".format(int(secs // 60), int(secs % 60))


def ask(prompt):
    """Read a line from the terminal, or raise EOFError if there is none."""
    return input(prompt)


def private_dir(path):
    os.makedirs(path, exist_ok=True)
    if os.name != "nt":
        try:
            os.chmod(path, stat.S_IRWXU)  # 0700, owner only
        except OSError:
            pass
    return path


# --------------------------------------------------------------------------
# authentication
# --------------------------------------------------------------------------

def _import_garmin():
    try:
        from garminconnect import Garmin
    except ImportError:
        sys.exit("The garminconnect library is missing. Run:  pip install -r requirements.txt")
    return Garmin


def save_token(client):
    """Persist the login token. Works with garminconnect 0.3.x and older garth builds."""
    private_dir(TOKEN_DIR)
    inner = getattr(client, "client", None)
    if inner is not None and hasattr(inner, "dump"):
        inner.dump(TOKEN_DIR)          # 0.3.x: writes garmin_tokens.json
    elif hasattr(client, "garth"):
        client.garth.dump(TOKEN_DIR)   # older garth-based versions
    else:
        sys.exit("This garminconnect version exposes no way to save the token.")


def do_login():
    """One-time interactive login. Saves a token; prints nothing sensitive."""
    Garmin = _import_garmin()

    not_a_terminal = (
        "Refusing to log in here: this is not a real terminal, so your password\n"
        "could not be hidden as you type it. Open Terminal (Mac) or PowerShell\n"
        "(Windows), go to this folder, and run:  python sync_garmin.py --login"
    )
    if not sys.stdin.isatty():
        sys.exit(not_a_terminal)

    try:
        email = ask("Garmin email: ").strip()
        # getpass warns instead of hiding when it has no real terminal to read
        # from. Treat that warning as a hard stop: no echoed passwords, ever.
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            password = getpass.getpass("Garmin password (hidden, nothing will appear): ")
    except (EOFError, getpass.GetPassWarning):
        sys.exit(not_a_terminal)

    if not email or not password:
        sys.exit("Email and password are both required.")

    try:
        try:
            client = Garmin(email=email, password=password, is_cn=False, return_on_mfa=True)
        except TypeError:  # older library signature
            client = Garmin(email, password)
        result = client.login()

        state, extra = result if isinstance(result, tuple) else (result, None)
        if state == "needs_mfa":
            code = ask("Garmin sent a 2FA code. Enter it here: ").strip()
            client.resume_login(extra, code)
    finally:
        del password  # not stored, not logged, not exported

    save_token(client)
    print("\nLogged in. Token saved privately in {} (not shown here).".format(TOKEN_DIR))
    print("It lasts about a year. You should not need to log in again until then.")
    return client


def connect():
    """Resume a saved session, or a CI token from GARMIN_TOKEN_B64."""
    Garmin = _import_garmin()
    client = Garmin()

    blob = os.environ.get("GARMIN_TOKEN_B64")
    if blob:
        private_dir(TOKEN_DIR)
        bundle = json.loads(base64.b64decode(blob).decode())
        for name, content in bundle.items():
            with open(os.path.join(TOKEN_DIR, name), "w", encoding="utf-8") as fh:
                fh.write(content)

    if not os.path.isdir(TOKEN_DIR) or not os.listdir(TOKEN_DIR):
        sys.exit("No saved login found. Run:  python sync_garmin.py --login")

    try:
        client.login(TOKEN_DIR)
    except Exception as exc:  # expired or invalidated token
        sys.exit(
            "Could not resume your Garmin session ({}).\n"
            "The token may have expired. Run:  python sync_garmin.py --login".format(
                type(exc).__name__)
        )
    return client


def export_ci_token():
    """Bundle the token files for a GitHub Actions secret (Path A only)."""
    if not os.path.isdir(TOKEN_DIR):
        sys.exit("No saved login found. Run:  python sync_garmin.py --login")
    bundle = {}
    for name in sorted(os.listdir(TOKEN_DIR)):
        path = os.path.join(TOKEN_DIR, name)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as fh:
                bundle[name] = fh.read()
    if not bundle:
        sys.exit("The token folder is empty. Run:  python sync_garmin.py --login")

    encoded = base64.b64encode(json.dumps(bundle).encode()).decode()
    with open(CI_TOKEN_FILE, "w", encoding="utf-8") as fh:
        fh.write(encoded)
    if os.name != "nt":
        os.chmod(CI_TOKEN_FILE, stat.S_IRUSR | stat.S_IWUSR)
    print("Wrote {}. Paste its contents into the GARMIN_TOKEN_B64 secret,".format(CI_TOKEN_FILE))
    print("then delete the file. It is a login credential -- never commit or share it.")


# --------------------------------------------------------------------------
# fetching
# --------------------------------------------------------------------------

def fetch_profile(client):
    """Age, size and training preferences -- needed to read heart rate sensibly."""
    settings = quiet(client.connectapi, "/userprofile-service/userprofile/user-settings") or {}
    ud = settings.get("userData") or {}
    weight_g = ud.get("weight")
    return {
        "birth_date": ud.get("birthDate"),
        "gender": ud.get("gender"),
        "height_cm": ud.get("height"),
        "weight_kg": round(weight_g / 1000.0, 1) if weight_g else None,
        "vo2max_running": ud.get("vo2MaxRunning"),
        "vo2max_cycling": ud.get("vo2MaxCycling"),
        "lactate_threshold_hr": ud.get("lactateThresholdHeartRate"),
        "lactate_threshold_speed": ud.get("lactateThresholdSpeed"),
        "long_training_days": ud.get("preferredLongTrainingDays"),
        "available_training_days": ud.get("availableTrainingDays"),
    }


def quiet(fn, *args, **kwargs):
    """Call an endpoint; return None instead of exploding if Garmin has no data."""
    try:
        return fn(*args, **kwargs)
    except Exception:
        return None


def fetch_activities(client, start, end):
    raw = quiet(client.get_activities_by_date, start.isoformat(), end.isoformat()) or []
    out = []
    for act in raw:
        start_local = act.get("startTimeLocal") or ""
        out.append({
            "id": act.get("activityId"),
            "name": act.get("activityName") or "Activity",
            "type": dig(act, "activityType", "typeKey", default="unknown"),
            "start_local": start_local,
            "date": start_local[:10] or end.isoformat(),
            "distance_m": act.get("distance"),
            "duration_s": act.get("duration"),
            "moving_duration_s": act.get("movingDuration"),
            "avg_hr": act.get("averageHR"),
            "max_hr": act.get("maxHR"),
            "calories": act.get("calories"),
            "elevation_gain_m": act.get("elevationGain"),
            "elevation_loss_m": act.get("elevationLoss"),
            "avg_speed_ms": act.get("averageSpeed"),
            "max_speed_ms": act.get("maxSpeed"),
            "gap_speed_ms": act.get("avgGradeAdjustedSpeed"),
            "training_effect_aerobic": act.get("aerobicTrainingEffect"),
            "training_effect_anaerobic": act.get("anaerobicTrainingEffect"),
            "training_effect_label": act.get("trainingEffectLabel"),
            # running dynamics
            "cadence_spm": act.get("averageRunningCadenceInStepsPerMinute"),
            "stride_cm": act.get("avgStrideLength"),
            "ground_contact_ms": act.get("avgGroundContactTime"),
            "vertical_osc_cm": act.get("avgVerticalOscillation"),
            "vertical_ratio": act.get("avgVerticalRatio"),
            "steps": act.get("steps"),
            "avg_power_w": act.get("avgPower"),
            "norm_power_w": act.get("normPower"),
            "vo2max": act.get("vO2MaxValue"),
            "temp_max_c": act.get("maxTemperature"),
            # seconds per heart-rate zone, straight from the activity payload
            "hr_zones_s": [act.get("hrTimeInZone_" + str(z)) for z in range(1, 6)],
        })
    return out


def clock(epoch_ms):
    """Garmin's *Local timestamps are already shifted, so read them as UTC."""
    if not epoch_ms:
        return None
    try:
        return datetime.utcfromtimestamp(epoch_ms / 1000.0).strftime("%H:%M")
    except (ValueError, OSError, OverflowError):
        return None


def hours(seconds):
    return round(seconds / 3600.0, 2) if seconds else None


def fetch_wellness_day(client, day):
    cdate = day.isoformat()
    stats = quiet(client.get_stats, cdate) or {}
    sleep = quiet(client.get_sleep_data, cdate) or {}
    hrv = quiet(client.get_hrv_data, cdate) or {}
    stress = quiet(client.get_stress_data, cdate) or {}
    readiness = quiet(client.get_training_readiness, cdate)
    maxmet = quiet(client.get_max_metrics, cdate)

    dto = dig(sleep, "dailySleepDTO", default={}) or {}
    sleep_seconds = dto.get("sleepTimeSeconds")
    bb_low = stats.get("bodyBatteryLowestValue")
    bb_high = stats.get("bodyBatteryHighestValue")
    if bb_low is None and bb_high is None:
        bb = quiet(client.get_body_battery, cdate) or []
        bb_low = dig(bb, 0, "bodyBatteryDrainedValue")
        bb_high = dig(bb, 0, "bodyBatteryChargedValue")

    return {
        "date": cdate,
        "resting_hr": stats.get("restingHeartRate"),
        "resting_hr_7d": stats.get("lastSevenDaysAvgRestingHeartRate"),
        "hrv_ms": dig(hrv, "hrvSummary", "lastNightAvg"),
        "hrv_status": dig(hrv, "hrvSummary", "status"),
        "hrv_baseline_low": dig(hrv, "hrvSummary", "baseline", "lowUpper"),
        "hrv_baseline_high": dig(hrv, "hrvSummary", "baseline", "balancedUpper"),
        "sleep_hours": round(sleep_seconds / 3600.0, 1) if sleep_seconds else None,
        "sleep_score": dig(sleep, "dailySleepDTO", "sleepScores", "overall", "value"),
        # sleep architecture
        "sleep_deep_h": hours(dto.get("deepSleepSeconds")),
        "sleep_light_h": hours(dto.get("lightSleepSeconds")),
        "sleep_rem_h": hours(dto.get("remSleepSeconds")),
        "sleep_awake_h": hours(dto.get("awakeSleepSeconds")),
        "bed_time": clock(dto.get("sleepStartTimestampLocal")),
        "wake_time": clock(dto.get("sleepEndTimestampLocal")),
        "sleep_hr": dto.get("avgHeartRate"),
        "sleep_stress": dto.get("avgSleepStress"),
        "sleep_feedback": dto.get("sleepScoreFeedback"),
        "respiration": dto.get("averageRespirationValue") or stats.get("avgWakingRespirationValue"),
        "spo2": dto.get("averageSpO2Value") or stats.get("averageSpo2"),
        "body_battery_low": bb_low,
        "body_battery_high": bb_high,
        "bb_at_wake": stats.get("bodyBatteryAtWakeTime"),
        "bb_during_sleep": stats.get("bodyBatteryDuringSleep"),
        "stress_avg": stress.get("avgStressLevel", stats.get("averageStressLevel")),
        "stress_rest_s": stats.get("restStressDuration"),
        "stress_low_s": stats.get("lowStressDuration"),
        "stress_med_s": stats.get("mediumStressDuration"),
        "stress_high_s": stats.get("highStressDuration"),
        "steps": stats.get("totalSteps"),
        "step_goal": stats.get("dailyStepGoal"),
        "floors": stats.get("floorsAscended"),
        "intensity_moderate": stats.get("moderateIntensityMinutes"),
        "intensity_vigorous": stats.get("vigorousIntensityMinutes"),
        "intensity_goal": stats.get("intensityMinutesGoal"),
        "active_seconds": stats.get("activeSeconds"),
        "sedentary_seconds": stats.get("sedentarySeconds"),
        "hr_max_day": stats.get("maxHeartRate"),
        "hr_min_day": stats.get("minHeartRate"),
        "training_readiness": dig(readiness, 0, "score"),
        "calories_total": stats.get("totalKilocalories"),
        "calories_active": stats.get("activeKilocalories"),
        "calories_bmr": stats.get("bmrKilocalories"),
        "vo2max": dig(maxmet, 0, "generic", "vo2MaxPreciseValue"),
    }


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

def render_wellness(w):
    lines = ["# Garmin wellness {}".format(w["date"])]

    def add(label, value, suffix=""):
        if value is not None:
            lines.append("- {}: {}{}".format(label, value, suffix))

    add("Resting HR", w["resting_hr"], " bpm")
    add("HRV (overnight)", w["hrv_ms"], " ms")
    if w["sleep_hours"] is not None:
        score = " (score {})".format(w["sleep_score"]) if w["sleep_score"] is not None else ""
        lines.append("- Sleep: {} h{}".format(w["sleep_hours"], score))
    if w.get("sleep_deep_h") is not None:
        lines.append("- Sleep stages: {} h deep / {} h light / {} h REM / {} h awake".format(
            w["sleep_deep_h"], w.get("sleep_light_h"), w.get("sleep_rem_h"), w.get("sleep_awake_h")))
    if w.get("bed_time"):
        lines.append("- In bed {} -> up {}".format(w["bed_time"], w.get("wake_time")))
    add("Sleeping HR", w.get("sleep_hr"), " bpm")
    add("Respiration", w.get("respiration"), " /min")
    add("SpO2", w.get("spo2"), " %")
    if w["body_battery_low"] is not None or w["body_battery_high"] is not None:
        lines.append("- Body battery: {} -> {}".format(w["body_battery_low"], w["body_battery_high"]))
    add("Stress (avg)", w["stress_avg"])
    add("Steps", w["steps"])
    if w.get("intensity_vigorous") is not None or w.get("intensity_moderate") is not None:
        lines.append("- Intensity minutes: {} vigorous / {} moderate (goal {}/week)".format(
            w.get("intensity_vigorous"), w.get("intensity_moderate"), w.get("intensity_goal")))
    add("VO2max", w.get("vo2max"))
    add("Training readiness", w["training_readiness"])
    if len(lines) == 1:
        lines.append("- No wellness data recorded (watch probably not worn).")
    return "\n".join(lines) + "\n"


def render_activity(a):
    lines = ["# {} -- {}".format(a["name"], a["date"]), "- Type: {}".format(a["type"])]
    if a["start_local"]:
        lines.append("- Start: {}".format(a["start_local"]))
    if a["distance_m"]:
        lines.append("- Distance: {:.2f} km".format(a["distance_m"] / 1000.0))
    if a["duration_s"]:
        lines.append("- Duration: {}".format(hhmm(a["duration_s"])))
    pace = pace_per_km(a["distance_m"], a["moving_duration_s"] or a["duration_s"])
    if pace:
        lines.append("- Pace: {} /km".format(pace))
    if a["avg_hr"]:
        mx = " (max {})".format(round(a["max_hr"])) if a["max_hr"] else ""
        lines.append("- Avg HR: {} bpm{}".format(round(a["avg_hr"]), mx))
    if a["elevation_gain_m"]:
        lines.append("- Elevation gain: {} m".format(round(a["elevation_gain_m"])))
    if a["calories"]:
        lines.append("- Calories: {}".format(round(a["calories"])))
    if a["training_effect_aerobic"]:
        label = " ({})".format(a["training_effect_label"].replace("_", " ").lower()) \
            if a.get("training_effect_label") else ""
        lines.append("- Training effect: {:.1f} aerobic / {:.1f} anaerobic{}".format(
            a["training_effect_aerobic"], a.get("training_effect_anaerobic") or 0.0, label))
    if a.get("cadence_spm"):
        lines.append("- Cadence: {} spm, stride {} cm".format(
            round(a["cadence_spm"]), round(a["stride_cm"]) if a.get("stride_cm") else "?"))
    if a.get("ground_contact_ms"):
        lines.append("- Ground contact: {} ms, vertical ratio {:.1f}%".format(
            round(a["ground_contact_ms"]), a.get("vertical_ratio") or 0.0))
    zones = [z for z in (a.get("hr_zones_s") or []) if z]
    if zones:
        mins = ["Z{}: {} min".format(i + 1, round((z or 0) / 60.0))
                for i, z in enumerate(a["hr_zones_s"]) if z]
        lines.append("- HR zones: " + ", ".join(mins))
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# sinks
# --------------------------------------------------------------------------

def write_files(out_dir, activities, wellness, profile=None):
    daily_dir = os.path.join(out_dir, "daily")
    act_dir = os.path.join(out_dir, "activities")
    os.makedirs(daily_dir, exist_ok=True)
    os.makedirs(act_dir, exist_ok=True)

    for w in wellness:
        with open(os.path.join(daily_dir, w["date"] + ".md"), "w", encoding="utf-8") as fh:
            fh.write(render_wellness(w))
    for a in activities:
        name = "{}-{}-{}.md".format(a["date"], slug(a["name"]), a["id"])
        with open(os.path.join(act_dir, name), "w", encoding="utf-8") as fh:
            fh.write(render_activity(a))

    store_path = os.path.join(out_dir, "data.json")
    store = {"activities": {}, "wellness": {}}
    if os.path.exists(store_path):
        try:
            with open(store_path, "r", encoding="utf-8") as fh:
                store = json.load(fh)
        except (json.JSONDecodeError, OSError):
            pass
    store.setdefault("activities", {})
    store.setdefault("wellness", {})
    for a in activities:
        store["activities"][str(a["id"])] = a
    for w in wellness:
        store["wellness"][w["date"]] = w
    if profile:
        store["profile"] = profile
    store["last_sync"] = datetime.now().isoformat(timespec="seconds")
    with open(store_path, "w", encoding="utf-8") as fh:
        json.dump(store, fh, indent=2, sort_keys=True)

    print("Wrote {} daily note(s) and {} activity note(s) to {}".format(
        len(wellness), len(activities), out_dir))


def post_to_endpoint(activities, wellness, profile=None):
    import requests
    url = os.environ.get("GARMIN_INGEST_URL")
    secret = os.environ.get("GARMIN_INGEST_SECRET") or os.environ.get("SESSION_LOG_SECRET")
    if not url:
        sys.exit("Set GARMIN_INGEST_URL to use --sink supabase.")
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["Authorization"] = "Bearer " + secret
    resp = requests.post(url, json={"activities": activities, "wellness": wellness,
                                    "profile": profile or {}},
                         headers=headers, timeout=30)
    print("POST {} -> {}".format(url, resp.status_code))
    resp.raise_for_status()


def print_preview(activities, wellness):
    for w in wellness:
        print(render_wellness(w))
    if activities:
        for a in activities:
            print(render_activity(a))
    else:
        print("(no activities in this window)\n")


# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Pull your Garmin data into readable notes.")
    parser.add_argument("--login", action="store_true", help="one-time interactive login")
    parser.add_argument("--export-ci-token", action="store_true",
                        help="write the token bundle for a GitHub Actions secret")
    parser.add_argument("--days", type=int, default=3, help="how many days back to pull (default 3)")
    parser.add_argument("--sink", choices=["files", "supabase"], default="files")
    parser.add_argument("--out", default="./garmin", help="output folder for --sink files")
    parser.add_argument("--dry-run", action="store_true", help="print instead of writing")
    args = parser.parse_args()

    if args.login:
        do_login()
        return
    if args.export_ci_token:
        export_ci_token()
        return

    client = connect()
    end = date.today()
    start = end - timedelta(days=max(args.days, 1) - 1)
    print("Pulling {} to {} ...".format(start, end))

    profile = fetch_profile(client)
    activities = fetch_activities(client, start, end)
    wellness = [fetch_wellness_day(client, start + timedelta(days=i))
                for i in range((end - start).days + 1)]

    if args.dry_run:
        print_preview(activities, wellness)
        print("Dry run -- nothing was written.")
    elif args.sink == "files":
        write_files(args.out, activities, wellness, profile)
    else:
        post_to_endpoint(activities, wellness, profile)


if __name__ == "__main__":
    main()
