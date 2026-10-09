"""docs/compare.html: what each Google Alert found next to what Serper found for the same query.

Both sources are matched by URL (see norm). Serper's first search per feed is its baseline,
so the head-to-head counts start when Serper started (its first run, T0):
  - both: a page each source found, with which one saw it first;
  - only Alerts / only Serper: a page the other never returned.
Pages the alerts found before T0 are checked against Serper's baseline separately, as a
read on whether Serper's search would have caught them too. Listing and archive pages
(is_listing) are left out on both sides. Standard library only; build.py
passes in its helpers and styles so this module never imports it.
"""

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


COMPARE_STYLE = """
.cmp td.n, .cmp th.n { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
.cmp th.c-comp { width: 22%; } .cmp th.c-q { width: 30%; } .cmp th.n { width: 8%; }
.zero { color: var(--onyx300); }
.only-a { color: var(--purple6); font-weight: 600; }
.only-s { color: var(--blue500); font-weight: 600; }
.urls { padding: 4px 24px 16px; }
.urls h4 { margin: 12px 0 4px; font-size: 12px; line-height: 18px; font-weight: 500; letter-spacing: 0.08em; text-transform: uppercase; color: var(--onyx500); }
.urls ul { margin: 0; padding-left: 18px; }
.urls li { font-size: 14px; line-height: 22px; margin: 2px 0; overflow-wrap: anywhere; }
.urls .when { color: var(--onyx500); }
.note { font-size: 14px; line-height: 22px; color: var(--onyx500); margin: 0 0 16px; }
tr.detail td { padding: 0; background: var(--onyx25); }
"""


def _minutes(delta):
    return delta.total_seconds() / 60


def _lead_text(minutes):
    if abs(minutes) < 1:
        return "same run"
    hours = abs(minutes) / 60
    span = ("%.0f min" % abs(minutes)) if abs(minutes) < 90 else ("%.1f h" % hours)
    return ("Serper %s earlier" if minutes > 0 else "Alerts %s earlier") % span


def analyze(config, google_state, serper_state, parse_iso):
    """Per-feed comparison rows plus totals; None when Serper hasn't run yet."""
    meta = serper_state.get("_meta") or {}
    if not meta.get("first_run"):
        return None
    t0 = parse_iso(meta["first_run"])
    s_feeds = serper_state.get("feeds") or {}
    rows, totals, leads = [], dict(alerts=0, serper=0, both=0, only_a=0, only_s=0, retro=0, retro_hit=0), []
    for slug, feed in config["feeds"].items():
        g = {}
        for entry in (google_state.get(slug) or {}).values():
            if is_listing(entry["link"]):
                continue
            k, t = norm(entry["link"]), parse_iso(entry["first_seen"])
            if k not in g or t < g[k][0]:
                g[k] = (t, entry)
        s = {k: (parse_iso(v["first_seen"]), v) for k, v in (s_feeds.get(slug) or {}).items() if not is_listing(v["link"])}
        g_new = {k for k, (t, _) in g.items() if t >= t0}
        s_new = {k for k, (_, v) in s.items() if not v.get("baseline")}
        both, only_a, only_s = [], [], []
        for k in sorted(g_new | s_new):
            if k in g and k in s:
                lead = _minutes(g[k][0] - s[k][0])  # positive: Serper saw it first
                both.append((k, g[k], s[k], lead))
                leads.append(lead)
            elif k in g:
                only_a.append((k, g[k]))
            else:
                only_s.append((k, s[k]))
        retro = [k for k, (t, _) in g.items() if t < t0]
        retro_hit = [k for k in retro if k in s]
        rows.append(dict(slug=slug, feed=feed, alerts=len(g_new), serper=len(s_new), both=both, only_a=only_a,
                         only_s=only_s, retro=retro, retro_hit=retro_hit, g=g, s=s))
        totals["alerts"] += len(g_new)
        totals["serper"] += len(s_new)
        totals["both"] += len(both)
        totals["only_a"] += len(only_a)
        totals["only_s"] += len(only_s)
        totals["retro"] += len(retro)
        totals["retro_hit"] += len(retro_hit)
    totals["median_lead"] = statistics.median(leads) if leads else None
    return dict(t0=t0, meta=meta, rows=rows, totals=totals)


def write_compare(config, google_state, serper_state, root, parse_iso, fmt_when, base_style, order):
    esc = html.escape
    result = analyze(config, google_state, serper_state, parse_iso)

    def link(entry):
        return '<a href="%s">%s</a>' % (esc(entry["link"]), esc(entry.get("title") or entry["link"]))

    def num(n, cls=""):
        return '<span class="%s">%d</span>' % ("zero" if not n else cls, n)

    if result is None:
        body = '<section class="portal"><div class="portal-head"><div><h2>Serper hasn\'t run yet</h2>' \
               '<p class="note">The comparison starts with Serper\'s first search.</p></div></div></section>'
        stats = ""
    else:
        t, meta = result["totals"], result["meta"]
        lead = t["median_lead"]
        stats = (
            '<div class="stats">'
            '<div class="stat"><b>%d</b><span>found by Alerts</span></div>'
            '<div class="stat"><b>%d</b><span>found by Serper</span></div>'
            '<div class="stat"><b>%d</b><span>found by both</span></div>'
            '<div class="stat"><b>%d</b><span>only Alerts</span></div>'
            '<div class="stat"><b>%d</b><span>only Serper</span></div>'
            '<div class="stat"><b>%s</b><span>median, pages found by both</span></div>'
            "</div>"
        ) % (t["alerts"], t["serper"], t["both"], t["only_a"], t["only_s"], esc(_lead_text(lead)) if lead is not None else "-")
        rows = []
        for r in sorted(result["rows"], key=lambda r: (r["feed"]["competitor"].lower(), order.get(r["feed"]["category"], 9))):
            f = r["feed"]
            detail = []
            if r["both"]:
                detail.append("<h4>Found by both</h4><ul>%s</ul>" % "".join(
                    '<li>%s <span class="when">&middot; Alerts %s &middot; Serper %s &middot; %s</span></li>'
                    % (link(g[1]), esc(fmt_when(g[0])), esc(fmt_when(s[0])), esc(_lead_text(lead))) for k, g, s, lead in r["both"]))
            if r["only_a"]:
                detail.append("<h4>Only Alerts</h4><ul>%s</ul>" % "".join(
                    '<li>%s <span class="when">&middot; %s</span></li>' % (link(g[1]), esc(fmt_when(g[0]))) for k, g in r["only_a"]))
            if r["only_s"]:
                detail.append("<h4>Only Serper</h4><ul>%s</ul>" % "".join(
                    '<li>%s <span class="when">&middot; %s%s</span></li>'
                    % (link(s[1]), esc(fmt_when(s[0])), (" &middot; Google says " + esc(s[1]["date_hint"])) if s[1].get("date_hint") else "")
                    for k, s in r["only_s"]))
            if r["retro"]:
                detail.append("<h4>Found by Alerts before Serper started</h4><ul>%s</ul>" % "".join(
                    '<li>%s <span class="when">&middot; %s</span></li>'
                    % (link(r["g"][k][1]), "in Serper's first search" if k in r["s"] else "not in Serper's first search") for k in r["retro"]))
            rows.append(
                "<tr><td><div class=\"name\">%s</div><div class=\"sub\">%s</div></td><td><code>%s</code></td>"
                '<td class="n">%s</td><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td><td class="n">%s</td>'
                '<td class="n">%s</td></tr>'
                % (esc(f["competitor"]), esc(f["category"]), esc(f["query"]), num(r["alerts"]), num(r["serper"]), num(len(r["both"])),
                   num(len(r["only_a"]), "only-a"), num(len(r["only_s"]), "only-s"),
                   ("%d of %d" % (len(r["retro_hit"]), len(r["retro"]))) if r["retro"] else '<span class="zero">-</span>')
            )
            if detail:
                rows.append('<tr class="detail"><td colspan="8"><details><summary><span class="toggle"></span></summary>'
                            '<div class="urls">%s</div></details></td></tr>' % "".join(detail))
        retro_note = ""
        if t["retro"]:
            retro_note = (" Before Serper started, the alerts had already found %d pages; Serper's first search returned "
                          "%d of them." % (t["retro"], t["retro_hit"]))
        body = (
            '<section class="portal"><div class="portal-head"><div>'
            '<div class="eyebrow">Since Serper started &middot; %s</div><h2>Per alert</h2>'
            '<p class="note">Alerts are checked every 20 minutes and Serper every %d, so "earlier" is only that precise. '
            "Serper searches the past %s for each query%s; its first search is a baseline and isn't counted. "
            "Listing and archive pages (/news, /page/3, /tag/...) are left out on both sides.%s "
            "Serper has run %d times and used %d credits%s.</p>"
            "</div></div>"
            '<div class="table-wrap"><table class="cmp"><thead><tr><th class="c-comp">Competitor</th><th class="c-q">Query</th>'
            '<th class="n">Alerts</th><th class="n">Serper</th><th class="n">Both</th><th class="n">Only Alerts</th>'
            '<th class="n">Only Serper</th><th class="n" title="Pages the alert found before Serper started that were in Serper\'s first search">Before</th>'
            "</tr></thead><tbody>%s</tbody></table></div></section>"
        ) % (esc(fmt_when(result["t0"])), (config.get("serper") or {}).get("every_minutes", 60),
             "day" if (config.get("serper") or {}).get("tbs") == "qdr:d" else "week",
             esc(" (past day for %s)" % ", ".join(sorted(f["competitor"] for f in config["feeds"].values() if f.get("serper_tbs") == "qdr:d")))
             if any(f.get("serper_tbs") == "qdr:d" for f in config["feeds"].values()) else "",
             esc(retro_note),
             meta.get("runs", 0), meta.get("credits_used", 0),
             (". Last error: " + esc(meta["last_error"])) if meta.get("last_error") else "", "".join(rows))

    page = (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="robots" content="noindex, nofollow">\n'
        "<title>Alerts vs Serper</title>\n<style>%s%s</style>\n</head>\n<body>\n"
        '<header class="top"><div class="container">'
        '<div class="eyebrow"><a href="./">Alert feeds</a> &middot; Comparison</div>'
        "<h1>Google Alerts vs Serper</h1>"
        '<p class="lede">The same site: queries, two ways: as Google Alerts, and as Serper searches checked for new URLs. '
        "Pages are matched by URL.</p>%s"
        "</div></header>\n"
        '<main class="container">%s</main>\n'
        '<footer class="container">Built by <a href="https://github.com/JonahLopin/alert-feeds">github.com/JonahLopin/alert-feeds</a>.</footer>\n'
        "</body>\n</html>\n"
    ) % (base_style, COMPARE_STYLE, stats, body)
    with open(os.path.join(root, "docs", "compare.html"), "w") as fh:
        fh.write(page)
