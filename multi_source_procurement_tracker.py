"""
Global Procurement Tracker — Multi-Source Streamlit App

Sources:
  - World Bank (IBRD + IDA)  → JSON API, no key
  - TED Europa (EU)          → REST API, no key
  - SAM.gov (US Federal)     → JSON API, free key required

Setup:
    python3 -m venv venv
    source venv/bin/activate
    pip install streamlit requests
    streamlit run procurement_tracker.py

SAM.gov API key (free):
    https://sam.gov → Sign In → Account Details → Generate Key
"""

import requests
import streamlit as st
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed



# ══════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════

RESULTS_LIMIT = 10

# ══════════════════════════════════════════════════════════════
#  PAGE CONFIG
# ══════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Global Procurement Tracker",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ══════════════════════════════════════════════════════════════
#  CSS
# ══════════════════════════════════════════════════════════════

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600&display=swap');

html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }

.app-header {
    background: linear-gradient(135deg, #002244 0%, #003a70 60%, #005BAA 100%);
    border-radius: 16px;
    padding: 2rem 2.5rem;
    margin-bottom: 1.5rem;
    color: white;
}
.app-header h1 {
    font-family: 'DM Serif Display', serif;
    font-size: 2.2rem;
    margin: 0 0 0.3rem 0;
    letter-spacing: -0.5px;
}
.app-header p { opacity: 0.75; font-size: 0.9rem; margin: 0; }

.notice-card {
    background: white;
    border: 1px solid #e8ecf0;
    border-left: 4px solid #005BAA;
    border-radius: 10px;
    padding: 1.2rem 1.5rem;
    margin-bottom: 0.8rem;
}
.notice-card:hover { box-shadow: 0 4px 20px rgba(0,91,170,0.08); }
.notice-title {
    font-family: 'DM Serif Display', serif;
    font-size: 1rem;
    color: #002244;
    margin: 0 0 0.5rem 0;
    line-height: 1.4;
}

/* Source colour strips */
.src-wb  { border-left-color: #005BAA; }
.src-ted { border-left-color: #003399; }
.src-adb { border-left-color: #c00000; }
.src-sam { border-left-color: #002868; }

.badge {
    display: inline-block;
    padding: 2px 9px;
    border-radius: 20px;
    font-size: 0.73rem;
    font-weight: 500;
    margin-right: 4px;
}
.badge-source  { background: #e8f0fa; color: #003a70; }
.badge-type    { background: #f0f7ee; color: #2d6a4f; }
.badge-country { background: #fff8e1; color: #795500; }
.badge-deadline-ok  { background: #e8f5e9; color: #1b5e20; }
.badge-deadline-warn { background: #fff3e0; color: #b45309; }
.badge-deadline-urgent { background: #fee2e2; color: #991b1b; }

section[data-testid="stSidebar"] { background: #f0f4fa; }
section[data-testid="stSidebar"] input,
section[data-testid="stSidebar"] div[data-baseweb="select"] > div { background: #e4ecf7 !important; }
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] div { color: #0a1628 !important; }
section[data-testid="stSidebar"] input { color: #0a1628 !important; }
section[data-testid="stSidebar"] input::placeholder { color: #5a7a9a !important; }
section[data-testid="stSidebar"] .stButton button {
    background: #e4ecf7 !important;
    border: 1px solid #c8d8ed !important;
    color: #002244 !important;
    border-radius: 6px !important;
}
section[data-testid="stSidebar"] .stButton button:hover { background: #d0dff5 !important; }

</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════

def days_until(date_str: str):
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d %b %Y", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return (datetime.strptime(date_str[:10], fmt[:10]) - datetime.today()).days
        except ValueError:
            continue
    return None

def deadline_badge(deadline_str: str) -> str:
    if not deadline_str:
        return ""
    days = days_until(deadline_str)
    dl   = deadline_str[:10]
    if days is None:
        return f'<span class="badge badge-deadline-ok">📅 {dl}</span>'
    if days < 0:
        return f'<span class="badge badge-deadline-urgent">⚠️ Expired</span>'
    if days <= 7:
        return f'<span class="badge badge-deadline-urgent">🔴 {dl} ({days}d)</span>'
    if days <= 14:
        return f'<span class="badge badge-deadline-warn">🟡 {dl} ({days}d)</span>'
    return f'<span class="badge badge-deadline-ok">🟢 {dl} ({days}d)</span>'

def render_card(notice: dict):
    src         = notice.get("source", "")
    title       = notice.get("title", "Untitled")
    ntype       = notice.get("type", "")
    country     = notice.get("country", "")
    agency      = notice.get("agency", "")
    amount      = notice.get("amount", "")
    link        = notice.get("link", "")
    dl          = notice.get("deadline", "")

    src_labels = {
        "World Bank": ("🌍 World Bank", "src-wb"),
        "TED Europa": ("🇪🇺 TED Europa", "src-ted"),
        "ADB":        ("🏦 ADB",         "src-adb"),
    }
    src_label, src_class = src_labels.get(src, (src, ""))

    src_badge     = f'<span class="badge badge-source">{src_label}</span>'
    type_badge    = f'<span class="badge badge-type">{ntype}</span>' if ntype else ""
    country_badge = f'<span class="badge badge-country">🌍 {country}</span>' if country else ""
    dl_badge      = deadline_badge(dl)
    agency_html   = f'<div style="font-size:0.8rem;color:#666;margin:4px 0;">🏛 {agency}</div>' if agency else ""
    amount_html   = f'<div style="font-size:0.82rem;font-weight:600;color:#002244;margin:4px 0;">💰 {amount}</div>' if amount else ""
    link_html     = f'<a href="{link}" target="_blank" style="font-size:0.82rem;color:#005BAA;">🔗 View notice →</a>' if link else ""

    html = (
        f'<div class="notice-card {src_class}">'
        f'<div class="notice-title">{title}</div>'
        f'<div style="margin-bottom:6px;">{src_badge}{type_badge}{country_badge}{dl_badge}</div>'
        f'{agency_html}{amount_html}{link_html}'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  SOURCE 1 — WORLD BANK
# ══════════════════════════════════════════════════════════════

def fetch_worldbank(keyword: str, rows: int) -> list:
    params = {
        "format": "json", "apilang": "en", "srce": "both",
        "rows": rows, "os": 0,
        "srt": "submission_deadline_date", "order": "desc",
        "fl": "id,notice_type,project_name,project_ctry_name,submission_deadline_date,contact_agency,url",
    }
    if keyword.strip():
        params["qterm"] = keyword.strip()

    try:
        r = requests.get("https://search.worldbank.org/api/v2/procnotices", params=params, timeout=15)
        r.raise_for_status()
        data = r.json()

        raw = data.get("notices", {})
        notices = list(raw.values()) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
        if not notices:
            for v in data.values():
                c = list(v.values()) if isinstance(v, dict) else (v if isinstance(v, list) else [])
                if c and isinstance(c[0], dict) and "project_name" in c[0]:
                    notices = c
                    break

        results = []
        for n in notices:
            nid  = n.get("id", "")
            link = n.get("url") or (f"http://projects.worldbank.org/en/projects-operations/procurement-detail/{nid}" if nid else "")
            results.append({
                "source":   "World Bank",
                "title":    n.get("project_name") or "Untitled",
                "type":     n.get("notice_type", ""),
                "country":  n.get("project_ctry_name", ""),
                "agency":   n.get("contact_agency", ""),
                "deadline": (n.get("submission_deadline_date") or "")[:10],
                "amount":   "",
                "link":     link,
            })
        return results
    except Exception as e:
        return [{"source": "World Bank", "title": f"⚠️ Error: {e}", "type": "", "country": "", "agency": "", "deadline": "", "amount": "", "link": ""}]


# ══════════════════════════════════════════════════════════════
#  SOURCE 2 — TED EUROPA
# ══════════════════════════════════════════════════════════════

# TED public RSS feeds — no API, no key, always works
# TED supports keyword search via the `q` URL param in RSS mode

def fetch_ted_rss(keyword: str, rows: int) -> list:
    """TED Europa fallback via requests XML parsing — no feedparser needed."""
    import xml.etree.ElementTree as ET
    kw = keyword.strip().lower()

    feed_url = "https://ted.europa.eu/en/simap/rss-feed/-/rss/search/comp"

    results = []
    try:
        r = requests.get(feed_url, timeout=15,
                         headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        root = ET.fromstring(r.content)
        ns = {"dc": "http://purl.org/dc/elements/1.1/"}
        items = root.findall(".//item")

        for item in items:
            title   = (item.findtext("title") or "Untitled").strip()
            link    = (item.findtext("link") or "").strip()
            desc    = (item.findtext("description") or "").strip()
            pubdate = (item.findtext("pubDate") or "")[:10]

            if kw and kw not in title.lower() and kw not in desc.lower():
                continue

            # Parse: "12345-2026: Romania – Construction work – Project name"
            parts = title.split("–")
            country = ""
            notice_type = "Contract Notice"
            if len(parts) >= 2:
                country     = parts[0].split(":")[-1].strip() if ":" in parts[0] else parts[0].strip()
                notice_type = parts[1].strip()

            results.append({
                "source":   "TED Europa",
                "title":    parts[-1].strip() if len(parts) >= 3 else title,
                "type":     notice_type,
                "country":  country,
                "agency":   "",
                "deadline": pubdate,
                "amount":   "",
                "link":     link,
            })
            if len(results) >= rows:
                break

    except Exception as e:
        return [{"source": "TED Europa", "title": f"⚠️ TED unavailable: {e}", "type": "", "country": "", "agency": "", "deadline": "", "amount": "", "link": "https://ted.europa.eu"}]

    if not results:
        return [{"source": "TED Europa", "title": "No TED results — try a broader keyword", "type": "", "country": "", "agency": "", "deadline": "", "amount": "", "link": "https://ted.europa.eu"}]

    return results[:rows]


def fetch_ted(keyword: str, rows: int) -> list:
    """
    TED Europa Search API v3 — anonymous, no key required.
    Exact schema from official TED workshop docs:
      - query: expert search language (field=value, IN, AND, OR)
      - fields: hyphenated field names from NoticeResponse schema
      - limit: int (not string)
      - scope: "ACTIVE" | "LATEST" | "ALL"
      - checkQuerySyntax: false (skip strict validation)
      - paginationMode: "PAGE_NUMBER" | "ITERATION"
    """
    if keyword.strip():
        # FT = full-text field, multilingual, stemmed — same as website quick search
        # Single word: FT~water  |  Phrase: FT~"climate change"
        kw = keyword.strip()
        if " " in kw:
            query = f'FT~"{kw}"'
        else:
            query = f"FT~{kw}"
    else:
        # Browse active contract notices
        query = "notice-type IN (cn-standard, cn-social)"

    payload = {
        "query":            query,
        "fields":           [
            "publication-number",
            "notice-title",
            "buyer-country",
            "buyer-name",
            "deadline-receipt-request",
            "notice-type",
            "contract-nature",
        ],
        "page":             1,
        "limit":            rows,
        "scope":            "ACTIVE",
        "checkQuerySyntax": False,
        "paginationMode":   "PAGE_NUMBER",
    }

    try:
        r = requests.post(
            "https://api.ted.europa.eu/v3/notices/search",
            json=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=15
        )

        if r.status_code == 400:
            print(f"TED 400 body: {r.text[:500]}")
            return fetch_ted_rss(keyword, rows)

        r.raise_for_status()
        data = r.json()
        notices = data.get("notices", [])

        def fv(n, k):
            v = n.get(k, "")
            if isinstance(v, list):
                return v[0] if v else ""
            if isinstance(v, dict):
                return v.get("ENG") or v.get("FRA") or next(iter(v.values()), "") if v else ""
            return str(v) if v else ""

        results = []
        for n in notices:
            pub = fv(n, "publication-number")
            results.append({
                "source":   "TED Europa",
                "title":    fv(n, "notice-title") or "Untitled",
                "type":     fv(n, "notice-type"),
                "country":  fv(n, "buyer-country"),
                "agency":   fv(n, "buyer-name"),
                "deadline": str(fv(n, "deadline-receipt-request"))[:10],
                "amount":   "",
                "link":     f"https://ted.europa.eu/en/notice/-/detail/{pub}" if pub else "",
            })
        return results if results else fetch_ted_rss(keyword, rows)

    except Exception as e:
        print(f"TED API error: {e}")
        return fetch_ted_rss(keyword, rows)



    """
    TED Europa Search API v3 — anonymous, no key required.
    Exact schema from official TED workshop docs:
      - query: expert search language (field=value, IN, AND, OR)
      - fields: hyphenated field names from NoticeResponse schema
      - limit: int (not string)
      - scope: "ACTIVE" | "LATEST" | "ALL"
      - checkQuerySyntax: false (skip strict validation)
      - paginationMode: "PAGE_NUMBER" | "ITERATION"
    """
    if keyword.strip():
        # FT = full-text field, multilingual, stemmed — same as website quick search
        # Single word: FT~water  |  Phrase: FT~"climate change"
        kw = keyword.strip()
        if " " in kw:
            query = f'FT~"{kw}"'
        else:
            query = f"FT~{kw}"
    else:
        # Browse active contract notices
        query = "notice-type IN (cn-standard, cn-social)"

    payload = {
        "query":            query,
        "fields":           [
            "publication-number",
            "notice-title",
            "buyer-country",
            "buyer-name",
            "deadline-receipt-request",
            "notice-type",
            "contract-nature",
        ],
        "page":             1,
        "limit":            rows,
        "scope":            "ACTIVE",
        "checkQuerySyntax": False,
        "paginationMode":   "PAGE_NUMBER",
    }

    try:
        r = requests.post(
            "https://api.ted.europa.eu/v3/notices/search",
            json=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=15
        )

        if r.status_code == 400:
            # Log exact error for debugging then fall back to RSS
            print(f"TED 400 body: {r.text[:500]}")
            return fetch_ted_rss(keyword, rows)

        r.raise_for_status()
        data = r.json()
        notices = data.get("notices", [])

        def fv(n, k):
            v = n.get(k, "")
            if isinstance(v, list):
                return v[0] if v else ""
            if isinstance(v, dict):
                # multilingual field — try English first
                return v.get("ENG") or v.get("FRA") or next(iter(v.values()), "") if v else ""
            return str(v) if v else ""

        results = []
        for n in notices:
            pub = fv(n, "publication-number")
            results.append({
                "source":   "TED Europa",
                "title":    fv(n, "notice-title") or "Untitled",
                "type":     fv(n, "notice-type"),
                "country":  fv(n, "buyer-country"),
                "agency":   fv(n, "buyer-name"),
                "deadline": str(fv(n, "deadline-receipt-request"))[:10],
                "amount":   "",
                "link":     f"https://ted.europa.eu/en/notice/-/detail/{pub}" if pub else "",
            })
        return results if results else fetch_ted_rss(keyword, rows)

    except Exception as e:
        print(f"TED API error: {e}")
        return fetch_ted_rss(keyword, rows)


# ══════════════════════════════════════════════════════════════
#  SOURCE 3 — ADB (RSS)
# ══════════════════════════════════════════════════════════════



# ══════════════════════════════════════════════════════════════
#  SOURCE 4 — SAM.GOV
# ══════════════════════════════════════════════════════════════

def fetch_samgov(keyword: str, rows: int) -> list:
    today     = datetime.today()
    from_date = (today - timedelta(days=60)).strftime("%m/%d/%Y")
    to_date   = today.strftime("%m/%d/%Y")

    params = {
        "api_key":    SAM_API_KEY,
        "postedFrom": from_date,
        "postedTo":   to_date,
        "limit":      rows,
        "offset":     0,
        # SAM.gov DEMO_KEY requires a keyword — default to broad term if none given
        "keyword":    keyword.strip() if keyword.strip() else "consulting",
    }

    try:
        r = requests.get("https://api.sam.gov/opportunities/v2/search", params=params, timeout=15)
        if r.status_code == 404:
            return [{"source": "SAM.gov", "title": "ℹ️ No results — try a specific keyword or add a real SAM.gov API key", "type": "", "country": "United States", "agency": "", "deadline": "", "amount": "", "link": "https://sam.gov"}]
        r.raise_for_status()
        data = r.json()
        opps = data.get("opportunitiesData", [])

        results = []
        for opp in opps:
            nid  = opp.get("noticeId", "")
            link = opp.get("uiLink") or (f"https://sam.gov/opp/{nid}/view" if nid else "")
            pop  = opp.get("placeOfPerformance", {})
            country = pop.get("country", {}).get("name", "") if pop else ""
            results.append({
                "source":   "SAM.gov",
                "title":    opp.get("title", "Untitled"),
                "type":     opp.get("type", ""),
                "country":  country or "United States",
                "agency":   opp.get("fullParentPathName", ""),
                "deadline": (opp.get("reponseDeadLine") or "")[:10],
                "amount":   "",
                "link":     link,
            })
        return results
    except Exception as e:
        return [{"source": "SAM.gov", "title": f"⚠️ Error: {e}", "type": "", "country": "", "agency": "", "deadline": "", "amount": "", "link": ""}]


# ══════════════════════════════════════════════════════════════
#  SIDEBAR
# ══════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("---")
    st.markdown("### 🔍 Search")

    keyword = st.text_input(
        "Keyword",
        value="",
        placeholder="climate, governance, health...",
        help="Leave blank to browse latest notices"
    )

    st.markdown("**Sources**")
    src_wb  = st.checkbox("🌍 World Bank",  value=True)
    src_ted = st.checkbox("🇪🇺 TED Europa", value=True)


    results_limit = st.slider("Results per source", 3, 20, 5, step=1)

    search_btn = st.button("🔎 Search", use_container_width=True, type="primary")

    st.markdown("---")
    st.markdown("**Quick keywords**")
    for qk in ["climate", "governance", "capacity building", "health",
                "public financial management", "infrastructure", "education", "digital"]:
        if st.button(qk, use_container_width=True, key=f"qk_{qk}"):
            keyword    = qk
            search_btn = True

    st.markdown("---")
    st.caption("Live data · No API key required for most sources")
    st.markdown("""
<div style="padding-top:0.5rem;">
<p style="font-size:0.72rem;color:#5a7a9a;line-height:1.6;margin:0;">
    Built by <strong style="color:#003a70;">Aqib Ahmed</strong>, KPMG G&amp;PS<br>
    <em>Personal initiative, not an official KPMG tool</em>
</p>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  MAIN CONTENT
# ══════════════════════════════════════════════════════════════

st.markdown("""
<div class="app-header">
    <div style="display:flex;justify-content:space-between;align-items:flex-end;">
        <div>
            <h1>🌐 Global Procurement Tracker</h1>
            <p>World Bank · TED Europa — all in one place · Live data</p>
        </div>
        <div style="text-align:right;flex-shrink:0;margin-left:2rem;">
            <p style="margin:0;font-size:0.72rem;opacity:0.6;line-height:1.7;">
                Developed by<br>
                <strong style="opacity:0.9;">Aqib Ahmed</strong><br>
                Associate Consultant · KPMG G&amp;PS<br>
                <em style="opacity:0.8;">Personal initiative, not an official KPMG tool</em>
            </p>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# Fetch on load or search
if "all_notices" not in st.session_state or search_btn:
    selected_sources = []
    if src_wb:  selected_sources.append(("World Bank", fetch_worldbank))
    if src_ted: selected_sources.append(("TED Europa", fetch_ted))

    all_notices = []

    with st.spinner("Fetching from all sources in parallel..."):
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(fn, keyword, results_limit): name
                for name, fn in selected_sources
            }
            for future in as_completed(futures):
                try:
                    all_notices.extend(future.result())
                except Exception as e:
                    st.warning(f"Error from {futures[future]}: {e}")

    # Sort all results by deadline
    def sort_key(n):
        dl = n.get("deadline", "")
        return dl if dl else "9999-99-99"

    all_notices.sort(key=sort_key)
    st.session_state["all_notices"] = all_notices
    st.session_state["kw"]          = keyword

all_notices = st.session_state.get("all_notices", [])
kw          = st.session_state.get("kw", "")

# ── Stats ────────────────────────────────────────────────────

if all_notices:
    source_counts = {}
    for n in all_notices:
        s = n.get("source", "Unknown")
        source_counts[s] = source_counts.get(s, 0) + 1

    urgent = sum(1 for n in all_notices if (days_until(n.get("deadline") or "") or 999) <= 14)

    cols = st.columns(len(source_counts) + 2)
    cols[0].metric("Total Notices", len(all_notices))
    cols[1].metric("Closing ≤14d", urgent)
    for i, (src, count) in enumerate(source_counts.items(), 2):
        cols[i].metric(src, count)

    st.markdown("---")

# ── Filters ──────────────────────────────────────────────────

if all_notices:
    col1, col2 = st.columns([2, 1])

    with col1:
        all_countries = sorted(set(n.get("country", "") for n in all_notices if n.get("country")))
        country_filter = st.multiselect("Filter by country", all_countries, placeholder="All countries")

    with col2:
        source_filter = st.multiselect(
            "Filter by source",
            ["World Bank", "TED Europa"],
            placeholder="All sources"
        )

    filtered = [
        n for n in all_notices
        if (not country_filter or n.get("country") in country_filter)
        and (not source_filter or n.get("source") in source_filter)
    ]

    label = f"**{len(filtered)} notices** " + (f'matching *"{kw}"*' if kw else "(latest)")
    st.caption(label)

    for notice in filtered:
        render_card(notice)

else:
    st.info("Use the sidebar to search or click Search to load the latest notices.")