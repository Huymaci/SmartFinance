import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"


def _section(html, class_name):
    match = re.search(rf'<[^>]+class="[^"]*{class_name}[^"]*"[^>]*>(.*?)</(?:div|header)>', html, re.DOTALL)
    assert match, f"Missing section: {class_name}"
    return match.group(1)


def test_account_entry_and_preferences_are_consolidated_in_sidebar():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    topbar = _section(html, "top-actions")
    preferences_start = html.index('class="profile-preferences')
    preferences = html[preferences_start : html.index("</aside>", preferences_start)]

    assert 'data-action="accounts"' not in topbar
    assert "language-switcher" not in topbar
    assert "data-theme-toggle" not in topbar
    assert html.count('data-action="accounts"') == 1
    assert 'class="avatar profile-avatar"' in html
    assert 'class="profile-more"' in html
    assert preferences.count("data-theme-choice=") == 3
    assert set(re.findall(r'data-theme-choice="([^"]+)"', preferences)) == {"light", "dark", "system"}
    assert set(re.findall(r'data-language="([^"]+)"', preferences)) == {"vi", "en"}


def test_alerts_have_one_navigation_entry_only():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    app = (FRONTEND / "app.js").read_text(encoding="utf-8")

    assert html.count('data-view="alerts"') == 1
    assert 'class="icon-btn notification-btn"' not in html
    assert "$('.notification-btn" not in app


def test_theme_controller_supports_and_tracks_system_preference():
    source = (FRONTEND / "theme.js").read_text(encoding="utf-8")

    assert "prefers-color-scheme: dark" in source
    assert "data-theme-choice" in source
    assert "get preference()" in source


def test_dynamic_api_content_uses_translation_helpers():
    app = (FRONTEND / "app.js").read_text(encoding="utf-8")
    i18n = (FRONTEND / "i18n.js").read_text(encoding="utf-8")

    assert "JSON không hợp lệ" not in app
    assert "displayCategoryName(category(x.category_id))" in app
    assert "displayCategoryText(item.category)" in app
    assert "const copy=alertCopy(x)" in app
    assert "templateName(x)" in app
    assert "document.querySelectorAll(selector)" in i18n
    for key in (
        "invalid_json",
        "threshold_warning_explanation",
        "threshold_critical_explanation",
        "threshold_action",
        "burn_rate_explanation",
        "burn_rate_action",
        "template_vcb",
        "template_tcb",
        "template_mb",
    ):
        assert i18n.count(f"{key}:") == 2
