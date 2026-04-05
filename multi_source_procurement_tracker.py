"""
Global Procurement Tracker — Multi-Source Streamlit App

Sources:
  - World Bank (IBRD + IDA)  → JSON API, no key
  - TED Europa (EU)          → REST API v3, no key (RSS fallback)

Setup:
    python3 -m venv venv
    source venv/bin/activate
    pip install streamlit requests deep-translator
    streamlit run procurement_tracker.py
"""

import requests
import streamlit as st
from datetime import datetime, timedelta
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
.src-wb  { border-left-color: #005BAA; }
.src-ted { border-left-color: #003399; }

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
    try:
        return (datetime.strptime(date_str[:10], "%Y-%m-%d") - datetime.today()).days
    except Exception:
        return None

def fmt_date(date_str: str) -> str:
    """Convert YYYY-MM-DD to DD-MM-YYYY for display. Returns original if unparseable."""
    if not date_str or date_str.strip() in ("", "N"):
        return ""
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d").strftime("%d-%m-%Y")
    except Exception:
        return date_str[:10]

def _translate(text: str) -> str:
    """Translate text to English using Google Translate via deep-translator.
    Falls back silently to the original text on any error."""
    if not _TRANSLATOR_AVAILABLE or not text or not text.strip():
        return text
    try:
        translated = GoogleTranslator(source="auto", target="en").translate(text)
        return translated if translated else text
    except Exception:
        return text


def _translate_notice(notice: dict) -> dict:
    """Return a copy of the notice with title and type translated to English.
    Only applied to TED Europa notices (World Bank API always returns English)."""
    if notice.get("source") != "TED Europa":
        return notice
    return {
        **notice,
        "title": _translate(notice.get("title", "")),
        "type":  _translate(notice.get("type", "")),
    }


def deadline_badge(dl: str) -> str:
    if not dl or dl.strip() in ("", "N"):
        return ""
    days = days_until(dl)
    label = fmt_date(dl)
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
    """Render one detail row, return empty string if value is blank."""
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
        "World Bank": ("🌍 World Bank", "src-wb"),
        "TED Europa": ("🇪🇺 TED Europa", "src-ted"),
    }
    src_label, src_class = src_labels.get(src, (src, ""))

    badges = [
        f'<span class="badge badge-source">{src_label}</span>',
        f'<span class="badge badge-type">{ntype}</span>'          if ntype    else "",
        f'<span class="badge badge-country">🌍 {country}</span>' if country else "",
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
    link_line   = f'<a href="{link}" target="_blank" style="font-size:0.82rem;color:#005BAA;text-decoration:none;">🔗 View notice →</a>' if link else ""

    card_html = (
        f'<div class="notice-card card-collapsed {src_class}">' 
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

        sections = []

        id_rows = "".join(filter(None, [
            _dr("Notice Ref / ID",       notice_id or pub_num or project_id),
            _dr("Publication Date",      fmt_date(pub_date)),
            _dr("Submission Deadline",   fmt_date(dl)),
            _dr("Source",                src_label),
            _dr("Language",              lang),
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
            sections.append(f'<h4>📝 Description / Documents</h4><div style="color:#1a2a40;line-height:1.7;">{desc_text}</div>')

        if link:
            sections.append(f'<h4>🔗 Source Link</h4><a href="{link}" target="_blank" style="color:#005BAA;">{link}</a>')

        if sections:
            st.markdown(f'<div class="detail-panel">{"".join(sections)}</div>', unsafe_allow_html=True)
        else:
            st.caption("No additional detail available for this notice.")


#  SOURCE 1 — WORLD BANK  (enriched)
# ══════════════════════════════════════════════════════════════

def fetch_worldbank(keyword: str, rows: int) -> list:
    params = {
        "format": "json", "apilang": "en", "srce": "both",
        "rows": rows, "os": 0,
        "srt": "submission_deadline_date", "order": "desc",
    }
    if keyword.strip():
        params["qterm"] = keyword.strip()

    try:
        r = requests.get(
            "https://search.worldbank.org/api/v2/procnotices",
            params=params, timeout=15,
        )
        r.raise_for_status()
        data = r.json()

        raw = data.get("procnotices") or data.get("notices", {})
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
            link = n.get("url") or (f"https://projects.worldbank.org/en/projects-operations/procurement-detail/{nid}" if nid else "")

            # Value: try multiple candidate fields
            amount_raw = (
                n.get("contract_amount_usd") or
                n.get("totalcontract") or
                n.get("totalContract") or ""
            )
            try:
                amount_str = f"USD {float(amount_raw):,.0f}" if amount_raw else ""
            except (ValueError, TypeError):
                amount_str = str(amount_raw) if amount_raw else ""

            contact_parts = list(filter(None, [
                n.get("contact_name", ""),
                n.get("contact_email", ""),
                n.get("contact_phone", ""),
            ]))

            results.append({
                "source":             "World Bank",
                "title":              n.get("project_name") or n.get("noticeTitle") or "Untitled",
                "type":               n.get("notice_type") or n.get("noticeType", ""),
                "country":            n.get("project_ctry_name") or n.get("countryname", ""),
                "agency":             n.get("contact_agency") or n.get("borrower", ""),
                "deadline":           (n.get("submission_deadline_date") or n.get("deadlineDate") or "")[:10],
                "amount":             amount_str,
                "link":               link,
                # enriched
                "notice_id":          nid,
                "project_id":         n.get("project_id", ""),
                "borrower":           n.get("borrower", ""),
                "publication_date":   (n.get("publish_date") or n.get("publishDate") or "")[:10],
                "sector":             n.get("sector") or n.get("majorsector_exact", ""),
                "description":        n.get("short_description") or n.get("noticeText", ""),
                "contact":            " · ".join(contact_parts),
                "procedure":          n.get("procurement_method") or n.get("procMethod", ""),
                "nature":             n.get("procurement_group", ""),
                "language":           n.get("lang", ""),
                "publication_number": nid,
                "buyer_id":           n.get("contact_agency", ""),
                "cpv_codes":          "",
                "nuts_code":          "",
                "award_value":        "",
                "lot_count":          "",
            })
        return results

    except Exception as e:
        return [{"source": "World Bank", "title": f"⚠️ Error: {e}",
                 "type": "", "country": "", "agency": "", "deadline": "",
                 "amount": "", "link": ""}]


# ══════════════════════════════════════════════════════════════
#  SOURCE 2 — TED EUROPA  (enriched, REST v3 + RSS fallback)
#  Field list cross-referenced with:
#   • Flutter TEDService (ted_service.dart)
#   • TED API v3 NoticeResponse schema
# ══════════════════════════════════════════════════════════════

# Fields confirmed working from Flutter TEDService implementation.
# Additional enrichment fields are requested in a second pass only if
# the primary fetch succeeds, to avoid triggering TED API 400 errors.
TED_FIELDS_CORE = [
    "publication-number",
    "notice-title",
    "buyer-name",
    "notice-type",
    "buyer-country",
    "publication-date",
]

TED_FIELDS_ENRICHED = TED_FIELDS_CORE + [
    "deadline-receipt-request",
    "contract-nature",
    "procedure-type",
    "estimated-value",
    "award-value",
    "currency",
    "cpv",
    "place-of-performance",
    "lot-count",
    "buyer-legal-type",
    "buyer-activity",
    "buyer-id",
    "language",
    "notice-links",
]

def _fv(n: dict, k: str) -> str:
    """Safely extract a scalar string from a TED v3 notice field."""
    v = n.get(k, "")
    if not v:
        return ""
    if isinstance(v, list):
        parts = []
        for item in v:
            if isinstance(item, dict):
                parts.append(
                    item.get("value") or item.get("ENG") or item.get("FRA")
                    or next(iter(item.values()), "")
                )
            else:
                parts.append(str(item))
        return ", ".join(str(p) for p in parts if p)
    if isinstance(v, dict):
        return (
            v.get("value") or v.get("ENG") or v.get("FRA")
            or next(iter(v.values()), "")
        )
    return str(v)

def fetch_ted(keyword: str, rows: int) -> list:
    """
    Mirrors Flutter TEDService._searchApi exactly:
      - blank keyword  → notice-type IN (cn-standard, cn-social)
      - single word    → FT~word
      - phrase         → FT~"phrase"
    First attempt uses enriched field list; if that 400s, retries with
    the 6 confirmed-safe core fields from the Flutter implementation.
    """
    kw = keyword.strip()
    if not kw:
        query = "notice-type IN (cn-standard, cn-social)"
    elif " " in kw:
        query = f'FT~"{kw}"'
    else:
        query = f"FT~{kw}"

    def _build_payload(fields):
        return {
            "query":            query,
            "fields":           fields,
            "page":             1,
            "limit":            rows,
            "scope":            "ACTIVE",
            "checkQuerySyntax": False,
            "paginationMode":   "PAGE_NUMBER",
        }

    def _post(payload):
        return requests.post(
            "https://api.ted.europa.eu/v3/notices/search",
            json=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=15,
        )

    def _parse_notices(notices: list, enriched: bool) -> list:
        results = []
        for n in notices:
            pub  = _fv(n, "publication-number")
            link = f"https://ted.europa.eu/en/notice/-/detail/{pub}" if pub else ""

            # Values — only present if enriched fields were fetched
            curr   = _fv(n, "currency") if enriched else ""
            def fmt_val(v):
                if not v or v in ("", "0"):
                    return ""
                try:
                    return f"{curr} {float(v):,.0f}".strip()
                except (ValueError, TypeError):
                    return str(v)

            # CPV
            cpv_str = ""
            if enriched:
                cpv_raw = n.get("cpv", [])
                if isinstance(cpv_raw, list):
                    parts = []
                    for c in cpv_raw:
                        if isinstance(c, dict):
                            code   = str(c.get("code", ""))
                            name_d = c.get("name", {})
                            name   = (name_d.get("ENG") or name_d.get("FRA") or "") if isinstance(name_d, dict) else str(name_d)
                            parts.append(f"{code} {name}".strip())
                        else:
                            parts.append(str(c))
                    cpv_str = " · ".join(filter(None, parts))

            # NUTS
            nuts_str = ""
            if enriched:
                pop_raw = n.get("place-of-performance", [])
                if isinstance(pop_raw, list):
                    nuts_str = ", ".join(
                        str(p.get("nuts", "")) for p in pop_raw
                        if isinstance(p, dict) and p.get("nuts")
                    )

            # Document links
            doc_links = ""
            if enriched:
                links_raw = n.get("notice-links", [])
                if isinstance(links_raw, list):
                    doc_links = " | ".join(
                        str(l.get("url", "")) for l in links_raw
                        if isinstance(l, dict) and l.get("url")
                    )

            results.append({
                "source":             "TED Europa",
                "title":              _fv(n, "notice-title") or "Untitled",
                "type":               _fv(n, "notice-type"),
                "country":            _fv(n, "buyer-country"),
                "agency":             _fv(n, "buyer-name"),
                "deadline":           str(_fv(n, "deadline-receipt-request"))[:10] if enriched else "",
                "amount":             fmt_val(_fv(n, "estimated-value")) if enriched else "",
                "link":               link,
                "publication_number": pub,
                "publication_date":   str(_fv(n, "publication-date"))[:10],
                "nature":             _fv(n, "contract-nature") if enriched else "",
                "procedure":          _fv(n, "procedure-type") if enriched else "",
                "cpv_codes":          cpv_str,
                "nuts_code":          nuts_str,
                "language":           _fv(n, "language") if enriched else "",
                "award_value":        fmt_val(_fv(n, "award-value")) if enriched else "",
                "lot_count":          str(_fv(n, "lot-count")) if enriched else "",
                "buyer_id":           _fv(n, "buyer-id") if enriched else "",
                "sector":             _fv(n, "buyer-activity") if enriched else "",
                "description":        doc_links,
                "notice_id":          pub,
                "project_id":         "",
                "borrower":           _fv(n, "buyer-legal-type") if enriched else "",
                "contact":            "",
            })
        return [_translate_notice(n) for n in results]

    try:
        # ── Attempt 1: enriched field list ──────────────────────────────
        r = _post(_build_payload(TED_FIELDS_ENRICHED))
        if r.status_code == 200:
            notices = r.json().get("notices", [])
            if notices:
                return _parse_notices(notices, enriched=True)
            # 200 but empty — fall through to RSS

        # ── Attempt 2: core fields only (matches Flutter exactly) ───────
        if r.status_code in (400, 422) or not r.json().get("notices"):
            r2 = _post(_build_payload(TED_FIELDS_CORE))
            if r2.status_code == 200:
                notices = r2.json().get("notices", [])
                if notices:
                    return _parse_notices(notices, enriched=False)

    except Exception:
        pass

    return _fetch_ted_rss(keyword, rows)

def _rss_text(block: str, tag: str) -> str:
    """Extract innerText of first <tag>…</tag> in a raw RSS item string.
    Works even when the XML is malformed — no parser involved."""
    import re
    # Try CDATA first:  <tag><![CDATA[…]]></tag>
    m = re.search(rf"<{tag}[^>]*>\s*<!\[CDATA\[(.*?)\]\]>", block, re.S)
    if m:
        return m.group(1).strip()
    # Plain text:  <tag>…</tag>
    m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.S)
    if m:
        import html
        return html.unescape(m.group(1).strip())
    return ""

def _parse_rss_items(raw_text: str, kw: str, rows: int) -> list:
    """Parse <item> blocks from raw RSS/XML text using regex — tolerates malformed XML."""
    import re
    item_blocks = re.findall(r"<item[^>]*>(.*?)</item>", raw_text, re.S)
    results = []
    for block in item_blocks:
        title   = _rss_text(block, "title") or "Untitled"
        link    = _rss_text(block, "link")
        desc    = _rss_text(block, "description")
        pubdate = _rss_text(block, "pubDate")[:10]

        if kw and kw not in title.lower() and kw not in desc.lower():
            continue

        # "12345-2026: Romania – Construction work – Project name"
        parts   = title.split("–")   # en-dash
        if len(parts) < 2:
            parts = title.split("-", 2)   # plain hyphen fallback
        country = (parts[0].split(":")[-1].strip() if ":" in parts[0] else parts[0].strip()) if len(parts) >= 2 else ""
        ntype   = parts[1].strip() if len(parts) >= 2 else "Contract Notice"
        clean   = parts[-1].strip() if len(parts) >= 3 else title

        results.append({
            "source": "TED Europa", "title": clean, "type": ntype,
            "country": country, "agency": "", "deadline": pubdate,
            "amount": "", "link": link,
            "nature": "", "sector": "", "publication_number": "",
            "publication_date": pubdate, "project_id": "", "borrower": "",
            "contact": "", "description": desc[:500],
            "notice_id": "", "language": "", "cpv_codes": "",
            "nuts_code": "", "procedure": "", "award_value": "",
            "lot_count": "", "buyer_id": "",
        })
        if len(results) >= rows:
            break
    return results

def _fetch_ted_rss(keyword: str, rows: int) -> list:
    kw = keyword.strip().lower()

    # TED supports keyword search via the `q` param on the SIMAP RSS endpoint
    # Try keyword-scoped feed first, then fall back to generic latest feed
    headers = {"User-Agent": "Mozilla/5.0 (compatible; BidAtlas/1.0)"}
    candidate_urls = []
    if kw:
        # q param performs full-text search in TED SIMAP
        candidate_urls.append(
            f"https://ted.europa.eu/en/simap/rss-feed/-/rss/search/comp?q={requests.utils.quote(keyword.strip())}"
        )
    # Generic latest contract notices — always try as final fallback
    candidate_urls.append("https://ted.europa.eu/en/simap/rss-feed/-/rss/search/comp")

    last_err = ""
    for url in candidate_urls:
        try:
            r = requests.get(url, timeout=20, headers=headers)
            if r.status_code != 200:
                last_err = f"HTTP {r.status_code}"
                continue
            raw_text = r.content.decode("utf-8", errors="replace")
            if "<item" not in raw_text:
                last_err = "Feed returned no items"
                continue
            results = _parse_rss_items(raw_text, kw, rows)
            if results:
                return [_translate_notice(n) for n in results]
            last_err = "No keyword matches in feed"
        except Exception as e:
            last_err = str(e)
            continue

    # Nothing worked — return a clean informational notice, not an error card
    kw_label = f' for "{keyword}"' if keyword.strip() else ''
    msg = 'No TED Europa results found' + kw_label
    return [{
        "source": "TED Europa",
        "title": msg,
        "type": "ℹ️ Info", "country": "", "agency": "", "deadline": "",
        "amount": "", "link": "https://ted.europa.eu/en/search?scope=ACTIVE",
        "nature": "", "sector": "", "publication_number": "", "publication_date": "",
        "project_id": "", "borrower": "", "contact": "",
        "description": f"The TED Europa feed could not return results ({last_err}). "
                       "Try a broader keyword or visit TED directly.",
        "notice_id": "", "language": "", "cpv_codes": "",
        "nuts_code": "", "procedure": "", "award_value": "",
        "lot_count": "", "buyer_id": "",
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
    src_wb  = st.checkbox("🌍 World Bank",  value=True)
    src_ted = st.checkbox("🇪🇺 TED Europa", value=True)

    results_limit = st.slider("Results per source", 3, 20, 5, step=1)
    search_btn    = st.button("🔎 Search", use_container_width=True, type="primary")

    st.markdown("---")
    st.markdown("**Quick keywords**")
    for qk in ["climate", "governance", "capacity building", "health",
                "public financial management", "infrastructure", "education", "digital"]:
        if st.button(qk, use_container_width=True, key=f"qk_{qk}"):
            keyword    = qk
            search_btn = True

    st.markdown("---")
    st.caption("Live data · World Bank & TED Europa")
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
      <p>World Bank · TED Europa · Live data · Click ▶ on any card to expand full details</p>
      <p style="margin-top:0.4rem;font-size:0.72rem;opacity:0.55;">Built by <strong style="opacity:0.9;">Aqib Ahmed</strong></p>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Version changelog expander ─────────────────────────────────
with st.expander("📦 v1.5 — Click to view version changes", expanded=False):
    st.markdown("""
**v1.5** *(current)*
- Added automatic translation of TED Europa notices to English via `deep-translator`

**v1.4**
- Dates now displayed in DD-MM-YYYY format across cards and detail panels

**v1.3**
- Integrated enriched field fetching for both World Bank and TED Europa
- Full Details panel with 4 structured sections: Identification, Procurement Details, Buyer / Authority, Financials
- Robust TED API two-tier fallback (enriched → core fields → RSS)
- Malformed RSS XML handled via regex parser instead of `xml.etree`

**v1.2**
- Added World Bank and TED Europa multi-source parallel fetching
- Deadline urgency badges (🟢 / 🟡 / 🔴) with days-remaining count
- Country, source, and nature filter controls

**v1.1**
- Initial multi-source procurement tracker
- World Bank JSON API integration
- TED Europa RSS fallback
""")

# ── Legal expanders ───────────────────────────────────────────
with st.expander("🔒 Privacy Policy & Terms of Use", expanded=False):
    st.markdown("""
**Privacy Policy**

BidAtlas does not collect, store, or share any personal data. All procurement data displayed is sourced directly from publicly available APIs (World Bank, TED Europa) and is not modified beyond translation and formatting. No user accounts, cookies, or tracking mechanisms are used.

Search queries are sent directly from your browser to third-party APIs and are not logged by BidAtlas.

**Terms of Use**

BidAtlas is provided as an internal tool for informational purposes only. It does not constitute procurement advice or a formal tender notification service. Users are responsible for verifying notice details directly with the issuing authority before acting on any information displayed.

Data sourced from World Bank and TED Europa is subject to their respective terms of use:
- [World Bank Terms](https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets)
- [TED Europa Terms](https://ted.europa.eu/en/legal-notice)

For questions, contact the tool maintainer.
""")

# ── Fetch ─────────────────────────────────────────────────────

if "all_notices" not in st.session_state or search_btn:
    selected_sources = []
    if src_wb:  selected_sources.append(("World Bank", fetch_worldbank))
    if src_ted: selected_sources.append(("TED Europa", fetch_ted))

    all_notices: list = []
    with st.spinner("Fetching from all sources in parallel…"):
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

    all_notices.sort(key=lambda n: n.get("deadline") or "9999-99-99")
    st.session_state["all_notices"] = all_notices
    st.session_state["kw"]          = keyword

all_notices: list = st.session_state.get("all_notices", [])
kw: str           = st.session_state.get("kw", "")

# ── Stats ─────────────────────────────────────────────────────

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

# ── Filters ───────────────────────────────────────────────────

if all_notices:
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        all_countries = sorted(set(n.get("country", "") for n in all_notices if n.get("country")))
        country_filter = st.multiselect("Filter by country", all_countries, placeholder="All countries")

    with col2:
        source_filter = st.multiselect(
            "Filter by source", ["World Bank", "TED Europa"], placeholder="All sources"
        )

    with col3:
        nature_vals = sorted(set(n.get("nature", "") for n in all_notices if n.get("nature")))
        nature_filter = st.multiselect("Filter by nature", nature_vals, placeholder="All types")

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