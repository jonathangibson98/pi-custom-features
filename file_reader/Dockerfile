FROM python:3.11-alpine

WORKDIR /usr/src/app

# jq parses the Home Assistant options.json
RUN apk add --no-cache jq

RUN pip install --no-cache-dir flask "paho-mqtt>=2.0,<3" requests

COPY app /usr/src/app/app
COPY CHANGELOG.md /usr/src/app/CHANGELOG.md
COPY backup.py /usr/src/app/backup.py
COPY run.sh /run.sh

RUN chmod +x /run.sh

CMD [ "/run.sh" ]
