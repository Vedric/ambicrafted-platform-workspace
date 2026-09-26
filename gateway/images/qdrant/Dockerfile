# Rebuild from the immutable, integration-tested upstream application image.
FROM qdrant/qdrant:v1.19.1@sha256:12364fe851b9f17356fc88189fc06d1b521262e04659ec7345975b00c9246a10

# Debian's signed repository carries the backport for the three reported Perl
# critical advisories. Keep the package version explicit and fail if absent.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends --only-upgrade \
        perl-base=5.40.1-6+deb13u1 \
    && rm -rf /var/lib/apt/lists/*
