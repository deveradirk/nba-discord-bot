import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

WEBHOOK = os.environ["WEBHOOK_SCHEDULE"]
API_KEY = os.environ["BALLDONTLIE_API_KEY"]
PH = ZoneInfo("Asia/Manila")
UA = "Mozilla/5.0 (nba-discord-bot)"

# balldontlie abbreviation -> ESPN logo code
LOGO_CODES = {"GSW": "gs", "NOP": "no", "NYK": "ny", "SAS": "sa",
              "UTA": "utah", "WAS": "wsh"}


def logo(abbr):
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


def parse_time(g):
    for key in ("datetime", "status"):
        val = g.get(key)
        if isinstance(val, str) and "T" in val:
            try:
                return datetime.fromisoformat(val.replace("Z", "+00:00")).astimezone(PH)
            except ValueError:
                pass
    return None


target = (datetime.now(PH) + timedelta(days=1)).date()

dates = [(target + timedelta(days=d)).isoformat() for d in (-1, 0, 1)]
query = urllib.parse.urlencode([("dates[]", d) for d in dates] + [("per_page", 100)])
data = get_json(f"https://api.balldontlie.io/v1/games?{query}")

games = {}
for g in data.get("data", []):
    start = parse_time(g)
    if start is None or start.date() != target:
        continue
    games[g["id"]] = (start, g["visitor_team"], g["home_team"])

heading = f"🏀 **NBA Games: {target.strftime('%A, %B %d, %Y')}**"

if not games:
    post({"content": heading + "\nNo games scheduled."})
    print("No games")
else:
    embeds = []
    for start, away, home in sorted(games.values(), key=lambda x: x[0]):
        embeds.append({
            "title": f"{away['full_name']} @ {home['full_name']}",
            "description": (f"🕒 **{start.strftime('%I:%M %p').lstrip('0')}** PH time\n"
                            f"🏠 Home court: **{home['full_name']}**"),
            "color": 0xF58426,
            "thumbnail": {"url": logo(home.get("abbreviation"))},
            "footer": {"text": f"Away: {away['full_name']}",
                       "icon_url": logo(away.get("abbreviation"))},
        })
    for i in range(0, len(embeds), 10):
        content = heading + f" • {len(embeds)} game(s)" if i == 0 else None
        payload = {"embeds": embeds[i:i + 10]}
        if content:
            payload["content"] = content
        post(payload)
        time.sleep(1.5)
    print(f"Posted {len(embeds)} games for {target}")
