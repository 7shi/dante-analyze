include ../model.mk

# Full build, end to end: node tables + typing cache, then the coreference overlay (which reads
# types.txt), then the node tables re-rendered WITH that overlay applied. This is the linear DAG
#   registry (build #1 -> types.txt) -> coref (-> 04-tags/coref.txt) -> registry (build #2, apply)
# NOTE: `all` applies coref's per-scene proposals WITHOUT the human-review gate. For a reviewed
# pass, run the steps individually: `make coref`, inspect 04-tags/coref.txt, then `make registry`.
all:
	$(MAKE) registry
	$(MAKE) coref
	$(MAKE) registry

# Node tables (05-registry/<canticle>.txt) + typing cache (types.txt). Pure code given a warm
# types.txt; calls the model only for not-yet-typed nodes. Applies whatever 04-tags/coref.txt holds.
registry:
	uv run registry.py inferno purgatorio paradiso -m $(MODEL)

# Coreference overlay (04-tags/coref.txt): reads the overlay-free types.txt, calls the model for
# scenes not yet in coref.cache.txt. Staged for review before the node tables are rebuilt.
coref:
	uv run coreference.py inferno purgatorio paradiso -m $(MODEL)

measure:
	uv run measure.py

.PHONY: all registry coref measure
