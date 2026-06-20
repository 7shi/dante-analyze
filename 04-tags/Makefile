include ../model.mk

all:
	uv run tags.py inferno purgatorio paradiso -m $(MODEL)

# Node typing (04-tags/types.txt): closed-vocabulary type for every label, overlay-free. NOT part of
# `all` — it is the LLM step the coreference overlay and the registry both read, run on its own timing.
# It depends only on the committed 04-tags labels, so it runs straight after `all` with nothing from
# 05-registry. The linear identity chain is: tags (all) -> typing -> coref -> 05-registry (registry).
typing:
	uv run node_types.py inferno purgatorio paradiso -m $(MODEL)

# Coreference overlay (04-tags/coref.txt): per-tag identity corrections for under-specified labels.
# NOT part of `all` — it reads 04-tags/types.txt (the typing cache), so run `make typing` first.
# Staged for review before the node tables are rebuilt (`make -C ../05-registry`).
coref:
	uv run coreference.py inferno purgatorio paradiso -m $(MODEL)

.PHONY: all typing coref
