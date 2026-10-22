# Narrow patch of the maintained stable line. No application code or database
# migrations are replaced. Build tools and downloaded wheels stay outside runtime.
FROM ghcr.io/berriai/litellm:main-v1.104.4-stable@sha256:a1e651f6e0b78ee40300fbbbce95c9cb8fae121bddd56285d728fc64de2069fa AS wheels
ADD --checksum=sha256:52b5c753a7c2d5f8323a70bb4c93118988356331d0758afa6446c81f974e7196 https://files.pythonhosted.org/packages/1e/ec/f352ca2cc3b4b6191bb4ec8cdf4bc190eed0ba8bda4c33b7fd66c5d33cec/uv-0.13.4-py3-none-musllinux_1_1_x86_64.whl /tmp/uv.whl
RUN /app/.venv/bin/python -c "import zipfile; zipfile.ZipFile('/tmp/uv.whl').extractall('/patch/tools')" \
    && chmod 0755 /patch/tools/uv-0.13.4.data/scripts/uv
ADD --checksum=sha256:ff4b366510c733974adb7a4102c094e4a6308e6f369315a4cf14d2d0a619cf82 https://files.pythonhosted.org/packages/69/c0/70667e82ec041f4122a17afce711bbcf94a71bec5888b69a49aed8817be2/aiohttp-3.14.4-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl /patch/aiohttp-3.14.4-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl
ADD --checksum=sha256:be80550d9bfe83d9b62398a37081a90434e6df2d978ec345c3d2820de6beddab https://files.pythonhosted.org/packages/0e/b7/a82a49bf88340b837ef6972b508a1604ae377b9e6904b46b10cf5f1cf925/yarl-1.25.1-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl /patch/yarl-1.25.1-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl
ADD --checksum=sha256:42d35340cc5b9ba78e818ddbff0c5b1c2b779de448a340fd1b989f5fa8670e1b https://files.pythonhosted.org/packages/c4/51/29046e48f693c54e5b7412216d447a1d8362c9653148d98c02cdf65fa733/certifi-2026.10.19-py3-none-any.whl /patch/certifi-2026.10.19-py3-none-any.whl
ADD --checksum=sha256:553e2d42f5bb3bb2a785a7d3de8ef90bb7df74b5413eff5a7b4388007ea9254b https://files.pythonhosted.org/packages/85/e6/24c944e473c34e818cf1b98085796fcd780465ecfe17663f2bf8fee1958b/pypdf-6.21.1-py3-none-any.whl /patch/pypdf-6.21.1-py3-none-any.whl
COPY requirements.txt /patch/requirements.txt
COPY verify_certifi.py /patch/verify_certifi.py
COPY verify_system_trust.py /patch/verify_system_trust.py

FROM ghcr.io/berriai/litellm:main-v1.104.4-stable@sha256:a1e651f6e0b78ee40300fbbbce95c9cb8fae121bddd56285d728fc64de2069fa AS application
RUN --network=none --mount=type=bind,from=wheels,source=/patch,target=/patch,ro \
    /patch/tools/uv-0.13.4.data/scripts/uv pip install --python /app/.venv/bin/python --no-cache --no-index --find-links /patch \
      --require-hashes --no-deps -r /patch/requirements.txt \
    && /app/.venv/bin/python -c "import aiohttp, yarl, litellm, pypdf; assert aiohttp.__version__ == '3.14.4'; assert yarl.__version__ == '1.25.1'; assert pypdf.__version__ == '6.21.1'" \
    && /app/.venv/bin/python /patch/verify_certifi.py
LABEL org.opencontainers.image.version="1.104.4-stable-security.20261022.1" \
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

FROM application
USER 0
# Adopt Wolfi's signed package correction for CVE-2026-111943. APK validates
# the repository index and package checksum; no untrusted-package mode is used.
RUN --mount=type=bind,from=wheels,source=/patch,target=/patch,ro \
    apk add --no-cache --repositories-file /dev/null --repository https://packages.wolfi.dev/os \
      --upgrade ca-certificates-bundle=20260909-r3 \
    && /app/.venv/bin/python /patch/verify_system_trust.py
# The independently verified native bundle already excludes G3. The shared
# check still refuses an invalid/empty store or any remaining G3 anchor.
RUN --network=none --mount=type=bind,from=trust-tools,source=/policy,target=/policy,ro ["/policy/distrust", "--native-prepared", "-report", "/usr/share/ambicrafted/ca-distrust.json"]
LABEL org.ambicrafted.trust.distrusted-sha256="86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b"
USER 0
