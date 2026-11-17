"""What every Desk page's live refresh shares: its timings and the page's script policy.

Each page draws and refreshes itself with its own script, from same-origin JSON (per GOV-0051):
the Work map from `map.json` (`workmap.js`, #1138), Crew and Governance from `state.json`
(`crew.js`, #1139; `governance.js`, #1140). They fetch on the same clock and grey the LIVE mark
at the same age, both set here. `poll.js` and its node trees (#411) retired with #1135.
"""
from __future__ import annotations

import base64
import hashlib

EVERY_SECONDS = 15        # how often an open Desk page fetches its JSON
STALE_MINUTES = 15        # older data greys the LIVE mark (#402)


def script_hash(js: str | bytes) -> str:
    """The CSP source for a script (its text, or a vendored file's bytes): 'sha256-<base64 digest>'."""
    data = js if isinstance(js, bytes) else js.encode("utf-8")
    return "'sha256-" + base64.b64encode(hashlib.sha256(data).digest()).decode() + "'"


def csp(js: str | None, libs: tuple[bytes, ...] = ()) -> str:
    """The page's Content-Security-Policy: same-origin fonts and fetches, inline styles
    (the page's <style> and the precedent table's cell shading), and no script but the
    same-origin ones whose hashes are given: the page's own (#1106) and any vendored
    libraries it loads (#1107)."""
    hashes = [script_hash(b) for b in libs] + ([script_hash(js)] if js else [])
    scripts = "'self' " + " ".join(hashes) if hashes else "'none'"
    return ("default-src 'none'; "
            f"script-src {scripts}; "
            "style-src 'unsafe-inline'; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "base-uri 'none'; "
            "form-action 'none'")
