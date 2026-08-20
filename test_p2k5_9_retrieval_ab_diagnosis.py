import unittest

from diagnostics.p2_k5_9_retrieval_ab_diagnosis import (
    QUERY_BUDGET,
    VARIANT_QUERIES,
    classify_and_measure,
    classify_result,
    choose_recommendation,
    flatten_query_matrix,
    normalize_url,
    validate_no_benchmark_leakage,
    validate_query_budget,
)


class P2K59RetrievalDiagnosisTests(unittest.TestCase):
    def test_generic_matrix_has_five_variants_and_fifteen_queries(self):
        query_rows = flatten_query_matrix()
        self.assertEqual(len(VARIANT_QUERIES), 5)
        self.assertEqual(len(query_rows), 15)
        validate_query_budget(query_rows)

    def test_benchmark_leakage_guard_rejects_specific_combo(self):
        self.assertTrue(validate_no_benchmark_leakage(flatten_query_matrix())["passed"])
        result = validate_no_benchmark_leakage([{"query": "hydrogen superconducting battery"}])
        self.assertFalse(result["passed"])
        self.assertEqual(result["violation_count"], 1)

    def test_classification_distinguishes_forward_rail_and_contamination(self):
        forward = classify_result({
            "title": "Metro pilots advanced composite materials for lighter vehicles",
            "summary": "The urban rail operator tests new materials in service to reduce weight.",
        })
        bus = classify_result({
            "title": "EV bus battery pilot expands",
            "summary": "The city bus fleet tests a new battery system on roads.",
        })
        metro_bus = classify_result({
            "title": "King County Metro to begin RapidRide bus service",
            "summary": "The bus route will connect to a light-rail station.",
        })
        mainline = classify_result({
            "title": "Freight rail locomotive energy storage trial",
            "summary": "A mainline freight operator tests traction batteries.",
        })
        generic = classify_result({
            "title": "New composite material research",
            "summary": "A laboratory evaluates a lightweight material.",
        })
        self.assertEqual(forward["classification"], "URBAN_RAIL_FORWARD_TECH")
        self.assertEqual(bus["classification"], "BUS_OR_ROAD")
        self.assertEqual(metro_bus["classification"], "BUS_OR_ROAD")
        self.assertEqual(mainline["classification"], "MAINLINE_RAIL")
        self.assertEqual(generic["classification"], "GENERIC_TECH")

    def test_duplicate_normalization_and_metrics(self):
        self.assertEqual(
            normalize_url("https://example.com/story/?utm_source=news#fragment"),
            "https://example.com/story",
        )
        query_rows = [{"variant": "A", "query": "metro technology", "raw_count": 3}]
        measured = classify_and_measure([
            {
                "title": "Metro pilots predictive maintenance",
                "summary": "Urban rail tests AI condition monitoring.",
                "link": "https://example.com/story?utm_medium=x",
            },
            {
                "title": "Metro pilots predictive maintenance",
                "summary": "Urban rail tests AI condition monitoring.",
                "link": "https://example.com/story",
            },
            {
                "title": "Metro orders trains",
                "summary": "The operator announces a procurement project.",
                "link": "https://example.com/other",
            },
        ], query_rows)
        self.assertEqual(measured["metrics"]["raw_result_count"], 3)
        self.assertEqual(measured["metrics"]["unique_result_count"], 2)
        self.assertEqual(measured["metrics"]["duplicate_rate"], 0.3333)

    def test_query_budget_rejects_more_than_twenty(self):
        with self.assertRaises(ValueError):
            validate_query_budget(
                [{"variant": "x", "query": f"metro technology {index}"} for index in range(QUERY_BUDGET + 1)]
            )

    def test_observed_complementary_lanes_recommend_multi_lane(self):
        metrics = {
            "A_baseline_generic": {"forward_precision": 0, "urban_rail_precision": 0, "sample_status": "SUFFICIENT_SAMPLE_SIZE", "unique_result_count": 19},
            "B_strong_urban_rail_anchor": {"forward_precision": 0, "urban_rail_precision": 0, "sample_status": "SUFFICIENT_SAMPLE_SIZE", "unique_result_count": 23},
            "C_quoted_phrase": {"forward_precision": 0, "urban_rail_precision": 0.2222, "sample_status": "LOW_SAMPLE_SIZE", "unique_result_count": 9},
            "D_dual_anchor": {"forward_precision": 0, "urban_rail_precision": 0.3684, "sample_status": "SUFFICIENT_SAMPLE_SIZE", "unique_result_count": 19},
            "E_source_strategy": {"forward_precision": 0.0435, "urban_rail_precision": 0.3043, "sample_status": "SUFFICIENT_SAMPLE_SIZE", "unique_result_count": 23},
        }
        payload = {variant: {"metrics": values} for variant, values in metrics.items()}
        self.assertEqual(choose_recommendation(payload)["code"], "RECOMMEND_MULTI_LANE_RETRIEVAL")


if __name__ == "__main__":
    unittest.main()
