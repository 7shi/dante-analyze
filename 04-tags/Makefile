include ../model.mk

# Full 04-tags identity build, in dependency order: tags -> typing -> coref.
# This is the linear identity chain; 05-registry (registry) reads the artifacts these produce.
# coref's proposals are staged for review before the node tables are rebuilt (`make -C ../05-registry`).
all: tags typing coref

tags:
	uv run tags.py inferno purgatorio paradiso -m $(MODEL)

# Node typing (04-tags/types.txt): closed-vocabulary type for every label, overlay-free.
# It is the LLM step the coreference overlay and the registry both read. It depends only on the
# committed 04-tags labels, so it runs straight after `tags` with nothing from 05-registry.
typing:
	uv run node_types.py inferno purgatorio paradiso -m $(MODEL)

# Coreference overlay (04-tags/coref.txt): per-tag identity corrections for under-specified labels.
# Reads 04-tags/types.txt (the typing cache), so it runs after `typing`.
# Staged for review before the node tables are rebuilt (`make -C ../05-registry`).
coref:
	uv run coreference.py inferno purgatorio paradiso -m $(MODEL)

.PHONY: all tags typing coref
