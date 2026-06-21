all: lock

lock:
	uv run lock.py inferno purgatorio paradiso

# Remove the generated locks (regenerable by `make`); keeps lock.py/README/Makefile.
clean:
	rm -rf inferno purgatorio paradiso

.PHONY: all lock clean
