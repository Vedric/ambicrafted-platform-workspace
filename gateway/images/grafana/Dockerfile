# Official signed plugin archives are updated as whole directories.
# Never rebuild or edit files covered by their MANIFEST signatures.
FROM grafana/grafana:13.2.2@sha256:ac461fb352abc50da10a51c7d02462e9c05488f11f53f14b3ad79a8145f638a0 AS plugins
USER root
ADD --checksum=sha256:d4380ee6a82f1e284e517bc78826c6ede6a34c0a60d3c147f37e80d3c7038cdb ["https://grafana.com/api/plugins/grafana-pyroscope-datasource/versions/13.0.6/download?os=linux&arch=amd64", "/archives/grafana-pyroscope-datasource.zip"]
ADD --checksum=sha256:5fbe65a810453d7edc40e968fb3e19f1114d17d82401c4806727eee5b2f7f612 ["https://grafana.com/api/plugins/opentsdb/versions/13.0.4/download?os=linux&arch=amd64", "/archives/opentsdb.zip"]
ADD --checksum=sha256:dd982c4b0e2466e0051a8001071c1ecc68c394a7eb31e2b1ad6dfff689c3ad72 ["https://grafana.com/api/plugins/prometheus/versions/13.2.1/download?os=linux&arch=amd64", "/archives/prometheus.zip"]
ADD --checksum=sha256:4792fb5705567b03dc0089db1bd688fbc541f9b8bb47e40488b7b6a32a19bf5a ["https://grafana.com/api/plugins/stackdriver/versions/12.6.2/download?os=linux&arch=amd64", "/archives/stackdriver.zip"]
ADD --checksum=sha256:36d53fdc7d0900b38f89e3e6da0babb7da99a2351caad6d19b736edda6deee8c ["https://grafana.com/api/plugins/tempo/versions/13.2.2/download?os=linux&arch=amd64", "/archives/tempo.zip"]
ADD --checksum=sha256:43dec3b7d37b26654b92de11cfe16916d918e9f67a7affaea9aa09a62ddc50be ["https://grafana.com/api/plugins/zipkin/versions/12.4.8/download?os=linux&arch=amd64", "/archives/zipkin.zip"]
ADD --checksum=sha256:d34f44bd13213502de4394955fcc170d70fb822531c181bff0179f216c35a0e0 ["https://grafana.com/api/plugins/grafana-postgresql-datasource/versions/13.0.4/download?os=linux&arch=amd64", "/archives/grafana-postgresql-datasource.zip"]
ADD --checksum=sha256:ebf559b2a3d2375efe7959568a132c16ebe1fe7c55bfaf2ce7643693d6b0bceb ["https://grafana.com/api/plugins/influxdb/versions/13.1.6/download?os=linux&arch=amd64", "/archives/influxdb.zip"]
ADD --checksum=sha256:2a2458a646e735715a47bddc02a0dbb86a0c88412bc7851f3fd7de212b0a7c14 ["https://grafana.com/api/plugins/jaeger/versions/13.0.4/download?os=linux&arch=amd64", "/archives/jaeger.zip"]
RUN test "$(uname -m)" = x86_64 && mkdir /prepared && unzip -q /archives/grafana-pyroscope-datasource.zip -d /prepared && unzip -q /archives/opentsdb.zip -d /prepared && unzip -q /archives/prometheus.zip -d /prepared && unzip -q /archives/stackdriver.zip -d /prepared && unzip -q /archives/tempo.zip -d /prepared && unzip -q /archives/zipkin.zip -d /prepared && unzip -q /archives/grafana-postgresql-datasource.zip -d /prepared && unzip -q /archives/influxdb.zip -d /prepared && unzip -q /archives/jaeger.zip -d /prepared

FROM grafana/grafana:13.2.2@sha256:ac461fb352abc50da10a51c7d02462e9c05488f11f53f14b3ad79a8145f638a0
USER root
RUN apk add --no-cache --upgrade libcrypto3=3.5.8-r0 libssl3=3.5.8-r0
RUN rm -rf /usr/share/grafana/data/plugins-bundled/grafana-pyroscope-datasource /usr/share/grafana/data/plugins-bundled/opentsdb /usr/share/grafana/data/plugins-bundled/prometheus /usr/share/grafana/data/plugins-bundled/stackdriver /usr/share/grafana/data/plugins-bundled/tempo /usr/share/grafana/data/plugins-bundled/zipkin /usr/share/grafana/data/plugins-bundled/grafana-postgresql-datasource /usr/share/grafana/data/plugins-bundled/influxdb /usr/share/grafana/data/plugins-bundled/jaeger
COPY --from=plugins --chown=472:0 /prepared/ /usr/share/grafana/data/plugins-bundled/
COPY plugins-provenance.json /usr/share/grafana/ambicrafted/plugins-provenance.json
USER 472
