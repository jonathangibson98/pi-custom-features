# Debian (glibc) base on purpose. The tracer (vtracer) is a Rust library, and its crash on the
# Alpine (musl) base used by the combined add-on is why SVG Maker was split out.
FROM python:3.15-slim-bookworm

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install aiohttp pillow vtracer

# Fail the build (not the first conversion) if the tracer cannot run on this machine.
RUN python -c "from PIL import Image; import vtracer; Image.new('RGB',(96,96),(200,30,30)).save('/tmp/t.png'); vtracer.convert_image_to_svg_py('/tmp/t.png','/tmp/t.svg'); print('vtracer build check OK')" \
 && rm -f /tmp/t.png /tmp/t.svg

WORKDIR /app
COPY server.py svg_tool.py /app/
COPY www /app/www

CMD ["python3", "-u", "/app/server.py"]
