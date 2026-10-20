# Narrow patch of the maintained stable line. No application code or database
# migrations are replaced. Build tools and downloaded wheels stay outside runtime.
FROM ghcr.io/berriai/litellm:main-v1.104.4-stable@sha256:a1e651f6e0b78ee40300fbbbce95c9cb8fae121bddd56285d728fc64de2069fa AS wheels
ADD --checksum=sha256:dc14e4f81a99b585a891350c60d1ff4557d54cb3c3c81fa45fd4e0dd512ba752 https://files.pythonhosted.org/packages/37/cc/01e39e1dbeb838a6b3c26bf97c867d6f366459b22a38bea691af8c6c94c0/uv-0.12.5-py3-none-musllinux_1_1_x86_64.whl /tmp/uv.whl
RUN /app/.venv/bin/python -c "import zipfile; zipfile.ZipFile('/tmp/uv.whl').extractall('/patch/tools')" \
    && chmod 0755 /patch/tools/uv-0.12.5.data/scripts/uv
ADD --checksum=sha256:ff4b366510c733974adb7a4102c094e4a6308e6f369315a4cf14d2d0a619cf82 https://files.pythonhosted.org/packages/69/c0/70667e82ec041f4122a17afce711bbcf94a71bec5888b69a49aed8817be2/aiohttp-3.14.4-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl /patch/aiohttp-3.14.4-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl
ADD --checksum=sha256:be80550d9bfe83d9b62398a37081a90434e6df2d978ec345c3d2820de6beddab https://files.pythonhosted.org/packages/0e/b7/a82a49bf88340b837ef6972b508a1604ae377b9e6904b46b10cf5f1cf925/yarl-1.25.1-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl /patch/yarl-1.25.1-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl
COPY requirements.txt /patch/requirements.txt

FROM ghcr.io/berriai/litellm:main-v1.104.4-stable@sha256:a1e651f6e0b78ee40300fbbbce95c9cb8fae121bddd56285d728fc64de2069fa
RUN --network=none --mount=type=bind,from=wheels,source=/patch,target=/patch,ro \
    /patch/tools/uv-0.12.5.data/scripts/uv pip install --python /app/.venv/bin/python --no-cache --no-index --find-links /patch \
      --require-hashes --no-deps -r /patch/requirements.txt \
    && /app/.venv/bin/python -c "import aiohttp, yarl, litellm; assert aiohttp.__version__ == '3.14.4'; assert yarl.__version__ == '1.25.1'"
LABEL org.opencontainers.image.version="1.104.4-stable-security.20261020" \
      org.opencontainers.image.source="https://github.com/BerriAI/litellm"
