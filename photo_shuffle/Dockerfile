# Debian (glibc) Python base on purpose: SVG Maker's tracer (vtracer) is a Rust library that crashes on
# Alpine (musl), and it only ships prebuilt wheels for released Python versions.
FROM python:3.15-slim-bookworm

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install --only-binary=vtracer flask requests paho-mqtt pillow pillow-heif aiohttp vtracer

# Fail the build (not the first conversion) if the tracer can't run on this machine.
RUN python -c "from PIL import Image; import vtracer, pillow_heif; pillow_heif.register_heif_opener(); Image.new('RGB',(96,96),(200,30,30)).save('/tmp/t.png'); vtracer.convert_image_to_svg_py('/tmp/t.png','/tmp/t.svg'); print('vtracer build check OK')" \
 && rm -f /tmp/t.png /tmp/t.svg

WORKDIR /app
COPY main.py index.html addon_backup.py /app/
COPY svg /app/svg

CMD ["python3", "-u", "/app/main.py"]
