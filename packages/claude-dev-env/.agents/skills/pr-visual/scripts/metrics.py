"""Resolve chart coordinates from captured JSON and Python literals."""
import ast
import json
import math
from pathlib import Path

from visual_config.config import constants as c


class MetricRunFatal(ValueError):
    """Reject an unsupported chart or an ungrounded metric."""


def _python_literal(reference: dict, source_text: str) -> object:
    candidates = [each_node for each_node in ast.walk(ast.parse(source_text)) if getattr(each_node, "lineno", None) == reference[c.PYTHON_LINE_FIELD]]
    for each_node in candidates:
        if c.PYTHON_ARGUMENT_FIELD in reference and isinstance(each_node, ast.Call):
            return ast.literal_eval(each_node.args[reference[c.PYTHON_ARGUMENT_FIELD]])
        if c.PYTHON_ELEMENT_FIELD in reference and isinstance(each_node, ast.Tuple):
            return ast.literal_eval(each_node.elts[reference[c.PYTHON_ELEMENT_FIELD]])
        if isinstance(each_node, ast.Assert) and isinstance(each_node.test, ast.Compare) and len(each_node.test.comparators) == 1:
            return ast.literal_eval(each_node.test.comparators[0])
    raise MetricRunFatal("No supported numeric literal at the referenced Python line.")


def _json_measurement(reference: dict, source_text: str) -> object:
    measurement = json.loads(source_text)
    pointer = reference["pointer"]
    if not pointer.startswith("/"):
        raise MetricRunFatal("Metric pointer must be an absolute JSON pointer.")
    for each_token in pointer.split("/")[1:]:
        token = each_token.replace("~1", "/").replace("~0", "~")
        measurement = measurement[int(token)] if isinstance(measurement, list) else measurement[token]
    return measurement


def _coordinate(reference: dict, node: dict, snapshot_path: Path) -> float:
    source = node["sources"][reference[c.METRIC_SOURCE_INDEX]]
    source_path = snapshot_path.parent / source.get("side", c.HEAD_SIDE) / source["path"]
    if c.PYTHON_LINE_FIELD in reference and not source["line"] <= reference[c.PYTHON_LINE_FIELD] <= source.get("end", source["line"]):
        raise MetricRunFatal("Python measurement lies outside its cited source lines.")
    source_text = source_path.read_text(encoding="utf-8-sig")
    measurement = _python_literal(reference, source_text) if c.PYTHON_LINE_FIELD in reference else _json_measurement(reference, source_text)
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


def _embedded_chart(chart: dict, node: dict, snapshot_path: Path) -> None:
    if chart.get("kind") not in c.ALL_CHART_KINDS or chart.get("basis") not in c.ALL_CHART_BASES:
        raise MetricRunFatal("Embedded charts need a supported kind and evidence basis.")
    if not all(chart.get(each_field) for each_field in c.ALL_EMBEDDED_CHART_FIELDS):
        raise MetricRunFatal("Embedded charts need a title, caption, units, and points.")
    try:
        for each_index, each_point in enumerate(chart["points"]):
            each_point["values"] = {c.CHART_Y_AXIS: _coordinate(each_point["metrics"][c.CHART_Y_AXIS], node, snapshot_path)}
            each_point["values"][c.CHART_X_AXIS] = _coordinate(each_point["metrics"][c.CHART_X_AXIS], node, snapshot_path) if c.CHART_X_AXIS in each_point["metrics"] else each_index + 1
    except (KeyError, IndexError, TypeError, ValueError, OSError) as error:
        raise MetricRunFatal(f"Cannot resolve embedded chart measurement: {error}") from error


def prepare_embedded_charts(scene: dict, snapshot_path: Path) -> None:
    """Bind step-card charts to their owning node's source.

    Args:
        scene: Source-validated scene.
        snapshot_path: Captured evidence snapshot path.

    Raises:
        MetricRunFatal: A chart lacks supported measurements or provenance.
    """
    for each_node in scene["nodes"]:
        if each_node.get("chart"):
            _embedded_chart(each_node["chart"], each_node, snapshot_path)
