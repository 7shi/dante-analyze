include ../model.mk

all: cohort rollup

cohort:
	uv run cohort.py inferno purgatorio paradiso -m $(MODEL)

# Code-only region consolidation (no model); safe to re-run any time.
rollup:
	uv run rollup.py inferno purgatorio paradiso

measure:
	uv run measure.py

# Remove the generated cohort cantos and rollups (regenerable by `make`); keeps the .py/README/Makefile.
clean:
	rm -rf inferno purgatorio paradiso inferno.txt purgatorio.txt paradiso.txt

.PHONY: all cohort rollup measure clean
