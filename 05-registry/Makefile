include ../model.mk

# Full build, end to end: node tables + typing cache, then the coreference overlay (which reads
# types.txt and is owned by 04-tags), then the node tables re-rendered WITH that overlay applied.
# This is the linear DAG
#   registry (build #1 -> types.txt) -> 04-tags coref (-> 04-tags/coref.txt) -> registry (build #2)
# NOTE: `all` applies coref's per-scene proposals WITHOUT the human-review gate. For a reviewed
# pass, run the steps individually: `make -C ../04-tags coref`, inspect 04-tags/coref.txt, then
# `make registry`.
all:
	$(MAKE) registry
	$(MAKE) -C ../04-tags coref
	$(MAKE) registry

# Node tables (05-registry/<canticle>.txt) + typing cache (types.txt). Pure code given a warm
# types.txt; calls the model only for not-yet-typed nodes. Applies whatever 04-tags/coref.txt holds.
registry:
	uv run registry.py inferno purgatorio paradiso -m $(MODEL)

measure:
	uv run measure.py

.PHONY: all registry measure
