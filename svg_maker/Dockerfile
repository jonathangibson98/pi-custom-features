# Debian (glibc) base on purpose. The tracer (vtracer) is a Rust library, and its crash on the
# Alpine (musl) base used by the combined add-on is why SVG Maker was split out.
#
# Pinned to a released Python on purpose: vtracer ships prebuilt wheels only for released
# Python versions. On a pre-release such as 3.15, pip falls back to compiling vtracer from
# source with maturin, which needs a Rust toolchain and fails ("Failed building wheel for vtracer").
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

# Only accept a prebuilt vtracer wheel, so a missing wheel fails fast with a clear message
# instead of a long Rust compile that cannot succeed here.
RUN pip install --only-binary=vtracer aiohttp pillow vtracer

# Fail the build (not the first conversion) if the tracer cannot run on this machine.
RUN python -c "from PIL import Image; import vtracer; Image.new('RGB',(96,96),(200,30,30)).save('/tmp/t.png'); vtracer.convert_image_to_svg_py('/tmp/t.png','/tmp/t.svg'); print('vtracer build check OK')" \
 && rm -f /tmp/t.png /tmp/t.svg

WORKDIR /app
COPY server.py svg_tool.py ai_logo.py addon_backup.py /app/
COPY www /app/www

CMD ["python3", "-u", "/app/server.py"]
