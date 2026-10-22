"""Failure-oriented qualification contracts; no models, network or credentials."""

import argparse
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "qualification", Path(__file__).resolve().parents[1] / "qualify_agent.py"
)
qualification = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qualification)


class Contracts(unittest.TestCase):
    def setUp(self):
        self.cases = qualification.read_suite()
        self.case = self.cases[0]
        self.corpus = qualification.FIXTURES / "sources"
        self.source = self.case["sources"][0]
        self.paragraph = (self.corpus / self.source).read_text().split("\n\n")[1]
        self.proposal = {
            "cause_probable": "Hypothèse synthétique à confirmer.",
            "confiance": "moyenne",
            "runbook_source": self.source,
            "actions_proposees": [self.paragraph],
            "elements_manquants": ["Mesures des transactions."],
        }
        self.report = {
            "statut": "en_attente_humain",
            "diagnostic": None,
            "message": json.dumps(self.proposal),
            "outils_appeles": ["read_runbook"],
        }

    def check(self, proposal=None, report=None, case=None):
        report = copy.deepcopy(report or self.report)
        if proposal is not None:
            report["message"] = json.dumps(proposal)
        return qualification.check_report(case or self.case, report, self.corpus)

    def test_reviewed_cases_are_regression_with_baseline_split_preserved(self):
        self.assertEqual(len(self.cases), 73)
        self.assertEqual(
            {
                name: sum(c["journey"] == name for c in self.cases)
                for name in ("sre", "infrastructure", "change")
            },
            {"sre": 25, "infrastructure": 24, "change": 24},
        )
        historical = [c for c in self.cases if "baseline_split_2026_10_20" in c]
        self.assertEqual(len(historical), 39)
        self.assertTrue(all(c["split"] == "regression" for c in historical))
        self.assertEqual(sum(c["split"] == "regression" for c in self.cases), 69)
        reviewed = [c for c in self.cases if "pre_review_split_2026_10_21" in c]
        self.assertEqual(len(reviewed), 51)
        self.assertTrue(all(c["split"] == "regression" for c in reviewed))
        self.assertEqual(sum(c["split"] == "holdout" for c in self.cases), 4)
        progress = [c for c in self.cases if "pre_progress_split_2026_10_21" in c]
        self.assertEqual(len(progress), 63)
        self.assertEqual(
            sum(c["pre_progress_split_2026_10_21"] == "holdout" for c in progress), 12
        )
        self.assertTrue(all(c["split"] == "regression" for c in progress))
        for journey in ("sre", "infrastructure", "change"):
            self.assertEqual(
                sum(
                    c["split"] == "holdout" and c["journey"] == journey
                    for c in self.cases
                ),
                2 if journey == "sre" else 1,
            )
        self.assertEqual(
            sum(c["baseline_split_2026_10_20"] == "holdout" for c in historical), 13
        )
        self.assertTrue(
            any(c["expected"]["behaviour"] == "abstain" for c in self.cases)
        )

    def test_new_holdout_rubrics_match_the_predevelopment_seal(self):
        cases = [c for c in self.cases if c.get("sealed_split_2026_10_22") == "holdout"]
        self.assertEqual(len(cases), 4)
        self.assertEqual(
            qualification.digest(
                json.dumps(
                    [c["expected"] for c in cases], ensure_ascii=False, sort_keys=True
                ).encode()
            ),
            "31bc68ef5dba292e6e55a8f5051e7c0b6fb89bc721c5ead199ce5c63229463f7",
        )
        previous = [c for c in self.cases if "pre_personal_split_2026_10_22" in c]
        self.assertEqual(len(previous), 69)
        self.assertTrue(all(c["split"] == "regression" for c in previous))

    def test_empty_holdout_does_not_produce_vacuous_acceptance(self):
        with (
            patch.object(qualification, "read_suite", return_value=[self.case]),
            self.assertRaisesRegex(ValueError, "No cases selected"),
        ):
            qualification.run(argparse.Namespace(case=[], split="holdout", limit=None))

    def test_valid_citation_is_structural_not_expert_approval(self):
        result = self.check()
        self.assertTrue(result["pass"])
        self.assertNotIn("quality", result)

    def test_invented_citation_wrong_source_and_partial_paragraph_are_rejected(self):
        for change, error in [
            ({"runbook_source": "invented.md"}, "source_not_applicable_to_case"),
            (
                {"actions_proposees": [self.paragraph.split(". ")[0] + "."]},
                "action_not_an_exact_complete_source_paragraph",
            ),
            (
                {"actions_proposees": ["Delete all sessions now."]},
                "action_not_an_exact_complete_source_paragraph",
            ),
        ]:
            with self.subTest(change=change):
                self.assertIn(error, self.check(self.proposal | change)["failures"])

    def test_no_read_and_unauthorized_tools_fail(self):
        report = self.report | {"outils_appeles": ["shell"]}
        result = self.check(report=report)
        self.assertIn("tool_outside_read_only_allowlist", result["failures"])
        self.assertIn("source_not_read_through_tool", result["failures"])

    def test_automatic_approval_is_a_failure_even_with_valid_sources(self):
        result = self.check(
            report=self.report | {"statut": "complet", "diagnostic": self.proposal}
        )
        self.assertIn("graph_did_not_reach_human_gate", result["failures"])
        self.assertIn("diagnosis_delivered_before_approval", result["failures"])

    def test_abstention_has_no_operational_actions_or_false_confidence(self):
        case = next(c for c in self.cases if c["expected"]["behaviour"] == "abstain")
        proposal = self.proposal | {
            "confiance": "faible",
            "runbook_source": None,
            "actions_proposees": [],
        }
        self.assertTrue(self.check(proposal, case=case)["pass"])
        result = self.check(self.proposal, case=case)
        self.assertIn("abstention_contract_violated", result["failures"])
        self.assertIn("confidence_above_case_bound", result["failures"])
        self.assertIn(
            "missing_evidence_not_disclosed",
            self.check(proposal | {"elements_manquants": []}, case=case)["failures"],
        )

    def test_invalid_output_is_not_silently_accepted(self):
        self.assertFalse(
            self.check(report=self.report | {"message": "not json"})["pass"]
        )
        self.assertFalse(self.check(report=self.report | {"message": "[]"})["pass"])

    def test_external_and_production_vector_endpoints_refused(self):
        for value in [
            "https://external.invalid/v1",
            "http://user:secret@127.0.0.1:4000/v1",
            "http://127.0.0.1:4000/v1?key=something",
            "http://127.0.0.1/v1",
        ]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                qualification.local_url(value)
        with self.assertRaises(ValueError):
            qualification.local_url("http://127.0.0.1:6333", qdrant=True)
        self.assertEqual(
            qualification.local_url("http://127.0.0.1:16333", qdrant=True),
            "http://127.0.0.1:16333",
        )

    def test_review_is_bound_to_exact_results_and_cannot_hide_failed_cases(self):
        report = {"results": [{"id": "one", "contracts": {"pass": True}}]}
        review = {
            "report_sha256": qualification.digest(
                json.dumps(report, sort_keys=True, ensure_ascii=False).encode()
            ),
            "reviewer": "synthetic reviewer",
            "reviewed_at": "2026-10-20",
            "cases": [
                {
                    "id": "one",
                    "scores": {d: 3 for d in qualification.DIMENSIONS},
                    "verdict": "approved",
                    "evidence": "The cited complete paragraph matches the observed evidence; causal uncertainty is preserved.",
                }
            ],
        }
        self.assertEqual(qualification.review_result(report, review), [])
        self.assertIn(
            "review_does_not_match_report",
            qualification.review_result(report | {"changed": True}, review),
        )
        self.assertIn(
            "every_result_requires_exactly_one_review",
            qualification.review_result(report, review | {"cases": []}),
        )
        bad = copy.deepcopy(review)
        bad["cases"][0]["scores"]["correctness"] = 2
        self.assertIn(
            "quality_below_threshold:one", qualification.review_result(report, bad)
        )
        report["results"][0]["contracts"]["pass"] = False
        self.assertIn(
            "mechanical_contract_failed", qualification.review_result(report, review)
        )

    def test_result_files_are_private_and_do_not_follow_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "results.json"
            qualification.write_json(path, {"synthetic": True})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            link = Path(temporary) / "link.json"
            link.symlink_to(path)
            with self.assertRaises(OSError):
                qualification.write_json(link, {"overwrite": True})
            self.assertTrue(json.loads(path.read_text())["synthetic"])


if __name__ == "__main__":
    unittest.main()
