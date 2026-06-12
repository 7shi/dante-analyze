# Corpus inputs (canto text, tokens, scene ranges) come from dante-corpus via its API.
# Build it first:  make -C ../dante-corpus

markup:
	$(MAKE) -C 02-markup markup

reading:
	$(MAKE) -C 03-reading

tags:
	$(MAKE) -C 04-tags

.PHONY: markup reading tags
