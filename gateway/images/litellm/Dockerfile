# Narrow patch of the maintained stable line. No application code or database
# migrations are replaced. Build tools and downloaded wheels stay outside runtime.
FROM ghcr.io/berriai/litellm:main-v1.104.4-stable@sha256:a1e651f6e0b78ee40300fbbbce95c9cb8fae121bddd56285d728fc64de2069fa AS wheels
ADD --checksum=sha256:52b5c753a7c2d5f8323a70bb4c93118988356331d0758afa6446c81f974e7196 https://files.pythonhosted.org/packages/1e/ec/f352ca2cc3b4b6191bb4ec8cdf4bc190eed0ba8bda4c33b7fd66c5d33cec/uv-0.13.4-py3-none-musllinux_1_1_x86_64.whl /tmp/uv.whl
RUN /app/.venv/bin/python -c "import zipfile; zipfile.ZipFile('/tmp/uv.whl').extractall('/patch/tools')" \
    && chmod 0755 /patch/tools/uv-0.13.4.data/scripts/uv
ADD --checksum=sha256:ff4b366510c733974adb7a4102c094e4a6308e6f369315a4cf14d2d0a619cf82 https://files.pythonhosted.org/packages/69/c0/70667e82ec041f4122a17afce711bbcf94a71bec5888b69a49aed8817be2/aiohttp-3.14.4-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl /patch/aiohttp-3.14.4-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl
ADD --checksum=sha256:be80550d9bfe83d9b62398a37081a90434e6df2d978ec345c3d2820de6beddab https://files.pythonhosted.org/packages/0e/b7/a82a49bf88340b837ef6972b508a1604ae377b9e6904b46b10cf5f1cf925/yarl-1.25.1-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl /patch/yarl-1.25.1-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl
ADD --checksum=sha256:42d35340cc5b9ba78e818ddbff0c5b1c2b779de448a340fd1b989f5fa8670e1b https://files.pythonhosted.org/packages/c4/51/29046e48f693c54e5b7412216d447a1d8362c9653148d98c02cdf65fa733/certifi-2026.10.19-py3-none-any.whl /patch/certifi-2026.10.19-py3-none-any.whl
ADD --checksum=sha256:1d44d1a3a200f25062adff0085b02040e4646431ac2ccac22e42679e91466084 https://files.pythonhosted.org/packages/1b/4d/c9d2d67f204eff463237a1a8f5e25a6923b7b1043982b91fcaf104c8ef60/pypdf-6.21.2-py3-none-any.whl /patch/pypdf-6.21.2-py3-none-any.whl
ADD --checksum=sha256:301241438c57936ef93f4243a94f2559022268bfcf9b375a9a72eb0f8db8358e https://files.pythonhosted.org/packages/e0/1b/5e74289a1878e666bb4b65fe5805a04cafcac2aa5f519ef1ead67ef91c56/filelock-4.2.4-py3-none-any.whl /patch/filelock-4.2.4-py3-none-any.whl
COPY requirements.txt /patch/requirements.txt
COPY verify_certifi.py /patch/verify_certifi.py
COPY verify_system_trust.py /patch/verify_system_trust.py
COPY backport_otel.py test_otel_backport.py test_otel_vendor.py /patch/
COPY qualify_filelock.py test_filelock_contract.py /patch/
# Full unchanged tests from the retained 1.33.1 package's source commit.
ADD --checksum=sha256:e1e496f64ee57fda76a19d6735c315fb9d699d38b640cb1d110f2d0f354b3044 https://raw.githubusercontent.com/open-telemetry/opentelemetry-python/acae2c232b101d3e447a82a7161355d66aa06fa2/opentelemetry-api/tests/trace/test_tracestate.py /patch/vendor-tests/test_tracestate_baseline.py
ADD --checksum=sha256:2ea08044b7e50128abc1f73045f3d66a55945f21558bfa1c3e9b9aae8756bd92 https://raw.githubusercontent.com/open-telemetry/opentelemetry-python/acae2c232b101d3e447a82a7161355d66aa06fa2/opentelemetry-api/tests/trace/propagation/test_tracecontexthttptextformat.py /patch/vendor-tests/test_tracecontext_baseline.py
# Unmodified Apache-2.0 vendor tests from the exact security fix commit.
ADD --checksum=sha256:ab4e4a0cc130260240b1e0314eca15f5c73764d28aae0a3099a2553220824e56 https://raw.githubusercontent.com/open-telemetry/opentelemetry-python/d5224bf4ffdf2aee1b592ad238dcc32ca957f26b/opentelemetry-api/tests/trace/test_tracestate.py /patch/vendor-tests/test_tracestate_upstream.py
ADD --checksum=sha256:d6302a2b59352c4793e04a46511b1d2e729d7193599745d2d0976e7bec227753 https://raw.githubusercontent.com/open-telemetry/opentelemetry-python/d5224bf4ffdf2aee1b592ad238dcc32ca957f26b/opentelemetry-api/tests/trace/propagation/test_tracecontexthttptextformat.py /patch/vendor-tests/test_tracecontext_upstream.py
ADD --checksum=sha256:c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4 https://raw.githubusercontent.com/open-telemetry/opentelemetry-python/d5224bf4ffdf2aee1b592ad238dcc32ca957f26b/LICENSE /patch/vendor-tests/LICENSE

FROM ghcr.io/berriai/litellm:main-v1.104.4-stable@sha256:a1e651f6e0b78ee40300fbbbce95c9cb8fae121bddd56285d728fc64de2069fa AS application
# Bundled metadata makes offline imports deterministic; reviewed image updates
# or explicit configured model prices refresh estimates. See ADR 0057.
ENV LITELLM_LOCAL_MODEL_COST_MAP=True
RUN --network=none --mount=type=bind,from=wheels,source=/patch,target=/patch,ro \
    /patch/tools/uv-0.13.4.data/scripts/uv pip install --python /app/.venv/bin/python --no-cache --no-index --find-links /patch \
      --require-hashes --no-deps -r /patch/requirements.txt \
    && /app/.venv/bin/python -c "import aiohttp, yarl, litellm, pypdf; assert aiohttp.__version__ == '3.14.4'; assert yarl.__version__ == '1.25.1'; assert pypdf.__version__ == '6.21.2'" \
    && /app/.venv/bin/python /patch/verify_certifi.py
# Preserve the pinned API/SDK cohort. Apply the bounded upstream parser fix
# with exact input/output hashes; package version and raw advisory stay honest.
RUN --network=none --mount=type=bind,from=wheels,source=/patch,target=/patch,ro \
    PYTHONDONTWRITEBYTECODE=1 /app/.venv/bin/python /patch/test_otel_backport.py --preflight \
    && PYTHONDONTWRITEBYTECODE=1 /app/.venv/bin/python /patch/backport_otel.py \
    && PYTHONDONTWRITEBYTECODE=1 /app/.venv/bin/python /patch/test_otel_vendor.py \
    && PYTHONDONTWRITEBYTECODE=1 /app/.venv/bin/python /patch/test_otel_backport.py --qualified
# The upstream <4 bound predates the only corrected filelock release line.
# Qualify the unchanged real consumers before declaring an exact local contract.
RUN --network=none --mount=type=bind,from=wheels,source=/patch,target=/patch,ro \
    PYTHONDONTWRITEBYTECODE=1 /app/.venv/bin/python /patch/test_filelock_contract.py --preflight \
    && PYTHONDONTWRITEBYTECODE=1 /app/.venv/bin/python /patch/qualify_filelock.py \
    && PYTHONDONTWRITEBYTECODE=1 /app/.venv/bin/python /patch/test_filelock_contract.py --qualified \
    && /patch/tools/uv-0.13.4.data/scripts/uv pip check --python /app/.venv/bin/python
LABEL org.opencontainers.image.version="1.104.4-stable-security.20261024.2" \
      org.opencontainers.image.source="https://github.com/BerriAI/litellm"

# Shared, build-only trust policy. No helper/toolchain enters the runtime.
FROM golang:1.26.8-bookworm@sha256:a688600ca24f8a4d3ca77f95b0dd40704a9fc787c826660eb7ba0b641b8b175d AS trust-tools
ADD --checksum=sha256:65efbc80fdc1fa2cd2631cad5b481777a68e8725f34e89f50fc6ac714e379b40 https://go.dev/dl/go1.27.3.linux-amd64.tar.gz /tmp/go.tar.gz
RUN test "$(uname -m)" = x86_64 && rm -rf /usr/local/go && tar -xzf /tmp/go.tar.gz -C /usr/local
ENV GOTOOLCHAIN=local GOTELEMETRY=off CGO_ENABLED=0
WORKDIR /policy
COPY --from=trust-policy distrust.go distrust_test.go distrusted-emsign-g3.crt VerifyTrust.java ./
RUN --network=none go test -count=1 -v distrust.go distrust_test.go \
    && go build -trimpath -buildvcs=false -o /policy/distrust distrust.go

# Wolfi authenticates these packages through its signed index. APK verifies
# that signature with the base image keys and matches each package checksum.
# APK bytes are additionally SHA-256 pinned; installation has no network.
FROM scratch AS os-packages
ADD https://packages.wolfi.dev/os/x86_64/APKINDEX.tar.gz /packages/x86_64/APKINDEX.tar.gz
ADD --checksum=sha256:e38603061dbeea4a647b2d46d454c954e8af89a495f9b2c07b51b590995a7da0 https://packages.wolfi.dev/os/x86_64/glibc-2.44-2.44-r8.apk /packages/x86_64/glibc-2.44-2.44-r8.apk
ADD --checksum=sha256:fb171f1e6f2ab314b5964e5b1ba5dbabf42ace912744e02c206f7d4bff32b284 https://packages.wolfi.dev/os/x86_64/glibc-2.44-locale-posix-2.44-r8.apk /packages/x86_64/glibc-2.44-locale-posix-2.44-r8.apk
ADD --checksum=sha256:e0c7e3b457c86a7d672a339a166ee13959356ac8a5b19ab4af5a771fee6c699f https://packages.wolfi.dev/os/x86_64/ld-linux-2.44-2.44-r8.apk /packages/x86_64/ld-linux-2.44-2.44-r8.apk
ADD --checksum=sha256:553ebdf51c301926dcb62e43396a550a5bfa8f7f5ce0544d59efc91356149695 https://packages.wolfi.dev/os/x86_64/libcrypt1-2.44-2.44-r8.apk /packages/x86_64/libcrypt1-2.44-2.44-r8.apk

ADD --checksum=sha256:33227d8494e635d6e38407e3f7229eeced413827bc89ca7681c1d92f1079977f https://packages.wolfi.dev/os/x86_64/libbrotlicommon1-1.2.0-r7.apk /packages/x86_64/libbrotlicommon1-1.2.0-r7.apk

ADD --checksum=sha256:072073b20da38ee5bced85a653f0f991319b183f6c70c1e053239e591d3aebfa https://packages.wolfi.dev/os/x86_64/libbrotlidec1-1.2.0-r7.apk /packages/x86_64/libbrotlidec1-1.2.0-r7.apk

ADD --checksum=sha256:60a271af5f45f4de7cf075ed1f8edc810f81e701b3b998094e3bad67919beeb1 https://packages.wolfi.dev/os/x86_64/libbrotlienc1-1.2.0-r7.apk /packages/x86_64/libbrotlienc1-1.2.0-r7.apk

FROM application
USER 0
# Adopt Wolfi's signed package correction for CVE-2026-111943. APK validates
# the repository index and package checksum; no untrusted-package mode is used.
RUN --mount=type=bind,from=wheels,source=/patch,target=/patch,ro \
    apk add --no-cache --repositories-file /dev/null --repository https://packages.wolfi.dev/os \
      --upgrade ca-certificates-bundle=20260909-r3 \
    && /app/.venv/bin/python /patch/verify_system_trust.py
RUN --network=none --mount=type=bind,from=os-packages,source=/packages,target=/packages,ro \
    apk add --no-network --no-cache --repositories-file /dev/null --repository /packages \
      --upgrade glibc-2.44=2.44-r8 glibc-2.44-locale-posix=2.44-r8 \
      ld-linux-2.44=2.44-r8 libcrypt1-2.44=2.44-r8 \
      libbrotlicommon1=1.2.0-r7 libbrotlidec1=1.2.0-r7 libbrotlienc1=1.2.0-r7
# The independently verified native bundle already excludes G3. The shared
# check still refuses an invalid/empty store or any remaining G3 anchor.
RUN --network=none --mount=type=bind,from=trust-tools,source=/policy,target=/policy,ro ["/policy/distrust", "--native-prepared", "-report", "/usr/share/ambicrafted/ca-distrust.json"]
LABEL org.ambicrafted.trust.distrusted-sha256="86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b"
USER 0
