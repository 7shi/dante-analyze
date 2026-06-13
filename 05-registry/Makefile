include ../model.mk

all:
	uv run registry.py inferno purgatorio paradiso -m $(MODEL)

measure:
	uv run measure.py

.PHONY: all measure
