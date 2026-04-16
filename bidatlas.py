"""
Global Procurement Tracker — Multi-Source Streamlit App

Sources:
  - World Bank (IBRD + IDA)  → JSON API, no key
  - TED Europa (EU)          → REST API v3, no key (RSS fallback)
  - CPPP India               → HTML scrape via curl + BeautifulSoup

Setup:
    python3 -m venv venv
    source venv/bin/activate
    pip install streamlit requests beautifulsoup4 deep-translator
    streamlit run procurement_tracker.py
"""

import json
import subprocess
import time
import requests
import streamlit as st
from bs4 import BeautifulSoup
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from deep_translator import GoogleTranslator
    _TRANSLATOR_AVAILABLE = True
except ImportError:
    _TRANSLATOR_AVAILABLE = False

RESULTS_LIMIT = 10

# ══════════════════════════════════════════════════════════════
#  PAGE CONFIG
# ══════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="BidAtlas — Global Procurement Tracker",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ══════════════════════════════════════════════════════════════
#  CSS
# ══════════════════════════════════════════════════════════════

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;1,9..40,300&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
    color: #0a1628;
}

.app-header {
    background: linear-gradient(135deg, #002244 0%, #003a70 60%, #005BAA 100%);
    border-radius: 16px;
    padding: 2rem 2.5rem;
    margin-bottom: 1.5rem;
    color: white;
}
.app-header h1 {
    font-family: 'DM Serif Display', serif;
    font-size: clamp(1.2rem, 4vw, 2.2rem);
    margin: 0 0 0.3rem 0;
    letter-spacing: -0.5px;
}
.app-header p { opacity: 0.75; font-size: 0.9rem; margin: 0; }

.notice-card {
    background: white;
    border: 1px solid #e8ecf0;
    border-left: 4px solid #005BAA;
    border-radius: 10px;
    padding: 1.2rem 1.5rem 1rem 1.5rem;
    margin-bottom: 0.4rem;
    transition: box-shadow 0.15s ease;
}
.notice-card:hover { box-shadow: 0 4px 24px rgba(0,91,170,0.10); }
.notice-title {
    font-family: 'DM Serif Display', serif;
    font-size: 1rem;
    color: #002244;
    margin: 0 0 0.5rem 0;
    line-height: 1.4;
}
.src-wb   { border-left-color: #005BAA; }
.src-ted  { border-left-color: #003399; }
.src-cppp { border-left-color: #FF6B00; }
.src-adb { border-left-color: #008080; }
.badge-source-adb { background: #e6fffb; color: #006666; }

.badge {
    display: inline-block;
    padding: 2px 9px;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 500;
    margin-right: 4px;
    margin-bottom: 3px;
}
.badge-source    { background: #e8f0fa; color: #003a70; }
.badge-source-cppp { background: #fff0e6; color: #b34500; }
.badge-type      { background: #f0f7ee; color: #2d6a4f; }
.badge-country   { background: #fff8e1; color: #795500; }
.badge-nature    { background: #fce8ff; color: #6b21a8; }
.badge-sector    { background: #e0f2fe; color: #075985; }
.badge-procedure { background: #fdf2f8; color: #9d174d; }
.badge-deadline-ok     { background: #e8f5e9; color: #1b5e20; }
.badge-deadline-warn   { background: #fff3e0; color: #b45309; }
.badge-deadline-urgent { background: #fee2e2; color: #991b1b; }
.badge-expired         { background: #f3f4f6; color: #6b7280; }

.detail-panel {
    background: #f6f9ff;
    border: 1px solid #dce7f5;
    border-radius: 10px;
    padding: 1.2rem 1.5rem;
    margin-bottom: 0.8rem;
    font-size: 0.86rem;
    color: #1a2a40;
    line-height: 1.7;
}
.detail-panel h4 {
    font-family: 'DM Serif Display', serif;
    font-size: 0.92rem;
    color: #002244;
    margin: 0.9rem 0 0.4rem 0;
    border-bottom: 1px solid #dce7f5;
    padding-bottom: 0.2rem;
}
.detail-panel h4:first-child { margin-top: 0; }
.detail-row { display: flex; gap: 0.5rem; margin-bottom: 0.2rem; }
.detail-label { color: #5a7a9a; min-width: 155px; font-weight: 500; flex-shrink: 0; }
.detail-value { color: #0a1628; flex: 1; word-break: break-word; }

section[data-testid="stSidebar"] { background: #f0f4fa; }
section[data-testid="stSidebar"] input,
section[data-testid="stSidebar"] div[data-baseweb="select"] > div {
    background: #e4ecf7 !important;
}
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span { color: #0a1628 !important; }
section[data-testid="stSidebar"] input { color: #0a1628 !important; }
section[data-testid="stSidebar"] input::placeholder { color: #5a7a9a !important; }
section[data-testid="stSidebar"] .stButton button {
    background: #e4ecf7 !important;
    border: 1px solid #c8d8ed !important;
    color: #002244 !important;
    border-radius: 6px !important;
    font-size: 0.82rem !important;
}
section[data-testid="stSidebar"] .stButton button:hover {
    background: #d0dff5 !important;
}
[data-testid="stToolbarActions"] { display: none !important; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════

def days_until(date_str: str):
    if not date_str or date_str.strip() in ("", "N"):
        return None
    s = date_str.strip()
    for fmt in ("%Y-%m-%d", "%d-%b-%Y %I:%M %p", "%d-%b-%Y %I:%M%p", "%d-%b-%Y"):
        try:
            return (datetime.strptime(s, fmt) - datetime.today()).days
        except Exception:
            pass
    return None

def fmt_date(date_str: str) -> str:
    if not date_str or date_str.strip() in ("", "N"):
        return ""
    for fmt, out in [
        ("%Y-%m-%d",          "%d-%m-%Y"),
        ("%d-%b-%Y %I:%M %p", "%d-%b-%Y %I:%M %p"),
        ("%d-%b-%Y",          "%d-%b-%Y"),
    ]:
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime(out)
        except Exception:
            pass
    return date_str.strip()

def _translate(text: str) -> str:
    if not _TRANSLATOR_AVAILABLE or not text or not text.strip():
        return text
    try:
        translated = GoogleTranslator(source="auto", target="en").translate(text)
        return translated if translated else text
    except Exception:
        return text

def _translate_notice(notice: dict) -> dict:
    if notice.get("source") != "TED Europa":
        return notice
    return {**notice, "title": _translate(notice.get("title", "")), "type": _translate(notice.get("type", ""))}

def deadline_badge(dl: str) -> str:
    if not dl or dl.strip() in ("", "N"):
        return ""
    days = days_until(dl)
    label = fmt_date(dl) or dl.strip()
    if days is None:
        return f'<span class="badge badge-deadline-ok">📅 {label}</span>'
    if days < 0:
        return f'<span class="badge badge-expired">⏳ Expired {label}</span>'
    if days <= 7:
        return f'<span class="badge badge-deadline-urgent">🔴 {label} ({days}d left)</span>'
    if days <= 14:
        return f'<span class="badge badge-deadline-warn">🟡 {label} ({days}d left)</span>'
    return f'<span class="badge badge-deadline-ok">🟢 {label} ({days}d left)</span>'

def _dr(label: str, value) -> str:
    v = str(value).strip() if value else ""
    if not v or v in ("None", "N/A", "0"):
        return ""
    return (
        f'<div class="detail-row">'
        f'<span class="detail-label">{label}</span>'
        f'<span class="detail-value">{v}</span>'
        f'</div>'
    )

def render_notice(notice: dict, idx: int):
    src     = notice.get("source", "")
    title   = notice.get("title", "Untitled")
    ntype   = notice.get("type", "")
    country = notice.get("country", "")
    agency  = notice.get("agency", "")
    amount  = notice.get("amount", "")
    link    = notice.get("link", "")
    dl      = notice.get("deadline", "")
    nature    = notice.get("nature", "")
    cpv       = notice.get("cpv_codes", "")
    procedure = notice.get("procedure", "")
    pub_num   = notice.get("publication_number", "")
    award_val = notice.get("award_value", "")
    lot_count = notice.get("lot_count", "")

    src_labels = {
        "World Bank": ("🌍 World Bank",  "src-wb",   "badge-source"),
        "TED Europa": ("🇪🇺 TED Europa", "src-ted",  "badge-source"),
        "CPPP India": ("🇮🇳 CPPP India", "src-cppp", "badge-source-cppp"),
    }
    src_label, src_class, src_badge_class = src_labels.get(src, (src, "", "badge-source"))

    badges = [
        f'<span class="badge {src_badge_class}">{src_label}</span>',
        f'<span class="badge badge-type">{ntype}</span>'          if ntype    else "",
        f'<span class="badge badge-country">🌍 {country}</span>' if country  else "",
        f'<span class="badge badge-nature">{nature}</span>'       if nature   else "",
        f'<span class="badge badge-procedure">{procedure}</span>' if procedure else "",
        deadline_badge(dl),
    ]

    agency_line = f'<div style="font-size:0.8rem;color:#4a6a8a;margin:5px 0 2px 0;">🏛 {agency}</div>' if agency else ""
    amount_line = f'<div style="font-size:0.82rem;font-weight:600;color:#002244;margin:2px 0;">💰 {amount}</div>' if amount else ""
    award_line  = f'<div style="font-size:0.82rem;font-weight:600;color:#1b5e20;margin:2px 0;">🏆 Award: {award_val}</div>' if award_val else ""
    lots_line   = f'<div style="font-size:0.78rem;color:#6a7a8a;margin:2px 0;">Lots: {lot_count}</div>' if lot_count and lot_count not in ("", "0") else ""
    cpv_line    = f'<div style="font-size:0.75rem;color:#6a7a8a;margin:2px 0;font-family:monospace;">CPV: {cpv[:120]}</div>' if cpv else ""
    pubnum_line = f'<div style="font-size:0.75rem;color:#9aaabb;margin:2px 0;font-family:monospace;">{pub_num}</div>' if pub_num else ""
    link_line   = f'<a href="{link}" target="_blank" style="font-size:0.82rem;color:#005BAA;text-decoration:none;">🔗 View notice →</a>' if link and src != "CPPP India" else ""

    card_html = (
        f'<div class="notice-card {src_class}">'
        f'<div class="notice-title">{title}</div>'
        f'<div style="margin-bottom:5px;">{"".join(badges)}</div>'
        f'{agency_line}{amount_line}{award_line}{lots_line}{cpv_line}{pubnum_line}'
        f'<div style="margin-top:6px;">{link_line}</div>'
        f'</div>'
    )
    st.markdown(card_html, unsafe_allow_html=True)

    with st.expander("📋 Full details", expanded=False):
        pub_date    = notice.get("publication_date", "")
        project_id  = notice.get("project_id", "")
        borrower    = notice.get("borrower", "")
        contact     = notice.get("contact", "")
        description = notice.get("description", "")
        notice_id   = notice.get("notice_id", "")
        lang        = notice.get("language", "")
        nuts        = notice.get("nuts_code", "")
        buyer_id    = notice.get("buyer_id", "")
        sector      = notice.get("sector", "")
        corrigendum = notice.get("corrigendum", "")

        sections = []
        id_rows = "".join(filter(None, [
            _dr("Notice Ref / ID",       notice_id or pub_num or project_id),
            _dr("Publication Date",      fmt_date(pub_date) or pub_date),
            _dr("Bid Closing Date",      dl),
            _dr("Source",                src_label),
            _dr("Language",              lang),
            _dr("Corrigendum",           corrigendum if corrigendum and corrigendum != "--" else ""),
        ]))
        if id_rows:
            sections.append(f'<h4>📌 Identification</h4>{id_rows}')

        proc_rows = "".join(filter(None, [
            _dr("Notice Type",           ntype),
            _dr("Contract Nature",       nature),
            _dr("Procedure Type",        procedure),
            _dr("CPV Codes",             cpv),
            _dr("NUTS / Region",         nuts),
            _dr("Sector / Activity",     sector),
            _dr("Number of Lots",        lot_count),
        ]))
        if proc_rows:
            sections.append(f'<h4>📄 Procurement Details</h4>{proc_rows}')

        buyer_rows = "".join(filter(None, [
            _dr("Contracting Authority", agency),
            _dr("Buyer ID / Ref",        buyer_id),
            _dr("Country",               country),
            _dr("Borrower / Client",     borrower),
            _dr("Contact",               contact),
        ]))
        if buyer_rows:
            sections.append(f'<h4>🏛 Buyer / Authority</h4>{buyer_rows}')

        fin_rows = "".join(filter(None, [
            _dr("Estimated Value",       amount),
            _dr("Award Value",           award_val),
            _dr("Project ID",            project_id),
        ]))
        if fin_rows:
            sections.append(f'<h4>💰 Financials</h4>{fin_rows}')

        if description and len(str(description).strip()) > 5:
            desc_text = str(description)[:900] + ("…" if len(str(description)) > 900 else "")
            sections.append(f'<h4>📝 Description</h4><div style="color:#1a2a40;line-height:1.7;">{desc_text}</div>')

        if link and src != "CPPP India":
            sections.append(f'<h4>🔗 Source Link</h4><a href="{link}" target="_blank" style="color:#005BAA;">{link}</a>')

        if sections:
            st.markdown(f'<div class="detail-panel">{"".join(sections)}</div>', unsafe_allow_html=True)
        else:
            st.caption("No additional detail available for this notice.")


# ══════════════════════════════════════════════════════════════
#  SEARCH HELPERS — keyword preprocessing
# ══════════════════════════════════════════════════════════════

# Common procurement synonyms — if the user types any of these,
# we also search for the alternatives to widen the net.
SYNONYM_MAP = {
    "it":           ["information technology", "software", "digital", "ICT"],
    "ict":          ["information technology", "software", "digital", "IT"],
    "roads":        ["highway", "infrastructure", "construction"],
    "health":       ["medical", "healthcare", "hospital", "medicines"],
    "education":    ["school", "training", "capacity building"],
    "water":        ["sanitation", "sewage", "drainage", "irrigation"],
    "power":        ["electricity", "energy", "solar", "renewable"],
    "construction": ["civil works", "building", "infrastructure"],
    "consulting":   ["consultancy", "advisory", "services"],
    "supply":       ["procurement", "purchase", "goods"],
}

def _expand_keywords(keyword: str) -> list[str]:
    """
    Return a list of search terms to try, ordered by specificity.
    - Multi-word phrase → try phrase first, then individual significant words
    - Single word → try word + any synonyms
    - Empty → return []
    """
    kw = keyword.strip().lower()
    if not kw:
        return []

    terms = [kw]  # always try the original first

    # Add synonyms for single-word queries
    if " " not in kw and kw in SYNONYM_MAP:
        terms.extend(SYNONYM_MAP[kw])

    # For multi-word phrases, also try each significant word individually
    if " " in kw:
        stop_words = {"and", "or", "the", "of", "for", "in", "to", "a", "an",
                      "with", "by", "at", "from", "on", "is", "are", "be"}
        words = [w for w in kw.split() if w not in stop_words and len(w) > 2]
        terms.extend(words)

    # Deduplicate preserving order
    seen, unique = set(), []
    for t in terms:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique


def _fuzzy_match(text: str, keywords: list[str]) -> bool:
    """
    Return True if any keyword matches the text.
    Handles partial matches and simple stemming (strips common suffixes).
    """
    text_lower = text.lower()
    for kw in keywords:
        kw = kw.lower()
        if kw in text_lower:
            return True
        # Simple stem: strip trailing s, ing, ed, tion, ment
        for suffix in ("tion", "ment", "ing", "ed", "s"):
            if kw.endswith(suffix):
                stem = kw[:-len(suffix)]
                if len(stem) >= 4 and stem in text_lower:
                    return True
    return False


# ══════════════════════════════════════════════════════════════
#  SOURCE 1 — WORLD BANK
# ══════════════════════════════════════════════════════════════

def fetch_worldbank(keyword: str, rows: int) -> list:
    # World Bank supports native search — fetch up to 50 server-side,
    # then return the top `rows` after local relevance re-check.
    fetch_limit = max(rows, 50)
    terms       = _expand_keywords(keyword)
    all_notices = []
    seen_ids    = set()

    def _fetch(qterm: str, limit: int) -> list:
        params = {
            "format": "json", "apilang": "en", "srce": "both",
            "rows": limit, "os": 0,
            "srt": "submission_deadline_date", "order": "desc",
        }
        if qterm:
            params["qterm"] = qterm
        r = requests.get("https://search.worldbank.org/api/v2/procnotices", params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        raw  = data.get("procnotices") or data.get("notices", {})
        notices = list(raw.values()) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
        if not notices:
            for v in data.values():
                c = list(v.values()) if isinstance(v, dict) else (v if isinstance(v, list) else [])
                if c and isinstance(c[0], dict) and "project_name" in c[0]:
                    return c
        return notices

    def _to_notice(n: dict) -> dict:
        nid  = n.get("id", "")
        link = n.get("url") or (f"https://projects.worldbank.org/en/projects-operations/procurement-detail/{nid}" if nid else "")
        amount_raw = n.get("contract_amount_usd") or n.get("totalcontract") or n.get("totalContract") or ""
        try:
            amount_str = f"USD {float(amount_raw):,.0f}" if amount_raw else ""
        except (ValueError, TypeError):
            amount_str = str(amount_raw) if amount_raw else ""
        contact_parts = list(filter(None, [n.get("contact_name", ""), n.get("contact_email", ""), n.get("contact_phone", "")]))
        return {
            "source": "World Bank", "title": n.get("project_name") or n.get("noticeTitle") or "Untitled",
            "type": n.get("notice_type") or n.get("noticeType", ""), "country": n.get("project_ctry_name") or n.get("countryname", ""),
            "agency": n.get("contact_agency") or n.get("borrower", ""),
            "deadline": (n.get("submission_deadline_date") or n.get("deadlineDate") or "")[:10],
            "amount": amount_str, "link": link, "notice_id": nid, "project_id": n.get("project_id", ""),
            "borrower": n.get("borrower", ""), "publication_date": (n.get("publish_date") or n.get("publishDate") or "")[:10],
            "sector": n.get("sector") or n.get("majorsector_exact", ""),
            "description": n.get("short_description") or n.get("noticeText", ""),
            "contact": " · ".join(contact_parts), "procedure": n.get("procurement_method") or n.get("procMethod", ""),
            "nature": n.get("procurement_group", ""), "language": n.get("lang", ""),
            "publication_number": nid, "buyer_id": n.get("contact_agency", ""),
            "cpv_codes": "", "nuts_code": "", "award_value": "", "lot_count": "", "corrigendum": "",
        }

    try:
        # Try each expanded term; collect unique results
        query_terms = terms if terms else [""]
        for term in query_terms:
            for raw in _fetch(term, fetch_limit):
                nid = raw.get("id", "")
                if nid and nid in seen_ids:
                    continue
                if nid:
                    seen_ids.add(nid)
                all_notices.append(_to_notice(raw))
            if len(all_notices) >= fetch_limit:
                break

        # If we searched with a keyword, keep only fuzzy-matched results
        if terms:
            all_notices = [n for n in all_notices
                           if _fuzzy_match(n["title"] + " " + n.get("description", "") + " " + n.get("sector", ""), terms)]

        return all_notices[:rows]

    except Exception as e:
        return [{"source": "World Bank", "title": f"⚠️ Error: {e}", "type": "", "country": "", "agency": "",
                 "deadline": "", "amount": "", "link": "", "corrigendum": ""}]


# ══════════════════════════════════════════════════════════════
#  SOURCE 2 — TED EUROPA
# ══════════════════════════════════════════════════════════════

TED_FIELDS_CORE = ["publication-number", "notice-title", "buyer-name", "notice-type", "buyer-country", "publication-date"]
TED_FIELDS_ENRICHED = TED_FIELDS_CORE + [
    "deadline-receipt-request", "contract-nature", "procedure-type", "estimated-value",
    "award-value", "currency", "cpv", "place-of-performance", "lot-count",
    "buyer-legal-type", "buyer-activity", "buyer-id", "language", "notice-links",
]

def _fv(n: dict, k: str) -> str:
    v = n.get(k, "")
    if not v:
        return ""
    if isinstance(v, list):
        parts = []
        for item in v:
            if isinstance(item, dict):
                parts.append(item.get("value") or item.get("ENG") or item.get("FRA") or next(iter(item.values()), ""))
            else:
                parts.append(str(item))
        return ", ".join(str(p) for p in parts if p)
    if isinstance(v, dict):
        return v.get("value") or v.get("ENG") or v.get("FRA") or next(iter(v.values()), "")
    return str(v)

def fetch_ted(keyword: str, rows: int) -> list:
    terms    = _expand_keywords(keyword)
    all_notices: list = []
    seen_pubs: set    = set()

    # TED API: fetch up to 10 per term across expanded terms,
    # paginate up to 3 pages per term to maximise coverage.
    PER_PAGE   = 10
    MAX_PAGES  = 3

    def _build_payload(query: str, fields: list, page: int) -> dict:
        return {"query": query, "fields": fields, "page": page, "limit": PER_PAGE,
                "scope": "ACTIVE", "checkQuerySyntax": False, "paginationMode": "PAGE_NUMBER"}

    def _post(payload: dict):
        return requests.post(
            "https://api.ted.europa.eu/v3/notices/search", json=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"}, timeout=15,
        )

    def _is_valid_notice(n: dict) -> bool:
        title = n.get("title", "")
        if not title or title == "Untitled":
            return False
        error_markers = ["Error 500", "Server Error", "That's an error", "Please try again", "502", "503", "504"]
        return not any(m.lower() in title.lower() for m in error_markers)

    def _parse_notices(notices: list, enriched: bool) -> list:
        results = []
        for n in notices:
            pub  = _fv(n, "publication-number")
            if pub in seen_pubs:
                continue
            if pub:
                seen_pubs.add(pub)
            link = f"https://ted.europa.eu/en/notice/-/detail/{pub}" if pub else ""
            curr = _fv(n, "currency") if enriched else ""
            def fmt_val(v):
                if not v or v in ("", "0"):
                    return ""
                try:
                    return f"{curr} {float(v):,.0f}".strip()
                except (ValueError, TypeError):
                    return str(v)
            cpv_str = ""
            if enriched:
                for c in (n.get("cpv", []) if isinstance(n.get("cpv"), list) else []):
                    if isinstance(c, dict):
                        code   = str(c.get("code", ""))
                        name_d = c.get("name", {})
                        name   = (name_d.get("ENG") or name_d.get("FRA") or "") if isinstance(name_d, dict) else str(name_d)
                        cpv_str += f"{code} {name} · ".strip()
            nuts_str = ""
            if enriched:
                nuts_str = ", ".join(
                    str(p.get("nuts", "")) for p in
                    (n.get("place-of-performance", []) if isinstance(n.get("place-of-performance"), list) else [])
                    if isinstance(p, dict) and p.get("nuts")
                )
            results.append({
                "source": "TED Europa", "title": _fv(n, "notice-title") or "Untitled",
                "type": _fv(n, "notice-type"), "country": _fv(n, "buyer-country"),
                "agency": _fv(n, "buyer-name"),
                "deadline": str(_fv(n, "deadline-receipt-request"))[:10] if enriched else "",
                "amount": fmt_val(_fv(n, "estimated-value")) if enriched else "", "link": link,
                "publication_number": pub, "publication_date": str(_fv(n, "publication-date"))[:10],
                "nature": _fv(n, "contract-nature") if enriched else "",
                "procedure": _fv(n, "procedure-type") if enriched else "",
                "cpv_codes": cpv_str, "nuts_code": nuts_str,
                "language": _fv(n, "language") if enriched else "",
                "award_value": fmt_val(_fv(n, "award-value")) if enriched else "",
                "lot_count": str(_fv(n, "lot-count")) if enriched else "",
                "buyer_id": _fv(n, "buyer-id") if enriched else "",
                "sector": _fv(n, "buyer-activity") if enriched else "",
                "description": "", "notice_id": pub, "project_id": "",
                "borrower": _fv(n, "buyer-legal-type") if enriched else "",
                "contact": "", "corrigendum": "",
            })
        translated = [_translate_notice(n) for n in results]
        return [n for n in translated if _is_valid_notice(n)]

    def _fetch_term(term: str) -> None:
        kw    = term.strip()
        query = "notice-type IN (cn-standard, cn-social)" if not kw else (f'FT~"{kw}"' if " " in kw else f"FT~{kw}")
        for page in range(1, MAX_PAGES + 1):
            try:
                r = _post(_build_payload(query, TED_FIELDS_ENRICHED, page))
                if r.status_code == 200:
                    notices = r.json().get("notices", [])
                    if not notices:
                        break
                    all_notices.extend(_parse_notices(notices, enriched=True))
                elif r.status_code in (400, 422, 500):
                    # Retry with core fields
                    r2 = _post(_build_payload(query, TED_FIELDS_CORE, page))
                    if r2.status_code == 200:
                        notices = r2.json().get("notices", [])
                        if not notices:
                            break
                        all_notices.extend(_parse_notices(notices, enriched=False))
                    else:
                        break
                else:
                    break
            except Exception:
                break
            if len(all_notices) >= rows * 3:
                break

    try:
        query_terms = terms if terms else [""]
        for term in query_terms:
            _fetch_term(term)
            if len(all_notices) >= rows * 2:
                break

        # Apply fuzzy filter if keyword given
        if terms:
            all_notices = [n for n in all_notices
                           if _fuzzy_match(n["title"] + " " + n.get("description", "") + " " + n.get("sector", ""), terms)]

        return all_notices[:rows] if all_notices else _fetch_ted_rss(keyword, rows)

    except Exception:
        return _fetch_ted_rss(keyword, rows)

def _rss_text(block, tag):
    import re, html
    m = re.search(rf"<{tag}[^>]*>\s*<!\[CDATA\[(.*?)\]\]>", block, re.S)
    if m:
        return m.group(1).strip()
    m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.S)
    if m:
        return html.unescape(m.group(1).strip())
    return ""

def _fetch_ted_rss(keyword, rows):
    import re
    kw = keyword.strip().lower()
    headers = {"User-Agent": "Mozilla/5.0 (compatible; BidAtlas/1.0)"}
    candidate_urls = []
    if kw:
        candidate_urls.append(f"https://ted.europa.eu/en/simap/rss-feed/-/rss/search/comp?q={requests.utils.quote(keyword.strip())}")
    candidate_urls.append("https://ted.europa.eu/en/simap/rss-feed/-/rss/search/comp")
    last_err = ""
    for url in candidate_urls:
        try:
            r = requests.get(url, timeout=20, headers=headers)
            if r.status_code != 200:
                last_err = f"HTTP {r.status_code}"; continue
            raw_text = r.content.decode("utf-8", errors="replace")
            if "<item" not in raw_text:
                last_err = "No items"; continue
            item_blocks = re.findall(r"<item[^>]*>(.*?)</item>", raw_text, re.S)
            results = []
            for block in item_blocks:
                title   = _rss_text(block, "title") or "Untitled"
                link    = _rss_text(block, "link")
                desc    = _rss_text(block, "description")
                pubdate = _rss_text(block, "pubDate")[:10]
                if kw and kw not in title.lower() and kw not in desc.lower():
                    continue
                parts   = title.split("–")
                if len(parts) < 2:
                    parts = title.split("-", 2)
                country = (parts[0].split(":")[-1].strip() if ":" in parts[0] else parts[0].strip()) if len(parts) >= 2 else ""
                ntype   = parts[1].strip() if len(parts) >= 2 else "Contract Notice"
                clean   = parts[-1].strip() if len(parts) >= 3 else title
                results.append({
                    "source": "TED Europa", "title": clean, "type": ntype, "country": country,
                    "agency": "", "deadline": pubdate, "amount": "", "link": link,
                    "nature": "", "sector": "", "publication_number": "", "publication_date": pubdate,
                    "project_id": "", "borrower": "", "contact": "", "description": desc[:500],
                    "notice_id": "", "language": "", "cpv_codes": "", "nuts_code": "",
                    "procedure": "", "award_value": "", "lot_count": "", "buyer_id": "", "corrigendum": "",
                })
                if len(results) >= rows:
                    break
            if results:
                return [_translate_notice(n) for n in results]
            last_err = "No keyword matches"
        except Exception as e:
            last_err = str(e); continue
    return [{"source": "TED Europa", "title": f'No TED Europa results found for "{keyword}"',
             "type": "ℹ️ Info", "country": "", "agency": "", "deadline": "", "amount": "",
             "link": "https://ted.europa.eu/en/search?scope=ACTIVE", "corrigendum": "",
             "description": f"TED Europa feed could not return results ({last_err})."}]


# ══════════════════════════════════════════════════════════════
#  SOURCE 3 — CPPP INDIA
# ══════════════════════════════════════════════════════════════

CPPP_BASE = "https://eprocure.gov.in/cppp/latestactivetendersnew/cpppdata"

CPPP_CURL_HEADERS = [
    "-A", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "-H", "Accept-Language: en-US,en;q=0.9",
    "-H", "Accept-Encoding: gzip, deflate, br",
    "-H", "Connection: keep-alive",
    "-c", "/tmp/cppp_cookies.txt",
    "-b", "/tmp/cppp_cookies.txt",
]

def _cppp_fetch_page(page: int) -> str:
    url = f"{CPPP_BASE}?page={page}"
    result = subprocess.run(
        ["curl", "--silent", "--show-error", "--location", "--compressed",
         "--max-time", "20", *CPPP_CURL_HEADERS, url],
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode())
    return result.stdout.decode("utf-8", errors="replace")

def _cppp_parse_page(html: str, keyword: str) -> list[dict]:
    soup  = BeautifulSoup(html, "html.parser")
    table = soup.find("table", {"id": "table"})
    if not table:
        return []

    kw = keyword.strip().lower()
    results = []

    for tbody in table.find_all("tbody"):
        cells = tbody.find_all("td")
        if len(cells) < 7:
            continue

        title_cell = cells[4]
        link_tag   = title_cell.find("a")
        title      = link_tag.get_text(strip=True) if link_tag else title_cell.get_text(strip=True)
        full_text  = title_cell.get_text(separator="|", strip=True)
        parts      = full_text.split("|")
        ref_no     = parts[1].strip() if len(parts) > 1 else ""

        # CPPP detail URLs embed a session hash + timestamp that expire immediately
        # after page load — no stable deep link can be constructed.
        url = ""
        org        = cells[5].get_text(strip=True)
        corrigendum = cells[6].get_text(strip=True)
        pub_date   = cells[1].get_text(strip=True)
        bid_close  = cells[2].get_text(strip=True)
        open_date  = cells[3].get_text(strip=True)

        # Apply keyword filter client-side if provided
        if kw and kw not in title.lower() and kw not in org.lower() and kw not in ref_no.lower():
            continue

        results.append({
            "source":           "CPPP India",
            "title":            title,
            "type":             "Active Tender",
            "country":          "India",
            "agency":           org,
            "deadline":         bid_close,
            "amount":           "",
            "link":             url,
            "notice_id":        ref_no,
            "publication_date": pub_date,
            "publication_number": ref_no,
            "project_id":       "",
            "borrower":         "",
            "contact":          "",
            "description":      f"Tender Opening Date: {open_date}",
            "sector":           "",
            "nature":           "",
            "procedure":        "",
            "language":         "English",
            "cpv_codes":        "",
            "nuts_code":        "",
            "award_value":      "",
            "lot_count":        "",
            "buyer_id":         "",
            "corrigendum":      corrigendum if corrigendum != "--" else "",
        })

    return results

def fetch_cppp(keyword: str, rows: int) -> list:
    """
    Fetches CPPP tenders. With a keyword, scans up to 20 pages using
    fuzzy multi-term matching. Without a keyword, returns the first 2 pages.
    """
    terms     = _expand_keywords(keyword)
    max_pages = 20 if terms else 2
    results   = []
    seen      = set()

    try:
        for page in range(1, max_pages + 1):
            html    = _cppp_fetch_page(page)
            # Parse without keyword filter first to get all rows
            notices = _cppp_parse_page(html, "")

            if not notices:
                break  # empty page means we've gone past the end

            for n in notices:
                uid = n.get("ref_no") or n.get("title", "")
                if uid in seen:
                    continue
                seen.add(uid)

                # Apply fuzzy match if keyword given
                if terms:
                    searchable = " ".join([
                        n.get("title", ""),
                        n.get("agency", ""),
                        n.get("notice_id", ""),
                        n.get("description", ""),
                    ])
                    if not _fuzzy_match(searchable, terms):
                        continue

                results.append(n)

            # Stop early if we have enough
            if len(results) >= rows:
                break

            time.sleep(0.5)

        # If keyword search found nothing, fall back to latest unfiltered
        if not results and terms:
            html    = _cppp_fetch_page(1)
            results = _cppp_parse_page(html, "")

        return results[:rows]

    except Exception as e:
        return [{
            "source": "CPPP India", "title": f"⚠️ Could not fetch CPPP: {e}",
            "type": "Error", "country": "India", "agency": "", "deadline": "",
            "amount": "", "link": "https://eprocure.gov.in/cppp/latestactivetendersnew/cpppdata",
            "corrigendum": "",
        }]
    

# ADD THIS ENTIRE BLOCK BELOW CPPP SECTION (before SIDEBAR)

# ══════════════════════════════════════════════════════════════
#  SOURCE 4 — ADB (Asian Development Bank)
# ══════════════════════════════════════════════════════════════

ADB_BASE = "https://www.adb.org/projects/tenders"

def _adb_build_url(page: int) -> str:
    if page == 0:
        return f"{ADB_BASE}?terms="
    return f"{ADB_BASE}?terms=&page={page}"

SCRAPER_KEY = st.secrets.get("SCRAPERAPI_KEY", "")

def _adb_fetch_page(page: int) -> str:
    url = _adb_build_url(page)

    if not SCRAPER_KEY:
        raise RuntimeError("Missing SCRAPERAPI_KEY in Streamlit secrets")

    params = {
        "api_key": SCRAPER_KEY,
        "url": url,
        "render": "false"  # faster; ADB doesn’t need JS
    }

    r = requests.get("https://api.scraperapi.com/", params=params, timeout=60)
    r.raise_for_status()
    return r.text

def _adb_detail_field(details_div, label: str) -> str:
    if not details_div:
        return ""
    for p in details_div.find_all("p"):
        spans = p.find_all("span")
        if len(spans) >= 2 and label.lower() in spans[0].get_text(strip=True).lower():
            return spans[1].get_text(strip=True)
    return ""

def _adb_parse_page(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items = soup.select("div.item")
    results = []

    for item in items:
        title_tag = item.select_one(".item-title a")
        if not title_tag:
            continue

        title = title_tag.get_text(strip=True)

        link = title_tag.get("href", "")
        if link and not link.startswith("http"):
            link = "https://www.adb.org" + link

        status = ""
        deadline = ""

        meta = item.select_one(".item-meta")
        if meta:
            for div in meta.find_all("div"):
                spans = div.find_all("span")
                if len(spans) >= 2:
                    label = spans[0].get_text(strip=True)
                    val   = spans[1].get_text(strip=True)
                    if "Status" in label:
                        status = val
                    elif "Deadline" in label:
                        deadline = val

        # ✅ ROBUST FILTER
        # ✅ FILTER
        status_clean = str(status).strip().lower() if status else ""
        if any(k in status_clean for k in ["award", "closed"]):
            continue

        summary_div = item.select_one(".item-summary")
        summary = summary_div.get_text(" ", strip=True) if summary_div else ""
        parts = [p.strip() for p in summary.split(";")]

        project_id = parts[0] if len(parts) > 0 else ""
        country    = parts[1] if len(parts) > 1 else ""
        sector_raw = parts[2] if len(parts) > 2 else ""

        sector = sector_raw.split("Posting")[0].strip() if sector_raw else ""

        details = item.select_one(".item-details")

        agency     = _adb_detail_field(details, "Executing Agency")
        contractor = _adb_detail_field(details, "Contractor Name")
        amount     = _adb_detail_field(details, "Total Contract Amount")

        results.append({
            "source": "ADB",
            "title": title,
            "type": status,
            "country": country,
            "agency": agency,
            "deadline": deadline,
            "amount": amount,
            "link": link,
            "project_id": project_id,
            "borrower": "",
            "publication_date": "",
            "sector": sector,
            "description": contractor,
            "contact": "",
            "notice_id": project_id,
            "publication_number": project_id,
            "nature": "",
            "procedure": "",
            "language": "English",
            "cpv_codes": "",
            "nuts_code": "",
            "award_value": "",
            "lot_count": "",
            "buyer_id": "",
            "corrigendum": "",
        })

    return results

def fetch_adb(keyword: str, rows: int) -> list:
    terms     = _expand_keywords(keyword)
    max_pages = 5 if terms else 2
    results   = []
    seen      = set()

    try:
        for page in range(0, max_pages):
            html    = _adb_fetch_page(page)
            notices = _adb_parse_page(html)

            if not notices:
                break

            for n in notices:
                uid = n.get("link") or n.get("title")
                if uid in seen:
                    continue
                seen.add(uid)

                if terms:
                    searchable = " ".join([
                        n.get("title", ""),
                        n.get("agency", ""),
                        n.get("sector", ""),
                        n.get("description", ""),
                    ])
                    if not _fuzzy_match(searchable, terms):
                        continue

                results.append(n)

            if len(results) >= rows:
                break

            time.sleep(0.5)

        return results[:rows]

    except Exception as e:
        return [{
            "source": "ADB",
            "title": f"⚠️ Could not fetch ADB: {e}",
            "type": "Error",
            "country": "",
            "agency": "",
            "deadline": "",
            "amount": "",
            "link": ADB_BASE,
            "corrigendum": "",
        }]


# ══════════════════════════════════════════════════════════════
#  SIDEBAR
# ══════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("---")
    st.markdown("### 🔍 Search")

    keyword = st.text_input(
        "Keyword", value="",
        placeholder="climate, governance, health…",
        help="Leave blank to browse latest notices",
    )

    st.markdown("**Sources**")
    src_wb   = st.checkbox("🌍 World Bank",  value=True)
    src_ted  = st.checkbox("🇪🇺 TED Europa", value=True)
    src_cppp = st.checkbox("🇮🇳 CPPP India", value=True)
    src_adb = st.checkbox("🌏 ADB", value=True)

    results_limit = st.slider("Results per source", 3, 20, 5, step=1)
    search_btn    = st.button("🔎 Search", use_container_width=True, type="primary")

    st.markdown("---")
    st.markdown("**Quick keywords**")
    for qk in ["climate", "governance", "health", "infrastructure",
                "education", "digital", "construction", "IT services"]:
        if st.button(qk, use_container_width=True, key=f"qk_{qk}"):
            keyword    = qk
            search_btn = True

    st.markdown("---")
    st.caption("Live data · World Bank · ADB · TED Europa · CPPP India")
    st.markdown(
        '<p style="font-size:0.72rem;color:#5a7a9a;margin:0;">'
        'Built by <strong style="color:#003a70;">Aqib Ahmed</strong>.</p>',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════

st.markdown("""
<div class="app-header">
  <div style="display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:0.5rem;">
    <div style="min-width:0;flex:1;">
      <h1>🌐 BidAtlas — Global Procurement Tracker</h1>
      <p>World Bank · ADB · TED Europa · CPPP India · Live data · Click ▶ on any card to expand full details</p>
      <p style="margin-top:0.4rem;font-size:0.72rem;opacity:0.55;">Built by <strong style="opacity:0.9;">Aqib Ahmed</strong></p>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

with st.expander("📦 v1.7 — Click to view version changes", expanded=False):
    st.markdown("""
**v1.7** *(current)*
- Added **ADB (Asian Development Bank)** as a fourth live source

**v1.6** *(current)*
- Added **CPPP India** as a third live source (Central Public Procurement Portal)
- CPPP tenders fetched via curl + BeautifulSoup, keyword-filtered client-side
- Orange accent colour and 🇮🇳 badge to distinguish Indian tenders
- Deadline badge now parses CPPP date format (DD-Mon-YYYY HH:MM AM/PM)

**v1.5**
- Auto-translation of TED Europa notices to English via `deep-translator`

**v1.4**
- Dates displayed in DD-MM-YYYY format

**v1.3**
- Enriched field fetching for World Bank and TED Europa
- Full Details panel with structured sections
""")

with st.expander("🔒 Privacy Policy", expanded=False):
    st.markdown("""
**Last updated: April 2026**

#### What this app does
BidAtlas is a read-only procurement tracking tool. It fetches publicly available tender
notices from the World Bank, TED Europa, and CPPP India and displays them in your browser.

#### Data we collect
**None.** BidAtlas does not collect, store, or transmit any personal data.

- **Search keywords** are sent directly to the respective third-party APIs (World Bank,
  TED Europa) or used locally to filter results. They are not logged or retained by this app.
- **No cookies** are set by this application. The `cookies.txt` file used during CPPP
  requests is written to local temporary storage on the server running the app and contains
  only session tokens issued by CPPP — no personal information.
- **No accounts, no tracking, no analytics.**

#### Third-party sources
This app retrieves data from:
- [World Bank Open Data](https://data.worldbank.org) — governed by the [World Bank Terms of Use](https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets)
- [TED Europa](https://ted.europa.eu) — governed by the [European Union Open Data policy](https://data.europa.eu/en/publications/open-data-in-europe)
- [CPPP India](https://eprocure.gov.in/cppp) — governed by the Government of India's portal terms

This app has no affiliation with any of these organisations.

#### Contact
For questions about this app, contact the developer: **Aqib Ahmed**.
""")

# ── Fetch ──────────────────────────────────────────────────────

if "all_notices" not in st.session_state or search_btn:
    selected_sources = []
    if src_wb:   selected_sources.append(("World Bank", fetch_worldbank))
    if src_ted:  selected_sources.append(("TED Europa", fetch_ted))
    if src_cppp: selected_sources.append(("CPPP India", fetch_cppp))
    if src_adb:  selected_sources.append(("ADB", fetch_adb))

    all_notices: list = []
    with st.spinner("Fetching from all sources in parallel…"):
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(fn, keyword, results_limit): name for name, fn in selected_sources}
            for future in as_completed(futures):
                try:
                    all_notices.extend(future.result())
                except Exception as e:
                    st.warning(f"Error from {futures[future]}: {e}")

    all_notices.sort(key=lambda n: n.get("deadline") or "9999-99-99")
    st.session_state["all_notices"] = all_notices
    st.session_state["kw"]          = keyword

all_notices: list = st.session_state.get("all_notices", [])
kw: str           = st.session_state.get("kw", "")

# ── Stats ──────────────────────────────────────────────────────

if all_notices:
    source_counts: dict = {}
    for n in all_notices:
        s = n.get("source", "Unknown")
        source_counts[s] = source_counts.get(s, 0) + 1

    urgent   = sum(1 for n in all_notices if 0 <= (days_until(n.get("deadline") or "") or 999) <= 14)
    with_val = sum(1 for n in all_notices if n.get("amount") or n.get("award_value"))

    cols = st.columns(len(source_counts) + 3)
    cols[0].metric("Total Notices", len(all_notices))
    cols[1].metric("Closing ≤14d",  urgent)
    cols[2].metric("With Value",     with_val)
    for i, (src, count) in enumerate(source_counts.items(), 3):
        cols[i].metric(src, count)

    st.markdown("---")

# ── Filters ────────────────────────────────────────────────────

if all_notices:
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        all_countries  = sorted(set(n.get("country", "") for n in all_notices if n.get("country")))
        country_filter = st.multiselect("Filter by country", all_countries, placeholder="All countries")
    with col2:
        source_filter  = st.multiselect("Filter by source", ["World Bank", "TED Europa", "CPPP India", "ADB"], placeholder="All sources")
    with col3:
        nature_vals    = sorted(set(n.get("nature", "") for n in all_notices if n.get("nature")))
        nature_filter  = st.multiselect("Filter by nature", nature_vals, placeholder="All types")

    filtered = [
        n for n in all_notices
        if (not country_filter or n.get("country") in country_filter)
        and (not source_filter  or n.get("source")  in source_filter)
        and (not nature_filter  or n.get("nature")  in nature_filter)
    ]

    label = f"**{len(filtered)} notices**" + (f' matching *"{kw}"*' if kw else " (latest)")
    st.caption(label)

    for i, notice in enumerate(filtered):
        render_notice(notice, i)

else:
    st.info("Use the sidebar to search, or click **Search** to load the latest notices.")