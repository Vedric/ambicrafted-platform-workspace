FROM golang:1.27.3-bookworm@sha256:972b4110ba0f47539a975c31e52c64765e1ff19f2d74469ae4a595c6676e80a5 AS source
ADD --checksum=sha256:65efbc80fdc1fa2cd2631cad5b481777a68e8725f34e89f50fc6ac714e379b40 https://go.dev/dl/go1.27.3.linux-amd64.tar.gz /tmp/go.tar.gz
RUN test "$(uname -m)" = x86_64 && rm -rf /usr/local/go && tar -xzf /tmp/go.tar.gz -C /usr/local
WORKDIR /src
ENV GOTOOLCHAIN=local GOTELEMETRY=off GOMAXPROCS=4
ADD --checksum=sha256:f10ae5ecaa7f1eade220b9d013ae73961227b51a7602694896675df1cb96e8e7 https://codeload.github.com/grafana/tempo/tar.gz/1900ed7bb5cad1a3edc285783d7d4ac4278337dc /tmp/source.tar.gz
RUN tar -xzf /tmp/source.tar.gz --strip-components=1 -C /src && rm /tmp/source.tar.gz
COPY go.mod go.sum ./
RUN go mod download && go mod verify

FROM source AS checked
COPY exporters_security_test.go ./cmd/tempo/exporters_security_test.go
# Check real upstream startup/configuration and OTLP receiver contracts.
# The build network namespace has eth0 for ring tests; localhost is isolated
# from host services. Tests use local fixtures, no production state or customer data.
RUN --mount=type=cache,target=/root/.cache/go-build go test -mod=readonly -p=4 -race -count=1 -timeout=10m -json ./cmd/tempo/... ./modules/distributor/receiver/... > /tmp/tempo-tests.json \
    || { cat /tmp/tempo-tests.json; exit 1; }

FROM checked AS build
RUN --network=none --mount=type=cache,target=/root/.cache/go-build CGO_ENABLED=0 GOAMD64=v2 go build -mod=readonly -p=4 -trimpath \
    -ldflags='-s -w -X main.Version=3.0.3-security.20261020 -X main.Revision=1900ed7bb5cad1a3edc285783d7d4ac4278337dc -X main.Branch=security-rebuild' \
    -o /out/tempo ./cmd/tempo

FROM grafana/tempo:3.0.3@sha256:0296560ac66f8a3600d7fb3014a52c189d4d9c3549ad6ff441bf2409855d68d5 AS runtime-base

# The package checksum is taken from authenticated Debian bookworm-security
# metadata. Extract the real data and package records together; do not relabel
# the old timezone files. No package manager is added to the final runtime.
FROM node:24.21.0-bookworm@sha256:64af3819f9275802414d7cdc38c27e9d82bd564dec4d4da87d008255d36c63b4 AS timezone
ADD --checksum=sha256:c6bdac9aa03e89a112c8d900cb60321889cfec535e0397b74383bd10c8b3cb44 https://deb.debian.org/debian-security/pool/updates/main/t/tzdata/tzdata_2026c-0+deb12u1_all.deb /tmp/tzdata.deb
COPY --from=runtime-base /var/lib/dpkg/status.d/tzdata.md5sums /tmp/old-tzdata.md5sums
RUN test "$(dpkg-deb -f /tmp/tzdata.deb Version)" = 2026c-0+deb12u1 \
    && dpkg-deb -x /tmp/tzdata.deb /runtime \
    && dpkg-deb -e /tmp/tzdata.deb /control \
    && mkdir -p /runtime/var/lib/dpkg/status.d \
    && cp /control/control /runtime/var/lib/dpkg/status.d/tzdata \
    && cp /control/md5sums /runtime/var/lib/dpkg/status.d/tzdata.md5sums \
    && cd /runtime && md5sum -c --quiet var/lib/dpkg/status.d/tzdata.md5sums \
    && while read -r checksum file; do test -e "/runtime/$file" || exit 1; done < /tmp/old-tzdata.md5sums \
    && test "$(head -n 1 /runtime/usr/share/zoneinfo/tzdata.zi)" = '# version 2026c'

# Preserve the upstream runtime, replacing only the rebuilt executable and the
# actual timezone package. All other OS inventory remains visible to scanners.
FROM runtime-base AS application
LABEL org.opencontainers.image.title="Ambicrafted Tempo security rebuild" \
      org.opencontainers.image.version="3.0.3-security.20261020" \
      org.opencontainers.image.source="https://github.com/grafana/tempo" \
      org.opencontainers.image.revision="1900ed7bb5cad1a3edc285783d7d4ac4278337dc" \
      org.opencontainers.image.licenses="AGPL-3.0-only"
COPY --from=build --chmod=0755 /out/tempo /tempo
COPY --from=timezone /runtime/ /
USER 10001:10001
ENTRYPOINT ["/tempo"]

# Shared, build-only trust policy. No helper/toolchain enters the runtime.
FROM golang:1.27.3-bookworm@sha256:972b4110ba0f47539a975c31e52c64765e1ff19f2d74469ae4a595c6676e80a5 AS trust-tools
ADD --checksum=sha256:65efbc80fdc1fa2cd2631cad5b481777a68e8725f34e89f50fc6ac714e379b40 https://go.dev/dl/go1.27.3.linux-amd64.tar.gz /tmp/go.tar.gz
RUN test "$(uname -m)" = x86_64 && rm -rf /usr/local/go && tar -xzf /tmp/go.tar.gz -C /usr/local
ENV GOTOOLCHAIN=local GOTELEMETRY=off CGO_ENABLED=0
WORKDIR /policy
COPY --from=trust-policy distrust.go distrust_test.go distrusted-emsign-g3.crt VerifyTrust.java ./
RUN --network=none go test -count=1 -v distrust.go distrust_test.go \
    && go build -trimpath -buildvcs=false -o /policy/distrust distrust.go

FROM application
USER 0
RUN --network=none --mount=type=bind,from=trust-tools,source=/policy,target=/policy,ro ["/policy/distrust", "-report", "/usr/share/ambicrafted/ca-distrust.json"]
LABEL org.ambicrafted.trust.distrusted-sha256="86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b"
USER 10001:10001
