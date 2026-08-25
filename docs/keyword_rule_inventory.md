# Keyword / Rule Inventory Freeze

**Artifact:** `KEYWORD_RULE_FREEZE_RESULT`
**Inventory version:** `A-FREEZE-2026-08-25`
**Baseline:** branch `codex/fix-v22-report-quality`, HEAD `5681a9ceb615d2f99bdb1ed23af7d2ab40bd384c`
**Scope:** Pack A1–A7 contracts and the active production code at the baseline above.
**Mode:** read-only inventory / contract freeze.

This file is a generated governance record of the executable sources. It is not a
second keyword source and does not change runtime behaviour. The executable lists
remain in the files named in the owner column. Terms below are representative
anchors for long lists; the source constant is the authoritative complete list.

## 1. Freeze rules

Every row is classified using exactly one of the following values:

`SEARCH_QUERY`, `SEARCH_EXCLUSION`, `NORMALIZATION`, `GEOGRAPHY_EVIDENCE`,
`EM_FORMAL_EVIDENCE`, `CATEGORY_GATE_EVIDENCE`, `CATEGORY_CONFLICT_RULE`,
`EVENT_IDENTITY_EVIDENCE`, `TEMPORAL_ROUTING`, `TEMPORAL_VALIDATION`,
`SELECTION_ONLY`, `DISPLAY_ONLY`, `COMPATIBILITY_ALIAS`,
`DEAD_OR_UNREACHABLE`.

The inventory records ownership, active state, terms/patterns, language and
provider scope, precedence, output fields, consumers, fallback status, duplicate
ownership, collision risk, coverage gaps and notes. No term, threshold, precedence,
Gate, taxonomy, identity, temporal route, ranking or fallback was added or removed
for this freeze.

## 2. Canonical ownership map

| Domain | Official owner | Active output | Duplicate formal owner | Freeze finding |
|---|---|---|---|---|
| Search templates and family metadata | `search_queries.py`: `QuerySpec`, `*_QUERY_SPECS`, `active_query_specs_for_family` | query, family, lang, topic, retrieval lane | NO | One provider-neutral template owner. `ddgs_search_service.py` consumes it; it does not maintain a second template list. |
| Region query expansion | `config.py`: `REGION_SEARCH_TERMS` and `search_queries.py` regional source builders | query prefix/source route | NO | Temporal router imports the same region map; no temporal keyword list. |
| Raw retrieval adapters | `ddgs_search_service.py`, `rss_feed_service.py` | raw items, provider status | NO | Adapter-specific discovery filters are not formal category owners. |
| Geography resolution | `article_processor.py`: `_region_resolution_details`, `_canonical_candidate_region`, `normalize_country` | `resolved_region`, evidence records | NO | Selector only consumes resolved geography; direct-call resolver is compatibility only. |
| E&M taxonomy | `electromechanical_taxonomy.py`: `classify_candidate_electromechanical` | `core_systems`, winning/rejected evidence | NO | Selector-local augmentation is gone for authoritative candidates; its compatibility terms remain labelled below. |
| Category Gate evidence | `article_selector.py`: `evaluate_category_gates` and `_compute_*_gate` | gate booleans, positive signals, failure reasons | NO formal output owner | Gate evidence is executable here; category conflict resolution is separate and singular. |
| Category conflict / primary category | `category_conflict_resolver.py`: `resolve_primary_category` | `primary_category`, conflict diagnostics | NO | Dominance precedence is 600/500/400/350/300/200. |
| Event identity / dedupe | `event_identity.py`: `build_event_identity`, `compare_event_candidates` | canonical event ID, duplicate diagnostics | NO | Selector/postprocessor consume the upstream identity and do not own a second fuzzy identity. |
| Temporal plan and verification | `temporal_retrieval_service.py`: `TemporalRetrievalRouter` | requested/verified bucket, coverage diagnostics | NO | Annual credit is `verified_bucket_only`. |
| Selection ranking/diversity | `article_selector.py`: `score_news_candidate`, `select_candidates_by_python` | scores, selected pool, diversity diagnostics | NO | A7 boundary prevents selector from re-owning formal gates. |
| Prompt/display | `report_prompt_service.py`, `report_postprocessor.py`, `report_formatter.py` | prompt fields, section labels, final Markdown/HTML | NO | Compatibility aliases are display/accessor only. |

## 3. Detailed inventory rows — retrieval and search

The following table is the required row schema. A dash means the field is not
applicable to that rule rather than unknown.

| Rule ID | Classification | Owner file / function / constant | Active | Positive / negative terms | Regex / pattern | Language / query / domain | Precedence | Output field | Consumers | Fallback | Duplicate owner | Collision / coverage gap | Notes |
|---|---|---|---|---|---|---|---:|---|---|---|---|---|---|
| KQ-001 | SEARCH_QUERY | `search_queries.py`: `QuerySpec`, `SEARCH_QUERY_SPECS` (61 specs) | YES | metro, subway, MRT, LRT, tram; CBTC/signalling, rolling stock, AFC, power, communications, maintenance | query string | en, de, fr, es, it, pt, ru, ja, ko, zh; DDGS/Google News | 1 | `query`, `family`, `lang` | DDGS, temporal router | NO | NO | Broad technology family can return non-urban rail; downstream scope Gate owns precision | Canonical technology/accident/policy/dispute/official-investigation templates. |
| KQ-002 | SEARCH_QUERY | `search_queries.py`: `DOMESTIC_METRO_QUERY_SPECS` | YES | 臺灣/捷運/號誌/維修/安全/票務/爭議 | literal templates | zh; domestic lane | 2 | domestic query metadata | workflow, DDGS | NO | NO | Domestic scope terms intentionally narrow | No new alias added. |
| KQ-003 | SEARCH_QUERY | `search_queries.py`: `SERVICE_OPENING_QUERY_SPECS`, `DOMESTIC_SERVICE_OPENING_QUERY_SPECS` | YES | opens to passengers, revenue/commercial service, begins passenger service; 通車 | literal templates | en/zh; Google News/DDGS | 3 | `service_opening` family | workflow, Gates | NO | NO | Future/planning/testing text is not an actual opening | Formal opening Gate owns actual-vs-future distinction. |
| KQ-004 | SEARCH_QUERY | `search_queries.py`: `ELECTROMECHANICAL_PROCUREMENT_QUERY_SPECS`, domestic counterpart | YES | urban rail, signalling/CBTC, traction power/substation, telecom/AFC/PSD, rolling stock, contract/tender/award | literal templates and `site:` hints | en/zh; DDGS | 4 | `electromechanical_procurement` family | workflow, procurement Gate | NO | NO | Snippet evidence may be insufficient; no keyword rescue added | Contract/project/system compatibility remains required. |
| KQ-005 | SEARCH_QUERY | `search_queries.py`: `FORWARD_TECHNOLOGY_QUERY_SPECS`, fallback specs and lane budgets | YES | energy, materials, predictive maintenance, digital twin, advanced control; broad/dual-anchor/source-aware/quoted lanes | literal templates | en; DDGS forward lane | 5 | `forward_technology`, topic, retrieval lane | forward radar, selector | Bounded source-aware fallback only | NO | Historical run had raw→0 Gate pass; inventory does not relax Gate | Query precision and Gate recall remain separate findings. |
| KQ-006 | SEARCH_QUERY | `search_queries.py`: `GLOBAL_REGIONAL_COVERAGE_QUERY_SPECS`, `ANNUAL_TECHNOLOGY_BREAKTHROUGH_QUERY_SPECS` | YES | region anchors; material/SiC/energy storage/sensor/signalling | literal templates | regional language metadata; DDGS/research supplement | 6 | query metadata | annual/research supplement | NO | NO | Supplement is not annual temporal authority | No annual-specific Gate. |
| KQ-007 | SEARCH_QUERY | `search_queries.py`: `REGION_QUERY_LANGUAGES`, `SEARCH_LANGUAGE_MARKERS` | YES | ja/ko/zh/ru/de/fr/es/it/pt markers | marker membership | provider query language | 7 | `lang` inference | DDGS metadata, diagnostics | NO | NO | Marker is language metadata, not geography evidence | Query language cannot override event geography. |
| KQ-008 | SEARCH_EXCLUSION | `config.py`: `TRANSIT_NEWS_TERMS`; `search_queries.py`: regional RSS query strings | YES | positive urban rail anchors | explicit `-` terms: high-speed rail, HSR, Shinkansen, bullet train, intercity, regional rail, freight, locomotive, bus, coach, highway; Japanese `-新幹線 -JR -在来線` | Google News RSS and Direct RSS source builders | 8 | provider query URL | RSS adapter, temporal router | NO | NO | Query/source precision depends on provider syntax | JR and 新幹線 exclusions are present in Japanese routes. |
| KQ-009 | SEARCH_EXCLUSION | `config.py`: `NON_URBAN_TRANSPORT_TERMS`, `NON_URBAN_HARD_EXCLUDE_TERMS`; `article_selector.py`: `GENERAL_RAIL_EXCLUDE_TERMS` | YES | — | term membership | all languages; candidate text | 9 | preliminary/final exclusion reason | article processor, selector Gates | NO | GUARDED duplicate by design | `railway` alone is not a hard exclusion; commuter/regional/freight/bus/road/aviation/high-speed terms are. |
| KQ-010 | SEARCH_EXCLUSION | `config.py`: `DOMESTIC_NON_METRO_TERMS`, `DOMESTIC_SCOPE_EXCLUDED_TERMS` | YES | metro context required | negative domestic terms: TRA/台鐵, THSR/高鐵, bus, road, aviation; civil/planning-only terms | domestic scope | 10 | `domestic_filter_reason` | article processor, procurement Gate | NO | NO | Pure civil/planning domestic material is outside domestic metro scope | Does not alter international scope. |
| KQ-011 | SEARCH_EXCLUSION | `config.py`: `BLOCKED_DOMAINS`, `LOW_VALUE_EXCLUDED_HOSTS`, portal/social domains | YES | — | host suffix/exact host | source URL | 11 | source validity/tier | article processor, selector | NO | NO | Source availability is a coverage limitation, not a Gate threshold | `msn/yahoo/aol/patch` portal reposts are low quality, not universally blocked. |
| KQ-012 | SEARCH_QUERY | `config.py`: journal/academic source query lists and `JOURNAL_*` terms | YES | urban rail transit, CBTC, maintenance, energy, digital twin, RAMS; excludes high-speed/freight/intercity/road/bus/pure algorithm | `site:` query templates, domain allow-list | academic provider lane | 12 | research candidate metadata | journal service, prompt | NO | NO | Academic lane is a supplement and cannot claim annual bucket credit | SEO/tourism terms are source/content exclusions. |
| KQ-013 | SEARCH_QUERY | `ddgs_search_service.py`: `_active_query_specs`, `build_search_queries`, `_annual_quarter_windows` | YES | consumes KQ-001…KQ-006 | query compaction and period suffix | DDGS; annual quarter metadata | 13 | query status/metadata | workflow, debug | bounded provider error handling | NO | DDGS date hints are untrusted for annual credit | No second canonical keyword list. |
| KQ-014 | SEARCH_EXCLUSION | `ddgs_search_service.py`: `_basic_search_url_exclusion_reason`, `_basic_search_date_exclusion_reason` | YES | — | URL/page/date checks | DDGS result | 14 | exclusion reason | workflow diagnostics | NO | NO | Provider result filtering is adapter-level and does not replace category Gate | `DDGS_ERROR_STATUSES` is status taxonomy only. |
| KQ-015 | SEARCH_QUERY | `ddgs_search_service.py`: `FORWARD_DISCOVERY_*` signals | YES | rail + technology + evidence + application terms | membership checks on title/snippet | DDGS forward only | 15 | discovery eligibility/status | forward radar | bounded fallback lane | GUARDED | `forward_technology` also has selector Gate vocabulary; this is discovery filtering, not a second query owner | Keep separate until an independent audit changes it. |

### Active constant census (complete source groups)

The following census prevents a grouped row from hiding an active owner. The
complete term values stay in the cited production constants.

| Rule ID | Classification | Owner source groups | Active | Scope / output |
|---|---|---|---|---|
| SRC-001 | CATEGORY_GATE_EVIDENCE | `LOW_VALUE_POLICY_TERMS`, `HIGH_VALUE_POLICY_TERMS`, `ACCIDENT_SIGNAL_TERMS`, `SAFETY_INCIDENT_DETAIL_TERMS`, `LOW_VALUE_OFFICIAL_NOTICE_TERMS`, `NON_TECH_NEWS_EXCLUDE_TERMS`, `NON_ACCIDENT_CONTEXT_TERMS`, `ACADEMIC_ACCIDENT_NON_EVENT_TERMS` | YES | policy/accident/technical context and exclusion signals |
| SRC-002 | CATEGORY_GATE_EVIDENCE | `OPERATIONAL_EVENT_TERMS`, `MAJOR_SERVICE_ADJUSTMENT_TERMS`, `MAJOR_SERVICE_ADJUSTMENT_SUBSTANTIVE_TERMS`, `SYSTEM_DISRUPTION_TERMS`, `SYSTEM_DISRUPTION_IMPACT_TERMS`, `URBAN_RAIL_INCIDENT_CONTEXT_TERMS`, `GENERAL_RAIL_EXCLUDE_TERMS` | YES | operational incident, service impact and urban-rail scope |
| SRC-003 | CATEGORY_GATE_EVIDENCE | `PROCUREMENT_LIST_NOTICE_TERMS`, `PROJECT_ONLY_ACTION_TERMS`, `ELECTROMECHANICAL_PROCUREMENT_SYSTEM_TERMS`, `ELECTROMECHANICAL_PROCUREMENT_ACTION_TERMS`, `PROCUREMENT_URBAN_RAIL_ANCHOR_TERMS`, `ELECTROMECHANICAL_GENERIC_SCOPE_TERMS` | YES | procurement system/action and low-value/project-only exclusions |
| SRC-004 | EM_FORMAL_EVIDENCE | `ROLLING_STOCK_EVENT_TERMS`, `DEPOT_FACILITY_TERMS`, `NON_CORE_EQUIPMENT_TERMS`, `CROSS_SYSTEM_TECHNICAL_APPLICATION_TERMS`, `TECHNICAL_THEME_TERM_GROUPS` | YES | E&M contextual semantics and report themes; formal system result still from taxonomy owner |
| SRC-005 | CATEGORY_GATE_EVIDENCE | `ELECTROMECHANICAL_PROCUREMENT_CIVIL_TERMS`, `ELECTROMECHANICAL_PROCUREMENT_PLANNING_TERMS`, `ELECTROMECHANICAL_PROCUREMENT_DETAILED_DESIGN_TERMS`, `ELECTROMECHANICAL_PROCUREMENT_SEPARATE_PACKAGE_TERMS`, `ELECTROMECHANICAL_PROCUREMENT_STATION_CONTEXT_TERMS` | YES | civil/planning/design/package guards |
| SRC-006 | CATEGORY_GATE_EVIDENCE | `SUBSTANTIVE_TECHNICAL_DETAIL_TERMS`, `SUBSTANTIVE_POLICY_DETAIL_TERMS`, `STRONG_TECHNICAL_DETAIL_TERMS`, `MEDIUM_TECHNICAL_DETAIL_TERMS`, `WEEKLY_BACKFILL_ALLOWED_TERMS` | YES | technology triad and policy detail evidence |
| SRC-007 | SEARCH_EXCLUSION | `LOW_REPORT_VALUE_TERMS`, `FINANCIAL_MARKET_TERMS`, `PROPERTY_OR_CAMPUS_DEVELOPMENT_TERMS`, `GENERIC_TEST_WITHOUT_TECH_TERMS`, `ENGINEERING_MILESTONE_ONLY_TERMS`, `SECURITY_OR_CRIME_TERMS` | YES | low-value, finance/property/security/project exclusions |
| SRC-008 | CATEGORY_GATE_EVIDENCE | `EQUIPMENT_FAILURE_TERMS`, `ENVIRONMENTAL_OPERATION_ABNORMALITY_TERMS`, `TECHNICAL_OPERATION_IMPACT_TERMS`, `MAJOR_SECURITY_RAIL_IMPACT_TERMS`, `CORE_METRO_TECHNICAL_TERMS`, `TECHNICAL_IMPLEMENTATION_TERMS` | YES | technical operation, accident and implementation evidence |
| SRC-009 | CATEGORY_GATE_EVIDENCE | `INNOVATION_NOVELTY_TERMS`, `INNOVATION_APPLICATION_TERMS`, `INNOVATION_EFFECT_TERMS`, `INNOVATION_SPECIAL_TECH_TERMS`, `INNOVATION_ARCHITECTURE_TERMS`, `INNOVATION_FORWARD_*` | YES | research/innovation evidence and quantified-benefit patterns |
| SRC-010 | CATEGORY_GATE_EVIDENCE | `FORWARD_GATE_APPLICATION_OBJECT_TERMS`, `FORWARD_GATE_NOVELTY_TERMS`, `FORWARD_GATE_VALIDATION_TERMS`, `FORWARD_GATE_BENEFIT_TERMS`, `FORWARD_TRACK_B_*`, `FORWARD_MATERIAL_TERMS`, `FORWARD_TRACK_B_CIVIL_MATERIAL_TERMS`, `FORWARD_TRACK_B_GENERIC_AI_MARKETING_TERMS` | YES | forward technology Track A/B and noise controls |
| SRC-011 | SELECTION_ONLY | `RESCUE_LOW_VALUE_TERMS`, `FORWARD_WATCHLIST_*`, `REPORT_SELECTION_DEBUG_DEFAULT`, `OPERATOR_DOMAIN_KEYS`, `OPERATOR_TEXT_KEYS`, `EVENT_LOCATION_TERMS`, `PROJECT_SERIES_TERMS`, `PROJECT_STAGE_GROUPS` | YES | bounded rescue/watchlist, selection diagnostics, diversity metadata |
| SRC-012 | CATEGORY_GATE_EVIDENCE | `STRICT_HIGH_VALUE_POLICY_TEXT_TERMS`, `MAJOR_ACCIDENT_SEVERITY_TERMS`, `MAJOR_ACCIDENT_DIRECT_TERMS`, `POST_INCIDENT_POLICY_TERMS`, `SINGLE_PERSON_INCIDENT_TERMS`, `OFFICIAL_TRANSPORT_SAFETY_INVESTIGATION_TERMS` | YES | policy/accident severity and official-investigation exceptions |
| SRC-013 | CATEGORY_GATE_EVIDENCE | `SHORT_TERM_SERVICE_NOTICE_TERMS`, `SHORT_TERM_TIME_SIGNALS`, `LOW_VALUE_CEREMONIAL_TERMS`, `FORMAL_ENGINEERING_EVENT_TERMS`, `LOW_IMPACT_ROAD_INTERFACE_TERMS`, `ROAD_INTERFACE_ACCIDENT_TERMS` | YES | service-notice, ceremonial and road-interface guards |
| SRC-014 | CATEGORY_GATE_EVIDENCE | `DISPUTE_SIGNAL_TERMS`, `DISPUTE_ACTOR_TERMS`, `DISPUTE_IMPACT_TERMS`, `DISPUTE_SECONDARY_IMPACT_TERMS`, `DISPUTE_SECONDARY_SIGNAL_TERMS`, `POLICY_DOMINANT_TERMS`, `HIGH_VALUE_POLICY_GATE_TERMS` | YES | dispute/policy gate evidence |
| SRC-015 | NORMALIZATION | `CANONICAL_TAG_PATTERNS`, `EVENT_LOCATION_TERMS`, `PROJECT_SERIES_TERMS`, `PROJECT_STAGE_GROUPS` | YES | canonical tags, event/project metadata; not final geography owner |
| SRC-016 | DISPLAY_ONLY | `report_prompt_service.py` source/category maps; `report_postprocessor.py` `INTERNAL_REPORT_REPLACEMENTS`, `REPORT_FIELD_ALIASES`, `FORMAL_REPORT_CATEGORY_MAP` | YES | prompt, section, field and label compatibility |

## 4. Geography and normalization inventory

| Rule ID | Classification | Owner file / function / constant | Active | Positive / negative terms | Regex / pattern | Language / query / domain | Precedence | Output field | Consumers | Fallback | Duplicate owner | Collision / coverage gap | Notes |
|---|---|---|---|---|---|---|---:|---|---|---|---|---|---|
| GEO-001 | GEOGRAPHY_EVIDENCE | `config.py`: `EVENT_REGION_PRIORITY_HINTS` | YES | Taipei/New Taipei/Taoyuan/Taichung/Kaohsiung; Sydney, Basel, Zürich, Lausanne, Austin, Houston, Vancouver, Toronto, Berlin, Leipzig, Munich | normalized term spans | multilingual article text | 10 | event-location evidence | `article_processor._region_resolution_details` | NO | NO | City/system collision guarded by owner | Sydney and München fixes are general rules, not special selector cases. |
| GEO-002 | GEOGRAPHY_EVIDENCE | `config.py`: `METRO_SYSTEM_OWNERSHIP_RULES` | YES | location aliases + operator aliases + system terms | rule tuple matching | Sydney, München, Vienna, Manchester, Chennai | 20 | metro-system evidence | article processor | NO | NO | Manufacturer/test location cannot override event/system | System evidence requires context. |
| GEO-003 | GEOGRAPHY_EVIDENCE | `config.py`: `GEOGRAPHY_EVIDENCE_PRECEDENCE`; `article_processor.py`: `_region_resolution_details` | YES | event > metro system > operator > project > article subject > manufacturer > vendor > publisher > source domain > query > language > unresolved | ordered numeric precedence | all providers | 10→90 | `resolved_region`, `region_evidence` | workflow, selector, diagnostics | unresolved only | NO | Query/language hints are lowest confidence | This is the frozen precedence contract. |
| GEO-004 | GEOGRAPHY_EVIDENCE | `article_processor.py`: `_REGION_ALIASES`, `_TAIWAN_SUBREGIONS`, `_manufacturer_location_evidence`, `_metro_system_ownership_evidence` | YES | country/city aliases; manufacturer/test-center context | alias and context regex | multilingual | as GEO-003 | region evidence records | candidate materialization | NO | NO | Test/manufacturer location is explicitly lower than event/system | Selector is not geography owner. |
| GEO-005 | NORMALIZATION | `article_processor.py`: `normalize_country`, source/domain normalizers | YES | Taiwan/臺灣 and country spelling variants; source label noise | casefold/alias maps | all providers | before evidence resolution | normalized country/domain/source | every candidate consumer | NO | NO | Generic source labels remain display-only | No new aliases introduced by freeze. |
| GEO-006 | SEARCH_QUERY | `config.py`: `REGION_SEARCH_TERMS`; temporal router region prefix | YES | region-specific metro/operator anchors | query prefix composition | regional DDGS/Google News routes | query-time only | query string | temporal router, DDGS | NO | NO | Query region cannot override article event | Temporal router imports this map; it does not copy it. |
| GEO-007 | SEARCH_EXCLUSION | `article_processor.py`: domestic scope helpers and config domestic term maps | YES | Taiwan domestic metro anchors | scope checks | domestic/both | after event evidence | domestic candidate boolean/reason | workflow, procurement Gate | NO | NO | High-speed rail, bus and non-metro domestic material excluded | Scope behavior is unchanged. |

Frozen precedence statement: **Event > Metro system > Operator > Project > Article
subject > Manufacturer > Vendor > Publisher > Source domain > Query > Language >
Unresolved.** `selector` and `postprocessor` are consumers only.

## 5. Electromechanical (E&M) inventory

Official owner is `electromechanical_taxonomy.py`. Active canonical systems are:
`電聯車`, `號誌`, `供電`, `通訊`, `自動收費`, `機廠維修設備`, `月臺門`.
`CORE_SYSTEM_TERM_GROUPS` contains the complete technical-function evidence;
`CORE_TO_REPORT_LABEL` and `CORE_TO_PROCUREMENT_GROUP` are output mappings.

| Rule ID | Classification | Owner file / function / constant | Active | Positive / negative terms | Regex / pattern | Language / query / domain | Precedence | Output field | Consumers | Fallback | Duplicate owner | Collision / coverage gap | Notes |
|---|---|---|---|---|---|---|---:|---|---|---|---|---|---|
| EM-001 | EM_FORMAL_EVIDENCE | `electromechanical_taxonomy.py`: `CORE_SYSTEM_LABELS`, `CORE_SYSTEM_TERM_GROUPS` | YES | technical function terms for the seven systems | positive term hits with negation handling | multilingual candidate title/snippet/prefetch | 1 | `core_systems`, winning evidence | procurement Gate, selector, report | NO | NO | Generic terms require context | Single formal taxonomy owner. |
| EM-002 | EM_FORMAL_EVIDENCE | taxonomy contextual signalling/depot helpers | YES | rail + automatic operation; commissioned maintenance facility | bounded contextual checks | multilingual | 2 | added system evidence | taxonomy only | NO | NO | Depot location alone is rejected | A3 semantics are owned here. |
| EM-003 | EM_FORMAL_EVIDENCE | taxonomy `_ROLLING_STOCK_*`, `_DEPOT_FACILITY_TERMS`, `_GENERIC_PACKAGE_TERMS` | YES | vehicle event + specific equipment; depot facility; generic E&M package | bounded proximity regex | multilingual | 3 | contextual vehicle/depot classification | taxonomy | NO | NO | Train ≠ rolling stock unless context; generic package does not imply vehicle | Compatibility semantics remain in owner. |
| EM-004 | EM_FORMAL_EVIDENCE | taxonomy `DEPOT_LOCATION_TERMS`, `GENERIC_NETWORK_TERMS` | YES | maintenance depot/workshop; thermal/district/heat/network | positive hit then reject when location/network only | multilingual | 4 | rejected evidence reason | diagnostics, procurement Gate | NO | NO | Depot location ≠ equipment; generic network ≠ communications | Required collision guards are active. |
| EM-005 | CATEGORY_GATE_EVIDENCE | `article_selector.py`: procurement system/action groups and `_compute_electromechanical_procurement_gate` | YES | contract/tender/award/signing/amendment; E&M system groups | title+snippet evidence; source/date/page checks | procurement family, en/zh | after EM-001 | procurement gate payload | category resolver, selector | NO | NO formal duplicate | Selector gate consumes taxonomy and adds procurement action/evidence only | Selector-local taxonomy augmentation is not authoritative. |
| EM-006 | COMPATIBILITY_ALIAS | `article_selector.py`: `_core_systems_for_candidate` direct-call compatibility path | YES, compatibility only | pre-materialized `core_systems` | field accessor, no new inference for authoritative path | legacy/direct callers | after authoritative materialization | compatible `core_systems` | tests/legacy callers | NO | NO | Could be mistaken for duplicate owner if used outside workflow | Keep until compatibility contract is retired. |

## 6. Category and Gate inventory

`article_selector.evaluate_category_gates` is the sole executable Gate-evidence
aggregator. `category_conflict_resolver.resolve_primary_category` is the sole
primary-category conflict resolver. Gate thresholds are frozen; this inventory
does not weaken them.

| Rule ID | Classification | Owner file / function / constant | Active | Positive / negative terms | Regex / pattern | Language / query / domain | Precedence | Output field | Consumers | Fallback | Duplicate owner | Collision / coverage gap | Notes |
|---|---|---|---|---|---|---|---:|---|---|---|---|---|---|
| CAT-001 | CATEGORY_GATE_EVIDENCE | `article_selector.py`: `_compute_passes_technical_triad`, technical term groups | YES | urban rail + technical system + technical action; rejects finance/security/airport/accessibility/non-core/project-only/non-technical | triad booleans plus term membership | all search families | 1 | `technology`, failure reasons | category resolver, selector | bounded research/forward alternate gates | GUARDED | Globally low recall observed in A6.1; no threshold change in freeze | Research/pilot/deployment path requires object and validated outcome. |
| CAT-002 | CATEGORY_GATE_EVIDENCE | `article_selector.py`: `_compute_electromechanical_procurement_gate` | YES | urban rail, E&M system/package, procurement action, valid date/source/page | action regex and context checks | procurement family and selected category | 2 | procurement signals/reasons/systems/actions | category resolver, report | no relaxed annual path | NO | Short snippets may cause evidence insufficiency | Contract/award/tender remain distinct in event identity. |
| CAT-003 | CATEGORY_GATE_EVIDENCE | `article_selector.py`: `_compute_passes_major_accident_gate` | YES | accident/failure + urban rail + severity/safety consequence; excludes academic/non-event, minor road interface, single-person without exception | fragment-level evidence and severity terms | accident family | 3 | accident signals/reasons | category resolver, selector | official investigation/equipment-failure exceptions | NO | Severity wording can be absent in snippets | No special accident keyword added. |
| CAT-004 | CATEGORY_GATE_EVIDENCE | `article_selector.py`: dispute gates | YES | dispute signal + actor + operational impact + urban rail/metadata | signal membership | dispute family | 4 | dispute signals/reasons | category resolver | secondary metadata gate | NO | Search precision and evidence availability remain separate | Does not classify a mere dispute word as report-worthy. |
| CAT-005 | CATEGORY_GATE_EVIDENCE | `article_selector.py`: policy gates, technical-operation incident, major service adjustment | YES | high-value policy/action/detail, service impact, system failure, major adjustment; rejects short notice/low value | signal combination | policy family and operational notices | 5 | policy signals/reasons/subtype | category resolver, prompt | no annual relaxation | NO | Policy response can override post-incident accident category | Contract is unchanged. |
| CAT-006 | CATEGORY_GATE_EVIDENCE | `article_selector.py`: `_compute_service_opening_gate` | YES | actual passenger/revenue/commercial service; rejects future/planning/testing-only | actual/future/planning/testing term groups | service-opening family | 6 | opening gate and failure reasons | category resolver, prompt | NO | NO | Formal opening vs future opening is explicitly separated | Event date is not publication coverage. |
| CAT-007 | CATEGORY_GATE_EVIDENCE | `article_selector.py`: `_compute_forward_technology_gate`, Track A/B | YES | application object + novelty + validation + benefit; Track B emerging/application/rail object | bounded term groups | forward family | 7 | forward gate signals/reasons | forward radar, selector | bounded discovery lane only | GUARDED | Past raw→0 pass requires audit, not a relaxed Gate | No annual-specific forward bonus. |
| CAT-008 | CATEGORY_GATE_EVIDENCE | `article_selector.py`: `_compute_research_innovation_gate` | YES | research/prototype/pilot/trial/demonstration + technical object + result status; not procurement | term membership | technology/research | 8 | research innovation payload | category resolver | NO | NO | Snippet may omit results | It is an alternate route to technology, not a threshold change. |
| CAT-009 | CATEGORY_CONFLICT_RULE | `category_conflict_resolver.py`: `resolve_primary_category` | YES | claim evidence from all gates | fixed dominance values | all categories | 600 accident; 500 procurement; 400 opening; 350 dispute; 300 policy; 200 technology | `primary_category`, rejected conflicts | workflow, prompt, postprocessor | NO | NO | Same candidate can have multiple gates; winner is event action/object/status | Post-incident policy response is explicit reclassification reason. |
| CAT-010 | CATEGORY_GATE_EVIDENCE | `article_selector.py`: `LOW_VALUE_*`, source/page/metadata and technical failure reason helpers | YES | travel/SEO, portal, financial, ceremonial, bus/road/airport, project-only | host/path/term checks | all providers | before Gate | `preliminary_reject_reason`, `technical_gate_failure_reasons` | workflow diagnostics | bounded rescue candidates only | GUARDED | Rescue is not a Gate bypass | No new fallback. |

### Frozen category conflict precedence

`major_accident (600) > electromechanical_procurement (500) > service_opening
(400) > operational_dispute (350) > operational_policy (300) > technology (200)`.
The resolver returns `excluded` when no supported claim exists. This is a
`CATEGORY_CONFLICT_RULE`, not a new selector threshold.

## 7. Event identity and dedupe inventory

Official owner: `event_identity.py`, contract `a5-v1`. Identity components are
country, city, operator, project/line, package, contract, action, event object,
incident type, vendor, stations, event date/kind and injury count. URL identity
uses normalized host/path/query with tracking keys removed.

| Rule ID | Classification | Owner file / function / constant | Active | Positive / negative terms | Regex / pattern | Language / query / domain | Precedence | Output field | Consumers | Fallback | Duplicate owner | Collision / coverage gap | Notes |
|---|---|---|---|---|---|---|---:|---|---|---|---|---|---|
| EVT-001 | EVENT_IDENTITY_EVIDENCE | `event_identity.py`: alias maps and `build_event_identity` | YES | country/city/operator/line/package/contract/vendor/station/incident/object terms | bounded alias and contract/vendor/station regex | multilingual candidate fields; URL | 1 | `event_identity_components`, `canonical_event_id` | workflow, selector, postprocessor | legacy fingerprint accessor | NO | Sydney/Taoyuan/Brown Line aliases are general identity components | No publisher/query location in identity. |
| EVT-002 | EVENT_IDENTITY_EVIDENCE | `event_identity.py`: `_procurement_action`, `_date_value`, `_event_class` | YES | amendment/award/tender/signing/procurement; incident/opening/upgrade/testing | action terms and ISO date extraction | multilingual | 2 | event class/action/date kind | compare/dedupe | NO | NO | Tender vs award and same vendor/different contract remain distinct | Publication date is not event date. |
| EVT-003 | EVENT_IDENTITY_EVIDENCE | `event_identity.py`: `compare_event_candidates` | YES | conflicting country/city/project/package/contract/vendor/action/incident/station | fixed windows and conflict list | all candidates | 3 | same_event, conflicts, date distance/window | article processor, selector | URL match only when structured fields do not conflict | NO | Procurement award window 21 days; otherwise 3 days, non-publication event dates cap at 3 | URL reconciliation cannot collapse contradictory events. |
| EVT-004 | COMPATIBILITY_ALIAS | `event_identity.py`: `canonical_event_id` legacy fingerprint accessor; selector `_compare_report_event` | YES, compatibility/consumer | explicit upstream ID/components/fingerprint | field accessor | legacy selected records | after upstream ID | canonical ID for old records | selector/postprocessor | NO | NO | Selector does not infer a second fuzzy owner | Keep compatibility. |

## 8. Temporal inventory

Official owner: `temporal_retrieval_service.py`. Modes are
`CONTINUOUS_RECENT` for lookbacks below 365 days and `BUCKETED_ABSOLUTE` for
annual/365-day runs. Annual buckets are dynamic contiguous calendar quarters.

| Rule ID | Classification | Owner file / function / constant | Active | Positive / negative terms | Regex / pattern | Language / query / domain | Precedence | Output field | Consumers | Fallback | Duplicate owner | Collision / coverage gap | Notes |
|---|---|---|---|---|---|---|---:|---|---|---|---|---|---|
| TMP-001 | TEMPORAL_ROUTING | `temporal_retrieval_service.py`: request mode and `build_calendar_quarter_buckets` | YES | — | half-open `[start, end)` dates | all query families; Google News RSS annual | 1 | plan, bucket label/start/end | workflow, diagnostics | no annual fallback mode | NO | Provider availability can still block routes | Query keywords come from `search_queries.py`. |
| TMP-002 | TEMPORAL_ROUTING | `TemporalRetrievalRouter.build_plan` and `build_temporal_query_specs` | YES | region prefix + canonical family template + after/before | query composition | Google News RSS; family language metadata | 2 | route metadata, requested bucket | RSS workflow | bounded provider error/no-result status | NO | No duplicated temporal keyword source | One legal `QuerySpec` is shared by DDGS and temporal routes. |
| TMP-003 | TEMPORAL_VALIDATION | `normalize_publication_date`, `verify_publication_window`, `verify_route_metadata` | YES | publication date only | ISO/RFC date parsing | RSS/DDGS metadata | 3 | `verified_bucket`, `date_source`, status | workflow, debug | missing-date status | NO | Event date cannot earn publication coverage | Requested old quarter with recent publication is `out_of_window`. |
| TMP-004 | TEMPORAL_VALIDATION | `PROVIDER_CAPABILITIES` | YES | DDGS discovery support; Google News primary bucketed; Direct RSS continuous discovery | capability map | provider-specific | 4 | coverage credit and annual role | workflow diagnostics | NO | NO | DDGS has no annual coverage credit; Direct RSS has no historical completeness guarantee | Exact A6 contract. |
| TMP-005 | TEMPORAL_VALIDATION | `report_workflow_service.py`: `_temporal_verify_result`, stage recording | YES | verified route result | route metadata lookup | annual workflow | 5 | RAW/retrieved/verified/missing/out-of-window/dedup/gate/selector/selected stages | developer debug, annual report | provider_error/no_results | NO | Stage matrix can show provider external failure | No date→quarter fallback in selector. |
| TMP-006 | TEMPORAL_VALIDATION | A6.1 provider finding | EXTERNAL BLOCKER | — | Google News RSS 503 observed in prior bounded probe | historical + recent RSS routes | — | provider status | LUNA audit | DDGS not creditable | NO | `PROVIDER_RECOVERED` depends on external availability | No code change or fallback allowed. |

## 9. Selection, ranking, diversity and boundary inventory

| Rule ID | Classification | Owner file / function / constant | Active | Positive / negative terms | Regex / pattern | Language / query / domain | Precedence | Output field | Consumers | Fallback | Duplicate owner | Collision / coverage gap | Notes |
|---|---|---|---|---|---|---|---:|---|---|---|---|---|---|
| SEL-001 | SELECTION_ONLY | `article_selector.py`: `score_news_candidate`, source quality/tier and date/URL/urban rail/technical signals | YES | official/professional/source/date/URL/urban rail/E&M/technical action; low value penalties | score key composition | all candidates | 1 | `python_score`, score reasons | selector | bounded ranking only | NO | Score cannot turn excluded candidate into Gate pass | A7 keeps selector downstream of materialization. |
| SEL-002 | SELECTION_ONLY | `article_selector.py`: `select_candidates_by_python`, `_python_selection_dynamic_key` | YES | category cap, source diversity, month/theme/operator diversity | deterministic sort/group keys | report period 7–365 days | 2 | selected list, selection diagnostics | workflow | bounded borderline backfill | NO | No selector Gate bypass | Selection-only constraints are not eligibility rules. |
| SEL-003 | SELECTION_ONLY | `article_selector.py`: event consolidation and duplicate consumers | YES | canonical event ID and `compare_event_candidates` result | structured comparison | all providers | 3 | duplicate type/reason/source merge | workflow, report | source merge only | NO | Identity owner remains `event_identity.py` | Selector cannot invent a second fuzzy identity. |
| SEL-004 | COMPATIBILITY_ALIAS | `selector_contract.py`: `validate_selector_candidate`, `validate_selector_entries` | YES | required authoritative fields: category, event identity, temporal mode/bucket | field validation | workflow boundary | before selection | contract validity | report workflow | NO | NO | Rejects missing ownership fields rather than inferring them | A7 boundary contract. |
| SEL-005 | SELECTION_ONLY | `forward_radar_service.py`: radar ranking/coverage output | YES | forward discovery signal, source tier, application/technical evidence | deterministic sort key | forward technology | 4 | radar result/status | radar workflow | bounded discovery fallback | NO | Forward radar does not alter category thresholds | A6.1 audit remains separate. |

## 10. Prompt, rendering and compatibility inventory

| Rule ID | Classification | Owner file / function / constant | Active | Positive / negative terms | Regex / pattern | Language / query / domain | Precedence | Output field | Consumers | Fallback | Duplicate owner | Collision / coverage gap | Notes |
|---|---|---|---|---|---|---|---:|---|---|---|---|---|---|
| DISP-001 | DISPLAY_ONLY | `report_prompt_service.py`: formal labels, section headings, `format_selection_candidate` | YES | category labels, source display, formal fields | label maps/accessors | zh report prompt | 1 | prompt text | MaiAgent selection/report | bounded parser fallback | NO | Generic source labels are display-only | Does not infer Gate or geography. |
| DISP-002 | DISPLAY_ONLY | `report_postprocessor.py`: category/title/section normalization | YES | `營運議題`/`營運政策`/`營運爭議`→`營運動態`; procurement and service labels | bounded section regex | final Markdown | 2 | final report sections/title/footer | PDF/email/UI | no candidate selection | NO | Compatibility aliases are intentional | No production rule duplication. |
| DISP-003 | DISPLAY_ONLY | `report_formatter.py`: Markdown→HTML | YES | formatting markers/URLs | Markdown parser | report output | 3 | HTML | Streamlit/PDF/email | NO | NO | Pure presentation | Does not change content eligibility. |
| DISP-004 | COMPATIBILITY_ALIAS | `report_postprocessor.py`: `FORMAL_REPORT_CATEGORY_MAP`, `REPORT_FIELD_ALIASES`, canonical category accessors | YES, compatibility | legacy internal/display labels | map/field accessor | selected legacy records | 4 | canonical display category/fields | postprocessor | NO | NO | Keep until old reports/contracts are retired | Not a second Gate owner. |

## 11. Exclusion and collision matrix

| Subject | Search/query treatment | Gate treatment | Source/page treatment | Collision label | Frozen interpretation |
|---|---|---|---|---|---|
| Bus/coach/road/highway | explicit negative terms in `TRANSIT_NEWS_TERMS` and regional RSS | non-urban/bus/road rejection unless a clear urban-rail event remains | route/schedule pages low information | SAFE | Search precision first; Gate confirms context. |
| JR/Shinkansen/high-speed/intercity/regional rail | explicit Japanese and global negatives | `GENERAL_RAIL_EXCLUDE_TERMS`/non-urban terms | source tier unchanged | GUARDED | JR is explicitly excluded in Japanese route templates; no standalone global JR owner. |
| Aviation/tourism/SEO | airport/aviation and tourism/SEO negatives | airport people mover only, travel/SEO/low-value rejection | blocked/low-quality hosts and paths | SAFE | People mover is eligible only with clear urban-rail system context. |
| Depot | no blanket search exclusion | location-only depot evidence rejected; commissioned facility can be technical subject | source unchanged | GUARDED | Depot location ≠ equipment. |
| Train | broad search anchor | taxonomy contextual semantics required for rolling stock | source unchanged | GUARDED | Train alone does not imply `電聯車`. |
| Generic network | broad search anchor | generic network without communications context rejected | source unchanged | SAFE | Prevents thermal/district energy network collision with 通訊. |
| Modernization/testing | positive query/Gate action terms | technical object/action or opening contract determines category | source unchanged | GUARDED | Generic testing without technology is low value; formal testing evidence remains. |
| Manufacturer/test location | region/domain may appear in query/source | lower geography precedence | source tier independent | SAFE | Cannot override event/system geography. |
| Opening | service-opening queries use actual-service language | future/planning/testing-only rejected; actual passenger service passes | source/date required | SAFE | Formal通車 vs future opening is explicit. |
| Contract/award/tender | procurement queries include all actions | system + action + source/date required | page/source checks | GUARDED | Award/tender/signing are distinct identity actions. |
| Accident | accident queries broad but rail anchored | severity/safety consequence and context required | source/date required | GUARDED | Major incident can be reclassified to policy only for post-incident response. |
| AI/forward technology | broad bounded lanes | application object + novelty + validation + benefit or Track B | source tier/metadata | COLLISION_RISK | A6.1 audit target; no keyword-by-article fix. |

Required collision labels used above: `SAFE`, `GUARDED`, `COLLISION_RISK`,
`DUPLICATED_RULE`, `DEAD_RULE`. No active formal rule was found with
`DUPLICATED_RULE`; no rule is removed during freeze.

## 12. Dead and legacy audit

| Item | Status | Evidence / owner | Action in freeze |
|---|---|---|---|
| `article_selector.py` direct compatibility accessors | KEEP_COMPATIBILITY | A7 boundary comments and tests | Keep; do not migrate or delete. |
| `event_identity.py` legacy fingerprint fields | KEEP_COMPATIBILITY | `canonical_event_id` accessor | Keep; no second inference. |
| `report_postprocessor.py` legacy labels (`營運議題`, old research headings) | KEEP_COMPATIBILITY | normalization maps and tests | Keep; display-only. |
| `PROVIDER_DDGS` annual credit | ACTIVE contract | `PROVIDER_CAPABILITIES` | Keep false; no annual credit. |
| Old rescue names/diagnostic fields | UNKNOWN until a dedicated removal task | selector/debug compatibility payloads | Do not delete. |
| Unreferenced-looking constants found by static scan | UNKNOWN, not proven dead | AST/name scan only | No deletion in freeze. |

## 13. Duplicate-ownership audit

- Query templates: one owner (`search_queries.py`). `ddgs_search_service.py` and
  `temporal_retrieval_service.py` consume `QuerySpec`; temporal code only adds
  route dates and region prefix.
- Geography: one resolution owner (`article_processor.py`). Selector accessors
  and `GEOGRAPHY_EVIDENCE_PRECEDENCE` consumers do not resolve a competing
  final region.
- E&M: one formal taxonomy owner (`electromechanical_taxonomy.py`). Procurement
  Gate maps taxonomy systems to procurement groups but does not replace
  `core_systems`.
- Category: one Gate evidence aggregator (`article_selector.py`) and one
  conflict resolver (`category_conflict_resolver.py`); these are complementary,
  not duplicated formal outputs.
- Event identity: one identity/dedupe owner (`event_identity.py`); selector and
  postprocessor are consumers/compatibility accessors.
- Temporal: one plan/verification owner (`temporal_retrieval_service.py`);
  workflow records stage counters but does not verify dates independently.

No `DUPLICATED_OWNERSHIP` finding was promoted to a production change. Any future
equivalent rule discovered in two active owners must be recorded as a freeze
finding first, not fixed by adding another keyword.

## 14. Query / temporal reconciliation

1. `search_queries.py` is the canonical query-template owner.
2. `ddgs_search_service.py` selects active `QuerySpec` families and records
   provider status; it does not keep an annual keyword list.
3. `temporal_retrieval_service.py` calls `build_temporal_query_specs` and adds
   region prefix plus `after:`/`before:` bounds; it does not duplicate query
   terms.
4. Annual Google News RSS routes and DDGS use the same legal family/template
   vocabulary. Provider capability differs: only verified Google News RSS
   results can earn annual bucket credit.
5. Direct RSS remains continuous discovery and is not historical completeness
   authority.

## 15. Verification evidence

Read-only checks for this freeze:

- Repository baseline: HEAD and `origin/codex/fix-v22-report-quality` both
  `5681a9c`; branch is not `main`.
- Working tree preservation: existing `developer_debug_service.py` metadata
  modification and untracked cache/artifact directories are excluded from this
  artifact and are not staged.
- Static source inventory: AST/name and targeted source scan covered the owner
  modules listed in Sections 3–10.
- Import/AST consistency: owner modules parse and import without a new code
  change; `py_compile` is run as part of completion verification.
- Focused owner contracts: A2 geography, A3 E&M, A4 category, A5 event, A6
  temporal, A7 selector boundary, prompt/postprocessor and K5 critical guards
  are run or compared with the recorded A7 baseline.
- `git diff --check` is required and must report no whitespace error for this
  documentation-only change.
- No full 600+ suite rerun is required for a docs-only inventory. The recorded
  A7 full-suite baseline remains `621 passed, 8 failed`; the eight failures were
  pre-existing (six provider/assertion baseline failures and two Windows temp
  permission errors), with `NEW_REGRESSION = 0` after A7 reconciliation.

## 16. Findings carried forward (not changed by freeze)

| Finding | Classification | Severity for freeze | Disposition |
|---|---|---|---|
| Google News RSS historical/recent 503 provider availability blocker in A6.1 bounded probe | `EVIDENCE_AVAILABILITY_ISSUE` (audit classification) | Non-blocking external | Leave code unchanged; rerun provider recovery when available. |
| A6.1 Gate recall was globally low (0–60: 1/24; 61–365: 2/51) | `GATE_RECALL_ISSUE` (audit classification) | Non-blocking audit follow-up | No threshold, annual relaxation or keyword special case. |
| DDGS cannot earn annual bucket credit | `TEMPORAL_VALIDATION` contract | Intentional | Keep `annual_bucket_coverage_credit = False`. |
| Direct RSS has no guaranteed historical completeness | `TEMPORAL_VALIDATION` contract | Intentional | Keep as continuous discovery only. |
| Eight full-suite baseline failures | `DEAD_OR_UNREACHABLE` only for environment-specific cases; otherwise baseline | Non-blocking baseline | No rollback or unrelated fix. |

No P0/P1 architecture finding was introduced by the inventory. A6.1 provider and
Gate-recall work remain independent follow-ups; they do not authorize a Gate or
keyword change in this freeze.

## 17. Freeze decision

**Inventory completeness:** PASS
**Ownership clarity:** PASS
**Duplicate formal ownership:** NONE FOUND
**Contract changes made:** NONE
**Blocking architecture issue:** NONE
**Non-blocking findings recorded:** YES (external provider availability, low Gate
recall audit, known baseline failures)

## 18. Final result

`KEYWORD_RULE_FREEZE_RESULT`

`KEYWORD_RULE_FREEZE_PASS_WITH_FINDINGS`

This documentation-only freeze is locally complete. No production code, tests,
Gate, selector, temporal architecture, A1–A7 contract, fallback or untracked
artifact was modified. No push was performed. Pack A8 was not entered.
