# PostgreSQL with a rebuilt gosu helper

## Targeted trust correction — 2026-10-21

The current dated image additionally distrusts the exact compromised emSign ECC
G3 root in its actual operating-system trust stores. See the shared
[trust policy](../trust-policy/README.md) for the fingerprint, native Java handling,
unchanged package inventory, qualification evidence and limits. This is a local
trust-policy change, not a claim that the vendor CA package was upgraded.
The named build context below contains only public policy code and certificates;
it is required when building manually. Compose and the image scanner supply it
explicitly. Existing application binaries and features are unchanged by this step.

## Application rebuild — 2026-10-20

The current Dockerfile preserves the same PostgreSQL 16.15 base and gosu 1.19
source described below, but builds gosu with **Go 1.27.3**. Its Linux/amd64 archive
SHA-256 is
`65efbc80fdc1fa2cd2631cad5b481777a68e8725f34e89f50fc6ac714e379b40`.
Upstream gosu dependencies and symbols remain preserved. The build runs upstream
tests, compares two builds and verifies a real user switch.

```sh
docker buildx build --load --build-context trust-policy=gateway/images/trust-policy --platform linux/amd64 \
  --tag ambicrafted/postgres:16.15-alpine-security.20261021 \
  gateway/images/postgres
```

The 20 October candidate scan records 0 CRITICAL, 0 HIGH, 2 MEDIUM and 1 UNKNOWN;
the remaining findings are retained. See
[the current qualification](../../../docs/QUALIFICATION-2026-10-20.md) and the
candidate's scan artifact. The old binary/image hashes below do not identify this
new build. Candidate validation does not promote the running database or replace
its backup and rollback procedure.

## Historical build and evidence — 2026-09-26

The following recipe, hashes, tag and measurements describe the earlier
Go 1.27.1 derivative. They are retained as historical evidence.

This linux/amd64 derivative preserves the tested PostgreSQL 16.15 Alpine base
digest and replaces only `/usr/local/bin/gosu`. It rebuilds the **same gosu 1.19
source** with Go 1.27.1 instead of Go 1.24.6. PostgreSQL, the entrypoint, OS
packages, default user and data paths remain those of the upstream base.

The upstream image's own `gosu --version` confirmed version 1.19. The source
is pinned to [the official 1.19 commit](https://github.com/tianon/gosu/commit/6456aaa0f3c854d199d0f037f068eb97515b7513),
and the compiler version/checksum were checked against
[Go's official download manifest](https://go.dev/dl/?mode=json).

| Input | Pinned value |
|---|---|
| PostgreSQL base SHA-256 | `721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea` |
| gosu 1.19 commit | `6456aaa0f3c854d199d0f037f068eb97515b7513` |
| Source archive SHA-256 | `33d7537d588ea49458b9509bcf4554bdf5ceacc66da71e5caa1058ea3b689c3b` |
| Go 1.27.1 linux-amd64 archive SHA-256 | `63d339f0da5ab53635a56f2490a7984dfe12dfcff22ad749f63edaf590168445` |
| Built gosu SHA-256 | `9ebd2c978d2a66aeee22a52a0679f0351ad72eb0cb7b61c4ee3e21a0ccc52f48` |

The source archive checksum was captured from the official commit URL; this
does not assert a separately verified release signature. Docker verifies both
archive checksums before building. The upstream `go.mod` and `go.sum` remain
unchanged, module integrity is checked, and automatic Go toolchain downloads
are disabled. The build uses CGO disabled, Linux/amd64, trimmed source paths
and unstripped symbol tables, following upstream's requirement to preserve
symbols for vulnerability analysis. Source provenance is recorded here because
automatic VCS stamping is disabled for the checksum-pinned source archive.
An additional forced compilation (`go build -a`) in a disposable builder with
no network access reproduced the exact gosu binary checksum independently of
the package compilation cache.

Build from the repository root:

```sh
docker build --pull=false --platform linux/amd64 \
  --tag ambicrafted/postgres:16.15-alpine-security.20260926 \
  gateway/images/postgres
```

The dedicated context includes only the Dockerfile and `.dockerignore`.
The multi-stage build leaves the Go compiler and sources outside the final
image. Do not use this recipe for another architecture without adding its
verified compiler archive, rebuilding and repeating all tests.

The tested local image ID is
`sha256:7cefe6bc2b60576666fbce7ad8ed9234c6189297fddbf2d788681d2ab687d373`.
A future build's image metadata may produce a different image ID; validate
that artifact rather than assuming it is identical. This tag has not been
published to a registry.

Validation used two disposable containers with `--network none`, no published
ports and fresh anonymous data volumes. Both initialized successfully.
gosu switched to PostgreSQL UID 70, and the PostgreSQL server's real/effective
UIDs were 70. A real private backup restored 86 public tables. A further 250
fixture rows survived restart, and a new `pg_dump` restored successfully into
the second candidate with matching row checksums and table counts. Containers
and their anonymous volumes were removed after testing.

Trivy 0.74.0, with the same fresh database as the baseline review, reports
**0 CRITICAL / 0 HIGH / 0 MEDIUM / 0 LOW / 1 UNKNOWN**, compared with
1/21/21/2/1 in the upstream image. The remaining advisory, CVE-2026-39824,
concerns `golang.org/x/sys/windows.NewNTUnicodeString`; this Linux build retains
the upstream dependency version. It is documented rather than suppressed.

All build, provenance, scan and validation evidence is under
`/home/vedric/platform/finalisation-2026-09-26/console/security/` with prefix
`postgres-` or `trivy-postgres-`. See the
[release review](../../../docs/SECURITY-RELEASE-2026-09-26.md) for remaining
platform risks. These candidate tests do not themselves promote the image or
replace a backup and rollback procedure for the running database.
