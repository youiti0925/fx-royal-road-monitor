"""Offline batch layer.

Operates on historical OHLC archives. May use lookahead (price action
after a candidate) for outcome labelling — that is exactly the point of
running offline. The live layer must never import from this package.
"""

from __future__ import annotations
