FROM node:lts-alpine3.23

# Which SillyTavern branch/tag to build. "release" = stable.
ARG ST_REF=release
ARG APP_HOME=/home/node/app

RUN apk add --no-cache gcompat tini git git-lfs jq nginx

WORKDIR ${APP_HOME}
ENV NODE_ENV=production

RUN git clone --depth 1 --branch ${ST_REF} https://github.com/SillyTavern/SillyTavern.git .

RUN npm ci --no-audit --no-fund --loglevel=error --no-progress --omit=dev --ignore-scripts \
 && npm cache clean --force

# Same layout the official image uses
RUN rm -f config.yaml \
 && mkdir -p config data plugins public/scripts/extensions/third-party backups \
 && ln -s ./config/config.yaml config.yaml

RUN node ./docker/build-lib.js

RUN git config --global --add safe.directory "*"

COPY run.sh /run.sh
COPY nginx.conf.tpl /etc/nginx/ingress.conf.tpl
COPY ingress-shim.js /etc/nginx/ingress-shim.js
RUN chmod +x /run.sh \
 && sed -i 's/\r$//' /run.sh /etc/nginx/ingress.conf.tpl /etc/nginx/ingress-shim.js

EXPOSE 8000 8099
ENTRYPOINT ["tini", "--", "/run.sh"]
