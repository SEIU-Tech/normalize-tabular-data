# Publishing workflow for normalize-tabular-data: build, check, upload via twine
# (twine is the uploader that honors $HOME/.pypirc; uv publish does not).

.PHONY: test dist check testpypi pypi clean

test:
	uv run pytest

dist:
	uv build
	uv run twine check dist/*

check: dist

upload:  # internal: dist must exist
	uv run twine upload --non-interactive

testpypi: dist
	uv run twine upload --non-interactive --repository testpypi dist/*

pypi: dist
	uv run twine upload --non-interactive dist/*

clean:
	rm -rf dist/
