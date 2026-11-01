import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

WEBHOOK = os.environ["WEBHOOK_STANDINGS"]
API_KEY = os.environ["API_NINJAS_KEY"]
PH = ZoneInfo("Asia/Manila")
UA = "Mozilla/5.0 (nba-discord-bot)"
STATE = "standings_state.json"
STATE_VERSION = 2
EDIT_IN_PLACE = True   # False = post new messages every update

ENDPOINTS = [
    "https://api.api-ninjas.com/v1/basketballstandings?league=nba",
    "https://api.api-ninjas.com/v1/sportsstandings?league=nba",
]

# ESPN logo codes (covers common abbreviation variants)
LOGO_CODES = {
    "ATL": "atl", "BOS": "bos", "BKN": "bkn", "BRK": "bkn", "CHA": "cha",
    "CHO": "cha", "CHI": "chi", "CLE": "cle", "DAL": "dal", "DEN": "den",
    "DET": "det", "GSW": "gs", "GS": "gs", "HOU": "hou", "IND": "ind",
    "LAC": "lac", "LAL": "lal", "MEM": "mem", "MIA": "mia", "MIL": "mil",
    "MIN": "min", "NOP": "no", "NO": "no", "NYK": "ny", "NY": "ny",
    "OKC": "okc", "ORL": "orl", "PHI": "phi", "PHX": "phx", "PHO": "phx",
    "POR": "por", "SAC": "sac", "SAS": "sa", "SA": "sa", "TOR": "tor",
    "UTA": "utah", "UTAH": "utah", "WAS": "wsh", "WSH": "wsh",
}


def logo(abbr):
    code = LOGO_CODES.get(abbr.upper(), abbr.lower())
    return f"https://a.espncdn.com/i/teamlogos/nba/500/{code}.png"


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
            "abbr": team.get("abbreviation") or "NBA",
            "name": team.get("name") or "Unknown",
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


def ordered(group):
    if all(isinstance(r["rank"], int) for r in group):
        return sorted(group, key=lambda r: r["rank"])
    return sorted(group, key=lambda r: (-pct(r), -r["w"], r["name"]))


def row_embeds(group):
    group = ordered(group)
    lead = group[0]
    embeds = []
    for i, r in enumerate(group, 1):
        gb = ((lead["w"] - r["w"]) + (r["l"] - lead["l"])) / 2
        gb_txt = "-" if gb == 0 else f"{gb:g}"
        color = 0x2ECC71 if i <= 6 else (0xF1C40F if i <= 10 else 0x95A5A6)
        text = f"{i}. {r['name']}  •  {r['w']}-{r['l']}  •  {fmt_pct(r)}  •  GB {gb_txt}"
        embeds.append({"author": {"name": text[:256], "icon_url": logo(r["abbr"])},
                       "color": color})
    return embeds


def build_messages(east, west, stamp):
    msgs = []
    for title, group in (("🏆 Eastern Conference", east), ("🏆 Western Conference", west)):
        embeds = row_embeds(group)
        msgs.append({"content": f"## {title}", "embeds": embeds[:10]})
        if embeds[10:]:
            msgs.append({"content": "", "embeds": embeds[10:]})
    msgs[-1]["embeds"][-1]["footer"] = {
        "text": f"🟢 Top 6  •  🟡 Play-In (7-10)  •  Updated {stamp} PH time  •  API Ninjas"
    }
    return msgs


def request(method, url, payload):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": UA}, method=method)
    return urllib.request.urlopen(req, timeout=30).read()


def post_new(payload):
    return str(json.loads(request("POST", WEBHOOK + "?wait=true", payload))["id"])


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

if state.get("sig") == sig and state.get("message_ids"):
    print("No changes in standings, skipping")
    raise SystemExit(0)

stamp = datetime.now(PH).strftime("%b %d, %I:%M %p").replace(" 0", " ")
msgs = build_messages(east, west, stamp)

ids = state.get("message_ids") or []
new_ids = None
if EDIT_IN_PLACE and len(ids) == len(msgs):
    try:
        for mid, m in zip(ids, msgs):
            request("PATCH", f"{WEBHOOK}/messages/{mid}", m)
            time.sleep(1)
        new_ids = ids
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
if new_ids is None:
    new_ids = []
    for m in msgs:
        new_ids.append(post_new(m))
        time.sleep(1.5)

state["message_ids"] = new_ids
state["sig"] = sig
json.dump(state, open(STATE, "w"))
print("Standings posted")
