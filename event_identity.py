"""Deterministic article and event identity contracts for report candidates."""

from __future__ import annotations

import datetime
import hashlib
import json
import re
import urllib.parse
from typing import Any


EVENT_IDENTITY_CONTRACT_VERSION = "a5-v1"

_TRACKING_QUERY_KEYS = {
    "fbclid", "gclid", "mc_cid", "mc_eid", "ocid", "ref", "source",
}

_COUNTRY_ALIASES = {
    "美國": "united-states",
    "united states": "united-states",
    "usa": "united-states",
    "英國": "united-kingdom",
    "united kingdom": "united-kingdom",
    "uk": "united-kingdom",
    "德國": "germany",
    "germany": "germany",
    "加拿大": "canada",
    "canada": "canada",
    "澳洲": "australia",
    "australia": "australia",
    "奧地利": "austria",
    "austria": "austria",
    "日本": "japan",
    "japan": "japan",
    "韓國": "south-korea",
    "south korea": "south-korea",
    "法國": "france",
    "france": "france",
    "義大利": "italy",
    "italy": "italy",
    "瑞士": "switzerland",
    "switzerland": "switzerland",
    "新加坡": "singapore",
    "singapore": "singapore",
    # Canonicalize the upstream geography owner output; Jakarta city
    # inference remains intentionally outside this module.
    "印尼": "indonesia",
    "印度尼西亞": "indonesia",
    "indonesia": "indonesia",
    "indonesian": "indonesia",
    "香港": "hong-kong",
    "hong kong": "hong-kong",
    "台灣": "taiwan",
    "臺灣": "taiwan",
    "taiwan": "taiwan",
    "阿聯酋": "united-arab-emirates",
    "united arab emirates": "united-arab-emirates",
}

_CITY_ALIASES = (
    ("new-york", ("new york city", "new york", "nyc", "manhattan", "紐約")),
    ("taoyuan", ("taoyuan", "桃園")),
    ("gelsenkirchen", ("gelsenkirchen", "蓋爾森基興")),
    ("berlin", ("berlin", "柏林")),
    ("london", ("london", "倫敦")),
    ("toronto", ("toronto", "多倫多")),
    ("washington", ("washington", "華盛頓")),
    ("dubai", ("dubai", "杜拜", "迪拜")),
    ("vienna", ("vienna", "wien", "維也納")),
    ("sydney", ("sydney", "雪梨", "悉尼")),
    ("basel", ("basel", "巴塞爾")),
    ("leipzig", ("leipzig", "萊比錫")),
    ("vancouver", ("vancouver", "溫哥華")),
    ("austin", ("austin", "奧斯汀")),
    ("paris", ("paris", "巴黎")),
    ("tokyo", ("tokyo", "東京")),
    ("seoul", ("seoul", "首爾", "서울")),
)

_CITY_COUNTRIES = {
    "new-york": "united-states",
    "taoyuan": "taiwan",
    "gelsenkirchen": "germany",
    "berlin": "germany",
    "london": "united-kingdom",
    "toronto": "canada",
    "washington": "united-states",
    "dubai": "united-arab-emirates",
    "vienna": "austria",
    "sydney": "australia",
    "basel": "switzerland",
    "leipzig": "germany",
    "vancouver": "canada",
    "austin": "united-states",
    "paris": "france",
    "tokyo": "japan",
    "seoul": "south-korea",
}

_OPERATOR_ALIASES = (
    ("mta", ("metropolitan transportation authority", "new york city transit", "nyc subway", "mta", "nyct")),
    ("taoyuan-metro", ("taoyuan metro", "桃園捷運", "桃捷")),
    ("tfl", ("transport for london", "london underground", "tfl")),
    ("ttc", ("toronto transit commission", "toronto subway", "ttc")),
    ("wmata", ("washington metropolitan area transit authority", "wmata")),
    ("bvg", ("berliner verkehrsbetriebe", "bvg")),
    ("wiener-linien", ("wiener linien",)),
    ("sydney-metro", ("sydney metro",)),
    ("tokyo-metro", ("tokyo metro",)),
)

_COLOR_LINES = {
    "brown": "brown-line", "棕": "brown-line",
    "green": "green-line", "綠": "green-line", "绿": "green-line",
    "red": "red-line", "紅": "red-line", "红": "red-line",
    "blue": "blue-line", "藍": "blue-line", "蓝": "blue-line",
    "orange": "orange-line", "橙": "orange-line",
    "yellow": "yellow-line", "黃": "yellow-line", "黄": "yellow-line",
    "purple": "purple-line", "紫": "purple-line",
}

_PACKAGE_TERMS = (
    ("electromechanical", ("electromechanical", "electro-mechanical", "e&m", "m&e", "systems turnkey", "機電系統統包", "機電統包", "機電標", "機電工程")),
    ("signalling", ("signalling", "signaling", "signal system", "cbtc", "號誌", "信號")),
    ("rolling-stock", ("rolling stock", "train fleet", "trainsets", "vehicles package", "車輛標", "電聯車", "列車採購")),
    ("traction-power", ("traction power", "power supply", "substation", "供電", "牽引電力")),
    ("communications", ("telecommunications", "communications system", "radio system", "通訊系統")),
    ("platform-doors", ("platform screen door", "platform doors", "psd", "月臺門", "月台門")),
    ("civil-works", ("civil works", "tunnel contract", "station construction", "土建", "隧道工程", "車站工程")),
)

_INCIDENT_TERMS = (
    ("hazardous-material", ("asbestos", "hazardous material", "有害物質", "石綿", "石棉")),
    ("air-quality-hazard", ("unusual odor", "unusual odour", "unusual smell", "異味", "異臭")),
    ("fire", ("caught fire", "train fire", "station fire", "subway fire", "metro fire", "fire", "blaze", "feuer", "brand", "火災", "火灾")),
    ("collision", ("collision", "collided", "crash", "accident", "unfall", "zusammenstoß", "碰撞", "相撞", "撞擊")),
    ("derailment", ("derailment", "derailed", "entgleist", "出軌", "脫軌")),
    ("power-failure", ("power outage", "power failure", "traction power failure", "供電故障", "供電中斷")),
    ("signal-failure", ("signal failure", "signalling failure", "signaling failure", "號誌故障", "信號故障")),
    ("security", ("stabbing", "shooting", "assault", "security incident", "持刀", "槍擊", "攻擊")),
)

_OBJECT_TERMS = (
    ("maintenance-train", ("work train", "cleaning train", "vacuum train", "maintenance train", "工程列車", "工作列車", "清潔列車")),
    ("tram", ("streetcar", "straßenbahn", "strassenbahn", "tram", "路面電車")),
    ("metro-train", ("subway train", "metro train", "trainset", "地鐵列車", "捷運列車")),
    ("station", ("subway station", "metro station", "rail station", "地鐵站", "捷運站", "車站")),
    ("signalling", ("signalling", "signaling", "signal system", "cbtc", "號誌", "信號")),
    ("platform-doors", ("platform screen door", "platform doors", "psd", "月臺門", "月台門")),
    ("rolling-stock", ("rolling stock", "fleet", "train cars", "車隊", "電聯車")),
)


def _compact(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _slug(value: Any) -> str:
    text = urllib.parse.unquote(_compact(value)).casefold().replace("&", " and ")
    return re.sub(r"[^a-z0-9\u3400-\u9fff]+", "-", text).strip("-")


def _contains_term(text: str, term: str) -> bool:
    term_lower = term.casefold()
    if any(ord(character) > 127 for character in term_lower) or len(term_lower) >= 5:
        return term_lower in text
    return re.search(rf"(?<![a-z0-9]){re.escape(term_lower)}(?![a-z0-9])", text) is not None


def _candidate_text(candidate: dict, *, include_url: bool = True) -> str:
    fields = ["title", "raw_title", "snippet", "summary", "summary_zh"]
    if include_url:
        fields.extend(("canonical_url", "resolved_article_url", "source_href", "url", "raw_url"))
    return " ".join(urllib.parse.unquote(_compact(candidate.get(field))) for field in fields if candidate.get(field))


def canonical_article_key(candidate: dict) -> str:
    """Return an article-level URL identity with tracking noise removed."""
    raw_url = next((
        _compact(candidate.get(field))
        for field in ("canonical_url", "resolved_article_url", "source_href", "url", "raw_url")
        if _compact(candidate.get(field)).startswith(("http://", "https://"))
    ), "")
    if not raw_url:
        return ""
    try:
        parsed = urllib.parse.urlsplit(raw_url)
        host = (parsed.hostname or "").casefold()
        if host.startswith("www."):
            host = host[4:]
        path = re.sub(r"/{2,}", "/", urllib.parse.unquote(parsed.path or "/")).rstrip("/") or "/"
        query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
        query = sorted(
            (key, value)
            for key, value in query
            if key.casefold() not in _TRACKING_QUERY_KEYS and not key.casefold().startswith("utm_")
        )
        return urllib.parse.urlunsplit(("https", host, path, urllib.parse.urlencode(query), ""))
    except (TypeError, ValueError):
        return raw_url.casefold().rstrip("/")


def _first_alias(text: str, groups: tuple[tuple[str, tuple[str, ...]], ...]) -> str:
    for canonical, aliases in groups:
        if any(_contains_term(text, alias) for alias in aliases):
            return canonical
    return ""


def _country(candidate: dict, city: str) -> str:
    for field in ("country", "resolved_region", "region"):
        value = _compact(candidate.get(field)).casefold()
        if value in _COUNTRY_ALIASES:
            return _COUNTRY_ALIASES[value]
    return _CITY_COUNTRIES.get(city, "")


def _station_keys(text: str) -> tuple[str, ...]:
    stations: set[str] = set()
    for match in re.findall(
        r"\b([A-Z][A-Za-z0-9'’.-]*(?:\s+[A-Z][A-Za-z0-9'’.-]*){0,3})\s+(?:subway\s+|metro\s+)?station\b",
        text,
    ):
        key = _slug(match)
        if key and key not in {"new-york-city", "metro", "subway"}:
            stations.add(key)
    for match in re.findall(r"([\u3400-\u9fffA-Za-z0-9]{1,16})(?:捷運站|地鐵站|車站)", text):
        key = _slug(match)
        if key:
            stations.add(key)
    return tuple(sorted(stations))[:6]


def _project_key(candidate: dict, title: str, text: str) -> str:
    explicit = next((_compact(candidate.get(field)) for field in ("project", "project_name", "line", "metro_line") if _compact(candidate.get(field))), "")
    if explicit:
        return _slug(explicit)
    for haystack in (title, text):
        lower = haystack.casefold()
        for color, canonical in _COLOR_LINES.items():
            if _contains_term(lower, f"{color} line") or f"{color}線" in lower:
                return canonical
        match = re.search(r"\b[Ll]ine\s*[-#]?\s*(\d{1,3}|[A-Z])\b", haystack)
        if match:
            return f"line-{match.group(1)}"
        match = re.search(r"\b([A-Za-z][A-Za-z0-9'’-]{2,})\s+line\b", haystack, flags=re.IGNORECASE)
        if match:
            return _slug(f"{match.group(1)} line")
        match = re.search(r"([\u3400-\u9fffA-Za-z0-9]{1,12}(?:捷運|地鐵)?[一二三四五六七八九十0-9A-Za-z]+線)", haystack)
        if match:
            return _slug(match.group(1))
    return ""


def _package_key(candidate: dict, text_lower: str) -> str:
    explicit = next((_compact(candidate.get(field)) for field in ("package", "package_name", "system_package", "contract_package") if _compact(candidate.get(field))), "")
    if explicit:
        return _slug(explicit)
    for canonical, terms in _PACKAGE_TERMS:
        if any(_contains_term(text_lower, term) for term in terms):
            return canonical
    return ""


def _contract_key(candidate: dict, text: str) -> str:
    explicit = next((_compact(candidate.get(field)) for field in ("contract_id", "contract_number", "package_id", "tender_id", "award_id") if _compact(candidate.get(field))), "")
    if explicit:
        return _slug(explicit)
    for match in re.findall(r"\b(?:contract|package|lot|tender)\s*(?:no\.?|number|#)?\s*([A-Z0-9][A-Z0-9._/-]{2,})\b", text, flags=re.IGNORECASE):
        if (
            any(character.isdigit() for character in match)
            or any(character in "._-/" for character in match)
        ):
            return _slug(match)
    return ""


def _vendor_key(candidate: dict, text: str) -> str:
    explicit = next((_compact(candidate.get(field)) for field in ("awarded_contractor", "contractor", "vendor", "supplier") if _compact(candidate.get(field))), "")
    if explicit:
        return _slug(explicit)
    patterns = (
        r"\b([A-Z][A-Za-z0-9&.-]{2,}(?:\s+[A-Z][A-Za-z0-9&.-]{2,}){0,2})\s+(?:is\s+)?(?:appointed|selected|wins|won|awarded)\b",
        r"\b(?:selects?|appoints?|awards?(?:\s+the\s+contract)?\s+to)\s+([A-Z][A-Za-z0-9&.-]{2,}(?:\s+[A-Z][A-Za-z0-9&.-]{2,}){0,2})\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return _slug(match.group(1))
    return ""


def _procurement_action(text_lower: str) -> str:
    if any(_contains_term(text_lower, term) for term in ("contract amendment", "variation order", "change order", "合約變更", "契約變更")):
        return "contract-amendment"
    if any(_contains_term(text_lower, term) for term in (
        "contract award", "awarded", "award decision", "appointed", "selected", "selects", "wins contract", "won contract",
        "completed award", "award announcement", "決標", "得標", "完成評選",
    )):
        return "award"
    if any(_contains_term(text_lower, term) for term in (
        "tender announcement", "invitation to tender", "invites bids", "call for bids", "procurement notice",
        "招標公告", "公開招標", "徵求投標", "公告招標",
    )):
        return "tender"
    if any(_contains_term(text_lower, term) for term in ("contract signing", "sign the contract", "contract to be signed", "簽約", "預定簽約")):
        return "contract-signing"
    return "procurement"


def _incident_type(text_lower: str) -> str:
    for canonical, terms in _INCIDENT_TERMS:
        if any(_contains_term(text_lower, term) for term in terms):
            return canonical
    return ""


def _event_object(text_lower: str, package: str) -> str:
    for canonical, terms in _OBJECT_TERMS:
        if any(_contains_term(text_lower, term) for term in terms):
            return canonical
    return package


def _injury_count(text_lower: str) -> int | None:
    patterns = (
        r"\binjures?\s+(\d{1,3})\b",
        r"\b(\d{1,3})\s+(?:people|persons|passengers|workers|firefighters)?\s*(?:were\s+)?(?:hurt|injured|hospitalized|hospitalised)\b",
        r"(\d{1,3})\s*人(?:受傷|受伤|送醫)",
    )
    for pattern in patterns:
        match = re.search(pattern, text_lower, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    if any(term in text_lower for term in ("more than a dozen", "over a dozen", "超過十人", "多人受傷")):
        return 14 if "14" in text_lower else 12
    return None


def _date_value(candidate: dict) -> tuple[str, str]:
    for field, kind in (
        ("incident_date", "incident_date"),
        ("award_date", "award_date"),
        ("opening_date", "opening_date"),
        ("event_date", "event_date"),
        ("published_date", "publication_date"),
        ("date", "publication_date"),
    ):
        value = _compact(candidate.get(field))
        match = re.search(r"(?<!\d)(20\d{2}-\d{2}-\d{2})(?!\d)", value)
        if match:
            return match.group(1), kind
    return "", "unknown"


def _date_obj(value: str) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _event_class(category: str, action: str, incident: str, text_lower: str) -> str:
    if incident or category == "重大事故":
        return "incident"
    if action in {"award", "tender", "contract-signing", "contract-amendment", "procurement"}:
        return "procurement"
    if any(term in text_lower for term in ("procurement", "tender", "contract award", "機電標案", "採購", "決標", "招標")):
        return "procurement"
    return "general"


def build_event_identity(candidate: dict) -> dict:
    """Build bounded structured components; never depend on publisher or query location."""
    text = _candidate_text(candidate)
    text_lower = text.casefold()
    title = _compact(candidate.get("title") or candidate.get("raw_title"))
    city = _first_alias(text_lower, _CITY_ALIASES)
    country = _country(candidate, city)
    operator = _first_alias(text_lower, _OPERATOR_ALIASES)
    project = _project_key(candidate, title, text)
    package = _package_key(candidate, text_lower)
    contract = _contract_key(candidate, text)
    vendor = _vendor_key(candidate, text)
    category = _compact(candidate.get("classification") or candidate.get("primary_category") or candidate.get("preliminary_type"))
    incident = _incident_type(text_lower)
    procurement_context = bool(
        category == "機電標案"
        or any(term in text_lower for term in (
            "procurement", "tender", "contract award", "awarded", "appointed",
            "selected", "selects", "wins contract", "won contract",
            "決標", "得標", "招標", "機電標",
        ))
    )
    if procurement_context:
        action = _procurement_action(text_lower)
    elif incident or category == "重大事故":
        action = "incident"
    elif any(term in text_lower for term in ("upgrade", "modernization", "modernisation", "renewal", "升級", "更新")):
        action = "upgrade"
    elif any(term in text_lower for term in ("testing", "trial", "commissioning", "測試", "試運轉")):
        action = "testing"
    elif any(term in text_lower for term in ("opening", "opens", "entered service", "通車", "啟用")):
        action = "opening"
    else:
        action = "event"
    event_object = _event_object(text_lower, package)
    date_value, date_kind = _date_value(candidate)
    event_class = _event_class(category, action, incident, text_lower)
    stations = _station_keys(text)
    injury_count = _injury_count(text_lower)
    geo_key = "/".join(value for value in (country, city) if value)
    identity_payload = {
        "contract_version": EVENT_IDENTITY_CONTRACT_VERSION,
        "event_class": event_class,
        "country": country,
        "city": city,
        "operator": operator,
        "project": project,
        "package": package,
        "contract": contract,
        "action": action,
        "event_object": event_object,
        "incident_type": incident,
        "vendor": vendor,
        "stations": list(stations),
        "event_date": date_value,
        "event_date_kind": date_kind,
        "injury_count": injury_count,
    }
    serialized = json.dumps(identity_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    canonical_id = "evt_" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:24]
    return {
        **identity_payload,
        "canonical_event_id": canonical_id,
        # Backward-compatible fingerprint names consumed by existing diagnostics.
        "operator_key": operator,
        "geo_key": geo_key,
        "asset_key": event_object or package or category,
        "action_key": action,
        "incident_key": incident,
        "injury_band": "none" if injury_count is None else "1" if injury_count == 1 else "2-9" if injury_count < 10 else "10+",
        "category_key": category,
        "date_bucket": date_value,
    }


def annotate_event_identity(candidate: dict) -> dict:
    identity = build_event_identity(candidate)
    candidate["canonical_event_id"] = identity["canonical_event_id"]
    candidate["event_identity_components"] = {
        key: identity[key]
        for key in (
            "contract_version", "event_class", "country", "city", "operator",
            "project", "package", "contract", "action", "event_object",
            "incident_type", "vendor", "stations", "event_date",
            "event_date_kind", "injury_count",
        )
    }
    candidate["event_fingerprint"] = {
        key: identity[key]
        for key in (
            "operator_key", "geo_key", "asset_key", "action_key", "incident_key",
            "injury_band", "category_key", "date_bucket", "canonical_event_id",
        )
    }
    candidate.setdefault("duplicate_type", "")
    candidate.setdefault("matched_event_id", "")
    candidate.setdefault("same_event_reason", "")
    candidate.setdefault("conflicting_evidence", [])
    return identity


def _conflict(component: str, left: Any, right: Any) -> dict:
    return {"component": component, "left": left, "right": right}


def compare_materialized_event_identities(
    left_candidate: dict,
    right_candidate: dict,
    left: dict,
    right: dict,
) -> dict:
    """Compare already materialized identities without rebuilding either side."""
    left_article = canonical_article_key(left_candidate)
    right_article = canonical_article_key(right_candidate)
    article_url_match = bool(left_article and left_article == right_article)
    conflicts: list[dict] = []
    for component in ("country", "city", "project", "package", "contract"):
        left_value = left.get(component)
        right_value = right.get(component)
        if left_value and right_value and left_value != right_value:
            conflicts.append(_conflict(component, left_value, right_value))
    if left["event_class"] == "procurement" and right["event_class"] == "procurement":
        if left["vendor"] and right["vendor"] and left["vendor"] != right["vendor"]:
            conflicts.append(_conflict("vendor", left["vendor"], right["vendor"]))
        if left["action"] != right["action"]:
            conflicts.append(_conflict("procurement_action", left["action"], right["action"]))
    if left["event_class"] == "incident" and right["event_class"] == "incident":
        if left["incident_type"] and right["incident_type"] and left["incident_type"] != right["incident_type"]:
            conflicts.append(_conflict("incident_type", left["incident_type"], right["incident_type"]))
        left_stations = set(left["stations"])
        right_stations = set(right["stations"])
        if left_stations and right_stations and left_stations.isdisjoint(right_stations):
            conflicts.append(_conflict("station", sorted(left_stations), sorted(right_stations)))

    left_date = _date_obj(left["event_date"])
    right_date = _date_obj(right["event_date"])
    date_days = abs((left_date - right_date).days) if left_date and right_date else None
    event_class = left["event_class"] if left["event_class"] == right["event_class"] else "mixed"
    date_window = 21 if event_class == "procurement" and left["action"] == right["action"] == "award" else 3
    if (
        left["event_date_kind"] != "publication_date"
        and right["event_date_kind"] != "publication_date"
        and left_date
        and right_date
    ):
        date_window = min(date_window, 3)
    if date_days is not None and date_days > date_window:
        conflicts.append(_conflict("event_date_window", left["event_date"], right["event_date"]))

    # URL identity is strong article evidence, but synthetic/reused URLs must not
    # collapse records whose structured geography, scope, or dates contradict it.
    article_duplicate = article_url_match and not conflicts

    same_event = False
    matched: list[str] = []
    if article_duplicate:
        same_event = True
        matched.append("canonical_article_url")
    elif not conflicts and event_class == "incident" and left["incident_type"] and left["incident_type"] == right["incident_type"]:
        score = 0
        matched.append("incident_type")
        if left["city"] and left["city"] == right["city"]:
            score += 1
            matched.append("city")
        elif left["country"] and left["country"] == right["country"]:
            matched.append("country")
        left_stations = set(left["stations"])
        right_stations = set(right["stations"])
        if left_stations and right_stations and not left_stations.isdisjoint(right_stations):
            score += 3
            matched.append("station")
        if left["operator"] and left["operator"] == right["operator"]:
            score += 1
            matched.append("operator")
        if left["event_object"] and left["event_object"] == right["event_object"]:
            score += 1
            matched.append("event_object")
        if left["injury_count"] is not None and left["injury_count"] == right["injury_count"]:
            score += 2
            matched.append("injury_count")
        if date_days is not None:
            matched.append("bounded_date")
        same_event = score >= 2 and bool(
            (left["country"] and left["country"] == right["country"])
            or (left["city"] and left["city"] == right["city"])
            or (left_stations and right_stations and not left_stations.isdisjoint(right_stations))
        )
    elif not conflicts and event_class == "procurement" and left["action"] == right["action"]:
        same_project = bool(left["project"] and left["project"] == right["project"])
        same_package = bool(left["package"] and left["package"] == right["package"])
        same_contract = bool(left["contract"] and left["contract"] == right["contract"])
        if same_project:
            matched.append("project")
        if same_package:
            matched.append("package")
        if same_contract:
            matched.append("contract")
        if left["vendor"] and left["vendor"] == right["vendor"]:
            matched.append("vendor")
        if date_days is not None:
            matched.append("bounded_date")
        same_event = same_project and bool(
            same_package
            or same_contract
            or (not left["package"] and not right["package"] and date_days is not None and date_days <= 3)
        )
    elif not conflicts and event_class != "mixed":
        anchors = 0
        scope_anchor = False
        for component in ("city", "operator", "project", "event_object", "action"):
            if left.get(component) and left.get(component) == right.get(component):
                anchors += 1
                matched.append(component)
                if component in {"city", "operator", "project"}:
                    scope_anchor = True
        if date_days is not None:
            matched.append("bounded_date")
        same_event = scope_anchor and anchors >= 2 and (date_days is None or date_days <= date_window)

    duplicate_type = "ARTICLE_DUPLICATE" if article_duplicate else "EVENT_DUPLICATE" if same_event else ""
    if same_event:
        reason = (
            "canonical article URL matched; structured event identity also treated as the same event"
            if article_duplicate
            else "matched structured event fields: " + ", ".join(dict.fromkeys(matched))
        )
    elif conflicts:
        reason = "conflicting structured event fields: " + ", ".join(item["component"] for item in conflicts[:8])
    else:
        reason = "insufficient shared structured event evidence"
    return {
        "same_event": same_event,
        "article_duplicate": article_duplicate,
        "duplicate_type": duplicate_type,
        "left_event_id": left["canonical_event_id"],
        "right_event_id": right["canonical_event_id"],
        "matched_fields": list(dict.fromkeys(matched))[:12],
        "same_event_reason": reason[:240],
        "conflicting_evidence": conflicts[:8],
        "date_distance_days": date_days,
        "date_window_days": date_window,
    }


def compare_event_candidates(left_candidate: dict, right_candidate: dict) -> dict:
    """Compare two structured identities and return a bounded explainable decision."""
    return compare_materialized_event_identities(
        left_candidate,
        right_candidate,
        build_event_identity(left_candidate),
        build_event_identity(right_candidate),
    )


def mark_duplicate(
    candidate: dict,
    matched: dict,
    comparison: dict,
    *,
    candidate_identity: dict | None = None,
    matched_identity: dict | None = None,
) -> None:
    """Attach bounded diagnostics to a suppressed candidate."""
    matched_identity = matched_identity or annotate_event_identity(matched)
    candidate_identity = candidate_identity or annotate_event_identity(candidate)
    candidate["duplicate_type"] = comparison.get("duplicate_type", "")
    candidate["matched_event_id"] = matched_identity["canonical_event_id"]
    candidate["same_event_reason"] = comparison.get("same_event_reason", "")[:240]
    candidate["conflicting_evidence"] = list(comparison.get("conflicting_evidence", []))[:8]
    if comparison.get("same_event"):
        candidate["canonical_event_id"] = matched_identity["canonical_event_id"]
        candidate["event_fingerprint"]["canonical_event_id"] = matched_identity["canonical_event_id"]


def canonical_event_id(candidate: dict) -> str:
    """Return the upstream identity, honoring explicit legacy fingerprints for old reports."""
    existing = _compact(candidate.get("canonical_event_id"))
    if existing:
        return existing
    components = candidate.get("event_identity_components")
    if isinstance(components, dict) and components:
        payload = json.dumps(components, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return "evt_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    fingerprint = candidate.get("event_fingerprint")
    if isinstance(fingerprint, dict) and fingerprint:
        payload = json.dumps(fingerprint, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return "legacy_evt_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return build_event_identity(candidate)["canonical_event_id"]
