#!/usr/bin/env python3
"""Run each alert's site: query through Serper (Google's search API) and record new URLs.

Serper returns search results, not "new" results, so this keeps a first-seen record per
URL in serper_state.json. The first search for a feed is a baseline: its results are
recorded but never published, the way a Google Alert only reports what's new after it
was created. Every later search adds only URLs it hasn't seen, dated when first seen.
build.py turns the record into docs/serper/<slug>.xml and the comparison page.

Each query is limited to the past week (config serper.tbs, default qdr:w; a feed can
override it with "serper_tbs", e.g. qdr:d for a site that publishes dozens of pages a
day). Google no longer serves 100 results a page, so a full page of 10 is followed by
the next page, up to serper.max_pages (default 5), at 1 credit a page. Searches run at
most once per serper.every_minutes (default 60) however often this is invoked, and skip
cleanly when SERPER_API_KEY isn't set. Standard library only.
"""

import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request

import build
from compare import clean_link, is_listing, norm

SERPER_URL = "https://google.serper.dev/search"
STATE_PATH = build.SERPER_STATE_PATH


class Fatal(Exception):
    """A refusal every later query would hit too: bad or revoked key, no credits left."""


def search(key, query, tbs, page=1, tries=4):
    body = json.dumps({"q": query, "num": 10, "tbs": tbs, "page": page}).encode()
    for attempt in range(tries):
        req = urllib.request.Request(SERPER_URL, data=body, headers={"X-API-KEY": key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:200]
            if exc.code in (401, 402, 403) or (400 <= exc.code < 500 and "credit" in detail.lower()):
                raise Fatal("Serper %s: %s" % (exc.code, detail))
            if exc.code != 429 and exc.code < 500 or attempt == tries - 1:
                raise RuntimeError("Serper %s: %s" % (exc.code, detail))
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == tries - 1:
                raise RuntimeError("Serper unreachable: %s" % exc)
        time.sleep(2 ** attempt * 2)


def main():
    key = os.environ.get("SERPER_API_KEY", "").strip()
    if not key:
        print("serper: SERPER_API_KEY not set, skipping")
        return
    with open(build.CONFIG_PATH) as fh:
        config = json.load(fh)
    settings = config.get("serper") or {}
    tbs = settings.get("tbs") or "qdr:w"
    every = int(settings.get("every_minutes") or 60)
    max_pages = int(settings.get("max_pages") or 5)
    state = {}
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as fh:
            state = json.load(fh)
    meta = state.setdefault("_meta", {})
    now = build.utcnow()
    force = os.environ.get("SERPER_FORCE") == "1"
    if meta.get("last_run") and not force:
        since = (now - build.parse_iso(meta["last_run"])).total_seconds() / 60
        if since < every - 5:  # a little slack for a scheduler that fires a few minutes early or late
            print("serper: last ran %d minutes ago, next run due after %d" % (since, every))
            return

    cutoff = now - dt.timedelta(days=build.KEEP_DAYS)
    feeds = state.setdefault("feeds", {})
    for slug, seen in feeds.items():
        merged = {}
        for entry in sorted(seen.values(), key=lambda e: e["first_seen"]):
            if is_listing(entry["link"]):
                continue
            entry["link"] = clean_link(entry["link"])
            merged.setdefault(norm(entry["link"]), entry)
        feeds[slug] = merged
    credits = queries = new_total = 0
    failures, fatal = [], None
    paged = meta.setdefault("paged", [])
    feed_tbs = meta.setdefault("feed_tbs", {})
    for slug, feed_cfg in sorted(config["feeds"].items()):
        first_search = slug not in feeds
        this_tbs = feed_cfg.get("serper_tbs") or tbs
        # Feeds searched before paging existed only ever saw page 1: their first deeper
        # search is a baseline for pages 2 and up, so older pages there don't count as new.
        rebaseline_deep = not first_search and slug not in paged
        # A feed whose time window changed starts over: its first search in the new window
        # is all baseline. Feeds from before this was recorded used the default window.
        rebaseline_all = not first_search and feed_tbs.get(slug, "qdr:w") != this_tbs
        seen = feeds.setdefault(slug, {})
        results = []  # (page, result)
        try:
            run_links = set()
            for page in range(1, max_pages + 1):
                answer = search(key, feed_cfg["query"], this_tbs, page)
                credits += answer.get("credits") or 1
                queries += 1
                organic = [o for o in answer.get("organic") or [] if o.get("link")]
                full_page = len(organic) >= 10
                organic = [o for o in organic if not is_listing(o["link"])]
                fresh = [o for o in organic if norm(o["link"]) not in run_links]
                run_links.update(norm(o["link"]) for o in fresh)
                results.extend((page, o) for o in fresh)
                if not full_page or not fresh:
                    break
        except Fatal as exc:
            fatal = str(exc)
            if first_search:
                del feeds[slug]  # no baseline yet, so the next good run takes it
            break
        except RuntimeError as exc:
            failures.append("%s: %s" % (slug, exc))
            if first_search:
                del feeds[slug]
            continue
        if slug not in paged:
            paged.append(slug)
        feed_tbs[slug] = this_tbs
        for page, result in results:
            link = clean_link(result["link"])
            k = norm(link)
            if k in seen:
                continue
            baseline = first_search or rebaseline_all or (rebaseline_deep and page > 1)
            seen[k] = {
                "first_seen": build.iso(now),
                "title": build.clean(result.get("title")),
                "link": link,
                "summary": build.clean(result.get("snippet"))[:1000],
                "date_hint": result.get("date") or "",
                "baseline": baseline,
                "page": page,
            }
            if not baseline:
                new_total += 1
        for k in [k for k, v in seen.items() if build.parse_iso(v["first_seen"]) < cutoff]:
            del seen[k]
        time.sleep(0.2)

    if queries:
        meta.setdefault("first_run", build.iso(now))
        meta["last_run"] = build.iso(now)
        meta["runs"] = meta.get("runs", 0) + 1
        meta["credits_used"] = meta.get("credits_used", 0) + credits
    meta["last_error"] = fatal or ("; ".join(failures[:3]) if failures else "")
    for slug in [s for s in feeds if s not in config["feeds"]]:
        del feeds[slug]
    meta["paged"] = sorted(s for s in paged if s in feeds)
    meta["feed_tbs"] = {s: t for s, t in sorted(feed_tbs.items()) if s in feeds}
    with open(STATE_PATH, "w") as fh:
        json.dump(state, fh, indent=1, sort_keys=True)
        fh.write("\n")

    print("serper: queries=%d credits=%d new_urls=%d failures=%d%s" % (
        queries, credits, new_total, len(failures), (" FATAL " + fatal) if fatal else ""))
    for line in failures:
        print("FAILED " + line)
    if fatal:
        sys.exit(fatal)


if __name__ == "__main__":
    main()
