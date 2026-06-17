include ../model.mk

all:
	uv run cohort.py inferno purgatorio paradiso -m $(MODEL)
	uv run rollup.py inferno purgatorio paradiso

# Code-only region consolidation (no model); safe to re-run any time.
rollup:
	uv run rollup.py inferno purgatorio paradiso

.PHONY: all rollup
