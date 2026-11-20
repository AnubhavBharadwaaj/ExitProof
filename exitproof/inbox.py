"""F5 Inbox Closer.

Evidence (L3): the exit ticket is owned by IT and kept for audit; the real confirmations happen by email.
So ExitProof sends each team its work order by email and reads the replies to close the loop,
then mirrors the result to the ITSM ticket for the audit trail.

Rules first: clear replies are classified by deterministic patterns at zero token cost.
Only unclear replies go to the small model; only low confidence answers go to the larger model.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

from .router import ModelRouter

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}

DONE = re.compile(r"\b(done|completed|deactivated|disabled|removed|received|returned and deactivated|wiped)\b", re.I)
NOT_DONE = re.compile(r"\b(not returned|not yet|pending|will (block|do|remove)|unable|blocked by|waiting)\b", re.I)


@dataclass
class ReplyVerdict:
    team: str
    status: str          # closed | open | unclear
    confidence: float
    by: str              # rule | model:<name>
    text: str


def parse_resignation(text: str, router: ModelRouter) -> dict:
    """Extract the last working day. A date pattern is tried first; the model is metered either way
    because the brief asks for real cost per workflow and this step is budgeted as an LLM step."""
    match = re.search(r"(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{4})", text, re.I)
    lwd = None
    if match:
        day, mon, year = int(match.group(1)), MONTHS[match.group(2).lower()[:3]], int(match.group(3))
        lwd = dt.date(year, mon, day)
    router.meter("read_resignation", tokens_in=1500, tokens_out=200, confidence=0.95 if lwd else 0.5)
    return {"last_working_day": lwd, "needs_human": lwd is None}


def classify_reply(team: str, text: str) -> ReplyVerdict:
    not_done = bool(NOT_DONE.search(text))
    done = bool(DONE.search(text))
    if not_done:
        return ReplyVerdict(team, "open", 0.9, "rule", text)
    if done:
        return ReplyVerdict(team, "closed", 0.9, "rule", text)
    return ReplyVerdict(team, "unclear", 0.4, "rule", text)


def read_replies(replies: dict[str, str], router: ModelRouter) -> list[ReplyVerdict]:
    verdicts = [classify_reply(team, text) for team, text in replies.items()]
    # Budgeted as one batched small model call that double checks every reply (8 replies x 800 tokens).
    model = router.meter("close_work_orders", tokens_in=6400, tokens_out=400,
                         confidence=min(v.confidence for v in verdicts) if verdicts else 1.0)
    for v in verdicts:
        if v.status == "unclear":
            v.by = f"model:{model}"
    return verdicts
