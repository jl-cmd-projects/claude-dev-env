"""Constants for the decision a gate gives when one of its checks raises."""

GATE_FAULT_TEXT_CHARACTER_LIMIT = 200
GATE_FAULT_REASON_TEMPLATE = (
    "The {gate_name} gate hit a fault while it checked this call: {error_type}: {error_text}."
    " The call is refused because the check did not finish."
    " Run the call again, and report the fault when it repeats."
)
GATE_FAULT_SYSTEM_MESSAGE_TEMPLATE = (
    "{gate_script_name} hit a fault and did not check this call: {error_type}: {error_text}."
    " The call goes on to the normal permission flow without this gate's check."
)
PROOF_EDIT_GATE_NAME = "pull request proof edit"
