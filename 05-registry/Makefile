include ../model.mk

# Node tables (05-registry/<canticle>.txt). PURE CODE: folds the committed 04-tags labels (overlay
# applied) and reads the type of each node from 04-tags/types.txt — it does NOT call the model and
# does NOT produce types.txt. The full identity build is the linear chain
#   04-tags: make        (tags) ->
#   04-tags: make typing (types.txt) ->
#   04-tags: make coref  (coref.txt, review) ->
#   05-registry: make    (these node tables)
# so this directory only ever READS 04-tags's artifacts — no back-edge, no re-render.
all: registry

registry:
	uv run registry.py inferno purgatorio paradiso

measure:
	uv run measure.py

.PHONY: all registry measure
