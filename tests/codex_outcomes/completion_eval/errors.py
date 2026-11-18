"""Failures that invalidate an assignment or its replay."""


class EvidenceRunFatal(ValueError):
    """The evidence cannot support a comparison."""
