"""Refuse incomplete or mislabeled service proof at the full acceptance gate."""

import base64
import unittest
from contextlib import closing
from unittest.mock import patch

import httpx
from qualifier import acceptance, check_trace_delivery

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


class TraceDelivery(unittest.TestCase):
    """Exercise the real polling/assertion code with only HTTP and sleep replaced."""

    @staticmethod
    def span(trace_id, parent_id, expected, **changes):
        return {
            "traceId": trace_id,
            "spanId": "1234567890abcdef",
            "parentSpanId": parent_id,
            "traceState": expected,
            "name": "Received Proxy Server Request",
            **changes,
        }

    @staticmethod
    def document(*spans, wrapper="batches"):
        return {wrapper: [{"scopeSpans": [{"spans": list(spans)}]}]}

    def invoke(self, response_for_poll):
        self.polls, self.requests = {}, []
        contexts = {}

        def embedding(request):
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.url.path, "/v1/embeddings")
            _, trace_id, parent_id, _ = request.headers["traceparent"].split("-")
            expected = "vendor=synthetic" if not self.requests else ""
            contexts[trace_id] = (parent_id, expected)
            self.requests.append(request)
            return httpx.Response(200, json={"data": [{"embedding": [0.25]}]})

        def trace(request):
            self.assertEqual(request.method, "GET")
            trace_id = request.url.path.rsplit("/", 1)[1]
            parent_id, expected = contexts[trace_id]
            poll = self.polls[trace_id] = self.polls.get(trace_id, 0) + 1
            return response_for_poll(trace_id, parent_id, expected, poll)

        with (
            httpx.Client(
                base_url="http://gateway.test", transport=httpx.MockTransport(embedding)
            ) as gateway,
            closing(
                httpx.Client(
                    base_url="http://tempo.test", transport=httpx.MockTransport(trace)
                )
            ) as tempo,
            patch("qualifier.httpx.Client", return_value=tempo),
            patch("qualifier.time.sleep") as sleep,
        ):
            self.sleep = sleep
            check_trace_delivery(gateway, "synthetic-fixture", 3200)

    def test_partial_children_are_followed_by_the_caller_parent_within_same_budget(
        self,
    ):
        def response(trace_id, parent_id, expected, poll):
            items = [
                self.span(trace_id, "abcdef1234567890", expected, name=name)
                for name in ("auth", "proxy_pre_call")
            ]
            items[1]["spanId"] = "fedcba0987654321"
            if poll == 2:
                items.append(
                    self.span(trace_id, parent_id, expected, spanId="abcdef1234567890")
                )
            return httpx.Response(200, json=self.document(*items))

        self.invoke(response)
        self.assertEqual(list(self.polls.values()), [2, 2])
        self.assertEqual(self.sleep.call_count, 2)
        self.assertEqual(len(self.requests[1].headers["tracestate"]), 8193)

    def test_missing_parent_exhausts_exactly_the_existing_sixty_polls(self):
        self.assert_failure(
            lambda trace_id, _parent, expected, _poll: self.document(
                self.span(trace_id, "abcdef1234567890", expected, name="auth")
            ),
            "caller's parent",
        )
        self.assertEqual(list(self.polls.values()), [60])
        self.assertEqual(self.sleep.call_count, 60)
        self.assertEqual(len(self.requests), 1)

    def test_missing_trace_exhausts_the_same_budget(self):
        with self.assertRaisesRegex(AssertionError, "did not reach"):
            self.invoke(lambda *_args: httpx.Response(404))
        self.assertEqual(list(self.polls.values()), [60])
        self.assertEqual(self.sleep.call_count, 60)

    def test_wrong_trace_is_rejected_before_a_later_valid_response(self):
        self.assert_failure(
            lambda trace_id, parent, expected, poll: self.document(
                self.span("f" * 32 if poll == 1 else trace_id, parent, expected)
            )
        )
        self.assertEqual(list(self.polls.values()), [1])
        self.sleep.assert_not_called()

    def test_wrong_root_state_is_not_retried_until_it_looks_correct(self):
        self.assert_failure(
            lambda trace_id, parent, expected, poll: self.document(
                self.span(trace_id, parent, "vendor=wrong" if poll == 1 else expected)
            )
        )
        self.assertEqual(list(self.polls.values()), [1])
        self.sleep.assert_not_called()

    def test_oversized_state_must_still_be_discarded(self):
        self.assert_failure(
            lambda trace_id, parent, expected, _poll: self.document(
                self.span(trace_id, parent, expected or "foo=1,bar=2")
            )
        )
        self.assertEqual(list(self.polls.values()), [1, 1])

    def test_link_to_another_trace_is_not_mistaken_for_a_span(self):
        def response(trace_id, parent, expected, _poll):
            root = self.span(
                trace_id,
                parent,
                expected,
                links=[{"traceId": "f" * 32, "spanId": "f" * 16}],
            )
            return httpx.Response(200, json=self.document(root))

        self.invoke(response)
        self.assertEqual(list(self.polls.values()), [1, 1])

    def test_link_to_the_external_parent_cannot_substitute_for_a_real_root(self):
        self.assert_failure(
            lambda trace_id, parent, expected, _poll: self.document(
                self.span(
                    trace_id,
                    "abcdef1234567890",
                    expected,
                    links=[{"traceId": trace_id, "spanId": parent}],
                )
            ),
            "caller's parent",
        )
        self.assertEqual(list(self.polls.values()), [60])

    def test_standard_otlp_wrapper_and_protobuf_base64_ids_are_supported(self):
        def response(trace_id, parent, expected, _poll):
            root = self.span(trace_id, parent, expected)
            for field in ("traceId", "spanId", "parentSpanId"):
                root[field] = base64.b64encode(bytes.fromhex(root[field])).decode()
            return httpx.Response(
                200, json=self.document(root, wrapper="resourceSpans")
            )

        self.invoke(response)
        self.assertEqual(list(self.polls.values()), [1, 1])

    def test_hex_identifier_case_does_not_change_its_value(self):
        def response(trace_id, parent, expected, _poll):
            root = self.span(trace_id, parent, expected)
            for field in ("traceId", "spanId", "parentSpanId"):
                root[field] = root[field].upper()
            return httpx.Response(200, json=self.document(root))

        self.invoke(response)
        self.assertEqual(list(self.polls.values()), [1, 1])

    def test_malformed_metadata_fails_without_polling_for_replacement(self):
        for changes in (
            {"traceId": None},
            {"traceId": "00" * 16},
            {"spanId": "1234"},
            {"parentSpanId": "not-an-identifier"},
            {"traceState": None},
        ):
            with self.subTest(changes=changes):
                self.assert_failure(
                    lambda trace_id, parent, expected, _poll, changes=changes: (
                        self.document(self.span(trace_id, parent, expected, **changes))
                    )
                )
                self.assertEqual(list(self.polls.values()), [1])
                self.sleep.assert_not_called()

    def test_malformed_otlp_collections_fail_without_becoming_missing_spans(self):
        for document in (
            [],
            {"batches": {}},
            {"batches": [None]},
            {"batches": [{"scopeSpans": {}}]},
            {"batches": [{"scopeSpans": [{"spans": {}}]}]},
            {"batches": [{"scopeSpans": [{"spans": [None]}]}]},
        ):
            with self.subTest(document=document):
                self.assert_failure(lambda *_args, document=document: document)
                self.assertEqual(list(self.polls.values()), [1])

    def assert_failure(self, document_for_poll, message=None):
        def response(*args):
            return httpx.Response(200, json=document_for_poll(*args))

        expected = (AssertionError, ValueError, KeyError)
        with self.assertRaises(expected) as failure:
            self.invoke(response)
        if message:
            self.assertIn(message, str(failure.exception))


if __name__ == "__main__":
    unittest.main()
