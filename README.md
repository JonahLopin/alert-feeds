# alert-feeds

Republishes a set of Google Alerts RSS feeds with real entry dates.

Google Alerts feeds stamp every entry `1970-01-01`, so readers that go by date skip everything. A scheduled GitHub Action (`build.py`, every 20 minutes) fetches each alert feed and records when each entry was first seen. It then writes a clean Atom feed per alert to `docs/feeds/<slug>.xml`, served by GitHub Pages, dated by that first-seen time and linking to the real article instead of Google's redirect.

- **Alert feed URLs:** the `ALERT_FEEDS` repository secret, as JSON `{slug: {"url": ..., "title": ...}}`.
- **`PUBLISH_START` repository variable (optional):** no entry is dated before this UTC time (`2026-10-08T15:30:00Z` format). If a reader starts watching a feed while it's empty, the backlog then arrives as new items.
- **`state.json`:** first-seen times. Entries older than 60 days are dropped.
