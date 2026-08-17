"""Streamlit V19.4 source specifications and source-list builders."""

from config import *
import urllib.parse
from urllib.parse import urlparse
from search_service import google_news_search_url, google_news_site_proxy_url

# Complete DDGS query families and language metadata (moved verbatim).
SEARCH_QUERY_SPECS = [
    {"family": "technology", "lang": "en", "query": "metro subway MRT LRT tram CBTC signalling upgrade commissioning"},
    {"family": "technology", "lang": "en", "query": "metro subway LRT tram rolling stock new trains ordered delivered"},
    {"family": "technology", "lang": "en", "query": "metro subway tram contactless payment AFC fare gates rollout"},
    {"family": "technology", "lang": "en", "query": "metro subway LRT tram traction power substation third rail overhead contact system upgrade commissioning"},
    {"family": "technology", "lang": "en", "query": "metro subway railway 5G private LTE CBTC train radio fibre network communications deployment testing"},
    {"family": "technology", "lang": "en", "query": "metro subway station platform screen doors HVAC ventilation escalator elevator smoke control upgrade testing"},
    {"family": "technology", "lang": "en", "query": "metro subway rail condition monitoring predictive maintenance fault detection onboard monitoring deployment"},
    {"family": "technology", "lang": "en", "query": "metro subway AI inspection computer vision video analytics image recognition passenger flow testing"},
    {"family": "technology", "lang": "en", "query": "metro subway digital twin BIM operations asset management IoT monitoring deployment"},
    {"family": "technology", "lang": "en", "query": "metro subway automated inspection robotic inspection autonomous inspection track inspection robot deployment"},
    {"family": "technology", "lang": "en", "query": "metro subway traction energy optimisation regenerative braking energy storage station energy management upgrade"},
    {"family": "technology", "lang": "en", "query": "metro railway signalling cybersecurity rail OT operational technology security deployment assessment"},
    {"family": "technology", "lang": "de", "query": "U-Bahn Stadtbahn Strassenbahn Signaltechnik Fahrzeuge Modernisierung"},
    {"family": "technology", "lang": "fr", "query": "métro tramway signalisation matériel roulant modernisation"},
    {"family": "technology", "lang": "es", "query": "metro tranvía tren ligero señalización material rodante modernización"},
    {"family": "technology", "lang": "it", "query": "metro metropolitana tram segnalamento materiale rotabile modernizzazione"},
    {"family": "technology", "lang": "pt", "query": "metro metropolitana tram funicular sinalização material circulante modernização"},
    {"family": "technology", "lang": "ru", "query": "метро трамвай сигнализация вагоны модернизация"},
    {"family": "technology", "lang": "ja", "query": "地下鉄 メトロ 路面電車 信号 車両 自動運転 更新 導入"},
    {"family": "technology", "lang": "ko", "query": "지하철 도시철도 경전철 신호 차량 자동운전 현대화 도입"},
    {"family": "technology", "lang": "zh", "query": "地鐵 地铁 捷運 輕軌 轻轨 信號 信号 車輛 车辆 自動化 自动化 更新"},
    {"family": "major_accident", "lang": "en", "query": "metro subway LRT tram derailment collision fire evacuation investigation"},
    {"family": "major_accident", "lang": "en", "query": "funicular tram metro fatal injured shutdown safety investigation"},
    {"family": "major_accident", "lang": "pt", "query": "metro metropolitana tram funicular descarrilamento colisão incêndio investigação"},
    {"family": "major_accident", "lang": "it", "query": "metro metropolitana tram funicular deragliamento collisione incendio indagine"},
    {"family": "major_accident", "lang": "ru", "query": "метро трамвай фуникулер сход с рельсов столкновение пожар расследование"},
    {"family": "major_accident", "lang": "fr", "query": "métro tramway funiculaire déraillement collision incendie enquête"},
    {"family": "major_accident", "lang": "es", "query": "metro tranvía funicular descarrilamiento colisión incendio investigación"},
    {"family": "major_accident", "lang": "ja", "query": "地下鉄 メトロ 路面電車 トラム 脱線 衝突 火災 避難 調査"},
    {"family": "major_accident", "lang": "ko", "query": "지하철 도시철도 경전철 트램 탈선 충돌 화재 대피 조사"},
    {"family": "major_accident", "lang": "zh", "query": "地鐵 地铁 捷運 輕軌 轻轨 脫軌 脱轨 碰撞 火災 火灾 調查 调查"},
    {"family": "policy", "lang": "en", "query": "metro subway tram line opening fare reform operating hours service change"},
    {"family": "policy", "lang": "en", "query": "metro subway LRT line extension capacity increase closure works"},
    {"family": "policy", "lang": "de", "query": "U-Bahn Stadtbahn Straßenbahn urbaner Schienenverkehr Fahrplan Betriebszeiten Tarife Eröffnung"},
    {"family": "policy", "lang": "de", "query": "U-Bahn Stadtbahn Straßenbahn U-Bahnlinie Kapazität Streckenerweiterung Betriebskosten Genehmigung"},
    {"family": "policy", "lang": "fr", "query": "métro tramway transport urbain sur rail ouverture ligne tarif horaires travaux"},
    {"family": "policy", "lang": "fr", "query": "métro tramway ligne nouvelle capacité extension service budget autorisation"},
    {"family": "policy", "lang": "es", "query": "metro tranvía tren urbano transporte ferroviario apertura línea tarifas horarios obras"},
    {"family": "policy", "lang": "es", "query": "metro tranvía línea nueva capacidad ampliación servicio presupuesto autorización"},
    {"family": "policy", "lang": "it", "query": "metro metropolitana tram trasporto ferroviario urbano apertura linea tariffe orari lavori"},
    {"family": "policy", "lang": "it", "query": "metro metropolitana tram nuova linea capacità servizio bilancio autorizzazione"},
    {"family": "policy", "lang": "pt", "query": "metro metropolitana tram transporte ferroviário urbano abertura linha tarifas horários obras"},
    {"family": "policy", "lang": "pt", "query": "metro metropolitana tram nova linha capacidade serviço orçamento autorização"},
    {"family": "policy", "lang": "ja", "query": "地下鉄 メトロ 路面電車 都市鉄道 新線 開業 運賃 運行時間 サービス変更"},
    {"family": "policy", "lang": "ja", "query": "地下鉄 メトロ 路面電車 都市鉄道 路線延伸 輸送力 運行計画 予算 認可"},
    {"family": "policy", "lang": "ko", "query": "지하철 도시철도 경전철 트램 노선 개통 요금 운행시간 서비스 변경"},
    {"family": "policy", "lang": "ko", "query": "지하철 도시철도 경전철 트램 노선 연장 수송능력 운영계획 예산 승인"},
    {"family": "policy", "lang": "zh", "query": "地鐵 地铁 捷運 MRT 輕軌 轻轨 電車 城市軌道 新線 通車 票價 班次 服務調整"},
    {"family": "policy", "lang": "zh", "query": "地鐵 地铁 捷運 MRT 輕軌 轻轨 城市軌道 路線延伸 運能 預算 核准"},
    {"family": "dispute", "lang": "en", "query": "metro subway tram strike union lawsuit procurement dispute delay cost overrun"},
    {"family": "dispute", "lang": "en", "query": "light rail metro contract dispute arbitration protest service disruption"},
    {"family": "dispute", "lang": "de", "query": "U-Bahn Stadtbahn Straßenbahn urbaner Schienenverkehr Streik Gewerkschaft Vertragsstreit Schiedsverfahren"},
    {"family": "dispute", "lang": "fr", "query": "métro tramway transport urbain sur rail grève litige contrat arbitrage perturbation"},
    {"family": "dispute", "lang": "es", "query": "metro tranvía tren urbano conflicto huelga disputa contractual arbitraje interrupción"},
    {"family": "dispute", "lang": "it", "query": "metro metropolitana tram trasporto ferroviario urbano sciopero controversia appalto arbitrato"},
    {"family": "dispute", "lang": "pt", "query": "metro metropolitana tram transporte ferroviário urbano greve disputa contrato arbitragem"},
    {"family": "dispute", "lang": "ru", "query": "метро трамвай городской рельсовый транспорт забастовка спор контракт арбитраж"},
    {"family": "dispute", "lang": "ja", "query": "地下鉄 メトロ 路面電車 都市鉄道 ストライキ 労使紛争 契約紛争 仲裁"},
    {"family": "dispute", "lang": "ko", "query": "지하철 도시철도 경전철 트램 파업 노사분쟁 계약분쟁 중재 운행차질"},
    {"family": "dispute", "lang": "zh", "query": "地鐵 地铁 捷運 MRT 輕軌 轻轨 電車 城市軌道 罷工 勞資爭議 合約爭議 仲裁"},
    {"family": "official_investigation", "lang": "en", "query": "urban rail metro tram derailment collision fire official investigation safety board", "use_news": False},
]

DOMESTIC_METRO_QUERY_SPECS = [
    {
        "family": "domestic_metro",
        "domestic_topic": "technology",
        "types": ("技術新知",),
        "lang": "zh",
        "query": "臺灣 捷運 號誌",
    },
    {
        "family": "domestic_metro",
        "domestic_topic": "technology",
        "types": ("技術新知",),
        "lang": "zh",
        "query": "臺灣 捷運 維修",
    },
    {
        "family": "domestic_metro",
        "domestic_topic": "major_accident",
        "types": ("重大事故",),
        "lang": "zh",
        "query": "臺灣 捷運 安全",
    },
    {
        "family": "domestic_metro",
        "domestic_topic": "policy",
        "types": ("營運政策",),
        "lang": "zh",
        "query": "臺灣 捷運 票務",
    },
    {
        "family": "domestic_metro",
        "domestic_topic": "dispute",
        "types": ("營運爭議",),
        "lang": "zh",
        "query": "臺灣 捷運 爭議",
    },
]

SERVICE_OPENING_QUERY_SPECS = [
    {
        "family": SERVICE_OPENING_CATEGORY_KEY,
        "types": ("營運政策",),
        "lang": "en",
        "query": "metro subway urban rail light rail tram opens to passengers enters revenue service",
    },
    {
        "family": SERVICE_OPENING_CATEGORY_KEY,
        "types": ("營運政策",),
        "lang": "en",
        "query": "metro subway light rail tram extension station begins passenger service commercial operations",
    },
]

DOMESTIC_SERVICE_OPENING_QUERY_SPECS = [
    {
        "family": SERVICE_OPENING_CATEGORY_KEY,
        "domestic_topic": "service_opening",
        "types": ("營運政策",),
        "lang": "zh",
        "query": "臺灣 捷運 通車",
    },
]

ELECTROMECHANICAL_PROCUREMENT_QUERY_SPECS = [
    {
        "family": ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY,
        "lang": "en",
        "query": "urban rail metro signalling CBTC train control contract tender award",
    },
    {
        "family": ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY,
        "lang": "en",
        "query": "metro traction power substation electrical system contract procurement",
    },
    {
        "family": ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY,
        "lang": "en",
        "query": "metro telecommunications AFC platform screen doors contract tender",
    },
    {
        "family": ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY,
        "lang": "en",
        "query": "metro rolling stock trains contract order procurement",
    },
    {
        "family": ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY,
        "lang": "en",
        "query": "metro station MEP electromechanical systems contract tender",
    },
]

DOMESTIC_ELECTROMECHANICAL_PROCUREMENT_QUERY_SPECS = [
    {
        "family": ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY,
        "domestic_topic": "electromechanical_procurement",
        "types": (ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL,),
        "lang": "zh",
        "query": "臺灣 捷運 機電 決標",
    },
    {
        "family": ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY,
        "domestic_topic": "electromechanical_procurement",
        "types": (ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL,),
        "lang": "zh",
        "query": "臺灣 捷運 車輛 採購",
    },
]

FORWARD_TECHNOLOGY_QUERY_SPECS = [
    {"family": "forward_technology", "lang": "en", "query": "metro subway urban rail light rail tram novel material prototype tested reduce vehicle weight energy consumption"},
    {"family": "forward_technology", "lang": "en", "query": "metro subway urban rail track new coating pilot trial reduce friction wear extend service life"},
    {"family": "forward_technology", "lang": "en", "query": "metro subway urban rail AI machine learning computer vision sensor pilot automated inspection reduce inspection time"},
    {"family": "forward_technology", "lang": "en", "query": "metro subway urban rail predictive maintenance condition monitoring pilot improve reliability reduce maintenance"},
    {"family": "forward_technology", "lang": "en", "query": "metro subway urban rail traction energy optimization regenerative energy storage demonstration reduce energy consumption improve efficiency"},
    {"family": "forward_technology", "lang": "en", "query": "metro subway urban rail new fire resistant composite insulation material prototype tested improve safety reduce emissions"},
    {"family": "forward_technology", "lang": "en", "query": "metro subway urban rail digital twin cybersecurity anomaly detection control network pilot improve reliability"},
    {"family": "forward_technology", "lang": "en", "query": "metro subway urban rail advanced signalling virtual coupling RAMS verification validation field test improve capacity"},
]

ANNUAL_TECHNOLOGY_BREAKTHROUGH_QUERY_SPECS = [
    {"family": "technology", "lang": "en", "query": "metro subway MRT light rail new material advanced material composite lightweight material fire resistant material"},
    {"family": "technology", "lang": "en", "query": "metro subway MRT light rail SiC semiconductor traction energy storage battery technology"},
    {"family": "technology", "lang": "en", "query": "metro subway MRT light rail breakthrough novel sensor advanced signalling"},
]

REGION_QUERY_LANGUAGES = {
    "日本": "ja", "韓國": "ko", "香港": "zh", "法國": "fr", "德國": "de",
    "西班牙": "es", "義大利": "it", "葡萄牙": "pt", "俄羅斯": "ru",
    "加拿大": "en", "瑞士": "de", "奧地利": "de", "巴西": "pt",
}

QUERY_FAMILY_BY_TYPE_INDEX = {
    0: "technology",
    1: "major_accident",
    2: "policy",
    3: "dispute",
}

SEARCH_LANGUAGE_MARKERS = [
    ("ja", ["地下鉄", "メトロ", "脱線", "運休", "新幹線"]),
    ("ko", ["지하철", "도시철도", "탈선", "운행중단"]),
    ("zh", ["地鐵", "地铁", "捷運", "輕軌", "脫軌", "調查"]),
    ("ru", ["метро", "трамвай", "сход", "пожар", "биометрическая"]),
    ("de", ["u-bahn", "stadtbahn", "straßenbahn", "entgleisung", "brandschutz"]),
    ("fr", ["métro", "tramway", "déraillement", "évacuation", "enquête"]),
    ("es", ["tranvía", "descarrilamiento", "colisión", "investigación"]),
    ("it", ["metropolitana", "sciopero", "funicolare", "segnalamento", "deragliamento"]),
    ("pt", ["eletrico", "elétrico", "greve", "investigacao", "investigação", "sinalizacao", "sinalização", "descarrilamento"]),
]

def build_rss_sources(lookback_days: int) -> list[tuple[str, str]]:
    RSS_SOURCES = [
        ("Railway Gazette International（已併入 Metro Report International 都市軌道報導）",
         "https://www.railwaygazette.com/149.rss"),
        ("Railway Gazette Urban rail（Google News代理）",
         google_news_site_proxy_url("railwaygazette.com", int(lookback_days), TRANSIT_NEWS_TERMS)),
        ("International Railway Journal (IRJ)", "https://www.railjournal.com/feed/"),
        ("IRJ metro / light rail（Google News代理）",
         google_news_site_proxy_url("railjournal.com", int(lookback_days), TRANSIT_NEWS_TERMS)),
        ("Railway Technology", "https://www.railway-technology.com/feed/"),
        ("Railway-News", "https://railway-news.com/feed/"),
        ("Global Railway Review", "https://www.globalrailwayreview.com/feed/"),
        ("Intelligent Transport", "https://www.intelligenttransport.com/feed/"),
        ("Urban Transport Magazine（Google News代理）",
         google_news_site_proxy_url("urban-transport-magazine.com", int(lookback_days), TRANSIT_NEWS_TERMS)),
        ("Mass Transit Magazine", "https://www.masstransitmag.com/rss"),
        ("METRO Magazine Rail（Google News代理）",
         google_news_site_proxy_url("metro-magazine.com", int(lookback_days), TRANSIT_NEWS_TERMS)),
        ("Smart Cities Dive Transportation（Google News代理）",
         google_news_site_proxy_url("smartcitiesdive.com", int(lookback_days), TRANSIT_NEWS_TERMS)),
        ("Railway Age urban rail / light rail（Google News代理）",
         google_news_site_proxy_url("railwayage.com", int(lookback_days), TRANSIT_NEWS_TERMS)),
        ("UITP（無官方RSS，改用Google News代理）",
         google_news_site_proxy_url("uitp.org", int(lookback_days), TRANSIT_NEWS_TERMS)),
        # 2026-07 查證：masstransit.network 的 RSS 端點實際回傳的是「會員名錄」頁面
        # （人名列表），不是新聞內容，已移除，改依賴下方已驗證有效的 Global Mass Transit。
        ("Global Mass Transit", "https://www.globalmasstransit.net/feed"),
        # 東洋經濟原本用全站 RSS，抓到的 20 篇裡沒有一篇是鐵道新聞（全是投資理財/職場/美食）。
        # 改用 Google News 代理鎖定 site:toyokeizai.net + 鐵道關鍵字，才會是真的鐵道新聞。
        ("東洋經濟 Online 鐵道（Google News代理，鎖定 site:toyokeizai.net + 鐵道）",
         google_news_site_proxy_url("toyokeizai.net", int(lookback_days), '(地下鉄 OR メトロ OR 新交通システム OR 都市鉄道 OR 路面電車) -新幹線 -JR -在来線 -バス', "ja", "JP", "ja")),
        ("乗りものニュース", "https://trafficnews.jp/feed"),
        ("鉄道総合技術研究所 RTRI（無官方RSS，改用Google News代理）",
         google_news_site_proxy_url("rtri.or.jp", int(lookback_days), '(地下鉄 OR メトロ OR 新交通システム OR 都市鉄道 OR 軌道) -新幹線 -在来線 -貨物鉄道', "ja", "JP", "ja")),
        ("Transit Jam", "https://transitjam.com/feed/"),
        ("TfL 官方新聞（Google News代理）",
         google_news_site_proxy_url("tfl.gov.uk", int(lookback_days), '(Tube OR Underground OR tram OR DLR OR "London Overground") -bus -coach', "en-GB", "GB", "en")),
        ("MTA 官方新聞（Google News代理）",
         google_news_site_proxy_url("mta.info", int(lookback_days), '(subway OR metro OR signal OR accessibility OR safety)')),
        ("WMATA 官方新聞（Google News代理）",
         google_news_site_proxy_url("wmata.com", int(lookback_days), '(Metro OR Metrorail OR subway OR station OR railcar) -bus')),
        ("TTC 官方新聞（Google News代理）",
         google_news_site_proxy_url("ttc.ca", int(lookback_days), '(subway OR streetcar OR signal OR fleet OR safety)', "en-CA", "CA", "en")),
        ("TransLink 官方新聞（Google News代理）",
         google_news_site_proxy_url("translink.ca", int(lookback_days), '(SkyTrain OR "Canada Line" OR rail transit OR station) -bus', "en-CA", "CA", "en")),
        ("RATP 官方新聞（Google News代理）",
         google_news_site_proxy_url("ratp.fr", int(lookback_days), '(metro OR tramway OR automatisation OR securite) -bus -RER', "fr", "FR", "fr")),
        ("Société des grands projets 官方新聞（Google News代理）",
         google_news_site_proxy_url("societedesgrandsprojets.fr", int(lookback_days), '("Grand Paris Express" OR metro OR gare)', "fr", "FR", "fr")),
        ("LTA 官方新聞（Google News代理）",
         google_news_site_proxy_url("lta.gov.sg", int(lookback_days), '(MRT OR LRT OR "Thomson-East Coast Line" OR "rail transit") -bus', "en-SG", "SG", "en")),
        ("MTR 官方新聞（Google News代理）",
         google_news_site_proxy_url("mtr.com.hk", int(lookback_days), '(MTR OR 港鐵 OR 地鐵 OR 輕鐵 OR signalling) -bus', "zh-HK", "HK", "zh-Hant")),
        ("Seoul Metro 官方新聞（Google News代理）",
         google_news_site_proxy_url("seoulmetro.co.kr", int(lookback_days), '(지하철 OR 도시철도 OR 안전 OR 열차)', "ko", "KR", "kr")),
        ("Tokyo Metro 官方新聞（Google News代理）",
         google_news_site_proxy_url("tokyometro.jp", int(lookback_days), '(東京メトロ OR 地下鉄 OR 安全 OR 車両)', "ja", "JP", "ja")),
    ]
    return RSS_SOURCES

KNOWN_BAD_OFFICIAL_RSS_HOSTS = {
    "railwaygazette.com",
    "railjournal.com",
    "globalrailwayreview.com",
    "intelligenttransport.com",
    "masstransitmag.com",
    "trafficnews.jp",
}

KNOWN_BAD_OFFICIAL_RSS_LABELS = [
    "Railway Gazette International",
    "International Railway Journal",
    "Global Railway Review",
    "Intelligent Transport",
    "Mass Transit Magazine",
    "乗りものニュース",
]

def _source_skip_record(
    source_name: str,
    url: str,
    status: str,
    reason: str,
    item_count: int = 0,
) -> dict:
    host = urlparse(url or "").netloc.lower().removeprefix("www.")
    return {
        "source_name": source_name,
        "method": "Google News 代理" if "news.google.com" in host else "官方 RSS",
        "status": status,
        "item_count": item_count,
        "error_message": reason,
        "fallback_used": False,
    }

def _source_identity(source: tuple[str, str]) -> tuple[str, str]:
    source_name, url = source
    return source_name.casefold(), url.casefold()

def _is_known_bad_official_rss(source_name: str, url: str) -> bool:
    parsed = urlparse(url or "")
    host = parsed.netloc.lower().removeprefix("www.")
    if "news.google.com" in host:
        return False
    if host in KNOWN_BAD_OFFICIAL_RSS_HOSTS:
        return True
    source_lower = (source_name or "").casefold()
    return any(label.casefold() in source_lower for label in KNOWN_BAD_OFFICIAL_RSS_LABELS)

FORMAL_SOURCE_PROXY_LABELS = {
    "日本地下鉄/メトロ", "韓國地下鐵", "Singapore MRT", "香港港鐵",
    "Australia Metro", "UK Underground", "France Metro", "Germany U-Bahn",
    "Spain Metro/Light Rail", "Netherlands Metro", "Switzerland Metro/Tram",
    "US Subway/Metro", "Canada Metro", "Italy Metro/Tram", "Sweden Metro/Tram",
    "Austria U-Bahn/Tram", "Denmark Metro/Light Rail", "Norway Metro/Tram",
}

def _conditional_news_sources(fast_mode: bool, lookback_days: int, lookback_int: int, standards_enabled: bool) -> tuple[list[tuple[str, str]], list[dict]]:
    sources: list[tuple[str, str]] = []
    skipped: list[dict] = []
    days = int(lookback_days)
    apta_source = (
        "APTA rail transit（Google News代理）",
        google_news_site_proxy_url("apta.com", days, TRANSIT_NEWS_TERMS),
    )
    smartcitiesworld_source = (
        "SmartCitiesWorld rail transit（Google News代理）",
        google_news_site_proxy_url(
            "smartcitiesworld.net",
            days,
            '("urban rail" OR metro OR subway OR "light rail" OR tram OR MRT OR "rail transit") -bus -parking -road -MaaS',
        ),
    )

    if lookback_int in ADVANCED_LOOKBACK_OPTIONS or standards_enabled:
        sources.append(apta_source)
    else:
        skipped.append(_source_skip_record(
            apta_source[0],
            apta_source[1],
            "long_term_only_source",
            "APTA 僅於長期報告或規範更新啟用",
        ))

    if fast_mode:
        skipped.append(_source_skip_record(
            smartcitiesworld_source[0],
            smartcitiesworld_source[1],
            "low_priority_source",
            "SmartCitiesWorld 低頻來源，快速模式跳過",
        ))
    else:
        sources.append(smartcitiesworld_source)

    return sources, skipped

REGION_NEWS_QUERIES: dict[str, list[tuple[str, str, str, str, str]]] = {
    "日本": [("Google News地區代理－日本地下鉄/メトロ",
             "(地下鉄 OR メトロ OR 新交通システム OR 都市鉄道 OR 路面電車) -新幹線 -JR -在来線 -高速バス -ゲーム -Steam -スタンプラリー -アニメ", "ja", "JP", "ja")],
    "韓國": [("Google News地區代理－韓國地下鐵",
             "(지하철 OR 도시철도 OR 경전철)", "ko", "KR", "kr")],
    "新加坡": [("Google News地區代理－Singapore MRT",
              "(MRT OR LTA OR SMRT Singapore)", "en-SG", "SG", "en")],
    "香港": [("Google News地區代理－香港港鐵",
             "(港鐵 OR MTR 香港)", "zh-HK", "HK", "zh-Hant")],
    "澳洲": [("Google News地區代理－Australia Metro",
             "(Sydney Metro OR Melbourne Metro OR Brisbane Metro OR light rail) -bus -coach -highway", "en-AU", "AU", "en")],
    "英國": [("Google News地區代理－UK Underground",
             "(London Underground OR TfL Tube OR DLR OR tram) -bus -coach -highway -National Rail", "en-GB", "GB", "en")],
    "法國": [("Google News地區代理－France Metro",
             "(Metro Paris OR RATP OR Grand Paris Express)", "fr", "FR", "fr")],
    "德國": [("Google News地區代理－Germany U-Bahn",
             "(U-Bahn OR Stadtbahn OR tram OR Straßenbahn) -ICE -DB -Fernverkehr -Spiel -Kinofilm -Videospiel", "de", "DE", "de")],
    "西班牙": [("Google News地區代理－Spain Metro/Light Rail",
              "(Madrid Metro OR Barcelona Metro OR Metro de Madrid OR tranvia OR tranvía OR light rail) -AVE -alta velocidad -autobus", "es", "ES", "es")],
    "荷蘭": [("Google News地區代理－Netherlands Metro",
             "(Amsterdam metro OR Rotterdam metro)", "nl", "NL", "nl")],
    "瑞士": [("Google News地區代理－Switzerland Metro/Tram",
             "(Zurich tram OR Lausanne metro)", "de-CH", "CH", "de")],
    "美國": [("Google News地區代理－US Subway/Metro",
             "(subway OR Metrorail OR light rail OR streetcar OR people mover) United States -Amtrak -intercity -bus -coach -highway", "en-US", "US", "en")],
    "加拿大": [("Google News地區代理－Canada Metro",
              "(TTC subway OR SkyTrain Vancouver OR REM Montreal OR light rail) -bus -coach -highway", "en-CA", "CA", "en")],
    "義大利": [("Google News地區代理－Italy Metro/Tram",
              "(metro OR metropolitana OR tram OR ferrovia urbana)", "it", "IT", "it")],
    "瑞典": [("Google News地區代理－Sweden Metro/Tram",
             "(Stockholm metro OR Gothenburg tram OR light rail)", "sv", "SE", "sv")],
    "奧地利": [("Google News地區代理－Austria U-Bahn/Tram",
              "(Vienna U-Bahn OR Wiener Linien OR tram)", "de-AT", "AT", "de")],
    "丹麥": [("Google News地區代理－Denmark Metro/Light Rail",
             "(Copenhagen Metro OR Odense Letbane OR light rail)", "da", "DK", "da")],
    "挪威": [("Google News地區代理－Norway Metro/Tram",
             "(Oslo Metro OR Sporveien OR tram OR light rail)", "no", "NO", "no")],
}

def build_region_news_sources(regions: list[str], days: int, fast_mode: bool = False) -> list[tuple[str, str]]:
    """依勾選國家動態組出 Google News 地區代理 RSS 來源清單。"""
    sources: list[tuple[str, str]] = []
    days = max(1, min(int(days), 365))
    for region in regions:
        region_queries = REGION_NEWS_QUERIES.get(region, [])
        if fast_mode:
            region_queries = region_queries[:1]
        for label, keyword, hl, gl, lang in region_queries:
            query = f"{keyword} when:{days}d"
            url = (
                "https://news.google.com/rss/search?q="
                f"{urllib.parse.quote(query)}&hl={hl}&gl={gl}&ceid={gl}:{lang}"
            )
            sources.append((label, url))
    return sources

def build_standards_news_sources(days: int) -> list[tuple[str, str]]:
    """只有勾選規範更新時，才組出標準版本狀態的 Google News RSS 代理來源。"""
    sources: list[tuple[str, str]] = []
    days = max(1, min(int(days), 365))
    update_terms = " OR ".join(f'"{term}"' for term in STANDARD_UPDATE_TERMS)
    for category, standards in STANDARDS_WATCHLIST.items():
        for standard in standards:
            query = f'"{standard}" ({update_terms}) when:{days}d'
            sources.append((f"規範更新代理－{category}－{standard}", google_news_search_url(query)))
    return sources

FAST_SOURCE_KEYWORDS = (
    "railway-news",
    "railway gazette",
    "urban transport magazine",
    "mass transit magazine",
    "metro magazine",
    "mta",
    "tfl",
    "lta",
    "mtr",
    "tokyo metro",
    "ttc",
    "wmata",
    "translink",
)

def select_fast_rss_sources(sources: list[tuple[str, str]]) -> list[tuple[str, str]]:
    selected: list[tuple[str, str]] = []
    seen_keys: set[str] = set()
    for source_name, url in sources:
        haystack = f"{source_name} {url}".casefold()
        if not any(keyword in haystack for keyword in FAST_SOURCE_KEYWORDS):
            continue
        netloc = urlparse(url).netloc.lower().removeprefix("www.")
        dedupe_key = source_name.casefold() if netloc == "news.google.com" else (netloc or source_name.casefold())
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        selected.append((source_name, url))
    return selected or sources[: min(12, len(sources))]

def build_run_news_sources(
    region_sources: list[tuple[str, str]],
    standards_sources: list[tuple[str, str]],
    fast_mode: bool,
    *, rss_sources: list[tuple[str, str]], lookback_days: int,
    lookback_int: int, standards_enabled: bool,
    return_skipped: bool = False,
) -> list[tuple[str, str]] | tuple[list[tuple[str, str]], list[dict]]:
    skipped_statuses: list[dict] = []
    usable_sources: list[tuple[str, str]] = []
    for source_name, url in rss_sources:
        if _is_known_bad_official_rss(source_name, url):
            skipped_statuses.append(_source_skip_record(
                source_name,
                url,
                "skipped_known_bad",
                "已知官方 RSS 長期失效，保留代理或未來自訂 RSS 可能性",
            ))
            continue
        usable_sources.append((source_name, url))

    conditional_sources, conditional_skips = _conditional_news_sources(fast_mode, lookback_days, lookback_int, standards_enabled)
    usable_sources.extend(conditional_sources)
    skipped_statuses.extend(conditional_skips)

    if fast_mode:
        selected_base = select_fast_rss_sources(usable_sources)
        selected_keys = {_source_identity(source) for source in selected_base}
        for source_name, url in usable_sources:
            if _source_identity((source_name, url)) not in selected_keys:
                skipped_statuses.append(_source_skip_record(
                    source_name,
                    url,
                    "skipped_fast_mode",
                    "快速模式跳過低優先來源",
                ))
        base_sources = selected_base
    else:
        base_sources = usable_sources

    combined = base_sources + region_sources + standards_sources
    if return_skipped:
        return combined, skipped_statuses
    return combined
