"""docs/compare.html: how closely the Google Alerts feeds and the Serper feeds match.

Both sources are matched by URL (see norm). Serper's first search per feed is its baseline,
so the head-to-head starts when Serper started (its first run, T0). A page is in the
head-to-head when the alert reported it after T0 or Serper found it after its baseline:
  - both: each source found it (Serper's baseline counts, so Serper can have had it first);
  - only Alerts / only Serper: the other source never returned it.
Match rate is both / all pages. A page first found in the last SETTLE_HOURS is "still
settling" and left out of the headline, since the other source may simply not have checked
yet (Alerts are read every 20 minutes, Serper hourly). Pages the alerts found before T0 are
checked against Serper's records separately. Listing and archive pages (is_listing) are
left out on both sides. Standard library only; build.py passes in its helpers and styles
so this module never imports it.
"""

import datetime as dt
import html
import os
import re
import statistics
import urllib.parse


# Query parameters that only track a click, never change the page. Google adds srsltid to
# result links and it differs between searches, so the same page would look new each time.
TRACKING = re.compile(r"^(utm_.*|srsltid|gclid|fbclid|mc_cid|mc_eid|_hsenc|_hsmi)$", re.I)
# Listing and archive pages rather than articles: /page/3, /tag/x, /category/x, /author/x,
# ?page=2, or a bare section such as /news or /blog.
ARCHIVE_PATH = re.compile(r"(^|/)(page/\d+|tag/[^/]+|category/[^/]+|author/[^/]+)/?$", re.I)
SECTION_ONLY = {"", "news", "blog", "blogs", "newsroom", "press", "press-releases", "press-room", "media",
                "articles", "insights", "resources", "company-news", "updates"}


def clean_link(url):
    """The link with click-tracking parameters removed."""
    parts = urllib.parse.urlsplit((url or "").strip())
    query = urllib.parse.urlencode(
        [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True) if not TRACKING.match(k)]
    )
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def norm(url):
    """Matching key for a URL: no scheme, www., trailing slash or tracking parameters."""
    parts = urllib.parse.urlsplit(clean_link(url))
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path.rstrip("/") or "/"
    return host + path + ("?" + parts.query if parts.query else "")


def is_listing(url):
    """True for a listing or archive page rather than an article (see ARCHIVE_PATH)."""
    parts = urllib.parse.urlsplit(url or "")
    if parts.path.strip("/").lower() in SECTION_ONLY or ARCHIVE_PATH.search(parts.path):
        return True
    return any(k.lower() in ("page", "paged") for k, _ in urllib.parse.parse_qsl(parts.query))


SETTLE_HOURS = 12

COMPARE_STYLE = """
:root { --green600: #13855C; --green25: #E8F6F0; --green35: #BFE6D5; }
.hero { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 40px; margin-top: 24px; }
.rate b { display: block; font-size: 56px; line-height: 64px; font-weight: 700; color: var(--onyx900); font-variant-numeric: tabular-nums; }
.rate span { font-size: 14px; line-height: 22px; color: var(--onyx500); }
.hero .stats { margin-top: 0; }
.bar { display: flex; height: 12px; border-radius: 999px; overflow: hidden; background: var(--onyx100); min-width: 80px; }
.bar i { display: block; height: 100%; }
.bar.big { height: 20px; margin: 16px 0 8px; max-width: 760px; }
.seg-a { background: var(--purple6); } .seg-b { background: var(--green600); } .seg-s { background: var(--blue400); }
.legend { display: flex; flex-wrap: wrap; gap: 16px; font-size: 14px; line-height: 22px; color: var(--onyx500); }
.legend span::before { content: ""; display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px; vertical-align: 0; }
.legend .l-a::before { background: var(--purple6); } .legend .l-b::before { background: var(--green600); } .legend .l-s::before { background: var(--blue400); }
.cmp, .days table { table-layout: auto; }
.cmp { min-width: 1100px; }
.cmp th, .days th { white-space: nowrap; }
.cmp td.n, .cmp th.n { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
.cmp th.c-comp { width: 18%; } .cmp td code { overflow-wrap: anywhere; }
.cmp td .bar { min-width: 140px; }
.cmp th button { all: unset; cursor: pointer; } .cmp th button:hover { color: var(--onyx800); }
.cmp th button[aria-sort="ascending"]::after { content: " \\25B4"; } .cmp th button[aria-sort="descending"]::after { content: " \\25BE"; }
tr.detail .toggle::after { content: "Show pages \\25BE"; } tr.detail details[open] .toggle::after { content: "Hide pages \\25B4"; }
.pct { font-size: 16px; line-height: 24px; font-weight: 600; color: var(--onyx900); }
.zero { color: var(--onyx300); }
.only-a { color: var(--purple6); font-weight: 600; }
.only-s { color: var(--blue500); font-weight: 600; }
.both { color: var(--green600); font-weight: 600; }
.urls { padding: 4px 24px 16px; }
.urls h4 { margin: 12px 0 4px; font-size: 12px; line-height: 18px; font-weight: 500; letter-spacing: 0.08em; text-transform: uppercase; color: var(--onyx500); }
.urls ul { margin: 0; padding-left: 18px; }
.urls li { font-size: 14px; line-height: 22px; margin: 2px 0; overflow-wrap: anywhere; }
.urls .when { color: var(--onyx500); }
.note { font-size: 14px; line-height: 22px; color: var(--onyx500); margin: 0 0 16px; max-width: 900px; }
.pad { padding: 0 24px 24px; }
tr.detail td { padding: 0; background: var(--onyx25); }
tr.detail summary { padding: 8px 16px; }
.days td, .days th { text-align: right; } .days td:first-child, .days th:first-child { text-align: left; }
.days table { min-width: 560px; }
"""

SORT_SCRIPT = """
document.querySelectorAll('table.cmp').forEach(function (table) {
  var body = table.tBodies[0];
  table.querySelectorAll('th button').forEach(function (btn, col) {
    btn.addEventListener('click', function () {
      var asc = btn.getAttribute('aria-sort') !== 'ascending';
      table.querySelectorAll('th button').forEach(function (b) { b.removeAttribute('aria-sort'); });
      btn.setAttribute('aria-sort', asc ? 'ascending' : 'descending');
      var rows = Array.prototype.filter.call(body.rows, function (r) { return !r.classList.contains('detail'); });
      rows.sort(function (a, b) {
        var x = a.cells[col].getAttribute('data-sort'), y = b.cells[col].getAttribute('data-sort');
        var nx = parseFloat(x), ny = parseFloat(y);
        var c = (!isNaN(nx) && !isNaN(ny)) ? nx - ny : String(x).localeCompare(String(y));
        return asc ? c : -c;
      });
      rows.forEach(function (r) {
        var d = r.nextElementSibling && r.nextElementSibling.classList.contains('detail') ? r.nextElementSibling : null;
        body.appendChild(r); if (d) body.appendChild(d);
      });
    });
  });
});
"""


def _minutes(delta):
    return delta.total_seconds() / 60


def _lead_text(minutes):
    if abs(minutes) < 1:
        return "same check"
    span = ("%.0f min" % abs(minutes)) if abs(minutes) < 90 else ("%.1f h" % (abs(minutes) / 60))
    return ("Serper %s earlier" if minutes > 0 else "Alerts %s earlier") % span


def _pct(part, whole):
    return None if not whole else 100.0 * part / whole


def _tally(pages):
    """Counts and rates for a list of page records."""
    both = [p for p in pages if p["status"] == "both"]
    only_a = [p for p in pages if p["status"] == "only_a"]
    only_s = [p for p in pages if p["status"] == "only_s"]
    leads = [p["lead"] for p in both]
    return dict(
        total=len(pages), both=len(both), only_a=len(only_a), only_s=len(only_s),
        match=_pct(len(both), len(pages)),
        alerts_cov=_pct(len(both), len(both) + len(only_a)),  # of the alerts' pages, share Serper also found
        serper_cov=_pct(len(both), len(both) + len(only_s)),  # of Serper's pages, share the alerts also found
        serper_first=sum(1 for l in leads if l >= 1), alerts_first=sum(1 for l in leads if l <= -1),
        median_lead=statistics.median(leads) if leads else None,
    )


def analyze(config, google_state, serper_state, parse_iso, now=None):
    """Page-by-page comparison; None when Serper hasn't run yet."""
    meta = serper_state.get("_meta") or {}
    if not meta.get("first_run"):
        return None
    now = now or dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    t0 = parse_iso(meta["first_run"])
    settle = now - dt.timedelta(hours=SETTLE_HOURS)
    s_feeds = serper_state.get("feeds") or {}
    pages, feeds, retro, retro_hit = [], [], 0, 0
    for slug, feed in config["feeds"].items():
        g = {}
        for entry in (google_state.get(slug) or {}).values():
            if is_listing(entry["link"]):
                continue
            k, t = norm(entry["link"]), parse_iso(entry["first_seen"])
            if k not in g or t < g[k][0]:
                g[k] = (t, entry)
        s = {k: (parse_iso(v["first_seen"]), v) for k, v in (s_feeds.get(slug) or {}).items() if not is_listing(v["link"])}
        window = {k for k, (t, _) in g.items() if t >= t0} | {k for k, (_, v) in s.items() if not v.get("baseline")}
        feed_pages = []
        for k in sorted(window):
            a, b = g.get(k), s.get(k)
            first = min(x[0] for x in (a, b) if x)
            page = dict(slug=slug, key=k, alerts=a, serper=b, first=first, settled=first <= settle,
                        status="both" if a and b else ("only_a" if a else "only_s"),
                        lead=_minutes(a[0] - b[0]) if a and b else None,
                        entry=(a or b)[1])
            feed_pages.append(page)
        old = [k for k, (t, _) in g.items() if t < t0]
        hits = [k for k in old if k in s]
        retro += len(old)
        retro_hit += len(hits)
        pages.extend(feed_pages)
        feeds.append(dict(slug=slug, feed=feed, pages=feed_pages, retro=len(old), retro_hit=len(hits),
                          all=_tally(feed_pages), settled=_tally([p for p in feed_pages if p["settled"]])))
    days = {}
    for p in pages:
        days.setdefault(p["first"].strftime("%Y-%m-%d"), []).append(p)
    return dict(t0=t0, now=now, meta=meta, pages=pages, feeds=feeds,
                all=_tally(pages), settled=_tally([p for p in pages if p["settled"]]),
                days=[(d, _tally(ps)) for d, ps in sorted(days.items())], retro=retro, retro_hit=retro_hit)


def _bar(t, big=False):
    if not t["total"]:
        return '<div class="bar%s"></div>' % (" big" if big else "")
    seg = lambda cls, n: ('<i class="%s" style="width:%.2f%%" title="%d"></i>' % (cls, 100.0 * n / t["total"], n)) if n else ""
    return '<div class="bar%s">%s%s%s</div>' % (" big" if big else "", seg("seg-a", t["only_a"]), seg("seg-b", t["both"]), seg("seg-s", t["only_s"]))


def _fmt_pct(v):
    return "-" if v is None else "%.0f%%" % v


def write_compare(config, google_state, serper_state, root, parse_iso, fmt_when, base_style, order):
    esc = html.escape
    result = analyze(config, google_state, serper_state, parse_iso)
    settings = config.get("serper") or {}
    portals = {p.get("source") or "google": p for p in config.get("portals", [])}
    portal_links = " &middot; ".join(
        '<a href="%s">%s portal &#8599;</a>' % (esc(p["url"]), "Google Alerts" if src == "google" else "Serper")
        for src, p in sorted(portals.items()))

    def link(entry):
        return '<a href="%s">%s</a>' % (esc(entry["link"]), esc(entry.get("title") or entry["link"]))

    if result is None:
        hero = ""
        body = ('<section class="portal"><div class="portal-head"><div><h2>Serper hasn\'t run yet</h2>'
                '<p class="note">The comparison starts with Serper\'s first search.</p></div></div></section>')
    else:
        settled, everything = result["settled"], result["all"]
        head_t = settled if settled["total"] else everything
        head_label = ("pages first found over %d hours ago" % SETTLE_HOURS) if settled["total"] else "all pages so far (none have settled yet)"
        lead = head_t["median_lead"]
        hero = (
            '<div class="hero"><div class="rate"><b>%s</b><span>match rate &middot; %s</span></div>'
            '<div class="stats">'
            '<div class="stat"><b>%s</b><span>of the alerts\' pages, Serper also found</span></div>'
            '<div class="stat"><b>%s</b><span>of Serper\'s pages, the alerts also found</span></div>'
            '<div class="stat"><b>%s</b><span>who saw shared pages first (median)</span></div>'
            "</div></div>"
            "%s"
            '<div class="legend"><span class="l-a">Only Alerts %d</span><span class="l-b">Both %d</span><span class="l-s">Only Serper %d</span>'
            "<span>%d pages compared%s</span></div>"
        ) % (_fmt_pct(head_t["match"]), esc(head_label), _fmt_pct(head_t["alerts_cov"]), _fmt_pct(head_t["serper_cov"]),
             esc(_lead_text(lead)) if lead is not None else "-", _bar(head_t, big=True),
             head_t["only_a"], head_t["both"], head_t["only_s"], head_t["total"],
             (", plus %d still settling" % (everything["total"] - settled["total"])) if settled["total"] and everything["total"] > settled["total"] else "")

        rows = []
        for f in sorted(result["feeds"], key=lambda f: (f["feed"]["competitor"].lower(), order.get(f["feed"]["category"], 9))):
            t, feed = f["all"], f["feed"]
            detail = []
            groups = [("Found by both", "both"), ("Only Alerts", "only_a"), ("Only Serper", "only_s")]
            for title, status in groups:
                ps = [p for p in f["pages"] if p["status"] == status]
                if not ps:
                    continue
                items = []
                for p in sorted(ps, key=lambda p: p["first"], reverse=True):
                    when = []
                    if p["alerts"]:
                        when.append("Alerts " + fmt_when(p["alerts"][0]))
                    if p["serper"]:
                        when.append(("Serper first search" if p["serper"][1].get("baseline") else "Serper ") +
                                    ("" if p["serper"][1].get("baseline") else fmt_when(p["serper"][0])))
                    if p["lead"] is not None:
                        when.append(_lead_text(p["lead"]))
                    if not p["settled"]:
                        when.append("still settling")
                    items.append('<li>%s <span class="when">&middot; %s</span></li>' % (link(p["entry"]), esc(" · ".join(when))))
                detail.append("<h4>%s</h4><ul>%s</ul>" % (title, "".join(items)))
            if f["retro"]:
                detail.append('<h4>Before Serper started</h4><p class="note">The alert had found %d page%s; %d %s in Serper\'s records.</p>'
                              % (f["retro"], "" if f["retro"] == 1 else "s", f["retro_hit"], "is" if f["retro_hit"] == 1 else "are"))
            match = t["match"]
            rows.append(
                '<tr><td data-sort="%s"><div class="name">%s</div><div class="sub">%s</div></td>'
                '<td data-sort="%s"><code>%s</code>%s</td>'
                '<td class="n" data-sort="%d">%s</td><td class="n" data-sort="%d">%s</td><td class="n" data-sort="%d">%s</td>'
                '<td class="n" data-sort="%d">%s</td><td class="n" data-sort="%s"><span class="pct">%s</span></td><td data-sort="%s">%s</td></tr>'
                % (esc(feed["competitor"].lower()), esc(feed["competitor"]), esc(feed["category"]),
                   esc(feed["query"]), esc(feed["query"]),
                   ('<div class="sub">past day</div>' if feed.get("serper_tbs") == "qdr:d" else ""),
                   t["both"], ('<span class="both">%d</span>' % t["both"]) if t["both"] else '<span class="zero">0</span>',
                   t["only_a"], ('<span class="only-a">%d</span>' % t["only_a"]) if t["only_a"] else '<span class="zero">0</span>',
                   t["only_s"], ('<span class="only-s">%d</span>' % t["only_s"]) if t["only_s"] else '<span class="zero">0</span>',
                   t["total"], t["total"] if t["total"] else '<span class="zero">0</span>',
                   "%.4f" % match if match is not None else "-1", _fmt_pct(match),
                   "%.4f" % match if match is not None else "-1", _bar(t))
            )
            if detail:
                rows.append('<tr class="detail"><td colspan="7"><details><summary><span class="toggle"></span></summary>'
                            '<div class="urls">%s</div></details></td></tr>' % "".join(detail))
        feed_table = (
            '<section class="portal"><div class="portal-head"><div><div class="eyebrow">By alert</div><h2>How each feed matches</h2>'
            '<p class="note">Counts include pages still settling. Click a header to sort; open a row to see the pages.</p></div></div>'
            '<div class="table-wrap"><table class="cmp"><thead><tr>'
            '<th class="c-comp"><button type="button">Competitor</button></th><th class="c-q"><button type="button">Query</button></th>'
            '<th class="n"><button type="button">Both</button></th><th class="n"><button type="button">Only Alerts</button></th>'
            '<th class="n"><button type="button">Only Serper</button></th><th class="n"><button type="button">Pages</button></th>'
            '<th class="n"><button type="button">Match</button></th><th class="c-bar"><button type="button">Split</button></th>'
            "</tr></thead><tbody>%s</tbody></table></div></section>"
        ) % "".join(rows)

        day_rows = "".join(
            '<tr><td>%s</td><td>%d</td><td>%d</td><td>%d</td><td>%d</td><td>%s</td></tr>'
            % (esc(d), t["total"], t["both"], t["only_a"], t["only_s"], _fmt_pct(t["match"])) for d, t in result["days"])
        day_table = (
            '<section class="portal"><div class="portal-head"><div><div class="eyebrow">Over time</div><h2>By day first found</h2></div></div>'
            '<div class="table-wrap days"><table><thead><tr><th>Day (UTC)</th><th>Pages</th><th>Both</th><th>Only Alerts</th>'
            "<th>Only Serper</th><th>Match</th></tr></thead><tbody>%s</tbody></table></div></section>"
        ) % day_rows

        meta = result["meta"]
        method = (
            '<section class="portal"><div class="portal-head"><div><div class="eyebrow">How this is measured</div><h2>Method</h2>'
            '<p class="note">Both sources run the same <code>site:</code> query per alert. The alerts are read every 20 minutes; '
            "Serper searches every %d minutes over the past week (the past day for %s), paging 10 results at a time. "
            "Serper's first search for each feed (%s) is a baseline: it isn't counted as found, but it does count as Serper having the "
            "page if the alert reports it later. Pages are matched by URL, ignoring tracking parameters; listing and archive pages "
            "(/news, /page/3, /tag/...) are left out on both sides. A page first found in the last %d hours is still settling, because the "
            "other source may not have checked yet; the headline leaves those out. Before Serper started, the alerts had already found "
            "%d pages; %d of them are in Serper's records. Serper has run %d times and used %d credits%s.</p>"
            "</div></div></section>"
        ) % (settings.get("every_minutes", 60),
             esc(", ".join(sorted(f["competitor"] for f in config["feeds"].values() if f.get("serper_tbs") == "qdr:d")) or "none"),
             esc(fmt_when(result["t0"])), SETTLE_HOURS, result["retro"], result["retro_hit"],
             meta.get("runs", 0), meta.get("credits_used", 0),
             (". Last error: " + esc(meta["last_error"])) if meta.get("last_error") else "")
        body = feed_table + day_table + method

    page = (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="robots" content="noindex, nofollow">\n'
        "<title>Alerts vs Serper</title>\n<style>%s%s</style>\n</head>\n<body>\n"
        '<header class="top"><div class="container">'
        '<div class="eyebrow"><a href="./">Alert feeds</a> &middot; Comparison</div>'
        "<h1>How closely do Google Alerts and Serper match?</h1>"
        '<p class="lede">The same 39 site: queries, two ways: as Google Alerts, and as hourly Serper searches checked for new URLs. '
        "Pages are matched by URL.%s</p>%s"
        "</div></header>\n"
        '<main class="container">%s</main>\n'
        '<footer class="container">Built by <a href="https://github.com/JonahLopin/alert-feeds">github.com/JonahLopin/alert-feeds</a>.</footer>\n'
        "<script>%s</script>\n</body>\n</html>\n"
    ) % (base_style, COMPARE_STYLE, (" " + portal_links + ".") if portal_links else "", hero, body, SORT_SCRIPT)
    with open(os.path.join(root, "docs", "compare.html"), "w") as fh:
        fh.write(page)
