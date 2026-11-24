"""Tolerant loader for ``riskpulse_29d_bundle.joblib``.

Why this exists
---------------
The shipped bundle pickles an ``xgboost.Booster`` through XGBoost's raw serialisation (UBJSON with a
``Config`` and a ``Model`` section). The ``Config`` section of this particular file stores
``learner/generic_param/rng_state`` as decimal numbers, which XGBoost 3.4.1 refuses to parse
(``XGBoostError: input stream corrupted``) even though the file is structurally valid and the ``Model``
section (220 trees, objective, base_score) loads fine.

``Config`` only holds training-time parameters (RNG state, thread counts, ...). Inference needs the
``Model`` section only, so on failure we re-load the pickle while loading just that section.
Predictions are unchanged: same trees, same objective, same base_score.
"""

from __future__ import annotations

import logging
import struct
from contextlib import contextmanager
from pathlib import Path

import joblib

logger = logging.getLogger(__name__)

_INT_FORMATS = {b"i": ("b", 1), b"U": ("B", 1), b"I": (">h", 2), b"l": (">i", 4), b"L": (">q", 8)}
_FIXED = {b"d": 4, b"D": 8, b"i": 1, b"U": 1, b"I": 2, b"l": 4, b"L": 8}


class _Reader:
    """Minimal UBJSON walker (the subset emitted by XGBoost); only used to find section offsets."""

    def __init__(self, buf: bytes):
        self.buf, self.pos = buf, 0

    def _take(self, n: int) -> bytes:
        chunk = self.buf[self.pos : self.pos + n]
        if len(chunk) != n:
            raise ValueError("truncated UBJSON buffer")
        self.pos += n
        return chunk

    def _int(self, marker: bytes) -> int:
        fmt, size = _INT_FORMATS[marker]
        return struct.unpack(fmt if fmt.startswith(">") else ">" + fmt, self._take(size))[0]

    def skip_value(self, marker: bytes | None = None) -> None:
        marker = marker or self._take(1)
        if marker == b"{":
            while self.buf[self.pos : self.pos + 1] != b"}":
                self._take(self._int(self._take(1)))  # key
                self.skip_value()
            self._take(1)
        elif marker == b"[":
            if self.buf[self.pos : self.pos + 1] == b"$":
                self._take(1)
                typ = self._take(1)
                self._take(1)  # '#'
                self._take(_FIXED[typ] * self._int(self._take(1)))
            elif self.buf[self.pos : self.pos + 1] == b"#":
                self._take(1)
                for _ in range(self._int(self._take(1))):
                    self.skip_value()
            else:
                while self.buf[self.pos : self.pos + 1] != b"]":
                    self.skip_value()
                self._take(1)
        elif marker in _INT_FORMATS:
            self._int(marker)
        elif marker == b"d":
            self._take(4)
        elif marker == b"D":
            self._take(8)
        elif marker == b"S":
            self._take(self._int(self._take(1)))
        elif marker in (b"T", b"F", b"Z"):
            pass
        else:
            raise ValueError(f"unsupported UBJSON marker {marker!r} at {self.pos - 1}")


def extract_model_section(raw: bytes) -> bytes:
    """Return the UBJSON document of the ``Model`` key from an XGBoost raw-serialised booster."""
    r = _Reader(raw)
    if r._take(1) != b"{":
        raise ValueError("not an XGBoost UBJSON object")
    while r.buf[r.pos : r.pos + 1] != b"}":
        key = r._take(r._int(r._take(1))).decode()
        if key == "Model":
            start = r.pos
            r.skip_value()
            return raw[start : r.pos]
        r.skip_value()
    raise ValueError("no 'Model' section in booster buffer")


@contextmanager
def _model_section_only_unpickling():
    from xgboost import core

    original = core.Booster.__setstate__

    def setstate(self, state):
        handle = state.get("handle")
        if handle is not None:
            tmp = core.Booster()
            tmp.load_model(bytearray(extract_model_section(bytes(handle))))
            state = {**state, "handle": tmp.handle}
            tmp.handle = None  # ownership moves to ``self``
        self.__dict__.update(state)

    core.Booster.__setstate__ = setstate
    try:
        yield
    finally:
        core.Booster.__setstate__ = original


def load_bundle(path: str | Path):
    """``joblib.load`` with a fallback for the XGBoost ``Config`` incompatibility described above."""
    try:
        return joblib.load(path)
    except Exception as exc:  # xgboost._c_api.XGBoostError (module path varies by version)
        if "XGBoost" not in type(exc).__name__ and "corrupted" not in str(exc):
            raise
        logger.warning("Booster config not loadable (%s); loading the Model section only", exc)
        with _model_section_only_unpickling():
            return joblib.load(path)
