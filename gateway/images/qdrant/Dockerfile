# The default final target is the qualified shell-free runtime.
# The apt-ui stage is retained only as an explicit comparison/rollback build.
FROM qdrant/qdrant:v1.19.2@sha256:b7b0444c4c351c970b98e90a6f89c2ee4287c65b44e52b4cb503fa5b2aa927ad AS patched

RUN apt-get update \
    && apt-get install --yes --no-install-recommends --only-upgrade \
        ca-certificates=20250419+deb13u1 \
        gzip=1.13-1+deb13u1 \
        libc-bin=2.41-12+deb13u4 \
        libc6=2.41-12+deb13u4 \
        liblzma5=5.8.1-1+deb13u2 \
        libpcre2-8-0=10.46-1~deb13u2 \
        libsqlite3-0=3.46.1-7+deb13u2 \
        perl-base=5.40.1-6+deb13u1 \
    && rm -rf /var/lib/apt/lists/*

# Native x86_64 CPU build, preserving upstream release LTO and stacktrace.
# Build-only toolchain and sources never enter the runtime. Cargo's source
# checksums and a narrow, hash-checked lock patch pin the three security updates.
FROM rust:1.98.1-bookworm@sha256:93ce27a88655056a51dbdd8f5f2d7ddc071c7b0070fb288a37b5a285fc83971e AS server-toolchain
RUN test "$(uname -m)" = x86_64 \
    && apt-get update \
    && apt-get install --yes --no-install-recommends \
        clang=1:14.0-55.7~deb12u1 lld=1:14.0-55.7~deb12u1 \
        cmake=3.25.1-1 protobuf-compiler=3.21.12-3+deb12u1 \
        libprotobuf-dev=3.21.12-3+deb12u1 libunwind-dev=1.6.2-3 \
        pkg-config=1.8.1-1 gcc=4:12.2.0-3 g++=4:12.2.0-3 \
        libc6-dev=2.36-9+deb12u14 \
    && rm -rf /var/lib/apt/lists/*
ADD --checksum=sha256:a3696680d99e692970590a178bc3a33d78d60d1c6dc9db7a11b557b02b751f5d https://github.com/rui314/mold/releases/download/v2.41.0/mold-2.41.0-x86_64-linux.tar.gz /tmp/mold.tar.gz
RUN mkdir -p /opt/mold \
    && tar -xf /tmp/mold.tar.gz --strip-components=1 -C /opt/mold \
    && rm /tmp/mold.tar.gz
ENV PATH="/opt/mold/bin:$PATH" CARGO_BUILD_JOBS=4 CMAKE_BUILD_PARALLEL_LEVEL=4

FROM server-toolchain AS server-sbom-tool
ADD --checksum=sha256:4ffe4b49660f4f4331fb5efcf7074a318b10f5f8fd75e42351a7ca32c58c2723 https://static.crates.io/crates/cargo-sbom/cargo-sbom-0.10.0.crate /tmp/cargo-sbom.crate
RUN mkdir /sbom-tool \
    && tar -xzf /tmp/cargo-sbom.crate --strip-components=1 -C /sbom-tool \
    && cargo fetch --locked --manifest-path /sbom-tool/Cargo.toml
RUN --network=none cargo install --path /sbom-tool --frozen --jobs 2

FROM server-toolchain AS server-build
ADD --checksum=sha256:f6ad6d177a4e5dd5667f95e43d22a54eef8b9e243fcaa507803ed2aa0ff4764b https://codeload.github.com/qdrant/qdrant/tar.gz/016542aa5deb6c66380bb137badf73d54f742bde /tmp/server.tar.gz
WORKDIR /src
COPY server-dependencies.patch /tmp/server-dependencies.patch
RUN tar -xzf /tmp/server.tar.gz --strip-components=1 -C /src \
    && patch --batch --fuzz=0 -p1 < /tmp/server-dependencies.patch \
    && printf '%s  %s\n' 42f9669834dbbc64461147d6aee793b861bbc807d4449fb366c34e7caf47de38 Cargo.lock | sha256sum --check --strict \
    && cargo fetch --locked
ENV RUSTFLAGS="-C link-arg=-fuse-ld=mold -C link-arg=-Wl,--threads=4" \
    GIT_COMMIT_ID=016542aa5deb6c66380bb137badf73d54f742bde
RUN --network=none cargo build --frozen --release --features stacktrace --bin qdrant
COPY --from=server-sbom-tool /usr/local/cargo/bin/cargo-sbom /usr/local/cargo/bin/cargo-sbom
RUN --network=none CARGO_NET_OFFLINE=true cargo sbom > qdrant.spdx.json \
    && printf '%s  %s\n' 42f9669834dbbc64461147d6aee793b861bbc807d4449fb366c34e7caf47de38 Cargo.lock | sha256sum --check --strict \
    && target/release/qdrant --version

FROM node:24.21.0-bookworm@sha256:64af3819f9275802414d7cdc38c27e9d82bd564dec4d4da87d008255d36c63b4 AS web-ui
ADD --checksum=sha256:41bb1ae7fa6e7011e62a0990ab2a90abfd3e44f4d2a0aa076e68c6dc8f39b44f https://codeload.github.com/qdrant/qdrant-web-ui/tar.gz/4a211d6dbbf1a60f0bc7035a49336df166a8dcd8 /tmp/source.tar.gz
WORKDIR /src
RUN tar -xzf /tmp/source.tar.gz --strip-components=1 -C /src \
    && git config --global url.https://github.com/.insteadOf ssh://git@github.com/
COPY web-ui-package.json package.json
COPY web-ui-package-lock.json package-lock.json
COPY web-ui.patch /tmp/web-ui.patch
COPY build-dependencies.check.mjs ./build-dependencies.check.mjs
COPY redirects-security.check.mjs ./redirects-security.check.mjs
ENV VITE_OFFLINE=true
RUN patch --batch --fuzz=0 -p1 < /tmp/web-ui.patch \
    && chown -R node:node /src
# Native watcher quotas are per UID; do not share the host root quota or run
# npm lifecycle scripts as root. The resulting runtime remains UID 65532.
USER node
RUN npm ci --no-fund --no-audit
RUN --network=none node --test build-dependencies.check.mjs redirects-security.check.mjs \
    && npm test -- --run --maxWorkers=2 \
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
    && test "$(dpkg-query -W -f='${Version}' liblzma5)" = 5.8.1-1+deb13u2 \
    && mkdir -p /runtime/var/lib/dpkg/status.d /runtime/qdrant/storage /runtime/qdrant/snapshots \
    && for package in libunwind8 liblzma5; do \
        dpkg-query -L "$package" | while IFS= read -r file; do \
            if test -f "$file" || test -L "$file"; then cp -a --parents "$file" /runtime; fi; \
        done; \
        dpkg-query -s "$package" > "/runtime/var/lib/dpkg/status.d/$package"; \
        cp "/var/lib/dpkg/info/$package:amd64.md5sums" "/runtime/var/lib/dpkg/status.d/$package.md5sums"; \
    done \
    && test "$(dpkg-query -W -f='${Version}' ca-certificates)" = 20250419+deb13u1 \
    && update-ca-certificates --fresh \
    && printf '%s  %s\n' e9c7b63ee2623386e9b0a3ee32f499d01a8ea23dc83b8383ddff9f8e749543b7 /etc/ssl/certs/ca-certificates.crt | sha256sum --check --strict \
    && test "$(find /usr/share/ca-certificates/mozilla -name '*.crt' | wc -l)" = 148 \
    && test ! -e /usr/share/ca-certificates/mozilla/emSign_ECC_Root_CA_-_G3.crt \
    && test ! -e /usr/share/ca-certificates/mozilla/Comodo_AAA_Services_root.crt \
    && cp -a --parents /etc/ssl/certs /etc/ca-certificates.conf \
        /usr/share/ca-certificates /usr/share/doc/ca-certificates /runtime \
    && dpkg-query -s ca-certificates > /runtime/var/lib/dpkg/status.d/ca-certificates \
    && cp /var/lib/dpkg/info/ca-certificates.md5sums /runtime/var/lib/dpkg/status.d/ca-certificates.md5sums \
    && chown 65532:65532 /runtime/qdrant/storage /runtime/qdrant/snapshots
ADD --checksum=sha256:210b508429e913d9de5301f90508bc2cbf5b2281de5b45e607c04d58f0f3bd8f https://raw.githubusercontent.com/qdrant/qdrant/6ab21cac18ebb6f4ae29102c7f8f5cc11affd5de/LICENSE /runtime/usr/share/licenses/qdrant/LICENSE

FROM node:24.21.0-bookworm@sha256:64af3819f9275802414d7cdc38c27e9d82bd564dec4d4da87d008255d36c63b4 AS health-builder
ADD --checksum=sha256:65efbc80fdc1fa2cd2631cad5b481777a68e8725f34e89f50fc6ac714e379b40 https://go.dev/dl/go1.27.3.linux-amd64.tar.gz /tmp/go.tar.gz
RUN test "$(uname -m)" = x86_64 && tar -xzf /tmp/go.tar.gz -C /usr/local
ENV CGO_ENABLED=0 GOOS=linux GOARCH=amd64 GOTOOLCHAIN=local GOMAXPROCS=2
WORKDIR /src
COPY healthcheck.go healthcheck_test.go ./
RUN --network=none /usr/local/go/bin/go test healthcheck.go healthcheck_test.go \
    && /usr/local/go/bin/go build -trimpath -buildvcs=false -o /healthcheck healthcheck.go \
    && /usr/local/go/bin/go version -m /healthcheck

FROM gcr.io/distroless/cc-debian13:nonroot@sha256:e792ab3d241a468a4fd7519ddbbebe66b49b5f365771716ea688ad40b6c6f1c2 AS minimal
# Replace, rather than overlay, the CA package's old anchors and generated links.
# In particular DSA-6572-1 removes both emSign G3 and Comodo AAA. The removal
# tool is mounted for this build step only; no shell or package manager is added.
USER 0
RUN --network=none --mount=type=bind,from=patched,source=/usr/bin/rm,target=/remove,ro ["/remove", "-rf", "/etc/ssl/certs", "/etc/ca-certificates.conf", "/usr/share/ca-certificates", "/usr/share/doc/ca-certificates", "/var/lib/dpkg/status.d/ca-certificates", "/var/lib/dpkg/status.d/ca-certificates.md5sums"]
COPY --from=runtime-libraries /runtime/ /
COPY --from=server-build /src/target/release/qdrant /qdrant/qdrant
COPY --from=server-build /src/qdrant.spdx.json /qdrant/qdrant.spdx.json
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

FROM minimal AS application

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
RUN --network=none --mount=type=bind,from=trust-tools,source=/policy,target=/policy,ro ["/policy/distrust", "--native-prepared", "-report", "/usr/share/ambicrafted/ca-distrust.json"]
LABEL org.ambicrafted.trust.distrusted-sha256="86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b"
LABEL org.ambicrafted.qdrant.source-commit="016542aa5deb6c66380bb137badf73d54f742bde" \
    org.ambicrafted.qdrant.cargo-lock-sha256="42f9669834dbbc64461147d6aee793b861bbc807d4449fb366c34e7caf47de38"
USER 65532:65532
