#!/usr/bin/env python3
"""
make_dashboard.py -- turn garmin/data.json into a self-contained dashboard page.

Writes two files from one template:
  dashboard.html           standalone page -- double-click it, works offline
  dashboard_artifact.html  same page without the <html>/<head> wrapper, for
                           publishing to a claude.ai artifact (phone access)

Run it after a sync:  py make_dashboard.py
"""

import json
import os
import sys
from datetime import datetime

import crypto_store

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "dashboard_template.html")
STORE = os.path.join(HERE, "garmin", "data.json")
PLACEHOLDER = "/*__GARMIN_DATA__*/null"

WRAPPER_HEAD = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<style>
  :root { color-scheme: light; padding-top: env(safe-area-inset-top, 0px);
          padding-bottom: env(safe-area-inset-bottom, 0px); }
  body { margin: 0; font: 14px system-ui, sans-serif; }
  img { max-width: 100%; }
  [hidden] { display: none !important; }
</style>
</head>
<body>
"""
WRAPPER_FOOT = "\n</body>\n</html>\n"


GATE_SCRIPT = """
<script>
(function () {
  "use strict";
  var ENC = __ENVELOPE__;
  var gate = document.getElementById("gate");
  var form = document.getElementById("gateform");
  var pw = document.getElementById("gatepw");
  var msg = document.getElementById("gatemsg");
  var wrap = document.querySelector(".wrap");
  if (wrap) wrap.hidden = true;
  if (gate) gate.hidden = false;

  function b64(str) {
    var bin = atob(str), out = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }

  /* Entschluesselt eine beliebige Huelle -- die eingebettete oder eine frisch geladene. */
  function decryptEnvelope(env, secret) {
    var enc = new TextEncoder();
    return crypto.subtle.importKey("raw", enc.encode(secret), "PBKDF2", false, ["deriveKey"])
      .then(function (base) {
        return crypto.subtle.deriveKey(
          { name: "PBKDF2", salt: b64(env.salt), iterations: env.iterations, hash: "SHA-256" },
          base, { name: "AES-GCM", length: 256 }, false, ["decrypt"]);
      })
      .then(function (key) {
        return crypto.subtle.decrypt({ name: "AES-GCM", iv: b64(env.iv) }, key, b64(env.data));
      })
      .then(function (buf) { return JSON.parse(new TextDecoder().decode(buf)); });
  }

  /* Holt die zuletzt veroeffentlichte Fassung nach, ohne die Seite zu verlassen. */
  window.__garminFetchLatest = function () {
    var secret = null;
    try { secret = localStorage.getItem("garmin-pw"); } catch (e) {}
    if (!secret) return Promise.reject(new Error("kein Passwort gespeichert"));
    var url = location.pathname + "?t=" + Date.now();
    return fetch(url, { cache: "no-store" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.text();
      })
      .then(function (html) {
        var m = html.match(/var ENC = (\{[\s\S]*?\});/);
        if (!m) throw new Error("kein Datenblock gefunden");
        return decryptEnvelope(JSON.parse(m[1]), secret);
      });
  };

  function unlock(secret, quiet) {
    if (!secret) return Promise.resolve(false);
    return decryptEnvelope(ENC, secret)
      .then(function (data) {
        try { localStorage.setItem("garmin-pw", secret); } catch (e) {}
        window.__garminStart(data);
        return true;
      })
      .catch(function () {
        if (!quiet) msg.textContent = "Passwort stimmt nicht.";
        try { localStorage.removeItem("garmin-pw"); } catch (e) {}
        return false;
      });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    msg.textContent = "Wird entschlusselt...";
    unlock(pw.value, false);
  });

  var saved = null;
  try { saved = localStorage.getItem("garmin-pw"); } catch (e) {}
  if (saved) {
    msg.textContent = "Wird entschlusselt...";
    unlock(saved, true).then(function (ok) { if (!ok) msg.textContent = ""; });
  }
})();
</script>
"""

def duration_seconds(act):
    return act.get("moving_duration_s") or act.get("duration_s") or 0


def build_payload():
    if not os.path.exists(STORE):
        sys.exit("No {} yet. Run:  py sync_garmin.py --days 45".format(STORE))
    with open(STORE, "r", encoding="utf-8") as fh:
        store = json.load(fh)

    days = []
    for d in sorted(store.get("wellness", {})):
        w = store["wellness"][d]
        days.append({
            "d": d,
            "rhr": w.get("resting_hr"),
            "rhr7": w.get("resting_hr_7d"),
            "hrv": w.get("hrv_ms"),
            "hrvStatus": w.get("hrv_status"),
            "sleep": w.get("sleep_hours"),
            "sleepScore": w.get("sleep_score"),
            "deep": w.get("sleep_deep_h"),
            "light": w.get("sleep_light_h"),
            "rem": w.get("sleep_rem_h"),
            "awake": w.get("sleep_awake_h"),
            "bed": w.get("bed_time"),
            "wake": w.get("wake_time"),
            "sleepHr": w.get("sleep_hr"),
            "sleepStress": w.get("sleep_stress"),
            "resp": w.get("respiration"),
            "spo2": w.get("spo2"),
            "bbLow": w.get("body_battery_low"),
            "bbHigh": w.get("body_battery_high"),
            "bbWake": w.get("bb_at_wake"),
            "stress": w.get("stress_avg"),
            "sRest": w.get("stress_rest_s"),
            "sLow": w.get("stress_low_s"),
            "sMed": w.get("stress_med_s"),
            "sHigh": w.get("stress_high_s"),
            "steps": w.get("steps"),
            "stepGoal": w.get("step_goal"),
            "floors": round(w["floors"]) if w.get("floors") else None,
            "imMod": w.get("intensity_moderate"),
            "imVig": w.get("intensity_vigorous"),
            "imGoal": w.get("intensity_goal"),
            "sedH": round(w["sedentary_seconds"] / 3600.0, 1) if w.get("sedentary_seconds") else None,
            "hrMax": w.get("hr_max_day"),
            "vo2": w.get("vo2max"),
            "kcal": w.get("calories_total"),
            "kcalActive": w.get("calories_active"),
            "readiness": w.get("training_readiness"),
        })

    acts = []
    for a in store.get("activities", {}).values():
        secs = duration_seconds(a)
        dist = a.get("distance_m") or 0
        zones = a.get("hr_zones_s") or []
        acts.append({
            "id": a.get("id"),
            "date": a.get("date"),
            "start": a.get("start_local"),
            "name": a.get("name"),
            "type": a.get("type"),
            "km": round(dist / 1000.0, 2) if dist else None,
            "sec": int(secs) if secs else None,
            "hr": round(a["avg_hr"]) if a.get("avg_hr") else None,
            "maxHr": round(a["max_hr"]) if a.get("max_hr") else None,
            "cal": round(a["calories"]) if a.get("calories") else None,
            "up": round(a["elevation_gain_m"]) if a.get("elevation_gain_m") else None,
            "te": round(a["training_effect_aerobic"], 1) if a.get("training_effect_aerobic") else None,
            "teLabel": a.get("training_effect_label"),
            "cad": round(a["cadence_spm"], 1) if a.get("cadence_spm") else None,
            "stride": round(a["stride_cm"]) if a.get("stride_cm") else None,
            "gct": round(a["ground_contact_ms"]) if a.get("ground_contact_ms") else None,
            "vr": round(a["vertical_ratio"], 1) if a.get("vertical_ratio") else None,
            "pw": round(a["avg_power_w"]) if a.get("avg_power_w") else None,
            "speed": round(a["avg_speed_ms"], 3) if a.get("avg_speed_ms") else None,
            "gap": round(a["gap_speed_ms"], 3) if a.get("gap_speed_ms") else None,
            "vo2": a.get("vo2max"),
            "temp": a.get("temp_max_c"),
            "zones": [round(z) if z else 0 for z in zones] if any(zones) else None,
        })
    acts.sort(key=lambda a: (a.get("start") or a.get("date") or ""), reverse=True)

    return {
        "generated": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "profile": store.get("profile") or {},
        "racePred": store.get("race_predictions") or {},
        "days": days,
        "activities": acts,
    }


def build_encrypted(template, payload, out_dir):
    """Write docs/index.html: the same page, but the data is ciphertext until
    the reader types the passphrase."""
    pw = crypto_store.passphrase()
    envelope = crypto_store.encrypt_obj(payload, pw)
    body = template.replace(PLACEHOLDER, "null")
    body += GATE_SCRIPT.replace("__ENVELOPE__", json.dumps(envelope))
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "index.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(WRAPPER_HEAD + body + WRAPPER_FOOT)
    print("Encrypted page written ({} days, {} activities, no readable data on disk):".format(
        len(payload["days"]), len(payload["activities"])))
    print("  " + path)


def main():
    encrypt = "--encrypt" in sys.argv
    payload = build_payload()
    with open(TEMPLATE, "r", encoding="utf-8") as fh:
        template = fh.read()
    if PLACEHOLDER not in template:
        sys.exit("Template is missing the {} placeholder.".format(PLACEHOLDER))

    if encrypt:
        build_encrypted(template, payload, os.path.join(HERE, "docs"))
        return

    body = template.replace(PLACEHOLDER, json.dumps(payload, ensure_ascii=False))

    standalone = os.path.join(HERE, "dashboard.html")
    with open(standalone, "w", encoding="utf-8") as fh:
        fh.write(WRAPPER_HEAD + body + WRAPPER_FOOT)

    artifact = os.path.join(HERE, "dashboard_artifact.html")
    with open(artifact, "w", encoding="utf-8") as fh:
        fh.write(body)

    print("Dashboard built from {} day(s) and {} activity(ies).".format(
        len(payload["days"]), len(payload["activities"])))
    print("  " + standalone)
    print("  " + artifact)


if __name__ == "__main__":
    main()
