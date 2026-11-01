import json
import os
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

WEBHOOK = os.environ["WEBHOOK_SCHEDULE"]
PH = ZoneInfo("Asia/Manila")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nba.com",
    "Referer": "https://www.nba.com/",
}
SCHEDULE_URL = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json"


def get_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def post(payload):
    req = urllib.request.Request(
        WEBHOOK,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "User-Agent": HEADERS["User-Agent"]},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=30).read()


def team_name(t):
    city = (t.get("teamCity") or "").strip()
    name = (t.get("teamName") or "").strip()
    return f"{city} {name}".strip()


target = (datetime.now(PH) + timedelta(days=1)).date()

data = get_json(SCHEDULE_URL)
games = {}
for day in data["leagueSchedule"]["gameDates"]:
    for g in day.get("games", []):
        utc = g.get("gameDateTimeUTC")
        if not utc:
            continue
        start = datetime.fromisoformat(utc.replace("Z", "+00:00")).astimezone(PH)
        if start.date() != target:
            continue
        away = team_name(g.get("awayTeam", {}))
        home = team_name(g.get("homeTeam", {}))
        if not away or not home:
            continue
        games[g["gameId"]] = (start, away, home)

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
        "footer": {"text": "All times in PH time (PHT)"},
    }]
})
print(f"Posted {len(games)} games for {target}")
