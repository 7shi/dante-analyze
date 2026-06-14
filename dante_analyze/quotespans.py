"""Quote-span geometry over `dante_corpus` `QuoteSpan`s: a
depth-first walk and column-aware containment, used by the speech pass (`06-speech/`)
to decide which referents fall inside a given quote's own region.

Positions are (line, col) with `col` a 0-based column into `canto.line(n).text` — the
same coordinate `marks.tag_positions` produces. `start_col`/`end_col` are the columns
of the opening and closing quote markers on the start/end line, so a position is inside
the marked content iff it lies strictly between them (per line)."""


def walk_spans(spans, depth=0):
    """Depth-first iterator over a quote forest, yielding (span, depth) for each node
    (a top-level span is depth 0, its children depth 1, …). Parent before children, in
    source order — the order the speech pass emits one line per span."""
    for span in spans:
        yield span, depth
        yield from walk_spans(span.children, depth + 1)


def contains(span, line, col):
    """Whether (line, col) lies strictly inside `span`'s marked content (between its
    quote markers). On the start line a position must be past the opening marker; on the
    end line, before the closing marker; interior lines are wholly contained. A single-
    line span therefore requires start_col < col < end_col, which is why column offsets
    (not just line numbers) are needed to attribute a one-line quote."""
    if line < span.start_line or line > span.end_line:
        return False
    if line == span.start_line and col <= span.start_col:
        return False
    if line == span.end_line and col >= span.end_col:
        return False
    return True


def own_region(span, line, col):
    """Whether (line, col) is in `span`'s OWN region: inside `span` but inside none of its
    direct children (a nested quote belongs to the child, not the parent). This is the
    region whose first-person referents attribute `span`'s speaker."""
    if not contains(span, line, col):
        return False
    return not any(contains(child, line, col) for child in span.children)
