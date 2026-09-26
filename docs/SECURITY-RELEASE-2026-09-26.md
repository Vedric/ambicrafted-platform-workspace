# Container security release review — 2026-09-26

The final promoted image set produces **0 CRITICAL and 166 HIGH package
occurrences** with Trivy 0.74.0 and a newly downloaded vulnerability database.
Two tested derivatives remove the four critical occurrences and 25 highs by
updating Qdrant's Perl package and rebuilding PostgreSQL's gosu helper with
patched Go. The upstream baseline at 16:38 UTC was **4 CRITICAL and 191 HIGH**.
No finding was hidden or assigned a lower severity to obtain these results.
Remaining highs still require remediation or documented reachability review;
these scans do not establish a platform without vulnerabilities or an
unconditional production security sign-off.

The coordinating task confirmed Compose promotion and service recreation with
the existing volumes: six services healthy, 31 indexed vectors, and all eleven
platform verification checks passing. The running PostgreSQL helper reports
gosu 1.19 with Go 1.27.1; Qdrant's running package reports the corrected Perl
version. A pre-promotion backup restored 86 database tables, 31 vectors and
four console analyses with four checkpoints, excluding sessions and tickets.
The separate post-promotion backup/restore exercise also passed: 86 database
tables, 31 vectors, six console analyses with six checkpoints, valid console/
Grafana/graph SQLite databases, and zero restored authentication sessions or
tickets. Evidence is `console/restauration-livraison.json` relative to the
dated evidence root, with backup provenance in `console/sauvegarde-livraison.json`.
This is a restore exercise, not a claim of atomicity across the independent
databases; the manifest explicitly records that limitation.

This review covers image contents and the checked-in Compose exposure. It
complements [the dependency review](DEPENDENCIES.md) and
[the control API test report](TEST-CONTROL.md); it is not a penetration test,
a host security assessment, or proof that every vulnerable function is called.
The initial scan was read-only. Separate Qdrant and PostgreSQL derivatives
were built and tested before their promotion by the coordinating task. The
security subtask did not operate on production volumes. No secret environment
file or container environment was printed by this review.

## Reproducible evidence and freshness

Evidence is outside Git at
`/home/vedric/platform/finalisation-2026-09-26/console/security/`:

- `trivy-<service>.json` and `.log`: six complete, unfiltered scans;
- `scanner-provenance.json`: download URL, time, and verified archive checksum;
- `scan-runs.json`: exact image references, start/end times, and exit codes;
- `cache/db/metadata.json`: the database actually used;
- `summary.json`: per-image counts and finding locations;
- `summary-promoted.json`: the final aggregate and six selected scan files;
- `findings-high-critical.csv`: all 195 upstream CRITICAL/HIGH occurrences, including
  package, binary location, installed/fixed versions, advisory URL and source;
- `findings-high-critical-promoted.csv`: all 166 remaining HIGH occurrences;
- `evidence-sha256.json`: hashes of these reports and metadata.

The official [Trivy 0.74.0 release](https://github.com/aquasecurity/trivy/releases/tag/v0.74.0)
archive was downloaded over HTTPS and matched the release checksum:
`2ae6fe3ee734b7fdf11335663e18c75ea12dccc76062f09f164a3b0f8be4371a`.
This is checksum verification against the publisher's release, not a claim of
independent signature verification.

| Evidence | UTC timestamp |
|---|---|
| New vulnerability database `UpdatedAt` | 2026-09-26 12:58:40 |
| New database downloaded | 2026-09-26 16:38:08 |
| New database `NextUpdate` | 2026-09-27 12:58:40 |
| Six scans | 2026-09-26 16:38:03–16:38:49 |
| Previous database `UpdatedAt` | 2026-09-26 06:33:51 |
| Previous scans using Trivy 0.69.1 | 2026-09-26 14:26:32–14:26:56 |

The previous vulnerability database was already from the same day. Its Java
index was old, but none of these reports contains a Java target. The fresh
scan used a separate cache and did not need a Java index. An Alpine 3.24 EOL
lookup warning persists in 0.74.0 for PostgreSQL and Grafana; it means that the
scanner's EOL list lacks that version, not that these images are proven EOL.

References were read directly from the six `image:` entries in
`gateway/docker-compose.yml`, including their SHA-256 digests. Each scan used
the Docker image source and this command shape from the evidence directory:

```sh
./trivy image --cache-dir ./cache --image-src docker --scanners vuln \
  --format json --output trivy-SERVICE.json --timeout 10m \
  --skip-version-check --no-progress 'IMAGE:TAG@sha256:DIGEST'
```

All six commands completed with exit code 0. That means scanning succeeded;
the default command does not fail because vulnerabilities exist. No severity
filter, `--ignore-unfixed`, ignore file, or VEX suppression was applied.
Detection used Trivy's default `precise` mode. Package inventories and severity
ratings have limitations, and distribution backports must be compared against
distribution versions. See [Trivy's detection and severity documentation](https://trivy.dev/docs/v0.74/guide/scanner/vulnerability/).

## Final promoted images and historical baseline

The final total combines the two derivative scans with the four unchanged
upstream scans using the same database. Scan files for the derivatives end in
`-candidate.json`, preserving their original evidence names after promotion.

| Promoted image | Critical | High | Medium | Low | Unknown |
|---|---:|---:|---:|---:|---:|
| LiteLLM 1.102.1, unchanged | 0 | 0 | 9 | 0 | 0 |
| PostgreSQL 16.15 Alpine security derivative | 0 | 0 | 0 | 0 | 1 |
| Tempo 3.0.3, unchanged | 0 | 12 | 4 | 4 | 2 |
| Prometheus 3.15.0, unchanged | 0 | 0 | 0 | 0 | 2 |
| Grafana 13.2.2, unchanged | 0 | 104 | 33 | 35 | 6 |
| Qdrant 1.19.1 security derivative | 0 | 50 | 63 | 59 | 2 |
| **Final promoted total** | **0** | **166** | **109** | **98** | **13** |

There are 148 distinct advisory identifiers across all severities in the final
set, with 123 HIGH occurrences having a reported fixed version and 43 without
one in this database. Critical count zero is a dated scan result,
not proof that remaining findings or unknown vulnerabilities are harmless.

### Upstream baseline, before the two derivative replacements

Counts are package occurrences, including repeated advisories in different
binaries. There are **177 distinct advisory identifiers across all severities**;
these are not necessarily 177 independent vulnerabilities because aliases may
also differ. Across CRITICAL/HIGH occurrences, 152 have a reported fixed version
and 43 do not. A blank fixed version means this database does not identify a
distribution fix; it does not mean correction is impossible everywhere.

| Image | Critical | High | Medium | Low | Unknown | Distinct IDs | C/H with fix |
|---|---:|---:|---:|---:|---:|---:|---:|
| LiteLLM 1.102.1 | 0 | 0 | 9 | 0 | 0 | 3 | 0 |
| PostgreSQL 16.15 Alpine | 1 | 21 | 21 | 2 | 1 | 46 | 22 |
| Tempo 3.0.3 | 0 | 12 | 4 | 4 | 2 | 19 | 12 |
| Prometheus 3.15.0 | 0 | 0 | 0 | 0 | 2 | 1 | 0 |
| Grafana 13.2.2 | 0 | 104 | 33 | 35 | 6 | 63 | 104 |
| Qdrant 1.19.1 | 3 | 54 | 69 | 59 | 2 | 97 | 14 |
| **Total occurrences** | **4** | **191** | **136** | **100** | **13** | — | **152** |

These numbers exactly match the earlier 0.69.1 scan. The complete references
below identify the reviewed artifacts; the review must be repeated after any
image rebuild, even when its human-readable tag stays the same.

| Image | SHA-256 digest |
|---|---|
| `ghcr.io/berriai/litellm:v1.102.1` | `87f34979b9f8cb274fac90ca8a4fdda07d8480de22755562a26adeb95ce20d02` |
| `postgres:16.15-alpine` | `721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea` |
| `grafana/tempo:3.0.3` | `0296560ac66f8a3600d7fb3014a52c189d4d9c3549ad6ff441bf2409855d68d5` |
| `prom/prometheus:v3.15.0` | `efd719c99d83b060d9daefdcf00360461adf279f45ef5391f8d111892118753e` |
| `grafana/grafana:13.2.2` | `ac461fb352abc50da10a51c7d02462e9c05488f11f53f14b3ad79a8145f638a0` |
| `qdrant/qdrant:v1.19.1` | `12364fe851b9f17356fc88189fc06d1b521262e04659ec7345975b00c9246a10` |

## The four critical occurrences in the upstream baseline

All four occurrences below disappear in the respective derivative scans. The
table preserves their original conditions and assessment so the remediation
is auditable; it does not describe four remaining critical findings.

| Image / package | Advisory and actual prerequisite | Installed → reported fix | Assessment |
|---|---|---|---|
| PostgreSQL / Go standard library in `usr/local/bin/gosu` | CVE-2025-68121: TLS session resumption after changing trusted CAs | Go 1.24.6 → 1.24.13 or 1.25.7; later maintained patched toolchains also apply | Strong candidate for non-applicability: gosu switches process identity and executes the command, rather than serving TLS. Exact artifact reachability attestation remains outstanding. |
| Qdrant / `perl-base` | CVE-2026-13221: compiling an attacker-controlled regular expression with more than 65,535 alternatives | 5.40.1-6 → 5.40.1-6+deb13u1 | No Perl-regex path identified in this repository's Qdrant usage. Presence alone does not prove such a path; the available package update remains appropriate. |
| Qdrant / `perl-base` | CVE-2026-42496: Perl Archive::Tar processing malicious symlink targets during extraction | 5.40.1-6 → 5.40.1-6+deb13u1 | The source-package advisory does not prove that this optional Perl module is installed or used. No extraction call chain was established. Patch or attest the exact package contents and call path. |
| Qdrant / `perl-base` | CVE-2026-8376: a crafted regex overflowing an allocation on a **32-bit Perl build** | 5.40.1-6 → 5.40.1-6+deb13u1 | Scanned image metadata is amd64. This weakens applicability, but image architecture alone does not prove the Perl executable's integer width. No automatic waiver is issued. |

The TLS condition and fixes are recorded by the [Go vulnerability database](https://pkg.go.dev/vuln/GO-2026-4337).
The three Perl conditions and Debian trixie fixes are confirmed by the
[regex advisory](https://security-tracker.debian.org/tracker/CVE-2026-13221),
[Archive::Tar advisory](https://security-tracker.debian.org/tracker/CVE-2026-42496),
and [32-bit overflow advisory](https://security-tracker.debian.org/tracker/CVE-2026-8376).
These are package/advisory facts. The applicability assessments in the table
are bounded inferences, not exploit demonstrations or completed VEX evidence.

## Image-by-image remediation

### PostgreSQL

All 46 upstream findings, including the critical and 21 highs, are located in `gosu`;
the scan reports no Alpine OS finding for this image. They are not 22 findings
in the PostgreSQL database engine. All critical/high entries concern the
embedded Go 1.24.6 standard library.

The [gosu 1.19 security policy](https://github.com/tianon/gosu/blob/1.19/SECURITY.md)
explicitly discusses irrelevant Go-library scanner findings and requests
function-level verification with its govulncheck wrapper. Its
[entry-point source](https://github.com/tianon/gosu/blob/1.19/main.go) supports
the narrow identity-switch/exec role. Complete an exact-version, Linux-amd64
call-graph review with the current advisory database before signing a
digest-bound non-applicability record. No such tool result is claimed here.

The implemented [PostgreSQL derivative](../gateway/images/postgres/Dockerfile)
retains the exact upstream base and replaces only `/usr/local/bin/gosu`.
Running the helper in the upstream image confirmed gosu 1.19 built with
Go 1.24.6. The replacement uses unchanged gosu source at official tag 1.19,
[commit 6456aaa0f3c854d199d0f037f068eb97515b7513](https://github.com/tianon/gosu/commit/6456aaa0f3c854d199d0f037f068eb97515b7513),
compiled with stable Go 1.27.1. The compiler archive SHA-256 was verified
against the [official Go download manifest](https://go.dev/dl/?mode=json);
the [release history](https://go.dev/doc/devel/release#go1.27) confirms this
stable compiler release.

Both source and compiler archives are checksum-pinned in the Dockerfile.
The original `go.mod` and `go.sum` are unchanged; dependencies are verified,
automatic toolchain downloads are disabled, and symbol tables are preserved
for later analysis. The multi-stage build copies only the helper into the
final image; the compiler and sources are absent. The build is limited to
the validated Linux/amd64 architecture. A fresh forced compilation using
`go build -a` without network access reproduced the helper's exact SHA-256.

| PostgreSQL derivative evidence | Value |
|---|---|
| Local tag | `ambicrafted/postgres:16.15-alpine-security.20260926` |
| Build image ID | `sha256:7cefe6bc2b60576666fbce7ad8ed9234c6189297fddbf2d788681d2ab687d373` |
| gosu binary SHA-256 | `9ebd2c978d2a66aeee22a52a0679f0351ad72eb0cb7b61c4ee3e21a0ccc52f48` |
| Upstream scan | 1 C / 21 H / 21 M / 2 L / 1 U |
| Derivative scan | **0 C / 0 H / 0 M / 0 L / 1 U** |
| Actual upstream helper | `1.19 (go1.24.6 on linux/amd64; gc)` |
| Replacement helper | `1.19 (go1.27.1 on linux/amd64; gc)` |

Two disposable containers initialized real databases with no network and no
published port. gosu switched to PostgreSQL UID 70 and the server's PID 1 had
real/effective/saved/filesystem UID 70. A real private backup restored
**86 public tables**. An additional 250 fixture rows survived restart; a new
custom-format `pg_dump` restored into the second candidate with matching table
counts and fixture checksum. Both containers and their fresh anonymous data
volumes were removed. No private records or passwords were printed.

The remaining UNKNOWN occurrence is CVE-2026-39824 in x/sys 0.1.0. The
[Go advisory](https://pkg.go.dev/vuln/GO-2026-5024) limits the affected symbol
to `golang.org/x/sys/windows.NewNTUnicodeString`, while this artifact is built
for Linux. It remains visible in the scan; no suppression or module upgrade
was used to alter this result. The standard-library critical and high findings
were removed by an actual rebuilt binary, not a non-applicability waiver.

Full evidence is in `postgres-candidate-build.log`,
`postgres-gosu-source-provenance.json`, `postgres-gosu-reproducibility.json`,
`postgres-candidate-validation.json` and `trivy-postgres-candidate.json`.
The [build README](../gateway/images/postgres/README.md) records checksums,
scope and reproduction commands. The derivative is local, not published to a
registry; build IDs must not be mistaken for remotely pullable image digests.

### Qdrant

Qdrant has the clearest small package-update opportunity. The following
minimum versions are reported by the scanner. They are candidates for a
reproducible derivative image. The Perl-only change was subsequently built and
tested as described below; the other updates were not implemented here.

| Package | Installed → fixed | C/H occurrences addressed | Advisory IDs |
|---|---|---:|---|
| `perl-base` | 5.40.1-6 → 5.40.1-6+deb13u1 | 3 C + 4 H | CVE-2026-13221, -42496, -8376, -42497, -48962, -57432, -57433 |
| `gzip` | 1.13-1 → 1.13-1+deb13u1 | 1 H | CVE-2026-41992 |
| `libpcre2-8-0` | 10.46-1~deb13u1 → 10.46-1~deb13u2 | 3 H | CVE-2026-86145, -89157, -89161 |
| `libsqlite3-0` | 3.46.1-7+deb13u1 → 3.46.1-7+deb13u2 | 2 H | CVE-2026-11822, -11824 |
| Bundled `js-yaml` | 4.3.1 → 4.3.2 | 1 H | CVE-2026-84375 |

The OS changes can address 13 of the 57 C/H occurrences if the vendor packages
are available and the rescan confirms them. The remaining fixable occurrence
is in the bundled JavaScript dependency inventory; rebuilding the relevant
web UI dependency is different from an OS upgrade. Arbitrarily installing an
npm package elsewhere in the image would not replace that dependency.

The 43 HIGH occurrences without a reported fixed version are fully accounted
for below. Several derive from the same Debian source package and are repeated
across binary packages; the table does not assert that each binary exposes the
affected program.

| Source / baseline installed packages | High occurrences | IDs | Reachability questions |
|---|---:|---|---|
| util-linux 2.41.5 family: `bsdutils`, `libblkid1`, `liblastlog2-2`, `libmount1`, `libsmartcols1`, `libuuid1`, `login`, `mount`, `util-linux` | 36 | CVE-2026-76642, -78408, -78409, -78410 in each of nine packages | Namespace, mount and ownership operations need relevant utilities, privileges and caller-controlled paths. Library presence alone does not establish those paths. |
| `libacl1` 2.3.2-2+b1 | 1 | CVE-2026-54369 | Check actual privileged ACL/path traversal operations. |
| `libsystemd0`, `libudev1` 257.13-1~deb13u1 | 2 | CVE-2026-16742 | A systemd-homed issue is not proof that homed runs inside Qdrant. |
| `libtinfo6`, `ncurses-base`, `ncurses-bin` 6.5+20250216-2 | 3 | CVE-2025-69720 | Check whether the affected terminal parsing is reachable. |
| `perl-base` 5.40.1-6 | 1 | CVE-2026-9538 | Check availability and use of the affected Perl Archive::Tar path. |

A minimal runtime image may reduce unused utilities, but requires ownership
of the build and validation of dynamic libraries, vector operations,
snapshots, restore, storage permissions and hardware compatibility. It is not
a safe untested shortcut to a zero counter. The latest stable release checked
on the [Qdrant release page](https://github.com/qdrant/qdrant/releases) was
already v1.19.1, so changing only to a newer advertised stable tag was not an
available complete remedy at review time.

#### Tested and promoted Perl correction

The new [Dockerfile](../gateway/images/qdrant/Dockerfile) uses the exact upstream
digest above and upgrades only `perl-base` to `5.40.1-6+deb13u1`, using APT's
normal signed repository verification. The dedicated build context excludes
all files other than the Dockerfile and `.dockerignore`; it contains no
environment file, backup or application data. The
[build instructions](../gateway/images/qdrant/README.md) explain its scope.

| Artifact | Value |
|---|---|
| Local candidate tag | `ambicrafted/qdrant:1.19.1-security.20260926` |
| Build image ID | `sha256:6bf8e2332c0e3a8305260a067301885ac617712e69f80458180bf9d28ea44578` |
| Package verified inside disposable candidate | `perl-base 5.40.1-6+deb13u1` |
| Upstream Qdrant scan | 3 C / 54 H / 69 M / 59 L / 2 U |
| Candidate scan, same Trivy and database | **0 C / 50 H / 63 M / 59 L / 2 U** |
| Candidate distinct advisory IDs | 84 |
| Difference | 3 C, 4 H and 6 M removed; no added advisory/package/severity tuple |
| Intermediate six-image aggregate with Qdrant correction only | **1 C / 187 H / 130 M / 100 L / 13 U** |

The candidate restored the existing private backup into a disposable
collection: **31 points, 768 dimensions**. Readiness, nearest-vector querying,
new collection creation, point upsert/query, restart persistence and deletion
all passed. Validation used a dedicated bridge network and one host-loopback
port, with telemetry disabled and a fresh anonymous storage volume. The
container, volume and network were removed afterwards. No restored payloads
were printed. An earlier attempt using Docker's `internal` network could not
reach the published readiness port; it was cleaned up and is retained as an
unsuccessful network-isolation attempt, not counted as a passing test.

Evidence files are `qdrant-candidate-build.log`, `qdrant-candidate-image-id`,
`qdrant-candidate-validation.json`, `qdrant-candidate-attempt-internal-network.json`,
`trivy-qdrant-candidate.json`, its scanner log and
`findings-high-critical-candidate.csv`. The image is local and was not
published to a registry. Its build ID is not a claim that a registry digest
can be pulled elsewhere. The derivative has now been promoted in Compose;
service health and the running corrected package version were confirmed by
the coordinating task. The historical baseline is preserved separately.
Fifty highs remain in this derivative, including seven
with announced fixes and 43 without a fixed version in this database.

### Tempo

All 12 HIGH occurrences are in the static `tempo` executable. The fixes listed
below require an upstream release or a maintained rebuild of the executable.
Updating Debian packages alone does not update those linked modules.

| Component | Installed → minimum target for listed findings | High IDs |
|---|---|---|
| Go standard library | 1.26.5 → 1.26.6 | CVE-2026-33818, -39821, -46600, -56853, -56858, -56859, -56860, -56862 |
| Apache Thrift | 0.23.0 → 0.24.0 | CVE-2026-43871 |
| `golang.org/x/crypto` | 0.53.0 → 0.55.0 | CVE-2026-56854 |
| gRPC | 1.82.1 → 1.83.2 | CVE-2026-84304, -84445 |

The Go and gRPC parser/transport findings deserve priority because Tempo is a
network service handling traces. The SSH-related x/crypto advisory still needs
an actual SSH use path; module inclusion is not proof. The current configuration
exposes OTLP HTTP and the query API only on host loopback. It explicitly runs
Tempo as root, increasing the impact of any successful compromise.
[Tempo 3.0.3](https://github.com/grafana/tempo/releases) was the latest stable
release checked; prerelease availability is not production validation.

### Grafana

The 104 HIGH occurrences comprise two OS OpenSSL findings, one Apache Thrift
finding in the main binary, and 101 findings in bundled backend plugins.
The active provisioned sources are Prometheus and Tempo: their plugin binaries
alone contain 10 and 16 HIGH occurrences respectively. Therefore, removing
unused plugins would not resolve the active-source findings.

| Location | High occurrences | Principal update targets reported by the scan |
|---|---:|---|
| `libcrypto3`, `libssl3` | 2 | 3.5.7-r0 → 3.5.8-r0; CVE-2026-14456, requiring the affected QUIC server path |
| Main Grafana binary | 1 | Apache Thrift pseudo-version based on 0.23.1 → 0.24.0; CVE-2026-43871 |
| PostgreSQL / InfluxDB / Jaeger plugins | 1 each | gRPC → 1.83.2 for CVE-2026-84445 |
| Pyroscope plugin | 14 | Go, gRPC, x/net, x/text |
| OpenTSDB plugin | 30 | Go, gRPC, x/net, x/text, OpenTelemetry |
| Prometheus plugin, provisioned | 10 | Go 1.26.5 → 1.26.6; gRPC 1.82.1 → 1.83.2 |
| Stackdriver plugin | 17 | Go, gRPC, x/crypto |
| Tempo plugin, provisioned | 16 | Go, gRPC, x/net, x/text and embedded Tempo module findings |
| Zipkin plugin | 11 | Go, gRPC, x/net, x/text |

Across these binaries the reported Go versions range from 1.25.7 to 1.26.5;
Go 1.26.6 addresses the listed standard-library highs. Additional targets are
x/net 0.56.0, x/text 0.39.0, x/crypto 0.55.0, OpenTelemetry 1.41.0 and its SDK
1.43.0. gRPC 1.83.2 covers the listed high advisories, including
GHSA-hrxh-6v49-42gf in older plugins. These are minimum candidates from this
snapshot, not a claim that unrelated compatibility constraints have been tested.

The Tempo plugin embeds module pseudo-version
`v1.5.1-0.20250529124718-87c2dc380cec`. The scanner maps CVE-2026-21728 and
CVE-2026-28377 to this version and lists fixes up to Tempo 2.10.3. A server
query/config-endpoint advisory does not establish that the vulnerable server
endpoint exists inside a Grafana client plugin; confirm the actual call path
before treating that module mapping as exploitable or issuing a waiver.

[Grafana 13.2.2](https://github.com/grafana/grafana/releases) was already the
latest stable release checked. A new OS layer would address only two highs.
An effective rebuild must cover the main binary and each retained plugin,
preserve plugin integrity checks, and test provisioned dashboards, queries and
authentication. Merely updating the host's Go toolchain changes none of these
already-built executables.

### LiteLLM and Prometheus

There are no reported CRITICAL/HIGH occurrences in these two images. LiteLLM
retains nine MEDIUM OS-package occurrences across three advisory IDs.
Prometheus retains two UNKNOWN occurrences of GO-2026-5932 in Prometheus and
promtool, concerning the unmaintained `golang.org/x/crypto/openpgp` package.
UNKNOWN is not equivalent to harmless, and a clean high/critical count is not
proof that an image has no security defects. Full remaining findings stay in
the JSON evidence and should remain in routine dependency triage.

## Exposure and release decision

The checked-in Compose file publishes LiteLLM 4000, Tempo 4318/3200,
Prometheus 9090, Grafana 3000 and Qdrant 6333 on `127.0.0.1`. PostgreSQL has
no published host port. Services share a Docker bridge network; it is not
declared `internal: true`. Compose now declares
`security_opt: [no-new-privileges:true]` for all six services. There is no
service-level `cap_drop` or `read_only` declaration. Actual kernel/container
capabilities were not independently inspected by this security subtask.

The authenticated private console reduces who can operate its own API. It
does not automatically authenticate the other published service ports.
Loopback prevents ordinary direct connections from another host, but local
processes, an affected application making local requests, and containers on
the shared network remain relevant. Qdrant, Prometheus and Tempo configuration
must not be assumed to provide a multi-tenant security boundary. No remote
binding or reverse-proxy publication should be inferred from this assessment.

| Intended release | Decision from this evidence | Required completion |
|---|---|---|
| Continued supervised use on a trusted private workstation by its single operator | **Conditional GO for the existing restricted operating scope**, with documented remaining findings | Keep loopback bindings, authenticated console and private data permissions; use only trusted inputs/operators; retain monitoring, backups and timely triage. This is not a zero-vulnerability or unrestricted production claim. |
| Unqualified local production security sign-off | **NO-GO at this snapshot** | Finish reachable HIGH triage and document owned residual risks, including recovery and update procedures. The promoted images now have zero reported criticals, but 166 highs remain. |
| Remote access, public exposure or mutually untrusted users | **NO-GO** | Complete image remediation/reachability work plus authenticated service access, TLS, per-user authorization, network separation, hardened runtime permissions and abuse/resource limits, with corresponding tests. |

Recommended closure order:

1. Preserve the validated post-promotion backup and rollback procedure, and
   continue the remaining Qdrant package fixes. The two tested, promoted
   replacements remove all four upstream criticals and 25 highs but do not
   close the whole image review.
2. Retain source, compiler, package and binary provenance for the derivative
   images and repeat their isolated restore tests on future updates. Keep the
   remaining Windows-only module advisory visible and documented.
3. Track or maintain corrected Tempo/Grafana binaries and active plugins;
   verify trace ingestion, query paths, dashboards and resource exhaustion
   behavior before replacement. Do not rely on an OS-only upgrade.
4. Validate non-root operation, capability removal and filesystem restrictions
   per service in an isolated stack, including volume migrations and restore.
   These reduce consequences; they do not substitute for dependency fixes.
5. Re-run scans against final image digests and attach any narrowly justified
   VEX statements with an owner, evidence and expiry. Do not lower severities
   or hide unfixed entries solely to obtain a green counter.

Review this dated assessment after every image change and no later than
**2026-10-10**. A future clean scan would still establish only the absence of
findings known to that scanner/database at that time.
