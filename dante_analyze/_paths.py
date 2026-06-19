from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
ROOT_DIR = PACKAGE_DIR.parent

# Analysis outputs live at the project root, alongside the pass scripts.
SCENE_DIR = ROOT_DIR / "01-scenes"    # scene JSON: 01-scenes/<canticle>/NN.json (committed)
MARKUP_DIR = ROOT_DIR / "02-markup"   # markup.py writes 02-markup/<canticle>/NN.txt (committed)
READING_DIR = ROOT_DIR / "03-reading" # reading.py writes 03-reading/<canticle>/NN.txt
TAGS_DIR = ROOT_DIR / "04-tags"       # tags.py writes 04-tags/<canticle>/NN.txt
REGISTRY_DIR = ROOT_DIR / "05-registry"  # registry.py writes 05-registry/<canticle>.txt (per-canticle)
SPEECH_DIR = ROOT_DIR / "06-speech"      # speech.py writes 06-speech/<canticle>/NN.txt
RELATIONS_DIR = ROOT_DIR / "07-relations"  # relations.py writes 07-relations/<canticle>/NN.txt
KG_DIR = ROOT_DIR / "08-kg"              # assembly.py writes 08-kg/<canticle>/NN.json + <canticle>.nodes.json
LOCATION_DIR = ROOT_DIR / "09-location"  # location.py writes 09-location/<canticle>/NN.txt
TOPOGRAPHY_DIR = ROOT_DIR / "10-topography"  # topography.py writes 10-topography/<canticle>.txt (per-canticle)
PRESENCE_DIR = ROOT_DIR / "11-presence"  # presence.py writes 11-presence/<canticle>/NN.txt
ADDRESSEE_DIR = ROOT_DIR / "12-addressee"  # addressee.py writes 12-addressee/<canticle>/NN.txt
COHORT_DIR = ROOT_DIR / "13-cohort"        # cohort.py writes 13-cohort/<canticle>/NN.txt (per-scene);
                                           # rollup.py writes 13-cohort/<canticle>.txt (per-region)
LOCK_DIR = ROOT_DIR / "14-lock"            # lock.py writes 14-lock/<canticle>/NN.toml (per-canto)
DIGEST_DIR = ROOT_DIR / "15-digest"        # digest.py writes 15-digest/<canticle>/NN.txt (per-scene en/ja)
