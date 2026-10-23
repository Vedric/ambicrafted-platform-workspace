"""Refuse incomplete or mislabeled service proof at the full acceptance gate."""

import unittest

from qualifier import acceptance

COMMON = {
    "old_key_and_auth": True,
    "key_survives_restart": True,
    "logical_rollback_preserves_key_and_auth": True,
    "isolated_resources_removed": True,
}
FULL = {
    **COMMON,
    "migrated_key_auth_streaming_embeddings": True,
    "structured_output_schema": True,
    "real_otlp_delivery_parent_and_tracestate_boundary": True,
}


class AcceptanceGate(unittest.TestCase):
    def test_complete_contract_can_pass(self):
        self.assertEqual(
            acceptance(FULL, generation_requested=True, tempo_requested=True),
            {"profile_passed": True, "passed": True},
        )

    def test_limited_success_never_becomes_full_success(self):
        limited = {
            **COMMON,
            "migrated_key_auth_embeddings": True,
            "real_otlp_delivery_parent_and_tracestate_boundary": True,
        }
        self.assertEqual(
            acceptance(limited, generation_requested=False, tempo_requested=True),
            {"profile_passed": True, "passed": False},
        )
        self.assertFalse(
            acceptance(limited, generation_requested=True, tempo_requested=True)[
                "passed"
            ]
        )

    def test_missing_generation_schema_or_trace_cannot_be_replaced_by_check_count(self):
        for name in (
            "migrated_key_auth_streaming_embeddings",
            "structured_output_schema",
            "real_otlp_delivery_parent_and_tracestate_boundary",
        ):
            with self.subTest(missing=name):
                altered = dict(FULL)
                del altered[name]
                # The old count-only comparison could accept this replacement.
                altered["unrelated_check"] = True
                self.assertEqual(len(altered), len(FULL))
                self.assertFalse(
                    acceptance(
                        altered, generation_requested=True, tempo_requested=True
                    )["passed"]
                )

    def test_false_or_truthy_non_boolean_evidence_is_rejected(self):
        for value in (False, "true", 1, None):
            with self.subTest(value=value):
                altered = {
                    **FULL,
                    "real_otlp_delivery_parent_and_tracestate_boundary": value,
                }
                self.assertFalse(
                    acceptance(
                        altered, generation_requested=True, tempo_requested=True
                    )["passed"]
                )

    def test_recorded_error_overrides_success_flags(self):
        self.assertFalse(
            acceptance(
                FULL,
                generation_requested=True,
                tempo_requested=True,
                error_present=True,
            )["passed"]
        )


if __name__ == "__main__":
    unittest.main()
