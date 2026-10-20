FROM golang:1.27.2-bookworm@sha256:5cf287a799e6b94384bad13d16b14904c531f51ba65792237e122ce42b392f61 AS source
ADD --checksum=sha256:65efbc80fdc1fa2cd2631cad5b481777a68e8725f34e89f50fc6ac714e379b40 https://go.dev/dl/go1.27.3.linux-amd64.tar.gz /tmp/go.tar.gz
RUN test "$(uname -m)" = x86_64 && rm -rf /usr/local/go && tar -xzf /tmp/go.tar.gz -C /usr/local
WORKDIR /src
ENV GOTOOLCHAIN=local GOTELEMETRY=off GOMAXPROCS=4
ADD --checksum=sha256:f10ae5ecaa7f1eade220b9d013ae73961227b51a7602694896675df1cb96e8e7 https://codeload.github.com/grafana/tempo/tar.gz/1900ed7bb5cad1a3edc285783d7d4ac4278337dc /tmp/source.tar.gz
RUN tar -xzf /tmp/source.tar.gz --strip-components=1 -C /src && rm /tmp/source.tar.gz
COPY go.mod go.sum ./
RUN go mod download && go mod verify

FROM source AS checked
# Check real upstream startup/configuration and OTLP receiver contracts.
# The build network namespace has eth0 for ring tests; localhost is isolated
# from host services. Tests use local fixtures, no production state or customer data.
RUN --mount=type=cache,target=/root/.cache/go-build go test -mod=readonly -p=4 -race -count=1 -timeout=10m -json ./cmd/tempo/... ./modules/distributor/receiver/... > /tmp/tempo-tests.json \
    || { cat /tmp/tempo-tests.json; exit 1; }

FROM checked AS build
RUN --network=none --mount=type=cache,target=/root/.cache/go-build CGO_ENABLED=0 GOAMD64=v2 go build -mod=readonly -p=4 -trimpath \
    -ldflags='-s -w -X main.Version=3.0.3-security.20261020 -X main.Revision=1900ed7bb5cad1a3edc285783d7d4ac4278337dc -X main.Branch=security-rebuild' \
    -o /out/tempo ./cmd/tempo

# Preserve the immutable upstream runtime and its package metadata. Only the
# embedded Go executable changes; OS findings must remain visible to scanners.
FROM grafana/tempo:3.0.3@sha256:0296560ac66f8a3600d7fb3014a52c189d4d9c3549ad6ff441bf2409855d68d5
LABEL org.opencontainers.image.title="Ambicrafted Tempo security rebuild" \
      org.opencontainers.image.version="3.0.3-security.20261020" \
      org.opencontainers.image.source="https://github.com/grafana/tempo" \
      org.opencontainers.image.revision="1900ed7bb5cad1a3edc285783d7d4ac4278337dc" \
      org.opencontainers.image.licenses="AGPL-3.0-only"
COPY --from=build --chmod=0755 /out/tempo /tempo
USER 10001:10001
ENTRYPOINT ["/tempo"]
