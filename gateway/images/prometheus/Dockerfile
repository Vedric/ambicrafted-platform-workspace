FROM golang:1.26.8-bookworm@sha256:a688600ca24f8a4d3ca77f95b0dd40704a9fc787c826660eb7ba0b641b8b175d AS build
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

FROM prom/prometheus:v3.15.0@sha256:efd719c99d83b060d9daefdcf00360461adf279f45ef5391f8d111892118753e
COPY --from=build --chmod=0755 /out/prometheus /bin/prometheus
COPY --from=build --chmod=0755 /out/promtool /bin/promtool
LABEL org.opencontainers.image.version="3.15.0-security.20261020" \
      org.opencontainers.image.revision="5241a27fe3c6983549fccc32f6e65917408c63cd" \
      org.opencontainers.image.source="https://github.com/prometheus/prometheus"
