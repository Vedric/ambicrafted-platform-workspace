# Dedicated graph-memory profile, not a general-purpose bulk-import distribution.
# Vendor-maintained UBI10 runtime and upstream Java/authentication/bootstrap remain intact.
FROM neo4j:5.26.32-community-ubi10@sha256:e94e5440ea760e2f96457fa90224c26771d4d0c5cd65bf9e1da6aa812db2f776
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
