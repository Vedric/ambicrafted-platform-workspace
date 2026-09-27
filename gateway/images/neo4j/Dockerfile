# Dedicated graph-memory runtime; no APOC downloads or native compilation at runtime.
FROM neo4j:5.26.31-community-trixie@sha256:5eb12ad77fa46ab73e23df9ea1f43f5c0f2a79523435577648e046be042b9b93
USER root
# Header packages are not the running kernel and are unnecessary for this Java service.
# Removing unused build headers also removes their shipped vulnerability inventory.
RUN apt-get purge -y --auto-remove linux-libc-dev wget \
    && rm -rf /var/lib/apt/lists/*
