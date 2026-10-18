import sys
from pathlib import Path

overlay_directory = Path(__file__).resolve().parent / "fixture_overlay"
fixture_directory = Path(__file__).resolve().parents[1] / "features-start-with-an-eval" / "fixture"
saved_modules = {
    each_name: each_module
    for each_name, each_module in sys.modules.items()
    if each_name == "jobs" or each_name.startswith("jobs.")
}
saved_path = list(sys.path)
for each_name in saved_modules:
    del sys.modules[each_name]
sys.path.insert(0, str(overlay_directory))
sys.path[:] = [each_entry for each_entry in sys.path if each_entry != str(fixture_directory)]
try:
    from jobs.durations import format_duration
finally:
    sys.path[:] = saved_path
    for each_name in [each_name for each_name in sys.modules if each_name == "jobs" or each_name.startswith("jobs.")]:
        del sys.modules[each_name]
    sys.modules.update(saved_modules)


def test_format_duration_uses_hours_and_zero_padded_minutes() -> None:
    assert format_duration(2 * 60 * 60 + 5 * 60 + 59) == "2h 05m"
    assert format_duration(59) == "0h 00m"
