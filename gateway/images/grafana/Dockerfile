# The private distribution uses two rebuilt, offline-signed data sources.
# No signing key enters this context. Rebuilding different bytes fails closed.
FROM node:24.21.0-bookworm@sha256:64af3819f9275802414d7cdc38c27e9d82bd564dec4d4da87d008255d36c63b4 AS plugin-builder
ADD --checksum=sha256:65efbc80fdc1fa2cd2631cad5b481777a68e8725f34e89f50fc6ac714e379b40 https://go.dev/dl/go1.27.3.linux-amd64.tar.gz /tmp/go.tar.gz
RUN tar -C /usr/local -xzf /tmp/go.tar.gz && rm /tmp/go.tar.gz
ENV PATH=/usr/local/go/bin:$PATH GOPATH=/go GOTOOLCHAIN=local GOTELEMETRY=off GOMAXPROCS=4
COPY prepare_plugins.py plugin-build-inputs.json distribution-manifests.json /inputs/
COPY test_prepare_plugins.py /inputs/
RUN --network=none python3 -m unittest discover -s /inputs -p 'test_prepare_plugins.py' -v

FROM plugin-builder AS prometheus-build
ADD --checksum=sha256:24b1f2ed395438a5574102b166314be621259431fbae3f04ae66b55a143f1c13 https://codeload.github.com/grafana/grafana-prometheus-datasource/tar.gz/6d21418acde6ce31c9f7a6418a88758842a881bb /tmp/source.tar.gz
ADD --checksum=sha256:8bdd6583e398f84d497dabec0287563b9eee471d711dea08a21482db5cd5a294 ["https://grafana.com/api/plugins/prometheus/versions/13.2.3/download?os=linux&arch=amd64", "/tmp/official.zip"]
RUN mkdir /src && tar -xzf /tmp/source.tar.gz --strip-components=1 -C /src
WORKDIR /src
COPY prometheus/go.mod prometheus/go.sum prometheus/SecurityMagefile.go ./
COPY prometheus/promlib/go.mod prometheus/promlib/go.sum ./pkg/promlib/
RUN python3 -c 'import json; p="package.json"; d=json.load(open(p)); d["version"]="13.2.3+ambicrafted.20261020"; open(p,"w").write(json.dumps(d,indent=2)+"\n")'
RUN --mount=type=cache,target=/go/pkg/mod go mod download && cd pkg/promlib && go mod download
RUN --network=none --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    go test -race -p 4 -mod=readonly ./pkg/... \
    && (cd pkg/promlib && go test -race -p 4 -mod=readonly ./...) \
    && go run -mod=readonly github.com/magefile/mage SecurityLinux
RUN python3 /inputs/prepare_plugins.py bundle prometheus /inputs/plugin-build-inputs.json /src /tmp/official.zip /prepared/prometheus
FROM prometheus-build AS prometheus
COPY prometheus/MANIFEST.txt /prepared/prometheus/MANIFEST.txt
RUN python3 /inputs/prepare_plugins.py verify /prepared/prometheus /inputs/distribution-manifests.json

FROM plugin-builder AS tempo-build
ADD --checksum=sha256:fdef6e02f81297dc9c26cd13c735fba011e31fa90bc08a6b231489251016238f https://codeload.github.com/grafana/grafana-tempo-datasource/tar.gz/cdacb742bae90fbf62c48c5cca0eacdc08fd2acd /tmp/source.tar.gz
ADD --checksum=sha256:a89fa4ee83a61e58dac30eae3ce42ae6f677545d05e419b88f0a6f5f6cfdf8e7 ["https://grafana.com/api/plugins/tempo/versions/13.2.4/download?os=linux&arch=amd64", "/tmp/official.zip"]
ADD --checksum=sha256:a5489d155031677121f8e715791012bc96f1ecacf5b4bcaaee6eb6a902560156 https://codeload.github.com/grafana/tempo/tar.gz/77fc4563d1135d0ca2656709c7384c278a9c67b0 /tmp/contract.tar.gz
RUN mkdir /src && tar -xzf /tmp/source.tar.gz --strip-components=1 -C /src
WORKDIR /src
COPY tempo/protobuf-imports.patch tempo/protobuf-source-inventory.json /inputs/
RUN python3 /inputs/prepare_plugins.py contract /tmp/contract.tar.gz /inputs/protobuf-source-inventory.json /src \
    && patch -p1 < /inputs/protobuf-imports.patch
COPY tempo/go.mod tempo/go.sum tempo/SecurityMagefile.go ./
RUN python3 -c 'import json; p="package.json"; d=json.load(open(p)); d["version"]="13.2.4+ambicrafted.20261020"; open(p,"w").write(json.dumps(d,indent=2)+"\n")'
RUN --mount=type=cache,target=/go/pkg/mod go mod download
RUN --network=none --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    go test -race -p 4 -mod=readonly ./pkg/... ./internal/tempopb/... \
    && go run -mod=readonly github.com/magefile/mage SecurityLinux \
    && go list -mod=readonly -deps ./pkg > /tmp/package-closure.txt \
    && ! grep '^github.com/grafana/tempo/' /tmp/package-closure.txt
RUN python3 /inputs/prepare_plugins.py bundle tempo /inputs/plugin-build-inputs.json /src /tmp/official.zip /prepared/tempo
FROM tempo-build AS tempo
COPY tempo/MANIFEST.txt /prepared/tempo/MANIFEST.txt
RUN python3 /inputs/prepare_plugins.py verify /prepared/tempo /inputs/distribution-manifests.json

FROM golang:1.27.3-alpine3.23@sha256:895e5feab11a4b3774d24ee3c9579028456b82ad37f42a9eb6f82adaf776a201 AS backend
ENV GOTOOLCHAIN=local CGO_ENABLED=0 GOMAXPROCS=4 GOTELEMETRY=off
ADD --checksum=sha256:60eed311bdf954198742a2a73f86d305c10a71f7a932b3e4f94ceaf566989ee3 https://github.com/grafana/grafana/archive/af4a33e3786594ad72f72d97e6744010330c2977.tar.gz /tmp/grafana-source.tar.gz
RUN mkdir /src && tar -xzf /tmp/grafana-source.tar.gz --strip-components=1 -C /src
WORKDIR /src
RUN --mount=type=cache,target=/go/pkg/mod \
    go get github.com/getkin/kin-openapi@v0.149.0 \
    && printf '6b5fe768dd60007f7dbb7b30a28b3c4ad0596cd179e747edd27275db325fd219  go.mod\n9df9d3bc91c69dbea45632447c4d88190f5e8a18ee7a768be585dfa1780dd2b2  go.sum\n' | sha256sum -c -
COPY distribution-signature.patch /tmp/distribution-signature.patch
RUN apk add --no-cache patch=2.8-r0 && patch --batch --fuzz=0 -p1 < /tmp/distribution-signature.patch
COPY distribution_signature.go distribution_signature_test.go distribution-public.asc distribution-manifests.json ./pkg/plugins/manager/signature/
COPY prometheus/MANIFEST.txt ./pkg/plugins/manager/signature/distribution-prometheus.txt
COPY tempo/MANIFEST.txt ./pkg/plugins/manager/signature/distribution-tempo.txt
COPY --from=prometheus /prepared/prometheus /distribution/prometheus
COPY --from=tempo /prepared/tempo /distribution/tempo
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    GRAFANA_DISTRIBUTION_TEST_PLUGINS=/distribution go test -short -p 4 ./pkg/plugins/manager/signature/... ./pkg/plugins/manager/loader/... \
    && go test -short -p 4 ./apps/alerting/rules/pkg/app/validation github.com/getkin/kin-openapi/openapi3 github.com/getkin/kin-openapi/openapi3filter \
    && go build -p 4 -tags oss -trimpath -buildvcs=false \
       -ldflags '-s -w -X main.version=13.2.4+ambicrafted.20261020.r2 -X main.commit=af4a33e3786594ad72f72d97e6744010330c2977 -X main.buildBranch=security-20261020 -X main.buildstamp=1792490400' \
       -o /out/grafana ./pkg/cmd/grafana \
    && go list -deps -tags oss ./pkg/cmd/grafana > /out/grafana-packages.txt \
    && ! grep '^golang.org/x/crypto/openpgp' /out/grafana-packages.txt

FROM grafana/grafana:13.2.4@sha256:dbbc38ea21103cefb50396340cd88afec779c7e070b0a7bf5a75b4ce46651d3f AS application
USER root
RUN apk add --no-cache --upgrade zlib=1.3.2-r1
# External bundled data sources only; built-in panels remain untouched.
RUN rm -rf /usr/share/grafana/data/plugins-bundled && mkdir /usr/share/grafana/data/plugins-bundled
COPY --from=backend --chown=472:0 /distribution/ /usr/share/grafana/data/plugins-bundled/
COPY --from=backend --chown=472:0 /out/grafana /usr/share/grafana/bin/grafana
COPY --from=backend /out/grafana-packages.txt /usr/share/grafana/ambicrafted/grafana-packages.txt
COPY plugins-provenance.json core-provenance.json core-dependencies.patch distribution-signature.patch distribution_signature.go distribution-public.asc distribution-manifests.json /usr/share/grafana/ambicrafted/
ENV GF_PLUGINS_PREINSTALL_DISABLED=true GF_PLUGINS_PREINSTALL_AUTO_UPDATE=false
USER 472

# Shared, build-only trust policy. No helper/toolchain enters the runtime.
FROM golang:1.26.8-bookworm@sha256:a688600ca24f8a4d3ca77f95b0dd40704a9fc787c826660eb7ba0b641b8b175d AS trust-tools
ADD --checksum=sha256:65efbc80fdc1fa2cd2631cad5b481777a68e8725f34e89f50fc6ac714e379b40 https://go.dev/dl/go1.27.3.linux-amd64.tar.gz /tmp/go.tar.gz
RUN test "$(uname -m)" = x86_64 && rm -rf /usr/local/go && tar -xzf /tmp/go.tar.gz -C /usr/local
ENV GOTOOLCHAIN=local GOTELEMETRY=off CGO_ENABLED=0
WORKDIR /policy
COPY --from=trust-policy distrust.go distrust_test.go distrusted-emsign-g3.crt VerifyTrust.java ./
RUN --network=none go test -count=1 -v distrust.go distrust_test.go \
    && go build -trimpath -buildvcs=false -o /policy/distrust distrust.go

# Alpine's signed musl correction; no backend/plugin bytes are rebuilt here.
FROM scratch AS os-packages
ADD --checksum=sha256:e142255d0fa397f14318996bc10378093dcc069dc3dd1b6818c8f28a789c21da https://dl-cdn.alpinelinux.org/alpine/v3.24/main/x86_64/musl-1.2.6-r3.apk /packages/musl.apk
ADD --checksum=sha256:47263d05842c5e12d01e0369e5b5bea51733323501c00ca21968a5102de137ca https://dl-cdn.alpinelinux.org/alpine/v3.24/main/x86_64/musl-utils-1.2.6-r3.apk /packages/musl-utils.apk

FROM application
USER 0
RUN --network=none --mount=type=bind,from=os-packages,source=/packages,target=/packages,ro \
    apk verify /packages/*.apk \
    && apk add --no-network --no-cache --repositories-file /dev/null /packages/*.apk
RUN --network=none --mount=type=bind,from=trust-tools,source=/policy,target=/policy,ro ["/policy/distrust", "-report", "/usr/share/ambicrafted/ca-distrust.json"]
LABEL org.ambicrafted.trust.distrusted-sha256="86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b"
LABEL org.opencontainers.image.version="13.2.4-security.20261022.2"
USER 472
