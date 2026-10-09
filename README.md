# alert-feeds

Republishes a set of Google Alerts RSS feeds with real entry dates.

Google Alerts feeds stamp every entry `1970-01-01`, so readers that go by date skip everything. A scheduled GitHub Action (`build.py`, every 20 minutes) fetches each alert feed and records when each entry was first seen. It then writes a clean Atom feed per alert to `docs/feeds/<slug>.xml`, served by GitHub Pages, dated by that first-seen time and linking to the real article instead of Google's redirect.

- **`config.json`:** the Crayon portals, plus for each feed its Google feed URL, alert query, competitor and the insight type and subtype it's wired to. The index page (`docs/index.html`) lists feeds under their portal.
- **`PUBLISH_START` repository variable (optional):** no entry is dated before this UTC time (`2026-10-08T15:30:00Z` format). If a reader starts watching a feed while it's empty, the backlog then arrives as new items.
- **`state.json`:** first-seen times. Entries older than 60 days are dropped.

## Serper feeds

`serper_build.py` runs each alert's `site:` query through [Serper](https://serper.dev), Google's search API, once an hour. It limits each search to the past week (`config.json` → `serper.tbs`) and asks for 10 results, or 100 when the 10 come back full. Serper bills 1 credit per search, or 2 for the 100-result version.

The first search for each feed is a baseline. Its results are recorded in `serper_state.json` but never published, the way an alert only reports what's new after it was created. After that, each URL is published to `docs/serper/<slug>.xml` the first time it shows up.

- **`SERPER_API_KEY` repository secret:** without it the Serper step skips itself.
- **`SERPER_PUBLISH_START` repository variable:** does the same job as `PUBLISH_START`, for the Serper feeds.
- **`docs/compare.html`:** matches the two sources by URL, per alert. It shows which pages both found and which one saw each first, plus what only Alerts or only Serper found.
