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

# Align the complete installed JLine module family with its security release.
# Official Maven Central artifacts, SHA-512 checked during qualification, SHA-256
# pinned here. jline-native and Jansi are the declared runtime dependencies.
ADD --checksum=sha256:f72f2ce167765b18a7604370963c1413b5bec923a97576b745fbce40a7034fbf https://repo.maven.apache.org/maven2/org/jline/jline-reader/3.30.15/jline-reader-3.30.15.jar /var/lib/neo4j/lib/jline-reader-3.30.15.jar
ADD --checksum=sha256:eed027d1f63a870c8d0522c067959382ad7d3ccddfd8c7041488432189e0e284 https://repo.maven.apache.org/maven2/org/jline/jline-terminal/3.30.15/jline-terminal-3.30.15.jar /var/lib/neo4j/lib/jline-terminal-3.30.15.jar
ADD --checksum=sha256:de0a419b6b5aaa6029c0546c7bf79e4ab326f0b9d749283687294b8506dcf545 https://repo.maven.apache.org/maven2/org/jline/jline-terminal-jansi/3.30.15/jline-terminal-jansi-3.30.15.jar /var/lib/neo4j/lib/jline-terminal-jansi-3.30.15.jar
ADD --checksum=sha256:076f95383993e5241d63704aef06a7d6a1e5233e762cf2b1130b663cfd9f39e4 https://repo.maven.apache.org/maven2/org/jline/jline-native/3.30.15/jline-native-3.30.15.jar /var/lib/neo4j/lib/jline-native-3.30.15.jar
ADD --checksum=sha256:ec168cf31c4c3849348dfff7a04e90170615f7784f1255ee6747b98a854c04c5 https://repo.maven.apache.org/maven2/org/fusesource/jansi/jansi/2.4.3/jansi-2.4.3.jar /var/lib/neo4j/lib/jansi-2.4.3.jar
RUN --network=none --mount=type=bind,source=VerifyJline.java,target=/tmp/VerifyJline.java,ro \
    set -eu; \
    for module in jline-reader jline-terminal jline-terminal-jansi; do \
      test -f "/var/lib/neo4j/lib/${module}-3.21.0.jar"; \
      rm "/var/lib/neo4j/lib/${module}-3.21.0.jar"; \
    done; \
    test -f /var/lib/neo4j/lib/jansi-2.4.0.jar; \
    rm /var/lib/neo4j/lib/jansi-2.4.0.jar; \
    chmod 0644 /var/lib/neo4j/lib/jline-*-3.30.15.jar /var/lib/neo4j/lib/jansi-2.4.3.jar; \
    java -cp '/var/lib/neo4j/lib/*' /tmp/VerifyJline.java

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
