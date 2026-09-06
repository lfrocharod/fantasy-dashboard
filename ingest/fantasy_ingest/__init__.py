"""UEFA Champions League Fantasy ingestion + projection engine.

Layering (import direction is one-way, top depends on bottom):

    run.py                      orchestration
      ucl/ , sources/ , mapping/ , model/
        db.py , config.py , secretbox.py
          types.py              plain dataclasses, no deps

`model/` depends only on `types.py` + the standard library + `pulp`, so it is
unit-testable without a database, network, or the heavy `soccerdata` stack.
"""

__version__ = "0.1.0"
MODEL_VERSION = "ucl-xpts-1"
