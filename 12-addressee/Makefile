include ../model.mk

all: addressee

addressee:
	uv run addressee.py inferno purgatorio paradiso -m $(MODEL)

# Remove the generated addressee cantos (regenerable by `make`); keeps addressee.py/README/Makefile.
clean:
	rm -rf inferno purgatorio paradiso

.PHONY: all addressee clean
