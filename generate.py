#!/usr/bin/env python3
"""Generate snl.ics from TVMaze API data."""

import json
import re
import urllib.request
from datetime import date, timedelta, datetime, timezone
from pathlib import Path

TVMAZE_URL = "https://api.tvmaze.com/shows/361/episodes?specials=1"
OVERRIDES_PATH = Path("data/overrides.json")
OUTPUT_PATH = Path("snl.ics")
ALERTS_OUTPUT_PATH = Path("snl-alerts.ics")

# Only generate events for seasons >= this number
MIN_SEASON = 50


def fetch_episodes():
    """Fetch all SNL episodes from TVMaze API."""
    req = urllib.request.Request(TVMAZE_URL, headers={"User-Agent": "snl-calendar/1.0"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def load_overrides():
    """Load manual overrides if the file exists."""
    if OVERRIDES_PATH.exists():
        return json.loads(OVERRIDES_PATH.read_text())
    return {}


def parse_episode_name(name):
    """Parse episode name into (host, musical_guest).

    Returns:
        (host, guest) where guest is None for double duty, or
        (None, None) for TBA episodes.
    """
    if name == "TBA" or not name:
        return None, None
    if " / " in name:
        parts = name.split(" / ", 1)
        return parts[0], parts[1]
    # Single name = double duty
    return name, None


def format_summary(host, guest, season_num, is_premiere, is_finale):
    """Format the calendar event summary line."""
    if host is None:
        label = "SNL: Host & Musical Guest TBA"
    elif guest is None:
        label = f"SNL: {host}"
    else:
        label = f"SNL: {host} / {guest}"

    if is_premiere and host is not None:
        label = label.replace("SNL:", f"SNL Season {season_num} Premiere:", 1)
    elif is_finale and host is not None:
        label = label.replace("SNL:", f"SNL Season {season_num} Finale:", 1)

    return label


def strip_html(text):
    """Strip HTML tags and decode common entities."""
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'")
    return text.strip()


def split_summary_paragraphs(html):
    """Split an HTML summary into cleaned paragraphs."""
    paragraphs = re.findall(r"<p>(.*?)</p>", html, re.DOTALL)
    return [strip_html(p) for p in paragraphs if strip_html(p)]


def escape_ical(text):
    """Escape text for iCal fields."""
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold_line(line, max_octets=75):
    """Fold a content line per RFC 5545 (max 75 octets per line)."""
    encoded = line.encode("utf-8")
    if len(encoded) <= max_octets:
        return line
    result = []
    while len(encoded) > max_octets:
        split_at = max_octets
        chunk = encoded[:split_at]
        try:
            chunk.decode("utf-8")
        except UnicodeDecodeError:
            while split_at > 0:
                split_at -= 1
                chunk = encoded[:split_at]
                try:
                    chunk.decode("utf-8")
                    break
                except UnicodeDecodeError:
                    continue
        result.append(chunk.decode("utf-8"))
        encoded = encoded[split_at:]
        max_octets = 74  # 75 minus the leading space
    if encoded:
        result.append(encoded.decode("utf-8"))
    return "\r\n ".join(result)


def generate_uid(date_str, suffix="snl"):
    """Generate a deterministic UID for an event."""
    return f"{date_str.replace('-', '')}-{suffix}@snl-calendar"


def format_vevent(dt, summary, uid, description=""):
    """Format a single VEVENT block."""
    dtstart = dt.strftime("%Y%m%d")
    dtend = (dt + timedelta(days=1)).strftime("%Y%m%d")
    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VEVENT",
        fold_line(f"UID:{uid}"),
        f"DTSTAMP:{dtstamp}",
        f"DTSTART;VALUE=DATE:{dtstart}",
        f"DTEND;VALUE=DATE:{dtend}",
        fold_line(f"SUMMARY:{escape_ical(summary)}"),
        "TRANSP:TRANSPARENT",
    ]
    if description:
        lines.append(fold_line(f"DESCRIPTION:{escape_ical(description)}"))
    lines.append("END:VEVENT")
    return "\r\n".join(lines)


def format_vevent_timed(dt, summary, uid, description=""):
    """Format a timed VEVENT block (11:30 PM - 1:00 AM ET with alert)."""
    dtstart = dt.strftime("%Y%m%dT233000")
    next_day = dt + timedelta(days=1)
    dtend = next_day.strftime("%Y%m%dT010000")
    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VEVENT",
        fold_line(f"UID:{uid}"),
        f"DTSTAMP:{dtstamp}",
        f"DTSTART;TZID=America/New_York:{dtstart}",
        f"DTEND;TZID=America/New_York:{dtend}",
        fold_line(f"SUMMARY:{escape_ical(summary)}"),
        "TRANSP:TRANSPARENT",
    ]
    if description:
        lines.append(fold_line(f"DESCRIPTION:{escape_ical(description)}"))
    lines.extend([
        "BEGIN:VALARM",
        "TRIGGER:-PT5M",
        "ACTION:DISPLAY",
        "DESCRIPTION:SNL starts in 5 minutes",
        "END:VALARM",
    ])
    lines.append("END:VEVENT")
    return "\r\n".join(lines)


# VTIMEZONE for America/New_York (EST/EDT)
VTIMEZONE_NY = "\r\n".join([
    "BEGIN:VTIMEZONE",
    "TZID:America/New_York",
    "BEGIN:STANDARD",
    "DTSTART:19701101T020000",
    "RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU",
    "TZOFFSETFROM:-0400",
    "TZOFFSETTO:-0500",
    "TZNAME:EST",
    "END:STANDARD",
    "BEGIN:DAYLIGHT",
    "DTSTART:19700308T020000",
    "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU",
    "TZOFFSETFROM:-0500",
    "TZOFFSETTO:-0400",
    "TZNAME:EDT",
    "END:DAYLIGHT",
    "END:VTIMEZONE",
])


def all_saturdays(start, end):
    """Yield every Saturday from start to end (inclusive)."""
    current = start
    while current.weekday() != 5:
        current += timedelta(days=1)
    while current <= end:
        yield current
        current += timedelta(days=7)


def _day_name(dt):
    """Return the weekday name for a date."""
    return ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][dt.weekday()]


def generate_ics(episodes_data, overrides):
    """Generate the full .ics file content."""
    # Separate regular episodes from specials
    regular_episodes = {}  # season_num -> [episodes]
    special_episodes = []  # flat list of (episode, season_num)

    for ep in episodes_data:
        s = ep["season"]
        if s < MIN_SEASON or not ep.get("airdate"):
            continue
        if ep.get("type") == "regular" and ep.get("number") is not None:
            regular_episodes.setdefault(s, []).append(ep)
        else:
            special_episodes.append((ep, s))

    for s in regular_episodes:
        regular_episodes[s].sort(key=lambda e: e["number"])

    if not regular_episodes:
        return None

    # Build episode lookup from regular episodes only
    episode_map = {}  # date_str -> (episode, season_num, season_regular_eps)
    season_ranges = []  # (start_date, end_date, season_num)

    for season_num, eps in sorted(regular_episodes.items()):
        finale_override = overrides.get("finale_dates", {}).get(str(season_num))
        start_dt = date.fromisoformat(eps[0]["airdate"])
        end_dt = date.fromisoformat(finale_override) if finale_override else date.fromisoformat(eps[-1]["airdate"])
        season_ranges.append((start_dt, end_dt, season_num))

        for ep in eps:
            episode_map[ep["airdate"]] = (ep, season_num, eps)

    # Collect events keyed by date to avoid duplicates
    events_by_date = {}  # date_str -> vevent string

    # 1. Process each season's Saturday range
    for start_dt, end_dt, season_num in season_ranges:
        for saturday in all_saturdays(start_dt, end_dt):
            date_str = saturday.isoformat()

            if date_str in episode_map:
                ep, snum, season_eps = episode_map[date_str]
                host, guest = parse_episode_name(ep["name"])
                is_premiere = ep["number"] == 1
                is_finale = ep["number"] == season_eps[-1]["number"]
                summary = format_summary(host, guest, snum, is_premiere, is_finale)
                uid = generate_uid(date_str, "snl")
                desc_parts = [f"S{snum}:E{ep['number']}"]
                if ep.get("summary"):
                    desc_parts.extend(split_summary_paragraphs(ep["summary"]))
                description = "\n".join(desc_parts)
                events_by_date[date_str] = format_vevent(saturday, summary, uid, description=description)
            else:
                uid = generate_uid(date_str, "nosnl")
                events_by_date[date_str] = format_vevent(saturday, "No SNL Tonight", uid)

    # 2. Handle non-Saturday specials from API
    for ep, snum in special_episodes:
        dt = date.fromisoformat(ep["airdate"])
        date_str = ep["airdate"]
        if dt.weekday() == 5:
            continue  # Skip Saturday specials, they'd conflict with regular logic
        summary = ep["name"]
        uid = generate_uid(date_str, "special")
        events_by_date[date_str] = format_vevent(dt, summary, uid)

    # 3. Handle override specials
    for special in overrides.get("specials", []):
        sp_date = date.fromisoformat(special["date"])
        sp_date_str = special["date"]
        uid = generate_uid(sp_date_str, "special-override")
        events_by_date[sp_date_str] = format_vevent(sp_date, special["title"], uid)
        # Add Saturday pointer
        if special.get("saturday_pointer") and sp_date.weekday() != 5:
            days_since_sat = (sp_date.weekday() - 5) % 7
            if days_since_sat == 0:
                days_since_sat = 7
            prev_saturday = sp_date - timedelta(days=days_since_sat)
            prev_str = prev_saturday.isoformat()
            pointer_uid = generate_uid(prev_str, "pointer")
            pointer_summary = f"{special['title']} - {_day_name(sp_date)}"
            # Pointer replaces any "No SNL Tonight" on that Saturday
            events_by_date[prev_str] = format_vevent(prev_saturday, pointer_summary, pointer_uid)

    # Assemble calendar
    header = "\r\n".join([
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//isolson//SNL Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:SNL Schedule",
        "X-WR-CALDESC:Saturday Night Live episode schedule",
        "REFRESH-INTERVAL;VALUE=DURATION:P1D",
        "X-PUBLISHED-TTL:P1D",
    ])
    footer = "END:VCALENDAR"

    # Sort events by date
    sorted_events = [events_by_date[k] for k in sorted(events_by_date)]

    return header + "\r\n" + "\r\n".join(sorted_events) + "\r\n" + footer + "\r\n"


def generate_alerts_ics(episodes_data, overrides):
    """Generate snl-alerts.ics with timed events and VALARM alerts."""
    regular_episodes = {}
    for ep in episodes_data:
        s = ep["season"]
        if s < MIN_SEASON or not ep.get("airdate"):
            continue
        if ep.get("type") == "regular" and ep.get("number") is not None:
            regular_episodes.setdefault(s, []).append(ep)

    for s in regular_episodes:
        regular_episodes[s].sort(key=lambda e: e["number"])

    if not regular_episodes:
        return None

    events = []
    for season_num, eps in sorted(regular_episodes.items()):
        for ep in eps:
            dt = date.fromisoformat(ep["airdate"])
            host, guest = parse_episode_name(ep["name"])
            is_premiere = ep["number"] == 1
            is_finale = ep["number"] == eps[-1]["number"]
            summary = format_summary(host, guest, season_num, is_premiere, is_finale)
            uid = generate_uid(ep["airdate"], "snl-alert")
            desc_parts = [f"S{season_num}:E{ep['number']}"]
            if ep.get("summary"):
                desc_parts.extend(split_summary_paragraphs(ep["summary"]))
            description = "\n".join(desc_parts)
            events.append((ep["airdate"], format_vevent_timed(dt, summary, uid, description=description)))

    events.sort(key=lambda x: x[0])

    header = "\r\n".join([
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//isolson//SNL Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:SNL Alerts",
        "X-WR-CALDESC:Saturday Night Live airtime alerts (11:30 PM ET)",
        "REFRESH-INTERVAL;VALUE=DURATION:P1D",
        "X-PUBLISHED-TTL:P1D",
    ])
    footer = "END:VCALENDAR"

    body = "\r\n".join([VTIMEZONE_NY] + [ev for _, ev in events])
    return header + "\r\n" + body + "\r\n" + footer + "\r\n"


def main():
    print("Fetching episodes from TVMaze...")
    episodes = fetch_episodes()
    overrides = load_overrides()

    print(f"Got {len(episodes)} episodes total")
    ics = generate_ics(episodes, overrides)
    if ics is None:
        print("No episodes found for configured seasons")
        return

    OUTPUT_PATH.write_text(ics)
    event_count = ics.count("BEGIN:VEVENT")
    print(f"Generated {OUTPUT_PATH} with {event_count} events")

    alerts_ics = generate_alerts_ics(episodes, overrides)
    if alerts_ics:
        ALERTS_OUTPUT_PATH.write_text(alerts_ics)
        alerts_count = alerts_ics.count("BEGIN:VEVENT")
        print(f"Generated {ALERTS_OUTPUT_PATH} with {alerts_count} events")


if __name__ == "__main__":
    main()
