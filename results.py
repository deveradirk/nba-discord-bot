import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

WEBHOOK = os.environ["WEBHOOK_RESULTS"]
API_KEY = os.environ["BALLDONTLIE_API_KEY"]
PH = ZoneInfo("Asia/Manila")
UA = "Mozilla/5.0 (nba-discord-bot)"
STATE = "results_seen.json"
FIRST_RUN_MAX = 5  # on the very first run, only post the latest few finals

LOGO_CODES = {
    "ATL": "atl", "BOS": "bos", "BKN": "bkn", "CHA": "cha", "CHI": "chi",
    "CLE": "cle", "DAL": "dal", "DEN": "den", "DET": "det", "GSW": "gs",
    "HOU": "hou", "IND": "ind", "LAC": "lac", "LAL": "lal", "MEM": "mem",
    "MIA": "mia", "MIL": "mil", "MIN": "min", "NOP": "no", "NYK": "ny",
    "OKC": "okc", "ORL": "orl", "PHI": "phi", "PHX": "phx", "POR": "por",
    "SAC": "sac", "SAS": "sa", "TOR": "tor", "UTA": "utah", "WAS": "wsh",
}


def logo_url(abbr):
    code = LOGO_CODES.get(abbr, (abbr or "nba").lower())
    return f"https://a.espncdn.com/i/teamlogos/nba/500/{code}.png"


def get_json(url):
    req = urllib.request.Request(url, headers={"Authorization": API_KEY, "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def post(payload):
    req = urllib.request.Request(
        WEBHOOK,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": UA},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=30).read()


def tipoff(g):
    val = g.get("datetime")
    if isinstance(val, str) and "T" in val:
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00")).astimezone(PH)
        except ValueError:
            pass
    return None


def build_embed(g):
    home, away = g["home_team"], g["visitor_team"]
    hs, vs = g["home_team_score"], g["visitor_team_score"]
    home_won = hs > vs
    extra = (g.get("period") or 4) - 4
    ot = "" if extra <= 0 else (" (OT)" if extra == 1 else f" ({extra}OT)")

    away_line = f"✈️ {away['full_name']} — {vs}"
    home_line = f"🏠 {home['full_name']} — {hs}"
    if home_won:
        home_line = f"**{home_line}** ✅"
    else:
        away_line = f"**{away_line}** ✅"

    winner = home if home_won else away
    embed = {
        "title": f"🏁 FINAL{ot}",
        "description": f"{away_line}\n{home_line}",
        "color": 0x2ECC71,
        "thumbnail": {"url": logo_url(winner.get("abbreviation"))},
    }
    t = tipoff(g)
    if t:
        embed["footer"] = {"text": t.strftime("%b %d, %Y") + " (PH date of tip-off)"}
    return embed


now = datetime.now(PH)
dates = [(now.date() + timedelta(days=d)).isoformat() for d in (-2, -1, 0)]
query = urllib.parse.urlencode([("dates[]", d) for d in dates] + [("per_page", 100)])
data = get_json(f"https://api.balldontlie.io/v1/games?{query}")

finals = [
    g for g in data.get("data", [])
    if str(g.get("status", "")).lower().startswith("final")
    and g.get("home_team_score") is not None
    and g.get("visitor_team_score") is not None
]
finals.sort(key=lambda g: g.get("datetime") or "")

first_run = not os.path.exists(STATE)
seen = set() if first_run else set(json.load(open(STATE)))

new = [g for g in finals if g["id"] not in seen]
if first_run:
    new = new[-FIRST_RUN_MAX:]

for i in range(0, len(new), 10):
    chunk = new[i:i + 10]
    payload = {"embeds": [build_embed(g) for g in chunk]}
    if i == 0:
        payload["content"] = f"🏀 **{len(new)} game(s) just finished**"
    post(payload)
    time.sleep(1.5)

seen.update(g["id"] for g in finals)
json.dump(sorted(seen)[-800:], open(STATE, "w"))
print(f"Finals found: {len(finals)}, posted: {len(new)}")
