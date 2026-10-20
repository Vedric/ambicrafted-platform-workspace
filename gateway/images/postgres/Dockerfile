# Rebuild only the existing gosu 1.19 helper with a patched, pinned compiler.
# This derivative is deliberately limited to the validated linux/amd64 host.
FROM postgres:16.15-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea AS gosu-builder

ADD --checksum=sha256:65efbc80fdc1fa2cd2631cad5b481777a68e8725f34e89f50fc6ac714e379b40 https://go.dev/dl/go1.27.3.linux-amd64.tar.gz /tmp/go.tar.gz
ADD --checksum=sha256:33d7537d588ea49458b9509bcf4554bdf5ceacc66da71e5caa1058ea3b689c3b https://codeload.github.com/tianon/gosu/tar.gz/6456aaa0f3c854d199d0f037f068eb97515b7513 /tmp/gosu.tar.gz

RUN test "$(uname -m)" = x86_64 \
    && tar -xzf /tmp/go.tar.gz -C /usr/local \
    && mkdir /src /out \
    && tar -xzf /tmp/gosu.tar.gz --strip-components=1 -C /src

ENV CGO_ENABLED=0 GOOS=linux GOARCH=amd64 GOTOOLCHAIN=local
WORKDIR /src
# Preserve upstream dependency versions and symbol tables for vulnerability
# analysis. Do not use -s, as documented by gosu's official build instructions.
RUN /usr/local/go/bin/go mod download \
    && /usr/local/go/bin/go mod verify \
    && /usr/local/go/bin/go test -mod=readonly ./... \
    && /usr/local/go/bin/go build -mod=readonly -trimpath -buildvcs=false \
        -ldflags='-d -w' -o /out/gosu . \
    && cp -R /src /src-rebuild \
    && cd /src-rebuild \
    && /usr/local/go/bin/go build -mod=readonly -trimpath -buildvcs=false \
        -ldflags='-d -w' -o /out/gosu-rebuilt . \
    && cmp /out/gosu /out/gosu-rebuilt \
    && /usr/local/go/bin/go version -m /out/gosu \
    && /out/gosu --version \
    && test "$(/out/gosu nobody id -u)" = 65534

FROM postgres:16.15-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea AS application
COPY --from=gosu-builder --chmod=0755 /out/gosu /usr/local/bin/gosu

# Shared, build-only trust policy. No helper/toolchain enters the runtime.
FROM golang:1.26.8-bookworm@sha256:a688600ca24f8a4d3ca77f95b0dd40704a9fc787c826660eb7ba0b641b8b175d AS trust-tools
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
USER 0
