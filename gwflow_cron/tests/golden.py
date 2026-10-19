"""Load and build independent copies of the GWF-2 golden portal corpus.

The shared golden corpus is not committed elsewhere in this repository, so
``fixtures/golden_corpus.json`` is its single cron-test transcription.  The
identity-to-superevent distribution is the working assumption recorded by
design A8 and open question OQ-1, rather than a claim about an external
canonical fixture.
"""

import copy as _copy
import json as _json
from pathlib import Path as _Path

_FIXTURE_PATH = _Path(__file__).with_name("fixtures") / "golden_corpus.json"


def load_golden_corpus():
    """Load and return a deep copy of the complete golden corpus."""
    with _FIXTURE_PATH.open(encoding="utf-8") as stream:
        corpus = _json.load(stream)
    return _copy.deepcopy(corpus)


def build_golden_corpus():
    """Build an independent mutable copy of the complete golden corpus."""
    return _copy.deepcopy(load_golden_corpus())


def build_superevent(sname):
    """Build an independent mutable copy of one golden superevent detail."""
    return _copy.deepcopy(load_golden_corpus()[sname])
