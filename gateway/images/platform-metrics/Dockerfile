FROM golang:1.26.8-bookworm@sha256:a688600ca24f8a4d3ca77f95b0dd40704a9fc787c826660eb7ba0b641b8b175d AS build
ADD --checksum=sha256:65efbc80fdc1fa2cd2631cad5b481777a68e8725f34e89f50fc6ac714e379b40 https://go.dev/dl/go1.27.3.linux-amd64.tar.gz /tmp/go.tar.gz
RUN test "$(uname -m)" = x86_64 && rm -rf /usr/local/go && tar -xzf /tmp/go.tar.gz -C /usr/local
ENV GOTOOLCHAIN=local GOTELEMETRY=off CGO_ENABLED=0 GOMAXPROCS=4
WORKDIR /src
ADD --checksum=sha256:c5603a127be807f9e8e372e06724ede9b77534d363c665eabebbe8d06d7bf858 https://codeload.github.com/prometheus/node_exporter/tar.gz/fc12f2c0ca65e65f046a5583bbcaf996a578afb4 /tmp/source.tar.gz
RUN tar -xzf /tmp/source.tar.gz --strip-components=1 -C /src
COPY go.mod go.sum ./
RUN go mod download && go mod verify
RUN --network=none --mount=type=cache,target=/root/.cache/go-build go test -mod=readonly -p=4 ./collector -run 'TestText|TestMetric' -count=1
RUN --network=none --mount=type=cache,target=/root/.cache/go-build go build -mod=readonly -p=4 -trimpath -buildvcs=false \
    -ldflags='-X github.com/prometheus/common/version.Version=1.12.1-security.20261020 -X github.com/prometheus/common/version.Revision=fc12f2c0ca65e65f046a5583bbcaf996a578afb4' -o /out/node_exporter .
FROM prom/node-exporter:v1.12.1@sha256:1b4e4438faca4dd7e001dd445d161a4a2091b0fededa84093b3a8dfeae1f1be0
COPY --from=build --chmod=0755 /out/node_exporter /bin/node_exporter
LABEL org.opencontainers.image.version="1.12.1-security.20261020" \
      org.opencontainers.image.revision="fc12f2c0ca65e65f046a5583bbcaf996a578afb4" \
      org.opencontainers.image.source="https://github.com/prometheus/node_exporter"
USER 65534:65534
