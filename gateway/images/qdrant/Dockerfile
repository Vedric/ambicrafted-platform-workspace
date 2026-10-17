# The default final target is the qualified shell-free runtime.
# The apt-ui stage is retained only as an explicit comparison/rollback build.
FROM qdrant/qdrant:v1.19.1@sha256:12364fe851b9f17356fc88189fc06d1b521262e04659ec7345975b00c9246a10 AS patched

RUN apt-get update \
    && apt-get install --yes --no-install-recommends --only-upgrade \
        gzip=1.13-1+deb13u1 \
        libc-bin=2.41-12+deb13u4 \
        libc6=2.41-12+deb13u4 \
        libpcre2-8-0=10.46-1~deb13u2 \
        libsqlite3-0=3.46.1-7+deb13u2 \
        perl-base=5.40.1-6+deb13u1 \
    && rm -rf /var/lib/apt/lists/*

FROM node:26.12.0-bookworm@sha256:a856ae5e25d498bbe5ec85fde88f00f5ed99908fda803ba39d7735ab8574f58c AS web-ui
ADD --checksum=sha256:41bb1ae7fa6e7011e62a0990ab2a90abfd3e44f4d2a0aa076e68c6dc8f39b44f https://codeload.github.com/qdrant/qdrant-web-ui/tar.gz/4a211d6dbbf1a60f0bc7035a49336df166a8dcd8 /tmp/source.tar.gz
WORKDIR /src
RUN tar -xzf /tmp/source.tar.gz --strip-components=1 -C /src \
    && git config --global url.https://github.com/.insteadOf ssh://git@github.com/
COPY web-ui-package.json package.json
COPY web-ui-package-lock.json package-lock.json
COPY web-ui.patch /tmp/web-ui.patch
ENV VITE_OFFLINE=true
RUN patch --batch --fuzz=0 -p1 < /tmp/web-ui.patch \
    && npm ci --no-fund --no-audit
RUN --network=none npm test -- --run --maxWorkers=2 \
    && npm run build-qdrant \
    && npm sbom --sbom-format spdx > dist/qdrant-web-ui.spdx.json

FROM patched AS apt-ui
# Replace the complete compiled dashboard and regenerate its complete build SBOM.
# Never edit dependency versions in an SBOM without rebuilding those artifacts.
RUN rm -rf /qdrant/static
COPY --from=web-ui /src/dist /qdrant/static
COPY --from=web-ui /src/LICENSE /usr/share/licenses/qdrant-web-ui/LICENSE

FROM patched AS runtime-libraries
# Copy the two required native packages with their real dpkg status, checksums
# and copyright files. The distroless base supplies the matching Debian libc.
RUN test "$(dpkg --print-architecture)" = amd64 \
    && test "$(dpkg-query -W -f='${Version}' libunwind8)" = 1.8.1-0.1 \
    && test "$(dpkg-query -W -f='${Version}' liblzma5)" = 5.8.1-1+deb13u1 \
    && mkdir -p /runtime/var/lib/dpkg/status.d /runtime/qdrant/storage /runtime/qdrant/snapshots \
    && for package in libunwind8 liblzma5; do \
        dpkg-query -L "$package" | while IFS= read -r file; do \
            if test -f "$file" || test -L "$file"; then cp -a --parents "$file" /runtime; fi; \
        done; \
        dpkg-query -s "$package" > "/runtime/var/lib/dpkg/status.d/$package"; \
        cp "/var/lib/dpkg/info/$package:amd64.md5sums" "/runtime/var/lib/dpkg/status.d/$package.md5sums"; \
    done \
    && chown 65532:65532 /runtime/qdrant/storage /runtime/qdrant/snapshots
ADD --checksum=sha256:210b508429e913d9de5301f90508bc2cbf5b2281de5b45e607c04d58f0f3bd8f https://raw.githubusercontent.com/qdrant/qdrant/6ab21cac18ebb6f4ae29102c7f8f5cc11affd5de/LICENSE /runtime/usr/share/licenses/qdrant/LICENSE

FROM node:26.12.0-bookworm@sha256:a856ae5e25d498bbe5ec85fde88f00f5ed99908fda803ba39d7735ab8574f58c AS health-builder
ADD --checksum=sha256:63d339f0da5ab53635a56f2490a7984dfe12dfcff22ad749f63edaf590168445 https://go.dev/dl/go1.27.1.linux-amd64.tar.gz /tmp/go.tar.gz
RUN test "$(uname -m)" = x86_64 && tar -xzf /tmp/go.tar.gz -C /usr/local
ENV CGO_ENABLED=0 GOOS=linux GOARCH=amd64 GOTOOLCHAIN=local GOMAXPROCS=2
WORKDIR /src
COPY healthcheck.go healthcheck_test.go ./
RUN --network=none /usr/local/go/bin/go test healthcheck.go healthcheck_test.go \
    && /usr/local/go/bin/go build -trimpath -buildvcs=false -o /healthcheck healthcheck.go \
    && /usr/local/go/bin/go version -m /healthcheck

FROM gcr.io/distroless/cc-debian13:nonroot@sha256:54df941ed0d06a1bd95ef5e0ce391fd8d9f94b64782dc9a60062727849ee3f97 AS minimal
COPY --from=runtime-libraries /runtime/ /
COPY --from=patched /qdrant/qdrant /qdrant/qdrant
COPY --from=patched /qdrant/qdrant.spdx.json /qdrant/qdrant.spdx.json
COPY --from=patched /qdrant/config /qdrant/config
COPY --from=web-ui /src/dist /qdrant/static
COPY --from=web-ui /src/LICENSE /usr/share/licenses/qdrant-web-ui/LICENSE
COPY --from=health-builder /healthcheck /qdrant/healthcheck
USER 65532:65532
WORKDIR /qdrant
ENV TZ=Etc/UTC RUN_MODE=production \
    QDRANT__TELEMETRY_DISABLED=true \
    QDRANT_INIT_FILE_PATH=/qdrant/storage/.qdrant-initialized
EXPOSE 6333 6334
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 CMD ["/qdrant/healthcheck"]
ENTRYPOINT ["/qdrant/qdrant"]

FROM minimal AS final
