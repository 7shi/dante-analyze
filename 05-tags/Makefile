include ../model.mk

all:
	uv run tags.py inferno purgatorio paradiso -m $(MODEL)

verify:
	uv run verify_tags.py inferno purgatorio paradiso

fix:
	uv run verify_tags.py inferno purgatorio paradiso --fix

.PHONY: all verify fix
