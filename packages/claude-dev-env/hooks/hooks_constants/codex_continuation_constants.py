"""Phrases that warrant one check of a Codex assignment before closing."""

import re

CHILD_FLAG = "--codex-child-stop"
CHILD_STOP_EVENT = "SubagentStop"
AGENT_TRANSCRIPT_KEY = "agent_transcript_path"
MAX_REASON_SENTENCES = 2
LINE_SEPARATOR = "\n"
ALL_CLOSING_PHRASES = (
    "unverified", "pending", "not yet verified", "still open", "remain open", "remains open",
    "still blocked", "remains unconfirmed", "one activation step remains", "awaiting checks",
    "no recording started", "did not establish", "evidence that would unlock", "missing piece",
)
CLOSING_PHRASE = re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, ALL_CLOSING_PHRASES)) + r")(?!\w)", re.IGNORECASE)
QUOTED_EXAMPLE = re.compile(r'''"[^"\n]*"|“[^”\n]*”|‘[^’\n]*’|(?<!\w)'[^'\n]+'(?!\w)''')
CLAUSE_BREAK = re.compile(r"[.!?;\n]+|\b(?:but|whereas)\b|,?\s+and\s+(?=(?:the|a|an|its|our|their|my|this|that|separate|independent|other)\b)", re.IGNORECASE)
NEGATED_STATUS = re.compile(r"(?:\b(?:no|zero|nothing|none|neither|without|formerly|previously)\s+(?:longer\s+)?(?:\w+\s+){0,2}|\b(?:is|was|are|were)\s+not\s+)$", re.IGNORECASE)
RESOLVED_STATUS = re.compile(r"^(?![^.!?;]*?\b(?:not|never|still)\b)\s+(?:\w+\s+){0,2}(?:(?:have|has|are|were|is|was)\s+)?(?:now\s+)?(?:passed|cleared|resolved|verified|completed|closed|shipped)\b", re.IGNORECASE)
CANCELLED_REQUEST = re.compile(r"\b(?:cancel (?:my |the |this |that |your )?(?:request|task|work|assignment)|cancel my earlier request|stop (?:all )?work (?:on (?:it|this) )?now|stop here|do not continue)\b", re.IGNORECASE)
ONLY_STATUS_REQUEST = re.compile(r"(?:please\s+)?(?:(?:give me |provide )?(?:a |the )?(?:current )?status(?: update)? only|report only|only (?:report|summarize) (?:the )?(?:current )?status)[.! ]*", re.IGNORECASE)
ADDITIONAL_REQUEST = re.compile(r"\b(?:but|then|instead|except|also|and(?!\s+(?:stop|end|cancel)))\b|[;\n]", re.IGNORECASE)
STANDALONE_STOP = re.compile(r"(?:please\s+)?(?:stop|cancel(?: everything| (?:the|this|that|my) (?![^.!?]*(?:\band\b|\bbut\b|\bthen\b|\binstead\b))(?:[\w-]+\s+){0,5}[\w-]+)?|end (?:this|the) task)[.! ]*", re.IGNORECASE)

APPROVAL_SUBJECT = re.compile(r"\b(?:approval|authorization|permission|sign[- ]off|owner decision|owner hold)\b", re.IGNORECASE)
PROTECTED_DECISION = re.compile(r"\b(?:only (?:the )?(?:[\w-]+\s+){0,4}(?:owner|admin|steward|operator) (?:can|may)|(?:owner|steward|admin|operator) must (?:approve|authorize|grant|release)|(?:permission|access) denied|(?:you|the owner) (?:denied|declined) (?:permission|approval|access)|(?:HTTP\s+)?403)\b", re.IGNORECASE)
WAIT_SUBJECT = re.compile(r"\b(?:awaiting checks|pending|still blocked|still open|remains? open)\b", re.IGNORECASE)
SEPARATE_SUBJECT = re.compile(r"\b(?:separate|independent|different|unrelated)\b", re.IGNORECASE)
WAKE_EXPLANATION = re.compile(r"^(?:(?:a|the|its|this|an) (?:registered|scheduled|armed|active)|(?:its|this|the) (?:wake|callback)|(?:run|check) \d+ is in progress|it (?:has|is))\b", re.IGNORECASE)
REGISTERED_WAKE = re.compile(r"\b(?:(?:registered|scheduled|armed|active) (?:[\w-]+\s+){0,3}(?:wake|notification|callback)|(?:wake|callback) (?:is |was )?(?:registered|scheduled|armed))\b", re.IGNORECASE)
CONTINUATION_REVIEW = (
    "Recheck the full assignment and the latest user instructions against what reached the destination. "
    "If an authorized step can advance an unfinished outcome, take it now and follow it through the requested "
    "checks, delivery and verification. If one lane is blocked, finish any independent work within scope. "
    "Honor cancellations, owner holds, existing writers, permissions and required approvals. If the work is "
    "complete, cancelled, or only a protected wait remains, close with the accurate result. Name any specific "
    "decision or dependency and preserve an existing wake. Keep accurate status wording."
)
