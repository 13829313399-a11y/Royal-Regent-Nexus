ARG BASE_IMAGE
FROM ${BASE_IMAGE}
COPY before.sha256 after.sha256 /usr/local/share/qc-mobile-20261124/
RUN cd /app && sha256sum --strict -c /usr/local/share/qc-mobile-20261124/before.sha256
COPY files/ /app/
RUN cd /app && sha256sum --strict -c /usr/local/share/qc-mobile-20261124/after.sha256
