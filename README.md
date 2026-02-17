# SNL Calendar

Built after the hundredth discussion of "Is there a new SNL this week?" with my wife

An auto-updating calendar that puts one all-day event on every Saturday during the SNL season: either the host and musical guest, or "No SNL Tonight." Updates automatically when new episodes are announced.

## Subscribe

Open this URL in your browser, or paste it into your calendar app:

```
webcal://raw.githubusercontent.com/isolson/snl-calendar/master/snl.ics
```

### Apple Calendar
File → New Calendar Subscription → paste the URL above.

### Google Calendar (not yet tested)
Settings → Add calendar → From URL → paste the URL above.

### Outlook (not yet tested)
Add Calendar → From internet → paste the URL above.

## What it shows

- **Episode week:** `SNL: Host / Musical Guest`
- **Season premiere:** `SNL Season 51 Premiere: Host / Musical Guest`
- **Season finale:** `SNL Season 51 Finale: Host / Musical Guest`
- **Double duty:** `SNL: Sabrina Carpenter`
- **Not yet announced:** `SNL: Host & Musical Guest TBA` — updates automatically once announced
- **Off week:** `No SNL Tonight`
- **Summer / off-season:** nothing (calendar is quiet)

Each episode's Notes field shows the season:episode number (e.g., `S51:E4`) followed by blurbs about the host and musical guest from the TVMaze API.

Specials (like the 50th Anniversary) show up on their actual air date, with a note on the preceding Saturday pointing to them.

## How it stays current

A GitHub Action runs daily, fetches the latest schedule from the [TVMaze API](https://api.tvmaze.com/shows/361/episodes), and regenerates `snl.ics` if anything changed. Your calendar app refreshes the subscription daily and picks up updates automatically — including when "TBA" episodes get their host announced.


## Manual overrides

`data/overrides.json` handles edge cases the API doesn't cover — like adding a Saturday pointer for the 50th Anniversary Special that aired on a Sunday. Edit it and push; the Action will regenerate.

## Running locally

```bash
python3 generate.py
```

No dependencies beyond Python 3's standard library.
