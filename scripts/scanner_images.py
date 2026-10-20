"""Scan the declared platform images without loading Compose environment files.

Only the repository's explicit image/build-context YAML subset is accepted. A
future Compose syntax change must update this reader and its tests deliberately.
The scanner never runs containers or changes the running Compose stack.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

SERVICES = (
    "litellm",
    "postgres",
    "tempo",
    "prometheus",
    "grafana",
    "qdrant",
    "platform-metrics",
)
SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN")
IMAGE = re.compile(r"[a-z0-9][a-z0-9./_-]*:[A-Za-z0-9_.-]+(?:@sha256:[a-f0-9]{64})?")


@dataclass(frozen=True)
class Target:
    service: str
    image: str
    context: Path | None = None
    trust_context: Path | None = None


@dataclass
class Result:
    service: str
    image: str
    status: str
    report: str | None = None
    counts: dict[str, int] | None = None
    error: str | None = None
    diagnostic: str | None = None
    image_id: str | None = None


def scalar(value: str) -> str:
    """Read only literal single-line values, without interpolation or YAML tags."""
    value = value.strip()
    if value.startswith(("'", '"')) and value.endswith(value[0]):
        value = value[1:-1]
    if not value or any(c in value for c in " \t$&*!{}[]#\\\"'\n\r"):
        raise ValueError(
            "Valeur image/contexte non littérale ou syntaxe non prise en charge."
        )
    return value


def read_targets(compose: Path, *, memory: bool = False) -> list[Target]:
    """Extract only service names, images and local build contexts; ignore env data."""
    expected = ("neo4j",) if memory else SERVICES
    entries: dict[str, dict[str, str]] = {}
    current: str | None = None
    in_services = False
    in_build = False
    in_additional = False
    sections = 0
    for raw in compose.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw == "services:":
            sections += 1
            in_services = True
            current = None
            continue
        if not raw.startswith(" "):
            in_services = False
        if not in_services:
            continue
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise ValueError("Indentation Compose non prise en charge.")
        indent = len(raw) - len(raw.lstrip(" "))
        if indent == 2:
            match = re.fullmatch(r"  ([a-z][a-z0-9_-]*):", raw)
            if not match or match[1] not in expected or match[1] in entries:
                raise ValueError("Services Compose inattendus, ambigus ou dupliqués.")
            current = match[1]
            entries[current] = {}
            in_build = False
            in_additional = False
            continue
        if current is None or indent < 4:
            raise ValueError("Structure des services Compose non prise en charge.")
        if indent == 4:
            in_build = False
            in_additional = False
            match = re.fullmatch(r"    ([a-z_]+|<<):(?:\s*(.*))?", raw)
            if not match:
                raise ValueError("Champ Compose non pris en charge.")
            key, value = match[1], match[2] or ""
            if key in {"<<", "extends"}:
                raise ValueError("Les héritages Compose ne sont pas pris en charge.")
            if key in {"image", "build"}:
                if key in entries[current]:
                    raise ValueError("Déclaration image/build dupliquée.")
                entries[current][key] = scalar(value) if key == "image" else value
                if key == "build":
                    if value:
                        raise ValueError(
                            "Seul un bloc build/context explicite est pris en charge."
                        )
                    in_build = True
        elif in_build:
            match = re.fullmatch(r"      context:\s*(.+)", raw)
            if match and "context" not in entries[current] and not in_additional:
                entries[current]["context"] = scalar(match[1])
            elif (
                raw == "      additional_contexts:"
                and "additional" not in entries[current]
            ):
                entries[current]["additional"] = "declared"
                in_additional = True
            elif in_additional and "trust-policy" not in entries[current]:
                match = re.fullmatch(r"        trust-policy:\s*(.+)", raw)
                if not match:
                    raise ValueError("Seul le contexte local trust-policy est accepté.")
                entries[current]["trust-policy"] = scalar(match[1])
            else:
                raise ValueError(
                    "Seuls context et additional_contexts/trust-policy sont acceptés."
                )
    if sections != 1 or set(entries) != set(expected):
        raise ValueError(
            "Le fichier Compose doit déclarer exactement les services attendus."
        )

    targets = []
    for service in expected:
        entry = entries[service]
        image = entry.get("image", "")
        if not IMAGE.fullmatch(image) or image.split(":", 1)[-1] in {
            "latest",
            "main-stable",
        }:
            raise ValueError(
                "Chaque service doit déclarer une image épinglée explicitement."
            )
        context = None
        trust_context = None
        if "build" in entry:
            if service not in {*SERVICES, "neo4j"}:
                raise ValueError("Construction dérivée non prévue pour ce service.")
            if entry.get("context") != f"./images/{service}":
                raise ValueError(
                    "Le contexte doit rester dans le répertoire images du service."
                )
            if not image.startswith(f"ambicrafted/{service}:"):
                raise ValueError(
                    "Une image dérivée doit utiliser son nom local explicite."
                )
            context = compose.parent / "images" / service
            if context.resolve() != compose.parent.resolve() / "images" / service:
                raise ValueError(
                    "Un contexte de construction ne peut pas être un lien externe."
                )
            if not (context / "Dockerfile").is_file():
                raise ValueError("Dockerfile de l'image dérivée absent.")
            if "additional" in entry:
                if entry.get("trust-policy") != "./images/trust-policy":
                    raise ValueError(
                        "Le contexte trust-policy doit rester local et explicite."
                    )
                trust_context = compose.parent / "images" / "trust-policy"
                expected = compose.parent.resolve() / "images" / "trust-policy"
                if trust_context.resolve() != expected or not trust_context.is_dir():
                    raise ValueError("Contexte trust-policy absent ou lien externe.")
                if any(
                    path.is_symlink() or not (path.is_file() or path.is_dir())
                    for path in trust_context.rglob("*")
                ):
                    raise ValueError("Aucun lien ou fichier spécial dans trust-policy.")
        elif "@sha256:" not in image:
            raise ValueError("Une image distante doit être épinglée par digest SHA256.")
        targets.append(Target(service, image, context, trust_context))
    return targets


def vulnerability_counts(report: Path) -> dict[str, int]:
    payload = json.loads(report.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("SchemaVersion") != 2:
        raise ValueError("Schéma du rapport Trivy non reconnu.")
    results = payload.get("Results")
    if not isinstance(results, list) or not results:
        raise ValueError("Rapport Trivy sans résultat de paquet exploitable.")
    counts = dict.fromkeys(SEVERITIES, 0)
    for result in results:
        if not isinstance(result, dict):
            raise TypeError("Résultat Trivy invalide.")
        if not isinstance(result.get("Target"), str) or not result["Target"]:
            raise ValueError("Cible du résultat Trivy absente.")
        vulnerabilities = result.get("Vulnerabilities", [])
        if vulnerabilities is None:
            vulnerabilities = []
        if not isinstance(vulnerabilities, list):
            raise TypeError("Liste de vulnérabilités Trivy invalide.")
        for vulnerability in vulnerabilities:
            if (
                not isinstance(vulnerability, dict)
                or vulnerability.get("Severity") not in counts
            ):
                raise ValueError("Sévérité Trivy absente ou non reconnue.")
            counts[vulnerability["Severity"]] += 1
    return counts


def sanitized_tail(raw: bytes) -> str:
    """Keep useful public build errors while redacting credential-shaped values."""
    value = raw[-16384:].decode("utf-8", errors="replace")
    for key, secret in os.environ.items():
        if len(secret) >= 8 and re.search(
            r"SECRET|TOKEN|PASSWORD|CREDENTIAL|AUTH|COOKIE|(?:^|_)KEY",
            key,
            re.IGNORECASE,
        ):
            value = value.replace(secret, "[REDACTED]")
    value = re.sub(r"(?i)((?:bearer|basic)\s+)[^\s\"']+", r"\1[REDACTED]", value)
    value = re.sub(
        r"(?im)^([^\r\n]*?\b(?:authorization|proxy-authorization|cookie|set-cookie)\s*:\s*)[^\r\n]+",
        r"\1[REDACTED]",
        value,
    )
    value = re.sub(r"(https?://)[^/\s:@]+:[^@\s/]+@", r"\1[REDACTED]@", value)
    value = re.sub(
        r"""(?ix)
        (["']?(?:password|token|secret|api[_-]?key|authorization|cookie)["']?\s*[=:]\s*)
        (?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s&;,"']+)
        """,
        r"\1[REDACTED]",
        value,
    )
    return value


def command(
    argv: list[str], timeout: int, diagnostic: Path | None = None
) -> str | None:
    """No raw logs or inherited application credentials enter report artifacts.

    Only reviewed public Dockerfile contexts are built. A private temporary file
    avoids keeping their full compiler output in memory; only a bounded, redacted
    failure tail is retained. Successful build logs are discarded.
    """
    # Trivy environment overrides must not silently hide vulnerabilities.
    permitted = {
        "PATH",
        "HOME",
        "USER",
        "LANG",
        "LC_ALL",
        "TMPDIR",
        "XDG_RUNTIME_DIR",
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_CONFIG",
        "DOCKER_TLS_VERIFY",
        "DOCKER_CERT_PATH",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
    }
    environment = {k: v for k, v in os.environ.items() if k in permitted}
    with tempfile.TemporaryFile() as log:
        try:
            completed = subprocess.run(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=log if diagnostic else subprocess.DEVNULL,
                stderr=subprocess.STDOUT if diagnostic else subprocess.DEVNULL,
                timeout=timeout,
                check=False,
                env=environment,
            )
            error = f"code {completed.returncode}" if completed.returncode else None
        except subprocess.TimeoutExpired:
            error = "délai dépassé"
        except OSError:
            error = "exécutable indisponible"
        if error and diagnostic:
            log.seek(0, os.SEEK_END)
            log.seek(max(0, log.tell() - 16384))
            diagnostic.write_text(sanitized_tail(log.read()) or error, encoding="utf-8")
            diagnostic.chmod(0o600)
        return error


def scan(target: Target, trivy: str, output: Path, cache: Path) -> Result:
    result = Result(target.service, target.image, "erreur")
    print(f"{target.service} : préparation puis analyse", flush=True)
    prepare = (
        [
            "docker",
            "buildx",
            "build",
            "--load",
            "--pull",
            "--tag",
            target.image,
            *(
                ["--build-context", f"trust-policy={target.trust_context}"]
                if target.trust_context
                else []
            ),
            str(target.context),
        ]
        if target.context
        else ["docker", "pull", target.image]
    )
    diagnostic = output / f"prepare-{target.service}.log"
    failure = command(prepare, 1800, diagnostic)
    if failure:
        result.error = f"Préparation : {failure}"
        result.diagnostic = diagnostic.name
        return result
    report = output / f"trivy-{target.service}.json"
    diagnostic = output / f"scan-{target.service}.log"
    failure = command(
        [
            trivy,
            "image",
            "--image-src",
            "docker",
            "--scanners",
            "vuln",
            "--format",
            "json",
            "--output",
            str(report),
            "--cache-dir",
            str(cache),
            "--config",
            str(cache / "scanner-config.yaml"),
            "--ignorefile",
            os.devnull,
            "--ignore-unfixed=false",
            "--severity",
            ",".join(SEVERITIES),
            "--exit-code",
            "0",
            "--timeout",
            "10m",
            "--skip-version-check",
            "--no-progress",
            target.image,
        ],
        660,
        diagnostic,
    )
    if report.is_file():
        result.report = report.name
    if failure:
        result.error = f"Analyse : {failure}"
        result.diagnostic = diagnostic.name
        return result
    try:
        result.counts = vulnerability_counts(report)
        image_id = json.loads(report.read_text()).get("Metadata", {}).get("ImageID")
        if not isinstance(image_id, str) or not re.fullmatch(
            r"sha256:[a-f0-9]{64}", image_id
        ):
            raise ValueError("Identité immuable de l'image absente du rapport.")
        result.image_id = image_id
    except (OSError, ValueError, TypeError):
        result.error = "Rapport Trivy absent, incomplet ou invalide"
        return result
    result.status = (
        "vulnérabilités"
        if result.counts["CRITICAL"] + result.counts["HIGH"]
        else "conforme"
    )
    return result


def write_summary(results: list[Result], output: Path) -> int:
    exit_code = (
        2
        if any(r.error for r in results)
        else int(any(r.status == "vulnérabilités" for r in results))
    )
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "policy": "Échec sur toute occurrence CRITICAL/HIGH, y compris sans correctif disponible.",
        "exit_code": exit_code,
        "images": [asdict(result) for result in results],
    }
    (output / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    rows = [
        f"# Sécurité des {len(results)} images",
        "",
        "Seuil : toute occurrence CRITICAL/HIGH. Aucun filtre de vulnérabilité ni dérogation.",
        "",
        "| Service | État | CRITICAL | HIGH | MEDIUM | LOW | UNKNOWN |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for result in results:
        counts = [str(result.counts[s]) if result.counts else "—" for s in SEVERITIES]
        rows.append(
            f"| {result.service} | {result.status} | " + " | ".join(counts) + " |"
        )
    for result in results:
        if result.error:
            rows.extend(["", f"{result.service} : {result.error}", ""])
            if result.diagnostic:
                rows.append(f"Diagnostic borné et expurgé : `{result.diagnostic}`.")
    rows.extend(
        [
            "",
            "Les nombres comptent les occurrences paquet/CVE. Une erreur ne vaut jamais validation.",
            "",
            "Les rapports JSON complets et les références d'images figurent dans l'artefact.",
            "",
        ]
    )
    (output / "summary.md").write_text("\n".join(rows), encoding="utf-8")
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--compose", type=Path, default=Path("gateway/docker-compose.yml")
    )
    parser.add_argument(
        "--trivy", required=True, help="Binaire Trivy 0.74.0 vérifié par SHA256"
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="Nouveau répertoire de rapports"
    )
    parser.add_argument(
        "--cache", type=Path, required=True, help="Cache Trivy hors des rapports"
    )
    parser.add_argument(
        "--memory-compose", type=Path, help="Compose de la mémoire Neo4j dédiée"
    )
    parser.add_argument(
        "--service",
        choices=(*SERVICES, "neo4j"),
        help="Analyser un service dans un job isolé, avec la même politique complète.",
    )
    args = parser.parse_args(argv)
    try:
        targets = read_targets(args.compose.resolve())
        if args.memory_compose:
            targets.extend(read_targets(args.memory_compose.resolve(), memory=True))
        if args.service:
            targets = [target for target in targets if target.service == args.service]
            if not targets:
                raise ValueError("Service non déclaré dans les fichiers fournis.")
        # Refuse old reports: a failed scan must never reuse a prior clean JSON.
        args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
        args.cache.mkdir(mode=0o700, parents=True, exist_ok=True)
        (args.cache / "scanner-config.yaml").write_text("{}\n", encoding="utf-8")
        results = [
            scan(target, args.trivy, args.output, args.cache) for target in targets
        ]
        code = write_summary(results, args.output)
    except (OSError, ValueError):
        print(
            "Configuration invalide ou répertoire de rapports déjà présent/inaccessible.",
            file=sys.stderr,
        )
        return 2
    print(
        f"Analyses terminées : {len(results)} services, code de contrôle {code}.",
        flush=True,
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
