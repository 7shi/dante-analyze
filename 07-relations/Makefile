include ../model.mk

all:
	uv run relations.py inferno purgatorio paradiso -m $(MODEL)

measure:
	uv run measure.py

.PHONY: all measure
