FROM ghcr.io/home-assistant/base-debian:bookworm

ARG PJSIP_VERSION=2.14.1

RUN set -ex \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-dev \
        python3-pip \
        build-essential \
        swig \
        wget \
        ca-certificates \
        pkg-config \
        libopus-dev \
    && cd /tmp \
    && wget -q "https://github.com/pjsip/pjproject/archive/refs/tags/${PJSIP_VERSION}.tar.gz" -O pjproject.tar.gz \
    && tar xzf pjproject.tar.gz \
    && cd "pjproject-${PJSIP_VERSION}" \
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
    && make dep \
    && make -j"$(nproc)" \
    && make install \
    && ldconfig \
    && pip3 install --break-system-packages --no-cache-dir setuptools \
    && cd pjsip-apps/src/swig/python \
    && make \
    && pip3 install --break-system-packages --no-cache-dir . \
    && apt-get install -y --no-install-recommends libopus0 \
    && apt-get purge -y --auto-remove build-essential swig wget ca-certificates pkg-config libopus-dev python3-dev \
    && rm -rf /var/lib/apt/lists/* /tmp/*

COPY shim.py /app/shim.py
COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD [ "/run.sh" ]
