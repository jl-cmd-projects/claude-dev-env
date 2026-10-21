"""Exercise docked panels, mini-diagrams, source disclosures, and isolation."""
import argparse
import json
import re
import shutil
from pathlib import Path

from playwright.sync_api import Locator, Page, sync_playwright
from visual_config.config import constants as c


def _panel_layout(root: Locator, is_mobile: bool = False) -> None:
    stage_box = root.locator(c.STAGE_SELECTOR).bounding_box()
    panel_box = root.locator(c.DRAWER_SELECTOR).bounding_box()
    assert stage_box is not None and panel_box is not None
    if is_mobile:
        assert panel_box["y"] + panel_box["height"] <= stage_box["y"] + 1
    else:
        assert stage_box["x"] + stage_box["width"] <= panel_box["x"] + 1


def _check_node(root: Locator, node: dict) -> None:
    assert root.locator(c.DRAWER_SELECTOR).is_visible()
    assert root.locator(".drawer .detail-map").is_visible()
    assert root.locator(".drawer .detail-map use").count() == len(node["drilldown"]["steps"])
    assert not root.locator(c.EXACT_SELECTOR).evaluate(c.DISCLOSURE_OPEN_EXPRESSION)
    _panel_layout(root)
    assert root.locator(".drawer [data-embedded-chart]").count() == int(bool(node.get("chart")))
    root.locator(c.DISCLOSURE_SELECTOR).click()
    assert root.locator(".exact-source a").count() == len(node["sources"])
    assert root.locator(".exact-source p").count() == len(node["detail"])
    assert (root.locator(".exact-source pre").count() > 0) == bool(node["sources"][0].get("excerpt"))


def _navigate_related(root: Locator) -> None:
    jumps = root.locator(c.JUMP_SELECTOR)
    if jumps.count():
        target = jumps.first.get_attribute("data-detail-target")
        jumps.first.click()
        assert root.locator(c.NODE_TARGET_SELECTOR.format(target=target)).get_attribute("aria-expanded") == "true"
        assert not root.locator(c.EXACT_SELECTOR).evaluate(c.DISCLOSURE_OPEN_EXPRESSION)


def _toolbar_details(root: Locator, node_count: int) -> None:
    for each_label in c.ALL_TOOLBAR_DETAIL_LABELS:
        root.get_by_role("button", name=each_label, exact=True).click()
        assert root.locator(".drawer .detail-map").is_visible()
        assert root.locator(c.JUMP_SELECTOR).count() == node_count
        root.locator(c.DISCLOSURE_SELECTOR).click()
        assert root.locator(".exact-source p").count() > 0
        root.get_by_role("button", name=c.CLOSE_BUTTON_LABEL).click()


def _check_board(root: Locator, scene: dict) -> None:
    all_cards = root.locator(c.BOARD_CARD_SELECTOR)
    if not scene.get("board"):
        assert all_cards.count() == 0
        return
    assert all_cards.count() == scene["board"]["count"]
    assert not all_cards.evaluate_all(c.CARD_FIT_EXPRESSION)
    background = _luminance(c.PAGE_BACKGROUND_COLOR)
    for each_text in root.locator(".canvas svg text").evaluate_all(c.BOARD_TEXT_EXPRESSION):
        assert each_text["size"] >= c.MINIMUM_BOARD_FONT_SIZE, each_text
        assert (background + c.CONTRAST_OFFSET) / (_luminance(each_text["color"]) + c.CONTRAST_OFFSET) >= c.MINIMUM_BOARD_CONTRAST, each_text


def _keyboard_and_zoom(page: Page, root: Locator) -> None:
    first_node = root.locator(c.NODE_SELECTOR).first
    first_node.focus()
    page.keyboard.press("Enter")
    page.keyboard.press("Escape")
    assert first_node.evaluate("(n)=>n===document.activeElement")
    root.get_by_role("button", name=c.ZOOM_BUTTON_LABEL, exact=True).click()
    assert root.locator(c.CANVAS_SELECTOR).evaluate(c.CANVAS_WIDTH_EXPRESSION)
    root.get_by_role("button", name="Fit", exact=True).click()
    assert root.locator(c.CANVAS_SELECTOR).evaluate(c.CANVAS_WIDTH_EXPRESSION) == ""
    assert not root.locator(".canvas svg text").evaluate_all(c.OVERFLOW_EXPRESSION)


def _scene_screenshots(page: Page, root: Locator, scene: dict, proof_directory: Path, scene_index: int) -> None:
    page.screenshot(path=str(proof_directory / c.PR_SCREENSHOT_NAME.format(number=scene["pr"]["number"], index=scene_index)), full_page=True)
    if scene.get("board"):
        root.locator(c.WORKSPACE_SELECTOR).evaluate(c.UNCLIP_WORKSPACE_EXPRESSION)
        root.locator(c.CANVAS_SELECTOR).screenshot(path=str(proof_directory / c.BOARD_SCREENSHOT_NAME.format(number=scene["pr"]["number"], index=scene_index)))
        root.locator(c.WORKSPACE_SELECTOR).evaluate(c.RECLIP_WORKSPACE_EXPRESSION)
    all_nodes = root.locator(c.NODE_SELECTOR)
    all_nodes.first.click()
    page.screenshot(path=str(proof_directory / c.DETAIL_SCREENSHOT_NAME.format(number=scene["pr"]["number"], index=scene_index)), full_page=True)
    if all_nodes.count() > 1:
        root.locator(c.NODE_TARGET_SELECTOR.format(target=scene["nodes"][1]["id"])).click()
        assert root.locator(c.DETAIL_TITLE_SELECTOR).inner_text() == c.SPACE_SEPARATOR.join(scene["nodes"][1]["label"])
    page.keyboard.press("Escape")


def _verify_scene(page: Page, root: Locator, scene: dict, scene_index: int, proof_directory: Path) -> dict:
    root.get_by_role("tab").nth(scene_index).click()
    all_nodes = root.locator(c.NODE_SELECTOR)
    for each_node in scene["nodes"]:
        root.locator(c.NODE_TARGET_SELECTOR.format(target=each_node["id"])).click()
        _check_node(root, each_node)
        _navigate_related(root)
        page.keyboard.press("Escape")
        assert root.locator(c.DRAWER_SELECTOR).is_hidden()
        assert root.locator(c.SELECTED_NODE_SELECTOR).count() == 0
    _toolbar_details(root, len(scene["nodes"]))
    _check_board(root, scene)
    _keyboard_and_zoom(page, root)
    _scene_screenshots(page, root, scene, proof_directory, scene_index)
    return {"pr": scene["pr"]["number"], "nodes_checked": all_nodes.count(), "docked_panel": "pass", "mini_diagrams": "pass", "related_navigation": "pass", "collapsed_sources": "pass", "keyboard_and_zoom": "pass", "board_cards": scene["board"]["count"] if scene.get("board") else "none"}


def _dashboard(page: Page, root: Locator, all_scenes: list[dict], proof_directory: Path) -> None:
    tabs = root.get_by_role("tab")
    assert tabs.count() == len(all_scenes)
    assert root.locator(".tabs svg").count() == 0
    assert root.locator(c.DASHBOARD_SELECTOR).bounding_box()["height"] <= c.MAXIMUM_DASHBOARD_HEIGHT
    for each_index, each_scene in enumerate(all_scenes):
        tabs.nth(each_index).click()
        assert tabs.nth(each_index).get_attribute("aria-selected") == "true"
        assert root.locator(c.DRAWER_SELECTOR).is_hidden()
        assert root.locator("[data-step-chart]").count() == (0 if each_scene.get("chart") else sum(bool(each_node.get("chart")) for each_node in each_scene["nodes"]))
    tabs.first.click()
    root.screenshot(path=str(proof_directory / c.DASHBOARD_SCREENSHOT_NAME))


def _verify_mobile(page: Page, root: Locator, proof_directory: Path) -> None:
    all_tabs = root.get_by_role("tab")
    all_tabs.first.focus()
    if all_tabs.count() > 1:
        page.keyboard.press("ArrowRight")
        assert all_tabs.nth(1).get_attribute("aria-selected") == "true"
    page.set_viewport_size(c.ALL_MOBILE_VIEWPORT)
    root.locator(c.NODE_SELECTOR).first.click()
    _panel_layout(root, is_mobile=True)
    assert root.locator(c.STAGE_SELECTOR).evaluate(c.SCROLLABLE_EXPRESSION)
    root.locator(c.STAGE_SELECTOR).evaluate(c.SCROLL_MAP_EXPRESSION)
    assert root.locator(c.STAGE_SELECTOR).evaluate(c.READ_SCROLL_EXPRESSION) > 0
    page.screenshot(path=str(proof_directory / c.MOBILE_SCREENSHOT_NAME), full_page=True)
    page.keyboard.press("Escape")


def _mount_two_widgets(page: Page, source: str) -> str:
    page.set_viewport_size(c.ALL_DESKTOP_VIEWPORT)
    page.set_content(c.HOST_FIXTURE_HTML)
    background = page.locator(c.HOST_FIXTURE_SELECTOR).evaluate(c.BACKGROUND_EXPRESSION)
    fragment = re.search(c.MAIN_FRAGMENT_PATTERN, source, re.DOTALL).group()
    style = re.search(c.STYLE_FRAGMENT_PATTERN, source, re.DOTALL).group()
    for each_instance in range(2):
        page.evaluate(c.MOUNT_WIDGET_EXPRESSION, style + fragment)
    return background


def _verify_isolation(page: Page, source: str) -> None:
    background = _mount_two_widgets(page, source)
    all_roots = page.locator(c.ROOT_SELECTOR)
    all_roots.nth(0).locator(c.NODE_SELECTOR).first.click()
    assert all_roots.nth(0).locator(c.DRAWER_SELECTOR).is_visible()
    assert all_roots.nth(1).locator(c.DRAWER_SELECTOR).is_hidden()
    all_roots.nth(1).get_by_role("button", name=c.ZOOM_BUTTON_LABEL, exact=True).click()
    assert all_roots.nth(0).locator(c.CANVAS_SELECTOR).evaluate(c.CANVAS_WIDTH_EXPRESSION) == ""
    assert all_roots.nth(0).get_by_role("tab").first.get_attribute("aria-selected") == "true"
    assert page.locator(c.HOST_FIXTURE_SELECTOR).evaluate(c.BACKGROUND_EXPRESSION) == background
    all_ids = page.locator("[id]").evaluate_all(c.READ_IDS_EXPRESSION)
    assert len(all_ids) == len(set(all_ids)), "Widget instances share SVG or control IDs"
    _verify_host_contrast(page, all_roots.nth(0))


def _luminance(color: str) -> float:
    channels = [int(each_component) / c.RGB_CHANNEL_MAXIMUM for each_component in re.findall(c.RGB_COMPONENT_PATTERN, color)]
    linear = [each_channel / c.SRGB_LINEAR_DIVISOR if each_channel <= c.SRGB_LINEAR_THRESHOLD else ((each_channel + c.SRGB_OFFSET) / c.SRGB_SCALE) ** c.SRGB_EXPONENT for each_channel in channels]
    return sum(each_channel * each_weight for each_channel, each_weight in zip(linear, c.ALL_LUMINANCE_WEIGHTS, strict=True))


def _verify_host_contrast(page: Page, root: Locator) -> None:
    page.add_style_tag(content=c.HOST_THEME_STYLES)
    assert page.locator("body").evaluate(c.CONTROL_STYLES_EXPRESSION)["scheme"] == "dark"
    assert page.locator(c.HOST_FIXTURE_SELECTOR).evaluate(c.CONTROL_STYLES_EXPRESSION)["color"] == c.WHITE_COLOR
    assert root.evaluate(c.CONTROL_STYLES_EXPRESSION)["scheme"] == "light"
    all_controls = root.locator("button")
    for each_index in range(all_controls.count()):
        control = all_controls.nth(each_index)
        styles = control.evaluate(c.CONTROL_STYLES_EXPRESSION)
        assert styles["opacity"] == "1" and styles["shadow"] == "none"
        foreground, background = sorted((_luminance(styles["color"]), _luminance(styles["background"])))
        assert (background + c.CONTRAST_OFFSET) / (foreground + c.CONTRAST_OFFSET) >= c.MINIMUM_TEXT_CONTRAST
        children = control.locator("span")
        for each_child in range(children.count()):
            assert children.nth(each_child).evaluate(c.CONTROL_STYLES_EXPRESSION)["color"] == styles["color"]
    close = root.get_by_role("button", name=c.CLOSE_BUTTON_LABEL)
    assert close.evaluate(c.CONTROL_STYLES_EXPRESSION)["color"] == c.TEAL_COLOR
    assert close.evaluate(c.CONTROL_STYLES_EXPRESSION)["border"] == c.CONTROL_BORDER_COLOR
    page.keyboard.press("Tab")
    close.focus()
    assert close.evaluate(c.CONTROL_STYLES_EXPRESSION)["outline"] == c.TEAL_COLOR
    root.get_by_role("button", name="Fit", exact=True).focus()
    assert root.get_by_role("button", name="Fit", exact=True).evaluate(c.CONTROL_STYLES_EXPRESSION)["outline"] == c.LIME_COLOR


def verify(path: Path, proof_directory: Path, browser_path: str | None = None, should_disable_sandbox: bool = False) -> None:
    """Exercise the rendered artifact in desktop, mobile, and shared-host layouts.

    Args:
        path: Rendered HTML artifact.
        proof_directory: Directory receiving screenshots and the verification report.
        browser_path: Optional Chromium executable; otherwise detect or use Playwright.
        should_disable_sandbox: Disable Chromium sandbox only in an isolated container.
    """
    proof_directory.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as driver:
        browser_path = browser_path or shutil.which("chromium") or shutil.which("google-chrome")
        browser = driver.chromium.launch(executable_path=browser_path, headless=True, args=["--no-sandbox"] if should_disable_sandbox else [])
        page = browser.new_page(viewport=c.ALL_DESKTOP_VIEWPORT, device_scale_factor=1)
        all_errors = []
        page.on("pageerror", lambda each_error: all_errors.append(str(each_error)))
        page.set_content(path.read_text(encoding="utf-8"))
        root = page.locator(c.ROOT_SELECTOR)
        all_scenes = root.locator(c.DATA_SCENES_SELECTOR).evaluate(c.READ_SCENES_EXPRESSION)
        _dashboard(page, root, all_scenes, proof_directory)
        all_verdicts = [_verify_scene(page, root, each_scene, each_index, proof_directory) for each_index, each_scene in enumerate(all_scenes)]
        _verify_mobile(page, root, proof_directory)
        _verify_isolation(page, path.read_text(encoding="utf-8"))
        assert not all_errors, all_errors
        browser.close()
    report = {"input": str(path), "diagrams": all_verdicts, "browser_errors": all_errors, "mobile_stacked_panel": "pass", "multiple_widget_isolation": "pass", "dark_host_contrast": "pass"}
    (proof_directory / c.REPORT_NAME).write_text(json.dumps(report, indent=c.JSON_INDENT), encoding="utf-8")
    print(json.dumps(report, indent=c.JSON_INDENT))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html", type=Path)
    parser.add_argument("--out", type=Path, default=Path(c.DEFAULT_PROOF_DIRECTORY))
    parser.add_argument("--browser-path", help="Chromium executable; defaults to a detected browser or Playwright Chromium.")
    parser.add_argument("--no-sandbox", action="store_true", help="Use only when the browser runs in an isolated container.")
    arguments = parser.parse_args()
    verify(arguments.html, arguments.out, arguments.browser_path, arguments.no_sandbox)
