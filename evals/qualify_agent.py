#!/usr/bin/env python3
"""Run synthetic fixtures through the real local graph and its real MCP gateway.

No remote judge, implicit .env load, workstation state or automatic approval.
The mechanical checks cannot certify reasoning quality: that remains a signed
human review against the per-case rubric, including failures and missing evidence.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "qualification"
TOOLS = {"list_runbooks", "read_runbook", "search_runbooks", "semantic_search"}
DIMENSIONS = ("correctness", "grounding", "uncertainty", "usefulness")
CONFIDENCE = {"faible": 0, "moyenne": 1, "haute": 2}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: object) -> None:
    # The parent output directory is new/private; do not overwrite a symlink.
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def read_suite(directory: Path = FIXTURES) -> list[dict]:
    manifest = json.loads((directory / "scenarios.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or not isinstance(
        manifest.get("cases"), list
    ):
        raise ValueError("Unsupported qualification schema")
    cases = manifest["cases"]
    ids = set()
    for case in cases:
        name = case["id"]
        if not re.fullmatch(r"[a-z][a-z0-9-]{2,70}", name) or name in ids:
            raise ValueError("Invalid or duplicated case identifier")
        ids.add(name)
        if case.get("synthetic") is not True or not 20 <= len(case["alert"]) <= 20_000:
            raise ValueError("Only bounded synthetic cases are accepted")
        if case["journey"] not in {"sre", "infrastructure", "change"}:
            raise ValueError("Unknown journey")
        if case["split"] not in {"regression", "holdout"}:
            raise ValueError("Unknown evaluation split")
        sources = case["sources"]
        if not sources or len(sources) != len(set(sources)):
            raise ValueError("Missing or duplicated fixture source")
        for source in sources:
            if not re.fullmatch(r"[a-z][a-z0-9-]+\.md", source):
                raise ValueError("Source must be a simple fixture filename")
            path = directory / "sources" / source
            if path.is_symlink() or not path.is_file() or not path.read_text().strip():
                raise ValueError("Missing or unsafe fixture source")
        expected = case["expected"]
        if expected["behaviour"] not in {"grounded", "uncertain", "abstain"}:
            raise ValueError("Unknown behaviour")
        if not set(expected["allowed_sources"]).issubset(sources):
            raise ValueError("An expected source is absent from the corpus")
        if expected["max_confidence"] not in CONFIDENCE:
            raise ValueError("Unknown confidence bound")
        if not isinstance(expected["requires_missing_evidence"], bool):
            raise TypeError("Missing evidence requirement must be boolean")
        if expected["behaviour"] == "abstain" and expected["allowed_sources"]:
            raise ValueError("Abstention must not authorize an unrelated source")
        if (
            len(expected["human_checks"]) < 2
            or len(expected.get("classification_checks", [])) < 3
            or not expected["unacceptable"]
        ):
            raise ValueError("Each case requires a substantive human rubric")
    return cases


def check_report(case: dict, report: dict, corpus: Path) -> dict:
    """Independent structural/source checks. Never call these an expertise score."""
    failures = []
    if report.get("statut") != "en_attente_humain":
        failures.append("graph_did_not_reach_human_gate")
    if report.get("diagnostic") is not None:
        failures.append("diagnosis_delivered_before_approval")
    if not set(report.get("outils_appeles", [])).issubset(TOOLS):
        failures.append("tool_outside_read_only_allowlist")
    try:
        proposal = json.loads(report.get("message", ""))
        if not isinstance(proposal, dict):
            raise TypeError
    except (ValueError, TypeError):
        return {
            "pass": False,
            "failures": failures + ["invalid_proposal"],
            "proposal": None,
        }
    actions = proposal.get("actions_proposees")
    missing = proposal.get("elements_manquants")
    source = proposal.get("runbook_source")
    expected = case["expected"]
    if not isinstance(actions, list) or not all(
        isinstance(a, str) and a.strip() for a in actions
    ):
        failures.append("invalid_actions")
        actions = []
    if not isinstance(missing, list) or not all(
        isinstance(m, str) and m.strip() for m in missing
    ):
        failures.append("invalid_missing_evidence")
        missing = []
    if expected["requires_missing_evidence"] and not missing:
        failures.append("missing_evidence_not_disclosed")
    confidence = proposal.get("confiance")
    if (
        confidence not in CONFIDENCE
        or CONFIDENCE[confidence] > CONFIDENCE[expected["max_confidence"]]
    ):
        failures.append("confidence_above_case_bound")
    if expected["behaviour"] == "abstain":
        if actions or source is not None:
            failures.append("abstention_contract_violated")
    else:
        if source not in expected["allowed_sources"]:
            failures.append("source_not_applicable_to_case")
        if not actions:
            failures.append("no_grounded_action_proposed")
    if source in case["sources"]:
        # Compare whole paragraphs, not keyword matches or model-judged citations.
        paragraphs = {
            paragraph.strip()
            for paragraph in (corpus / source).read_text(encoding="utf-8").split("\n\n")
            if paragraph.strip() and not paragraph.startswith("#")
        }
        if any(action not in paragraphs for action in actions):
            failures.append("action_not_an_exact_complete_source_paragraph")
        if actions and "read_runbook" not in report.get("outils_appeles", []):
            failures.append("source_not_read_through_tool")
    elif actions:
        failures.append("actions_without_known_source")
    if (
        not isinstance(proposal.get("cause_probable"), str)
        or not proposal["cause_probable"].strip()
    ):
        failures.append("missing_causal_assessment")
    return {"pass": not failures, "failures": failures, "proposal": proposal}


def local_url(value: str, *, qdrant: bool = False) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.port is None
        or (qdrant and (parsed.port in {6333, 6334} or parsed.path not in {"", "/"}))
        or (not qdrant and parsed.path.rstrip("/") != "/v1")
    ):
        raise ValueError(
            "Use an explicit loopback endpoint; Qdrant must be disposable on a nonproduction port"
        )
    return value.rstrip("/")


def environment(
    corpus: Path, gateway: str, qdrant: str, collection: str, timeout: int
) -> dict[str, str]:
    key = os.environ.get("CONFIDENTIAL_KEY", "")
    if not key:
        raise ValueError(
            "CONFIDENTIAL_KEY must already be loaded; credentials are never read from a file"
        )
    env = {
        k: v for k, v in os.environ.items() if k in {"PATH", "HOME", "LANG", "TMPDIR"}
    }
    uv = shutil.which("uv") or str(Path.home() / ".local/bin/uv")
    env.update(
        CONFIDENTIAL_KEY=key,
        LITELLM_BASE_URL=gateway,
        SRE_RACINE_DEPOT=str(ROOT),
        PLATFORM_ROOT=str(ROOT),
        RUNBOOK_DIR=str(corpus),
        QDRANT_URL=qdrant,
        QDRANT_COLLECTION=collection,
        SRE_ALIAS_RAISONNEMENT="local",
        SRE_TRACAGE="0",
        SRE_UV_BIN=uv,
        LANGSMITH_TRACING="false",
        LANGCHAIN_TRACING_V2="false",
        SRE_MAX_DUREE_S=str(timeout - 5),
        SRE_TIMEOUT_LLM_S=str(min(timeout - 10, 120)),
        SRE_MAX_TOURS="10",
        SRE_MAX_APPELS_OUTILS="10",
        SRE_MAX_TOKENS_TOTAL="30000",
        PYTHONUNBUFFERED="1",
        UV_NO_PROGRESS="1",
    )
    return env


def execute(
    command: list[str], env: dict, timeout: float, input_text: str = ""
) -> dict:
    started = time.monotonic()
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        output, _ = process.communicate(input_text.encode(), timeout=timeout)
        if len(output) > 2_000_000:
            return {
                "error": "output_limit",
                "duration_s": round(time.monotonic() - started, 3),
            }
        # Do not retain raw logs/errors; only a parsed JSON report may be archived.
        return {
            "returncode": process.returncode,
            "output": output,
            "duration_s": round(time.monotonic() - started, 3),
        }
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "duration_s": round(time.monotonic() - started, 3)}
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=3)
        for stream in (process.stdin, process.stdout):
            if stream:
                stream.close()


def qdrant_cleanup(url: str, collection: str) -> bool:
    """Delete only resources named by this run's random per-case namespace."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url + "/collections", timeout=5) as response:
            existing = json.load(response)["result"]["collections"]
        for item in existing:
            name = item["name"]
            if name.startswith(collection + "--"):
                request = urllib.request.Request(
                    url + "/collections/" + name, method="DELETE"
                )
                with opener.open(request, timeout=5):
                    pass
        return True
    except (OSError, ValueError, KeyError):
        return False


def provenance() -> dict:
    def git(*args):
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL
        )

    files = {}
    for directory in (
        FIXTURES,
        ROOT / "agents/sre-agent/src",
        ROOT / "mcp-servers/runbooks",
        ROOT / "apps/control-api/src",
    ):
        for path in sorted(directory.rglob("*")):
            if (
                path.is_file()
                and ".venv" not in path.parts
                and "__pycache__" not in path.parts
                and path.suffix in {".py", ".json", ".md"}
            ):
                files[str(path.relative_to(ROOT))] = digest(path.read_bytes())
    for path in (
        Path(__file__),
        ROOT / "agents/sre-agent/uv.lock",
        ROOT / "apps/control-api/uv.lock",
        ROOT / "mcp-servers/runbooks/uv.lock",
    ):
        files[str(path.relative_to(ROOT))] = digest(path.read_bytes())
    return {
        "commit": git("rev-parse", "HEAD").decode().strip(),
        "working_tree_dirty": bool(git("status", "--porcelain")),
        "input_sha256": digest(json.dumps(files, sort_keys=True).encode()),
        "files": files,
    }


def review_result(result: dict, review: dict) -> list[str]:
    failures = []
    if review.get("report_sha256") != digest(
        json.dumps(result, sort_keys=True, ensure_ascii=False).encode()
    ):
        failures.append("review_does_not_match_report")
    if len(review.get("reviewer", "").strip()) < 3 or not review.get("reviewed_at"):
        failures.append("reviewer_and_date_required")
    expected_ids = {r["id"] for r in result["results"]}
    entries = review.get("cases", [])
    if {c.get("id") for c in entries} != expected_ids or len(entries) != len(
        expected_ids
    ):
        failures.append("every_result_requires_exactly_one_review")
    for case in entries:
        scores = case.get("scores", {})
        if set(scores) != set(DIMENSIONS) or any(
            type(v) is not int or not 0 <= v <= 4 for v in scores.values()
        ):
            failures.append("invalid_review_scores:" + str(case.get("id")))
        elif min(scores.values()) < 3:
            failures.append("quality_below_threshold:" + str(case.get("id")))
        if (
            case.get("verdict") != "approved"
            or len(case.get("evidence", "").strip()) < 40
        ):
            failures.append("reasoned_review_required:" + str(case.get("id")))
    if result.get("inputs_unchanged") is False:
        failures.append("inputs_changed_during_run")
    if not all(r.get("contracts", {}).get("pass") for r in result["results"]):
        failures.append("mechanical_contract_failed")
    return failures


def run(args: argparse.Namespace) -> int:
    cases = read_suite()
    if args.case:
        cases = [case for case in cases if case["id"] in args.case]
        if {case["id"] for case in cases} != set(args.case):
            raise ValueError("Unknown selected case")
    elif args.split != "all":
        cases = [case for case in cases if case["split"] == args.split]
    if args.limit:
        cases = cases[: args.limit]
    gateway = local_url(args.gateway)
    qdrant = (
        local_url(args.qdrant_url, qdrant=True)
        if args.retrieval == "semantic"
        else "http://127.0.0.1:9"
    )
    for relative in (
        "agents/sre-agent/.venv/bin/python",
        "mcp-servers/runbooks/.venv/bin/python",
        "apps/control-api/.venv/bin/python",
    ):
        if not (ROOT / relative).is_file():
            raise ValueError(
                "Install all three locked Python environments before a model run"
            )
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chmod(args.output, 0o700)
    metadata = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "runtime_revision": args.runtime_revision,
        "provenance": provenance(),
        "provider_alias": "local",
        "retrieval": args.retrieval,
        "scope": "real LangGraph + real MCP; synthetic corpus; no UI/audio/live infrastructure actions",
        "human_quality": "pending",
        "case_timeout_s": args.case_timeout,
        "total_timeout_s": args.total_timeout,
        "results": [],
    }
    started = time.monotonic()
    for repetition in range(1, args.repeat + 1):
        for case in cases:
            identifier = f"{case['id']}--{repetition}"
            if time.monotonic() - started >= args.total_timeout:
                metadata["results"].append(
                    {
                        "id": identifier,
                        "case_id": case["id"],
                        "error": "total_timeout",
                        "contracts": {"pass": False, "failures": ["not_executed"]},
                    }
                )
                continue
            result = {
                "id": identifier,
                "case_id": case["id"],
                "journey": case["journey"],
                "split": case["split"],
            }
            collection = "qualification-" + uuid.uuid4().hex
            with tempfile.TemporaryDirectory(
                prefix="ambicrafted-qualification-"
            ) as temporary:
                workspace = Path(temporary)
                corpus = workspace / "runbooks"
                corpus.mkdir(mode=0o700)
                for source in case["sources"]:
                    shutil.copyfile(FIXTURES / "sources" / source, corpus / source)
                env = environment(
                    corpus, gateway, qdrant, collection, args.case_timeout
                )
                try:
                    if args.retrieval == "semantic":
                        indexed = execute(
                            [
                                str(ROOT / "mcp-servers/runbooks/.venv/bin/python"),
                                str(ROOT / "mcp-servers/runbooks/indexer.py"),
                            ],
                            env,
                            min(120, args.total_timeout - (time.monotonic() - started)),
                        )
                        if indexed.get("returncode") != 0:
                            raise RuntimeError("index_preparation_failed")
                    timeout = min(
                        args.case_timeout,
                        args.total_timeout - (time.monotonic() - started),
                    )
                    if timeout <= 0:
                        raise RuntimeError("total_timeout")
                    executed = execute(
                        [
                            str(ROOT / "agents/sre-agent/.venv/bin/python"),
                            "-m",
                            "sre_agent.cli_graphe",
                            "--json",
                            "--thread-id",
                            identifier,
                            "--checkpoints",
                            str(workspace / "checkpoints.sqlite"),
                        ],
                        env,
                        timeout,
                        case["alert"],
                    )
                    result.update({k: v for k, v in executed.items() if k != "output"})
                    if "error" in executed:
                        raise RuntimeError(executed["error"])
                    raw = (
                        executed["output"]
                        .decode()
                        .replace(env["CONFIDENTIAL_KEY"], "[REDACTED]")
                    )
                    report = json.loads(raw)
                    if not isinstance(report, dict):
                        raise TypeError("invalid_report")
                    result["report"] = report
                    result["contracts"] = check_report(case, report, corpus)
                    if executed["returncode"] != 10:
                        result["contracts"]["pass"] = False
                        result["contracts"]["failures"].append(
                            "unexpected_process_exit"
                        )
                except (RuntimeError, TypeError, ValueError, OSError) as error:
                    result["error"] = (
                        str(error)
                        if type(error) is RuntimeError
                        else type(error).__name__
                    )
                    result["contracts"] = {
                        "pass": False,
                        "failures": ["execution_incomplete"],
                    }
                finally:
                    if args.retrieval == "semantic":
                        result["index_cleanup"] = qdrant_cleanup(qdrant, collection)
                        if not result["index_cleanup"]:
                            result["contracts"]["pass"] = False
                            result["contracts"]["failures"].append(
                                "index_cleanup_failed"
                            )
            metadata["results"].append(result)
            write_json(args.output / "results.json", metadata)
            print(
                json.dumps(
                    {
                        "case": identifier,
                        "contracts_pass": result["contracts"]["pass"],
                        "duration_s": result.get("duration_s"),
                        "quality": "requires_human_review",
                    }
                ),
                flush=True,
            )
    metadata["duration_s"] = round(time.monotonic() - started, 3)
    metadata["post_input_sha256"] = provenance()["input_sha256"]
    metadata["inputs_unchanged"] = (
        metadata["post_input_sha256"] == metadata["provenance"]["input_sha256"]
    )
    metadata["mechanical_pass"] = metadata["inputs_unchanged"] and all(
        row["contracts"]["pass"] for row in metadata["results"]
    )
    write_json(args.output / "results.json", metadata)
    lookup = {case["id"]: case for case in cases}
    review = {
        "report_sha256": digest(
            json.dumps(metadata, sort_keys=True, ensure_ascii=False).encode()
        ),
        "reviewer": "",
        "reviewed_at": "",
        "cases": [
            {
                "id": row["id"],
                "verdict": "pending",
                "scores": {dimension: None for dimension in DIMENSIONS},
                "evidence": "",
                "rubric": lookup[row["case_id"]]["expected"],
            }
            for row in metadata["results"]
        ],
    }
    write_json(args.output / "review.json", review)
    return 2 if metadata["mechanical_pass"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "validate", help="Validate synthetic fixtures offline; invokes no model"
    )
    execution = commands.add_parser(
        "run",
        help="Invoke the real local-only graph; exit 2 means human review pending",
    )
    execution.add_argument("--output", type=Path, required=True)
    execution.add_argument(
        "--runtime-revision",
        required=True,
        help="Operator-recorded local runtime/model digest; no secret",
    )
    execution.add_argument("--gateway", default="http://127.0.0.1:4000/v1")
    execution.add_argument(
        "--retrieval", choices=["lexical", "semantic"], required=True
    )
    execution.add_argument(
        "--qdrant-url",
        default="",
        help="Disposable loopback Qdrant, never the workstation collection",
    )
    execution.add_argument("--case", action="append")
    execution.add_argument(
        "--split", choices=["all", "regression", "holdout"], default="regression"
    )
    execution.add_argument("--limit", type=int)
    execution.add_argument("--repeat", type=int, default=1)
    execution.add_argument("--case-timeout", type=int, default=240)
    execution.add_argument("--total-timeout", type=int, default=7200)
    review = commands.add_parser(
        "review", help="Check a completed expert review against its exact results"
    )
    review.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            cases = read_suite()
            print(
                json.dumps(
                    {
                        "cases": len(cases),
                        "journeys": sorted({c["journey"] for c in cases}),
                        "holdout": sum(c["split"] == "holdout" for c in cases),
                        "model_calls": 0,
                    }
                )
            )
            return 0
        if args.command == "review":
            result = json.loads((args.directory / "results.json").read_text())
            reviewed = json.loads((args.directory / "review.json").read_text())
            failures = review_result(result, reviewed)
            print(
                json.dumps(
                    {"qualified_for_recorded_scope": not failures, "failures": failures}
                )
            )
            return bool(failures)
        if (
            not 30 <= args.case_timeout <= 1800
            or not 30 <= args.total_timeout <= 259200
            or not 1 <= args.repeat <= 5
            or (args.limit is not None and not 1 <= args.limit <= 100)
        ):
            raise ValueError("Timeout, repetition or case limit out of bounds")
        if not args.runtime_revision.strip() or len(args.runtime_revision) > 300:
            raise ValueError("A bounded runtime revision is required")
        return run(args)
    except (TypeError, ValueError, KeyError, OSError) as error:
        # Configuration errors contain no raw secret or subprocess stderr.
        print(
            json.dumps(
                {
                    "error": type(error).__name__,
                    "message": str(error)
                    if isinstance(error, ValueError)
                    else "Qualification configuration or files unavailable",
                }
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
