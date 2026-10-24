FROM golang:1.27.3-bookworm@sha256:972b4110ba0f47539a975c31e52c64765e1ff19f2d74469ae4a595c6676e80a5 AS build
ADD --checksum=sha256:65efbc80fdc1fa2cd2631cad5b481777a68e8725f34e89f50fc6ac714e379b40 https://go.dev/dl/go1.27.3.linux-amd64.tar.gz /tmp/go.tar.gz
RUN test "$(uname -m)" = x86_64 && rm -rf /usr/local/go && tar -xzf /tmp/go.tar.gz -C /usr/local
ENV GOTOOLCHAIN=local GOTELEMETRY=off GOMAXPROCS=4
WORKDIR /src
ADD --checksum=sha256:eee7ec029ffdba7d9ee59171cad5ddaff10e71514b0bae1a6fde6dc1ae99e181 https://codeload.github.com/prometheus/prometheus/tar.gz/5241a27fe3c6983549fccc32f6e65917408c63cd /tmp/source.tar.gz
RUN tar -xzf /tmp/source.tar.gz --strip-components=1 -C /src
# Preserve the official UI release while replacing the vulnerable Go binaries.
ADD --checksum=sha256:fa8c918ed05e3f89e232e9b69eccd6ed074602cd9e8a2cab7a92bec9651974ae https://github.com/prometheus/prometheus/releases/download/v3.15.0/prometheus-web-ui-3.15.0.tar.gz /tmp/ui.tar.gz
RUN tar -xzf /tmp/ui.tar.gz -C /src/web/ui && bash scripts/compress_assets.sh
COPY go.mod go.sum ./
RUN go mod download && go mod verify
RUN --mount=type=cache,target=/root/.cache/go-build go test -mod=readonly -p=4 -race -count=1 -timeout=10m ./config ./rules ./web/api/v1
RUN --network=none --mount=type=cache,target=/root/.cache/go-build CGO_ENABLED=0 go build -mod=readonly -p=4 -trimpath -buildvcs=false -tags netgo,builtinassets \
    -ldflags='-X github.com/prometheus/common/version.Version=3.15.0-security.20261020 -X github.com/prometheus/common/version.Revision=5241a27fe3c6983549fccc32f6e65917408c63cd -X github.com/prometheus/common/version.Branch=security-rebuild' \
    -o /out/ ./cmd/prometheus ./cmd/promtool

FROM prom/prometheus:v3.15.0@sha256:efd719c99d83b060d9daefdcf00360461adf279f45ef5391f8d111892118753e AS application
COPY --from=build --chmod=0755 /out/prometheus /bin/prometheus
COPY --from=build --chmod=0755 /out/promtool /bin/promtool
LABEL org.opencontainers.image.version="3.15.0-security.20261020" \
      org.opencontainers.image.revision="5241a27fe3c6983549fccc32f6e65917408c63cd" \
      org.opencontainers.image.source="https://github.com/prometheus/prometheus"

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
# DSA-6572-1 also removes this exact Comodo AAA root. Preserve all other anchors.
RUN --network=none --mount=type=bind,from=trust-tools,source=/policy,target=/policy,ro ["/policy/distrust", "-fingerprint", "d7a7a0fb5d7e2731d771e9484ebcdef71d5f0c3e0a2948782bc83ee0ea699ef4", "-report", "/usr/share/ambicrafted/ca-distrust-aaa.json"]
LABEL org.ambicrafted.trust.distrusted-sha256="86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b"
USER nobody
