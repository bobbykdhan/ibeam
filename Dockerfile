FROM python:3.11-slim-bookworm

ENV PATH="/opt/venv/bin:$PATH" \
    JAVA_HOME="/usr/lib/jvm/default-java" \
    USER_ID="1000" \
    GROUP_ID="1000" \
    USER_NAME="basic_user" \
    GROUP_NAME="basic_group" \
    SRC_ROOT="/srv/ibeam" \
    OUTPUTS_DIR="/srv/outputs" \
    IBEAM_GATEWAY_DIR="/srv/clientportal.gw" \
    IBEAM_CHROME_DRIVER_PATH="/usr/bin/chromedriver" \
    PYTHONPATH="${PYTHONPATH}:/srv:/srv/ibeam"

COPY requirements.txt /srv/requirements.txt

RUN \
    # Create python virtual environment and required directories
    python -m venv /opt/venv && \
    mkdir -p /usr/share/man/man1 $OUTPUTS_DIR $IBEAM_GATEWAY_DIR $SRC_ROOT && \
    # Create basic user
    addgroup --gid $GROUP_ID $GROUP_NAME && \
    adduser --disabled-password --gecos "" --uid $USER_ID --gid $GROUP_ID --shell /bin/bash $USER_NAME && \
    # Install apt packages
    apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y default-jre dbus-x11 xfonts-base xfonts-100dpi \
        xfonts-75dpi xfonts-scalable xorg xvfb gtk2-engines-pixbuf nano curl iputils-ping \
        build-essential && \
    # Pin chromium/chromium-driver: 150.0.7871.46 crashed on startup with SIGTRAP
    # (int3;ud2 trap in a stripped Chromium function) regardless of sandbox/seccomp
    # flags. 147.0.7727.137 was pinned as the prior known-good version, but by the
    # time this image is rebuilt that version has usually been superseded and purged
    # from the Debian mirrors, so the exact-version apt install fails (or, on hosts
    # that fell back to an unpinned older image, silently reinstalls whatever
    # version -- including the broken 150.x -- is current at build time). 153.x has
    # been verified to start reliably; keep this pin current and bump it whenever a
    # rebuild is needed rather than letting it go stale.
    DEBIAN_FRONTEND=noninteractive apt-get install -y --allow-downgrades \
        chromium=153.0.8010.52-1~deb12u1 \
        chromium-driver=153.0.8010.52-1~deb12u1 \
        chromium-common=153.0.8010.52-1~deb12u1 && \
    apt-mark hold chromium chromium-driver chromium-common && \
    # Install python packages
    pip install --upgrade pip setuptools wheel && \
    pip install -r /srv/requirements.txt && \
    # Remove packages and package lists
    apt-get purge -y --auto-remove build-essential && \
    rm -rf /var/lib/apt/lists/*

COPY copy_cache/clientportal.gw $IBEAM_GATEWAY_DIR
COPY ibeam $SRC_ROOT

RUN \
    # Create environment activation script
    echo "/opt/venv/bin/activate" >> $SRC_ROOT/activate.sh && \
    # Update file ownership and permissions
    chown -R $USER_NAME:$GROUP_NAME $SRC_ROOT $OUTPUTS_DIR $IBEAM_GATEWAY_DIR && \
    chmod 744 /opt/venv/bin/activate /srv/ibeam/run.sh $SRC_ROOT/activate.sh

WORKDIR $SRC_ROOT

USER $USER_NAME

#CMD python ./ibeam_starter.py
#ENTRYPOINT ["/srv/ibeam/run.sh"]
#ENTRYPOINT ["bash"]
#CMD ["/srv/ibeam/run.sh"]
CMD ["python", "ibeam_starter.py"]