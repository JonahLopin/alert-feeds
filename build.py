#!/usr/bin/env python3
"""Republish Google Alerts RSS feeds with usable entry dates.

Google Alerts feeds stamp every entry 1970-01-01, so feed readers that go by date
(Crayon's RSSeymour among them) skip everything. This fetches each alert feed,
records when each entry was first seen, and writes one clean Atom feed per alert to
docs/feeds/<slug>.xml, dated by that first-seen time. Links are unwrapped from
Google's redirect to the real article URL.

Config is the ALERT_FEEDS env var, JSON {slug: {"url": ..., "title": ...}}, kept in
a repository secret so the Google feed URLs (which carry the account's user id)
aren't published. Standard library only.
"""

import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ATOM_NS = "http://www.w3.org/2005/Atom"
ATOM = "{%s}" % ATOM_NS
ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(ROOT, "state.json")
OUT_DIR = os.path.join(ROOT, "docs", "feeds")
KEEP_DAYS = 60
MAX_ENTRIES = 100
PAGES_BASE = os.environ.get("PAGES_BASE", "").rstrip("/")
# No entry is dated before this moment. A reader that registers a feed while it is
# still empty then sees the backlog arrive as new items once this time passes.
PUBLISH_START = os.environ.get("PUBLISH_START") or "1970-01-01T00:00:00Z"
TAG = re.compile(r"<[^>]+>")


def utcnow():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)


def clean(markup):
    """Alert titles and snippets are HTML (<b> highlights, entities): flatten to text."""
    text = html.unescape(TAG.sub("", markup or ""))
    return re.sub(r"\s+", " ", text).strip()


def unwrap(link):
    """https://www.google.com/url?...&url=<real>&... -> <real>"""
    try:
        parts = urllib.parse.urlsplit(link)
        if parts.netloc.endswith("google.com") and parts.path == "/url":
            real = urllib.parse.parse_qs(parts.query).get("url")
            if real:
                return real[0]
    except ValueError:
        pass
    return link


def fetch(url, tries=4):
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; alert-feeds/1.0)"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                root = ET.fromstring(resp.read())
            if root.tag != ATOM + "feed":
                raise ValueError("not an Atom feed: %s" % root.tag)
            return root
        except Exception as exc:  # network errors, 429s, a consent page instead of XML
            last = exc
            time.sleep(5 * (attempt + 1))
    raise last


def write_feed(slug, cfg, seen, now, start):
    # An entry's date is when it was first seen, but never before PUBLISH_START; entries
    # whose date is still in the future stay out of the feed until it arrives.
    items = []
    for eid, entry in seen.items():
        when = max(parse_iso(entry["first_seen"]), start)
        if when <= now:
            items.append((when, eid, entry))
    items.sort(key=lambda item: (item[0], item[1]), reverse=True)
    items = items[:MAX_ENTRIES]

    feed = ET.Element("feed", {"xmlns": ATOM_NS})
    ET.SubElement(feed, "id").text = "urn:alert-feeds:%s" % slug
    ET.SubElement(feed, "title").text = cfg.get("title") or slug
    # Latest entry date rather than build time, so an unchanged feed writes identical bytes.
    ET.SubElement(feed, "updated").text = iso(items[0][0]) if items else iso(start)
    if PAGES_BASE:
        ET.SubElement(feed, "link", {"rel": "self", "href": "%s/feeds/%s.xml" % (PAGES_BASE, slug)})
    for when, eid, entry in items:
        node = ET.SubElement(feed, "entry")
        ET.SubElement(node, "id").text = eid
        ET.SubElement(node, "title").text = entry["title"] or entry["link"]
        ET.SubElement(node, "link", {"href": entry["link"]})
        ET.SubElement(node, "published").text = iso(when)
        ET.SubElement(node, "updated").text = iso(when)
        if entry.get("summary"):
            ET.SubElement(node, "summary").text = entry["summary"]
    ET.indent(feed)
    ET.ElementTree(feed).write(os.path.join(OUT_DIR, slug + ".xml"), encoding="utf-8", xml_declaration=True)
    return len(items)


def main():
    feeds = json.loads(os.environ["ALERT_FEEDS"])
    state = {}
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as fh:
            state = json.load(fh)
    now = utcnow()
    start = parse_iso(PUBLISH_START)
    cutoff = now - dt.timedelta(days=KEEP_DAYS)
    os.makedirs(OUT_DIR, exist_ok=True)

    failures, new_total, published_total = [], 0, 0
    for slug, cfg in sorted(feeds.items()):
        seen = state.setdefault(slug, {})
        try:
            root = fetch(cfg["url"])
            for entry in root.findall(ATOM + "entry"):
                eid = (entry.findtext(ATOM + "id") or "").strip()
                link_el = entry.find(ATOM + "link")
                link = unwrap(link_el.get("href", "") if link_el is not None else "")
                if not eid or not link or eid in seen:
                    continue
                seen[eid] = {
                    "first_seen": iso(now),
                    "title": clean(entry.findtext(ATOM + "title")),
                    "link": link,
                    "summary": clean(entry.findtext(ATOM + "content"))[:1000],
                }
                new_total += 1
        except Exception as exc:  # keep the previous entries; a failed fetch only means no new ones
            failures.append("%s: %s" % (slug, exc))
        for eid in [k for k, v in seen.items() if parse_iso(v["first_seen"]) < cutoff]:
            del seen[eid]
        published_total += write_feed(slug, cfg, seen, now, start)
        time.sleep(2)

    for slug in [s for s in state if s not in feeds]:
        del state[slug]
    with open(STATE_PATH, "w") as fh:
        json.dump(state, fh, indent=1, sort_keys=True)
        fh.write("\n")

    print("feeds=%d new_entries=%d published_entries=%d failures=%d" % (len(feeds), new_total, published_total, len(failures)))
    for line in failures:
        print("FAILED " + line)
    if feeds and len(failures) == len(feeds):
        sys.exit("every feed failed to fetch")


if __name__ == "__main__":
    main()
