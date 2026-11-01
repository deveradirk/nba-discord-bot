import hashlib
import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

WEBHOOK = os.environ["WEBHOOK_STANDINGS"]
API_KEY = os.environ["API_NINJAS_KEY"]
PH = ZoneInfo("Asia/Manila")
UA = "Mozilla/5.0 (nba-discord-bot)"
STATE = "standings_state.json"
STATE_VERSION = 3
EDIT_IN_PLACE = True   # False = post a new message every update

ENDPOINTS = [
    "https://api.api-ninjas.com/v1/basketballstandings?league=nba",
    "https://api.api-ninjas.com/v1/sportsstandings?league=nba",
]


def load_rows():
    last_err = None
    for url in ENDPOINTS:
        try:
            req = urllib.request.Request(url, headers={"X-Api-Key": API_KEY, "User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)
            if isinstance(data, list) and data:
                print("Sample row:", json.dumps(data[0]))
                return data
            last_err = "empty response"
        except Exception as e:
            last_err = e
            print(f"Endpoint failed ({url}): {e}")
    raise SystemExit(f"Could not load standings: {last_err}")


def conference(row):
    c = str(row.get("conference") or "").lower()
    if c.startswith("e"):
        return "East"
    if c.startswith("w"):
        return "West"
    return None


def normalize(data):
    out = []
    for r in data:
        conf = conference(r)
        if not conf:
            continue
        team = r.get("team") or {}
        out.append({
            "conf": conf,
            "abbr": team.get("abbreviation") or "???",
            "name": team.get("name") or "",
            "w": int(r.get("wins") or 0),
            "l": int(r.get("losses") or 0),
            "rank": r.get("conference_rank"),
        })
    return out


def pct(r):
    return r["w"] / (r["w"] + r["l"]) if r["w"] + r["l"] else 0.0


def fmt_pct(r):
    p = pct(r)
    return "1.000" if p == 1 else f"{p:.3f}"[1:]


def build_table(group):
    if all(isinstance(r["rank"], int) for r in group):
        group = sorted(group, key=lambda r: r["rank"])
    else:
        group = sorted(group, key=lambda r: (-pct(r), -r["w"], r["name"]))
    lead = group[0]
    lines = [f"{'':<3}{'#':>2} {'TEAM':<4} {'W-L':<7} {'PCT':>5} {'GB':>4}"]
    for i, r in enumerate(group, 1):
        gb = ((lead["w"] - r["w"]) + (r["l"] - lead["l"])) / 2
        gb_txt = "-" if gb == 0 else f"{gb:g}"
        mark = "🟢" if i <= 6 else ("🟡" if i <= 10 else "⚪")
        record = f"{r['w']}-{r['l']}"
        lines.append(f"{mark} {i:>2} {r['abbr']:<4} {record:<7} {fmt_pct(r):>5} {gb_txt:>4}")
    return "```\n" + "\n".join(lines) + "\n```"


def request(method, url, payload):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": UA}, method=method)
    return urllib.request.urlopen(req, timeout=30).read()


rows = normalize(load_rows())
east = [r for r in rows if r["conf"] == "East"]
west = [r for r in rows if r["conf"] == "West"]
if not east or not west:
    raise SystemExit(f"Unexpected data: {len(east)} East teams, {len(west)} West teams")

sig = hashlib.sha256(json.dumps(
    [STATE_VERSION] + sorted((r["abbr"], r["w"], r["l"]) for r in rows)).encode()).hexdigest()

state = json.load(open(STATE)) if os.path.exists(STATE) else {}
if state.get("v") != STATE_VERSION:
    state = {"v": STATE_VERSION}

if state.get("sig") == sig and state.get("message_id"):
    print("No changes in standings, skipping")
    raise SystemExit(0)

stamp = datetime.now(PH).strftime("%b %d, %I:%M %p").replace(" 0", " ")
payload = {
    "content": f"🏆 **NBA Standings** • updated {stamp} PH time",
    "embeds": [
        {"title": "🏆 Eastern Conference", "description": build_table(east),
         "color": 0x1D428A},
        {"title": "🏆 Western Conference", "description": build_table(west),
         "color": 0xC8102E,
         "footer": {"text": "🟢 Top 6  •  🟡 Play-In (7-10)  •  ⚪ Out  •  Source: API Ninjas"}},
    ],
}

mid = state.get("message_id")
done = False
if EDIT_IN_PLACE and mid:
    try:
        request("PATCH", f"{WEBHOOK}/messages/{mid}", payload)
        done = True
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
if not done:
    resp = json.loads(request("POST", WEBHOOK + "?wait=true", payload))
    state["message_id"] = str(resp["id"])

state["sig"] = sig
json.dump(state, open(STATE, "w"))
print("Standings posted")
