# Central version constant for Server Protocol Bridge.
#
# This file intentionally holds ONLY the version string: every other piece of
# version / identity logic lives in ``proxy/version.py``, which imports
# ``VERSION`` from here so the release number has a single source of truth.
#
# Bump this constant (and the matching numbers in android/app/build.gradle and
# web/api/version.json) for every release.

VERSION = '2.6'
