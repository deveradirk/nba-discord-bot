import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

WEBHOOK = os.environ["WEBHOOK_SCHEDULE"]
API_KEY = os.environ["BALLDONTLIE_API_KEY"]
PH = ZoneInfo("Asia/Manila")
UA = "Mozilla/5.0 (nba-discord-bot)"
LOGO = "https://a.espncdn.com/i/teamlogos/leagues/500/nba.png"


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
    # Upcoming games carry their tip-off time in "datetime" (or "status")
    for key in ("datetime", "status"):
        val = g.get(key)
        if isinstance(val, str) and "T" in val:
            try:
                return datetime.fromisoformat(val.replace("Z", "+00:00")).astimezone(PH)
            except ValueError:
                pass
    return None


target = (datetime.now(PH) + timedelta(days=1)).date()

# Games are listed by US date, so request the days around the PH target date
dates = [(target + timedelta(days=d)).isoformat() for d in (-1, 0, 1)]
query = urllib.parse.urlencode([("dates[]", d) for d in dates] + [("per_page", 100)])
data = get_json(f"https://api.balldontlie.io/v1/games?{query}")

games = {}
for g in data.get("data", []):
    start = parse_time(g)
    if start is None or start.date() != target:
        continue
    away = g["visitor_team"]["full_name"]
    home = g["home_team"]["full_name"]
    games[g["id"]] = (start, away, home)

title = f"🏀 NBA Games: {target.strftime('%A, %B %d, %Y')}"
if games:
    lines = [
        f"`{s.strftime('%I:%M %p').lstrip('0')}`  **{a}** @ **{h}**"
        for s, a, h in sorted(games.values())
    ]
    description = "\n".join(lines)
else:
    description = "No games scheduled."

post({
    "embeds": [{
        "title": title,
        "description": description,
        "color": 0xF58426,
        "thumbnail": {"url": LOGO},
        "footer": {"text": "All times in PH time (PHT)"},
    }]
})
print(f"Posted {len(games)} games for {target}")
