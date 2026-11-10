"""Named constants for choosing the Codex account a review runs on."""

from __future__ import annotations

ACCOUNT_BROKER_CHOOSE_COMMAND = "choose"
ACCOUNT_BROKER_PRODUCT_FLAG = "--product"
ACCOUNT_BROKER_CODEX_PRODUCT = "codex"
ALL_ACCOUNT_BROKER_REQUIRE_TIER_ARGUMENTS = ("--require-tier", "normal")
ALL_ACCOUNT_BROKER_RELATIVE_PARTS = ("scripts", "account_broker.py")
SHARED_ROOT_PARENT_INDEX = 3
ACCOUNT_BROKER_TIMEOUT_SECONDS = 150
BROKER_WAIT_EXIT_CODE = 3
ALL_BROKER_ACCEPTED_EXIT_CODES = (0, BROKER_WAIT_EXIT_CODE)
NO_ACCOUNT_EXIT_CODE = 69
BROKER_DECISION_KEY = "decision"
BROKER_TIER_KEY = "tier"
BROKER_HOME_KEY = "home"
BROKER_REASON_KEY = "reason"
BROKER_NORMAL_TIER = "normal"
BROKER_LUNA_TIER = "luna"
ALL_NORMAL_ONLY_TIERS = (BROKER_NORMAL_TIER,)
ALL_RUN_TIERS = (BROKER_NORMAL_TIER, BROKER_LUNA_TIER)
ACCOUNT_BROKER_HOME_FLAG = "--home"
BROKER_NOT_RUN_REASON_TEMPLATE = "account broker did not answer: exit {exit_code}"
BROKER_EXIT_REASON_TEMPLATE = "account broker exit {exit_code}"
BROKER_MALFORMED_REASON = "account broker answer is malformed"
BROKER_NO_HOME_REASON = "account broker answer names no Codex home"
NO_ROOM_REASON_TEMPLATE = "no Codex account has room for a review ({reason})"
