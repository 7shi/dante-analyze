include ../model.mk

all:
	uv run tags.py inferno purgatorio paradiso -m $(MODEL)

# Coreference overlay (04-tags/coref.txt): per-tag identity corrections for under-specified labels.
# NOT part of `all` — it reads 05-registry/types.txt (the typing cache), so it can only run AFTER a
# first registry build. The full build order lives in 05-registry/Makefile's `all`
# (registry -> this -> registry). Staged for review before the node tables are rebuilt.
coref:
	uv run coreference.py inferno purgatorio paradiso -m $(MODEL)

.PHONY: all coref
