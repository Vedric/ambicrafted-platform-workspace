# The backend is rebuilt from the exact upstream source with two pinned module
# updates. Signed plugin files are replaced only by complete official archives.
FROM golang:1.27.3-alpine3.23@sha256:895e5feab11a4b3774d24ee3c9579028456b82ad37f42a9eb6f82adaf776a201 AS backend
ENV GOTOOLCHAIN=local CGO_ENABLED=0 GOMAXPROCS=4
ADD --checksum=sha256:60eed311bdf954198742a2a73f86d305c10a71f7a932b3e4f94ceaf566989ee3 https://github.com/grafana/grafana/archive/af4a33e3786594ad72f72d97e6744010330c2977.tar.gz /tmp/grafana-source.tar.gz
RUN mkdir /src && tar -xzf /tmp/grafana-source.tar.gz --strip-components=1 -C /src
WORKDIR /src
RUN --mount=type=cache,target=/go/pkg/mod \
    go get github.com/getkin/kin-openapi@v0.149.0 \
    && printf '6b5fe768dd60007f7dbb7b30a28b3c4ad0596cd179e747edd27275db325fd219  go.mod\n9df9d3bc91c69dbea45632447c4d88190f5e8a18ee7a768be585dfa1780dd2b2  go.sum\n' | sha256sum -c -
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    go test -short -p 4 ./apps/alerting/rules/pkg/app/validation github.com/getkin/kin-openapi/openapi3 github.com/getkin/kin-openapi/openapi3filter \
    && go build -p 4 -tags oss -trimpath -buildvcs=false \
       -ldflags '-s -w -X main.version=13.2.4+ambicrafted.20261020 -X main.commit=af4a33e3786594ad72f72d97e6744010330c2977 -X main.buildBranch=security-20261020 -X main.buildstamp=1791891415' \
       -o /out/grafana ./pkg/cmd/grafana

FROM grafana/grafana:13.2.4@sha256:dbbc38ea21103cefb50396340cd88afec779c7e070b0a7bf5a75b4ce46651d3f AS plugins
USER root
ADD --checksum=sha256:ae51e0a76901de07860777f5b992fe3924206181f4c99287a9d840710682bf24 ["https://grafana.com/api/plugins/opentsdb/versions/13.0.5/download?os=linux&arch=amd64", "/archives/opentsdb.zip"]
ADD --checksum=sha256:3288d1bb06330449e7335346667ea7c74e5367c0d32390396c93ee54c89900cb ["https://grafana.com/api/plugins/stackdriver/versions/12.6.3/download?os=linux&arch=amd64", "/archives/stackdriver.zip"]
RUN test "$(uname -m)" = x86_64 && mkdir /prepared \
    && unzip -q /archives/opentsdb.zip -d /prepared \
    && unzip -q /archives/stackdriver.zip -d /prepared

FROM grafana/grafana:13.2.4@sha256:dbbc38ea21103cefb50396340cd88afec779c7e070b0a7bf5a75b4ce46651d3f
USER root
RUN rm -rf /usr/share/grafana/data/plugins-bundled/opentsdb /usr/share/grafana/data/plugins-bundled/stackdriver
COPY --from=plugins --chown=472:0 /prepared/ /usr/share/grafana/data/plugins-bundled/
COPY --from=backend --chown=472:0 /out/grafana /usr/share/grafana/bin/grafana
COPY plugins-provenance.json core-provenance.json core-dependencies.patch /usr/share/grafana/ambicrafted/
USER 472
