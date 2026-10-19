"""Resolve chart coordinates from captured JSON."""
import json
import math
from pathlib import Path

from visual_config.config import constants as c


class MetricRunFatal(ValueError):
    """Reject an unsupported chart or an ungrounded metric."""


def _coordinate(reference: dict, node: dict, snapshot_path: Path) -> float:
    source = node["sources"][reference[c.METRIC_SOURCE_INDEX]]
    source_path = snapshot_path.parent / source.get("side", c.HEAD_SIDE) / source["path"]
    measurement = json.loads(source_path.read_text(encoding="utf-8-sig"))
    pointer = reference["pointer"]
    if not pointer.startswith("/"):
        raise MetricRunFatal("Metric pointer must be an absolute JSON pointer.")
    for each_token in pointer.split("/")[1:]:
        token = each_token.replace("~1", "/").replace("~0", "~")
        measurement = measurement[int(token)] if isinstance(measurement, list) else measurement[token]
    if isinstance(measurement, bool) or not isinstance(measurement, (int, float)) or not math.isfinite(measurement):
        raise MetricRunFatal("Chart coordinates must be finite numbers from captured JSON.")
    return measurement


def prepare_chart(scene: dict, snapshot_path: Path) -> None:
    """Resolve every chart coordinate against the node's captured source.

    Args:
        scene: Source-validated scene with optional chart metadata.
        snapshot_path: Captured snapshot path.

    Raises:
        MetricRunFatal: Chart kind, axis labels, or metric values are invalid.
    """
    chart = scene.get("chart")
    if not chart:
        return
    if chart["kind"] not in c.ALL_CHART_KINDS or not chart.get("x_label") or not chart.get("y_label"):
        raise MetricRunFatal("Charts need a supported kind and labeled axes with units.")
    if not scene["nodes"]:
        raise MetricRunFatal("Charts need at least one measured point.")
    axes = (c.CHART_Y_AXIS,) if chart["kind"] == c.ALL_CHART_KINDS[0] else c.ALL_CHART_AXES
    try:
        for each_node in scene["nodes"]:
            each_node["values"] = {each_axis: _coordinate(each_node["metrics"][each_axis], each_node, snapshot_path) for each_axis in axes}
    except (KeyError, IndexError, TypeError, ValueError, OSError) as error:
        raise MetricRunFatal(f"Cannot resolve chart measurement: {error}") from error
