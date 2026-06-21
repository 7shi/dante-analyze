include ../model.mk

all: presence

presence:
	uv run presence.py inferno purgatorio paradiso -m $(MODEL)

# Remove the generated presence cantos (regenerable by `make`); keeps presence.py/README/Makefile.
clean:
	rm -rf inferno purgatorio paradiso

.PHONY: all presence clean
