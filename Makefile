# Corpus inputs (canto text, tokens, scene ranges) come from dante-corpus via its API.
# Build it first:  make -C ../dante-corpus
#
# Each target is a pass directory with the numeric prefix dropped; `all` runs the whole pipeline in
# order. Per-pass options (targets, model, etc.) live in each subdir's Makefile.

all: scenes markup reading tags registry speech relations kg \
     location topography presence addressee cohort lock digest

scenes:
	$(MAKE) -C 01-scenes

markup:
	$(MAKE) -C 02-markup

reading:
	$(MAKE) -C 03-reading

tags:
	$(MAKE) -C 04-tags

registry:
	$(MAKE) -C 05-registry

speech:
	$(MAKE) -C 06-speech

relations:
	$(MAKE) -C 07-relations

kg:
	$(MAKE) -C 08-kg

location:
	$(MAKE) -C 09-location

topography:
	$(MAKE) -C 10-topography

presence:
	$(MAKE) -C 11-presence

addressee:
	$(MAKE) -C 12-addressee

cohort:
	$(MAKE) -C 13-cohort

lock:
	$(MAKE) -C 14-lock

digest:
	$(MAKE) -C 15-digest

.PHONY: all scenes markup reading tags registry speech relations kg \
        location topography presence addressee cohort lock digest
