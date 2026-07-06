FROM ghcr.io/home-assistant/base:latest

ARG BUILD_ARCH
ARG BUILD_VERSION

RUN apk add --no-cache python3

COPY run.sh /
COPY app /app

RUN chmod a+x /run.sh

LABEL \
    io.hass.name="Load Optimizer" \
    io.hass.description="Learn appliance cycles and optimize their running cost" \
    io.hass.arch="${BUILD_ARCH}" \
    io.hass.type="app" \
    io.hass.version="${BUILD_VERSION}"

CMD ["/run.sh"]
