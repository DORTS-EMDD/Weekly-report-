"""Shared evidence resolver for formal electromechanical system taxonomy."""

from __future__ import annotations

import re
from collections.abc import Mapping


CORE_SYSTEM_LABELS = (
    "電聯車",
    "號誌",
    "供電",
    "通訊",
    "自動收費",
    "機廠維修設備",
    "月臺門",
    "垂直運輸設備",
    "通風空調系統",
)


CORE_SYSTEM_TERM_GROUPS: dict[str, tuple[str, ...]] = {
    "電聯車": (
        "vehicle equipment", "car door", "train door", "bogie", "wheelset",
        "coupler", "propulsion", "traction inverter", "traction inverters", "traction motor",
        "braking system", "brake system", "tcms", "rolling-stock", "車門", "轉向架",
        "輪對", "聯結器", "推進", "牽引變流器", "牽引馬達", "煞車", "制動",
        "車載", "電聯車",
    ),
    "號誌": (
        "communication-based train control", "automatic train operation",
        "automatic train protection", "automatic train supervision",
        "unattended train operation", "cbtc", "atp", "ato", "ats", "uto",
        "goa4", "goa3", "goa2", "goa", "driverless operation", "driverless",
        "unattended operation", "autonomous train", "signalling", "signaling",
        "signal system", "interlocking", "train control", "train supervision",
        "wayside signal", "axle counter", "axle counters", "號誌", "信號", "聯鎖",
        "列車控制", "列控", "行車監控", "自動列車監控", "軸計數器",
        "全自動無人駕駛", "無人駕駛", "無人運轉", "自動駕駛",
        "自動列車運轉", "全自動列車運轉", "信号", "信号システム", "신호", "신호 시스템",
    ),
    "供電": (
        "traction power", "traction power supply", "power supply", "traction substation",
        "substation", "third rail", "third-rail", "overhead catenary", "power rail",
        "ups", "供電", "牽引供電", "牽引變電站", "變電站", "第三軌", "電力系統",
        "不斷電系統",
    ),
    "通訊": (
        "cctv communication", "cctv", "data transmission", "communications network",
        "communication network", "telecommunications", "telecommunication system",
        "communications system", "communications systems", "communications", "telecom",
        "wireless communication", "wireless radio", "radio network", "radio system",
        "fiber optic", "fibre optic", "fiber communication", "fibre communication",
        "pids", "passenger information display", "tetra", "lte", "5g", "telephone system",
        "通訊網路", "通訊系統", "通訊", "無線通訊", "無線電", "光纖通訊", "光纖",
        "資料傳輸", "旅客資訊顯示", "電話",
    ),
    "自動收費": (
        "automatic fare collection", "afc", "fare gate", "ticket gate", "ticketing system",
        "ticketing", "ticket vending machine", "contactless payment", "smart card", "票閘",
        "售票機", "自動收費", "票務", "感應支付", "智慧卡",
    ),
    "機廠維修設備": (
        "underfloor wheel lathe", "wheel lathe", "lifting equipment", "lifting jack",
        "train washing system", "train washer", "wash plant", "inspection equipment",
        "depot machinery", "maintenance facility equipment", "maintenance equipment",
        "workshop maintenance equipment", "workshop equipment", "depot equipment",
        "rescue equipment", "depot electromechanical", "depot e&m", "depot mep",
        "機廠維修設備", "機廠設備", "機廠機電", "維修設備", "檢修設備", "車床",
        "舉升設備", "舉升", "列車清洗系統", "洗車設備", "洗車", "救援設備",
    ),
    "月臺門": (
        "platform screen door", "platform screen doors", "platform door", "platform doors",
        "psd", "月臺門", "月台門",
    ),
    "垂直運輸設備": (
        "elevator", "elevators", "lift", "lifts", "escalator", "escalators",
        "moving walk", "moving walkway", "travelator", "vertical transport",
        "垂直運輸", "電梯", "升降機", "電扶梯", "手扶梯", "走道電梯",
    ),
    "通風空調系統": (
        "station ventilation", "tunnel ventilation", "ventilation system",
        "ventilation", "hvac", "air conditioning", "smoke extraction",
        "smoke control", "environmental control", "environmental control system",
        "platform cooling", "通風系統", "隧道通風", "車站通風", "空調",
        "環控系統", "環境控制系統", "排煙", "排煙系統", "月臺降溫",
    ),
}


DEPOT_LOCATION_TERMS = (
    "maintenance depot", "train maintenance facility", "maintenance facility",
    "depot maintenance", "operations and maintenance centre",
    "operations and maintenance center", "depot", "workshop", "北機廠", "機廠",
    "維修廠", "維修中心",
)

GENERIC_NETWORK_TERMS = (
    "thermal energy network", "district energy network", "heat network", "network",
)

CORE_TO_REPORT_LABEL = {
    "電聯車": "車輛系統",
    "號誌": "號誌系統",
    "供電": "供電系統",
    "通訊": "通訊系統",
    "自動收費": "自動收費系統 AFC",
    "機廠維修設備": "機廠設備",
    "月臺門": "月臺門系統",
    "垂直運輸設備": "垂直運輸設備",
    "通風空調系統": "通風空調系統",
}

CORE_TO_PROCUREMENT_GROUP = {
    "電聯車": "rolling_stock",
    "號誌": "signalling",
    "供電": "traction_power",
    "通訊": "telecommunications",
    "自動收費": "afc",
    "機廠維修設備": "depot_electromechanical",
    "月臺門": "platform_screen_doors",
    "垂直運輸設備": "vertical_transport",
    "通風空調系統": "ventilation_hvac",
}


# These contextual terms were historically applied by the selector after the
# shared taxonomy ran.  They remain part of the A3 semantics, but now live in
# this owner so a candidate receives one authoritative `core_systems` result.
_ROLLING_STOCK_SPECIFIC_TERMS = (
    "vehicle equipment", "car door", "train door", "bogie", "wheelset", "coupler",
    "propulsion", "traction inverter", "traction inverters", "traction motor",
    "braking system", "brake system", "tcms", "車門", "轉向架", "輪對", "聯結器",
    "牽引變流器", "牽引馬達", "煞車", "制動", "車載",
)
_ROLLING_STOCK_EVENT_TERMS = (
    "new", "supply", "supplied", "order", "orders", "ordered", "procure", "procurement", "procured",
    "purchase", "purchased", "delivery", "delivered", "introduce", "introduced",
    "deployment", "deployed", "upgrade", "upgraded", "modernization", "modernisation",
    "performance", "maintenance", "overhaul", "acquisition", "acquire", "fleet",
    "award", "awarded", "awards",
    "replacement", "replaced", "採購", "訂購", "交車", "供應", "得標", "決標",
    "導入", "投入", "性能", "維修", "更新", "汰換",
)
_DEPOT_FACILITY_TERMS = (
    "maintenance facility", "maintenance depot", "train maintenance facility",
    "depot maintenance", "depot", "workshop", "operations and maintenance centre",
    "operations and maintenance center", "電扶梯", "電梯", "空調", "月臺設備",
    "月台設備", "旅客資訊系統", "影像分析", "監控中心", "安全中心", "行控中心",
    "維修機廠",
)
_GENERIC_PACKAGE_TERMS = (
    "e&m package", "e & m package", "electromechanical package",
    "electromechanical systems package", "electromechanical systems",
    "integrated e&m", "integrated electromechanical", "mep package", "systems package",
    "systems contract", "機電標", "機電系統標", "機電系統", "機電設備",
)

_URBAN_RAIL_CONTEXT_TERMS = (
    "metro", "subway", "underground", "urban rail", "light rail", "light-rail",
    "tram", "tramway", "streetcar", "rapid transit", "mass rapid transit", "mrt",
    "lrt", "station", "platform", "tunnel", "rail line", "metro line", "捷運",
    "地鐵", "輕軌", "都市軌道", "車站", "月臺", "隧道",
)
_BUILDING_ONLY_CONTEXT_TERMS = (
    "office", "offices", "office building", "building", "property", "residential",
    "apartment", "hotel", "shopping mall", "corporate headquarters", "辦公室",
    "辦公大樓", "建築", "大樓", "住宅", "商場", "房地產",
)
_VERTICAL_TRANSPORT_ACTION_TERMS = (
    "upgrade", "upgraded", "modernize", "modernizes", "modernized", "modernise", "modernises",
    "modernization", "modernisation",
    "replace", "replaced", "replacement", "install", "installed", "installation",
    "procure", "procurement", "contract", "award", "awarded", "supply", "supplied",
    "deliver", "delivered", "commission", "commissioned", "package", "renewal",
    "更新", "升級", "汰換", "更換", "新建", "安裝", "採購", "決標", "發包", "啟用",
)
_NON_URBAN_VEHICLE_CONTEXT_TERMS = (
    "high-speed rail", "high speed rail", "high-speed train", "high speed train",
    "hsr", "shinkansen", "bullet train", "tgv", "intercity", "inter-city",
    "long-distance", "long distance", "regional rail", "commuter rail",
    "mainline", "main line", "freight", "rail freight", "locomotive",
    "national rail", "高速鐵路", "高鐵", "城際鐵路", "貨運鐵路",
)


def _has_urban_rail_context(text: str) -> bool:
    """Return whether text identifies a rail facility rather than a generic building."""
    lowered = str(text or "").casefold()
    if not _contains_any(lowered, _URBAN_RAIL_CONTEXT_TERMS):
        return False
    explicit_facility = _contains_any(
        lowered,
        (
            "metro station", "subway station", "rail station", "urban rail station",
            "light rail station", "metro line", "subway line", "rail line", "tunnel",
            "station", "platform", "捷運站", "地鐵站", "車站", "隧道", "月臺",
        ),
    )
    if _contains_any(lowered, _BUILDING_ONLY_CONTEXT_TERMS) and not explicit_facility:
        return False
    return True


def _contextual_facility_hits(
    evidence_fields: Mapping[str, str],
    system: str,
) -> list[dict[str, str]]:
    """Require rail-facility context for context-sensitive E&M classes."""
    hits: list[dict[str, str]] = []
    terms = CORE_SYSTEM_TERM_GROUPS[system]
    for field, value in evidence_fields.items():
        text = str(value or "")
        if not _has_urban_rail_context(text):
            continue
        if system == "垂直運輸設備" and not _contains_any(text, _VERTICAL_TRANSPORT_ACTION_TERMS):
            continue
        for hit in _positive_hits({field: text}, terms):
            hits.append(hit)
    return hits


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = str(text or "").casefold()
    for term in terms:
        normalized = str(term or "").casefold()
        if re.fullmatch(r"[a-z0-9][a-z0-9\s/&.\-]*", normalized):
            if re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", lowered):
                return True
        elif normalized in lowered:
            return True
    return False


def _apply_contextual_vehicle_semantics(text: str, systems: list[str]) -> list[str]:
    """Preserve the former A3 rolling-stock/depot context rules in the owner."""

    lowered = str(text or "").casefold()
    has_depot_facility = _contains_any(lowered, _DEPOT_FACILITY_TERMS)
    has_specific_vehicle_evidence = _contains_any(lowered, _ROLLING_STOCK_SPECIFIC_TERMS)
    explicit_vehicle_terms = (
        *_ROLLING_STOCK_SPECIFIC_TERMS,
        "rolling stock", "vehicle fleet", "train fleet", "trainset", "trainsets",
        "metro train", "metro trains", "subway train", "subway trains",
        "tram-train", "tram-trains", "tram train", "tram trains",
        "light rail vehicle", "light rail vehicles", "lrv", "車輛系統", "車輛設備", "電聯車",
    )
    generic_package_without_vehicle_detail = (
        _contains_any(lowered, _GENERIC_PACKAGE_TERMS)
        and not _contains_any(lowered, explicit_vehicle_terms)
    )
    has_vehicle_event = bool(
        re.search(
            r"\b(?:new|supply|supplied|order(?:s|ed)?|procure(?:d|ment)?|purchase(?:d)?|"
            r"deliver(?:y|ed)?|introduc(?:e|ed|tion)|deploy(?:ed|ment)?|upgrade(?:d)?|"
            r"moderni[sz](?:e|ed|ation)|performance|maintenan(?:ce|t)|overhaul|"
            r"acqui(?:re|red|sition)|replace(?:d|ment)?)\b.{0,60}\b(?:rolling stock|"
            r"vehicle fleet|train fleet|metro trains?|subway trains?|tram-trains?|tram trains?|"
            r"light rail vehicles?|lrv|trainsets?|trains?|列車|車輛)\b",
            lowered,
        )
        or re.search(
            r"\b(?:rolling stock|vehicle fleet|train fleet|metro trains?|subway trains?|"
            r"tram-trains?|tram trains?|light rail vehicles?|lrv|trainsets?|列車|車輛)\b.{0,60}\b(?:"
            r"maintenan(?:ce|t)|overhaul|performance|upgrade(?:d)?|moderni[sz](?:e|ed|ation)|"
            r"replace(?:d|ment)|renewal)\b",
            lowered,
        )
        or (
            _contains_any(lowered, explicit_vehicle_terms)
            and _contains_any(lowered, _ROLLING_STOCK_EVENT_TERMS)
        )
    )
    intrinsic_urban_vehicle = _contains_any(
        lowered,
        (
            "rolling stock", "train fleet", "trainset", "trainsets",
            "tram-train", "tram train", "light rail vehicle", "light rail vehicles",
            "metro train", "metro trains", "subway train", "subway trains", "lrv",
        ),
    )
    non_urban_vehicle_context = _contains_any(lowered, _NON_URBAN_VEHICLE_CONTEXT_TERMS)
    vehicle_context = (
        (_has_urban_rail_context(lowered) or intrinsic_urban_vehicle)
        and not non_urban_vehicle_context
    )
    systems = list(systems)
    if (
        not generic_package_without_vehicle_detail
        and (has_specific_vehicle_evidence or (has_vehicle_event and vehicle_context))
        and "電聯車" not in systems
        and (not has_depot_facility or has_specific_vehicle_evidence)
    ):
        systems.append("電聯車")
    if generic_package_without_vehicle_detail:
        systems = [system for system in systems if system != "電聯車"]
    if "號誌" in systems and "電聯車" in systems and not _contains_any(lowered, _ROLLING_STOCK_SPECIFIC_TERMS):
        systems.remove("電聯車")
    return systems

_NEGATION_PATTERN = re.compile(
    r"\b(?:no|not|without|neither|nor|lacks?|missing|rather than)\b|"
    r"(?:沒有|未列明|未提供|不含|未包含|並非|不是)",
    flags=re.IGNORECASE,
)


def _term_matches(text: str, term: str):
    lowered = (text or "").casefold()
    needle = (term or "").casefold()
    if not needle:
        return []
    if re.fullmatch(r"[a-z0-9][a-z0-9\s/&.\-]*", needle):
        return list(re.finditer(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", lowered))
    return list(re.finditer(re.escape(needle), lowered))


def _is_positive_match(text: str, start: int) -> bool:
    lowered = (text or "").casefold()
    clause_start = max(
        lowered.rfind(mark, 0, start)
        for mark in (".", "!", "?", ";", ":", "。", "！", "？", "；", "：", "\n")
    )
    return not _NEGATION_PATTERN.search(lowered[clause_start + 1:start])


def _positive_hits(fields: Mapping[str, str], terms: tuple[str, ...]) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for field, value in fields.items():
        text = str(value or "")
        for term in terms:
            for match in _term_matches(text, term):
                if not _is_positive_match(text, match.start()):
                    continue
                key = (field, term.casefold())
                if key in seen:
                    continue
                seen.add(key)
                hits.append({"field": field, "evidence": term})
                break
    return hits


def _contextual_signalling_hits(fields: Mapping[str, str]) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    rail_terms = (
        "train", "metro", "subway", "urban rail", "light rail", "捷運", "地鐵", "輕軌",
        "列車", "電聯車", "行車",
    )
    contextual_terms = ("automatic operation", "unattended", "autonomous", "自動運轉")
    for field, value in fields.items():
        text = str(value or "")
        if not _positive_hits({field: text}, rail_terms):
            continue
        hits.extend(_positive_hits({field: text}, contextual_terms))
    return hits


def _contextual_depot_subject_hits(fields: Mapping[str, str]) -> list[dict[str, str]]:
    """Accept an operationally commissioned maintenance facility as the event subject."""
    subject_actions = (
        "opens", "opened", "commissioned", "enters service", "entered service",
        "inaugurated", "啟用", "投入使用", "正式營運",
    )
    subject_terms = (
        "train maintenance facility", "maintenance facility", "maintenance depot",
        "operations and maintenance centre", "operations and maintenance center",
        "維修機廠", "維修中心", "機廠",
    )
    hits: list[dict[str, str]] = []
    for field, value in fields.items():
        text = str(value or "")
        if not _positive_hits({field: text}, subject_actions):
            continue
        for hit in _positive_hits({field: text}, subject_terms):
            hits.append({
                "field": field,
                "evidence": hit["evidence"],
            })
    return hits


def classify_electromechanical_evidence(fields: Mapping[str, str] | str) -> dict[str, object]:
    """Resolve formal systems from technical-function evidence, rejecting location-only collisions."""
    if isinstance(fields, str):
        evidence_fields: dict[str, str] = {"text": fields}
    else:
        evidence_fields = {
            str(field): str(value or "")
            for field, value in fields.items()
            if value
        }

    systems: list[str] = []
    winning: list[dict[str, str]] = []
    rejected: list[dict[str, str]] = []

    for system in CORE_SYSTEM_LABELS:
        if system in {"垂直運輸設備", "通風空調系統"}:
            hits = _contextual_facility_hits(evidence_fields, system)
        else:
            hits = _positive_hits(evidence_fields, CORE_SYSTEM_TERM_GROUPS[system])
        if system == "號誌":
            hits.extend(_contextual_signalling_hits(evidence_fields))
        elif system == "機廠維修設備":
            hits.extend(_contextual_depot_subject_hits(evidence_fields))
        if hits:
            systems.append(system)
            for hit in hits[:6]:
                winning.append({"system": system, "evidence_type": "technical_function", **hit})

    depot_locations = _positive_hits(evidence_fields, DEPOT_LOCATION_TERMS)
    if depot_locations and "機廠維修設備" not in systems:
        for hit in depot_locations[:6]:
            rejected.append({
                "system": "機廠維修設備",
                "evidence_type": "event_location",
                **hit,
                "reason": "location_only_evidence",
            })

    communication_hits = [
        item for item in winning
        if item.get("system") == "通訊"
    ]
    if not communication_hits:
        for hit in _positive_hits(evidence_fields, GENERIC_NETWORK_TERMS)[:4]:
            rejected.append({
                "system": "通訊",
                "evidence_type": "generic_network",
                **hit,
                "reason": "network_without_communications_context",
            })

    reason = (
        "technical_function_evidence"
        if systems
        else "insufficient_electromechanical_evidence"
    )
    return {
        "systems": systems,
        "winning_evidence": winning[:16],
        "rejected_evidence": rejected[:12],
        "classification_reason": reason,
    }


def classify_candidate_electromechanical(candidate: Mapping[str, object]) -> dict[str, object]:
    fields = {
        field: str(candidate.get(field, "") or "")
        for field in ("raw_title", "title", "raw_snippet", "snippet", "prefetched_text_snippet")
        if candidate.get(field)
    }
    result = classify_electromechanical_evidence(fields)
    text = " ".join(fields.values())
    systems = _apply_contextual_vehicle_semantics(text, list(result["systems"]))
    if systems and not result["systems"]:
        result["classification_reason"] = "technical_event_evidence"
    result["systems"] = systems
    return result


def report_labels_for_core_systems(systems: list[str] | tuple[str, ...]) -> list[str]:
    selected = set(systems or [])
    return [CORE_TO_REPORT_LABEL[label] for label in CORE_SYSTEM_LABELS if label in selected]
