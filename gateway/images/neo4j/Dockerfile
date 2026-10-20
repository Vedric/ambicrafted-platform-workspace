# Dedicated graph-memory profile, not a general-purpose bulk-import distribution.
# Vendor-maintained UBI10 runtime and upstream Java/authentication/bootstrap remain intact.
FROM neo4j:5.26.32-community-ubi10@sha256:e94e5440ea760e2f96457fa90224c26771d4d0c5cd65bf9e1da6aa812db2f776 AS application
USER root
# Parquet bulk import is outside this platform's bounded Cypher/JSON memory contract.
# Its shaded Jackson 2.22.2 has no released Parquet fix at qualification time.
# Remove the unused feature's actual JARs, never package metadata or scanner evidence.
# Do not replace shaded classes by hand: that would break the upstream artifact contract.
RUN set -eu; \
    for artifact in \
      parquet-column-1.18.1 \
      parquet-encoding-1.18.1 \
      parquet-floor-1.62 \
      parquet-jackson-1.18.1 \
      parquet-hadoop-1.18.1 \
      parquet-format-structures-1.18.1 \
      parquet-common-1.18.1; do \
        test -f "/var/lib/neo4j/lib/${artifact}.jar"; \
        rm "/var/lib/neo4j/lib/${artifact}.jar"; \
    done

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
# Keep the vendor's native p11-kit/OpenSSL/Java trust generation semantics.
RUN --network=none --mount=type=bind,from=trust-tools,source=/policy,target=/policy,ro \
    java /policy/VerifyTrust.java before /tmp/java-ca-before /policy/distrusted-emsign-g3.crt \
    && cp /policy/distrusted-emsign-g3.crt /etc/pki/ca-trust/source/blocklist/ambicrafted-emsign-g3.crt \
    && update-ca-trust extract \
    && mkdir -p /usr/share/ambicrafted \
    && java /policy/VerifyTrust.java after /tmp/java-ca-before /policy/distrusted-emsign-g3.crt > /usr/share/ambicrafted/ca-distrust-java.json \
    && rm /tmp/java-ca-before
LABEL org.ambicrafted.trust.distrusted-sha256="86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b"
USER root
