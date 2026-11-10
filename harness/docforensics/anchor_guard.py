"""Operator/anchor drift guard: name what a formula candidate silently changed.

Issue #28 item B: a candidate that degrades ``\iint`` to ``\int``, drops
``\sum``, or loses a superscript must never slip through merely because the
remainder still parses. This module compares anchors between the original and
a candidate and returns stable, bounded findings; it does not judge syntax
(the checker does that) and it does not authorize any edit.

Anchors covered: big operators, Greek letters, and the ``^``/``_`` script
structure. Token comparison is spacing-insensitive because both sides are
tokenized with the same tokenizer as the preservation checks.
"""

import re
from collections import Counter

from .formula_repair import _tokens

_BIG_OPERATORS = (
    r"\int", r"\iint", r"\iiint", r"\oint", r"\varoint",
    r"\sum", r"\prod", r"\coprod",
    r"\bigcup", r"\bigcap", r"\bigvee", r"\bigwedge", r"\bigoplus", r"\bigotimes",
    r"\lim", r"\limsup", r"\liminf", r"\sup", r"\inf", r"\max", r"\min",
)
# Rank order for downgrade/upgrade detection, highest rank first.
_OPERATOR_RANKS = (r"\iiint", r"\iint", r"\int")
_GREEK_LETTERS = (
    r"\alpha", r"\beta", r"\gamma", r"\delta", r"\epsilon", r"\varepsilon",
    r"\zeta", r"\eta", r"\theta", r"\vartheta", r"\iota", r"\kappa", r"\varkappa",
    r"\lambda", r"\mu", r"\nu", r"\xi", r"\pi", r"\varpi", r"\rho", r"\varrho",
    r"\sigma", r"\varsigma", r"\tau", r"\upsilon", r"\phi", r"\varphi", r"\chi",
    r"\psi", r"\omega",
    r"\Gamma", r"\Delta", r"\Theta", r"\Lambda", r"\Xi", r"\Pi", r"\Sigma",
    r"\Upsilon", r"\Phi", r"\Psi", r"\Omega",
)
_SCRIPT_TOKENS = {"^": "superscript", "_": "subscript"}


def _counts(tokens, anchors):
    names = Counter(token.text for token in tokens if token.text in anchors)
    return {anchor: names.get(anchor, 0) for anchor in anchors}


def anchor_drift(original, candidate):
    """Compare anchors between original and candidate.

    Returns ``{"drift": bool, "findings": [...], "reason": str}``. ``reason``
    is empty when no anchor drifted, else ``anchor_drift:<kind>:<anchor>`` for
    the first finding — a stable, bounded category suitable for retry
    feedback. Non-string inputs are not this module's business: they yield a
    verdict without drift so the checker and preservation scope stay
    responsible for them.
    """
    if not isinstance(original, str) or not isinstance(candidate, str):
        return {"drift": False, "findings": [], "reason": "invalid_input"}
    old_tokens, new_tokens = _tokens(original), _tokens(candidate)
    findings = []

    old_ops, new_ops = _counts(old_tokens, set(_BIG_OPERATORS)), _counts(new_tokens, set(_BIG_OPERATORS))
    deficits = {anchor: old_ops[anchor] - new_ops[anchor] for anchor in _BIG_OPERATORS
                if old_ops[anchor] > new_ops[anchor]}
    surpluses = {anchor: new_ops[anchor] - old_ops[anchor] for anchor in _BIG_OPERATORS
                 if new_ops[anchor] > old_ops[anchor]}
    # Rank swaps are one drift event, not two: pair them along the chain first
    # (\iiint→\iint→\int), then report what is genuinely lost or added.
    for higher, lower in zip(_OPERATOR_RANKS, _OPERATOR_RANKS[1:]):
        moved = min(deficits.get(higher, 0), surpluses.get(lower, 0))
        if moved > 0:
            findings.append({"kind": "operator_downgraded", "anchor": higher,
                             "original": old_ops[higher], "candidate": new_ops[higher]})
            deficits[higher] -= moved
            surpluses[lower] -= moved
        moved = min(surpluses.get(higher, 0), deficits.get(lower, 0))
        if moved > 0:
            findings.append({"kind": "operator_upgraded", "anchor": lower,
                             "original": old_ops[lower], "candidate": new_ops[lower]})
            surpluses[higher] -= moved
            deficits[lower] -= moved
    for anchor in _BIG_OPERATORS:
        if deficits.get(anchor, 0) > 0:
            findings.append({"kind": "operator_lost", "anchor": anchor,
                             "original": old_ops[anchor], "candidate": new_ops[anchor]})
        elif surpluses.get(anchor, 0) > 0:
            findings.append({"kind": "operator_added", "anchor": anchor,
                             "original": old_ops[anchor], "candidate": new_ops[anchor]})

    old_greek, new_greek = _counts(old_tokens, set(_GREEK_LETTERS)), _counts(new_tokens, set(_GREEK_LETTERS))
    for anchor in _GREEK_LETTERS:
        if old_greek[anchor] > new_greek[anchor]:
            findings.append({"kind": "greek_lost", "anchor": anchor,
                             "original": old_greek[anchor], "candidate": new_greek[anchor]})
        elif new_greek[anchor] > old_greek[anchor]:
            findings.append({"kind": "greek_added", "anchor": anchor,
                             "original": old_greek[anchor], "candidate": new_greek[anchor]})

    for token, label in _SCRIPT_TOKENS.items():
        old_count = sum(1 for item in old_tokens if item.text == token)
        new_count = sum(1 for item in new_tokens if item.text == token)
        if old_count > new_count:
            findings.append({"kind": "script_lost", "anchor": label,
                             "original": old_count, "candidate": new_count})
        elif new_count > old_count:
            findings.append({"kind": "script_added", "anchor": label,
                             "original": old_count, "candidate": new_count})

    if not findings:
        return {"drift": False, "findings": [], "reason": ""}
    first = findings[0]
    return {"drift": True, "findings": findings,
            "reason": "anchor_drift:%s:%s" % (first["kind"], first["anchor"])}
