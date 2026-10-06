# Publishing workflow for normalize-tabular-data: build, check, upload via twine
# (twine is the uploader that honors $HOME/.pypirc; uv publish does not).

VERSION := $(shell grep -m1 '^version = ' pyproject.toml | cut -d'"' -f2)

.PHONY: test dist check testpypi pypi clean

test:
	uv run pytest

dist:
	uv build
	uv run twine check dist/*

check: dist

# Upload only the files of the version declared in pyproject.toml: dist/
# accumulates every artifact ever built here, and re-uploading an already
# published version makes PyPI answer 400 Bad Request
CURRENT_DIST := dist/normalize_tabular_data-$(VERSION)*.whl dist/normalize_tabular_data-$(VERSION).tar.gz

testpypi: dist
	uv run twine upload --non-interactive --repository testpypi $(CURRENT_DIST)

pypi: dist
	uv run twine upload --non-interactive $(CURRENT_DIST)

clean:
	rm -rf dist/
