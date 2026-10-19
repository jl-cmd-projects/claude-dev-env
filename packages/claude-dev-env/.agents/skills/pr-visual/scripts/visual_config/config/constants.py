"""Capture limits, artifact names, and diagram boundaries."""
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[3]
PAGE_SIZE = 100
SOURCE_WORKERS = 4
JSON_INDENT = 2
NEWLINE = "\n"
PARAGRAPH_BREAK = "\n\n"
ALL_SOURCE_SIDES = ("base", "head")
HEAD_SIDE = "head"
BASE_SIDE = "base"
PR_URL_PATTERN = r"https://github\.com/([\w.-]+/[\w.-]+)/pull/([1-9]\d*)/?"
PR_ENDPOINT = "repos/{repo}/pulls/{number}"
COMPARE_ENDPOINT = "repos/{repo}/compare/{base}...{head}"
FILES_ENDPOINT = "repos/{repo}/pulls/{number}/files?per_page={size}&page={page}"
CONTENTS_ENDPOINT = "repos/{repo}/contents/{path}?ref={revision}"
SOURCE_LINK = "https://github.com/{repo}/blob/{revision}/{path}#L{first}-L{last}"
DIFF_SECTION = "--- {filename}\n{patch}"
SOURCE_LINE = "{number:4}  {line}"
SNAPSHOT_NAME = "snapshot.json"
DIFF_NAME = "changes.diff"
DEFAULT_EVIDENCE_DIRECTORY = "evidence"
SVG_PATH_PATTERN = r"[MmLlHhVvQqCcSsTtAaZz0-9.,\s-]+"
MINIMUM_NODE_X = 60
MAXIMUM_NODE_X = 1380
MINIMUM_NODE_Y = 200
MAXIMUM_NODE_Y = 760
MINIMUM_DRILLDOWN_STEPS = 2
MAXIMUM_DRILLDOWN_STEPS = 6
MAXIMUM_HTML_BYTES = 256 * 1024
VIEWER_PATH = SKILL_ROOT / "assets" / "viewer.html"
ICONS_PATH = SKILL_ROOT / "assets" / "icons.symbols"
ALL_DESKTOP_VIEWPORT = {"width": 1440, "height": 1200}
ALL_MOBILE_VIEWPORT = {"width": 390, "height": 844}
ROOT_SELECTOR = "[data-pr-visual]"
DRAWER_SELECTOR = ".drawer"
STAGE_SELECTOR = ".stage"
CANVAS_SELECTOR = ".canvas"
EXACT_SELECTOR = ".exact-source"
DISCLOSURE_SELECTOR = ".exact-source summary"
DETAIL_TITLE_SELECTOR = "[data-detail-title]"
NODE_SELECTOR = "[data-node]"
JUMP_SELECTOR = "[data-detail-target]"
DATA_SCENES_SELECTOR = "[data-scenes]"
CANVAS_WIDTH_EXPRESSION = "(n)=>n.style.width"
DISCLOSURE_OPEN_EXPRESSION = "(n)=>n.open"
SOURCE_HAS_EXCERPTS_EXPRESSION = "s=>s.nodes.some(n=>n.sources.some(r=>r.excerpt))"
BACKGROUND_EXPRESSION = "(n)=>getComputedStyle(n).backgroundColor"
SCROLLABLE_EXPRESSION = "(n)=>n.scrollWidth>n.clientWidth"
SCROLL_MAP_EXPRESSION = "(n)=>n.scrollLeft=600"
READ_SCROLL_EXPRESSION = "(n)=>n.scrollLeft"
READ_SCENES_EXPRESSION = "(n)=>JSON.parse(n.textContent)"
READ_IDS_EXPRESSION = "(nodes)=>nodes.map(n=>n.id)"
NODE_TARGET_SELECTOR = '[data-node="{target}"]'
SELECTED_NODE_SELECTOR = '[data-node][aria-expanded=true]'
PR_SCREENSHOT_NAME = "scene-{index}-pr-{number}.png"
DETAIL_SCREENSHOT_NAME = "scene-{index}-pr-{number}-detail.png"
MOBILE_SCREENSHOT_NAME = "mobile-detail.png"
REPORT_NAME = "verification.json"
DEFAULT_PROOF_DIRECTORY = "proof"
SPACE_SEPARATOR = " "
ZOOM_BUTTON_LABEL = "Zoom in"
CLOSE_BUTTON_LABEL = "Close details"
ALL_TOOLBAR_DETAIL_LABELS = ("Summary vs code", "Review notes")
OVERFLOW_EXPRESSION = "(nodes)=>nodes.filter(n=>{const b=n.getBBox(); return b.x<0||b.x+b.width>1440||b.y<0||b.y+b.height>1020}).map(n=>n.textContent)"
MAIN_FRAGMENT_PATTERN = r"<main data-pr-visual>.*?</main>"
STYLE_FRAGMENT_PATTERN = r"<style>.*?</style>"
HOST_FIXTURE_HTML = '<div class="toolbar" id="host-toolbar">Host toolbar</div>'
HOST_FIXTURE_SELECTOR = "#host-toolbar"
HOST_THEME_STYLES = 'body{color-scheme:dark;color:white;background:#121212}button{color:white;opacity:.45;text-shadow:0 0 2px white}span{color:#cccccc}'
CONTROL_STYLES_EXPRESSION = '(n)=>{const s=getComputedStyle(n);return {color:s.color,background:s.backgroundColor,opacity:s.opacity,shadow:s.textShadow,scheme:s.colorScheme,border:s.borderTopColor,outline:s.outlineColor}}'
TEAL_COLOR = "rgb(23, 53, 63)"
WHITE_COLOR = "rgb(255, 255, 255)"
LIME_COLOR = "rgb(216, 246, 135)"
CONTROL_BORDER_COLOR = "rgb(135, 155, 142)"
MINIMUM_TEXT_CONTRAST = 4.5
RGB_COMPONENT_PATTERN = r"\d+"
RGB_CHANNEL_MAXIMUM = 255
SRGB_LINEAR_THRESHOLD = 0.04045
SRGB_LINEAR_DIVISOR = 12.92
SRGB_OFFSET = 0.055
SRGB_SCALE = 1.055
SRGB_EXPONENT = 2.4
ALL_LUMINANCE_WEIGHTS = (0.2126, 0.7152, 0.0722)
CONTRAST_OFFSET = 0.05
MOUNT_WIDGET_EXPRESSION = 'html=>{const t=document.createElement("template");t.innerHTML=html;const scripts=[...t.content.querySelectorAll("script:not([type])")];scripts.forEach(n=>n.remove());document.body.append(t.content);scripts.forEach(old=>{const script=document.createElement("script");script.textContent=old.textContent;document.querySelectorAll("[data-pr-visual]").item(document.querySelectorAll("[data-pr-visual]").length-1).append(script)})}'

ALL_CHART_KINDS = ("bar", "line", "scatter")
ALL_CHART_AXES = ("x", "y")
CHART_Y_AXIS = "y"
METRIC_SOURCE_INDEX = "source"

PYTHON_LINE_FIELD = "python_line"
PYTHON_ARGUMENT_FIELD = "argument"
PYTHON_ELEMENT_FIELD = "element"
CHART_X_AXIS = "x"
ALL_CHART_BASES = ("captured", "source-example")
ALL_EMBEDDED_CHART_FIELDS = ("title", "caption", "x_label", "y_label", "points")

DASHBOARD_SCREENSHOT_NAME = "dashboard.png"
MAXIMUM_DASHBOARD_HEIGHT = 120

DASHBOARD_SELECTOR = ".tabs"
