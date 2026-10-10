from __future__ import annotations

from pathlib import Path

QML = Path(__file__).resolve().parents[1] / "xray_fluent" / "qml_app" / "qml"


def _read(name: str) -> str:
    return (QML / name).read_text(encoding="utf-8")


def test_combo_popups_flip_up_and_use_fluent_scrollbar() -> None:
    for name in ("FluentCombo.qml", "SearchCombo.qml"):
        text = _read(name)
        assert "property bool openUp" in text
        assert "y: openUp ? -height - 4 : control.height + 4" in text
        assert "onAboutToShow" in text
    assert "ScrollBar.vertical: FluentScrollBar {}" in _read("FluentCombo.qml")
    for path in QML.glob("*.qml"):
        assert "ScrollIndicator" not in path.read_text(encoding="utf-8"), path.name


def test_zapret_page_has_single_start_stop_button() -> None:
    text = _read("ZapretPage.qml")
    assert "id: statePill" not in text
    assert 'I18n.t("Zapret")' in text
    assert "Обход блокировок (zapret)" not in text
    assert "Перезапустить" not in text and "Переключить" not in text
    assert "onClicked: page.running ? App.stopZapret() : page.startSelected()" in text
    assert text.count("App.stopZapret()") == 1


def test_support_card_has_no_star_icon() -> None:
    text = _read("OnboardingOverlay.qml")
    start = text.index("component SupportCard")
    card = text[start:start + 2500]
    assert 'text: "\\uE734"' not in card  # the GitHub button keeps its glyph


def test_domain_dialog_previews_normalized_input() -> None:
    text = _read("RoutingPage.qml")
    assert "App.normalizeDomainRuleInput(domainInput.text)" in text


def test_onboarding_done_page_and_accent_choices() -> None:
    text = _read("OnboardingOverlay.qml")
    done = text[text.index("id: doneScroll"):text.index("// \u2500\u2500 action bar")]
    assert "SuccessMark {" not in done
    assert done.index("Layout.fillHeight: true") < done.index("SupportCard {")
    assert "flagSource: App.countryFlagSource(modelData.code)" in text
    assert '"\u041a\u0430\u043a \u0432 Windows"' not in text
    assert "CustomAccentDot {" in text and "onboardingAccentDlg.openWith(App.accentColor)" in text

def test_zapret_page_offers_server_strategies() -> None:
    text = _read("ZapretPage.qml")

    assert "App.zapretBindingChoices(bindNodeId)" in text
    assert "App.setZapretServerBinding(modelData.nodeId, modelData.choices[index].value)" in text
    # One picker per server: no separate mode combo, no "current preset" entry.
    assert "Текущий пресет" not in text
    assert "presetChoices" not in text
    assert "function onSelectionChanged()" in text
    # Compact card: the explanation lives in a tooltip, no per-kind strategy block.
    assert "Стратегии для сервера" not in text
    assert "FluentToolTip" in text
