FROM ubuntu:22.04

ARG DEBIAN_FRONTEND=noninteractive

ARG ACCELERGY_REF
ARG PLUGIN_REF
ARG MCPAT_REF

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        g++-multilib \
        gcc-multilib \
        git \
        libc6-dev-i386 \
        make \
        python3 \
        python3-pip \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/energy-venv

ENV PATH="/opt/energy-venv/bin:/usr/local/bin:${PATH}"
ENV PYTHONUNBUFFERED=1

WORKDIR /opt/src

RUN test -n "${MCPAT_REF}" \
    && git clone \
        https://github.com/HewlettPackard/mcpat.git \
        /opt/src/mcpat \
    && cd /opt/src/mcpat \
    && git checkout "${MCPAT_REF}" \
    && make -j2 \
    && install -m 0755 \
        /opt/src/mcpat/mcpat \
        /usr/local/bin/mcpat

RUN test -n "${ACCELERGY_REF}" \
    && git clone \
        https://github.com/Accelergy-Project/accelergy.git \
        /opt/src/accelergy \
    && cd /opt/src/accelergy \
    && git checkout "${ACCELERGY_REF}" \
    && pip install \
        --no-cache-dir \
        --upgrade \
        pip \
        setuptools \
        wheel \
    && pip install \
        --no-cache-dir \
        .

RUN test -n "${PLUGIN_REF}" \
    && git clone \
        https://github.com/Accelergy-Project/accelergy-mcpat-plug-in.git \
        /opt/src/accelergy-mcpat-plug-in \
    && cd /opt/src/accelergy-mcpat-plug-in \
    && git checkout "${PLUGIN_REF}" \
    && pip install \
        --no-cache-dir \
        .

RUN test -x /usr/local/bin/mcpat \
    && command -v accelergy \
    && python -c \
        "import accelergy; print('Accelergy import: OK')" \
    && accelergy -h > /tmp/accelergy-help.txt

COPY run-accelergy.sh /usr/local/bin/chia-accelergy

RUN chmod 0755 /usr/local/bin/chia-accelergy \
    && /bin/sh -n /usr/local/bin/chia-accelergy

LABEL org.chia.toolchain="accelergy-mcpat"
LABEL org.chia.accelergy.commit="${ACCELERGY_REF}"
LABEL org.chia.accelergy-mcpat-plugin.commit="${PLUGIN_REF}"
LABEL org.chia.mcpat.commit="${MCPAT_REF}"
LABEL org.chia.runtime-wrapper="ephemeral-unprivileged-v1"

WORKDIR /work

CMD ["bash"]
