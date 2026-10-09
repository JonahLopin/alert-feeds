#!/usr/bin/env python3
"""Republish Google Alerts RSS feeds with usable entry dates.

Google Alerts feeds stamp every entry 1970-01-01, so feed readers that go by date
(Crayon's RSSeymour among them) skip everything. This fetches each alert feed,
records when each entry was first seen, and writes one clean Atom feed per alert to
docs/feeds/<slug>.xml, dated by that first-seen time. Links are unwrapped from
Google's redirect to the real article URL. docs/index.html lists the feeds under
the Crayon portal each one is wired into.

config.json holds the portals and, per feed, the Google feed URL, the alert query,
the competitor and the insight type and subtype it is wired to. Standard library only.
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

import compare

ATOM_NS = "http://www.w3.org/2005/Atom"
ATOM = "{%s}" % ATOM_NS
ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(ROOT, "config.json")
STATE_PATH = os.path.join(ROOT, "state.json")
OUT_DIR = os.path.join(ROOT, "docs", "feeds")
# serper_build.py records the Serper side here; this script turns it into docs/serper/<slug>.xml.
SERPER_STATE_PATH = os.path.join(ROOT, "serper_state.json")
SERPER_OUT_DIR = os.path.join(ROOT, "docs", "serper")
KEEP_DAYS = 60
MAX_ENTRIES = 100
PAGES_BASE = os.environ.get("PAGES_BASE", "").rstrip("/")
# No entry is dated before this moment. A reader that registers a feed while it is
# still empty then sees the backlog arrive as new items once this time passes.
PUBLISH_START = os.environ.get("PUBLISH_START") or "1970-01-01T00:00:00Z"
SERPER_PUBLISH_START = os.environ.get("SERPER_PUBLISH_START") or "1970-01-01T00:00:00Z"
TAG = re.compile(r"<[^>]+>")
CATEGORY_ORDER = {"help": 0, "press": 1, "blog": 2}


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


def feed_title(feed):
    return "%s %s (%s)" % (feed["competitor"], feed["category"], feed["query"])


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


def write_feed(slug, feed_cfg, seen, now, start, out_dir=OUT_DIR, path="feeds", urn="alert-feeds", source=""):
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
    ET.SubElement(feed, "id").text = "urn:%s:%s" % (urn, slug)
    ET.SubElement(feed, "title").text = feed_title(feed_cfg) + source
    # Latest entry date rather than build time, so an unchanged feed writes identical bytes.
    ET.SubElement(feed, "updated").text = iso(items[0][0]) if items else iso(start)
    if PAGES_BASE:
        ET.SubElement(feed, "link", {"rel": "self", "href": "%s/%s/%s.xml" % (PAGES_BASE, path, slug)})
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
    ET.ElementTree(feed).write(os.path.join(out_dir, slug + ".xml"), encoding="utf-8", xml_declaration=True)
    return len(items), (items[0][0] if items else None)


# Crayon @crayon/box tokens (product palette, Calibre type, 16px rhythm).
INDEX_STYLE = """
:root {
  color-scheme: light;
  --ff-base: Calibre, 'HelveticaNeue-Light', 'Helvetica Neue Light', 'Helvetica Neue', Helvetica, Arial, 'Lucida Grande', sans-serif;
  --ff-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  --white: #FFFFFF; --onyx25: #F6F7F7; --onyx50: #ECEEEF; --onyx100: #E3E6E8; --onyx300: #A2ACB1;
  --onyx500: #606E75; --onyx700: #363D41; --onyx800: #1F2325; --onyx900: #101213;
  --onyx200: #C7CDD0;
  --blue25: #E6EFFA; --blue35: #CDE0F6; --blue50: #9AC1ED; --blue400: #0363D1; --blue500: #024FA7;
  --blurple25: #F5F6FE; --blurple100: #B9C2F6; --blurple600: #1731BB;
  --purple1: #f9f0ff; --purple3: #d3adf7; --purple6: #722ed1;
  --gold500: #C6900A;
  --shadow-card: 0 1px 2px rgba(0, 10, 21, 0.04);
}
* { box-sizing: border-box; }
html, body { margin: 0; background: var(--onyx25); color: var(--onyx700); }
body { font: 400 16px/24px var(--ff-base); -webkit-font-smoothing: antialiased; }
a { color: var(--blue400); text-decoration: none; }
a:hover { color: var(--blue500); text-decoration: underline; }
.container { max-width: 1240px; margin: 0 auto; padding: 0 24px; }
.top { background: var(--white); border-bottom: 1px solid var(--onyx100); padding: 40px 0 32px; }
.eyebrow { font-size: 12px; line-height: 18px; font-weight: 500; letter-spacing: 0.08em; text-transform: uppercase; color: var(--onyx500); }
h1 { margin: 4px 0 8px; font-size: 26px; line-height: 40px; font-weight: 600; color: var(--onyx900); }
.lede { margin: 0; max-width: 760px; font-size: 16px; line-height: 24px; color: var(--onyx500); }
.stats { display: flex; flex-wrap: wrap; gap: 32px; margin-top: 24px; }
.stat b { display: block; font-size: 28px; line-height: 42px; font-weight: 700; color: var(--blue500); font-variant-numeric: tabular-nums; }
.stat span { font-size: 14px; line-height: 22px; color: var(--onyx500); }
main { padding: 32px 0 40px; }
.portal { background: var(--white); border: 1px solid var(--onyx100); border-radius: 8px; box-shadow: var(--shadow-card); margin-bottom: 24px; }
.portal-head { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: 16px; padding: 24px; }
.portal h2 { margin: 4px 0 4px; font-size: 22px; line-height: 32px; font-weight: 600; color: var(--onyx900); }
.portal h2 a { color: inherit; }
.links { font-size: 14px; line-height: 22px; color: var(--onyx300); }
.links a { font-weight: 500; }
.portal-stats { display: flex; gap: 24px; font-size: 14px; line-height: 22px; color: var(--onyx500); }
.portal-stats b { color: var(--onyx800); font-weight: 600; font-variant-numeric: tabular-nums; }
details { border-top: 1px solid var(--onyx100); }
summary { list-style: none; cursor: pointer; padding: 16px 24px; display: flex; align-items: center; gap: 12px; }
summary::-webkit-details-marker { display: none; }
summary:focus-visible { outline: none; box-shadow: inset 0 0 0 3px var(--blue35); }
.chip { display: inline-flex; align-items: center; gap: 8px; padding: 4px 12px; border-radius: 999px; background: var(--blue25); border: 1px solid var(--blue35); color: var(--blue500); font-size: 14px; line-height: 22px; font-weight: 500; }
.chip::before { content: ""; width: 6px; height: 6px; border-radius: 999px; background: var(--blue400); }
.toggle { font-size: 14px; line-height: 22px; color: var(--onyx500); }
.toggle::after { content: "Show feeds \\25BE"; }
details[open] .toggle::after { content: "Hide feeds \\25B4"; }
.table-wrap { overflow-x: auto; border-top: 1px solid var(--onyx100); }
table { width: 100%; min-width: 1040px; border-collapse: collapse; table-layout: fixed; }
th { background: var(--onyx25); text-align: left; padding: 8px 16px; font-size: 12px; line-height: 18px; font-weight: 500; letter-spacing: 0.08em; text-transform: uppercase; color: var(--onyx500); border-bottom: 1px solid var(--onyx100); }
td { padding: 12px 16px; border-bottom: 1px solid var(--onyx100); vertical-align: top; font-size: 14px; line-height: 22px; }
tr:last-child td { border-bottom: 0; }
tbody tr:hover td { background: var(--onyx25); }
.name { font-size: 16px; line-height: 24px; font-weight: 600; color: var(--onyx800); }
.sub { color: var(--onyx500); }
.sep { color: var(--onyx300); padding: 0 8px; }
code { font-family: var(--ff-mono); font-size: 13px; line-height: 20px; color: var(--onyx800); overflow-wrap: anywhere; }
td.num { text-align: right; white-space: nowrap; }
td.feeds { white-space: nowrap; }
th.c-comp { width: 17%; } th.c-alert { width: 31%; } th.c-feeds { width: 14%; } th.c-num { width: 11%; text-align: right; } th.c-wired { width: 27%; }
th button { all: unset; cursor: pointer; display: inline-flex; align-items: center; gap: 4px; }
th button:hover { color: var(--onyx800); }
th button:focus-visible { box-shadow: 0 0 0 3px var(--blue50); border-radius: 4px; }
th button::after { content: "\\2195"; opacity: 0.4; }
th[aria-sort] button { color: var(--onyx800); }
th[aria-sort="ascending"] button::after { content: "\\25B2"; opacity: 1; font-size: 9px; }
th[aria-sort="descending"] button::after { content: "\\25BC"; opacity: 1; font-size: 9px; }
.toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; padding: 0 24px 16px; }
.search { flex: 1 1 280px; max-width: 420px; padding: 8px 12px; border: 1px solid var(--onyx200); border-radius: 6px; background: var(--white); font: 400 16px/24px var(--ff-base); color: var(--onyx800); }
.search:focus { outline: none; border-color: var(--blue400); box-shadow: 0 0 0 3px var(--blue25); }
.match-count { font-size: 14px; line-height: 22px; color: var(--onyx500); }
.empty { margin: 0; padding: 16px 24px; font-size: 14px; line-height: 22px; color: var(--onyx500); }
.wired { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
a.tag:hover { text-decoration: none; filter: brightness(0.96); }
.btn-sm { display: inline-flex; align-items: center; padding: 2px 10px; border: 1px solid var(--blue400); border-radius: 6px; background: var(--white); color: var(--blue400); font-size: 12px; line-height: 18px; font-weight: 500; white-space: nowrap; }
.btn-sm:hover { background: var(--blue25); color: var(--blue500); text-decoration: none; }
.count { font-size: 18px; line-height: 28px; font-weight: 600; color: var(--onyx900); font-variant-numeric: tabular-nums; }
.waiting { color: var(--gold500); font-weight: 500; }
.tag { display: inline-flex; align-items: center; gap: 4px; padding: 2px 10px; border-radius: 999px; font-size: 12px; line-height: 18px; font-weight: 500; white-space: nowrap; }
.t-product { background: var(--blue25); border: 1px solid var(--blue35); color: var(--blue500); }
.t-content { background: var(--blurple25); border: 1px solid var(--blurple100); color: var(--blurple600); }
.t-news { background: var(--purple1); border: 1px solid var(--purple3); color: var(--purple6); }
.t-other { background: var(--onyx25); border: 1px solid var(--onyx100); color: var(--onyx700); }
footer { padding: 0 0 40px; font-size: 14px; line-height: 22px; color: var(--onyx500); }
@media (min-width: 769px) { .container { padding: 0 40px; } }
"""
TYPE_CLASS = {"Product": "t-product", "Content Marketing": "t-content", "News & PR": "t-news"}
# Click a column header to sort (again to reverse); type in the search box to filter rows.
INDEX_SCRIPT = """
(function () {
  function textCompare(a, b) { return a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" }); }
  function feeds(n) { return n + (n === 1 ? " feed" : " feeds"); }
  document.querySelectorAll(".feed-list").forEach(function (box) {
    var table = box.querySelector("table"), tbody = table.tBodies[0];
    var rows = Array.prototype.slice.call(tbody.rows);
    var input = box.querySelector(".search"), count = box.querySelector(".match-count"), empty = box.querySelector(".empty");
    input.addEventListener("input", function () {
      var q = input.value.trim().toLowerCase(), shown = 0;
      rows.forEach(function (r) {
        var hit = !q || r.getAttribute("data-search").indexOf(q) !== -1;
        r.hidden = !hit;
        if (hit) shown++;
      });
      count.textContent = q ? shown + " of " + feeds(rows.length) : feeds(rows.length);
      empty.hidden = shown !== 0;
    });
    var ths = Array.prototype.slice.call(table.tHead.rows[0].cells);
    ths.forEach(function (th, idx) {
      th.querySelector("button").addEventListener("click", function () {
        var num = th.getAttribute("data-type") === "num", cur = th.getAttribute("aria-sort");
        var dir = cur ? (cur === "ascending" ? "descending" : "ascending") : (num ? "descending" : "ascending");
        ths.forEach(function (h) { h.removeAttribute("aria-sort"); });
        th.setAttribute("aria-sort", dir);
        rows.sort(function (a, b) {
          var x = a.cells[idx].getAttribute("data-sort"), y = b.cells[idx].getAttribute("data-sort");
          var c = num ? parseFloat(x) - parseFloat(y) : textCompare(x, y);
          if (c !== 0) return dir === "ascending" ? c : -c;
          return textCompare(a.getAttribute("data-key"), b.getAttribute("data-key"));
        });
        rows.forEach(function (r) { tbody.appendChild(r); });
      });
    });
  });
})();
"""


def insights_url(portal, competitor_id, subtype_id):
    """The portal's insight search filtered to one competitor and one subtype, all time.
    portal["url"] is any page in the portal, e.g. https://app.crayon.co/intel/<portal>/search/."""
    m = re.match(r"(https?://[^/]+/intel/[^/]+)", (portal or {}).get("url") or "")
    if not m or not competitor_id or not subtype_id:
        return None
    return "%s/search/competitor/%s/subtype/%s/timerange/all_time/" % (m.group(1), competitor_id, subtype_id)


def fmt_when(t):
    return t.strftime("%b %-d, %H:%M UTC")


SOURCES = {
    # source -> (feed key holding its Crayon wiring, label, folder its feeds are served from)
    "google": ("crayon", "Google Alerts", "feeds"),
    "serper": ("serper_crayon", "Serper", "serper"),
}


def write_index(config, state, results, start, serper_state, serper_results, serper_start):
    """docs/index.html: each Crayon portal with a chip for how many feeds are wired into it,
    expanding to one row per feed. A portal's "source" ("google", the default, or "serper")
    says which version of the feeds it reads. Built only from entry dates and run records,
    never the build time, so the page changes only when a feed does."""
    esc = html.escape
    feeds = config["feeds"]
    s_feeds = serper_state.get("feeds") or {}
    s_meta = serper_state.get("_meta") or {}
    tbs = (config.get("serper") or {}).get("tbs") or "qdr:w"

    def tally(slug, source):
        """(published, waiting, latest, baseline) for one feed in one source."""
        if source == "serper":
            entries = s_feeds.get(slug) or {}
            published, latest = serper_results.get(slug, (0, None))
            live = sum(1 for v in entries.values() if not v.get("baseline"))
            return published, live - published, latest, len(entries) - live
        published, latest = results.get(slug, (0, None))
        return published, len(state.get(slug, {})) - published, latest, 0

    def counts(slugs, source):
        rows = [tally(s, source) for s in slugs]
        return sum(r[0] for r in rows), sum(r[1] for r in rows)

    def row(slug, source, portal=None):
        f = feeds[slug]
        crayon = f.get(SOURCES[source][0]) or {}
        link = insights_url(portal, crayon.get("competitor_id"), f.get("insight_subtype_id")) if portal else None
        published, waiting, latest, baseline = tally(slug, source)
        competitor_sub = esc(f["category"])
        if crayon.get("competitor"):
            admin = "https://app.crayon.co/admin-console/dashboards/%s/competitor/%s/rss" % (crayon["portal"], crayon["competitor_id"])
            competitor_sub = '<a href="%s" title="RSS feeds for this competitor in the admin console">%s</a><span class="sep">&middot;</span>%s' % (
                esc(admin), esc(crayon["competitor"]), competitor_sub)
        entries = '<div class="count">%d</div>' % published
        if waiting > 0:
            entries += '<div class="waiting">+%d waiting</div>' % waiting
        entries += '<div class="sub">%s</div>' % (esc("Latest " + fmt_when(latest)) if latest else "No entries yet")
        if baseline:
            entries += '<div class="sub" title="Results of the first search, recorded so they never count as new">%d in first search</div>' % baseline
        # Just the subtype; it and the button open the portal's insights for this competitor and subtype.
        klass = TYPE_CLASS.get(f.get("insight_type"), "t-other")
        subtype = esc(f.get("insight_subtype") or "-")
        if link:
            wired_cell = ('<div class="wired"><a class="tag %s" href="%s" title="Open these insights in the portal">%s</a>'
                          '<a class="btn-sm" href="%s">View insights &#8599;</a></div>') % (klass, esc(link), subtype, esc(link))
        else:
            wired_cell = '<div class="wired"><span class="tag %s">%s</span></div>' % (klass, subtype)
        key = "%s|%d|%s" % (f["competitor"].lower(), CATEGORY_ORDER.get(f["category"], 9), slug)
        haystack = " ".join([f["competitor"], crayon.get("competitor") or "", f["category"], f["query"], f.get("insight_subtype") or "", slug]).lower()
        if source == "serper":
            search = "https://www.google.com/search?q=%s&tbs=%s" % (urllib.parse.quote(f["query"], safe=""), urllib.parse.quote(tbs, safe=""))
            alert_link = '<a href="%s">Run the search &#8599;</a>' % esc(search)
            feed_links = '<a href="serper/%s.xml">Our feed</a><span class="sep">&middot;</span><a href="feeds/%s.xml">Alerts version</a>' % (esc(slug), esc(slug))
        else:
            view_alert = "https://www.google.com/alerts?q=%s&hl=en" % urllib.parse.quote(f["query"], safe="")
            alert_link = '<a href="%s">View alert &#8599;</a>' % esc(view_alert)
            feed_links = '<a href="feeds/%s.xml">Our feed</a><span class="sep">&middot;</span><a href="%s">Google feed</a>' % (esc(slug), esc(f["google_feed"]))
        return (
            '<tr data-key="%s" data-search="%s">'
            '<td data-sort="%s"><div class="name">%s</div><div class="sub">%s</div></td>'
            '<td data-sort="%s"><code>%s</code><div class="sub">%s</div></td>'
            '<td class="feeds" data-sort="%s">%s</td>'
            '<td class="num" data-sort="%d">%s</td>'
            '<td data-sort="%s">%s</td>'
            "</tr>"
        ) % (esc(key), esc(haystack), esc(key), esc(f["competitor"]), competitor_sub, esc(f["query"].lower()), esc(f["query"]), alert_link,
             esc(slug), feed_links, published, entries, esc(((f.get("insight_subtype") or "") + "|" + key).lower()), wired_cell)

    def table(slugs, source, portal=None):
        slugs = sorted(slugs, key=lambda s: (feeds[s]["competitor"].lower(), CATEGORY_ORDER.get(feeds[s]["category"], 9), s))
        # Rows start sorted by competitor, so that header starts marked ascending.
        head = ('<thead><tr>'
                '<th class="c-comp" aria-sort="ascending"><button type="button">Competitor</button></th>'
                '<th class="c-alert"><button type="button">%s</button></th>'
                '<th class="c-feeds"><button type="button">Feeds</button></th>'
                '<th class="c-num" data-type="num"><button type="button">Entries</button></th>'
                '<th class="c-wired" title="Insight subtype in Crayon"><button type="button">Wired to</button></th>'
                "</tr></thead>" % ("Search" if source == "serper" else "Alert"))
        return (
            '<div class="feed-list">'
            '<div class="toolbar"><input class="search" type="search" placeholder="Search competitor, %s or subtype" aria-label="Search feeds">'
            '<span class="match-count">%d feed%s</span></div>'
            '<div class="table-wrap"><table>%s<tbody>%s</tbody></table></div>'
            '<p class="empty" hidden>No feeds match your search.</p>'
            "</div>"
        ) % ("search" if source == "serper" else "alert", len(slugs), "" if len(slugs) == 1 else "s", head,
             "".join(row(s, source, portal) for s in slugs))

    sections = []
    wired = {source: set() for source in SOURCES}
    for portal in config.get("portals", []):
        source = portal.get("source") or "google"
        key, label, _ = SOURCES[source]
        slugs = [s for s, f in feeds.items() if (f.get(key) or {}).get("portal") == portal["id"]]
        wired[source].update(slugs)
        published, waiting = counts(slugs, source)
        competitors = len({(feeds[s].get(key) or {}).get("competitor_id") for s in slugs})
        sections.append(
            '<section class="portal">'
            '<div class="portal-head"><div>'
            '<div class="eyebrow">Crayon portal &middot; %d &middot; %s feeds</div>'
            '<h2><a href="%s">%s</a></h2>'
            '<div class="links"><a href="%s">Open portal &#8599;</a><span class="sep">&middot;</span><a href="%s">Admin console &#8599;</a></div>'
            "</div>"
            '<div class="portal-stats"><span><b>%d</b> competitors</span><span><b>%d</b> entries published</span>%s</div>'
            "</div>"
            "<details><summary><span class=\"chip\">This portal has %d feed%s wired into it</span><span class=\"toggle\"></span></summary>%s</details>"
            "</section>"
            % (portal["id"], esc(label), esc(portal["url"]), esc(portal["name"]), esc(portal["url"]), esc(portal.get("admin_url") or portal["url"]),
               competitors, published, ('<span><b>%d</b> waiting</span>' % waiting) if waiting else "",
               len(slugs), "" if len(slugs) == 1 else "s", table(slugs, source, portal))
        )
    for source in SOURCES:
        if source == "serper" and "serper" not in config:
            continue
        loose = [s for s in feeds if s not in wired[source]]
        if loose:
            sections.append(
                '<section class="portal"><div class="portal-head"><div><div class="eyebrow">Not wired into a portal yet</div>'
                "<h2>%s feeds</h2></div></div>"
                "<details><summary><span class=\"chip\">%d feed%s</span><span class=\"toggle\"></span></summary>%s</details></section>"
                % (esc(SOURCES[source][1]), len(loose), "" if len(loose) == 1 else "s", table(loose, source))
            )

    published, waiting = counts(list(feeds), "google")
    waiting_stat = ('<div class="stat"><b>%d</b><span>waiting until %s</span></div>' % (waiting, esc(fmt_when(start)))) if waiting else ""
    serper_stat = ""
    if "serper" in config:
        s_published, s_waiting = counts(list(feeds), "serper")
        serper_stat = '<div class="stat"><b>%d</b><span>Serper entries published%s</span></div>' % (
            s_published, esc(", %d waiting until %s" % (s_waiting, fmt_when(serper_start))) if s_waiting else "")
        if s_meta.get("last_run"):
            serper_stat += '<div class="stat"><b>%s</b><span>last Serper search &middot; %d credits used</span></div>' % (
                esc(fmt_when(parse_iso(s_meta["last_run"]))), s_meta.get("credits_used", 0))
    page = (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="robots" content="noindex, nofollow">\n'
        "<title>Alert Feeds</title>\n<style>%s</style>\n</head>\n<body>\n"
        '<header class="top"><div class="container">'
        '<div class="eyebrow">Alert feeds</div>'
        "<h1>Google Alerts, republished for Crayon</h1>"
        '<p class="lede">Google stamps every alert entry 1970-01-01, so Crayon skips them. Each feed here is the same alert '
        "with the date it was first seen and the real article link, checked every 20 minutes. The Serper feeds run the same "
        'site: queries as searches and publish each URL the first time it appears. <a href="compare.html">Compare Alerts and Serper &rarr;</a></p>'
        '<div class="stats"><div class="stat"><b>%d</b><span>feeds</span></div>'
        '<div class="stat"><b>%d</b><span>Alerts entries published</span></div>%s%s</div>'
        "</div></header>\n"
        '<main class="container">%s</main>\n'
        '<footer class="container">Built by <a href="https://github.com/JonahLopin/alert-feeds">github.com/JonahLopin/alert-feeds</a>.</footer>\n'
        "<script>%s</script>\n"
        "</body>\n</html>\n"
    ) % (INDEX_STYLE, len(feeds), published, waiting_stat, serper_stat, "".join(sections), INDEX_SCRIPT)
    with open(os.path.join(ROOT, "docs", "index.html"), "w") as fh:
        fh.write(page)

def main():
    with open(CONFIG_PATH) as fh:
        config = json.load(fh)
    feeds = config["feeds"]
    state = {}
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as fh:
            state = json.load(fh)
    now = utcnow()
    start = parse_iso(PUBLISH_START)
    cutoff = now - dt.timedelta(days=KEEP_DAYS)
    os.makedirs(OUT_DIR, exist_ok=True)

    failures, new_total, results = [], 0, {}
    for slug, feed_cfg in sorted(feeds.items()):
        seen = state.setdefault(slug, {})
        try:
            root = fetch(feed_cfg["google_feed"])
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
        results[slug] = write_feed(slug, feed_cfg, seen, now, start)
        time.sleep(2)

    for slug in [s for s in state if s not in feeds]:
        del state[slug]
    with open(STATE_PATH, "w") as fh:
        json.dump(state, fh, indent=1, sort_keys=True)
        fh.write("\n")

    # The Serper side: serper_build.py records what each search found; publish everything
    # but the baseline (first-search) results, keyed by the result's own URL. Every feed gets
    # a file, empty or not, so a feed can be registered before Serper has searched for it.
    serper_state = {}
    if os.path.exists(SERPER_STATE_PATH):
        with open(SERPER_STATE_PATH) as fh:
            serper_state = json.load(fh)
    serper_start = parse_iso(SERPER_PUBLISH_START)
    serper_results = {}
    if "serper" in config:
        os.makedirs(SERPER_OUT_DIR, exist_ok=True)
        for slug, feed_cfg in feeds.items():
            seen = (serper_state.get("feeds") or {}).get(slug) or {}
            live = {v["link"]: v for v in seen.values() if not v.get("baseline")}
            serper_results[slug] = write_feed(slug, feed_cfg, live, now, serper_start, out_dir=SERPER_OUT_DIR,
                                              path="serper", urn="serper-feeds", source=" via Serper")
    write_index(config, state, results, start, serper_state, serper_results, serper_start)
    compare.write_compare(config, state, serper_state, ROOT, parse_iso, fmt_when, INDEX_STYLE, CATEGORY_ORDER)

    published_total = sum(n for n, _ in results.values())
    print("feeds=%d new_entries=%d published_entries=%d failures=%d" % (len(feeds), new_total, published_total, len(failures)))
    for line in failures:
        print("FAILED " + line)
    if feeds and len(failures) == len(feeds):
        sys.exit("every feed failed to fetch")


if __name__ == "__main__":
    main()
