"""V19.4 candidate admission, classification, gates, scoring, and Python selection."""

import datetime
import difflib
import json
import re
import time
import urllib.parse
from collections import Counter
from urllib.parse import urlparse

from config import *
from article_processor import (
    _candidate_date_obj,
    _canonical_candidate_region,
    _contains_any_term,
    _contains_taiwan_reference,
    _date_from_url_path,
    _date_sort_key,
    _dedupe_route_line_tokens,
    _dedupe_titles_conflict_on_entities,
    _domain_from_url,
    _effective_source_url,
    _extract_complete_url,
    _extract_domain_hint,
    _host_matches,
    _is_valid_news_url,
    _normalize_source_domain,
    _original_source_domain,
    _prefetch_candidate_article,
    _quality_rank,
    _shorten,
    _source_tier_rank,
    _strip_source_name_noise,
)

LOW_VALUE_POLICY_TERMS = [
    "holiday service", "weekend service", "weekender", "service advisory",
    "travel information", "trip result", "route page", "take transit",
    "RouteNumber", "route number", "minor delay", "detour", "service alert",
    "trip planner", "schedule change", "planned service change",
    "bus replacement", "shuttle bus", "customer notice", "service update",
    "temporary stop closure", "take the ttc", "route information", "public preview",
    "fare table", "game day", "event traffic", "escalator guide", "escalator information",
    "station entrance", "station access information", "accessibility policy",
    "accessibility service", "barrier-free", "construction work",
    "schedule", "timetable", "bus route", "bus schedule", "anniversary",
    "celebration", "campaign", "promotion", "promotional",
    "搭乘資訊", "假日服務", "週末服務", "服務提醒", "旅客資訊更新",
    "活動搭乘", "旅客資訊", "路線資訊", "票價表", "球賽", "活動交通",
    "電扶梯導引", "電扶梯資訊", "出入口資訊", "車站出入口",
    "無障礙政策", "無障礙服務", "施工通知", "工程通知",
    "時刻表", "班表", "公車路線", "公車班表", "週年", "周年",
    "紀念活動", "宣傳", "促銷",
]

HIGH_VALUE_POLICY_TERMS = [
    "fare", "afc", "ticketing", "headway", "special train", "extra train",
    "crowd control", "station control", "passenger information system",
    "trial operation", "system conversion", "asset renewal", "maintenance",
    "engineering works", "track renewal", "rail replacement", "signal testing",
    "system testing", "station equipment", "equipment upgrade",
    "fare adjustment", "major event", "event service", "station access control",
    "platform crowding", "passenger flow control",
    "票價", "票務", "班距", "加班車", "人流管制", "車站管制", "試營運",
    "系統轉換", "資產更新", "維修", "工程",
]

ACCIDENT_SIGNAL_TERMS = [
    "derailment", "collision", "fire", "smoke", "power outage", "signal failure",
    "service suspension", "disruption", "platform screen door", "train door",
    "death", "fatal", "killed", "injury", "injured", "crash", "hit", "rammed",
    "suspended", "heat damage", "damage", "barrier", "platform barrier",
    "entgleist", "Verletzte", "Unfall", "Zusammenstoß",
    "出軌", "脫軌", "追撞", "火災", "冒煙", "停駛", "供電異常", "號誌異常",
    "通訊異常", "月臺門", "車門異常", "死亡", "受傷", "撞擊", "營運中斷",
    "月臺屏障", "設備損壞",
]

SAFETY_INCIDENT_DETAIL_TERMS = [
    "derailment", "collision", "death", "fatal", "killed", "injury", "injured",
    "crash", "hit", "rammed", "disruption", "suspended", "heat damage",
    "damage", "platform barrier", "entgleist", "Verletzte", "Unfall",
    "Zusammenstoß", "死亡", "受傷", "撞擊", "出軌", "脫軌", "營運中斷",
    "停駛", "月臺屏障", "設備損壞",
]

LOW_VALUE_OFFICIAL_NOTICE_TERMS = [
    "construction notice", "contract documents holders list", "bid number",
    "open date", "take the ttc", "match", "stadium", "fireworks",
    "event service", "public preview", "route information", "travel information",
    "service advisory", "platform ilaa", "symbol character", "mascot",
    "character", "fare table", "game day", "event traffic", "escalator guide",
    "escalator information", "station entrance", "station access information",
    "accessibility policy", "accessibility service", "barrier-free", "construction work",
    "schedule", "timetable", "bus route", "bus schedule", "anniversary",
    "celebration", "campaign", "promotion", "open day",
    "活動搭乘", "花火大會", "加開列車", "觀賽", "吉祥物", "角色",
    "標案文件持有人", "施工通知", "旅客資訊", "路線資訊", "票價表",
    "球賽", "活動交通", "電扶梯導引", "電扶梯資訊", "出入口資訊", "車站出入口",
    "無障礙政策", "無障礙服務", "工程通知",
    "時刻表", "班表", "公車路線", "公車班表", "週年", "周年",
    "紀念活動", "宣傳", "促銷", "開放日",
]

NON_TECH_NEWS_EXCLUDE_TERMS = [
    "extra train", "special train", "theme train", "themed train",
    "character train", "stamp rally", "digital stamp", "passenger event",
    "anniversary", "celebration", "campaign", "promotion", "promotional",
    "open day", "schedule", "timetable", "bus route", "bus schedule",
    "road maintenance", "road works", "road construction", "road accident", "pothole", "bus",
    "autonomous bus", "self-driving bus", "tunnel boring machine farewell",
    "tbm farewell", "tbm removal", "tbm demobilization", "mascot", "character",
    "加開列車", "主題列車", "角色列車", "數位集章", "集章活動",
    "週年", "周年", "紀念活動", "宣傳", "促銷", "開放日",
    "時刻表", "班表", "公車路線", "公車班表",
    "一般旅客活動", "旅客活動", "道路維護", "道路施工", "道路坑洞", "道路事故",
    "巴士", "公車", "自動駕駛巴士", "吉祥物", "角色",
    "隧道鑽掘機告別", "潛盾機告別", "潛盾機撤場",
]

NON_ACCIDENT_CONTEXT_TERMS = [
    "tunnel boring machine farewell", "tbm farewell", "road maintenance",
    "tbm removal", "tbm demobilization", "road works", "road construction",
    "road accident", "traffic accident", "pothole", "strike date",
    "roadblock", "police roadblock", "law enforcement", "enforcement case",
    "planned weekend closure", "weekend closure", "maintenance closure",
    "routine maintenance", "testing progress", "engineering milestone",
    "strike dates", "strike notice", "罷工日期", "罷工日期公告",
    "道路維護", "道路施工", "道路坑洞", "道路事故", "一般道路事故",
    "道路路障", "執法案件", "預定週末封閉", "週末封閉", "例行維修",
    "一般測試進度", "工程里程碑", "隧道鑽掘機告別", "潛盾機告別", "潛盾機撤場",
]

URBAN_RAIL_INCIDENT_CONTEXT_TERMS = [
    "metro", "subway", "underground", "tram", "light rail", "lrt", "mrt",
    "urban rail", "funicular", "station", "platform", "train", "track", "railcar",
    "metro train", "subway train", "捷運", "地鐵", "都市軌道", "輕軌",
    "車站", "月臺", "月台", "列車", "軌道", "軌道車輛",
]

GENERAL_RAIL_EXCLUDE_TERMS = [
    "lirr", "long island rail road", "commuter rail", "regional rail",
    "intercity rail", "amtrak", "national rail",
]

PROCUREMENT_LIST_NOTICE_TERMS = [
    "contract documents holders list", "bid number", "open date", "標案文件持有人",
]

PROJECT_ONLY_ACTION_TERMS = [
    "contract", "contract awarded", "awarded contract", "wins contract", "won contract",
    "selected contractor", "contractor selected", "procurement", "procure", "purchase order",
    "order placed", "orders", "ordered", "delivery", "delivered", "train delivery",
    "construction begins", "construction started", "construction start", "groundbreaking",
    "feasibility study", "feasibility", "project approved", "project approval",
    "project milestone", "construction progress", "tender", "bid awarded", "contract signed",
    "project launch", "開工", "動工", "可行性研究", "工程進度", "工程里程碑", "專案核准",
    "得標", "採購", "訂購", "交車", "交付", "投標", "招標",
]

SUBSTANTIVE_TECHNICAL_DETAIL_TERMS = [
    "system architecture", "technical architecture", "moving-block", "moving block",
    "fixed-block", "fixed block", "goa", "driverless", "unattended train operation",
    "automatic train operation", "virtual coupling", "train separation", "headway",
    "capacity increase", "increasing capacity", "interface", "interoperability",
    "system integration", "integrated with", "fail-safe", "redundancy", "control logic",
    "technical method", "technical specification", "technical parameter", "performance test",
    "acceptance test", "validation", "validated", "verification", "demonstration",
    "demonstrated", "pilot uses", "onboard sensor", "onboard sensors", "condition monitoring",
    "predictive maintenance", "fault detection", "continuous monitoring", "non-destructive",
    "silicon carbide", "sic traction inverter", "traction inverter", "regenerative braking",
    "energy consumption", "energy efficiency", "energy saving", "reducing energy",
    "lightweight", "composite", "battery", "fire-resistant", "fire resistant",
    "low-friction", "low friction", "wear reduction", "noise reduction", "vibration reduction",
    "service life", "life-cycle", "lifecycle", "thermal", "heat recovery", "carbon reduction",
    "碳纖維", "複合材料", "低摩擦", "阻燃", "耐火", "節能", "能耗", "牽引變流器",
    "感測器", "感測", "狀態監測", "預測性維護", "故障偵測", "技術架構", "介面整合",
    "技術參數", "性能改善", "效能提升", "驗證", "示範", "試驗內容",
]

SUBSTANTIVE_POLICY_DETAIL_TERMS = [
    "headway", "capacity", "crowd control", "station control",
    "passenger flow control", "afc", "ticketing", "fare gate",
    "system conversion", "asset renewal", "engineering works",
    "signal testing", "system testing", "station equipment", "equipment upgrade",
    "班距", "容量", "人流管制", "車站管制", "旅客流量", "AFC", "票務系統",
    "票閘", "系統轉換", "資產更新", "號誌測試", "系統測試", "車站設備",
    "設備更新", "營運規劃",
]

STRONG_TECHNICAL_DETAIL_TERMS = [
    "cbtc", "train control", "signalling", "signaling", "signal system",
    "rolling stock", "trainset", "power supply", "traction power", "substation",
    "communications", "telecom", "cybersecurity", "api", "data governance",
    "platform screen door", "platform doors", "psd", "afc", "depot",
    "maintenance", "condition monitoring", "monitoring equipment",
    "video analytics", "ai image analysis", "system integration", "testing",
    "commissioning", "system verification",
    "號誌", "信號", "列控", "車輛", "供電", "牽引", "變電站", "通訊",
    "資安", "資料治理", "月臺門", "月台門", "票務系統", "機廠", "維修監測",
    "AI 影像分析", "影像分析", "系統整合", "測試驗證",
]

MEDIUM_TECHNICAL_DETAIL_TERMS = [
    "station equipment", "passenger information", "operations control",
    "operational control", "control centre", "control center", "maintenance facility",
    "vehicle introduction", "fleet introduction", "system upgrade", "equipment improvement",
    "safety management", "asset management", "station systems", "platform equipment",
    "escalator", "elevator", "air conditioning", "hvac", "passenger information system",
    "ai", "image analysis", "video analytics", "monitoring center", "safety center",
    "control room", "operations control center", "maintenance depot",
    "車站設備", "旅客資訊", "營運監控", "行控", "控制中心", "維修設施",
    "車輛導入", "系統更新", "設備改善", "營運安全管理", "資產管理",
    "電扶梯", "電梯", "空調", "月臺設備", "月台設備", "旅客資訊系統",
    "影像分析", "監控中心", "安全中心", "行控中心", "維修機廠",
]

WEEKLY_BACKFILL_ALLOWED_TERMS = [
    "station equipment", "escalator", "elevator", "air conditioning", "hvac",
    "platform equipment", "passenger information system", "ai", "image analysis",
    "video analytics", "data", "monitoring", "maintenance support",
    "operations control center", "control centre", "control center", "safety center",
    "monitoring center", "maintenance facility", "maintenance depot",
    "vehicle introduction", "fleet introduction", "rolling stock introduction",
    "safety management", "operations safety", "operational safety",
    "車站設備", "電扶梯", "電梯", "空調", "月臺設備", "月台設備",
    "旅客資訊系統", "AI", "影像", "資料", "監控", "維修輔助",
    "營運安全", "控制中心", "安全中心", "監控中心", "維修設施",
    "維修機廠", "車輛導入",
]

LOW_REPORT_VALUE_TERMS = [
    "passenger praised", "passenger praises", "traveller praised", "traveler praised",
    "clean and safe", "low fare", "cheap fare", "social media", "viral video",
    "youtube", "tiktok", "instagram", "personal experience", "first-time rider",
    "reviewed the metro", "lost property", "delay certificate", "mascot",
    "stamp rally", "theme train", "themed train", "road maintenance",
    "road works", "road construction", "pothole", "travel information",
    "weekend service", "weekend travel", "tourism information", "tbm farewell",
    "tbm removal", "tbm demobilization", "contract documents holders list",
    "旅客稱讚", "乘客稱讚", "乾淨安全", "低票價", "票價便宜", "社群影片",
    "個人經驗", "旅客心得", "失物招領", "延誤證明", "吉祥物", "數位集章",
    "主題列車", "道路維護", "道路施工", "道路坑洞", "旅遊資訊",
    "週末搭乘提醒", "潛盾機告別", "潛盾機撤場", "標案文件持有人",
    "passengers praise", "riders praise", "rider praised", "commuters praise",
    "praised the metro", "praises the metro", "lauds metro", "anniversary",
    "celebration", "campaign", "promotion", "promotional", "tour package",
    "乘客大讚", "旅客大讚", "大讚捷運", "稱讚捷運", "週年", "周年",
    "紀念活動", "宣傳", "促銷", "旅遊套票",
]

FINANCIAL_MARKET_TERMS = [
    "yahoo finance", "finance.yahoo.com", "stock price", "share price",
    "stock market", "market cap", "trading", "ticker", "nasdaq", "nyse",
    "earnings", "quarterly results", "financial results", "investor",
    "investment analysis", "analyst rating", "price target",
    "股價", "股票", "股市", "財報", "營收", "投資分析", "投資人",
    "目標價", "券商", "分析師評級",
]

PROPERTY_OR_CAMPUS_DEVELOPMENT_TERMS = [
    "property development", "real estate", "land development", "campus development",
    "university campus", "commercial development", "shopping mall", "housing development",
    "white shek kok", "pak shek kok", "station-area development",
    "土地開發", "物業開發", "車站周邊開發", "校園發展", "校園開發",
    "白石角", "大學校園", "商場", "住宅開發",
]

GENERIC_TEST_WITHOUT_TECH_TERMS = [
    "resume weekend testing", "weekend testing resumes", "testing resumes",
    "restore weekend testing", "restored weekend testing", "trial runs resume",
    "恢復週末測試", "週末測試恢復", "恢復測試", "測試恢復", "試運轉恢復",
]

EQUIPMENT_FAILURE_TERMS = [
    "signal failure", "signalling failure", "signaling failure", "signal fault",
    "power failure", "power outage", "communications failure", "communication fault",
    "platform screen door failure", "platform door fault", "train door failure",
    "switch failure", "points failure", "afc failure", "ticketing system failure",
    "equipment failure", "equipment fault",
    "號誌故障", "號誌異常", "信號故障", "信號異常", "供電故障", "供電異常",
    "通訊故障", "通訊異常", "月臺門故障", "月台門故障", "車門故障",
    "轉轍器故障", "道岔故障", "票務系統故障", "自動收費故障", "設備故障",
]

ENGINEERING_MILESTONE_ONLY_TERMS = [
    "tunnel boring machine", "tbm", "tbm removal", "tbm demobilization",
    "tbm breakthrough", "construction milestone", "civil works complete",
    "construction progress", "site handover", "boring machine leaves",
    "隧道鑽掘機", "潛盾機", "潛盾機撤場", "潛盾機離場", "隧道鑽掘機離場",
    "工程里程碑", "施工進度", "土建完工", "工地移交",
]

SECURITY_OR_CRIME_TERMS = [
    "knife", "stabbing", "fight", "assault", "attack", "murder", "homicide",
    "shooting", "pushed", "shoved", "pepper spray", "tear gas", "irritant gas",
    "security incident", "police incident", "police investigation", "crime",
    "passenger dispute", "fare evasion", "roadblock", "law enforcement",
    "刀具", "持刀", "刺傷", "鬥毆", "打架", "攻擊", "謀殺", "兇殺", "槍擊",
    "推落", "推下", "推擠", "刺激性氣體", "催淚氣體", "治安事件", "警方事件",
    "警方調查", "刑事案件", "旅客糾紛", "逃票", "道路路障", "執法案件",
]

MAJOR_SECURITY_RAIL_IMPACT_TERMS = [
    "hit by train", "struck by train", "train collision", "train collided",
    "train derailment", "train derailed", "track intrusion", "on the tracks",
    "signal failure", "signalling failure", "signaling failure", "power failure",
    "power outage", "train door", "platform screen door", "platform door",
    "rail fire", "subway fire", "metro fire", "station fire", "train fire",
    "derailment", "derailed", "collision", "collided", "evacuation", "evacuated",
    "service suspended", "service suspension", "major disruption", "station evacuated",
    "train evacuated", "emergency response", "security lockdown",
    "列車撞擊", "列車碰撞", "列車相撞", "列車出軌", "列車脫軌", "軌道侵入",
    "號誌故障", "信號故障", "供電故障", "供電中斷", "車門", "月臺門", "月台門",
    "火災", "出軌", "脫軌", "碰撞", "相撞", "疏散", "停駛", "營運中斷",
    "重大中斷", "車站疏散", "列車疏散", "緊急應變", "封鎖車站",
]

CORE_METRO_TECHNICAL_TERMS = [
    "rolling stock", "railcar", "trainset", "vehicle equipment", "depot equipment",
    "maintenance equipment", "signalling", "signaling", "signal system", "train control",
    "cbtc", "ato", "atp", "ats", "operations control", "operation control",
    "control centre", "control center", "occ", "traction power", "power supply",
    "substation", "regenerative braking", "energy storage", "energy management",
    "communications", "telecom", "radio", "wireless", "data transmission",
    "platform screen door", "platform door", "psd", "afc", "fare gate",
    "station equipment", "hvac", "air conditioning", "ventilation", "fire system",
    "environmental control", "escalator", "elevator", "condition monitoring",
    "fault diagnosis", "predictive maintenance", "video analytics", "image recognition",
    "ai image", "system integration", "system assurance", "rams", "safety verification",
    "interface management", "ot security", "ics security", "cybersecurity",
    "commissioning", "system testing", "technical verification",
    "電聯車", "車輛設備", "機廠設備", "維修設備", "號誌", "信號", "列車控制",
    "列控", "行車監控", "行控中心", "牽引供電", "一般電力", "變電站", "再生煞車",
    "儲能", "能源管理", "通訊系統", "無線通訊", "資料傳輸", "月臺門", "月台門",
    "自動收費", "票務系統", "票閘", "車站機電", "空調", "通風", "消防",
    "環境控制", "電扶梯", "電梯", "無障礙機電", "狀態監測", "故障診斷",
    "預測性維護", "影像辨識", "系統整合", "系統保證", "安全驗證", "介面管理",
    "資安", "工控資安", "系統測試", "技術驗證", "投入營運",
]

TECHNICAL_IMPLEMENTATION_TERMS = [
    "introduce", "introduced", "deploy", "deployed", "roll out", "upgrade",
    "renewal", "replace", "replacement", "retrofit", "modernisation", "modernization",
    "commission", "commissioning", "enter service", "entered service", "launch",
    "trial", "pilot", "test", "testing", "verification", "validated", "validation",
    "installation", "integrated", "integration", "improvement", "new system",
    "new equipment", "導入", "啟用", "部署", "升級", "更新", "汰換",
    "改造", "現代化", "試辦", "試行", "測試", "驗證", "改善", "新系統",
    "新設備", "安裝", "整合", "投入營運", "正式營運",
]

LOW_IMPACT_ACCIDENT_TERMS = [
    "animal on tracks", "dog on tracks", "cat on tracks", "bird on tracks",
    "passenger dispute", "minor altercation", "trespasser", "small animal",
    "動物落軌", "犬隻落軌", "貓落軌", "小動物", "旅客糾紛", "輕微衝突",
]

HIGH_IMPACT_ACCIDENT_TERMS = [
    "third rail", "power rail", "platform screen door", "platform barrier",
    "service suspension", "major disruption", "investigation", "safety review",
    "brake failure", "switch failure", "points failure", "power outage",
    "第三軌", "供電軌", "月臺門", "月臺屏障", "停駛", "重大中斷",
    "制度檢討", "安全檢討", "煞車失效", "轉轍器", "供電異常",
]

REPORT_SELECTION_DEBUG_DEFAULT = {
    "strict_selected_count": 0,
    "borderline_added_count": 0,
    "B_added_count": 0,
    "incident_search_raw_count": 0,
    "incident_gate_pass_count": 0,
    "incident_selected_count": 0,
    "incident_coverage_warning": False,
    "incident_coverage_reason": "",
    "borderline_candidates": [],
    "shortfall_before_backfill": 0,
    "shortfall_after_backfill": 0,
    "backfill_reason": "",
    "B_backfill_triggered": False,
    "B_backfill_cap": 0,
    "B_backfill_considered_count": 0,
    "B_backfill_appended_ids": [],
    "B_backfill_append_stage": "",
    "duplicate_event_records": [],
    "operational_coverage_triggered": False,
    "operational_coverage_added": False,
    "operational_coverage_category": "",
    "operational_coverage_replaced_id": "",
}

URBAN_RAIL_MODE_TERMS.extend(["metros"])

URBAN_RAIL_UNAMBIGUOUS_MODE_TERMS.extend(["metros"])

TECH_NEWS_REQUIRED_TERMS.extend([
    "ato", "atp", "ats", "metro rail", "light rail vehicle", "light rail vehicles", "LRV", "LRVs", "train cars",
    "fleet renewal", "fleet replacement", "overhaul", "energy storage",
    "regenerative braking", "power system", "energy management",
    "automatic fare collection", "contactless payment", "tap to pay",
    "scan to pay", "tap or scan to pay", "open-loop payment", "open loop payment",
    "qr payment", "biometric fare payment", "validator", "ticketing system",
    "handheld inspection device", "payment system integration", "compatibility",
    "passenger information system", "platform screen door", "accessibility upgrade",
    "made accessible", "fire protection", "fire safety", "station systems",
    "ventilation", "fleet life-cycle management", "life-cycle management services",
    "maintenance services", "track renewal", "lubricator replacement",
    "track lubrication", "operations and maintenance centre", "operations and maintenance center",
    "omc", "wheel lathe", "axle counter", "axle counters", "life cycle management", "life cycle management services",
])

TITLE_TECHNICAL_ACTION_TERMS.extend([
    "implement", "implemented", "implementation", "activated", "activate",
    "go into service", "expanded", "expansion", "upgraded", "upgrades",
    "modernise", "modernize", "modernisation", "modernization", "procure",
    "procurement", "design services", "life-cycle management services",
    "life cycle management services", "overhaul",
    "made accessible", "tap or scan to pay", "unveils", "unveiled",
    "confirms", "boost capacity", "boosts capacity",
])

CORE_METRO_TECHNICAL_TERMS.extend([
    "ato", "atp", "ats", "light rail vehicle", "light rail vehicles", "LRV", "LRVs", "train cars", "new train",
    "two-car sets", "two car sets", "car sets", "automated metro", "automated metros",
    "line modernization", "line modernisation", "metro modernization", "metro modernisation",
    "modernization", "modernisation", "life cycle management", "life cycle management services",
    "fleet renewal", "fleet replacement", "overhaul", "power system",
    "energy storage", "regenerative braking", "energy management",
    "automatic fare collection", "contactless payment", "tap to pay",
    "scan to pay", "tap or scan to pay", "open-loop payment", "open loop payment",
    "qr payment", "biometric fare payment", "validator", "ticketing system",
    "handheld inspection device", "payment system integration", "system interface problem",
    "ticketing outage", "rollout flaw", "passenger information system",
    "accessibility upgrade", "made accessible", "fire protection", "fire safety",
    "station systems", "ventilation", "fleet life-cycle management",
    "life-cycle management services", "maintenance services", "track renewal",
    "lubricator replacement", "track lubrication", "operations and maintenance centre",
    "operations and maintenance center", "omc", "wheel lathe", "axle counter", "axle counters",
])

TECHNICAL_IMPLEMENTATION_TERMS.extend([
    "implement", "implemented", "implementation", "activate", "activated",
    "go into service", "rollout", "expanded", "expansion", "upgraded",
    "upgrades", "procure", "procurement", "order", "ordered", "design services",
    "life-cycle management services", "life cycle management services", "overhaul",
    "made accessible", "tap or scan to pay",
    "unveils", "unveiled", "confirms", "boost capacity", "boosts capacity",
])

STRONG_TECHNICAL_DETAIL_TERMS.extend([
    "automatic fare collection", "contactless payment", "tap to pay",
    "scan to pay", "tap or scan to pay", "biometric fare payment",
    "validator", "ticketing system", "fare gate", "handheld inspection device",
    "payment system integration", "passenger information system",
    "light rail vehicle", "light rail vehicles", "LRV", "LRVs", "train cars", "two-car sets", "two car sets",
    "automated metros", "line modernization", "line modernisation",
    "modernization", "modernisation", "fleet renewal", "fleet replacement",
    "life-cycle management services", "life cycle management services", "fire protection", "fire safety",
    "track renewal", "operations and maintenance centre", "operations and maintenance center",
    "omc", "wheel lathe", "axle counter", "axle counters",
])

MEDIUM_TECHNICAL_DETAIL_TERMS.extend([
    "contactless payment", "tap to pay", "scan to pay", "tap or scan to pay",
    "open-loop payment", "qr payment", "biometric fare payment", "validator",
    "ticketing system", "fare gate", "accessibility upgrade", "made accessible",
    "fire protection", "fire safety", "track renewal", "wheel lathe",
])

STRICT_HIGH_VALUE_POLICY_TEXT_TERMS = [
    "fare reform", "payment policy", "service restructure", "service restructuring",
    "headway", "service frequency", "operating hours", "capacity", "trial operation",
    "system conversion", "line closure", "full line closure", "major closure",
    "maintenance closure", "long closure", "seven week closure", "seven-week closure",
    "accessibility plan", "fleet deployment", "budget approval", "governance decision",
    "replacement bus service", "alternative transport", "major engineering works",
    "票務制度", "支付政策", "班距", "營運時間", "容量", "試營運", "系統轉換",
    "全線封閉", "多站封閉", "無障礙改善計畫", "預算核准", "治理決策",
]

MAJOR_ACCIDENT_SEVERITY_TERMS = [
    "fatal", "death", "died", "killed", "serious injury", "serious injuries",
    "multiple injuries", "multiple injured", "hospitalized", "hospitalised",
    "derailment", "derailed", "train-to-train collision", "trains collided",
    "major fire", "smoke filled", "evacuated", "evacuation", "mass evacuation",
    "service suspended", "service suspension", "long suspension", "major disruption",
    "power outage", "signal failure", "signalling failure", "communications failure",
    "formal investigation", "safety investigation", "investigation launched",
    "safety review", "systemic failure", "repeated incident",
    "死亡", "多人重傷", "多人受傷", "多人送醫", "重傷", "送醫", "出軌", "脫軌",
    "列車碰撞", "列車相撞", "重大火災", "大量疏散", "長時間停駛", "大範圍停駛",
    "正式調查", "事故調查", "安全調查", "制度檢討", "系統性故障", "反覆發生",
    "entgleist", "entgleisung", "verletzte", "déraillement", "blessés",
    "descarrilamiento", "heridos", "сход с рельсов", "пострадал",
    "脱線", "負傷", "탈선", "부상", "脱轨", "受伤",
]

MAJOR_ACCIDENT_DIRECT_TERMS = [
    "derailment", "derailed", "train-to-train collision", "trains collided",
    "collision", "collided", "crash", "major fire", "train fire", "station fire",
    "mass evacuation", "official investigation", "formal investigation",
    "safety investigation", "investigation launched", "死亡", "重傷", "多人受傷",
    "多人重傷", "出軌", "脫軌", "列車碰撞", "列車相撞", "重大火災", "大量疏散",
    "正式調查", "事故調查", "安全調查",
]

POST_INCIDENT_POLICY_TERMS = [
    "after the accident", "after collision", "following the incident", "in response to",
    "safety improvement", "improve safety", "safety measures", "safety plan",
    "safety review", "policy response", "事故後", "事故後續", "安全改善", "安全措施",
    "安全提升", "改善計畫", "改善方案", "檢討", "政策回應", "治理措施",
]

SINGLE_PERSON_INCIDENT_TERMS = [
    "person struck by train", "person hit by train", "struck by a train",
    "hit by a train", "trespass", "trespasser", "police investigation",
    "medical emergency", "woman struck", "woman hit", "man struck", "man hit",
    "passenger struck", "passenger hit", "一人遭列車撞擊", "單一人員",
    "闖入軌道", "醫療緊急事件", "警方調查",
]

OFFICIAL_TRANSPORT_SAFETY_INVESTIGATION_TERMS = [
    "national transportation safety board", "ntsb", "transportation safety board",
    "transport safety board", "rail accident investigation branch", "raib",
    "official transport safety investigation", "official railway investigation",
    "formal rail safety investigation", "運輸安全委員會", "運安會",
    "官方運輸安全調查", "鐵路事故調查機構",
]

SHORT_TERM_SERVICE_NOTICE_TERMS = [
    "shortened operating hours", "operating hours shortened", "shorten operating hours",
    "reduced operating hours", "service closure",
    "maintenance advisory", "temporary timetable", "temporary station closure",
    "station closure", "one-day closure", "one day closure", "service advisory",
    "temporary service change", "limited service hours", "縮短營運時間",
    "縮短營業時間", "維修公告", "臨時時刻表", "臨時班表", "臨時封站",
    "車站臨時關閉", "單日停駛", "短期停駛",
]

SHORT_TERM_TIME_SIGNALS = [
    "temporary", "one-day", "one day", "for one day", "this weekend",
    "weekend", "maintenance", "repair", "repairs", "advisory", "on july",
    "on monday", "on tuesday", "on wednesday", "on thursday", "on friday",
    "on saturday", "on sunday", "臨時", "單日", "一天", "本週末", "週末",
    "維修", "修繕", "公告",
]

LOW_VALUE_CEREMONIAL_TERMS = [
    "donation", "donates", "donated", "csr", "corporate social responsibility",
    "college donation", "award", "awards", "award ceremony", "awards ceremony", "ceremony",
    "education outreach", "educational outreach", "community outreach",
    "捐贈", "企業社會責任", "頒獎", "典禮", "教育推廣", "校園推廣",
]

FORMAL_ENGINEERING_EVENT_TERMS = [
    "contract awarded", "awarded contract", "awards contract", "award of a contract",
    "contract signing", "project launch",
    "installation begins", "installation started", "construction begins",
    "commissioned", "entered service", "goes into service", "deployed",
    "system integration", "engineering design", "testing programme",
    "testing program", "正式工程", "工程開工", "投入營運", "系統整合",
]

LOW_IMPACT_ROAD_INTERFACE_TERMS = [
    "one injured", "minor injury", "minor injuries", "slight injury", "slightly injured",
    "short delay", "brief delay", "no derailment", "no major damage",
    "一人受傷", "一人輕傷", "輕傷", "短暫延誤", "未出軌", "無重大損壞",
]

ROAD_INTERFACE_ACCIDENT_TERMS = [
    "car", "truck", "vehicle", "motorist", "driver", "pedestrian", "cyclist",
    "intersection", "road", "roadway", "level crossing",
    "汽車", "卡車", "車輛", "駕駛", "行人", "自行車", "路口", "道路", "平交道",
]

DISPUTE_SIGNAL_TERMS = [
    "strike", "industrial action", "union dispute", "labor dispute", "labour dispute",
    "lawsuit", "court order", "judicial order", "contract dispute", "procurement dispute",
    "tender dispute", "budget dispute", "cost overrun", "project delay", "arbitration",
    "organized protest", "organised protest", "service disruption",
    "罷工", "工業行動", "工會爭議", "勞資爭議", "訴訟", "司法命令",
    "合約爭議", "採購爭議", "招標爭議", "預算爭議", "成本超支",
    "工程延誤", "組織性抗議", "服務中斷", "仲裁",
]

DISPUTE_ACTOR_TERMS = [
    "union", "workers", "employees", "contractor", "supplier", "procurement authority",
    "government", "operator", "court", "regulator", "auditor", "council",
    "protesters", "advocacy group", "工會", "勞工", "員工", "承包商", "供應商",
    "採購機關", "政府", "營運機構", "法院", "監管機關", "稽核機關", "議會",
    "抗議團體", "權益團體",
]

DISPUTE_IMPACT_TERMS = [
    "service", "delay", "delayed", "disruption", "suspended", "cost", "budget",
    "contract", "procurement", "project", "construction", "schedule", "governance",
    "服務", "延誤", "延宕", "中斷", "停駛", "成本", "預算", "合約", "採購",
    "專案", "工程", "工期", "治理",
]

DISPUTE_SECONDARY_IMPACT_TERMS = [
    "service", "delay", "delayed", "disruption", "suspended", "cost", "contract",
    "procurement", "project", "construction", "schedule", "governance", "capacity",
    "服務", "延誤", "延宕", "中斷", "停駛", "成本", "合約", "採購", "專案",
    "工程", "工期", "治理", "運能",
]

DISPUTE_SECONDARY_SIGNAL_TERMS = [
    term for term in DISPUTE_SIGNAL_TERMS if term not in {"project delay", "工程延誤"}
]

POLICY_DOMINANT_TERMS = [
    "fare reform", "fare adjustment", "fare policy", "operating hours", "service change",
    "service restructuring", "line opening", "line extension", "capacity increase",
    "route restructuring", "budget approval", "funding approval", "regulatory approval",
    "government approved", "approved by the government", "policy decision", "governance",
    "票價改革", "票價調整", "營運時間", "服務調整", "服務重整", "路線延伸", "運能提升",
    "路線重整", "預算核准", "經費核定", "法規核准", "政府核准", "政策決定", "治理",
]

HIGH_VALUE_POLICY_GATE_TERMS = STRICT_HIGH_VALUE_POLICY_TEXT_TERMS + [
    "new line opening", "new system opening", "service begins", "fleet replacement plan",
    "fleet renewal plan", "station group", "system upgrade", "signal upgrade",
    "track upgrade", "route restructuring", "major service change", "fare reform",
    "fare adjustment", "fare policy", "operating hours", "service restructuring",
    "line extension", "capacity increase", "budget approval", "funding approval",
    "regulatory approval", "government approved", "governance",
    "新線通車", "新系統通車", "服務重整", "重大服務調整", "車隊汰換計畫",
    "車隊更新計畫", "路線重整", "系統升級", "號誌升級", "軌道升級", "票價改革",
    "票價調整", "營運時間", "服務調整", "路線延伸", "運能提升", "預算核准", "政府核准",
]

CANONICAL_TAG_PATTERNS: list[tuple[str, list[str]]] = [
    ("derailment", ["derailment", "derailed", "entgleisung", "entgleist", "déraillement", "descarrilamiento", "сход с рельсов", "脱線", "탈선", "脫軌", "脱轨", "出軌"]),
    ("collision", ["collision", "collided", "kollision", "colisión", "столкновение", "衝突", "충돌", "碰撞", "相撞"]),
    ("fire", ["fire", "brand", "incendie", "incendio", "пожар", "火災", "火灾", "화재"]),
    ("evacuation", ["evacuation", "evacuated", "evakuierung", "évacuation", "evacuación", "эвакуация", "避難", "대피", "疏散"]),
    ("fatality", ["fatal", "killed", "death", "tote", "morts", "muertos", "погиб", "死亡", "사망"]),
    ("injury", ["injured", "verletzte", "blessés", "heridos", "пострадал", "負傷", "부상", "受傷", "受伤"]),
    ("service_suspension", ["shutdown", "service suspended", "service suspension", "betrieb eingestellt", "interruption", "suspensión", "остановка движения", "運休", "운행중단", "停駛", "停驶"]),
    ("investigation", ["investigation", "inquiry", "untersuchung", "enquête", "investigación", "расследование", "調査", "조사", "調查", "调查"]),
    ("order", ["ordered", "order", "bestellen", "commande", "pedido", "заказ", "採購", "訂購"]),
    ("enter service", ["enter service", "entered service", "go into service", "inbetriebnahme", "mise en service", "puesta en servicio", "ввод", "投入營運", "投入运营"]),
    ("modernization", ["modernization", "modernisation", "modernize", "modernise", "modernized", "modernised", "modernizing", "modernising", "modernisierung", "modernización", "modernização", "modernizzazione", "модернизация", "現代化"]),
    ("upgrade", ["upgrade", "upgraded", "upgrades", "renewal", "replacement", "升級", "更新", "汰換"]),
    ("deployment", ["deploy", "deployed", "deployment", "rollout", "roll out", "導入", "部署"]),
    ("fire protection", ["fire protection", "fire safety", "brandschutz", "protection incendie", "protezione antincendio", "消防"]),
    ("contactless payment", ["contactless payment", "tap to pay", "scan to pay", "kontaktloses bezahlen", "paiement sans contact", "pago sin contacto", "pagamento sem contacto", "非接触決済", "非接觸支付"]),
    ("biometric payment", ["biometric payment", "biometric fare", "biometrische zahlung", "биометрическая оплата", "生物辨識支付"]),
]

OPERATOR_DOMAIN_KEYS = {
    "mta.info": "mta",
    "wmata.com": "wmata",
    "ttc.ca": "ttc",
    "translink.ca": "translink",
    "tfl.gov.uk": "tfl",
    "ratp.fr": "ratp",
    "lta.gov.sg": "lta",
    "smrt.com.sg": "smrt",
    "mtr.com.hk": "mtr",
    "seoulmetro.co.kr": "seoulmetro",
    "tokyometro.jp": "tokyometro",
    "metro.tokyo.lg.jp": "tokyo-metropolitan-government",
    "metro-madrid.es": "metro-madrid",
    "tmb.cat": "tmb",
    "wienerlinien.at": "wiener-linien",
    "sl.se": "sl",
    "cph.dk": "copenhagen-metro",
    "rta.ae": "rta-dubai",
    "soundtransit.org": "sound-transit",
}

OPERATOR_TEXT_KEYS = [
    ("tokyometro", ["tokyo metro", "東京メトロ"]),
    ("seoulmetro", ["seoul metro", "서울교통공사"]),
    ("mtr", ["mtr", "港鐵"]),
    ("lta", ["lta"]),
    ("smrt", ["smrt"]),
    ("tfl", ["tfl", "transport for london"]),
    ("ratp", ["ratp"]),
    ("wmata", ["wmata"]),
    ("ttc", ["ttc"]),
    ("translink", ["translink"]),
    ("mta", ["mta", "nyct"]),
    ("cta", ["cta"]),
    ("bart", ["bart"]),
    ("bvg", ["bvg", "berliner verkehrsbetriebe"]),
    ("wiener-linien", ["wiener linien"]),
    ("copenhagen-metro", ["copenhagen metro"]),
    ("metro-madrid", ["metro de madrid", "madrid metro"]),
]

EVENT_LOCATION_TERMS = [
    "tokyo", "osaka", "seoul", "singapore", "hong kong", "sydney", "melbourne",
    "london", "paris", "berlin", "munich", "new york", "washington", "chicago", "austin",
    "toronto", "vancouver", "houston", "madrid", "barcelona", "amsterdam", "rotterdam",
    "basel", "zurich", "leipzig", "adlershof", "milan", "rome", "stockholm",
    "vienna", "copenhagen", "oslo", "northern ireland", "belfast",
    "東京", "大阪", "首爾", "新加坡", "香港", "雪梨", "悉尼", "墨爾本",
    "倫敦", "巴黎", "柏林", "慕尼黑", "紐約", "華盛頓", "芝加哥",
    "多倫多", "溫哥華", "休士頓", "馬德里", "巴塞隆納", "阿姆斯特丹", "鹿特丹",
    "巴塞爾", "蘇黎世", "萊比錫", "米蘭", "羅馬", "斯德哥爾摩",
    "維也納", "哥本哈根", "奧斯陸", "北愛爾蘭", "貝爾法斯特",
]

PROJECT_SERIES_TERMS = [
    "project", "programme", "program", "extension", "line", "station", "construction",
    "contract", "upgrade", "rollout", "renewal", "trial", "testing", "commissioning",
    "opening", "launch", "fleet", "trainset", "cbtc", "signalling", "signaling",
    "platform screen door", "depot", "maintenance facility",
    "計畫", "專案", "延伸線", "路線", "車站", "工程", "合約", "升級", "更新",
    "試運轉", "測試", "通車", "啟用", "車隊", "列車", "號誌", "月臺門", "機廠",
]

PROJECT_STAGE_GROUPS = {
    "procurement": [
        "contract", "award", "tender", "bid", "procurement", "合約", "得標", "招標", "採購",
    ],
    "construction": [
        "construction", "works", "tunnel", "tbm", "civil works", "工程", "施工", "隧道", "潛盾",
    ],
    "testing": [
        "testing", "trial", "commissioning", "test run", "試運轉", "測試", "試車", "調試",
    ],
    "opening": [
        "opening", "opens", "launch", "service begins", "starts service", "通車", "啟用", "營運",
    ],
    "vehicle": [
        "trainset", "rolling stock", "fleet", "vehicle", "train arrival", "車輛", "列車", "車隊",
    ],
    "systems": [
        "cbtc", "signalling", "signaling", "platform screen door", "power supply",
        "號誌", "信號", "月臺門", "月台門", "供電",
    ],
}


LAST_PYTHON_SELECTION_DEBUG: dict = dict(REPORT_SELECTION_DEBUG_DEFAULT)


def build_selector_api(**dependencies) -> dict[str, object]:
    selected_types = dependencies["selected_types"]
    active_regions = dependencies["active_regions"]
    lookback_days = dependencies["lookback_days"]
    lookback_int = dependencies["lookback_int"]
    fast_mode_enabled = dependencies["fast_mode_enabled"]
    is_global_scope = dependencies["is_global_scope"]
    today = dependencies["today"]
    _search_family_from_query = dependencies["_search_family_from_query"]
    _search_language_from_query = dependencies["_search_language_from_query"]
    create_requests_session = dependencies["create_requests_session"]
    _profile_timing_add = dependencies["_profile_timing_add"]

    def _has_high_value_operational_detail(text: str) -> bool:
        return (
            _contains_any_term(text, globals().get("STRICT_HIGH_VALUE_POLICY_TEXT_TERMS", []))
            or _contains_any_term(text, TECH_NEWS_REQUIRED_TERMS)
            or _contains_any_term(text, ACCIDENT_SIGNAL_TERMS)
            or _is_standard_update_candidate(text, require_url=True)
        )


    def _has_clear_urban_rail_context(text: str, source_name: str = "") -> bool:
        topic_text = _strip_source_name_noise(f"{source_name} {text}")
        has_metro_with_rail_context = (
            _contains_any_term(topic_text, ["metro"])
            and _contains_any_term(topic_text, METRO_RAIL_CONTEXT_TERMS)
        )
        return (
            _contains_any_term(topic_text, URBAN_RAIL_UNAMBIGUOUS_MODE_TERMS)
            or _contains_any_term(topic_text, URBAN_RAIL_OPERATOR_TERMS)
            or has_metro_with_rail_context
        )


    def _is_airport_people_mover_only_text(text: str, source_name: str = "") -> bool:
        topic_text = _strip_source_name_noise(f"{source_name} {text}")
        if not _contains_any_term(topic_text, AIRPORT_PEOPLE_MOVER_EXCLUDE_TERMS):
            return False
        airport_specific = _contains_any_term(topic_text, [
            "airport people mover", "terminal people mover", "airport transit",
            "airport shuttle", "terminal shuttle", "lax", "aviation",
            "機場旅客捷運", "航廈旅客捷運", "航廈接駁", "機場接駁",
        ])
        non_airport_urban_terms = [
            term for term in URBAN_RAIL_UNAMBIGUOUS_MODE_TERMS
            if term not in {"people mover", "automated guideway transit", "agt", "mover"}
        ]
        has_non_airport_urban_context = (
            _contains_any_term(topic_text, non_airport_urban_terms)
            or _contains_any_term(topic_text, URBAN_RAIL_OPERATOR_TERMS)
        )
        return airport_specific and not has_non_airport_urban_context


    def _trusted_source_title_technical_signal(candidate: dict) -> bool:
        tier = candidate.get("source_tier", "")
        if tier not in {"A_official", "B_professional"}:
            return False
        title = candidate.get("title", "")
        if not title or _wordish_count(title) < 4:
            return False
        source = candidate.get("source", "")
        source_domain = candidate.get("source_domain", "")
        title_text = f"{title} {source} {source_domain}"
        full_text = _candidate_selection_text(candidate) if "_candidate_selection_text" in globals() else title_text
        if _contains_any_term(title_text, LOW_QUALITY_CONTENT_TERMS + HARD_LOW_VALUE_CANDIDATE_TERMS):
            return False
        if _is_airport_people_mover_only_text(full_text, source):
            return False
        if not _has_clear_urban_rail_context(title_text, source):
            return False
        has_system = _contains_any_term(title_text, TECH_NEWS_REQUIRED_TERMS)
        has_action = _contains_any_term(title_text, TITLE_TECHNICAL_ACTION_TERMS)
        return has_system and has_action


    def _candidate_has_high_value_operational_detail(candidate: dict, text: str = "") -> bool:
        combined = text or _candidate_selection_text(candidate)
        return _has_high_value_operational_detail(combined) or _trusted_source_title_technical_signal(candidate)


    def _is_low_value_service_notice_text(text: str) -> bool:
        return _contains_any_term(text, LOW_VALUE_POLICY_TERMS + LOW_INFORMATION_PAGE_TERMS)


    def hard_low_value_candidate_reason(candidate: dict) -> str:
        title = candidate.get("title", "")
        snippet = candidate.get("snippet", "")
        source = candidate.get("source", "")
        url = candidate.get("url", "")
        source_href = candidate.get("source_href", "")
        text = f"{title} {snippet} {source} {url} {source_href}"
        text_lower = text.casefold()
        host_candidates = [
            _domain_from_url(source_href),
            _domain_from_url(url),
            candidate.get("source_domain", ""),
        ]
        if any(
            host and _host_matches(host, domain)
            for host in host_candidates
            for domain in LOW_VALUE_EXCLUDED_HOSTS
        ):
            return "硬性低價值來源或子網域"
        if _contains_any_term(text, FINANCIAL_MARKET_TERMS):
            return "股票行情或企業財經分析"

        has_high_value = _candidate_has_high_value_operational_detail(candidate, text)
        if has_high_value:
            return ""
        if "_candidate_prefetch_signal" in globals() and _candidate_prefetch_signal(candidate):
            return ""

        if any(term.casefold() in text_lower for term in HARD_LOW_VALUE_CANDIDATE_TERMS):
            return "硬性低價值頁面"

        path_text = " ".join(urlparse(value or "").path.casefold() for value in (url, source_href))
        if any(marker in path_text for marker in LOW_INFORMATION_PATH_MARKERS):
            return "硬性低價值路徑"

        return ""


    def _wordish_count(text: str) -> int:
        return len(re.findall(r"[A-Za-z0-9\u4e00-\u9fff]+", text or ""))


    def _information_quality_issue(candidate: dict) -> str:
        title = candidate.get("title", "")
        snippet = candidate.get("snippet", "")
        source = candidate.get("source", "")
        text = f"{title} {snippet} {source} {candidate.get('url', '')} {candidate.get('source_href', '')}"
        title_count = _wordish_count(title)
        snippet_count = _wordish_count(snippet)
        is_official = candidate.get("source_tier") == "A_official"
        has_high_value = _candidate_has_high_value_operational_detail(candidate, text)

        if _is_low_value_service_notice_text(text) and not has_high_value:
            if _contains_any_term(text, ["route page", "route number", "RouteNumber", "trip planner"]):
                return "低價值路線公告"
            return "日常服務推播"
        if title_count < 4 and snippet_count < 10 and not (is_official and has_high_value):
            return "摘要資訊不足"
        if snippet_count < 8 and not has_high_value:
            return "摘要資訊不足"
        return ""


    def _is_standards_source(source_name: str) -> bool:
        return (source_name or "").startswith("規範更新代理")


    def _is_standard_update_query(query: str) -> bool:
        query_lower = (query or "").casefold()
        return any(
            standard.casefold() in query_lower
            for standards in STANDARDS_WATCHLIST.values()
            for standard in standards
        )


    def _is_standard_update_candidate(text: str, require_url: bool = True) -> bool:
        """
        判斷是否為真正的規範更新。
        只有「標準編號 + 明確更新動作 + 可查證來源」才算規範更新。
        單純標準清單、官方首頁、持續追蹤中，不可列入正式週報。
        """
        text_raw = text or ""
        text_lower = text_raw.casefold()

        has_standard = any(
            standard.casefold() in text_lower
            for standards in STANDARDS_WATCHLIST.values()
            for standard in standards
        )

        update_action_terms = [
            "new edition", "revision", "amendment", "corrigendum",
            "draft", "public comment", "published", "withdrawn",
            "superseded", "revised", "updated",
            "新版", "新版本", "修訂", "修正", "增補", "勘誤",
            "草案", "徵詢", "公告", "發布", "撤回", "取代",
        ]

        tracking_only_terms = [
            "持續追蹤中", "持續追蹤", "追蹤清單",
            "標準體系公告", "無單一新聞連結",
            "standard watchlist", "tracking only",
            "catalogue", "catalog", "webstore",
        ]

        has_update_action = any(term.casefold() in text_lower for term in update_action_terms)
        is_tracking_only = any(term.casefold() in text_lower for term in tracking_only_terms)
        has_url = re.search(r"https?://", text_raw) is not None

        if is_tracking_only:
            return False
        if require_url and not has_url:
            return False

        return has_standard and has_update_action


    def _is_allowed_international_candidate(candidate: dict, text: str, looks_like_standard: bool) -> bool:
        source = candidate.get("source", "")
        host = _original_source_domain(
            source,
            candidate.get("url", ""),
            candidate.get("source_href", ""),
            candidate.get("query", ""),
        )
        if looks_like_standard or _is_standards_source(source):
            return True
        if host and _host_matches(host, "uitp.org"):
            return True
        international_terms = [
            "international report", "global report", "cross-national", "multinational",
            "global survey", "benchmark report", "technical report",
            "國際報告", "全球報告", "跨國", "多國", "技術報告",
        ]
        return _contains_any_term(text, international_terms) and _contains_any_term(text, URBAN_RAIL_MODE_TERMS)


    def _is_urban_rail_candidate(text: str, source_name: str = "") -> bool:
        """正式新聞候選須直接連到都會軌道；標準更新另由規範規則處理。"""
        if _is_standards_source(source_name):
            return True

        topic_text = _strip_source_name_noise(text)
        has_metro_word = _contains_any_term(topic_text, ["metro"])
        has_metro_with_rail_context = has_metro_word and _contains_any_term(topic_text, METRO_RAIL_CONTEXT_TERMS)
        has_unambiguous_mode = _contains_any_term(topic_text, URBAN_RAIL_UNAMBIGUOUS_MODE_TERMS)
        has_operator = _contains_any_term(f"{source_name} {topic_text}", URBAN_RAIL_OPERATOR_TERMS)
        has_non_urban = _contains_any_term(topic_text, NON_URBAN_TRANSPORT_TERMS)
        has_hard_non_urban = _contains_any_term(topic_text, NON_URBAN_HARD_EXCLUDE_TERMS)
        has_civic_metro_name_only = _contains_any_term(topic_text, CIVIC_METRO_NAME_ONLY_TERMS)
        has_clear_urban_context = has_unambiguous_mode or has_operator or has_metro_with_rail_context

        if has_civic_metro_name_only and not (has_unambiguous_mode or has_operator):
            return False
        if _is_airport_people_mover_only_text(topic_text, source_name):
            return False
        if has_hard_non_urban and not has_clear_urban_context:
            return False
        if has_non_urban and not has_clear_urban_context:
            return False
        return has_clear_urban_context


    def _is_tech_news_only_mode() -> bool:
        return bool(selected_types) and set(selected_types) == {"技術新知"}


    def _is_technical_news_candidate(text: str, source_name: str = "") -> bool:
        """只勾技術新知時，排除純事故、政策、人事、行銷或一般工程進度。"""
        if _is_standards_source(source_name):
            return True

        topic_text = _strip_source_name_noise(f"{source_name} {text}")
        has_technical_term = _contains_any_term(topic_text, TECH_NEWS_REQUIRED_TERMS)
        has_soft_exclude = _contains_any_term(topic_text, TECH_NEWS_SOFT_EXCLUDE_TERMS)

        if has_soft_exclude and not has_technical_term:
            return False
        return has_technical_term


    def _compute_candidate_page_type(candidate: dict) -> tuple[str, str]:
        url = candidate.get("url", "")
        source_href = candidate.get("source_href", "")
        parsed = urlparse(url or "")
        path = (parsed.path or "").casefold()
        query = (parsed.query or "").casefold()
        text = _candidate_selection_text(candidate).casefold()
        if parsed.path in ("", "/") and "news.google.com" not in parsed.netloc:
            return "home_page", "URL path 為首頁"
        if any(marker in path for marker in ("/search", "/tag/", "/tags/", "/category", "/categories", "/archive", "/archives", "/topic", "/topics")) or "q=" in query:
            return "index_or_search_page", "索引、分類或搜尋頁"
        if any(marker in path for marker in ("/login", "/signin", "/sign-in", "/account", "/subscribe", "/privacy", "/terms")):
            return "login_or_policy_page", "登入、會員或政策頁"
        route_like_path = any(
            re.search(pattern, path)
            for pattern in (
                r"/schedules?(?:/|$)", r"/timetables?(?:/|$)", r"/trips?(?:/|$)",
                r"/journey(?:-|/|$)", r"/routes?(?:/|$)", r"/buses?(?:/|$)",
            )
        )
        if route_like_path:
            return "route_schedule_or_bus_page", "時刻表、路線、旅程規劃或公車頁"
        if any(marker in path for marker in ("/store", "/estore", "/e-store", "/shop", "/product", "/promotion", "/promotions", "/campaign", "/campaigns")):
            return "ticketing_promotion_or_product_page", "票券、促銷或商品頁"
        if any(marker in path for marker in ("/event", "/events", "/anniversary", "/celebration", "/jobs", "/careers", "/hiring")):
            return "event_or_recruiting_page", "活動、週年或招募頁"
        if _contains_any_term(text, FINANCIAL_MARKET_TERMS):
            return "financial_market_page", "股票、財務或市場分析"
        if _contains_any_term(text, PROPERTY_OR_CAMPUS_DEVELOPMENT_TERMS):
            return "property_or_life_page", "房地產、校園或周邊生活內容"
        if _contains_any_term(text, SECURITY_OR_CRIME_TERMS) and not _has_major_security_rail_impact(candidate):
            return "security_or_crime_page", "治安或一般警察案件"
        if _contains_any_term(text, LOW_QUALITY_CONTENT_TERMS + LOW_INFORMATION_PAGE_TERMS + HARD_LOW_VALUE_CANDIDATE_TERMS):
            return "low_information_page", "旅遊、入口、活動、常設服務或低資訊頁"
        if _is_airport_people_mover_only_text(text, candidate.get("source", "")):
            return "airport_people_mover_page", "機場航廈 people mover 或航空旅遊內容"
        if source_href and "news.google.com" not in _domain_from_url(source_href):
            return "news_article", "Google News 代理已提供原始來源"
        return "news_article", "具備候選新聞頁基本結構"


    def _candidate_page_type(candidate: dict) -> tuple[str, str]:
        cache = _candidate_analysis_cache(candidate)
        cached = cache.get("page_type")
        if isinstance(cached, tuple) and len(cached) == 2:
            return cached
        result = _compute_candidate_page_type(candidate)
        cache["page_type"] = result
        return result


    def _prefetch_limit_for_period(days: int) -> int:
        try:
            days = int(days)
        except (TypeError, ValueError):
            days = 7
        if days >= 365:
            return PREFETCH_LIMIT_BY_PERIOD["annual"]
        if days >= 30:
            return PREFETCH_LIMIT_BY_PERIOD["monthly"]
        return PREFETCH_LIMIT_BY_PERIOD["weekly"]


    def _candidate_prefetch_signal(candidate: dict) -> bool:
        if candidate.get("source_tier") not in {"A_official", "B_professional"}:
            return False
        title = candidate.get("title", "")
        if not title or _wordish_count(title) < 4:
            return False
        source = candidate.get("source", "")
        title_text = f"{title} {source} {candidate.get('source_domain', '')}"
        if not _has_clear_urban_rail_context(title_text, source):
            return False
        has_system_or_institution = (
            _contains_any_term(title_text, TECH_NEWS_REQUIRED_TERMS)
            or _contains_any_term(title_text, globals().get("HIGH_VALUE_POLICY_TERMS", []))
            or _contains_any_term(title_text, ACCIDENT_SIGNAL_TERMS + SAFETY_INCIDENT_DETAIL_TERMS)
            or _contains_any_term(title_text, DISPUTE_SIGNAL_TERMS + DISPUTE_ACTOR_TERMS)
        )
        has_action = _contains_any_term(
            title_text,
            TITLE_TECHNICAL_ACTION_TERMS + [
                "investigation", "investigate", "inquiry", "review", "suspend", "suspended",
                "resume", "opened", "opening", "approve", "approved", "announce", "announced",
                "award", "awarded", "strike", "lawsuit", "protest", "delay", "delayed",
            ],
        )
        return has_system_or_institution and has_action


    def prefetch_candidates_before_filter(candidates: list[dict]) -> dict:
        limit = _prefetch_limit_for_period(lookback_days)
        stats = {
            "limit": limit,
            "eligible_count": 0,
            "attempted_count": 0,
            "success_count": 0,
            "failed_count": 0,
            "skipped_limit_count": 0,
            "elapsed_seconds": 0.0,
        }
        started = time.perf_counter()
        eligible = [candidate for candidate in candidates or [] if _candidate_prefetch_signal(candidate)]
        stats["eligible_count"] = len(eligible)
        if not eligible or limit <= 0:
            stats["elapsed_seconds"] = round(time.perf_counter() - started, 2)
            return stats
        session = create_requests_session()
        for candidate in sorted(
            eligible,
            key=lambda item: (
                _source_tier_rank(item.get("source_tier", "C_media")),
                _quality_rank(item.get("source_quality", "B")),
                -_date_sort_key(item),
            ),
        ):
            if stats["attempted_count"] >= limit:
                candidate["prefetch_status"] = "skipped_limit"
                stats["skipped_limit_count"] += 1
                continue
            stats["attempted_count"] += 1
            candidate["prefetch_attempted"] = True
            result = _prefetch_candidate_article(candidate, session)
            candidate["prefetch_status"] = result.get("status", "")
            candidate["prefetch_reason"] = result.get("reason", "")
            candidate["prefetch_chars"] = result.get("chars", 0)
            candidate["prefetch_elapsed_seconds"] = result.get("elapsed_seconds", 0.0)
            if result.get("status") == "success":
                stats["success_count"] += 1
            else:
                stats["failed_count"] += 1
        stats["elapsed_seconds"] = round(time.perf_counter() - started, 2)
        return stats


    def preliminary_filter_candidate(candidate: dict) -> tuple[bool, str]:
        url = candidate.get("url", "")
        source_href = candidate.get("source_href", "")
        source = candidate.get("source", "")
        title = candidate.get("title", "")
        snippet = candidate.get("snippet", "")
        text = f"{title} {snippet} {source} {url} {source_href}"
        text_lower = text.casefold()
        candidate_region = _canonical_candidate_region(candidate)

        def _reject(reason: str) -> tuple[bool, str]:
            candidate["preliminary_keep"] = False
            candidate["preliminary_reject_reason"] = reason
            candidate.setdefault("date_validation", "")
            return False, reason

        def _keep() -> tuple[bool, str]:
            candidate["preliminary_keep"] = True
            candidate["preliminary_reject_reason"] = ""
            return True, ""

        if not url:
            return _reject("沒有 URL")

        is_valid, reason = _is_valid_news_url(url, source_href=source_href)
        if not is_valid:
            return _reject(reason)

        date_obj = _candidate_date_obj(candidate.get("date", ""))
        if not date_obj:
            date_obj = _date_from_url_path(source_href, url)
            if date_obj:
                candidate["date"] = date_obj.isoformat()
                candidate["date_source"] = "url_path"
        if not date_obj:
            candidate["date_validation"] = "invalid_or_missing"
            return _reject("日期不明或無法判斷")
        cutoff_date = today - datetime.timedelta(days=max(1, min(int(lookback_days), 365)))
        if date_obj < cutoff_date:
            candidate["date_validation"] = "out_of_range_old"
            return _reject("日期不符搜尋期間")
        if date_obj > today + datetime.timedelta(days=1):
            candidate["date_validation"] = "future_date"
            return _reject("未來日期不合理")
        candidate["date_validation"] = "valid_in_range"

        page_type, page_type_reason = _candidate_page_type(candidate)
        candidate["page_type"] = page_type
        candidate["page_type_reason"] = page_type_reason
        if page_type != "news_article":
            return _reject(page_type_reason)

        if _contains_taiwan_reference(text):
            return _reject("國內新聞排除")

        if _is_airport_people_mover_only_text(text, source):
            return _reject("機場/航空 people mover 排除")

        if any(term.casefold() in text_lower for term in LOW_QUALITY_CONTENT_TERMS):
            return _reject("旅遊/SEO/內容農場")

        information_issue = _information_quality_issue(candidate)
        if information_issue:
            return _reject(information_issue)
        if _is_low_value_long_term_candidate(candidate):
            return _reject("長期回顧低價值或錯分類候選")

        parsed_url = urlparse(url)
        path_lower = (parsed_url.path or "").casefold()
        has_entry_path = any(marker in path_lower for marker in LOW_INFORMATION_PATH_MARKERS)
        has_entry_terms = any(term.casefold() in text_lower for term in LOW_INFORMATION_PAGE_TERMS)
        has_technical_detail = (
            _contains_any_term(text, TECH_NEWS_REQUIRED_TERMS)
            or _trusted_source_title_technical_signal(candidate)
        )
        has_dispute_detail = _contains_any_term(text, [
            "strike", "fare dispute", "contract dispute", "lawsuit", "delay compensation",
            "cost overrun", "budget overrun", "service disruption", "public backlash",
            "罷工", "勞資爭議", "票價爭議", "合約糾紛", "工程延宕", "成本增加", "服務中斷", "民怨",
        ])
        has_policy_value = _contains_any_term(text, HIGH_VALUE_POLICY_TERMS) if "HIGH_VALUE_POLICY_TERMS" in globals() else False
        is_low_value_tier = candidate.get("source_tier") == "D_proxy_low_value"
        if (has_entry_path or has_entry_terms or is_low_value_tier) and not (
            has_technical_detail
            or has_dispute_detail
            or has_policy_value
            or _is_standard_update_candidate(text, require_url=True)
        ):
            return _reject("入口頁/服務頁/分類頁且缺少明確事件")

        looks_like_standard = _is_standards_source(source) or any(
            standard.casefold() in text_lower
            for standards in STANDARDS_WATCHLIST.values()
            for standard in standards
        )
        if looks_like_standard:
            if "規範更新" not in selected_types:
                return _reject("規範更新未勾選")
            if not _is_standard_update_candidate(f"{text} {candidate.get('date', '')}", require_url=True):
                return _reject("規範更新條件不足")
            return _keep()

        if not is_global_scope:
            if candidate_region not in active_regions:
                if candidate_region in {"國際", "國際研究", "未判定"} and _is_allowed_international_candidate(candidate, text, looks_like_standard):
                    candidate["region"] = "國際"
                else:
                    return _reject("國家/地區不在指定範圍")
        elif candidate_region in {"國際", "國際研究"} and not _is_allowed_international_candidate(candidate, text, looks_like_standard):
            candidate["region"] = "未判定"

        if not _is_urban_rail_candidate(text, source):
            return _reject("非捷運/都市軌道")

        if _is_tech_news_only_mode() and not _is_technical_news_candidate(text, source):
            return _reject("非技術新知")

        gate_info = evaluate_category_gates(candidate)
        candidate.update(gate_info)
        if gate_info.get("primary_category") == "excluded":
            candidate["classification"] = "excluded"
            candidate["exclude_reason"] = "no_category_gate"
            return _reject("no_category_gate")
        candidate["classification"] = gate_info.get("primary_category", "")

        if candidate.get("source_quality") == "C" and not _contains_any_term(text, URBAN_RAIL_UNAMBIGUOUS_MODE_TERMS):
            return _reject("C級來源且主題關聯不足")

        return _keep()


    def _excluded_candidate_value_reasons(candidate: dict) -> list[str]:
        reasons: list[str] = []
        tier = candidate.get("source_tier", "")
        if tier in {"A_official", "B_professional"}:
            reasons.append(f"source_tier={tier}")
        score = int(candidate.get("python_score", 0) or 0)
        if score >= 55:
            reasons.append(f"python_score={score}")
        family = candidate.get("search_family", "")
        if family in {"technology", "major_accident", "policy", "dispute", "official_investigation"}:
            reasons.append(f"search_family={family}")
        flags = candidate.get("candidate_flags", []) or []
        useful_flags = [
            flag for flag in flags
            if flag in {"technical_or_system_detail", "incident_or_safety_signal", "high_value_policy", "trusted_title_technical_signal", "operational_dispute_gate"}
        ]
        if useful_flags:
            reasons.append("flags=" + ",".join(useful_flags[:3]))
        if candidate.get("prefetch_status") == "success":
            reasons.append("prefetch=success")
        return reasons


    def build_top_excluded_valuable_candidates(excluded_candidates: list[dict], limit: int = 20) -> list[dict]:
        rows: list[dict] = []
        for candidate in excluded_candidates or []:
            reasons = _excluded_candidate_value_reasons(candidate)
            if not reasons:
                continue
            score = int(candidate.get("python_score", 0) or 0)
            tier_bonus = 20 if candidate.get("source_tier") == "A_official" else 12 if candidate.get("source_tier") == "B_professional" else 0
            family_bonus = 10 if candidate.get("search_family") in {"major_accident", "official_investigation", "technology"} else 0
            rows.append({
                "title": candidate.get("title", ""),
                "source": candidate.get("source_display") or candidate.get("source", ""),
                "source_tier": candidate.get("source_tier", ""),
                "search_family": candidate.get("search_family", ""),
                "search_language": candidate.get("search_language", ""),
                "python_score": score,
                "value_reason": "; ".join(reasons),
                "excluded_reason": candidate.get("final_exclude_reason") or candidate.get("preliminary_reject_reason") or candidate.get("exclude_reason", ""),
                "prefetch_status": candidate.get("prefetch_status", ""),
                "url": _effective_source_url(candidate),
                "_rank": score + tier_bonus + family_bonus,
            })
        rows.sort(key=lambda row: (-int(row.get("_rank", 0)), -int(row.get("python_score", 0)), row.get("title", "")))
        for row in rows:
            row.pop("_rank", None)
        return rows[:limit]


    def _canonical_tags_from_text(text: str) -> list[str]:
        text_lower = (text or "").casefold()
        tags: list[str] = []
        for tag, terms in CANONICAL_TAG_PATTERNS:
            if any(term.casefold() in text_lower for term in terms):
                tags.append(tag)
        return tags


    def _candidate_selection_text(candidate: dict) -> str:
        fingerprint = (
            candidate.get("title", ""),
            candidate.get("snippet", ""),
            candidate.get("source", ""),
            candidate.get("url", ""),
            candidate.get("source_href", ""),
        )
        if candidate.get("_selection_text_fingerprint") == fingerprint and candidate.get("_selection_text_cache"):
            return candidate["_selection_text_cache"]
        paths = " ".join(
            urlparse(candidate.get(key, "") or "").path.replace("/", " ")
            for key in ("url", "source_href")
        )
        base_text = (
            f"{candidate.get('title', '')} {candidate.get('snippet', '')} "
            f"{candidate.get('source', '')} "
            f"{candidate.get('url', '')} {candidate.get('source_href', '')} {paths}"
        )
        canonical_tags = " ".join(_canonical_tags_from_text(base_text))
        text = f"{base_text} {canonical_tags}".strip()
        candidate["_selection_text_fingerprint"] = fingerprint
        candidate["_selection_text_cache"] = text
        return text


    def _candidate_analysis_fingerprint(candidate: dict) -> tuple:
        return (
            candidate.get("title", ""),
            candidate.get("snippet", ""),
            candidate.get("date", ""),
            candidate.get("source", ""),
            candidate.get("url", ""),
            candidate.get("source_href", ""),
            candidate.get("resolved_article_url", ""),
            candidate.get("source_tier", ""),
            candidate.get("source_quality", ""),
            candidate.get("region", ""),
            candidate.get("classification", ""),
        )


    def _candidate_analysis_cache(candidate: dict) -> dict:
        fingerprint = _candidate_analysis_fingerprint(candidate)
        if candidate.get("_analysis_cache_fingerprint") != fingerprint:
            candidate["_analysis_cache_fingerprint"] = fingerprint
            candidate["_analysis_cache"] = {}
        return candidate.setdefault("_analysis_cache", {})


    def _cached_candidate_bool(candidate: dict, key: str, compute) -> bool:
        cache = _candidate_analysis_cache(candidate)
        if key not in cache:
            cache[key] = bool(compute(candidate))
        return bool(cache[key])


    def _candidate_urban_rail_gate(candidate: dict) -> bool:
        return _cached_candidate_bool(
            candidate,
            "urban_rail_gate",
            lambda item: _is_urban_rail_candidate(_candidate_selection_text(item), item.get("source", "")),
        )


    def _compute_technical_system_gate(candidate: dict) -> bool:
        text = _candidate_selection_text(candidate)
        has_known_system = _contains_any_term(
            text,
            CORE_METRO_TECHNICAL_TERMS
            + TECH_NEWS_REQUIRED_TERMS
            + STRONG_TECHNICAL_DETAIL_TERMS
            + MEDIUM_TECHNICAL_DETAIL_TERMS,
        )
        if has_known_system:
            return True
        canonical_actions = set(_canonical_tags_from_text(text)).intersection({"enter service", "modernization", "upgrade", "deployment"})
        title = candidate.get("title", "")
        return bool(
            canonical_actions
            and _contains_any_term(title, ["tram", "streetcar", "light rail vehicle"])
            and (_contains_any_term(title, ["urbanliner", "new tram", "alstom tram"]) or re.search(r"\b[A-Z][A-Za-z0-9-]+\s+tram\b", title))
        )


    def _technical_system_gate(candidate: dict) -> bool:
        return _cached_candidate_bool(candidate, "technical_system_gate", _compute_technical_system_gate)


    def _compute_technical_action_gate(candidate: dict) -> bool:
        text = _candidate_selection_text(candidate)
        title = candidate.get("title", "")
        if set(_canonical_tags_from_text(text)).intersection({"enter service", "modernization", "upgrade", "deployment"}):
            return True
        if _contains_any_term(text, TECHNICAL_IMPLEMENTATION_TERMS + TITLE_TECHNICAL_ACTION_TERMS):
            return True
        if _technical_system_gate(candidate) and _contains_any_term(text, SUBSTANTIVE_TECHNICAL_DETAIL_TERMS):
            return True
        return _trusted_source_title_technical_signal(candidate) or _contains_any_term(
            title,
            TECHNICAL_IMPLEMENTATION_TERMS + TITLE_TECHNICAL_ACTION_TERMS,
        )


    def _technical_action_gate(candidate: dict) -> bool:
        return _cached_candidate_bool(candidate, "technical_action_gate", _compute_technical_action_gate)


    def _is_project_only_technical_candidate(candidate: dict) -> bool:
        text = _candidate_selection_text(candidate)
        if not _contains_any_term(text, PROJECT_ONLY_ACTION_TERMS):
            return False
        if _contains_any_term(text, SUBSTANTIVE_TECHNICAL_DETAIL_TERMS):
            return False
        return not bool(re.search(
            r"\b\d+(?:\.\d+)?\s*(?:%|kw|kwh|mw|mwh|km/h|mm|db|tons?|tonnes?)\b",
            text,
            flags=re.IGNORECASE,
        ))


    def _compute_passes_technical_triad(candidate: dict) -> bool:
        text = _candidate_selection_text(candidate)
        if _is_financial_market_candidate(candidate):
            return False
        if _is_security_or_crime_candidate(candidate):
            return False
        if _is_airport_people_mover_only_text(text, candidate.get("source", "")):
            return False
        if _is_project_only_technical_candidate(candidate):
            return False
        if _contains_any_term(text, NON_TECH_NEWS_EXCLUDE_TERMS) and not _contains_any_term(
            text,
            CORE_METRO_TECHNICAL_TERMS + STRONG_TECHNICAL_DETAIL_TERMS + TECHNICAL_IMPLEMENTATION_TERMS,
        ):
            return False
        if not _candidate_urban_rail_gate(candidate):
            return False
        return _technical_system_gate(candidate) and _technical_action_gate(candidate)


    def _passes_technical_triad(candidate: dict) -> bool:
        return _cached_candidate_bool(candidate, "passes_technical_triad", _compute_passes_technical_triad)


    def _candidate_event_fragments(candidate: dict) -> list[str]:
        fragments: list[str] = []
        for value in (candidate.get("title", ""), candidate.get("snippet", "")):
            for fragment in re.split(r"(?:[。！？!?]+|…+|\.\s+(?=[A-Z0-9]))", value or ""):
                cleaned = re.sub(r"\s+", " ", fragment).strip(" -–—|/、，,")
                if cleaned:
                    fragments.append(cleaned)
        return fragments


    def _fragment_has_urban_rail_context(fragment: str) -> bool:
        return _contains_any_term(
            fragment,
            URBAN_RAIL_INCIDENT_CONTEXT_TERMS + URBAN_RAIL_OPERATOR_TERMS,
        )


    def _is_single_person_rail_incident(fragment: str) -> bool:
        if _contains_any_term(fragment, SINGLE_PERSON_INCIDENT_TERMS):
            return True
        return bool(re.search(
            r"\b(?:person|woman|man|passenger|trespasser)\b.{0,45}"
            r"\b(?:struck|hit|killed)\b.{0,35}\b(?:train|subway|metro|tram|rail)\b",
            fragment or "",
            flags=re.IGNORECASE,
        ))


    def _has_single_person_incident_exception(candidate: dict, fragment: str) -> bool:
        full_text = _candidate_selection_text(candidate)
        return (
            _contains_any_term(full_text, OFFICIAL_TRANSPORT_SAFETY_INVESTIGATION_TERMS)
            or _contains_any_term(full_text, EQUIPMENT_FAILURE_TERMS)
            or (
                _contains_any_term(fragment, ["system failure", "system fault", "mechanical failure"])
                and _contains_any_term(fragment, CORE_METRO_TECHNICAL_TERMS)
            )
        )


    def _is_post_incident_policy_response(candidate: dict) -> bool:
        text = _candidate_selection_text(candidate)
        title = str(candidate.get("title", "") or "")
        policy_action = _contains_any_term(
            text,
            POST_INCIDENT_POLICY_TERMS + HIGH_VALUE_POLICY_GATE_TERMS + SUBSTANTIVE_POLICY_DETAIL_TERMS,
        )
        current_accident = _contains_any_term(
            title,
            [
                "derailment", "derailed", "collision", "collided", "crash", "train fire",
                "station fire", "mass evacuation", "fatal", "killed", "serious injury",
                "multiple injuries", "death", "出軌", "脫軌", "碰撞", "火災", "大量疏散",
                "死亡", "重傷", "多人受傷",
            ],
        ) and not _contains_any_term(title, POST_INCIDENT_POLICY_TERMS)
        return policy_action and not current_accident and _contains_any_term(
            text,
            [
                "improve", "improvement", "measure", "plan", "review", "upgrade", "enhance",
                "policy", "response", "改善", "措施", "計畫", "檢討", "提升", "部署",
            ],
        )


    def _has_major_accident_evidence(fragment: str) -> bool:
        if _contains_any_term(fragment, MAJOR_ACCIDENT_DIRECT_TERMS):
            return True
        if re.search(r"\b\d{1,3}\+?\s+(?:people\s+)?(?:were\s+)?injured\b", fragment or "", flags=re.IGNORECASE):
            return True
        if _contains_any_term(fragment, ["dozens injured", "dozens of people injured", "multiple injured", "多人受傷", "數十人受傷"]):
            return True
        if _contains_any_term(fragment, ["major safety consequence", "major safety consequences", "重大安全後果", "重大安全影響"]):
            return True
        return _contains_any_term(fragment, ["train fire", "station fire", "subway fire", "metro fire", "列車火災", "車站火災"])


    def _compute_passes_major_accident_gate(candidate: dict) -> bool:
        text = _candidate_selection_text(candidate)
        if not _candidate_urban_rail_gate(candidate):
            return False
        if _is_post_incident_policy_response(candidate):
            return False
        if _contains_any_term(text, NON_ACCIDENT_CONTEXT_TERMS):
            return False
        if _is_security_or_crime_candidate(candidate) and not _has_major_security_rail_impact(candidate):
            return False
        for fragment in _candidate_event_fragments(candidate):
            if not _fragment_has_urban_rail_context(fragment):
                continue
            has_accident_context = (
                _contains_any_term(fragment, ACCIDENT_SIGNAL_TERMS + SAFETY_INCIDENT_DETAIL_TERMS + EQUIPMENT_FAILURE_TERMS)
                or _contains_any_term(fragment, ["accident", "incident", "failure", "fault", "事故", "故障", "異常"])
            )
            if not has_accident_context:
                continue
            has_severity = (
                _has_major_accident_evidence(fragment)
                or (
                    _contains_any_term(fragment, EQUIPMENT_FAILURE_TERMS)
                    and _contains_any_term(fragment, [
                        "evacuation", "evacuated", "injury", "injured", "fatal", "death",
                        "fire", "collision", "derailment", "official investigation",
                        "安全後果", "安全調查", "疏散", "受傷", "死亡",
                    ])
                )
            )
            if not has_severity:
                continue
            if _is_single_person_rail_incident(fragment) and not _has_single_person_incident_exception(candidate, fragment):
                continue
            road_interface = _contains_any_term(fragment, ROAD_INTERFACE_ACCIDENT_TERMS)
            low_impact = _contains_any_term(fragment, LOW_IMPACT_ACCIDENT_TERMS + LOW_IMPACT_ROAD_INTERFACE_TERMS)
            explicitly_minor_road_interface = road_interface and low_impact and _contains_any_term(fragment, [
                "no derailment", "not derailed", "without derailment", "no formal investigation",
                "no investigation", "short delay", "brief delay", "minor injury", "slight injury",
                "未出軌", "無出軌", "未脫軌", "無正式調查", "短暫延誤", "輕傷",
            ])
            if explicitly_minor_road_interface:
                continue
            if low_impact and not has_severity:
                continue
            if road_interface and not has_severity:
                continue
            return True
        return False


    def _passes_major_accident_gate(candidate: dict) -> bool:
        return _cached_candidate_bool(candidate, "passes_major_accident_gate", _compute_passes_major_accident_gate)


    def _compute_passes_operational_dispute_primary_gate(candidate: dict) -> bool:
        text = _candidate_selection_text(candidate)
        if not _candidate_urban_rail_gate(candidate):
            return False
        if _contains_any_term(text, LOW_REPORT_VALUE_TERMS + LOW_QUALITY_CONTENT_TERMS):
            return False
        return (
            _contains_any_term(text, DISPUTE_SIGNAL_TERMS)
            and _contains_any_term(text, DISPUTE_ACTOR_TERMS)
            and _contains_any_term(text, DISPUTE_IMPACT_TERMS)
        )


    def _passes_operational_dispute_primary_gate(candidate: dict) -> bool:
        return _cached_candidate_bool(
            candidate,
            "passes_operational_dispute_primary_gate",
            _compute_passes_operational_dispute_primary_gate,
        )


    def _has_valid_operational_metadata(candidate: dict) -> bool:
        return bool(
            _candidate_date_obj(candidate.get("date", ""))
            and _has_source_reference(candidate)
        )


    def _compute_passes_operational_dispute_secondary_gate(candidate: dict) -> bool:
        text = _candidate_selection_text(candidate)
        title_snippet = f"{candidate.get('title', '')} {candidate.get('snippet', '')}"
        if not _candidate_urban_rail_gate(candidate):
            return False
        if not _has_valid_operational_metadata(candidate):
            return False
        if candidate.get("source_tier") not in {"A_official", "B_professional"}:
            return False
        if _contains_any_term(text, LOW_REPORT_VALUE_TERMS + LOW_QUALITY_CONTENT_TERMS):
            return False
        if not _contains_any_term(text, DISPUTE_SECONDARY_SIGNAL_TERMS):
            return False
        if not _contains_any_term(text, DISPUTE_SECONDARY_IMPACT_TERMS):
            return False
        return _contains_any_term(
            title_snippet,
            [
                "arbitration", "lawsuit", "court", "strike", "dispute", "protest",
                "contract", "procurement", "delays", "delayed", "suspended",
                "terminated", "cancelled", "canceled", "awarded", "rejected",
                "decision", "action", "仲裁", "訴訟", "法院", "罷工", "爭議",
                "抗議", "合約", "延誤", "停駛", "裁決", "決議",
            ],
        )


    def _passes_operational_dispute_secondary_gate(candidate: dict) -> bool:
        return _cached_candidate_bool(
            candidate,
            "passes_operational_dispute_secondary_gate",
            _compute_passes_operational_dispute_secondary_gate,
        )


    def _compute_passes_operational_dispute_gate(candidate: dict) -> bool:
        return (
            _passes_operational_dispute_primary_gate(candidate)
            or _passes_operational_dispute_secondary_gate(candidate)
        )


    def _passes_operational_dispute_gate(candidate: dict) -> bool:
        return _cached_candidate_bool(
            candidate,
            "passes_operational_dispute_gate",
            _compute_passes_operational_dispute_gate,
        )


    def _is_dispute_dominant(candidate: dict) -> bool:
        return _passes_operational_dispute_gate(candidate)


    def _is_policy_dominant(candidate: dict) -> bool:
        title_snippet = f"{candidate.get('title', '')} {candidate.get('snippet', '')}"
        return (
            _candidate_urban_rail_gate(candidate)
            and _contains_any_term(title_snippet, POLICY_DOMINANT_TERMS)
            and _contains_any_term(
                title_snippet,
                [
                    "approved", "approve", "adopted", "announced", "introduced", "reform",
                    "opening", "opened", "extension", "increase", "change", "decision",
                    "核准", "核定", "通車", "開通", "改革", "調整", "延伸", "提升",
                    "決定", "公告",
                ],
            )
        )


    def _is_short_term_service_notice(candidate: dict) -> bool:
        text = f"{candidate.get('title', '')} {candidate.get('snippet', '')}"
        if not _contains_any_term(text, SHORT_TERM_SERVICE_NOTICE_TERMS):
            return False
        has_short_window = (
            _contains_any_term(text, SHORT_TERM_TIME_SIGNALS)
            or bool(re.search(r"\b(?:on|for)\s+(?:20\d{2}[-/]\d{1,2}[-/]\d{1,2}|(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2})\b", text, flags=re.IGNORECASE))
            or bool(re.search(r"(?:20\d{2}年)?\d{1,2}月\d{1,2}日", text))
        )
        return has_short_window


    def _compute_passes_high_value_policy_gate(candidate: dict) -> bool:
        text = _candidate_selection_text(candidate)
        if not _candidate_urban_rail_gate(candidate):
            return False
        if not _has_valid_operational_metadata(candidate):
            return False
        if _is_short_term_service_notice(candidate):
            return False
        if _passes_major_accident_gate(candidate) or _is_dispute_dominant(candidate):
            return False
        if _passes_technical_triad(candidate) and not _is_policy_dominant(candidate):
            return False
        if _contains_any_term(text, LOW_REPORT_VALUE_TERMS + LOW_QUALITY_CONTENT_TERMS):
            return False
        if _contains_any_term(text, ["fare table", "fare difference table", "ticket price list", "票價表", "車費差額", "票價查詢"]):
            return False
        if _contains_any_term(text, ["bus riders", "bus, train", "bus and train", "公車", "巴士"]) and not _contains_any_term(text, ["metro", "subway", "mrt", "lrt", "tram", "light rail"]):
            return False
        return _contains_any_term(text, HIGH_VALUE_POLICY_GATE_TERMS + SUBSTANTIVE_POLICY_DETAIL_TERMS)


    def _passes_high_value_policy_gate(candidate: dict) -> bool:
        return _cached_candidate_bool(candidate, "passes_high_value_policy_gate", _compute_passes_high_value_policy_gate)


    def evaluate_category_gates(candidate: dict) -> dict:
        analysis_cache = _candidate_analysis_cache(candidate)
        cached = analysis_cache.get("category_gate_payload")
        if isinstance(cached, dict):
            return dict(cached)
        text = _candidate_selection_text(candidate)
        canonical_tags = _canonical_tags_from_text(text)
        gates = {
            "major_accident": _passes_major_accident_gate(candidate),
            "technology": _passes_technical_triad(candidate),
            "operational_dispute": _passes_operational_dispute_gate(candidate),
            "operational_policy": _passes_high_value_policy_gate(candidate),
        }
        reasons: dict[str, str] = {}
        if gates["major_accident"]:
            reasons["major_accident"] = "具都市軌道情境、事故/故障訊號及嚴重度。"
        elif _contains_any_term(text, ACCIDENT_SIGNAL_TERMS + SAFETY_INCIDENT_DETAIL_TERMS):
            reasons["major_accident"] = "有事故訊號但未達重大事故嚴重度或非都市軌道。"
        if gates["technology"]:
            reasons["technology"] = "具都市軌道對象、機電/設備主題及導入/更新/維修行為。"
        elif _is_project_only_technical_candidate(candidate):
            reasons["technology"] = "專案或商務動作明顯，但缺乏實質技術架構、方法、效益或驗證內容。"
        elif _technical_system_gate(candidate) or _technical_action_gate(candidate):
            reasons["technology"] = "技術三聯條件不完整。"
        if gates["operational_dispute"]:
            if _passes_operational_dispute_primary_gate(candidate):
                reasons["operational_dispute"] = "具衝突主體、爭議議題及服務/合約/成本/治理影響。"
            else:
                reasons["operational_dispute"] = "具都市軌道、日期、A/B來源、爭議訊號及營運影響（次級 gate）。"
        elif _contains_any_term(text, DISPUTE_SIGNAL_TERMS):
            reasons["operational_dispute"] = "有爭議詞但缺少明確主體或營運影響。"
        if gates["operational_policy"]:
            reasons["operational_policy"] = "具系統、路線、容量或制度層級營運影響。"
        elif _contains_any_term(text, HIGH_VALUE_POLICY_GATE_TERMS + SUBSTANTIVE_POLICY_DETAIL_TERMS):
            reasons["operational_policy"] = "政策訊號不足或被低價值公告排除。"

        primary_category = "excluded"
        for key, label in (
            ("major_accident", "重大事故"),
            ("operational_dispute", "營運爭議"),
            ("operational_policy", "營運政策"),
            ("technology", "技術新知"),
        ):
            if gates.get(key):
                primary_category = label
                break
        alternatives = [
            label for key, label in (
                ("major_accident", "重大事故"),
                ("operational_dispute", "營運爭議"),
                ("operational_policy", "營運政策"),
                ("technology", "技術新知"),
            )
            if gates.get(key) and label != primary_category
        ]
        if primary_category == "excluded":
            reasons.setdefault("no_category_gate", "未通過重大事故、技術新知、營運爭議或營運政策 gate。")
        original_category = (
            candidate.get("classification")
            or candidate.get("primary_category")
            or candidate.get("preliminary_type")
            or ""
        )
        category_reclassification = None
        if original_category in ADVANCED_TYPES and original_category != primary_category:
            supporting_terms = [
                reason for key, reason in reasons.items()
                if key in gates and reason
            ]
            rule = "category_gate_priority"
            if original_category == "重大事故" and primary_category == "營運政策" and _is_post_incident_policy_response(candidate):
                rule = "post_incident_policy_response_overrides_accident"
            category_reclassification = {
                "original_category": original_category,
                "new_category": primary_category,
                "rule": rule,
                "supporting_evidence": supporting_terms,
                "python_rewrite": True,
            }
        result = {
            "category_gates": gates,
            "category_gate_reasons": reasons,
            "canonical_tags": canonical_tags,
            "primary_category": primary_category,
            "alternative_category_flags": alternatives,
            "category_reclassification": category_reclassification,
        }
        analysis_cache["category_gate_payload"] = dict(result)
        return result


    def _candidate_level(candidate: dict, score: int | None = None) -> str:
        score_value = int(candidate.get("python_score", score or 0) or score or 0)
        tier = candidate.get("source_tier", "C_media")
        primary = candidate.get("primary_category") or infer_preliminary_type(candidate)
        has_date = bool(_candidate_date_obj(candidate.get("date", "")))
        has_source = _has_source_reference(candidate) if "_has_source_reference" in globals() else bool(candidate.get("source_domain"))
        if primary == "excluded" or tier == "D_proxy_low_value" or not has_date or not has_source:
            return "C"
        if _is_low_value_ceremonial_candidate(candidate):
            return "B" if tier in {"A_official", "B_professional"} else "C"
        if primary == "重大事故" and score_value < 62:
            return "C"
        if score_value >= 68 and tier in {"A_official", "B_professional", "C_media"}:
            return "A"
        if score_value >= (62 if primary == "重大事故" else 58) and tier in {"A_official", "B_professional"}:
            return "B"
        return "C"


    def _is_accident_signal_text(text: str) -> bool:
        if _contains_any_term(text, NON_ACCIDENT_CONTEXT_TERMS):
            return False
        if _contains_any_term(text, SECURITY_OR_CRIME_TERMS) and not _contains_any_term(text, MAJOR_SECURITY_RAIL_IMPACT_TERMS):
            return False
        if not _contains_any_term(text, URBAN_RAIL_INCIDENT_CONTEXT_TERMS):
            return False
        if _contains_any_term(text, SAFETY_INCIDENT_DETAIL_TERMS):
            return True
        equipment_terms = [
            "platform screen door", "platform doors", "train door", "barrier",
            "platform barrier", "月臺門", "月台門", "車門", "月臺屏障",
        ]
        issue_terms = [
            "failure", "fault", "damage", "incident", "accident", "review",
            "safety", "stuck", "broken", "異常", "故障", "損壞", "事故", "檢討", "安全",
        ]
        return _contains_any_term(text, equipment_terms) and _contains_any_term(text, issue_terms)


    def _has_strong_technical_detail_text(text: str) -> bool:
        return _contains_any_term(text, STRONG_TECHNICAL_DETAIL_TERMS)


    def _has_explicit_technical_system_detail(candidate: dict) -> bool:
        flags = set(candidate.get("candidate_flags", []) or [])
        if "technical_or_system_detail" in flags:
            return True
        return _has_strong_technical_detail_text(_candidate_selection_text(candidate))


    def _has_good_report_signal(candidate: dict) -> bool:
        flags = set(candidate.get("candidate_flags", []) or [])
        if flags.intersection({"technical_or_system_detail", "incident_or_safety_signal", "high_value_policy", "trusted_title_technical_signal"}):
            return True
        text = _candidate_selection_text(candidate)
        return (
            _passes_technical_triad(candidate)
            or _trusted_source_title_technical_signal(candidate)
            or _passes_major_accident_gate(candidate)
            or _passes_high_value_policy_gate(candidate)
            or _passes_operational_dispute_gate(candidate)
        )


    def _has_low_value_official_notice(candidate: dict) -> bool:
        return _contains_any_term(_candidate_selection_text(candidate), LOW_VALUE_OFFICIAL_NOTICE_TERMS)


    def _has_procurement_list_notice(candidate: dict) -> bool:
        return _contains_any_term(_candidate_selection_text(candidate), PROCUREMENT_LIST_NOTICE_TERMS)


    def _is_financial_market_candidate(candidate: dict) -> bool:
        text = _candidate_selection_text(candidate)
        return _contains_any_term(text, FINANCIAL_MARKET_TERMS)


    def _is_low_value_ceremonial_candidate(candidate: dict) -> bool:
        title = candidate.get("title", "")
        text = f"{title} {candidate.get('snippet', '')}"
        if not _contains_any_term(text, LOW_VALUE_CEREMONIAL_TERMS):
            return False
        if _contains_any_term(text, ["award", "awards", "awarded"]) and _contains_any_term(
            text, ["contract", "procurement", "tender", "採購", "合約", "標案"]
        ):
            return False
        if _contains_any_term(title, FORMAL_ENGINEERING_EVENT_TERMS):
            return False
        return not _contains_any_term(text, FORMAL_ENGINEERING_EVENT_TERMS)


    def _is_security_or_crime_candidate(candidate: dict) -> bool:
        return _contains_any_term(_candidate_selection_text(candidate), SECURITY_OR_CRIME_TERMS)


    def _has_major_security_rail_impact(candidate: dict) -> bool:
        text = _candidate_selection_text(candidate)
        return _contains_any_term(text, MAJOR_SECURITY_RAIL_IMPACT_TERMS)


    def _has_core_metro_technical_content(candidate: dict) -> bool:
        text = _candidate_selection_text(candidate)
        if _contains_any_term(text, EQUIPMENT_FAILURE_TERMS) and not _contains_any_term(text, ["rollout flaw", "system interface problem", "ticketing outage"]):
            return False
        if _contains_any_term(text, PROPERTY_OR_CAMPUS_DEVELOPMENT_TERMS) and not _technical_system_gate(candidate):
            return False
        if _contains_any_term(text, ENGINEERING_MILESTONE_ONLY_TERMS) and not _technical_system_gate(candidate):
            return False
        if _contains_any_term(text, GENERIC_TEST_WITHOUT_TECH_TERMS) and not _technical_system_gate(candidate):
            return False
        return _passes_technical_triad(candidate)


    def _has_general_rail_exclusion(candidate: dict) -> bool:
        text = _candidate_selection_text(candidate)
        if not _contains_any_term(text, GENERAL_RAIL_EXCLUDE_TERMS):
            return False
        return not _has_clear_urban_rail_context(text, candidate.get("source", ""))


    def _has_substantive_detail_for_low_value_notice(candidate: dict) -> bool:
        text = _candidate_selection_text(candidate)
        return (
            _contains_any_term(text, STRONG_TECHNICAL_DETAIL_TERMS)
            or _contains_any_term(text, SAFETY_INCIDENT_DETAIL_TERMS)
            or _contains_any_term(text, SUBSTANTIVE_POLICY_DETAIL_TERMS)
            or _contains_any_term(text, WEEKLY_BACKFILL_ALLOWED_TERMS)
        )


    def _has_long_term_report_value(candidate: dict) -> bool:
        text = _candidate_selection_text(candidate)
        return (
            _has_good_report_signal(candidate)
            or _contains_any_term(text, STRONG_TECHNICAL_DETAIL_TERMS)
            or _contains_any_term(text, SAFETY_INCIDENT_DETAIL_TERMS)
            or _contains_any_term(text, SUBSTANTIVE_POLICY_DETAIL_TERMS)
            or _contains_any_term(text, HIGH_IMPACT_ACCIDENT_TERMS)
        )


    def _is_low_value_long_term_candidate(candidate: dict) -> bool:
        lookback_value = int(lookback_int)
        if lookback_value < 30:
            return False
        text = _candidate_selection_text(candidate)
        classification = candidate.get("classification") or candidate.get("preliminary_type") or infer_preliminary_type(candidate)
        if _contains_any_term(text, LOW_REPORT_VALUE_TERMS) and not _has_long_term_report_value(candidate):
            return True
        if _contains_any_term(text, NON_TECH_NEWS_EXCLUDE_TERMS) and not _has_long_term_report_value(candidate):
            return True
        if _contains_any_term(text, CIVIC_METRO_NAME_ONLY_TERMS) and not _contains_any_term(text, URBAN_RAIL_UNAMBIGUOUS_MODE_TERMS):
            return True
        if lookback_value in ADVANCED_LOOKBACK_OPTIONS and classification == "重大事故" and not _passes_major_accident_gate(candidate):
            return True
        return False


    def _is_technical_news_selection_candidate(candidate: dict) -> bool:
        if candidate.get("classification") != "技術新知":
            return False
        text = _candidate_selection_text(candidate)
        if _is_financial_market_candidate(candidate):
            return False
        if _contains_any_term(text, NON_TECH_NEWS_EXCLUDE_TERMS):
            return False
        if _is_accident_signal_text(text):
            return False
        if _is_low_value_ceremonial_candidate(candidate):
            return False
        if not _passes_technical_triad(candidate):
            return False
        if _has_low_value_official_notice(candidate):
            return False
        if candidate.get("source_tier") == "D_proxy_low_value":
            return False
        return True


    def get_selection_candidate_limit(days: int, fast_mode: bool = False) -> int:
        try:
            days = int(days)
        except (TypeError, ValueError):
            days = 7
        if fast_mode:
            if days >= 90:
                return 100
            if days >= 30:
                return 80
            if days >= 14:
                return 70
            return 60
        if days >= 90:
            return 150
        if days >= 30:
            return 120
        return 100


    def get_selection_output_range(days: int) -> str:
        try:
            days = int(days)
        except (TypeError, ValueError):
            days = 7
        if days >= 365:
            return "9～12"
        if days >= 180:
            return "9～12"
        if days >= 90:
            return "9～12"
        if days >= 30:
            return "6～9"
        if days >= 14:
            return "6～9"
        return "3～6"


    def infer_preliminary_type(candidate: dict) -> str:
        text = _candidate_selection_text(candidate)
        if _is_standard_update_candidate(f"{text} {candidate.get('date', '')}", require_url=True):
            return "規範更新"
        gate_info = evaluate_category_gates(candidate)
        return gate_info.get("primary_category", "excluded")


    def build_candidate_flags(candidate: dict) -> list[str]:
        text = _candidate_selection_text(candidate)
        flags: list[str] = []
        information_issue = _information_quality_issue(candidate)
        if candidate.get("source_tier") == "A_official":
            flags.append("official_source")
        if candidate.get("source_tier") == "B_professional":
            flags.append("professional_source")
        if candidate.get("source_tier") == "D_proxy_low_value":
            flags.append("low_value_proxy_or_page")
        if _domain_from_url(_effective_source_url(candidate)):
            flags.append("source_domain_detected")
        if "news.google.com" in _domain_from_url(candidate.get("url", "")):
            flags.append("google_news_proxy")
            if not (candidate.get("source_domain") or _original_source_domain(
                candidate.get("source", ""),
                candidate.get("url", ""),
                candidate.get("source_href", ""),
                candidate.get("query", ""),
            )):
                flags.append("source_domain_unresolved")
        if _candidate_date_obj(candidate.get("date", "")):
            flags.append("date_detected")

        if _candidate_urban_rail_gate(candidate):
            flags.append("urban_rail")
        if _technical_system_gate(candidate):
            flags.append("technical_or_system_detail")
        if _trusted_source_title_technical_signal(candidate):
            flags.append("trusted_title_technical_signal")
        if _passes_technical_triad(candidate):
            flags.append("core_metro_technical_content")
        if _is_project_only_technical_candidate(candidate):
            flags.append("project_only_without_technical_detail")
        if _passes_major_accident_gate(candidate):
            flags.append("incident_or_safety_signal")
        if _passes_high_value_policy_gate(candidate):
            flags.append("high_value_policy")
        if _passes_operational_dispute_gate(candidate):
            flags.append("operational_dispute_gate")
        if _passes_operational_dispute_secondary_gate(candidate):
            flags.append("operational_dispute_secondary_gate")
        if _is_low_value_ceremonial_candidate(candidate):
            flags.append("low_value_ceremonial")
        if _contains_any_term(text, LOW_VALUE_POLICY_TERMS) or information_issue in {"日常服務推播", "低價值路線公告"}:
            flags.append("low_value_service_notice")
        if _has_low_value_official_notice(candidate):
            flags.append("low_value_official_notice")
        if _has_procurement_list_notice(candidate):
            flags.append("procurement_list_notice")
        if _is_financial_market_candidate(candidate):
            flags.append("financial_market_content")
        if _contains_any_term(text, EQUIPMENT_FAILURE_TERMS):
            flags.append("equipment_failure_not_tech")
        if _is_security_or_crime_candidate(candidate):
            flags.append("security_or_crime_context")
        if _contains_any_term(text, PROPERTY_OR_CAMPUS_DEVELOPMENT_TERMS):
            flags.append("property_or_campus_development")
        if _contains_any_term(text, GENERIC_TEST_WITHOUT_TECH_TERMS):
            flags.append("generic_testing_notice")
        if _has_general_rail_exclusion(candidate):
            flags.append("general_rail_exclusion")
        if information_issue == "摘要資訊不足":
            flags.append("insufficient_information")
        if len(candidate.get("title", "")) < 20:
            flags.append("short_title")
        if len(candidate.get("snippet", "")) < 80:
            flags.append("short_snippet")
        return flags


    def score_news_candidate(candidate: dict) -> dict:
        text = _candidate_selection_text(candidate)
        gate_info = evaluate_category_gates(candidate)
        primary_category = gate_info.get("primary_category", "excluded")
        score = 50
        reasons: list[str] = []
        tier = candidate.get("source_tier", "C_media")
        if tier == "A_official":
            score += 20
            reasons.append("官方來源 +20")
        elif tier == "B_professional":
            score += 14
            reasons.append("專業鐵道媒體 +14")
        elif tier == "C_media":
            score -= 4
            reasons.append("一般媒體 -4")
        elif tier == "D_proxy_low_value":
            score -= 25
            reasons.append("低價值頁面/代理來源 -25")

        if _candidate_date_obj(candidate.get("date", "")):
            score += 10
            reasons.append("明確日期 +10")
        else:
            score -= 20
            reasons.append("日期不明 -20")

        source_url = _effective_source_url(candidate)
        unresolved_google_proxy = (
            "news.google.com" in _domain_from_url(candidate.get("url", ""))
            and "news.google.com" in _domain_from_url(source_url)
        )
        if _extract_complete_url(source_url):
            score += 8
            reasons.append("完整 URL +8")
        elif _extract_domain_hint(source_url):
            score += 4
            reasons.append("可辨識 domain +4")
        else:
            score -= 15
            reasons.append("URL 不完整 -15")

        if unresolved_google_proxy:
            score -= 10
            reasons.append("Google News proxy unresolved original source -10")

        if _candidate_urban_rail_gate(candidate):
            score += 15
            reasons.append("都市軌道明確 +15")
        else:
            score -= 30
            reasons.append("都市軌道關聯不足 -30")

        if _technical_system_gate(candidate):
            score += 15
            reasons.append("機電/系統技術訊號 +15")
        if _passes_technical_triad(candidate):
            score += 10
            reasons.append("都市軌道+系統設備+技術行為三聯條件 +10")
        elif _trusted_source_title_technical_signal(candidate):
            score += 8
            reasons.append("可信來源標題具系統與技術行為 +8")
        if _passes_major_accident_gate(candidate):
            score += 10
            reasons.append("重大事故嚴重度門檻 +10")
        if _passes_high_value_policy_gate(candidate):
            score += 8
            reasons.append("高價值營運政策門檻 +8")
        if _passes_operational_dispute_gate(candidate):
            score += 8
            reasons.append("營運爭議衝突與影響門檻 +8")
        if _contains_any_term(text, LOW_VALUE_POLICY_TERMS):
            score -= 12
            reasons.append("低價值服務提醒 -12")
        if _is_low_value_ceremonial_candidate(candidate):
            score -= 30
            reasons.append("公益捐贈／典禮／教育推廣且無正式工程內容 -30")
            if score > 64:
                score = 64
                reasons.append("低價值事件僅列 B 級候補，分數上限 64")
        if _has_low_value_official_notice(candidate) and not _has_explicit_technical_system_detail(candidate):
            score -= 35
            reasons.append("低價值官方公告且缺少機電細節 -35")
        if _has_general_rail_exclusion(candidate):
            score -= 40
            reasons.append("一般鐵路/通勤鐵路排除訊號 -40")
        if _is_financial_market_candidate(candidate):
            score -= 45
            reasons.append("股票行情或企業財經分析 -45")
        if any(marker in urlparse(candidate.get("url", "")).path.casefold() for marker in LOW_INFORMATION_PATH_MARKERS):
            score -= 18
            reasons.append("入口/路線/查詢頁路徑 -18")
        if any(term.casefold() in text.casefold() for term in LOW_QUALITY_CONTENT_TERMS):
            score -= 15
            reasons.append("旅遊/SEO/低價值內容 -15")
        if len(candidate.get("title", "")) < 20:
            score -= 5
            reasons.append("標題過短 -5")
        if len(candidate.get("snippet", "")) < 80:
            score -= 8
            reasons.append("摘要過短 -8")

        information_issue = _information_quality_issue(candidate)
        if information_issue == "日常服務推播":
            score -= 25
            reasons.append("日常服務推播 -25")
        elif information_issue == "低價值路線公告":
            score -= 30
            reasons.append("低價值路線公告 -30")
        elif information_issue == "摘要資訊不足":
            score -= 18
            reasons.append("摘要資訊不足 -18")

        flags = build_candidate_flags(candidate)
        good_flags = {"technical_or_system_detail", "incident_or_safety_signal", "high_value_policy", "trusted_title_technical_signal", "operational_dispute_gate"}
        has_good_flag = bool(set(flags).intersection(good_flags))
        if not has_good_flag:
            score_cap = 55 if "short_snippet" in flags else 65
            if score > score_cap:
                score = score_cap
                reasons.append(f"缺少技術/事故/高價值政策旗標，分數上限 {score_cap}")
        if (tier == "D_proxy_low_value" or "low_value_service_notice" in flags) and not _has_explicit_technical_system_detail(candidate):
            if score > 50:
                score = 50
                reasons.append("低價值來源或服務提醒且無技術細節，分數上限 50")
        if primary_category == "excluded":
            score = min(score, 35)
            reasons.append("未通過類別 gate，分數上限 35")
        preliminary_type = "規範更新" if _is_standard_update_candidate(f"{text} {candidate.get('date', '')}", require_url=True) else primary_category
        temp_candidate = dict(candidate, python_score=max(0, min(100, score)), primary_category=primary_category)
        return {
            "python_score": max(0, min(100, score)),
            "score_reason": "；".join(reasons),
            "candidate_flags": flags,
            "preliminary_type": preliminary_type,
            "short_snippet": _shorten(candidate.get("snippet", ""), CANDIDATE_SNIPPET_CHARS),
            "source_domain": candidate.get("source_domain") or _normalize_source_domain(_domain_from_url(_effective_source_url(candidate))),
            "source_domain_normalized": candidate.get("source_domain_normalized") or candidate.get("source_domain") or _normalize_source_domain(_domain_from_url(_effective_source_url(candidate))),
            "source_domain_raw": candidate.get("source_domain_raw") or _domain_from_url(candidate.get("source_href") or candidate.get("url", "")),
            "category_gates": gate_info.get("category_gates", {}),
            "category_gate_reasons": gate_info.get("category_gate_reasons", {}),
            "canonical_tags": gate_info.get("canonical_tags", []),
            "primary_category": primary_category,
            "alternative_category_flags": gate_info.get("alternative_category_flags", []),
            "candidate_level": _candidate_level(temp_candidate, score),
            "urban_rail_gate": _candidate_urban_rail_gate(candidate),
            "technical_triplet_status": "pass" if _passes_technical_triad(candidate) else "fail",
            "accident_severity_score": 80 if _passes_major_accident_gate(candidate) else (35 if _contains_any_term(text, ACCIDENT_SIGNAL_TERMS + SAFETY_INCIDENT_DETAIL_TERMS) else 0),
        }


    def _candidate_score_fingerprint(candidate: dict) -> tuple:
        return (
            candidate.get("title", ""),
            candidate.get("snippet", ""),
            candidate.get("date", ""),
            candidate.get("source", ""),
            candidate.get("url", ""),
            candidate.get("source_href", ""),
            candidate.get("source_tier", ""),
            candidate.get("source_quality", ""),
        )


    def annotate_candidate_for_scheme_d(candidate: dict, exclude_reason: str = "", profile_timings: dict | None = None) -> dict:
        enriched = dict(candidate)
        scoring_started = time.perf_counter()
        score_fingerprint = _candidate_score_fingerprint(enriched)
        cached_score = (
            enriched.get("_score_cache")
            if enriched.get("_score_cache_fingerprint") == score_fingerprint
            else None
        )
        if cached_score:
            score_payload = dict(cached_score)
        else:
            score_payload = score_news_candidate(enriched)
            enriched["_score_cache"] = dict(score_payload)
            enriched["_score_cache_fingerprint"] = score_fingerprint
        _profile_timing_add(profile_timings, "scoring", time.perf_counter() - scoring_started)
        enriched.update(score_payload)
        enriched["exclude_reason"] = exclude_reason
        enriched["final_exclude_reason"] = exclude_reason or enriched.get("preliminary_reject_reason", "")
        enriched["candidate_id"] = enriched.get("candidate_id") or enriched.get("id", "")
        enriched["search_family"] = enriched.get("search_family") or _search_family_from_query(enriched.get("query", ""))
        enriched["search_query"] = enriched.get("search_query") or enriched.get("query", "")
        enriched["search_language"] = enriched.get("search_language") or _search_language_from_query(enriched.get("query", ""))
        enriched["source_domain_normalized"] = enriched.get("source_domain_normalized") or _normalize_source_domain(enriched.get("source_domain", ""))
        fingerprint_started = time.perf_counter()
        enriched["event_fingerprint"] = build_event_fingerprint(enriched)
        _profile_timing_add(profile_timings, "event_fingerprint", time.perf_counter() - fingerprint_started)
        enriched["duplicate_of"] = enriched.get("duplicate_of", "")
        enriched["selection_stage"] = enriched.get("selection_stage", "excluded" if exclude_reason else "candidate_pool")
        return enriched


    def build_candidate_card(candidate: dict) -> dict:
        source_url = _effective_source_url(candidate)
        return {
            "id": candidate.get("id", ""),
            "candidate_id": candidate.get("candidate_id", candidate.get("id", "")),
            "date": candidate.get("date", ""),
            "title": candidate.get("title", ""),
            "search_family": candidate.get("search_family", ""),
            "search_query": candidate.get("search_query", candidate.get("query", "")),
            "search_language": candidate.get("search_language", ""),
            "query_region": candidate.get("query_region", ""),
            "source_display": candidate.get("source_display", candidate.get("source", "")),
            "source_domain_raw": candidate.get("source_domain_raw", ""),
            "source_domain_normalized": candidate.get("source_domain_normalized", candidate.get("source_domain", "")),
            "source_domain": candidate.get("source_domain") or _domain_from_url(source_url),
            "source_tier": candidate.get("source_tier", ""),
            "source_type": candidate.get("source_type", ""),
            "source_verb": candidate.get("source_verb", ""),
            "region": candidate.get("region", "未判定"),
            "page_type": candidate.get("page_type", ""),
            "page_type_reason": candidate.get("page_type_reason", ""),
            "date_validation": candidate.get("date_validation", ""),
            "urban_rail_gate": candidate.get("urban_rail_gate", ""),
            "canonical_tags": candidate.get("canonical_tags", []),
            "category_gates": candidate.get("category_gates", {}),
            "category_gate_reasons": candidate.get("category_gate_reasons", {}),
            "primary_category": candidate.get("primary_category", ""),
            "alternative_category_flags": candidate.get("alternative_category_flags", []),
            "accident_severity_score": candidate.get("accident_severity_score", 0),
            "technical_triplet_status": candidate.get("technical_triplet_status", ""),
            "candidate_level": candidate.get("candidate_level", ""),
            "preliminary_type": candidate.get("preliminary_type", infer_preliminary_type(candidate)),
            "short_snippet": candidate.get("short_snippet", _shorten(candidate.get("snippet", ""), CANDIDATE_SNIPPET_CHARS)),
            "url": source_url,
            "python_score": candidate.get("python_score", 0),
            "score_reason": candidate.get("score_reason", ""),
            "candidate_flags": candidate.get("candidate_flags", []),
            "event_fingerprint": candidate.get("event_fingerprint", {}),
            "supplemental_sources": candidate.get("supplemental_sources", []),
            "event_source_merge_count": candidate.get("event_source_merge_count", 0),
            "duplicate_of": candidate.get("duplicate_of", ""),
            "selection_stage": candidate.get("selection_stage", ""),
            "final_exclude_reason": candidate.get("final_exclude_reason", ""),
        }


    def _is_low_value_policy_candidate(candidate: dict) -> bool:
        text = f"{candidate.get('title', '')} {candidate.get('snippet', '')} {candidate.get('source', '')}"
        has_low = _contains_any_term(text, LOW_VALUE_POLICY_TERMS)
        has_high = _passes_high_value_policy_gate(candidate)
        return has_low and not has_high


    def rebalance_selected_candidates(selected: list[dict]) -> list[dict]:
        if lookback_int != 7 or "營運政策" not in selected_types:
            return selected
        balanced: list[dict] = []
        policy_count = 0
        for candidate in selected:
            if candidate.get("classification") != "營運政策":
                balanced.append(candidate)
                continue
            if _is_low_value_policy_candidate(candidate):
                candidate = dict(candidate)
                candidate["selected_reason"] = (
                    f"{candidate.get('selected_reason', '')}；因屬一般服務公告，週報中降權。"
                ).strip("；")
                if policy_count >= 3:
                    continue
            if policy_count >= 5:
                continue
            policy_count += 1
            balanced.append(candidate)
        return balanced


    def _selection_target_range(days: int) -> tuple[int, int]:
        try:
            days = int(days)
        except (TypeError, ValueError):
            days = 7
        if days >= 365:
            return 9, 12
        if days >= 180:
            return 9, 12
        if days >= 90:
            return 9, 12
        if days >= 30:
            return 6, 9
        if days >= 14:
            return 6, 9
        return 3, 6


    def _selection_classification(candidate: dict) -> str:
        if candidate.get("classification") == "excluded" or candidate.get("primary_category") == "excluded":
            return "excluded"
        primary_category = candidate.get("primary_category")
        if primary_category in ADVANCED_TYPES:
            return primary_category
        inferred_type = infer_preliminary_type(candidate)
        if inferred_type in ADVANCED_TYPES:
            return inferred_type
        preliminary_type = candidate.get("preliminary_type")
        if preliminary_type in ADVANCED_TYPES:
            return preliminary_type
        return "excluded"


    def _has_source_reference(candidate: dict) -> bool:
        source_url = _effective_source_url(candidate)
        return bool(_extract_complete_url(source_url) or candidate.get("source_domain") or _extract_domain_hint(source_url))


    def _selection_good_flag_count(candidate: dict) -> int:
        flags = set(candidate.get("candidate_flags", []) or [])
        return sum(1 for flag in ("technical_or_system_detail", "incident_or_safety_signal", "high_value_policy", "core_metro_technical_content", "operational_dispute_gate") if flag in flags)


    def _selection_bad_flag_count(candidate: dict) -> int:
        flags = set(candidate.get("candidate_flags", []) or [])
        return sum(1 for flag in (
            "low_value_service_notice", "insufficient_information", "short_snippet",
            "low_value_official_notice", "procurement_list_notice", "general_rail_exclusion",
        ) if flag in flags)


    def _candidate_month_key(candidate: dict) -> str:
        date_obj = _candidate_date_obj(candidate.get("date", ""))
        return date_obj.strftime("%Y-%m") if date_obj else "日期未知"


    def _candidate_system_theme(candidate: dict) -> str:
        text = f"{candidate.get('title', '')} {candidate.get('snippet', '')} {candidate.get('source', '')}"
        theme_terms = [
            ("號誌與列車控制", ["cbtc", "signalling", "signaling", "signal", "train control", "line modernization", "line modernisation", "metro modernization", "metro modernisation", "modernization", "modernisation", "號誌", "信號"]),
            ("自動化與無人駕駛", ["driverless", "automation", "automated", "unattended train", "自動", "無人"]),
            ("車輛與車隊更新", ["rolling stock", "fleet", "trainset", "new train", "train cars", "two-car sets", "two car sets", "automated metros", "metro trains", "8000 series trains", "車輛", "列車"]),
            ("月臺門與車站設備", ["platform screen door", "platform doors", "psd", "elevator", "escalator", "月臺門", "月台門", "電梯", "電扶梯"]),
            ("供電與能源管理", ["power supply", "traction power", "substation", "third rail", "energy", "供電", "牽引", "變電", "能源"]),
            ("通訊、資安與資料治理", ["communications", "telecom", "radio", "5g", "lte", "cyber", "data", "通訊", "資安", "資料"]),
            ("維修監測與影像分析", ["maintenance", "monitoring", "condition monitoring", "video", "camera", "ai", "omc", "overhaul", "life cycle management", "life-cycle management", "維修", "監測", "影像", "AI"]),
            ("軌道與機廠設備", ["track renewal", "track lubrication", "lubricator", "wheel lathe", "depot", "operations and maintenance centre", "operations and maintenance center", "軌道更新", "機廠"]),
            ("AFC 與票務系統", ["afc", "ticketing", "fare gate", "fare", "票務", "票閘", "票價"]),
        ]
        for label, terms in theme_terms:
            if _contains_any_term(text, terms):
                return label
        return candidate.get("classification") or candidate.get("preliminary_type") or "未分類"


    def _candidate_operator_key(candidate: dict) -> str:
        source_url = _effective_source_url(candidate)
        hosts = [
            candidate.get("source_domain", ""),
            _domain_from_url(source_url),
            _domain_from_url(candidate.get("source_href", "")),
            _domain_from_url(candidate.get("url", "")),
        ]
        for host in hosts:
            for domain, key in OPERATOR_DOMAIN_KEYS.items():
                if host and _host_matches(host, domain):
                    return key
        text = _candidate_selection_text(candidate)
        text_lower = text.casefold()
        if "toronto subway" in text_lower and re.search(r"\bline\s*2\b", text_lower):
            return "ttc"
        for key, terms in OPERATOR_TEXT_KEYS:
            if _contains_any_term(text, terms):
                return key
        return ""


    def _candidate_incident_type(candidate: dict) -> str:
        text = _candidate_selection_text(candidate)
        incident_terms = [
            ("tram_collision", ["tram", "streetcar", "collision", "crash", "hit", "rammed", "電車", "路面電車", "撞擊", "碰撞"]),
            ("derailment", ["derailment", "derailed", "entgleist", "出軌", "脫軌"]),
            ("power_supply", ["power outage", "power failure", "traction power", "third rail", "供電", "牽引", "第三軌"]),
            ("signal_or_switch", ["signal failure", "signalling", "signaling", "switch failure", "points failure", "號誌", "信號", "轉轍器", "道岔"]),
            ("platform_door", ["platform screen door", "platform door", "psd", "月臺門", "月台門"]),
            ("service_disruption", ["service suspension", "disruption", "suspended", "停駛", "營運中斷", "重大中斷"]),
            ("security", SECURITY_OR_CRIME_TERMS),
        ]
        for label, terms in incident_terms:
            if _contains_any_term(text, terms):
                return label
        return _candidate_system_theme(candidate)


    def _candidate_injury_band(candidate: dict) -> str:
        text = _candidate_selection_text(candidate)
        if _contains_any_term(text, ["fatal", "death", "killed", "死亡"]):
            return "fatality"
        match = re.search(
            r"\b(\d{1,3})\s*(?:people|persons|passengers|人)?\s*(?:were\s+)?injured\b",
            text,
            flags=re.IGNORECASE,
        )
        if match:
            number = int(match.group(1))
            return "1" if number == 1 else "2-9" if number < 10 else "10+"
        if _contains_any_term(text, ["dozens injured", "dozens of people injured", "multiple injuries", "多人受傷", "數十人受傷"]):
            return "10+"
        if _contains_any_term(text, ["serious injury", "serious injuries", "hospitalized", "hospitalised", "重傷", "送醫"]):
            return "serious_or_hospitalized"
        return "none"


    def _injury_bands_conflict(left: dict, right: dict) -> bool:
        bands = {
            _candidate_injury_band(left),
            _candidate_injury_band(right),
        }
        return "fatality" in bands and len(bands) > 1


    def _candidate_action_key(candidate: dict) -> str:
        text = _candidate_selection_text(candidate)
        if _contains_any_term(text, ["signalling", "signaling", "train control", "號誌", "信號"]) and _contains_any_term(text, [
            "signalling upgrade", "signaling upgrade", "digital signalling", "digital signaling",
            "capacity increase", "increase capacity", "boost capacity", "modernise", "modernize",
            "modernisation", "modernization", "號誌升級", "信號升級",
        ]):
            return "signalling_upgrade"
        action_terms = [
            ("accident", ACCIDENT_SIGNAL_TERMS + SAFETY_INCIDENT_DETAIL_TERMS),
            ("strike_or_dispute", DISPUTE_SIGNAL_TERMS),
            ("order", ["order", "ordered", "procurement", "採購", "訂購"]),
            ("enter_service", ["enter service", "entered service", "go into service", "投入營運"]),
            ("upgrade", ["upgrade", "modernization", "modernisation", "renewal", "replacement", "升級", "更新", "汰換", "現代化"]),
            ("testing", ["test", "testing", "trial", "commissioning", "測試", "試運轉"]),
            ("maintenance", ["maintenance", "overhaul", "life-cycle", "asset management", "維修", "翻修", "資產管理"]),
            ("opening_or_policy", HIGH_VALUE_POLICY_GATE_TERMS),
        ]
        for label, terms in action_terms:
            if _contains_any_term(text, terms):
                return label
        return "event"


    def _canonical_event_geo(candidate: dict) -> str:
        specific = _candidate_specific_event_location(candidate)
        region = _canonical_candidate_region(candidate)
        country_keys = {
            "美國": "united-states", "加拿大": "canada", "德國": "germany", "英國": "united-kingdom",
            "法國": "france", "義大利": "italy", "新加坡": "singapore", "日本": "japan",
            "韓國": "south-korea", "香港": "hong-kong", "澳洲": "australia", "瑞士": "switzerland",
        }
        city_country = {
            "austin": "united-states", "washington": "united-states", "new york": "united-states",
            "toronto": "canada", "vancouver": "canada", "berlin": "germany",
            "berlin-adlershof": "germany", "northern-ireland": "united-kingdom",
            "gelsenkirchen": "germany",
        }
        if not specific:
            specific = {
                "ttc": "toronto",
                "wmata": "washington",
                "mta": "new york",
                "bvg": "berlin",
            }.get(_candidate_operator_key(candidate), "")
        if specific:
            country = city_country.get(specific) or country_keys.get(region, "")
            return f"{country}/{specific}" if country else specific
        return country_keys.get(region, str(region or "").casefold())


    def build_event_fingerprint(candidate: dict) -> dict:
        analysis_cache = _candidate_analysis_cache(candidate)
        cached = analysis_cache.get("event_fingerprint")
        if isinstance(cached, dict):
            return dict(cached)
        date_obj = _candidate_date_obj(candidate.get("date", ""))
        date_bucket = ""
        if date_obj:
            bucket_start = date_obj - datetime.timedelta(days=date_obj.toordinal() % 7)
            date_bucket = bucket_start.isoformat()
        result = {
            "operator_key": _candidate_operator_key(candidate),
            "geo_key": _canonical_event_geo(candidate),
            "asset_key": _candidate_system_theme(candidate),
            "action_key": _candidate_action_key(candidate),
            "incident_key": _candidate_incident_type(candidate),
            "injury_band": _candidate_injury_band(candidate),
            "category_key": candidate.get("classification") or candidate.get("primary_category") or candidate.get("preliminary_type", ""),
            "date_bucket": date_bucket,
        }
        analysis_cache["event_fingerprint"] = dict(result)
        return result


    def _candidate_specific_event_location(candidate: dict) -> str:
        text = _candidate_selection_text(candidate).casefold()
        priority_locations = [
            ("austin", ["austin transit partnership", "austin light rail", "austin"]),
            ("berlin-adlershof", ["adlershof"]),
            ("basel", ["basel", "巴塞爾"]),
            ("leipzig", ["leipzig", "萊比錫"]),
            ("houston", ["houston", "休士頓", "休斯頓"]),
            ("vancouver", ["vancouver", "broadway subway", "溫哥華"]),
            ("toronto", ["toronto", "finch west", "多倫多"]),
            ("northern-ireland", ["northern ireland", "belfast", "北愛爾蘭", "貝爾法斯特"]),
            ("gelsenkirchen", ["gelsenkirchen", "蓋爾森基興"]),
            ("berlin", ["berlin", "柏林"]),
        ]
        for canonical, terms in priority_locations:
            if any(term.casefold() in text for term in terms):
                return canonical
        for term in EVENT_LOCATION_TERMS:
            if term.casefold() in text:
                return term.casefold()
        return ""


    def _candidate_event_location(candidate: dict) -> str:
        specific = _candidate_specific_event_location(candidate)
        if specific:
            return specific
        return str(candidate.get("region", "") or "").casefold()


    def _event_date_close(left: dict, right: dict, days: int = 3) -> bool:
        left_date = _candidate_date_obj(left.get("date", ""))
        right_date = _candidate_date_obj(right.get("date", ""))
        if not left_date or not right_date:
            return True
        return abs((left_date - right_date).days) <= days


    def _event_similarity_text(candidate: dict) -> str:
        text = _candidate_selection_text(candidate)
        text = _strip_source_name_noise(text)
        text = re.sub(r"https?://\S+", " ", text)
        text = re.sub(r"\b(20\d{2})[-/]\d{1,2}[-/]\d{1,2}\b", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.casefold().strip()


    def _is_project_series_candidate(candidate: dict) -> bool:
        return _contains_any_term(_candidate_selection_text(candidate), PROJECT_SERIES_TERMS)


    def _candidate_project_stage(candidate: dict) -> str:
        text = _candidate_selection_text(candidate)
        for stage, terms in PROJECT_STAGE_GROUPS.items():
            if _contains_any_term(text, terms):
                return stage
        return ""


    def _same_project_stage_or_unspecified(left: dict, right: dict) -> bool:
        left_stage = _candidate_project_stage(left)
        right_stage = _candidate_project_stage(right)
        return not left_stage or not right_stage or left_stage == right_stage


    def _duplicate_event_reason(candidate: dict, selected_item: dict) -> str:
        if int(lookback_int) in ADVANCED_LOOKBACK_OPTIONS and _is_project_series_candidate(candidate) and _is_project_series_candidate(selected_item):
            return "同一城市/地點、相同系統主題與相近專案階段，長期回顧視為同一專案系列。"
        if candidate.get("classification") == "重大事故":
            return "同一城市/地點、相近日期與相同事故/安全主題，事件級重複排除。"
        return "相同城市/地點、相近日期與相同系統主題，事件級重複排除。"


    def _is_same_report_event(candidate: dict, selected_item: dict) -> bool:
        candidate_fp = build_event_fingerprint(candidate)
        selected_fp = build_event_fingerprint(selected_item)
        candidate_operator = candidate_fp.get("operator_key", "")
        selected_operator = selected_fp.get("operator_key", "")
        if candidate_operator and selected_operator and candidate_operator != selected_operator:
            return False
        candidate_geo = candidate_fp.get("geo_key", "")
        selected_geo = selected_fp.get("geo_key", "")
        if candidate_geo and selected_geo and candidate_geo != selected_geo:
            return False
        candidate_asset = candidate_fp.get("asset_key", "")
        selected_asset = selected_fp.get("asset_key", "")
        if candidate_asset and selected_asset and candidate_asset != selected_asset:
            return False
        candidate_lines = _dedupe_route_line_tokens(candidate)
        selected_lines = _dedupe_route_line_tokens(selected_item)
        if candidate_lines and selected_lines and candidate_lines.isdisjoint(selected_lines):
            return False

        is_accident = "重大事故" in {
            candidate.get("classification"), selected_item.get("classification"),
            candidate.get("primary_category"), selected_item.get("primary_category"),
        }
        if is_accident and _injury_bands_conflict(candidate, selected_item):
            return False
        date_close = _event_date_close(candidate, selected_item, days=1 if is_accident else 3)
        if (
            date_close
            and candidate_geo
            and candidate_geo == selected_geo
            and candidate_asset
            and candidate_asset == selected_asset
            and candidate_fp.get("action_key") == selected_fp.get("action_key")
            and (candidate_operator == selected_operator or not candidate_operator or not selected_operator)
        ):
            return True

        if _dedupe_titles_conflict_on_entities(candidate, selected_item):
            return False
        candidate_location = _candidate_event_location(candidate)
        selected_location = _candidate_event_location(selected_item)
        similarity = difflib.SequenceMatcher(
            None,
            _event_similarity_text(candidate),
            _event_similarity_text(selected_item),
        ).ratio()
        candidate_specific_location = _candidate_specific_event_location(candidate)
        selected_specific_location = _candidate_specific_event_location(selected_item)
        same_specific_location = bool(candidate_specific_location and selected_specific_location and candidate_specific_location == selected_specific_location)
        if candidate_specific_location and selected_specific_location and candidate_specific_location != selected_specific_location:
            return False
        if int(lookback_int) in ADVANCED_LOOKBACK_OPTIONS and same_specific_location:
            if is_accident and (date_close or similarity >= 0.70):
                return True
            if _is_project_series_candidate(candidate) and _is_project_series_candidate(selected_item) and _same_project_stage_or_unspecified(candidate, selected_item):
                return True
            if similarity >= 0.76:
                return True
        if not date_close:
            return False
        if same_specific_location:
            return True
        return similarity >= 0.62


    def _is_duplicate_selected_event(candidate: dict, selected: list[dict]) -> bool:
        return any(_is_same_report_event(candidate, item) for item in selected)


    def _python_selection_sort_key(candidate: dict) -> tuple:
        return (
            -int(candidate.get("python_score", 0) or 0),
            _source_tier_rank(candidate.get("source_tier", "C_media")),
            -_date_sort_key(candidate),
            -int(_has_source_reference(candidate)),
            -_selection_good_flag_count(candidate),
            _selection_bad_flag_count(candidate),
            int(candidate.get("id", 0) or 0),
        )


    def _python_selection_dynamic_key(candidate: dict, selected: list[dict]) -> tuple:
        base_key = _python_selection_sort_key(candidate)
        if int(lookback_int) not in ADVANCED_LOOKBACK_OPTIONS:
            return base_key
        selected_locations = [_candidate_specific_event_location(item) or _candidate_event_location(item) for item in selected]
        selected_regions = [item.get("region", "") for item in selected]
        selected_months = [_candidate_month_key(item) for item in selected]
        selected_themes = [_candidate_system_theme(item) for item in selected]
        selected_incidents = [_candidate_incident_type(item) for item in selected]
        selected_operators = [_candidate_operator_key(item) for item in selected if _candidate_operator_key(item)]
        candidate_location = _candidate_specific_event_location(candidate) or _candidate_event_location(candidate)
        candidate_operator = _candidate_operator_key(candidate)
        operator_penalty = selected_operators.count(candidate_operator) if int(lookback_int) >= 365 and candidate_operator else 0
        diversity_penalty = (
            operator_penalty,
            selected_locations.count(candidate_location),
            selected_regions.count(candidate.get("region", "")),
            selected_incidents.count(_candidate_incident_type(candidate)),
            selected_months.count(_candidate_month_key(candidate)),
            selected_themes.count(_candidate_system_theme(candidate)),
        )
        return base_key[:2] + diversity_penalty + base_key[2:]


    def _long_term_diversity_skip_reason(candidate: dict, selected: list[dict]) -> str:
        if int(lookback_int) not in ADVANCED_LOOKBACK_OPTIONS or len(selected) < 6:
            return ""
        classification = _selection_classification(candidate)
        location = _candidate_specific_event_location(candidate) or _candidate_event_location(candidate)
        region = candidate.get("region", "")
        theme = _candidate_system_theme(candidate)
        incident_type = _candidate_incident_type(candidate)
        operator = _candidate_operator_key(candidate)
        same_location_count = sum(
            1 for item in selected
            if (_candidate_specific_event_location(item) or _candidate_event_location(item)) == location
            and _selection_classification(item) == classification
        )
        same_region_incident_count = sum(
            1 for item in selected
            if item.get("region", "") == region
            and _candidate_incident_type(item) == incident_type
            and _selection_classification(item) == classification
        )
        same_theme_count = sum(
            1 for item in selected
            if _candidate_system_theme(item) == theme
            and _selection_classification(item) == classification
        )
        same_operator_count = sum(
            1 for item in selected
            if operator and _candidate_operator_key(item) == operator
        )
        same_operator_theme_count = sum(
            1 for item in selected
            if operator
            and _candidate_operator_key(item) == operator
            and _candidate_system_theme(item) == theme
        )
        if int(lookback_int) >= 365 and operator:
            if theme and same_operator_theme_count >= 1:
                return "年度代表性限制：同一營運機構相同設備/系統主題已入選，避免相似設備案件重複占用篇幅。"
            if same_operator_count >= 2:
                return "年度代表性限制：同一營運機構已達 2 則，避免年度回顧過度集中於單一營運者。"
        if int(lookback_int) >= 365 and theme and same_theme_count >= 3:
            return "年度代表性限制：相似設備/系統主題已達 3 則，候選不足時可少列。"
        if classification == "重大事故":
            if location and same_location_count >= 2:
                return "長期代表性限制：同一城市/地點重大事故已達 2 則，避免年度回顧過度集中。"
            if region and incident_type and same_region_incident_count >= 2:
                return "長期代表性限制：同一國家/地區相同事故型態已達 2 則，避免單一事故類型過度占用篇幅。"
            if theme and same_theme_count >= 4:
                return "長期代表性限制：相同系統主題重大事故已達 4 則，候選不足時可少列。"
        if _is_project_series_candidate(candidate) and location and theme:
            same_project_theme_count = sum(
                1 for item in selected
                if (_candidate_specific_event_location(item) or _candidate_event_location(item)) == location
                and _candidate_system_theme(item) == theme
                and _is_project_series_candidate(item)
            )
            if same_project_theme_count >= 2:
                return "長期代表性限制：同一城市/系統專案系列已達 2 則，避免宣傳稿或相近里程碑重複占用篇幅。"
        return ""


    def _python_candidate_allowed_for_scope(candidate: dict) -> bool:
        if is_global_scope:
            return True
        region = _canonical_candidate_region(candidate)
        if region in active_regions:
            return True
        text = f"{candidate.get('title', '')} {candidate.get('snippet', '')} {candidate.get('source', '')} {candidate.get('url', '')} {candidate.get('source_href', '')}"
        looks_like_standard = candidate.get("classification") == "規範更新" or _is_standard_update_candidate(f"{text} {candidate.get('date', '')}", require_url=True)
        if region in {"國際", "國際研究", "未判定"} and _is_allowed_international_candidate(candidate, text, looks_like_standard):
            candidate["region"] = "國際"
            return True
        return False


    def _is_low_value_python_selection_candidate(candidate: dict) -> bool:
        flags = set(candidate.get("candidate_flags", []) or [])
        score = int(candidate.get("python_score", 0) or 0)
        has_good_signal = _has_good_report_signal(candidate)
        has_technical_detail = _has_explicit_technical_system_detail(candidate)
        text = _candidate_selection_text(candidate)
        classification = _selection_classification(candidate)
        if classification == "excluded":
            return True
        if _is_financial_market_candidate(candidate):
            return True
        if candidate.get("source_tier") == "D_proxy_low_value":
            return True
        if classification == "技術新知" and not _passes_technical_triad(dict(candidate, classification="技術新知")):
            return True
        if classification == "重大事故" and not _passes_major_accident_gate(dict(candidate, classification="重大事故")):
            return True
        if classification == "營運政策" and not _passes_high_value_policy_gate(dict(candidate, classification="營運政策")):
            return True
        if classification == "營運爭議" and not _passes_operational_dispute_gate(dict(candidate, classification="營運爭議")):
            return True
        if _is_security_or_crime_candidate(candidate) and not _has_major_security_rail_impact(candidate):
            return True
        if _contains_any_term(text, EQUIPMENT_FAILURE_TERMS) and classification == "技術新知":
            return True
        if _is_low_value_long_term_candidate(candidate):
            return True
        if "general_rail_exclusion" in flags or _has_general_rail_exclusion(candidate):
            return True
        if _contains_any_term(text, NON_TECH_NEWS_EXCLUDE_TERMS) and not _has_substantive_detail_for_low_value_notice(candidate):
            return True
        if _has_procurement_list_notice(candidate):
            return True
        if _has_low_value_official_notice(candidate) and not _has_substantive_detail_for_low_value_notice(candidate):
            return True
        if "low_value_service_notice" in flags and not has_good_signal:
            return True
        if "low_value_proxy_or_page" in flags and not has_technical_detail:
            return True
        if candidate.get("source_tier") == "D_proxy_low_value" and not has_technical_detail:
            return True
        if "insufficient_information" in flags and not has_good_signal:
            return True
        return score < 45


    def _is_strict_technical_candidate(candidate: dict) -> bool:
        return _is_technical_news_selection_candidate(candidate)


    def _event_source_preference_key(candidate: dict) -> tuple:
        return (
            _source_tier_rank(candidate.get("source_tier", "C_media")),
            _quality_rank(candidate.get("source_quality", "B")),
            1 if "news.google.com" in _domain_from_url(_effective_source_url(candidate)) else 0,
            -int(candidate.get("python_score", 0) or 0),
        )


    def _supplemental_source_record(candidate: dict) -> dict:
        return {
            "title": candidate.get("title", ""),
            "source_display": candidate.get("source_display") or candidate.get("source", ""),
            "source_tier": candidate.get("source_tier", ""),
            "url": _effective_source_url(candidate),
        }


    def _merge_duplicate_event_sources(selected_item: dict, candidate: dict) -> bool:
        incoming_is_preferred = _event_source_preference_key(candidate) < _event_source_preference_key(selected_item)
        existing_copy = dict(selected_item)
        primary = candidate if incoming_is_preferred else selected_item
        supplement = existing_copy if incoming_is_preferred else candidate
        supplemental_sources = list(primary.get("supplemental_sources", []) or [])
        supplemental_sources.extend(supplement.get("supplemental_sources", []) or [])
        supplemental_sources.append(_supplemental_source_record(supplement))
        unique_sources: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for source_row in supplemental_sources:
            key = (str(source_row.get("url", "") or ""), str(source_row.get("title", "") or ""))
            if key not in seen:
                seen.add(key)
                unique_sources.append(source_row)
        if incoming_is_preferred:
            selection_state = {
                key: existing_copy.get(key)
                for key in ("include_in_report", "selected_reason", "selection_stage")
                if key in existing_copy
            }
            selected_item.clear()
            selected_item.update(candidate)
            selected_item.update(selection_state)
        selected_item["supplemental_sources"] = unique_sources
        selected_item["event_source_merge_count"] = len(unique_sources)
        return incoming_is_preferred


    def _take_next_python_candidate(pool: list[dict], selected: list[dict]) -> dict | None:
        while pool:
            candidate = min(pool, key=lambda item: _python_selection_dynamic_key(item, selected))
            pool.remove(candidate)
            duplicate_of = next((item for item in selected if _is_same_report_event(candidate, item)), None)
            if duplicate_of:
                source_replaced = _merge_duplicate_event_sources(duplicate_of, candidate)
                candidate["duplicate_of"] = duplicate_of.get("id", "")
                candidate["selection_stage"] = "duplicate_suppressed"
                try:
                    LAST_PYTHON_SELECTION_DEBUG.setdefault("duplicate_event_records", []).append({
                        "candidate_id": candidate.get("id", ""),
                        "candidate_title": candidate.get("title", ""),
                        "duplicate_of_id": duplicate_of.get("id", ""),
                        "duplicate_of_title": duplicate_of.get("title", ""),
                        "duplicate_event_reason": _duplicate_event_reason(candidate, duplicate_of),
                        "candidate_location": _candidate_specific_event_location(candidate) or _candidate_event_location(candidate),
                        "duplicate_of_location": _candidate_specific_event_location(duplicate_of) or _candidate_event_location(duplicate_of),
                        "candidate_date": candidate.get("date", ""),
                        "duplicate_of_date": duplicate_of.get("date", ""),
                        "candidate_theme": _candidate_system_theme(candidate),
                        "duplicate_of_theme": _candidate_system_theme(duplicate_of),
                        "candidate_fingerprint": build_event_fingerprint(candidate),
                        "duplicate_of_fingerprint": build_event_fingerprint(duplicate_of),
                        "kept_primary_source": duplicate_of.get("source_display") or duplicate_of.get("source", ""),
                        "source_replaced_by_higher_priority": source_replaced,
                        "supplemental_source_count": len(duplicate_of.get("supplemental_sources", []) or []),
                    })
                except Exception:
                    pass
                continue
            diversity_reason = _long_term_diversity_skip_reason(candidate, selected)
            if diversity_reason:
                try:
                    LAST_PYTHON_SELECTION_DEBUG.setdefault("duplicate_event_records", []).append({
                        "candidate_id": candidate.get("id", ""),
                        "candidate_title": candidate.get("title", ""),
                        "duplicate_of_id": "",
                        "duplicate_of_title": "",
                        "duplicate_event_reason": diversity_reason,
                        "candidate_location": _candidate_specific_event_location(candidate) or _candidate_event_location(candidate),
                        "duplicate_of_location": "",
                        "candidate_date": candidate.get("date", ""),
                        "duplicate_of_date": "",
                        "candidate_theme": _candidate_system_theme(candidate),
                        "duplicate_of_theme": "",
                        "candidate_incident_type": _candidate_incident_type(candidate),
                        "candidate_fingerprint": build_event_fingerprint(candidate),
                    })
                except Exception:
                    pass
                continue
            return candidate
        return None


    def _is_hard_excluded_for_borderline(candidate: dict) -> bool:
        text = _candidate_selection_text(candidate)
        if _is_financial_market_candidate(candidate):
            return True
        if candidate.get("source_tier") == "D_proxy_low_value":
            return True
        classification = _selection_classification(candidate)
        if classification == "excluded":
            return True
        if classification == "技術新知" and not _passes_technical_triad(dict(candidate, classification="技術新知")):
            return True
        if classification == "重大事故" and not _passes_major_accident_gate(dict(candidate, classification="重大事故")):
            return True
        if classification == "營運政策" and not _passes_high_value_policy_gate(dict(candidate, classification="營運政策")):
            return True
        if classification == "營運爭議" and not _passes_operational_dispute_gate(dict(candidate, classification="營運爭議")):
            return True
        if _is_security_or_crime_candidate(candidate) and not _has_major_security_rail_impact(candidate):
            return True
        if _is_low_value_long_term_candidate(candidate):
            return True
        if _has_general_rail_exclusion(candidate):
            return True
        if _has_procurement_list_notice(candidate):
            return True
        if _is_airport_people_mover_only_text(text, candidate.get("source", "")):
            return True
        if _contains_any_term(text, GENERAL_RAIL_EXCLUDE_TERMS):
            return True
        if _contains_any_term(text, LOW_REPORT_VALUE_TERMS):
            return True
        if _contains_any_term(text, NON_URBAN_HARD_EXCLUDE_TERMS) and not _contains_any_term(text, URBAN_RAIL_UNAMBIGUOUS_MODE_TERMS):
            return True
        if _contains_any_term(text, [
            "lost property", "delay certificate", "route page", "trip result",
            "contract documents holders list", "mtr e-store", "product page",
            "失物招領", "延誤證明", "標案文件持有人", "商品", "旅遊攻略",
        ]):
            return True
        return False


    def _is_b_level_technical_candidate(candidate: dict) -> bool:
        text = _candidate_selection_text(candidate)
        if candidate.get("classification") != "技術新知":
            return False
        if _is_hard_excluded_for_borderline(candidate):
            return False
        if _contains_any_term(text, NON_TECH_NEWS_EXCLUDE_TERMS):
            return False
        if _is_accident_signal_text(text):
            return False
        if not _candidate_date_obj(candidate.get("date", "")):
            return False
        if not _has_source_reference(candidate):
            return False
        if not _candidate_urban_rail_gate(candidate):
            return False
        if not _passes_technical_triad(candidate):
            return False
        if candidate.get("source_tier") in {"A_official", "B_professional"}:
            return True
        return _contains_any_term(text, MEDIUM_TECHNICAL_DETAIL_TERMS + WEEKLY_BACKFILL_ALLOWED_TERMS)


    def _is_borderline_report_candidate(candidate: dict) -> tuple[bool, str]:
        classification = candidate.get("classification") or _selection_classification(candidate)
        candidate["classification"] = classification
        if classification not in selected_types:
            return False, "類型未勾選"
        if not _python_candidate_allowed_for_scope(candidate):
            return False, "國家/地區不在指定範圍"
        if _is_hard_excluded_for_borderline(candidate):
            return False, "硬排除項"
        flags = set(candidate.get("candidate_flags", []) or [])
        text = _candidate_selection_text(candidate)
        if not _candidate_date_obj(candidate.get("date", "")):
            return False, "日期不明"
        if not _has_source_reference(candidate):
            return False, "來源/URL 不明"
        score = int(candidate.get("python_score", 0) or 0)
        if classification == "重大事故" and score < 62:
            return False, "重大事故候補分數低於 62"
        if classification != "重大事故" and score < 58:
            return False, "B級候補分數低於 58"
        if candidate.get("source_tier") == "C_media" and score < 70:
            return False, "一般媒體候補需較完整內容與較高分數"
        if classification == "技術新知":
            if _is_strict_technical_candidate(candidate):
                return True, "A級技術新知"
            if _is_b_level_technical_candidate(candidate):
                return True, "B級技術新知候補"
            return False, "技術門檻不足"
        if classification == "重大事故":
            if _passes_major_accident_gate(candidate):
                return True, "重大事故嚴重度門檻明確"
            return False, "事故價值不足"
        if classification == "營運政策":
            if _passes_high_value_policy_gate(candidate):
                return True, "具捷運專屬性與系統/路線層級影響"
            return False, "營運政策價值不足"
        if classification == "營運爭議":
            if _passes_operational_dispute_gate(candidate):
                return True, "具明確衝突主體與營運影響"
            return False, "營運爭議衝突或影響不足"
        if classification == "規範更新":
            if _is_standard_update_candidate(f"{text} {candidate.get('date', '')}", require_url=True):
                return True, "規範更新條件完整"
            return False, "規範更新條件不足"
        return False, "未符合候補條件"


    def _selection_lower_bound(days: int) -> int:
        lower, _ = _selection_target_range(days)
        return lower


    def _borderline_cap(days: int) -> int:
        try:
            days = int(days)
        except (TypeError, ValueError):
            days = 7
        if days >= 365:
            return 4
        if days >= 30:
            return 3
        return 2


    def _selection_debug_reset() -> dict:
        debug = dict(REPORT_SELECTION_DEBUG_DEFAULT)
        debug["duplicate_event_records"] = []
        debug["borderline_candidates"] = []
        debug["B_backfill_appended_ids"] = []
        debug["backfill_reason"] = ""
        return debug


    def _qualifying_operational_coverage_candidate(candidate: dict, selected: list[dict]) -> dict | None:
        candidate = dict(candidate)
        classification = _selection_classification(candidate)
        if classification not in {"營運政策", "營運爭議"} or classification not in selected_types:
            return None
        candidate["classification"] = classification
        if candidate.get("source_tier") not in {"A_official", "B_professional"}:
            return None
        if not _candidate_date_obj(candidate.get("date", "")) or not _has_source_reference(candidate):
            return None
        if _is_low_value_python_selection_candidate(candidate):
            return None
        if classification == "營運政策" and not _passes_high_value_policy_gate(candidate):
            return None
        if classification == "營運爭議" and not _passes_operational_dispute_gate(candidate):
            return None
        level = candidate.get("candidate_level") or _candidate_level(candidate)
        if level not in {"A", "B"}:
            return None
        if _is_duplicate_selected_event(candidate, selected):
            return None
        candidate["candidate_level"] = level
        candidate["include_in_report"] = True
        candidate["selection_stage"] = "operational_coverage_protection"
        candidate["selected_reason"] = (
            f"營運議題覆蓋保護：{classification}；level={level}；"
            f"score={candidate.get('python_score', 0)}；tier={candidate.get('source_tier', '')}"
        )
        return candidate


    def _ensure_operational_topic_coverage(
        selected: list[dict],
        model_candidates: list[dict],
        max_items: int,
        debug: dict,
    ) -> list[dict]:
        if not {"營運政策", "營運爭議"}.issubset(set(selected_types)):
            return selected
        if any(item.get("classification") in {"營運政策", "營運爭議"} for item in selected):
            return selected
        debug["operational_coverage_triggered"] = True
        coverage_pool = [
            candidate
            for candidate in (
                _qualifying_operational_coverage_candidate(raw_candidate, selected)
                for raw_candidate in model_candidates or []
            )
            if candidate is not None
        ]
        if not coverage_pool:
            return selected
        coverage_candidate = min(coverage_pool, key=_python_selection_sort_key)
        if len(selected) < max_items:
            selected.append(coverage_candidate)
        else:
            classification_counts = Counter(item.get("classification") for item in selected)
            removable = [
                item
                for item in selected
                if item.get("classification") != "重大事故"
                and not (
                    item.get("classification") == "技術新知"
                    and classification_counts.get("技術新知", 0) <= 1
                )
            ]
            if not removable:
                removable = [item for item in selected if item.get("classification") != "重大事故"]
            if not removable:
                return selected
            removed = min(removable, key=_python_selection_sort_key)
            selected.remove(removed)
            selected.append(coverage_candidate)
            debug["operational_coverage_replaced_id"] = removed.get("id", "")
        debug["operational_coverage_added"] = True
        debug["operational_coverage_category"] = coverage_candidate.get("classification", "")
        return selected


    def _select_from_grouped_pools(grouped: dict[str, list[dict]], max_items: int) -> list[dict]:
        selected: list[dict] = []
        if len(selected_types) <= 1:
            only_type = selected_types[0] if selected_types else ""
            while len(selected) < max_items:
                candidate = _take_next_python_candidate(grouped.get(only_type, []), selected)
                if not candidate:
                    break
                selected.append(candidate)
            return selected

        for category in selected_types:
            if len(selected) >= max_items:
                break
            candidate = _take_next_python_candidate(grouped.get(category, []), selected)
            if candidate:
                selected.append(candidate)

        while len(selected) < max_items:
            added = False
            for category in selected_types:
                if len(selected) >= max_items:
                    break
                candidate = _take_next_python_candidate(grouped.get(category, []), selected)
                if candidate:
                    selected.append(candidate)
                    added = True
            if not added:
                break
        return selected


    def _backfill_borderline_candidates(
        selected: list[dict],
        model_candidates: list[dict],
        min_items: int,
        max_items: int,
        debug: dict,
    ) -> list[dict]:
        selected_ids = {int(item.get("id", 0) or 0) for item in selected}
        shortfall_before = max(0, min_items - len(selected))
        borderline_cap = _borderline_cap(lookback_int)
        debug["shortfall_before_backfill"] = shortfall_before
        debug["B_backfill_triggered"] = shortfall_before > 0
        debug["B_backfill_cap"] = borderline_cap
        debug["B_backfill_append_stage"] = "after_strict_selection_before_rebalance"
        debug["B_backfill_considered_count"] = 0
        debug["B_backfill_appended_ids"] = []
        if shortfall_before <= 0:
            debug["shortfall_after_backfill"] = 0
            debug["backfill_reason"] = "嚴格入選已達目標下限，無需候補。"
            return selected

        borderline_pool: list[dict] = []
        for raw_candidate in model_candidates or []:
            candidate_id = int(raw_candidate.get("id", 0) or 0)
            if candidate_id in selected_ids:
                continue
            candidate = dict(raw_candidate)
            classification = _selection_classification(candidate)
            candidate["classification"] = classification
            allowed, reason = _is_borderline_report_candidate(candidate)
            if not allowed:
                continue
            candidate["selected_reason"] = (
                f"Python 合格候補：{reason}；score={candidate.get('python_score', 0)}；"
                f"tier={candidate.get('source_tier', '')}；flags={','.join(candidate.get('candidate_flags', []) or [])}"
            )
            candidate["include_in_report"] = True
            candidate["borderline_reason"] = reason
            candidate["selection_stage"] = "B_backfill_candidate"
            candidate["candidate_level"] = "B"
            borderline_pool.append(candidate)

        borderline_pool = sorted(borderline_pool, key=_python_selection_sort_key)
        debug["B_backfill_considered_count"] = len(borderline_pool)
        while borderline_pool and len(selected) < min_items and len(selected) < max_items:
            if len(debug["borderline_candidates"]) >= borderline_cap:
                debug["backfill_reason"] = f"B級候補已達本期上限 {borderline_cap} 則。"
                break
            candidate = _take_next_python_candidate(borderline_pool, selected)
            if not candidate:
                break
            selected.append(candidate)
            candidate["selection_stage"] = "B_backfilled_selected"
            selected_ids.add(int(candidate.get("id", 0) or 0))
            debug["B_backfill_appended_ids"].append(int(candidate.get("id", 0) or 0))
            if len(debug["borderline_candidates"]) < 20:
                debug["borderline_candidates"].append(build_candidate_card(candidate) | {"borderline_reason": candidate.get("borderline_reason", "")})

        debug["borderline_added_count"] = len(debug["B_backfill_appended_ids"])
        debug["B_added_count"] = debug["borderline_added_count"]
        debug["shortfall_after_backfill"] = max(0, min_items - len(selected))
        if debug["borderline_added_count"]:
            debug["backfill_reason"] = f"嚴格入選不足 {shortfall_before} 則，已補入合格候補 {debug['borderline_added_count']} 則。"
        elif debug["shortfall_after_backfill"]:
            debug["backfill_reason"] = "嚴格入選不足，且未找到符合日期、來源、都市軌道與報告價值門檻之合格候補。"
        else:
            debug["backfill_reason"] = "候補後已達目標下限。"
        return selected


    def select_candidates_by_python(model_candidates: list[dict]) -> list[dict]:
        global LAST_PYTHON_SELECTION_DEBUG
        LAST_PYTHON_SELECTION_DEBUG = _selection_debug_reset()
        min_items, max_items = _selection_target_range(lookback_int)
        grouped: dict[str, list[dict]] = {category: [] for category in selected_types}
        for raw_candidate in model_candidates or []:
            candidate = dict(raw_candidate)
            classification = _selection_classification(candidate)
            candidate["classification"] = classification
            if classification not in selected_types:
                continue
            if classification == "技術新知" and not _is_strict_technical_candidate(candidate):
                continue
            if not _python_candidate_allowed_for_scope(candidate):
                continue
            if _is_low_value_python_selection_candidate(candidate):
                continue
            candidate["selected_reason"] = (
                f"Python 嚴格規則選題：score={candidate.get('python_score', 0)}；"
                f"tier={candidate.get('source_tier', '')}；flags={','.join(candidate.get('candidate_flags', []) or [])}"
            )
            candidate["include_in_report"] = True
            candidate["selection_stage"] = "A_strict_selected"
            candidate["candidate_level"] = "A"
            grouped.setdefault(classification, []).append(candidate)

        for category in grouped:
            grouped[category] = sorted(grouped[category], key=_python_selection_sort_key)

        selected = _select_from_grouped_pools(grouped, max_items)
        selected = _ensure_operational_topic_coverage(
            selected,
            model_candidates or [],
            max_items,
            LAST_PYTHON_SELECTION_DEBUG,
        )
        LAST_PYTHON_SELECTION_DEBUG["strict_selected_count"] = len(selected)
        selected = _backfill_borderline_candidates(selected, model_candidates or [], min_items, max_items, LAST_PYTHON_SELECTION_DEBUG)
        LAST_PYTHON_SELECTION_DEBUG["final_selected_count"] = len(selected)
        LAST_PYTHON_SELECTION_DEBUG["incident_selected_count"] = sum(1 for item in selected if item.get("classification") == "重大事故")
        LAST_PYTHON_SELECTION_DEBUG["B_added_count"] = LAST_PYTHON_SELECTION_DEBUG.get("borderline_added_count", 0)
        return rebalance_selected_candidates(selected)

    return {
        "_has_high_value_operational_detail": _has_high_value_operational_detail,
        "_has_clear_urban_rail_context": _has_clear_urban_rail_context,
        "_is_airport_people_mover_only_text": _is_airport_people_mover_only_text,
        "_trusted_source_title_technical_signal": _trusted_source_title_technical_signal,
        "_candidate_has_high_value_operational_detail": _candidate_has_high_value_operational_detail,
        "_is_low_value_service_notice_text": _is_low_value_service_notice_text,
        "hard_low_value_candidate_reason": hard_low_value_candidate_reason,
        "_wordish_count": _wordish_count,
        "_information_quality_issue": _information_quality_issue,
        "_is_standards_source": _is_standards_source,
        "_is_standard_update_query": _is_standard_update_query,
        "_is_standard_update_candidate": _is_standard_update_candidate,
        "_is_allowed_international_candidate": _is_allowed_international_candidate,
        "_is_urban_rail_candidate": _is_urban_rail_candidate,
        "_is_tech_news_only_mode": _is_tech_news_only_mode,
        "_is_technical_news_candidate": _is_technical_news_candidate,
        "_compute_candidate_page_type": _compute_candidate_page_type,
        "_candidate_page_type": _candidate_page_type,
        "_prefetch_limit_for_period": _prefetch_limit_for_period,
        "_candidate_prefetch_signal": _candidate_prefetch_signal,
        "prefetch_candidates_before_filter": prefetch_candidates_before_filter,
        "preliminary_filter_candidate": preliminary_filter_candidate,
        "_excluded_candidate_value_reasons": _excluded_candidate_value_reasons,
        "build_top_excluded_valuable_candidates": build_top_excluded_valuable_candidates,
        "_canonical_tags_from_text": _canonical_tags_from_text,
        "_candidate_selection_text": _candidate_selection_text,
        "_candidate_analysis_fingerprint": _candidate_analysis_fingerprint,
        "_candidate_analysis_cache": _candidate_analysis_cache,
        "_cached_candidate_bool": _cached_candidate_bool,
        "_candidate_urban_rail_gate": _candidate_urban_rail_gate,
        "_compute_technical_system_gate": _compute_technical_system_gate,
        "_technical_system_gate": _technical_system_gate,
        "_compute_technical_action_gate": _compute_technical_action_gate,
        "_technical_action_gate": _technical_action_gate,
        "_is_project_only_technical_candidate": _is_project_only_technical_candidate,
        "_compute_passes_technical_triad": _compute_passes_technical_triad,
        "_passes_technical_triad": _passes_technical_triad,
        "_candidate_event_fragments": _candidate_event_fragments,
        "_fragment_has_urban_rail_context": _fragment_has_urban_rail_context,
        "_is_single_person_rail_incident": _is_single_person_rail_incident,
        "_has_single_person_incident_exception": _has_single_person_incident_exception,
        "_compute_passes_major_accident_gate": _compute_passes_major_accident_gate,
        "_passes_major_accident_gate": _passes_major_accident_gate,
        "_compute_passes_operational_dispute_gate": _compute_passes_operational_dispute_gate,
        "_compute_passes_operational_dispute_primary_gate": _compute_passes_operational_dispute_primary_gate,
        "_passes_operational_dispute_primary_gate": _passes_operational_dispute_primary_gate,
        "_compute_passes_operational_dispute_secondary_gate": _compute_passes_operational_dispute_secondary_gate,
        "_passes_operational_dispute_secondary_gate": _passes_operational_dispute_secondary_gate,
        "_passes_operational_dispute_gate": _passes_operational_dispute_gate,
        "_is_dispute_dominant": _is_dispute_dominant,
        "_is_policy_dominant": _is_policy_dominant,
        "_is_short_term_service_notice": _is_short_term_service_notice,
        "_compute_passes_high_value_policy_gate": _compute_passes_high_value_policy_gate,
        "_passes_high_value_policy_gate": _passes_high_value_policy_gate,
        "evaluate_category_gates": evaluate_category_gates,
        "_candidate_level": _candidate_level,
        "_is_accident_signal_text": _is_accident_signal_text,
        "_has_strong_technical_detail_text": _has_strong_technical_detail_text,
        "_has_explicit_technical_system_detail": _has_explicit_technical_system_detail,
        "_has_good_report_signal": _has_good_report_signal,
        "_has_low_value_official_notice": _has_low_value_official_notice,
        "_has_procurement_list_notice": _has_procurement_list_notice,
        "_is_financial_market_candidate": _is_financial_market_candidate,
        "_is_low_value_ceremonial_candidate": _is_low_value_ceremonial_candidate,
        "_is_security_or_crime_candidate": _is_security_or_crime_candidate,
        "_has_major_security_rail_impact": _has_major_security_rail_impact,
        "_has_core_metro_technical_content": _has_core_metro_technical_content,
        "_has_general_rail_exclusion": _has_general_rail_exclusion,
        "_has_substantive_detail_for_low_value_notice": _has_substantive_detail_for_low_value_notice,
        "_has_long_term_report_value": _has_long_term_report_value,
        "_is_low_value_long_term_candidate": _is_low_value_long_term_candidate,
        "_is_technical_news_selection_candidate": _is_technical_news_selection_candidate,
        "get_selection_candidate_limit": get_selection_candidate_limit,
        "get_selection_output_range": get_selection_output_range,
        "infer_preliminary_type": infer_preliminary_type,
        "build_candidate_flags": build_candidate_flags,
        "score_news_candidate": score_news_candidate,
        "_candidate_score_fingerprint": _candidate_score_fingerprint,
        "annotate_candidate_for_scheme_d": annotate_candidate_for_scheme_d,
        "build_candidate_card": build_candidate_card,
        "_is_low_value_policy_candidate": _is_low_value_policy_candidate,
        "rebalance_selected_candidates": rebalance_selected_candidates,
        "_selection_target_range": _selection_target_range,
        "_selection_classification": _selection_classification,
        "_has_source_reference": _has_source_reference,
        "_selection_good_flag_count": _selection_good_flag_count,
        "_selection_bad_flag_count": _selection_bad_flag_count,
        "_candidate_month_key": _candidate_month_key,
        "_candidate_system_theme": _candidate_system_theme,
        "_candidate_operator_key": _candidate_operator_key,
        "_candidate_incident_type": _candidate_incident_type,
        "_candidate_injury_band": _candidate_injury_band,
        "_candidate_action_key": _candidate_action_key,
        "_canonical_event_geo": _canonical_event_geo,
        "build_event_fingerprint": build_event_fingerprint,
        "_candidate_specific_event_location": _candidate_specific_event_location,
        "_candidate_event_location": _candidate_event_location,
        "_event_date_close": _event_date_close,
        "_event_similarity_text": _event_similarity_text,
        "_is_project_series_candidate": _is_project_series_candidate,
        "_candidate_project_stage": _candidate_project_stage,
        "_same_project_stage_or_unspecified": _same_project_stage_or_unspecified,
        "_duplicate_event_reason": _duplicate_event_reason,
        "_is_same_report_event": _is_same_report_event,
        "_is_duplicate_selected_event": _is_duplicate_selected_event,
        "_python_selection_sort_key": _python_selection_sort_key,
        "_python_selection_dynamic_key": _python_selection_dynamic_key,
        "_long_term_diversity_skip_reason": _long_term_diversity_skip_reason,
        "_python_candidate_allowed_for_scope": _python_candidate_allowed_for_scope,
        "_is_low_value_python_selection_candidate": _is_low_value_python_selection_candidate,
        "_is_strict_technical_candidate": _is_strict_technical_candidate,
        "_event_source_preference_key": _event_source_preference_key,
        "_supplemental_source_record": _supplemental_source_record,
        "_merge_duplicate_event_sources": _merge_duplicate_event_sources,
        "_take_next_python_candidate": _take_next_python_candidate,
        "_is_hard_excluded_for_borderline": _is_hard_excluded_for_borderline,
        "_is_b_level_technical_candidate": _is_b_level_technical_candidate,
        "_is_borderline_report_candidate": _is_borderline_report_candidate,
        "_selection_lower_bound": _selection_lower_bound,
        "_borderline_cap": _borderline_cap,
        "_selection_debug_reset": _selection_debug_reset,
        "_select_from_grouped_pools": _select_from_grouped_pools,
        "_qualifying_operational_coverage_candidate": _qualifying_operational_coverage_candidate,
        "_ensure_operational_topic_coverage": _ensure_operational_topic_coverage,
        "_backfill_borderline_candidates": _backfill_borderline_candidates,
        "select_candidates_by_python": select_candidates_by_python
    }
