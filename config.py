"""Non-sensitive configuration names shared by both application entry points."""

MAIAGENT_ENV_NAMES = ("MAIAGENT_API_KEY", "MAIAGENT_CHATBOT_ID", "MAIAGENT_API_BASE")
EMAIL_ENV_NAMES = ("GMAIL_USER", "GMAIL_APP_PASS", "RECIPIENTS", "DEFAULT_RECIPIENTS")
RUNTIME_ENV_NAMES = (
    "NEWS_LOOKBACK_DAYS", "MAIAGENT_TIMEOUT_SECONDS", "MAIAGENT_MAX_RSS_CHARS",
    "MAIAGENT_MAX_DDG_CHARS", "DDGS_MAX_WORKERS", "DDGS_MAX_QUERIES", "ENABLE_DDGS",
)
REPORT_TYPES = ("技術新知", "重大事故", "營運政策", "營運爭議", "規範更新")
NEWS_SCOPE_OPTIONS = ("international", "domestic", "both")
DEFAULT_NEWS_SCOPE = "international"

# Streamlit V19.4 non-sensitive configuration (moved verbatim).
ADVANCED_TYPES = ["技術新知", "重大事故", "營運政策", "營運爭議", "規範更新"]

ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY = "electromechanical_procurement"
ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL = "機電標案"
ELECTROMECHANICAL_PROCUREMENT_SELECTION_CAP = 3
OPERATIONAL_DYNAMICS_CATEGORY_LABEL = "營運動態"
SERVICE_OPENING_CATEGORY_KEY = "service_opening"
OPERATIONAL_DYNAMICS_SELECTION_CAP = 5

SERVICE_OPENING_ACTUAL_TERMS = [
    "opens to passengers", "opened to passengers",
    "opens for passenger service", "opened for passenger service",
    "enters revenue service", "entered revenue service",
    "enters commercial service", "entered commercial service",
    "begins passenger service", "began passenger service",
    "starts passenger operations", "started passenger operations",
    "commercial service begins", "commercial operations begin",
    "revenue service begins", "revenue operations begin",
    "inaugurated and opened to passengers",
    "正式通車", "正式啟用", "正式營運", "正式投入營運", "正式載客",
    "開始載客", "開始營運", "通車啟用", "投入載客服務",
]

SERVICE_OPENING_FUTURE_TERMS = [
    "will open", "set to open", "expected to open", "scheduled to open",
    "plans to open", "proposed opening", "target opening",
    "opening planned for", "due to open",
    "預計通車", "預定通車", "預計啟用", "將通車", "將啟用",
    "預計營運", "目標通車", "預計於", "預定於",
]

SERVICE_OPENING_PLANNING_TERMS = [
    "feasibility study", "route planning", "network planning",
    "preliminary planning", "approved route", "government approval",
    "groundbreaking", "construction begins", "construction progress",
    "civil works", "contract award", "tender", "design stage",
    "可行性研究", "綜合規劃", "路網規劃", "路線規劃", "核定",
    "獲准", "動工", "開工", "施工", "工程進度", "招標", "決標", "發包",
]

SERVICE_OPENING_TESTING_TERMS = [
    "testing begins", "trial runs", "test operation", "dynamic testing",
    "commissioning test", "train testing", "trial operation",
    "試車", "動態測試", "系統測試", "試運轉", "測試營運",
]

# 「機電標案」先接入搜尋、分類與 selection backend；正式報告章節仍沿用
# ADVANCED_TYPES，避免在 P4-B 提前改動 MaiAgent／報告後處理。
BACKEND_CATEGORY_TYPES = [
    *ADVANCED_TYPES,
    ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL,
]

DEFAULT_SELECTED_TYPES = ["技術新知", "重大事故", "營運政策", "營運爭議"]

SECTION_NUMBER_BY_TYPE = {
    "技術新知": "一",
    "重大事故": "二",
    "營運政策": "三",
    "營運爭議": "四",
    "規範更新": "五",
}

EMPTY_TEXT_BY_TYPE = {
    "技術新知": "本期未發現符合條件之技術新知案例。",
    "重大事故": "本期未發現符合條件之重大事故案例。",
    "營運政策": "本期未發現符合條件之營運政策案例。",
    "營運爭議": "本期未發現符合條件之營運爭議事件。",
    "規範更新": "本期未發現符合條件之規範版本更新、修訂草案、公告或徵詢事件。",
}

MIN_REPORT_ITEMS = 3

MAX_ITEMS_PER_SOURCE = 25

DDGS_RESULTS_PER_QUERY = 8

DDGS_QUERY_CHAR_LIMIT = 180

DDGS_GLOBAL_QUERY_LIMIT = 40

DDGS_REGIONAL_QUERY_LIMIT = 60

PREFETCH_TIMEOUT_SECONDS = 4

PREFETCH_MAX_CHARS = 6000

PREFETCH_LIMIT_BY_PERIOD = {
    "weekly": 8,
    "monthly": 15,
    "annual": 25,
}

RESEARCH_SUPPLEMENT_LOOKBACK_DAYS = 90

NORMAL_LOOKBACK_OPTIONS = [7, 14, 30]

ADVANCED_LOOKBACK_OPTIONS = [90, 180, 365]

REPORT_TARGET_BY_DAYS = {
    7: 3,
    14: 6,
    30: 6,
    90: 9,
    180: 9,
    365: 9,
}

LONG_TERM_TARGET_LABELS = {
    90: "趨勢回顧",
    180: "半年報",
    365: "年度回顧",
}

REPORT_PERIOD_LABELS = {
    7: "週報",
    14: "雙週報",
    30: "月報",
    90: "季報",
    180: "半年報",
    365: "年度回顧",
}

def get_research_supplement_lookback_days(days: int) -> int:
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = 90
    if days >= 365:
        return 365
    if days >= 180:
        return 180
    return 90

def research_supplement_allowed_for_report(days: int) -> bool:
    return int(days or 0) in {7, 14, 30, 90, 180, 365}

ADVANCED_REGIONS = [
    "日本", "韓國", "新加坡", "香港", "澳洲", "英國", "法國", "德國",
    "美國", "加拿大", "西班牙", "荷蘭", "瑞士", "義大利", "瑞典",
    "奧地利", "丹麥", "挪威", "俄羅斯", "葡萄牙", "巴西", "印度",
]

DEFAULT_REGIONS = [
    "日本", "韓國", "新加坡", "香港", "澳洲", "英國", "法國", "德國",
    "美國", "加拿大", "西班牙",
]

REGION_SEARCH_TERMS = {
    "日本": "Japan Tokyo Metro Osaka Metro subway new transit system",
    "韓國": "Korea Seoul Metro subway urban rail light rail",
    "新加坡": "Singapore MRT LTA SMRT",
    "香港": "Hong Kong MTR light rail metro",
    "美國": "United States New York subway Washington Metro Chicago CTA",
    "加拿大": "Canada Toronto TTC Vancouver SkyTrain Montreal REM",
    "英國": "United Kingdom London Underground DLR tram Transport for London",
    "法國": "France Paris Metro RATP Grand Paris Express",
    "德國": "Germany Berlin U-Bahn Munich U-Bahn Hamburg U-Bahn",
    "西班牙": "Spain Madrid Metro Barcelona Metro tranvia light rail metro project",
    "荷蘭": "Netherlands Amsterdam metro Rotterdam metro",
    "瑞士": "Switzerland Zurich tram Lausanne metro",
    "澳洲": "Australia Sydney Metro Melbourne Metro Brisbane Metro light rail",
    "義大利": "Italy metro metropolitana tram light rail",
    "瑞典": "Sweden Stockholm metro Gothenburg tram light rail",
    "奧地利": "Austria Vienna U-Bahn Wiener Linien tram metro",
    "丹麥": "Denmark Copenhagen Metro light rail",
    "挪威": "Norway Oslo Metro tram light rail",
    "俄羅斯": "Russia Moscow Metro tram metro rolling stock signalling",
    "葡萄牙": "Portugal metro metropolitana tram funicular",
    "巴西": "Brazil Sao Paulo Metro Rio Metro metro tram",
    "印度": "India Delhi Metro Mumbai Metro Bengaluru Metro metro rail",
}

EVENT_REGION_PRIORITY_HINTS: list[tuple[str, list[str]]] = [
    ("臺北", ["臺北捷運", "台北捷運", "taipei metro", "taipei mrt", "trtc", "北捷", "臺北市政府捷運工程局", "台北市政府捷運工程局"]),
    ("新北", ["新北捷運", "new taipei metro", "新北輕軌", "new taipei light rail"]),
    ("桃園", ["桃園捷運", "桃園機場捷運", "taoyuan metro", "taoyuan mrt", "taoyuan airport mrt", "桃捷"]),
    ("臺中", ["臺中捷運", "台中捷運", "taichung metro", "taichung mrt", "中捷"]),
    ("高雄", ["高雄捷運", "kaohsiung metro", "kaohsiung mrt", "krtc", "高捷"]),
    ("瑞士", ["basel", "basel tram", "bvb", "zürich", "zurich", "lausanne", "瑞士", "巴塞爾", "蘇黎世", "洛桑"]),
    ("美國", ["austin transit partnership", "austin light rail", "houston", "metrorail", "houston metrorail", "metro rail houston", "wmata", "washington metro", "mta", "nyct", "new york subway", "休士頓", "休斯頓"]),
    ("加拿大", ["vancouver", "translink vancouver", "vancouver translink", "broadway subway", "toronto", "toronto subway", "finch west", "finch west lrt", "metrolinx", "ttc", "skytrain", "溫哥華", "多倫多"]),
    ("英國", ["northern ireland", "belfast", "translink ni", "translink northern ireland", "北愛爾蘭", "貝爾法斯特"]),
    ("德國", ["bvg", "berlin", "adlershof", "leipzig", "munich", "hamburg", "u-bahn", "柏林", "萊比錫", "慕尼黑", "漢堡"]),
]

REGION_DOMAIN_HINTS = {
    "translink.ca": "加拿大",
    "ttc.ca": "加拿大",
    "mta.info": "美國",
    "wmata.com": "美國",
    "soundtransit.org": "美國",
    "tokyometro.jp": "日本",
    "mtr.com.hk": "香港",
    "lta.gov.sg": "新加坡",
    "smrt.com.sg": "新加坡",
    "ratp.fr": "法國",
    "tfl.gov.uk": "英國",
}

STANDARDS_WATCHLIST = {
    "碰撞/出軌類": ["EN 50126", "EN 50128", "EN 50129", "IEEE 1474.1", "EN 13674-1", "UIC 860-0", "IEC 61373"],
    "觸電/電弧爆炸類": ["EN 50122", "EN 50122-2", "EN 50327", "EN 50328", "EN 50329", "IEC 62271-100", "IEC 62271-102", "IEC 60947-1", "IEC 60850"],
    "火災/中毒類": ["NFPA 130", "ASTM E119", "IEC 60754-1", "IEC 60754-2", "IEC 60332-1", "ASTM E662", "NFPA 258", "NFPA 70"],
    "結構性/爆炸性設備失效類": ["IEC 60076", "IEC 60076-11", "IEC 62695"],
}

STANDARD_UPDATE_TERMS = [
    "new edition", "revision", "amendment", "corrigendum", "draft",
    "public comment", "published", "withdrawn", "superseded",
]

BLOCKED_DOMAINS = {
    ".cn", ".kp", ".by", ".ir",
}

LOW_VALUE_EXCLUDED_HOSTS = {
    "buseta.wmata.com",
    "estore.mtr.com.hk",
    "portal.mtr.com.hk",
    "link.mtrmb.mtr.com.hk",
    "art.tfl.gov.uk",
    "travelandtourworld.com",
}

PORTAL_REPOST_DOMAINS = {"msn.com", "yahoo.com", "aol.com", "patch.com"}

PORTAL_SOCIAL_LOW_VALUE_DOMAINS = {
    "facebook.com", "instagram.com", "x.com", "twitter.com",
    "youtube.com", "youtu.be", "reddit.com",
}

ALLOWED_NEWS_DOMAINS: set[str] = set()

DOMESTIC_EXCLUDED_DOMAINS = {
    ".tw",
}

DOMESTIC_EXCLUDED_TERMS = [
    "台灣", "臺灣", "Taiwan",
    "台北", "臺北", "Taipei", "Taipei MRT", "北捷",
    "新北", "New Taipei",
    "桃園", "Taoyuan", "Taoyuan Metro", "桃捷",
    "台中", "臺中", "Taichung",
    "台南", "臺南", "Tainan",
    "高雄", "Kaohsiung", "Kaohsiung MRT", "高捷",
    "基隆", "Keelung", "新竹", "Hsinchu", "苗栗", "Miaoli",
    "宜蘭", "Yilan", "花蓮", "Hualien", "台東", "臺東", "Taitung",
    "屏東", "Pingtung",
]

DOMESTIC_METRO_SYSTEM_TERMS = {
    "臺北": ["臺北捷運", "台北捷運", "taipei metro", "taipei mrt", "trtc", "北捷", "臺北市政府捷運工程局", "台北市政府捷運工程局"],
    "新北": ["新北捷運", "new taipei metro", "新北輕軌", "new taipei light rail"],
    "桃園": ["桃園捷運", "桃園機場捷運", "taoyuan metro", "taoyuan mrt", "taoyuan airport mrt", "桃捷"],
    "臺中": ["臺中捷運", "台中捷運", "taichung metro", "taichung mrt", "中捷"],
    "高雄": ["高雄捷運", "kaohsiung metro", "kaohsiung mrt", "krtc", "高捷"],
    "臺灣": ["台灣捷運", "臺灣捷運", "taiwan metro", "taiwan mrt", "臺灣都市軌道", "台灣都市軌道"],
}

DOMESTIC_METRO_CONTEXT_TERMS = [
    "捷運", "metro", "mrt", "light rail", "輕軌", "urban rail", "transit",
    "line", "station", "train", "fare", "system", "service", "operation",
    "列車", "車站", "票價", "營運", "服務", "系統", "設備", "維修", "號誌",
]

DOMESTIC_NON_METRO_TERMS = [
    "台鐵", "臺鐵", "taiwan railway", "taiwan railways", "tra", "台灣高鐵", "臺灣高鐵",
    "台灣高鐵", "taiwan high speed rail", "thsr", "高鐵", "公車", "巴士", "bus", "客運",
    "航空", "aviation", "高速公路", "highway", "道路", "road", "一般鐵路", "regional rail",
]

DOMESTIC_SCOPE_EXCLUDED_TERMS = [
    "新線規劃", "新路線規劃", "路網規劃", "可行性研究", "feasibility study", "feasibility",
    "土建標", "土木工程", "純土建", "civil works", "civil engineering", "construction progress",
    "工程進度", "工程里程碑",
]

TRANSIT_NEWS_TERMS = (
    '("urban rail" OR metro OR subway OR underground OR "mass rapid transit" OR MRT OR '
    '"light rail" OR tram OR tramway OR streetcar OR LRRT OR LRT OR AGT OR '
    '"automated guideway transit" OR "people mover") '
    '-"high-speed rail" -"high speed rail" -HSR -Shinkansen -"bullet train" '
    '-intercity -"regional rail" -freight -locomotive -bus -coach -highway'
)

URBAN_RAIL_MODE_TERMS = [
    "metro", "subway", "underground", "tube", "metrorail", "mass rapid transit", "mrt",
    "light rail", "tram", "tramway", "streetcar", "lrrt", "lrt",
    "urban rail", "urban metro", "rapid transit", "people mover", "automated guideway transit",
    "agt", "monorail", "funicular", "u-bahn", "stadtbahn", "skytrain", "dlr", "mover",
    "地下鉄", "メトロ", "新交通システム", "都市鉄道", "路面電車", "トラム",
    "지하철", "도시철도", "경전철",
    "地鐵", "港鐵", "輕軌", "轻轨", "都市軌道", "捷運",
]

URBAN_RAIL_UNAMBIGUOUS_MODE_TERMS = [
    term for term in URBAN_RAIL_MODE_TERMS
    if term not in {"metro"}
]

URBAN_RAIL_OPERATOR_TERMS = [
    "tokyo metro", "seoul metro", "mtr", "lta", "smrt", "tfl", "transport for london",
    "ratp", "wmata", "ttc", "translink", "mta", "nyct", "cta", "bart",
    "metro de madrid", "madrid metro", "barcelona metro", "wiener linien",
    "stockholm metro", "sporveien", "copenhagen metro", "rta dubai",
    "東京メトロ", "서울교통공사", "港鐵", "巴黎地鐵",
]

CIVIC_METRO_NAME_ONLY_TERMS = [
    "metro vancouver", "metro council", "metro mayor", "metro government",
    "metro area", "metro region", "metropolitan council", "metropolitan government",
    "metropolitan planning organization",
    "metro atlanta", "metro nashville", "metro police", "metro fire",
    "metro housing", "metropolitan area",
]

METRO_RAIL_CONTEXT_TERMS = [
    "rail", "train", "station", "line", "fare", "fleet", "signalling", "signaling",
    "rolling stock", "subway", "transit system", "platform", "depot",
    "metro operator", "metro rail", "metro network", "metro line", "metro station",
    "ticketing", "fare gate", "track", "tram", "light rail",
]

SOURCE_NAME_NOISE_TERMS = [
    "metro magazine", "metro report international", "urban transport magazine",
    "mass transit", "railway gazette international", "international railway journal",
    "railway age", "railway-news", "railway news", "railway technology",
    "global railway review", "intelligent transport",
]

NON_URBAN_TRANSPORT_TERMS = [
    "high-speed rail", "high speed rail", "high-speed train", "high speed train",
    "hsr", "shinkansen", "bullet train", "tgv", "ice train", "renfe high speed",
    "intercity", "inter-city", "long-distance", "long distance", "regional rail",
    "commuter rail", "national rail", "mainline", "main line", "heavy haul",
    "freight", "locomotive", "rail freight", "passenger rail", "railway contract",
    "railway contracts", "railway procurement", "lirr", "long island rail road",
    "amtrak", "korail", "network rail", "east midlands railway", "regiojet",
    "battery train", "hybrid train", "diesel-hybrid", "gsm-r outage",
    "bus", "coach", "highway", "intercity bus", "long-distance coach", "brt",
    "airport", "aviation", "lax", "airport people mover", "terminal people mover",
    "airport transit", "airport shuttle", "terminal shuttle",
    "road maintenance", "road works", "road construction", "road closure",
    "pothole", "highway works", "traffic advisory",
    "高速鐵路", "高速铁路", "高鐵", "高铁", "新幹線", "新干线",
    "台鐵", "臺鐵", "台湾鉄路", "台灣鐵路", "在来線", "特急",
    "貨運", "貨物列車", "客運鐵路", "城際鐵路", "區域鐵路", "通勤鐵路",
    "公路", "高速公路", "道路維護", "道路施工", "道路封閉", "道路坑洞",
    "交通提醒", "長途巴士", "客運", "機場", "航空", "航廈", "航站",
    "高速鉄道", "高速バス", "バス", "貨物鉄道", "在来線",
]

NON_URBAN_HARD_EXCLUDE_TERMS = [
    term for term in NON_URBAN_TRANSPORT_TERMS
    if term not in {"passenger rail", "railway contract", "railway contracts", "railway procurement"}
]

LAST_DDGS_QUERY_METADATA: dict[str, dict] = {}

LAST_DDGS_QUERY_STATUSES: list[dict] = []

LAST_DDGS_SEARCH_SUMMARY: dict = {}





AIRPORT_PEOPLE_MOVER_EXCLUDE_TERMS = [
    "airport", "aviation", "lax", "airport people mover", "terminal people mover",
    "airport transit", "airport shuttle", "terminal shuttle",
    "機場", "航空", "航廈", "航站",
]

TECH_NEWS_REQUIRED_TERMS = [
    "cbtc", "goa4", "driverless", "unattended train operation", "automatic train operation",
    "automation", "automated", "train control", "signalling", "signaling", "signal system",
    "rolling stock", "fleet", "new train", "trainset", "vehicle", "platform screen door",
    "platform doors", "psd", "power supply", "traction power", "substation", "third rail",
    "overhead line", "communications", "telecom", "4g", "5g", "lte", "radio", "cybersecurity",
    "data", "monitoring", "condition monitoring", "real-time", "digital", "asset management",
    "depot", "maintenance", "workshop", "afc", "fare gate", "ticketing", "elevator",
    "escalator", "system integration", "testing", "commissioning", "trial run",
    "api", "data governance", "ai image analysis", "video analytics", "system verification",
    "自動運転", "無人運転", "ワンマン運転", "信号", "ホームドア", "車両", "電力",
    "変電所", "通信", "保守", "検査", "試験", "システム",
    "自動駕駛", "無人駕駛", "單人駕駛", "號誌", "信號", "月臺門", "月台門",
    "車輛", "列車", "供電", "牽引", "變電站", "通訊", "資安", "即時監控",
    "維修", "機廠", "測試", "試運轉", "系統整合", "列控", "資料治理",
    "AI 影像分析", "影像分析", "測試驗證", "故障預測", "設備故障預測", "智慧維修", "自動巡檢",
]

TITLE_TECHNICAL_ACTION_TERMS = [
    "upgrade", "upgraded", "modernise", "modernize", "modernisation", "modernization",
    "renewal", "replace", "replacement", "retrofit", "deploy", "deployed", "roll out",
    "rollout", "install", "installation", "commission", "commissioning", "test", "testing",
    "trial", "pilot", "launch", "enter service", "entered service", "open", "opened",
    "introduced", "introduce", "integrate", "integrated", "integration", "contract awarded",
    "award contract", "selected", "order", "ordered", "deliver", "delivered",
    "upgrades", "replaces", "renews", "retrofits", "deploys", "installs",
    "commissions", "launches", "introduces", "integrates", "awards",
    "orders", "delivers", "activates",
    "啟用", "導入", "部署", "升級", "更新", "汰換", "更換", "改造", "現代化",
    "安裝", "裝設", "整合", "測試", "試運轉", "試辦", "試行", "驗證",
    "投入營運", "正式營運", "得標", "採購", "交付", "導入新",
]

TECH_NEWS_SOFT_EXCLUDE_TERMS = [
    "accident", "derailment", "collision", "fire", "arson", "incident", "strike",
    "wage", "salary", "union", "fare dispute", "budget overrun", "lawsuit",
    "ceo", "resignation", "appoints", "appointment", "preview", "ceremony",
    "anniversary", "mascot", "branding", "pest", "hygiene", "route planning",
    "network expansion", "line extension", "funding", "procurement scandal",
    "bus procurement", "electric bus", "policy", "ban",
    "事故", "脱線", "火災", "放火", "スト", "労組", "賃金", "社長", "退任",
    "就任", "記念", "ラッピング", "ドラゴンズ", "害虫", "禁止", "バス",
    "事故", "出軌", "脫軌", "火災", "縱火", "罷工", "工會", "薪資", "票價",
    "爭議", "執行長", "離職", "任命", "預覽", "開幕", "紀念", "彩繪",
    "行銷", "害蟲", "禁帶", "禁令", "公車", "電動巴士",
]

MAX_SELECTION_CANDIDATES = 150

SELECTION_MIN_ITEMS = 8

SELECTION_MAX_ITEMS = 20

CANDIDATE_SNIPPET_CHARS = 140

REPORT_SNIPPET_CHARS = 420

JOURNAL_MAX_RESULTS_PER_QUERY = 3

JOURNAL_MAX_ITEMS = 8

JOURNAL_ARTICLE_FETCH_LIMIT = 18

SOURCE_QUALITY_A_DOMAINS = {
    "tfl.gov.uk", "mta.info", "wmata.com", "ttc.ca", "translink.ca",
    "ratp.fr", "lta.gov.sg", "smrt.com.sg", "mtr.com.hk",
    "seoulmetro.co.kr", "tokyometro.jp", "metro.tokyo.lg.jp",
    "metro-madrid.es", "tmb.cat", "wienerlinien.at", "sl.se",
    "cph.dk", "rta.ae", "bvg.de", "sydneymetro.info",
    "infrastructure.gov.au", "kaupunkiliikenne.fi", "mosmetro.ru",
    "transport.mos.ru", "lrta.gov.ph", "ntsb.gov", "tsb.gc.ca",
    "atsb.gov.au", "bea-tt.developpement-durable.gouv.fr", "gov.uk",
    "raib.gov.uk", "railwaygazette.com", "railjournal.com",
    "railway-technology.com", "railway-news.com",
    "urban-transport-magazine.com", "masstransitmag.com",
    "intelligenttransport.com", "metro-magazine.com",
}

SOURCE_TIER_OFFICIAL_DOMAINS = {
    "tfl.gov.uk", "mta.info", "wmata.com", "ttc.ca", "translink.ca",
    "ratp.fr", "lta.gov.sg", "smrt.com.sg", "mtr.com.hk",
    "seoulmetro.co.kr", "tokyometro.jp", "metro.tokyo.lg.jp",
    "metro-madrid.es", "tmb.cat", "wienerlinien.at", "sl.se",
    "cph.dk", "rta.ae", "uitp.org", "societedesgrandsprojets.fr",
    "bvg.de", "sydneymetro.info", "infrastructure.gov.au",
    "kaupunkiliikenne.fi", "mosmetro.ru", "transport.mos.ru",
    "lrta.gov.ph", "ntsb.gov", "tsb.gc.ca", "atsb.gov.au",
    "bea-tt.developpement-durable.gouv.fr", "gov.uk", "raib.gov.uk",
}

SOURCE_TIER_PROFESSIONAL_DOMAINS = {
    "railwaygazette.com", "railjournal.com", "railway-technology.com",
    "railway-news.com", "urban-transport-magazine.com", "masstransitmag.com",
    "intelligenttransport.com", "metro-magazine.com", "railwayage.com",
    "globalmasstransit.net", "globalmasstransit.com",
}

SOURCE_DISPLAY_BY_DOMAIN = {
    "mta.info": "MTA 官方公告",
    "tokyometro.jp": "Tokyo Metro 官方公告",
    "mtr.com.hk": "港鐵官方資料",
    "ttc.ca": "TTC 官方公告",
    "tfl.gov.uk": "TfL 官方公告",
    "wmata.com": "WMATA 官方公告",
    "translink.ca": "TransLink 官方公告",
    "ratp.fr": "RATP 官方資料",
    "lta.gov.sg": "LTA 官方公告",
    "smrt.com.sg": "SMRT 官方公告",
    "seoulmetro.co.kr": "Seoul Metro 官方公告",
    "railway-news.com": "Railway-News",
    "railwaygazette.com": "Railway Gazette",
    "railjournal.com": "International Railway Journal",
    "urban-transport-magazine.com": "Urban Transport Magazine",
    "globalmasstransit.net": "Global Mass Transit",
    "globalmasstransit.com": "Global Mass Transit",
    "masstransitmag.com": "Mass Transit Magazine",
    "metro-magazine.com": "METRO Magazine",
    "railwayage.com": "Railway Age",
    "bvg.de": "BVG 官方公告",
    "sydneymetro.info": "Sydney Metro 官方公告",
    "infrastructure.gov.au": "澳洲基礎建設主管機關",
    "kaupunkiliikenne.fi": "Kaupunkiliikenne 官方公告",
    "mosmetro.ru": "Moscow Metro 官方公告",
    "transport.mos.ru": "Moscow Transport 官方公告",
    "lrta.gov.ph": "LRTA 官方公告",
    "ntsb.gov": "NTSB 事故調查資料",
    "tsb.gc.ca": "TSB Canada 事故調查資料",
    "atsb.gov.au": "ATSB 事故調查資料",
    "bea-tt.developpement-durable.gouv.fr": "BEA-TT 事故調查資料",
    "gov.uk": "英國政府/RAIB 事故調查資料",
    "raib.gov.uk": "RAIB 事故調查資料",
}

SOURCE_DOMAIN_HINT_BY_LABEL = {
    "mta": "mta.info",
    "tokyo metro": "tokyometro.jp",
    "mtr": "mtr.com.hk",
    "ttc": "ttc.ca",
    "tfl": "tfl.gov.uk",
    "wmata": "wmata.com",
    "translink": "translink.ca",
    "ratp": "ratp.fr",
    "lta": "lta.gov.sg",
    "smrt": "smrt.com.sg",
    "seoul metro": "seoulmetro.co.kr",
    "railway-news": "railway-news.com",
    "railway news": "railway-news.com",
    "railway gazette": "railwaygazette.com",
    "international railway journal": "railjournal.com",
    "irj": "railjournal.com",
    "urban transport magazine": "urban-transport-magazine.com",
    "global mass transit": "globalmasstransit.net",
    "mass transit magazine": "masstransitmag.com",
    "metro magazine": "metro-magazine.com",
    "railway age": "railwayage.com",
    "bvg": "bvg.de",
    "sydney metro": "sydneymetro.info",
    "moscow metro": "mosmetro.ru",
    "mosmetro": "mosmetro.ru",
    "lrta": "lrta.gov.ph",
    "ntsb": "ntsb.gov",
    "tsb canada": "tsb.gc.ca",
    "atsb": "atsb.gov.au",
    "bea-tt": "bea-tt.developpement-durable.gouv.fr",
    "raib": "gov.uk",
}

SOURCE_QUALITY_C_DOMAINS = {
    "msn.com", "yahoo.com", "aol.com", "tripadvisor.com", "timeout.com",
    "lonelyplanet.com", "booking.com", "expedia.com", "trip.com",
    "wikipedia.org", "wikivoyage.org", "travelandtourworld.com",
}

LOW_QUALITY_CONTENT_TERMS = [
    "wikipedia", "travel guide", "tourist", "hotel", "airport parking",
    "things to do", "itinerary", "visitor guide", "travel tips", "travel reminder",
    "tourism information", "weekend travel", "airport travel", "travel and tour world",
    "futuristic metro network", "international expansion", "seo", "sponsored",
    "minor delay", "detour", "service alert", "service advisory",
    "customer notice", "take transit", "temporary stop closure",
    "hiring", "jobs", "careers", "conference registration", "event page",
    "product page", "mtr e-store", "passenger praised", "passenger review",
    "traveler review", "viral video", "social media", "列車模型", "吊牌掛飾",
    "一般旅遊", "旅遊攻略", "景點", "飯店", "酒店", "旅客心得",
    "社群影片", "旅遊資訊", "週末搭乘提醒",
    "passengers praise", "passenger praises", "riders praise", "rider praised",
    "commuters praise", "praised the metro", "praises the metro", "clean and safe",
    "cheap fare", "low fare", "anniversary", "celebration", "campaign",
    "promotion", "promotional", "open day", "tour package",
    "旅客稱讚", "乘客稱讚", "乘客大讚", "大讚捷運", "乾淨安全",
    "票價便宜", "低票價", "週年", "周年", "紀念活動", "宣傳", "促銷",
]

LOW_INFORMATION_PAGE_TERMS = [
    "home", "homepage", "topic page", "archive", "category", "service page",
    "portal", "入口", "首頁", "分類頁", "服務頁", "旅客資訊", "活動資訊",
    "archive page", "route page", "trip result", "journey planner", "route map",
    "route number", "RouteNumber", "trip planner", "travel information",
    "trip results", "rider tools", "service alerts", "service advisory",
    "mtr e-store", "untitled", "pdf map", "plan-metro", "plan-de-ligne",
    "archives", "event page", "conference registration", "product page",
    "jobs", "hiring", "vacancy", "career", "careers",
    "主頁", "列車模型", "吊牌掛飾",
    "schedule", "schedules", "timetable", "timetables", "bus schedule",
    "bus schedules", "bus timetable", "bus timetables", "bus route",
    "bus routes", "bus stop", "bus stops", "bus services", "promotions",
    "campaign page", "anniversary page", "celebration page",
    "時刻表", "班表", "公車頁", "公車路線", "公車班表", "巴士路線",
    "巴士班表", "宣傳頁", "活動頁", "週年頁", "周年頁",
]

LOW_INFORMATION_PATH_MARKERS = [
    "/topic", "/topics", "/archive", "/archives", "/category", "/categories",
    "/tag/", "/tags/", "/services", "/service", "/customer", "/passenger",
    "/mobile", "/app", "/apps", "/route", "/routes", "/trip", "/trips",
    "/journey", "/journey-planner", "/trip-planner", "/travel-information",
    "/rider-tools", "/service-alert", "/service-advisory", "/map", "/maps",
    "/search", "/store", "/estore", "/e-store", "/shop", "/product",
    "/event", "/events", "/registration", "/register", "/jobs", "/hiring",
    "/careers", "plan-metro", "plan-de-ligne", ".pdf",
    "/schedule", "/schedules", "/timetable", "/timetables", "/bus",
    "/buses", "/bus-route", "/bus-routes", "/bus-services", "/promotion",
    "/promotions", "/campaign", "/campaigns", "/anniversary", "/celebration",
]

HARD_LOW_VALUE_CANDIDATE_TERMS = [
    "trip results", "trip result", "service alerts", "service alert",
    "service advisory", "rider tools", "careers", "career", "hiring",
    "jobs", "plan-metro", "plan-de-ligne", "route page", "route map",
    "pdf map", "mtr e-store", "product page", "conference registration",
    "event page", "untitled", "lost property", "delay certificate",
    "contract documents holders list", "passenger praised", "passenger review",
    "traveler review", "viral video", "social media", "mascot", "stamp rally",
    "theme train", "themed train", "tbm farewell", "tbm demobilization",
    "tbm removal", "tunnel boring machine farewell", "pothole",
    "失物招領", "延誤證明", "標案文件持有人", "旅客心得", "社群影片",
    "吉祥物", "集章活動", "主題列車", "潛盾機告別", "潛盾機撤場", "道路坑洞",
    "schedule", "timetable", "bus schedule", "bus route", "bus stop",
    "anniversary", "celebration", "promotional campaign", "open day",
    "時刻表", "班表", "公車路線", "公車班表", "巴士路線", "巴士班表",
    "週年", "周年", "紀念活動", "宣傳活動", "開放日",
]

JOURNAL_PRECISION_QUERIES = [
    '"urban rail transit" "predictive maintenance" "condition monitoring"',
    '"metro system" "fault diagnosis" "machine learning"',
    '"urban rail transit" "digital twin" maintenance',
    '"metro system" "digital twin" operation maintenance',
    '"CBTC" "urban rail transit" safety',
    '"communication based train control" "metro" reliability',
    '"driverless metro" "system assurance"',
    '"urban rail transit" "regenerative braking" energy storage',
    '"metro" "wayside energy storage" supercapacitor',
    '"platform screen door" "metro" fault diagnosis',
    '"platform screen doors" "urban rail transit" reliability',
    '"urban rail transit" cybersecurity',
    '"CBTC" cybersecurity',
    '"railway operational technology" cybersecurity',
]

JOURNAL_EXPLORATORY_QUERIES = [
    '"urban rail transit" emerging technology',
    '"metro system" innovation',
    '"smart metro" system integration',
    '"urban rail" advanced monitoring',
    '"driverless metro" technology',
    '"rail transit" intelligent maintenance',
    '"urban rail transit" intelligent operation maintenance',
]

JOURNAL_SOURCE_PAGES = [
    ("Springer Urban Rail Transit articles", "https://link.springer.com/journal/40864/articles"),
]

JOURNAL_EXCLUDE_TERMS = [
    "high-speed rail", "freight railway", "intercity rail", "road traffic",
    "bus", "autonomous vehicle", "air traffic", "pure algorithm",
    "高速鐵路", "貨運鐵路", "城際鐵路", "公車", "自駕車", "航空",
]

JOURNAL_RAIL_CONTEXT_TERMS = [
    "railway", "rail transit", "urban rail", "urban rail transit", "metro",
    "metro system", "subway", "mass rapid transit", "mrt", "light rail",
    "tram", "tramway", "cbtc", "rolling stock", "railway signalling",
    "railway signaling", "platform screen door", "traction power",
    "都市軌道", "捷運", "地鐵", "地下鉄", "都市鉄道", "軌道",
]

JOURNAL_ALLOWED_SOURCE_DOMAINS = {
    "mdpi.com", "nature.com", "springer.com", "link.springer.com",
    "sciencedirect.com", "doi.org", "tandfonline.com", "ieee.org",
    "ieeexplore.ieee.org", "elsevier.com", "frontiersin.org",
    "ascelibrary.org", "sagepub.com", "emerald.com",
}

JOURNAL_PREFERRED_SOURCE_TERMS = [
    "mdpi", "sciencedirect", "ieee", "springer", "taylor & francis",
    "tandfonline", "elsevier", "transportation research",
    "railway engineering science",
]

JOURNAL_SYSTEM_TERMS = [
    "cbtc", "signalling", "signaling", "train control", "rolling stock",
    "traction power", "power supply", "maintenance", "condition monitoring",
    "predictive maintenance", "artificial intelligence", "machine learning",
    "digital twin", "cybersecurity", "energy efficiency", "data governance",
    "passenger flow", "system integration", "platform screen door",
    "號誌", "列控", "車輛", "牽引供電", "維修", "AI", "數位分身",
    "資安", "能源效率", "資料治理", "旅客流量", "系統整合", "月臺門",
]

JOURNAL_INSIGHT_TERMS = [
    "maintenance", "energy", "safety", "risk", "cyber", "data", "system",
    "integration", "planning", "operations", "condition monitoring",
    "維修", "能源", "安全", "風險", "資安", "資料", "系統", "整合", "規劃",
]

JOURNAL_CORE_SYSTEM_TERMS = [
    "rolling stock", "vehicle system", "trainset", "signalling", "signaling",
    "train control", "cbtc", "ato", "atp", "ats", "operations control",
    "operation control", "traction power", "regenerative braking", "energy storage",
    "power supply", "communications", "wireless", "data transmission",
    "platform screen door", "platform door", "automatic fare collection", "afc",
    "depot equipment", "maintenance equipment", "condition monitoring",
    "fault diagnosis", "predictive maintenance", "image recognition",
    "video analytics", "system integration", "system assurance", "rams",
    "safety verification", "cybersecurity", "hvac", "ventilation", "fire safety",
    "environmental control", "energy management", "digital twin",
    "電聯車", "車輛系統", "號誌", "信號", "列車控制", "列控", "行車監控",
    "行控中心", "牽引供電", "再生煞車", "儲能", "供電", "通訊", "無線通訊",
    "月臺門", "月台門", "自動收費", "票務系統", "機廠設備", "維修設備",
    "狀態監測", "故障診斷", "預測性維護", "影像辨識", "系統整合", "系統保證",
    "安全驗證", "RAMS", "資安", "空調", "通風", "消防", "環控", "能源管理",
    "數位孿生", "數位分身",
]

JOURNAL_SECONDARY_SYSTEM_TERMS = [
    "track monitoring", "tunnel monitoring", "construction interface",
    "equipment layout", "installation interface", "metro construction interface",
    "軌道監測", "隧道監測", "施工介面", "設備配置", "安裝介面", "機電安裝",
]

JOURNAL_LOW_PRIORITY_TERMS = [
    "crew scheduling", "crew rostering", "staff scheduling", "workforce scheduling",
    "manpower scheduling", "passenger behavior", "passenger behaviour", "mode choice",
    "passenger choice", "commuter behavior", "pure operation management",
    "construction site layout", "civil construction", "civil engineering",
    "tunnel excavation", "excavation optimization", "general railway",
    "commuter rail", "人力排班", "人員排班", "乘務排班", "旅客行為",
    "旅客運具選擇", "通勤行為", "純營運管理", "施工場地配置", "土建施工",
    "隧道開挖", "一般鐵路", "通勤鐵路",
]
