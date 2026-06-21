include ../model.mk

all: relations

relations:
	uv run relations.py inferno purgatorio paradiso -m $(MODEL)

measure:
	uv run measure.py

.PHONY: all relations measure
