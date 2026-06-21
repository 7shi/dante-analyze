all: digest

digest:
	uv run digest.py inferno purgatorio paradiso

# Measure 14-lock conformance of the committed digest (the proof; no LLM).
check:
	uv run conformance.py inferno purgatorio paradiso

# Remove the generated digests (regenerable by `make`); keeps digest.py/conformance.py/README/Makefile.
clean:
	rm -rf inferno purgatorio paradiso

.PHONY: all digest check clean
