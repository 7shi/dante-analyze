include ../model.mk

all: cohort rollup

cohort:
	uv run cohort.py inferno purgatorio paradiso -m $(MODEL)

# Code-only region consolidation (no model); safe to re-run any time.
rollup:
	uv run rollup.py inferno purgatorio paradiso

measure:
	uv run measure.py

.PHONY: all cohort rollup measure
