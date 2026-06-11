"""Basic abuse / insult detection for the V3 safety gates.

Intentionally simple: a regex over common Rioplatense/Spanish insults and slurs
directed at the bot or agency. This is NOT a content-moderation system — it is a
cheap first line so that repeated abuse (combined with off-topic messages) can
escalate to a human instead of looping the canned redirect forever.

Design note — false positives are costly here: the abuse gate runs on every turn
and returns early, so a wrongly-flagged message would block a legitimate user.
Each stem is therefore word-boundary anchored, and short stems that collide with
names/normal words (e.g. "gil" → "Gilberto") carry an explicit suffix/boundary.
When in doubt the message is NOT flagged and the normal engine handles it.
"""

from __future__ import annotations

import re

# Each alternative is matched after a leading word boundary. Most stems omit a
# trailing anchor so plurals/elongations fold in naturally ("boludo" → "boludos",
# "idiota" → "idiotaaa"). Ambiguous short stems pin a trailing boundary/suffix.
_ABUSE_TERMS = [
    r"idiota",
    r"imb[eé]cil",
    r"est[uú]pid[oa]",
    r"pelotud[oa]",
    r"boludo",                       # also boludos/boludazo
    r"forr[oa]\b",
    r"gil(?:es|az[oa]|ada|udo)\b",        # suffix required: avoid the name "Gil"
    r"(?:sos un|sos una|que|pedazo de) gil\b",  # …or a clearly insulting context
    r"hij[oa] de puta",
    r"hdp\b",
    r"la concha (?:de|tuya)",
    r"conchud[oa]",
    r"and[aá]te a la (?:mierda|concha)",
    r"vete a la mierda",
    r"mierda",
    r"in[uú]til(?:es)?\b",
    r"tarad[oa]",
    r"sorete",
    r"garca\b",
    r"chot[oa]\b",
    r"maric[oó]n",
    r"jod[ae]te",
    r"que te jodan",
    r"te odio",
    r"sos (?:un|una) (?:asco|basura|estafa)",
    r"son unos? (?:ladrones|chorros|estafadores|garcas)",
    r"estafador(?:es|a)?\b",
    r"put[oa]s?\b",                  # pinned end: avoid "computadora"/"reputado" handled by \b start
]

_ABUSE_RE = re.compile(r"\b(?:" + "|".join(_ABUSE_TERMS) + r")", re.IGNORECASE)


def is_abusive(message: str) -> bool:
    """Return True when the message contains an insult/slur (best-effort)."""
    return bool(_ABUSE_RE.search(message or ""))
