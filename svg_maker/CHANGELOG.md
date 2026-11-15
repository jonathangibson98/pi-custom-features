# Changelog

## 1.0.3 - 2026-11-14

- Fixed the image build failing with "Failed building wheel for vtracer". The base image is now pinned to Python 3.12 (a released version with prebuilt tracer wheels) instead of the 3.15 pre-release, and the build only accepts a prebuilt tracer wheel so it can't fall into a Rust compile.
- The add-on page link now really points at this repository.

## 1.0.1 - 2026-11-13

- Now published as a prebuilt image (`ghcr.io/jonathangibson98/{arch}-addon-svg_maker`), so it installs without building on the Pi.
- The add-on page link now points at this repository.

## 1.0.0 - 2026-11-05

SVG Maker is now its own add-on, split out of Creator & AI Builder, where it failed to convert photos.

- Runs on a Debian (glibc) base instead of Alpine, which fixes the tracer crash ("killed by signal 11") seen in the combined add-on
- Tracer gets a larger stack and, if it still crashes, the conversion is retried automatically at smaller sizes before an error is shown
- The install build runs a tracer test, and the add-on logs a tracer self-test at every start
- Same crop editor, auto-crop, auto-enhance, color / black and white tracing, naming, Save locally / Download / Both, and the same `svg_*` options and defaults as before
