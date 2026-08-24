"""Deterministic primary-category resolution from formal gate evidence."""

from config import (
    ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY,
    ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL,
    SERVICE_OPENING_CATEGORY_KEY,
)


_CATEGORY_LABELS = {
    "major_accident": "重大事故",
    ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY: ELECTROMECHANICAL_PROCUREMENT_CATEGORY_LABEL,
    SERVICE_OPENING_CATEGORY_KEY: "營運政策",
    "operational_dispute": "營運爭議",
    "operational_policy": "營運政策",
    "technology": "技術新知",
}


def _claim(
    gate: str,
    *,
    action: str,
    event_object: list[str],
    status: str,
    evidence: list[str],
    dominance: int,
) -> dict:
    return {
        "gate": gate,
        "category": _CATEGORY_LABELS[gate],
        "event_action": action,
        "event_object": list(dict.fromkeys(event_object)),
        "event_status": status,
        "evidence": list(dict.fromkeys(evidence)),
        "dominance": dominance,
    }


def resolve_primary_category(
    *,
    gates: dict,
    procurement_actions: list[str],
    procurement_systems: list[str],
    service_opening_signals: list[str],
    major_accident_signals: list[str],
    policy_signals: list[str],
    dispute_signals: list[str],
    technology_signals: list[str],
) -> dict:
    """Choose the event represented by the strongest action/object/status claim.

    Gate booleans remain independently observable.  They are converted into event
    claims here so a contract award is not displaced by incidental technology,
    policy, future-line, or dispute vocabulary.
    """
    claims: list[dict] = []
    if gates.get("major_accident"):
        claims.append(
            _claim(
                "major_accident",
                action="major_safety_event",
                event_object=["urban_rail_service"],
                status="occurred_with_severe_consequence",
                evidence=major_accident_signals,
                dominance=600,
            )
        )

    if (
        gates.get(ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY)
        and procurement_actions
        and procurement_systems
    ):
        claims.append(
            _claim(
                ELECTROMECHANICAL_PROCUREMENT_CATEGORY_KEY,
                action=procurement_actions[0],
                event_object=procurement_systems,
                status="formal_procurement_action",
                evidence=procurement_actions + procurement_systems,
                dominance=500,
            )
        )

    if gates.get(SERVICE_OPENING_CATEGORY_KEY) and "passenger_service_started" in service_opening_signals:
        claims.append(
            _claim(
                SERVICE_OPENING_CATEGORY_KEY,
                action="open_passenger_service",
                event_object=["urban_rail_line_or_extension"],
                status="revenue_service_started",
                evidence=service_opening_signals,
                dominance=400,
            )
        )

    if gates.get("operational_dispute"):
        claims.append(
            _claim(
                "operational_dispute",
                action="active_operational_dispute",
                event_object=["urban_rail_operation_or_governance"],
                status="dispute_with_operational_impact",
                evidence=dispute_signals,
                dominance=350,
            )
        )

    if gates.get("operational_policy"):
        claims.append(
            _claim(
                "operational_policy",
                action="policy_or_operational_change",
                event_object=["urban_rail_operation"],
                status="approved_or_in_effect",
                evidence=policy_signals,
                dominance=300,
            )
        )

    if gates.get("technology"):
        claims.append(
            _claim(
                "technology",
                action="research_pilot_or_technical_change",
                event_object=["urban_rail_technology"],
                status="supported_technical_change",
                evidence=technology_signals or ["technical_gate"],
                dominance=200,
            )
        )

    if not claims:
        return {
            "primary_category": "excluded",
            "category_resolution_method": "event_action_object_status",
            "category_winning_evidence": [],
            "category_rejected_conflicts": [],
            "category_conflict_reason": "no_supported_event_claim",
            "winning_gate": "",
        }

    winner = max(claims, key=lambda item: item["dominance"])
    rejected = [
        {
            "gate": item["gate"],
            "category": item["category"],
            "event_action": item["event_action"],
            "event_status": item["event_status"],
        }
        for item in claims
        if item is not winner and item["category"] != winner["category"]
    ]
    winning_evidence = {
        "gate": winner["gate"],
        "event_action": winner["event_action"],
        "event_object": winner["event_object"],
        "event_status": winner["event_status"],
        "signals": winner["evidence"],
    }
    conflict_reason = (
        f"{winner['event_action']}:{winner['event_status']}"
        if not rejected
        else f"{winner['event_action']}:{winner['event_status']}_dominates_"
        + ",".join(item["gate"] for item in rejected)
    )
    return {
        "primary_category": winner["category"],
        "category_resolution_method": "event_action_object_status",
        "category_winning_evidence": winning_evidence,
        "category_rejected_conflicts": rejected,
        "category_conflict_reason": conflict_reason,
        "winning_gate": winner["gate"],
    }
