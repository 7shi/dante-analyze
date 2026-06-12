from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
ROOT_DIR = PACKAGE_DIR.parent

# Analysis outputs live at the project root, alongside the pass scripts.
SCENE_DIR = ROOT_DIR / "01-scenes"    # scene JSON: 01-scenes/<canticle>/NN.json (committed)
MARKUP_DIR = ROOT_DIR / "02-markup"   # markup.py writes 02-markup/<canticle>/NN.txt (committed)
READING_DIR = ROOT_DIR / "03-reading" # reading.py writes 03-reading/<canticle>/NN.txt
TAGS_DIR = ROOT_DIR / "04-tags"       # tags.py writes 04-tags/<canticle>/NN.txt
