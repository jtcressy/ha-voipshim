FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.source="https://github.com/zacs/ha-voipshim"
LABEL org.opencontainers.image.description="UniFi Talk to Home Assistant VOIP bridge"

ARG PJSIP_VERSION=2.14.1

# Build PJSIP with Python bindings in a single layer, then clean up.
RUN set -ex \
    # ── build tools ──
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        swig \
        wget \
        ca-certificates \
        pkg-config \
        libopus-dev \
    # ── download PJSIP ──
    && cd /tmp \
    && wget -q "https://github.com/pjsip/pjproject/archive/refs/tags/${PJSIP_VERSION}.tar.gz" \
         -O pjproject.tar.gz \
    && tar xzf pjproject.tar.gz \
    && cd "pjproject-${PJSIP_VERSION}" \
    # ── configure: shared libs, no video, no unneeded codecs ──
    && ./configure \
        --enable-shared \
        --disable-video \
        --disable-v4l2 \
        --disable-opencore-amr \
        --disable-silk \
        --disable-bcg729 \
        --disable-libyuv \
        --disable-libwebrtc \
        --prefix=/usr/local \
    # ── build + install ──
    && make dep \
    && make -j"$(nproc)" \
    && make install \
    && ldconfig \
    # ── Python SWIG bindings ──
    && pip install --no-cache-dir setuptools \
    && cd pjsip-apps/src/swig/python \
    && make \
    && pip install --no-cache-dir . \
    # ── clean up build artifacts ──
    && cd / && rm -rf /tmp/* \
    && apt-get install -y --no-install-recommends libopus0 \
    && apt-get purge -y --auto-remove \
        build-essential swig wget ca-certificates pkg-config libopus-dev \
    && rm -rf /var/lib/apt/lists/*

COPY voipshim-addon/shim.py /app/shim.py
WORKDIR /app

HEALTHCHECK --interval=60s --timeout=5s --start-period=30s --retries=3 \
    CMD [ -f /tmp/voipshim-healthy ] || exit 1

CMD ["python", "-u", "shim.py"]
