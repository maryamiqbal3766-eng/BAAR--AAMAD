"""
THE PERMANENT LIGHT THEME

Two properties worth holding with tests rather than with good intentions:

  1. the application is light whatever the viewer's operating system says,
     enforced in three places that must not drift apart;
  2. every colour used for text meets WCAG AA on the grounds it sits on.

The contrast maths is here rather than in a comment because "this looks fine"
is how #8B97A3 spent a release at 2.98:1 being used for real text.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from ui import theme

CONFIG = Path(__file__).resolve().parent.parent / ".streamlit" / "config.toml"


# ---------------------------------------------------------------------------
# Contrast
# ---------------------------------------------------------------------------


def _channel(value: int) -> float:
    channel = value / 255
    return channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4


def luminance(colour: str) -> float:
    colour = colour.lstrip("#")
    r, g, b = (int(colour[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast(foreground: str, background: str) -> float:
    a, b = luminance(foreground), luminance(background)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def test_the_contrast_helper_is_right():
    """Anchor it against two known values before trusting it below."""
    assert contrast("#000000", "#FFFFFF") == pytest.approx(21.0, abs=0.01)
    assert contrast("#FFFFFF", "#FFFFFF") == pytest.approx(1.0, abs=0.01)


@pytest.mark.parametrize("ground", [theme.CREAM, theme.CARD, theme.PANEL])
@pytest.mark.parametrize("ink", [theme.INK, theme.MUTED, theme.FAINT])
def test_every_text_colour_meets_aa_on_every_ground(ink, ground):
    assert contrast(ink, ground) >= 4.5, f"{ink} on {ground} is {contrast(ink, ground):.2f}:1"


@pytest.mark.parametrize("ground", [theme.CREAM, theme.CARD, theme.PANEL])
@pytest.mark.parametrize("status", [theme.ACCENT, theme.OK, theme.WARN, theme.ALERT])
def test_status_colours_meet_aa(status, ground):
    assert contrast(status, ground) >= 4.5


def test_white_on_the_accent_is_readable():
    """Primary buttons and the current workflow step."""
    assert contrast(theme.CARD, theme.ACCENT) >= 4.5


def test_the_primary_button_label_is_styled_not_just_the_button():
    """Streamlit wraps a button label in a <p>, and the blanket `p` colour rule
    out-specifies a rule that names only the button. That left the primary
    button rendering ink-on-teal at about 1.4:1 in the running app."""
    assert '.stButton > button[kind="primary"] p' in theme.CSS
    assert contrast(theme.INK, theme.ACCENT) < 4.5, "the failure mode this guards"


def test_the_old_faint_grey_is_gone():
    """It measured 2.98:1 on white and was used for real text."""
    assert theme.FAINT != "#8B97A3"
    assert "#8B97A3" not in theme.CSS


# ---------------------------------------------------------------------------
# Permanently light
# ---------------------------------------------------------------------------


def test_the_browser_is_told_not_to_invert_anything():
    assert "color-scheme: light only" in theme.CSS


def test_dark_mode_is_answered_rather_than_inherited():
    assert "@media (prefers-color-scheme: dark)" in theme.CSS

    start = theme.CSS.index("@media (prefers-color-scheme: dark)")
    block = theme.CSS[start:]
    # The ground and the body text are both re-stated, not left to Streamlit.
    assert theme.CREAM in block
    assert theme.INK in block
    assert "color-scheme: light only" in block


def test_there_is_no_dark_palette_anywhere():
    """A theme with no toggle must not carry the colours for one."""
    for dark in ("#000000", "#111", "#1E1E1E", "#0E1117", "#262730"):
        assert dark not in theme.CSS


def test_streamlit_is_pinned_to_light():
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    assert config["theme"]["base"] == "light"


def test_the_config_and_the_stylesheet_agree():
    """Three enforcement points, one palette. They must not drift."""
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))["theme"]
    assert config["backgroundColor"].upper() == theme.CREAM
    assert config["secondaryBackgroundColor"].upper() == theme.PANEL
    assert config["textColor"].upper() == theme.INK
    assert config["primaryColor"].upper() == theme.ACCENT


# ---------------------------------------------------------------------------
# The workflow story
# ---------------------------------------------------------------------------


def test_the_five_stages_are_the_specified_ones():
    assert theme.WORKFLOW == ["Find", "Check", "Explain", "Fix", "Recheck"]


def test_the_stepper_shows_progress_not_just_the_current_step(monkeypatch):
    captured: list[str] = []
    monkeypatch.setattr(theme.st, "markdown", lambda html, **_: captured.append(html))

    theme.workflow_strip("Explain")
    html = captured[0]

    # Find and Check are behind us; Explain is current; Fix and Recheck are not.
    assert html.count("is-done") == 2
    assert html.count("is-now") == 1
    assert "<span class=\"ba-step-i\">1</span>Find" in html
    assert "<span class=\"ba-step-i\">5</span>Recheck" in html


def test_the_last_screen_shows_the_whole_story_complete(monkeypatch):
    captured: list[str] = []
    monkeypatch.setattr(theme.st, "markdown", lambda html, **_: captured.append(html))

    theme.workflow_strip()
    assert captured[0].count("is-done") == len(theme.WORKFLOW)


# ---------------------------------------------------------------------------
# No loose ends in the stylesheet
# ---------------------------------------------------------------------------


def _classes_used_in_pages() -> set[str]:
    pages = Path(__file__).resolve().parent.parent / "ui"
    used: set[str] = set()
    for path in pages.rglob("*.py"):
        for match in re.finditer(r'class="([^"{}]+)"', path.read_text(encoding="utf-8")):
            used.update(part for part in match.group(1).split() if part.startswith("ba-"))
    return used


def test_every_ba_class_the_pages_use_is_defined():
    """`.ba-tally-item` and `.ba-stage.is-waiting` were both being used with no
    rule behind them. Nothing should be styled by accident."""
    undefined = [name for name in _classes_used_in_pages() if f".{name}" not in theme.CSS]
    assert undefined == [], f"used in a page but not styled: {sorted(undefined)}"
