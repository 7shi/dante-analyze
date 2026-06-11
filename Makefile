# Corpus inputs (canto text, tokens, scene ranges) come from dante-corpus via its API.
# Build it first:  make -C ../dante-corpus

markup-step1:
	$(MAKE) -C 2_markup step1

markup-step2:
	$(MAKE) -C 2_markup step2

markup-step3:
	$(MAKE) -C 2_markup step3

markup-step4:
	$(MAKE) -C 2_markup step4

markup:
	$(MAKE) -C 2_markup all

reading:
	$(MAKE) -C 3_reading

bullets:
	$(MAKE) -C 4_bullets

tags:
	$(MAKE) -C 5_tags

verify:
	$(MAKE) -C 5_tags verify

.PHONY: markup-step1 markup-step2 markup-step3 markup-step4 markup reading bullets tags verify
