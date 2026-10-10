import QtQuick
import QtQuick.Controls.Universal
import QtQuick.Layouts
import QtQuick.Effects
import QtQuick.Shapes
import App 1.0
import "."

// First-run / post-update welcome flow. A modal "window inside the window":
// it blurs the live Lumen UI behind it, walks the user through the essentials
// (language, theme, palette, region, routing, configs) and then dissolves into
// the regular dashboard. After an update it opens with "What's new"; fresh
// installs see only the setup. Shown while App.onboardingRequired is true;
// progress is persisted through App.completeOnboarding().
Item {
    id: root
    anchors.fill: parent
    z: 40

    // Live Lumen chrome to blur behind the card (optional).
    property Item blurSource: null
    // Emitted when the exit animation starts (dashboard should settle in)
    // and after it ends.
    signal closingStarted()
    signal finished()

    readonly property bool wanted: App.onboardingRequired && !App.locked
    property bool shown: false
    property bool closing: false
    property int step: 0
    // Page keys of the current run, fixed when the flow opens:
    // news (update notes) · welcome · look · route · configs · done.
    property var flow: ["welcome", "look", "route", "configs", "done"]
    readonly property int stepCount: flow.length
    readonly property bool lastStep: step === stepCount - 1
    property var newsGroups: []
    property string previousVersion: ""
    property bool hasConfigs: App.onboardingReturningUser || App.onboardingServerCount > 0
    property bool configsAnswered: App.onboardingReturningUser || App.onboardingServerCount > 0
    readonly property bool returning: App.onboardingReturningUser
    readonly property bool motion: Theme.animations
    readonly property string iconFont: "Segoe Fluent Icons"

    visible: shown
    enabled: shown && !closing

    readonly property var stepTitleMap: ({
        "news": I18n.t("Что нового"),
        "welcome": I18n.t("Знакомство"),
        "look": I18n.t("Оформление"),
        "route": I18n.t("Регион и маршруты"),
        "configs": I18n.t("Конфигурации"),
        "done": I18n.t("Готово")
    })
    readonly property var stepGlyphMap: ({
        "news": "\uE8BC", "welcome": "\uE80F", "look": "\uE790",
        "route": "\uE909", "configs": "\uEC05", "done": "\uE73E"
    })
    function pageIndex(key) { return flow.indexOf(key) }

    readonly property var themeKeys: ["system", "light", "dark"]
    readonly property var paletteKeys: ["default", "midnight", "catppuccin", "dracula", "nord", "tokyo-night",
        "github", "rose-pine", "gruvbox", "everforest", "solarized", "vercel"]
    readonly property var paletteLabels: ({
        "default": "Default", "midnight": "Midnight", "catppuccin": "Catppuccin", "dracula": "Dracula",
        "nord": "Nord", "tokyo-night": "Tokyo Night", "github": "GitHub", "rose-pine": "Rose Pine",
        "gruvbox": "Gruvbox", "everforest": "Everforest", "solarized": "Solarized", "vercel": "Vercel"
    })
    readonly property var paletteAccents: ({
        "default": "#0078D4", "midnight": "#2563EB", "catppuccin": "#CBA6F7", "dracula": "#BD93F9",
        "nord": "#5E81AC", "tokyo-night": "#34548A", "github": "#0969DA", "rose-pine": "#907AA9",
        "gruvbox": "#B57614", "everforest": "#4F8A10", "solarized": "#268BD2", "vercel": "#111111"
    })
    property string windowsAccent: ""

    function routingDescription(id) {
        if (id === "global") return I18n.t("Весь трафик идёт через VPN")
        if (id === "blocked" || id === "blocked_cn") return I18n.t("Через VPN — только заблокированные сайты, остальное напрямую")
        if (id === "except_ru") return I18n.t("Через VPN всё, кроме российских сайтов и сервисов")
        if (id === "except_cn") return I18n.t("Через VPN всё, кроме китайских сайтов и сервисов")
        if (id === "except_ir") return I18n.t("Через VPN всё, кроме иранских сайтов и сервисов")
        return ""
    }
    function routingGlyph(id) {
        if (id === "global") return "\uE774"
        if (id === "blocked" || id === "blocked_cn") return "\uE72E"
        return "\uE909"
    }
    function regionLabel(key) {
        return key === "china" ? I18n.t("Китай") : (key === "iran" ? I18n.t("Иран") : I18n.t("Россия"))
    }
    function themeLabel(key) {
        return key === "light" ? I18n.t("Светлая") : (key === "dark" ? I18n.t("Тёмная") : I18n.t("Авто"))
    }
    function languageLabel() {
        var idx = App.availableLanguages.indexOf(App.language)
        return idx >= 0 ? App.languageLabels[idx] : App.language
    }
    function paletteLabel() {
        var key = App.uiThemePreset
        if (paletteLabels[key] !== undefined) return paletteLabels[key]
        return key.length ? key.charAt(0).toUpperCase() + key.slice(1) : "Default"
    }
    function routingLabel() {
        var items = App.regionalRoutingPresets
        for (var i = 0; items && i < items.length; ++i) {
            if (items[i].id === App.activeRoutingPresetId)
                return items[i].name
        }
        return I18n.t("Свои правила")
    }
    // Swatches without the system accent (it is shown separately, first).
    readonly property var accentChoices: {
        var out = []
        var all = Theme.accentSwatches.slice(0, 10)
        for (var i = 0; i < all.length; ++i)
            if (windowsAccent === "" || !sameColor(all[i], windowsAccent))
                out.push(all[i])
        return out
    }
    readonly property bool customAccent: {
        if (windowsAccent !== "" && sameColor(App.accentColor, windowsAccent))
            return false
        for (var i = 0; i < accentChoices.length; ++i)
            if (sameColor(App.accentColor, accentChoices[i]))
                return false
        return true
    }

    function sameColor(a, b) {
        return ("" + a).toUpperCase() === ("" + b).toUpperCase()
    }
    // Tallest implicit height among layout children: cards of one group keep
    // the same size whatever length the current language wraps to.
    function tallest(items) {
        var h = 0
        for (var i = 0; i < items.length; ++i) {
            var it = items[i]
            if (it && it.implicitHeight > h)
                h = it.implicitHeight
        }
        return h
    }

    // ---- lifecycle ------------------------------------------------------
    function buildFlow() {
        var setup = App.onboardingSetupRequired
        var news = App.onboardingShowWhatsNew
        // The first page always carries the language picker: update notes
        // for upgraded profiles, the introduction for fresh installs.
        var keys = [news ? "news" : "welcome"]
        if (setup || !news)
            keys = keys.concat(["look", "route", "configs", "done"])
        newsGroups = news ? App.onboardingWhatsNew : []
        previousVersion = App.onboardingPreviousVersion
        flow = keys
    }
    function open() {
        if (shown)
            return
        buildFlow()
        step = 0
        closing = false
        windowsAccent = App.systemAccent()
        // Fresh installs adopt the Windows accent so Lumen feels native from
        // the first frame; returning users keep the accent they chose.
        if (!App.onboardingReturningUser && windowsAccent !== ""
                && sameColor(App.accentColor, "#0078D4"))
            Qt.callLater(App.applySystemAccentQuietly)
        shown = true
        enterAnim.restart()
        root.forceActiveFocus()
    }
    function next() {
        if (step < stepCount - 1)
            step += 1
        else
            finish()
    }
    function back() {
        if (step > 0)
            step -= 1
    }
    function finish() {
        if (closing)
            return
        closing = true
        App.completeOnboarding()
        closingStarted()
        exitAnim.restart()
    }

    onWantedChanged: if (wanted) open()
    Component.onCompleted: if (wanted) Qt.callLater(open)

    Keys.onReturnPressed: next()
    Keys.onEnterPressed: next()
    Keys.onRightPressed: if (!lastStep) next()
    Keys.onLeftPressed: back()

    // ---- animations -----------------------------------------------------
    // Drives the Lumen mark drawing only; the card itself is animated by
    // Animators below.
    property real cardLevel: 0

    // Opacity, scale and position run as Animators on the render thread:
    // they advance on every vsync of the monitor (60/120/144/240 Hz) and stay
    // smooth while the GUI thread saves settings or switches pages under the
    // closing card.
    ParallelAnimation {
        id: enterAnim
        OpacityAnimator { target: backdrop; from: 0; to: 1; duration: root.motion ? 420 : 0; easing.type: Easing.OutCubic }
        SequentialAnimation {
            PauseAnimation { duration: root.motion ? 110 : 0 }
            ParallelAnimation {
                OpacityAnimator { target: cardLayer; from: 0; to: 1; duration: root.motion ? 620 : 0; easing.type: Easing.OutQuint }
                ScaleAnimator { target: cardLayer; from: 0.94; to: 1; duration: root.motion ? 620 : 0; easing.type: Easing.OutQuint }
                YAnimator { target: cardLayer; from: 28; to: 0; duration: root.motion ? 620 : 0; easing.type: Easing.OutQuint }
                NumberAnimation { target: root; property: "cardLevel"; from: 0; to: 1; duration: root.motion ? 620 : 0; easing.type: Easing.OutQuint }
            }
        }
    }
    SequentialAnimation {
        id: exitAnim
        ParallelAnimation {
            OpacityAnimator { target: cardLayer; to: 0; duration: root.motion ? 380 : 0; easing.type: Easing.InCubic }
            ScaleAnimator { target: cardLayer; to: 0.94; duration: root.motion ? 380 : 0; easing.type: Easing.InCubic }
            YAnimator { target: cardLayer; to: 28; duration: root.motion ? 380 : 0; easing.type: Easing.InCubic }
            SequentialAnimation {
                PauseAnimation { duration: root.motion ? 140 : 0 }
                OpacityAnimator { target: backdrop; to: 0; duration: root.motion ? 460 : 0; easing.type: Easing.InOutCubic }
            }
        }
        ScriptAction {
            script: {
                root.shown = false
                root.closing = false
                root.finished()
            }
        }
    }

    // ---- backdrop: heavily blurred live UI + Lumen tint -----------------
    MouseArea { anchors.fill: parent; hoverEnabled: true; preventStealing: true; acceptedButtons: Qt.AllButtons; onWheel: (wheel) => wheel.accepted = true }

    Item {
        id: backdrop
        anchors.fill: parent
        opacity: 0

        // Opaque base: the strong blur fades out towards the window edges,
        // so never let the sharp UI underneath show through there.
        Rectangle {
            anchors.fill: parent
            color: Theme.bg
            Behavior on color { ColorAnimation { duration: Theme.animSlow } }
        }
        // Snapshot of the live UI. It stops updating once the card starts
        // closing, so the heavy blur is not recomputed on every frame while
        // the dashboard settles in underneath.
        ShaderEffectSource {
            id: blurTexture
            x: root.blurSource ? root.blurSource.x : 0
            y: root.blurSource ? root.blurSource.y : 0
            width: root.blurSource ? root.blurSource.width : 0
            height: root.blurSource ? root.blurSource.height : 0
            visible: false
            sourceItem: root.blurSource
            hideSource: false
            live: !root.closing
        }
        MultiEffect {
            x: root.blurSource ? root.blurSource.x : 0
            y: root.blurSource ? root.blurSource.y : 0
            width: root.blurSource ? root.blurSource.width : 0
            height: root.blurSource ? root.blurSource.height : 0
            visible: root.blurSource !== null
            source: blurTexture
            blurEnabled: true
            blur: 1.0
            blurMax: 128
            blurMultiplier: 1.6
            saturation: -0.25
            autoPaddingEnabled: false
        }
        Rectangle {
            anchors.fill: parent
            color: Theme.bg
            opacity: Theme.dark ? 0.62 : 0.56
            Behavior on color { ColorAnimation { duration: Theme.animSlow } }
        }
    }

    // ---- the card ("window inside the window") -------------------------
    readonly property bool wide: card.width >= 760

    // Card and shadow move as one layer (driven by the Animators above).
    Item {
        id: cardLayer
        width: root.width
        height: root.height
        opacity: 0
        scale: 0.94
        y: 28

    RectangularShadow {
        anchors.fill: card
        radius: card.radius
        blur: 60
        spread: 0
        offset.y: 22
        color: Qt.rgba(0, 0, 0, Theme.dark ? 0.55 : 0.20)
    }

    Rectangle {
        id: card
        width: Math.min(980, root.width - 48)
        height: Math.min(640, root.height - 34 - 40)
        x: Math.round((root.width - width) / 2)
        y: Math.round(34 + (root.height - 34 - height) / 2)
        radius: Math.max(10, Theme.radius + 6)
        color: Theme.flyout
        // No `clip` here: an Item clip is rectangular and would let children
        // paint square corners past the rounded edge. Nothing inside fills
        // the corners, and the border is drawn last (cardBorder) on top.
        Behavior on color { ColorAnimation { duration: Theme.animSlow } }

        // ── side panel: brand + stepper ────────────────────────────
        Rectangle {
            id: side
            visible: root.wide
            width: root.wide ? 272 : 0
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.left: parent.left
            color: "transparent"
            Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: Theme.divider }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 28
                spacing: 0

                RowLayout {
                    spacing: 12
                    LumenMark { Layout.preferredWidth: 34; Layout.preferredHeight: 34; ink: Theme.text; level: root.cardLevel }
                    ColumnLayout {
                        spacing: 0
                        Text { text: "Lumen"; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Math.round(20 * Theme.fontScale); font.weight: Font.DemiBold }
                        Text { text: "v" + App.appVersion; color: Theme.textFaint; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall }
                    }
                }

                Item { Layout.preferredHeight: 40 }

                Item {
                    id: stepper
                    Layout.fillWidth: true
                    Layout.preferredHeight: root.stepCount * 52
                    readonly property int rowH: 52

                    // rail line + animated progress fill
                    Rectangle {
                        x: 15; y: 26; width: 2; height: (root.stepCount - 1) * stepper.rowH
                        radius: 1; color: Theme.divider
                    }
                    Rectangle {
                        x: 15; y: 26; width: 2; radius: 1
                        color: Theme.accent
                        height: root.step * stepper.rowH
                        Behavior on height { NumberAnimation { duration: root.motion ? 520 : 0; easing.type: Easing.OutQuint } }
                    }

                    Repeater {
                        model: root.stepCount
                        delegate: Item {
                            id: stepRow
                            required property int index
                            readonly property bool done: index < root.step
                            readonly property bool current: index === root.step
                            y: index * stepper.rowH
                            width: stepper.width
                            height: stepper.rowH

                            Rectangle {
                                id: dot
                                x: 0; y: 10; width: 32; height: 32; radius: 16
                                color: stepRow.current || stepRow.done ? Theme.accent : Theme.flyout
                                border.width: stepRow.current || stepRow.done ? 0 : 1
                                border.color: Theme.flyoutBorder
                                scale: stepRow.current ? 1.0 : 0.86
                                Behavior on color { ColorAnimation { duration: root.motion ? 260 : 0 } }
                                Behavior on scale { NumberAnimation { duration: root.motion ? 420 : 0; easing.type: Easing.OutBack } }
                                Text {
                                    anchors.centerIn: parent
                                    text: stepRow.done ? "\uE73E" : (root.stepGlyphMap[root.flow[stepRow.index]] || "")
                                    font.family: root.iconFont
                                    font.pixelSize: 14
                                    color: stepRow.current || stepRow.done ? Theme.accentText : Theme.textMuted
                                }
                            }
                            Text {
                                anchors.left: dot.right
                                anchors.leftMargin: 14
                                anchors.verticalCenter: dot.verticalCenter
                                text: root.stepTitleMap[root.flow[stepRow.index]] || ""
                                color: stepRow.current ? Theme.text : (stepRow.done ? Theme.textMuted : Theme.textFaint)
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontNormal
                                font.weight: stepRow.current ? Font.DemiBold : Font.Normal
                                Behavior on color { ColorAnimation { duration: root.motion ? 220 : 0 } }
                            }
                            TapHandler {
                                enabled: stepRow.done
                                onTapped: root.step = stepRow.index
                            }
                        }
                    }
                }

                Item { Layout.fillHeight: true }

                Text {
                    Layout.fillWidth: true
                    text: I18n.t("Всё можно изменить позже в Настройках")
                    wrapMode: Text.NoWrap
                    maximumLineCount: 1
                    elide: Text.ElideRight
                    fontSizeMode: Text.HorizontalFit
                    minimumPixelSize: 10
                    color: Theme.textFaint
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSmall
                }
            }
        }

        // ── main column: pages + action bar ───────────────────────
        Item {
            id: mainCol
            anchors.left: side.right
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom

            // compact progress (narrow layout)
            Row {
                visible: !root.wide
                anchors.top: parent.top
                anchors.topMargin: 18
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 6
                Repeater {
                    model: root.stepCount
                    delegate: Rectangle {
                        required property int index
                        height: 6; radius: 3
                        width: index === root.step ? 26 : 6
                        color: index <= root.step ? Theme.accent : Theme.divider
                        Behavior on width { NumberAnimation { duration: root.motion ? 360 : 0; easing.type: Easing.OutQuint } }
                        Behavior on color { ColorAnimation { duration: root.motion ? 240 : 0 } }
                    }
                }
            }

            Item {
                id: pages
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.bottom: actionBar.top
                anchors.topMargin: root.wide ? 34 : 38
                anchors.leftMargin: root.wide ? 40 : 24
                anchors.rightMargin: root.wide ? 40 : 24
                clip: true

                // ───────────── What's new (after an update) ─────────────
                StepPage {
                    id: newsPage
                    index: root.pageIndex("news")
                    activeStep: root.step
                    motion: root.motion
                    FluentScroll {
                        id: newsScroll
                        anchors.fill: parent
                        roundedClip: false
                        ColumnLayout {
                            width: newsScroll.width
                            spacing: 0

                            Text {
                                Layout.fillWidth: true
                                wrapMode: Text.WordWrap
                                text: I18n.t("Lumen обновлён до версии {version}", { version: App.appVersion })
                                color: Theme.text
                                font.family: Theme.fontFamily
                                font.pixelSize: Math.round(28 * Theme.fontScale)
                                font.weight: Font.DemiBold
                                opacity: newsPage.rv(0)
                                transform: Translate { y: (1 - newsPage.rv(0)) * 16 }
                            }
                            Item { Layout.preferredHeight: 8 }
                            Text {
                                Layout.fillWidth: true
                                wrapMode: Text.WordWrap
                                lineHeight: 1.2
                                text: root.flow.length > 1
                                      ? (root.previousVersion !== ""
                                         ? I18n.t("Предыдущая версия — {version}. Посмотрите, что изменилось, а затем проверим основные настройки.", { version: root.previousVersion })
                                         : I18n.t("Посмотрите, что изменилось, а затем проверим основные настройки."))
                                      : (root.previousVersion !== ""
                                         ? I18n.t("Предыдущая версия — {version}. Вот что изменилось.", { version: root.previousVersion })
                                         : I18n.t("Вот что изменилось в этой версии."))
                                color: Theme.textMuted
                                font.family: Theme.fontFamily
                                font.pixelSize: Math.round(15 * Theme.fontScale)
                                opacity: newsPage.rv(1)
                                transform: Translate { y: (1 - newsPage.rv(1)) * 16 }
                            }

                            Repeater {
                                model: root.newsGroups
                                delegate: ColumnLayout {
                                    id: newsGroup
                                    required property var modelData
                                    required property int index
                                    Layout.fillWidth: true
                                    spacing: 0
                                    opacity: newsPage.rv(3 + index)
                                    transform: Translate { y: (1 - newsPage.rv(3 + index)) * 16 }
                                    SectionLabel {
                                        text: I18n.t("Что нового в {version}", { version: newsGroup.modelData.version })
                                    }
                                    Rectangle {
                                        Layout.fillWidth: true
                                        implicitHeight: notesCol.implicitHeight
                                        radius: Theme.radius + 2
                                        color: Theme.card
                                        border.width: 1
                                        border.color: Theme.divider
                                        ColumnLayout {
                                            id: notesCol
                                            width: parent.width
                                            spacing: 0
                                            Repeater {
                                                model: newsGroup.modelData.items
                                                delegate: NoteRow {
                                                    required property var modelData
                                                    required property int index
                                                    Layout.fillWidth: true
                                                    glyph: modelData.glyph || ""
                                                    title: I18n.t(modelData.title || "")
                                                    text: I18n.t(modelData.text || "")
                                                    iconFont: root.iconFont
                                                    separated: index > 0
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                            Item { Layout.preferredHeight: 8 }
                        }
                    }
                }

                // ───────────── 0 · Welcome ─────────────
                StepPage {
                    id: welcomePage
                    index: root.pageIndex("welcome")
                    activeStep: root.step
                    motion: root.motion
                    FluentScroll {
                        id: welcomeScroll
                        anchors.fill: parent
                        roundedClip: false
                        ColumnLayout {
                            width: welcomeScroll.width
                            spacing: 0

                            Text {
                                Layout.fillWidth: true
                                wrapMode: Text.WordWrap
                                text: root.returning ? I18n.t("С возвращением в Lumen") : I18n.t("Добро пожаловать в Lumen")
                                color: Theme.text
                                font.family: Theme.fontFamily
                                font.pixelSize: Math.round(30 * Theme.fontScale)
                                font.weight: Font.DemiBold
                                opacity: welcomePage.rv(1)
                                transform: Translate { y: (1 - welcomePage.rv(1)) * 18 }
                            }
                            Item { Layout.preferredHeight: 10 }
                            Text {
                                Layout.fillWidth: true
                                wrapMode: Text.WordWrap
                                lineHeight: 1.2
                                text: root.returning
                                      ? I18n.t("Lumen обновлён до версии {version}. Давайте за минуту проверим основные настройки.", { version: App.appVersion })
                                      : I18n.t("Lumen — VPN-клиент для Windows: два ядра, TUN и системный прокси, умная маршрутизация и обход DPI через zapret. Настроим всё за минуту.")
                                color: Theme.textMuted
                                font.family: Theme.fontFamily
                                font.pixelSize: Math.round(15 * Theme.fontScale)
                                opacity: welcomePage.rv(2)
                                transform: Translate { y: (1 - welcomePage.rv(2)) * 18 }
                            }

                            LanguagePicker {
                                Layout.fillWidth: true
                                opacity: welcomePage.rv(3)
                                transform: Translate { y: (1 - welcomePage.rv(3)) * 16 }
                            }

                            SectionLabel { text: I18n.t("Возможности"); opacity: welcomePage.rv(4) }

                            GridLayout {
                                id: featureGrid
                                readonly property real cellHeight: root.tallest(children)
                                Layout.fillWidth: true
                                columns: welcomeScroll.width >= 560 ? 2 : 1
                                columnSpacing: 12
                                rowSpacing: 12
                                Repeater {
                                    model: [
                                        { g: "\uEC05", t: I18n.t("Xray и sing-box"), s: I18n.t("Два ядра и автоматический выбор подходящего") },
                                        { g: "\uE701", t: I18n.t("TUN и системный прокси"), s: I18n.t("Весь трафик системы или только нужные приложения") },
                                        { g: "\uE774", t: I18n.t("Умная маршрутизация"), s: I18n.t("Региональные пресеты и свои правила для сайтов") },
                                        { g: "\uE945", t: "Zapret", s: I18n.t("Обход DPI-блокировок даже без VPN-сервера") }
                                    ]
                                    delegate: FeatureTile {
                                        required property var modelData
                                        required property int index
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: featureGrid.cellHeight
                                        glyph: modelData.g
                                        title: modelData.t
                                        subtitle: modelData.s
                                        iconFont: root.iconFont
                                        opacity: welcomePage.rv(4 + index * 0.6)
                                        transform: Translate { y: (1 - welcomePage.rv(4 + index * 0.6)) * 22 }
                                    }
                                }
                            }
                            Item { Layout.preferredHeight: 8 }
                        }
                    }
                }

                // ───────────── 1 · Appearance ─────────────
                StepPage {
                    id: lookPage
                    index: root.pageIndex("look")
                    activeStep: root.step
                    motion: root.motion
                    FluentScroll {
                        id: lookScroll
                        anchors.fill: parent
                        roundedClip: false
                        ColumnLayout {
                            width: lookScroll.width
                            spacing: 0

                            PageHeader {
                                Layout.fillWidth: true
                                title: I18n.t("Оформление")
                                subtitle: I18n.t("Выберите внешний вид — изменения применяются сразу")
                                opacity: lookPage.rv(0)
                                transform: Translate { y: (1 - lookPage.rv(0)) * 16 }
                            }

                            // Fresh installs pick the language on the first page;
                            // upgraded profiles get it here, next to the look.
                            LanguagePicker {
                                visible: root.flow[0] !== "welcome"
                                Layout.fillWidth: true
                                opacity: lookPage.rv(1)
                                transform: Translate { y: (1 - lookPage.rv(1)) * 16 }
                            }

                            SectionLabel { text: I18n.t("Тема"); opacity: lookPage.rv(2) }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 10
                                opacity: lookPage.rv(2)
                                transform: Translate { y: (1 - lookPage.rv(2)) * 16 }
                                Repeater {
                                    model: root.themeKeys
                                    delegate: ThemeCard {
                                        required property string modelData
                                        Layout.fillWidth: true
                                        mode: modelData
                                        label: root.themeLabel(modelData)
                                        selected: App.themeName === modelData
                                        onClicked: App.setTheme(modelData)
                                    }
                                }
                            }

                            SectionLabel { text: I18n.t("Палитра"); opacity: lookPage.rv(3) }
                            Flow {
                                Layout.fillWidth: true
                                spacing: 10
                                opacity: lookPage.rv(3)
                                transform: Translate { y: (1 - lookPage.rv(3)) * 16 }
                                Repeater {
                                    model: root.paletteKeys
                                    delegate: PaletteSwatch {
                                        required property string modelData
                                        label: root.paletteLabels[modelData]
                                        base: Theme.dark ? Theme._presetMap[modelData].d0 : Theme._lightPresetMap[modelData].bg
                                        surface: Theme.dark ? Theme._presetMap[modelData].d1 : Theme._lightPresetMap[modelData].layer
                                        tint: root.paletteAccents[modelData]
                                        selected: App.uiThemePreset === modelData
                                        onClicked: App.setUiThemePreset(modelData)
                                    }
                                }
                            }

                            SectionLabel { text: I18n.t("Цвет акцента"); opacity: lookPage.rv(4) }
                            Flow {
                                Layout.fillWidth: true
                                spacing: 8
                                opacity: lookPage.rv(4)
                                transform: Translate { y: (1 - lookPage.rv(4)) * 16 }
                                // The system accent comes first and is the default.
                                AccentDot {
                                    id: systemAccentDot
                                    visible: root.windowsAccent !== ""
                                    tint: root.windowsAccent !== "" ? root.windowsAccent : Theme.accent
                                    selected: root.windowsAccent !== "" && root.sameColor(App.accentColor, root.windowsAccent)
                                    onClicked: App.setAccent(root.windowsAccent)
                                }
                                Item {
                                    visible: root.windowsAccent !== ""
                                    width: 9; height: 34
                                    Rectangle {
                                        anchors.centerIn: parent
                                        width: 1; height: 20
                                        color: Theme.divider
                                    }
                                }
                                Repeater {
                                    model: root.accentChoices
                                    delegate: AccentDot {
                                        required property string modelData
                                        tint: modelData
                                        selected: root.sameColor(App.accentColor, modelData)
                                        onClicked: App.setAccent(modelData)
                                    }
                                }
                                CustomAccentDot {
                                    selected: root.customAccent
                                    tint: App.accentColor
                                    onClicked: onboardingAccentDlg.openWith(App.accentColor)
                                }
                            }
                            ColorPickerDialog {
                                id: onboardingAccentDlg
                                showDarkness: true
                                onAccepted: (hex) => App.setAccent(hex)
                            }
                            Item { Layout.preferredHeight: 8 }
                        }
                    }
                }

                // ───────────── 2 · Region & routing ─────────────
                StepPage {
                    id: routePage
                    index: root.pageIndex("route")
                    activeStep: root.step
                    motion: root.motion
                    FluentScroll {
                        id: routeScroll
                        anchors.fill: parent
                        roundedClip: false
                        ColumnLayout {
                            width: routeScroll.width
                            spacing: 0

                            PageHeader {
                                Layout.fillWidth: true
                                title: I18n.t("Регион и маршрутизация")
                                subtitle: I18n.t("Регион определяет списки заблокированных ресурсов и быстрые пресеты маршрутов")
                                opacity: routePage.rv(0)
                                transform: Translate { y: (1 - routePage.rv(0)) * 16 }
                            }

                            RowLayout {
                                SectionLabel { text: I18n.t("Региональный профиль") }
                                BusyIndicator {
                                    visible: App.regionalPresetBusy
                                    running: visible
                                    Layout.preferredWidth: 18
                                    Layout.preferredHeight: 18
                                    Layout.topMargin: 14
                                }
                                opacity: routePage.rv(1)
                            }
                            GridLayout {
                                id: regionGrid
                                readonly property real cellHeight: root.tallest(children)
                                Layout.fillWidth: true
                                columns: routeScroll.width >= 520 ? 3 : 1
                                columnSpacing: 10
                                rowSpacing: 10
                                opacity: routePage.rv(1)
                                transform: Translate { y: (1 - routePage.rv(1)) * 16 }
                                Repeater {
                                    model: [
                                        { key: "russia", code: "RU" },
                                        { key: "china", code: "CN" },
                                        { key: "iran", code: "IR" }
                                    ]
                                    delegate: ChoiceCard {
                                        required property var modelData
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: regionGrid.cellHeight
                                        flagSource: App.countryFlagSource(modelData.code)
                                        badge: flagSource === "" ? modelData.code : ""
                                        title: root.regionLabel(modelData.key)
                                        selected: App.regionalPreset === modelData.key
                                        enabled: !App.regionalPresetBusy
                                        iconFont: root.iconFont
                                        onClicked: if (App.regionalPreset !== modelData.key) App.setRegionalPreset(modelData.key)
                                    }
                                }
                            }

                            SectionLabel { text: I18n.t("Что пускать через VPN"); opacity: routePage.rv(2) }
                            ColumnLayout {
                                id: routingColumn
                                readonly property real cellHeight: root.tallest(children)
                                Layout.fillWidth: true
                                spacing: 10
                                opacity: routePage.rv(2)
                                transform: Translate { y: (1 - routePage.rv(2)) * 16 }
                                Repeater {
                                    model: App.regionalRoutingPresets
                                    delegate: ChoiceCard {
                                        required property var modelData
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: routingColumn.cellHeight
                                        glyph: root.routingGlyph(modelData.id)
                                        title: modelData.name
                                        subtitle: root.routingDescription(modelData.id)
                                        recommended: modelData.id === "blocked" || modelData.id === "blocked_cn"
                                        selected: App.activeRoutingPresetId === modelData.id
                                        iconFont: root.iconFont
                                        onClicked: App.applyRoutingPresetOption(modelData.id)
                                    }
                                }
                            }
                            Item { Layout.preferredHeight: 8 }
                        }
                    }
                }

                // ───────────── 3 · Configs ─────────────
                StepPage {
                    id: cfgPage
                    index: root.pageIndex("configs")
                    activeStep: root.step
                    motion: root.motion
                    FluentScroll {
                        id: cfgScroll
                        anchors.fill: parent
                        roundedClip: false
                        ColumnLayout {
                            width: cfgScroll.width
                            spacing: 0

                            PageHeader {
                                Layout.fillWidth: true
                                title: I18n.t("У вас уже есть VPN-конфигурация?")
                                subtitle: App.onboardingServerCount > 0
                                          ? I18n.t("Серверов в Lumen: {count}. Можно добавить ещё или перейти дальше.", { count: App.onboardingServerCount })
                                          : I18n.t("Ключ, ссылка на подписку или файл конфигурации — Lumen поймёт любой из них")
                                opacity: cfgPage.rv(0)
                                transform: Translate { y: (1 - cfgPage.rv(0)) * 16 }
                            }

                            GridLayout {
                                id: answerGrid
                                readonly property real cellHeight: root.tallest(children)
                                Layout.fillWidth: true
                                Layout.topMargin: 18
                                columns: cfgScroll.width >= 520 ? 2 : 1
                                columnSpacing: 10
                                rowSpacing: 10
                                opacity: cfgPage.rv(1)
                                transform: Translate { y: (1 - cfgPage.rv(1)) * 16 }
                                ChoiceCard {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: answerGrid.cellHeight
                                    glyph: "\uE8B7"
                                    title: I18n.t("Да, есть")
                                    subtitle: I18n.t("Импортирую ключ, подписку или файл")
                                    selected: root.configsAnswered && root.hasConfigs
                                    iconFont: root.iconFont
                                    onClicked: { root.hasConfigs = true; root.configsAnswered = true }
                                }
                                ChoiceCard {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: answerGrid.cellHeight
                                    glyph: "\uEA18"
                                    title: I18n.t("Нет, пока нет")
                                    subtitle: I18n.t("Получу бесплатный WARP прямо здесь")
                                    selected: root.configsAnswered && !root.hasConfigs
                                    iconFont: root.iconFont
                                    onClicked: { root.hasConfigs = false; root.configsAnswered = true }
                                }
                            }

                            // ── import panel ──
                            Reveal {
                                Layout.fillWidth: true
                                gap: 16
                                shownWhen: root.configsAnswered && root.hasConfigs
                                motion: root.motion
                                Card {
                                    width: parent.width
                                    hoverable: false
                                    padding: 18
                                    ColumnLayout {
                                        width: parent.width
                                        spacing: 12
                                        Flow {
                                            Layout.fillWidth: true
                                            spacing: 8
                                            AccentButton {
                                                kind: "accent"
                                                glyph: "\uE77F"
                                                text: I18n.t("Вставить из буфера")
                                                onClicked: App.importClipboard()
                                            }
                                            AccentButton {
                                                kind: "ghost"
                                                glyph: "\uE8E5"
                                                text: I18n.t("Открыть файл")
                                                onClicked: App.importNodeFile()
                                            }
                                        }
                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 8
                                            SearchField {
                                                id: subField
                                                Layout.fillWidth: true
                                                glyph: "\uE71B"
                                                placeholderText: I18n.t("Ссылка на подписку (https://…)")
                                                enabled: !App.subscriptionImporting
                                                onAccepted: addSubButton.clicked()
                                            }
                                            AccentButton {
                                                id: addSubButton
                                                kind: "ghost"
                                                glyph: "\uE71B"
                                                text: I18n.t("Добавить")
                                                enabled: subField.text.trim().length > 0 && !App.subscriptionImporting
                                                onClicked: {
                                                    App.importSubscription(subField.text.trim(), "")
                                                    subField.text = ""
                                                }
                                            }
                                        }
                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 8
                                            BusyIndicator {
                                                visible: App.subscriptionImporting
                                                running: visible
                                                Layout.preferredWidth: 18
                                                Layout.preferredHeight: 18
                                            }
                                            Text {
                                                id: serverCountText
                                                visible: App.onboardingServerCount > 0 && !App.subscriptionImporting
                                                text: "\uE73E"
                                                font.family: root.iconFont
                                                font.pixelSize: 14
                                                color: Theme.success
                                            }
                                            Text {
                                                Layout.fillWidth: true
                                                wrapMode: Text.WordWrap
                                                text: App.subscriptionImporting
                                                      ? I18n.t("Загрузка подписки...")
                                                      : (App.onboardingServerCount > 0
                                                         ? I18n.t("Серверов в Lumen: {count}", { count: App.onboardingServerCount })
                                                         : I18n.t("Файлы .conf, .ovpn, .json и .yaml можно просто перетащить в окно"))
                                                color: App.onboardingServerCount > 0 ? Theme.text : Theme.textFaint
                                                font.family: Theme.fontFamily
                                                font.pixelSize: Theme.fontSmall
                                            }
                                        }
                                    }
                                }
                            }

                            // ── free WARP panel ──
                            Reveal {
                                Layout.fillWidth: true
                                gap: 16
                                shownWhen: root.configsAnswered && !root.hasConfigs
                                motion: root.motion
                                Card {
                                    width: parent.width
                                    hoverable: false
                                    padding: 18
                                    ColumnLayout {
                                        width: parent.width
                                        spacing: 6
                                        Text {
                                            Layout.fillWidth: true
                                            wrapMode: Text.WordWrap
                                            text: I18n.t("Бесплатный Cloudflare WARP")
                                            color: Theme.text
                                            font.family: Theme.fontFamily
                                            font.pixelSize: Math.round(16 * Theme.fontScale)
                                            font.weight: Font.DemiBold
                                        }
                                        Text {
                                            Layout.fillWidth: true
                                            wrapMode: Text.WordWrap
                                            lineHeight: 1.15
                                            text: I18n.t("Lumen зарегистрирует бесплатный профиль WARP и добавит готовые конфигурации AmneziaWG и MASQUE в группу «WARP».")
                                            color: Theme.textMuted
                                            font.family: Theme.fontFamily
                                            font.pixelSize: Theme.fontNormal
                                        }
                                        RowLayout {
                                            Layout.fillWidth: true
                                            Layout.topMargin: 8
                                            spacing: 10
                                            AccentButton {
                                                id: warpButton
                                                kind: App.warpGeneratedCount > 0 ? "ghost" : "accent"
                                                glyph: App.warpGeneratedCount > 0 ? "\uE73E" : "\uE753"
                                                text: App.warpGenerating
                                                      ? I18n.t("Получаем профили…")
                                                      : (App.warpGeneratedCount > 0 ? I18n.t("Профили WARP добавлены") : I18n.t("Получить WARP"))
                                                enabled: !App.warpGenerating && App.warpGeneratedCount === 0
                                                onClicked: App.generateWarpConfigs()
                                            }
                                            BusyIndicator {
                                                visible: App.warpGenerating
                                                running: visible
                                                Layout.preferredWidth: 18
                                                Layout.preferredHeight: 18
                                            }
                                            Text {
                                                Layout.fillWidth: true
                                                wrapMode: Text.WordWrap
                                                text: App.warpGenerating
                                                      ? I18n.t("Обычно это занимает несколько секунд")
                                                      : (App.warpGeneratedCount > 0
                                                         ? I18n.t("Серверов в Lumen: {count}", { count: App.onboardingServerCount })
                                                         : I18n.t("AmneziaWG ×3 и MASQUE ×2 — выберите любой на панели"))
                                                color: App.warpGeneratedCount > 0 && !App.warpGenerating ? Theme.text : Theme.textFaint
                                                font.family: Theme.fontFamily
                                                font.pixelSize: Theme.fontSmall
                                            }
                                        }
                                    }
                                }
                            }
                            Item { Layout.preferredHeight: 8 }
                        }
                    }
                }

                // ───────────── 4 · Done ─────────────
                StepPage {
                    id: donePage
                    index: root.pageIndex("done")
                    activeStep: root.step
                    motion: root.motion
                    FluentScroll {
                        id: doneScroll
                        anchors.fill: parent
                        roundedClip: false
                        ColumnLayout {
                            width: doneScroll.width
                            // Fill the page so the support card sits at the bottom.
                            height: Math.max(implicitHeight, doneScroll.height)
                            spacing: 0

                            Item { Layout.preferredHeight: 6 }
                            Text {
                                Layout.fillWidth: true
                                wrapMode: Text.WordWrap
                                text: I18n.t("Всё готово")
                                color: Theme.text
                                font.family: Theme.fontFamily
                                font.pixelSize: Math.round(30 * Theme.fontScale)
                                font.weight: Font.DemiBold
                                opacity: donePage.rv(1)
                                transform: Translate { y: (1 - donePage.rv(1)) * 16 }
                            }
                            Item { Layout.preferredHeight: 8 }
                            Text {
                                Layout.fillWidth: true
                                wrapMode: Text.WordWrap
                                lineHeight: 1.2
                                text: App.onboardingServerCount > 0
                                      ? I18n.t("Lumen настроен. Выберите сервер на панели и нажмите «Подключить».")
                                      : I18n.t("Lumen настроен. Добавьте сервер, когда он появится, — и можно подключаться.")
                                color: Theme.textMuted
                                font.family: Theme.fontFamily
                                font.pixelSize: Math.round(15 * Theme.fontScale)
                                opacity: donePage.rv(2)
                                transform: Translate { y: (1 - donePage.rv(2)) * 16 }
                            }
                            Item { Layout.preferredHeight: 22 }
                            GridLayout {
                                id: summaryGrid
                                readonly property real cellHeight: root.tallest(children)
                                Layout.fillWidth: true
                                columns: doneScroll.width >= 560 ? 2 : 1
                                columnSpacing: 10
                                rowSpacing: 10
                                Repeater {
                                    model: [
                                        { g: "\uE774", k: I18n.t("Язык"), v: root.languageLabel(), s: root.flow[0] === "welcome" ? 0 : root.pageIndex("look") },
                                        { g: "\uE790", k: I18n.t("Тема"), v: root.themeLabel(App.themeName) + " · " + root.paletteLabel(), s: root.pageIndex("look") },
                                        { g: "\uE909", k: I18n.t("Регион"), v: root.regionLabel(App.regionalPreset), s: root.pageIndex("route") },
                                        { g: "\uE72E", k: I18n.t("Маршрутизация"), v: root.routingLabel(), s: root.pageIndex("route") }
                                    ]
                                    delegate: SummaryRow {
                                        required property var modelData
                                        required property int index
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: summaryGrid.cellHeight
                                        glyph: modelData.g
                                        key: modelData.k
                                        value: modelData.v
                                        iconFont: root.iconFont
                                        onClicked: if (modelData.s >= 0) root.step = modelData.s
                                        opacity: donePage.rv(3 + index * 0.5)
                                        transform: Translate { y: (1 - donePage.rv(3 + index * 0.5)) * 16 }
                                    }
                                }
                            }
                            Item { Layout.fillHeight: true; Layout.minimumHeight: 32 }
                            SupportCard {
                                Layout.fillWidth: true
                                opacity: donePage.rv(5.5)
                                transform: Translate { y: (1 - donePage.rv(5.5)) * 16 }
                            }
                            Item { Layout.preferredHeight: 12 }
                        }
                    }
                }
            }

            // ── action bar ──
            Item {
                id: actionBar
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: 76
                Rectangle { anchors.top: parent.top; width: parent.width; height: 1; color: Theme.divider }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: root.wide ? 40 : 24
                    anchors.rightMargin: root.wide ? 40 : 24
                    spacing: 10

                    AccentButton {
                        kind: "ghost"
                        text: I18n.t("Пропустить")
                        visible: !root.lastStep
                        flat: true
                        onClicked: root.finish()
                    }
                    Item { Layout.fillWidth: true }
                    AccentButton {
                        kind: "ghost"
                        glyph: "\uE72B"
                        text: I18n.t("Назад")
                        opacity: root.step > 0 ? 1 : 0
                        enabled: root.step > 0
                        Behavior on opacity { NumberAnimation { duration: root.motion ? 200 : 0 } }
                        onClicked: root.back()
                    }
                    AccentButton {
                        id: primaryButton
                        kind: "accent"
                        glyph: root.lastStep ? "\uE73E" : ""
                        text: root.lastStep ? I18n.t("Открыть Lumen")
                              : (root.step === 0 && root.flow[0] === "welcome" ? I18n.t("Начать") : I18n.t("Далее"))
                        Layout.minimumWidth: 132
                        onClicked: root.next()
                    }
                }
            }
        }

        // Border on top of everything, following the rounded outline.
        Rectangle {
            id: cardBorder
            anchors.fill: parent
            radius: parent.radius
            color: "transparent"
            border.width: 1
            border.color: Theme.flyoutBorder
        }
    }
    } // cardLayer

    // =====================================================================
    // Inline components
    // =====================================================================

    // One onboarding step. Pages before the active one rest to the left,
    // pages after it to the right, so navigation always slides directionally.
    // `reveal` drives a staggered entrance of the page contents (rv()).
    // "Support Lumen" block on the last page: GitHub star and donations.
    component SupportCard: Rectangle {
        id: sup
        readonly property string repoUrl: "https://github.com/krambovic/Lumen"
        readonly property string donateUrl: "https://www.donationalerts.com/r/studiobebraedition"
        readonly property string usdtAddress: "TWHsuUDru4pXBcGpfeKfzymbkfajyFnb2s"
        property bool donateOpen: false
        implicitHeight: supCol.implicitHeight + 32
        radius: Theme.radius + 2
        color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, Theme.dark ? 0.08 : 0.05)
        border.width: 1
        border.color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.35)
        Behavior on implicitHeight { NumberAnimation { duration: root.motion ? 260 : 0; easing.type: Easing.OutCubic } }
        clip: true
        ColumnLayout {
            id: supCol
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 16
            spacing: 12
            RowLayout {
                Layout.fillWidth: true
                spacing: 12
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3
                    Text {
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        text: I18n.t("Нравится Lumen?")
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontNormal
                        font.weight: Font.DemiBold
                    }
                    Text {
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        lineHeight: 1.15
                        text: I18n.t("Lumen бесплатный и с открытым кодом. Поставьте звезду на GitHub — так о проекте узнает больше людей. А если хотите помочь развитию — поддержите проект.")
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSmall
                    }
                }
            }
            Flow {
                Layout.fillWidth: true
                spacing: 8
                AccentButton {
                    kind: "accent"
                    glyph: "\uE734"
                    text: I18n.t("Поставить звезду на GitHub")
                    onClicked: App.openUrl(sup.repoUrl)
                }
                AccentButton {
                    kind: "ghost"
                    glyph: "\uEB52"
                    text: I18n.t("Поддержать проект")
                    onClicked: sup.donateOpen = !sup.donateOpen
                }
            }
            Flow {
                Layout.fillWidth: true
                visible: sup.donateOpen
                spacing: 8
                AccentButton {
                    kind: "ghost"
                    glyph: "\uE8F1"
                    text: "DonationAlerts"
                    onClicked: App.openUrl(sup.donateUrl)
                }
                AccentButton {
                    kind: "ghost"
                    glyph: "\uE8C8"
                    text: I18n.t("Скопировать адрес USDT (TRC20)")
                    onClicked: App.copyText(sup.usdtAddress)
                }
            }
        }
    }

    component StepPage: Item {
        id: sp
        property int index: 0
        property int activeStep: 0
        property bool motion: true
        readonly property bool current: index === activeStep
        property real reveal: 0
        anchors.fill: parent
        visible: opacity > 0.001
        opacity: current ? 1 : 0
        enabled: current
        transform: Translate {
            x: sp.current ? 0 : (sp.index < sp.activeStep ? -56 : 56)
            Behavior on x { NumberAnimation { duration: sp.motion ? 520 : 0; easing.type: Easing.OutQuint } }
        }
        Behavior on opacity { NumberAnimation { duration: sp.motion ? 300 : 0; easing.type: Easing.OutCubic } }

        function rv(order) {
            var v = (reveal - order * 0.085) / 0.42
            v = Math.max(0, Math.min(1, v))
            return 1 - Math.pow(1 - v, 3)
        }
        NumberAnimation {
            id: revealAnim
            target: sp
            property: "reveal"
            from: 0; to: 1
            duration: sp.motion ? 1100 : 0
        }
        onCurrentChanged: if (current) revealAnim.restart()
        Component.onCompleted: if (current) revealAnim.restart()
    }

    // Collapsible block that fades/slides in when `shownWhen` turns true.
    component Reveal: Item {
        id: rvl
        property bool shownWhen: false
        property bool motion: true
        default property alias content: holder.data
        // Space above the block. It grows and shrinks together with the block,
        // so a neighbouring panel never jumps when this one appears or hides.
        property real gap: 0
        property real level: shownWhen ? 1 : 0
        Behavior on level { NumberAnimation { duration: rvl.motion ? 420 : 0; easing.type: Easing.OutCubic } }
        implicitHeight: (holder.childrenRect.height + gap) * level
        Layout.preferredHeight: implicitHeight
        visible: level > 0.001
        clip: true
        Item {
            id: holder
            width: rvl.width
            height: childrenRect.height
            opacity: rvl.level
            y: rvl.gap * rvl.level + (1 - rvl.level) * -12
        }
    }

    component PageHeader: ColumnLayout {
        property string title: ""
        property string subtitle: ""
        spacing: 6
        Text {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            text: parent.title
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Math.round(24 * Theme.fontScale)
            font.weight: Font.DemiBold
        }
        Text {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            visible: text.length > 0
            text: parent.subtitle
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontNormal
            lineHeight: 1.15
        }
    }

    component SectionLabel: Text {
        Layout.topMargin: 22
        Layout.bottomMargin: 10
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSmall
        font.weight: Font.DemiBold
        font.capitalization: Font.AllUppercase
        font.letterSpacing: 0.6
    }

    // Lumen "L" mark, drawn as a vector so it follows the palette.
    component LumenMark: Item {
        id: mark
        property color ink: Theme.text
        property real level: 1
        Item {
            anchors.fill: parent
            // wipe-in: the stem appears top→bottom, then the foot extends
            Item {
                id: wipe
                width: parent.width
                height: parent.height * Math.min(1, mark.level * 1.25)
                clip: true
                Shape {
                    width: mark.width
                    height: mark.height
                    preferredRendererType: Shape.CurveRenderer
                    ShapePath {
                        strokeWidth: -1
                        fillColor: mark.ink
                        scale: Qt.size(mark.width / 100, mark.height / 100)
                        startX: 24; startY: 24
                        PathLine { x: 37.5; y: 10 }
                        PathLine { x: 37.5; y: 74 }
                        PathLine { x: 85; y: 74 }
                        PathLine { x: 72.5; y: 87.5 }
                        PathLine { x: 24; y: 87.5 }
                        PathLine { x: 24; y: 24 }
                    }
                }
            }
        }
    }

    // Accent circle with a check that pops in.
    component SuccessMark: Item {
        id: sm
        property color tint: Theme.accent
        property color ink: Theme.accentText
        property real level: 1
        Rectangle {
            anchors.centerIn: parent
            width: parent.width; height: width; radius: width / 2
            color: sm.tint
            scale: 0.6 + 0.4 * sm.level
            opacity: Math.min(1, sm.level * 2)
            Text {
                anchors.centerIn: parent
                text: "\uE73E"
                font.family: "Segoe Fluent Icons"
                font.pixelSize: Math.round(sm.width * 0.42)
                color: sm.ink
                scale: Math.max(0, (sm.level - 0.35) / 0.65)
            }
        }
    }

    component FeatureTile: Rectangle {
        id: ft
        property string glyph: ""
        property string title: ""
        property string subtitle: ""
        property string iconFont: "Segoe Fluent Icons"
        implicitHeight: ftRow.implicitHeight + 28
        radius: Theme.radius + 2
        color: ftHover.hovered ? Theme.cardHover : Theme.card
        border.width: 1
        border.color: Theme.divider
        Behavior on color { ColorAnimation { duration: Theme.animFast } }
        HoverHandler { id: ftHover }
        RowLayout {
            id: ftRow
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            anchors.margins: 14
            spacing: 14
            Text {
                Layout.alignment: Qt.AlignTop
                Layout.topMargin: 2
                Layout.preferredWidth: 22
                text: ft.glyph
                font.family: ft.iconFont
                font.pixelSize: 18
                color: Theme.accent
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 3
                Text { text: ft.title; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontNormal; font.weight: Font.DemiBold; Layout.fillWidth: true; elide: Text.ElideRight }
                Text { text: ft.subtitle; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            }
        }
    }

    // Selectable card (region / routing / yes-no).
    component ChoiceCard: Rectangle {
        id: cc
        property string glyph: ""
        property string badge: ""
        property string flagSource: ""
        property string title: ""
        property string subtitle: ""
        property bool selected: false
        property bool recommended: false
        property string iconFont: "Segoe Fluent Icons"
        signal clicked()
        implicitHeight: Math.max(60, ccRow.implicitHeight + 26)
        radius: Theme.radius + 2
        color: cc.selected
               ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, Theme.dark ? 0.10 : 0.06)
               : (ccTap.pressed ? Theme.cardPressed : (ccHover.hovered ? Theme.cardHover : Theme.card))
        border.width: cc.selected ? 2 : 1
        border.color: cc.selected ? Theme.accent : Theme.divider
        opacity: enabled ? 1 : 0.55
        scale: ccTap.pressed ? 0.985 : 1
        Behavior on color { ColorAnimation { duration: Theme.animNormal } }
        Behavior on border.color { ColorAnimation { duration: Theme.animNormal } }
        Behavior on scale { NumberAnimation { duration: Theme.animFast; easing.type: Easing.OutCubic } }
        HoverHandler { id: ccHover; cursorShape: Qt.PointingHandCursor }
        TapHandler { id: ccTap; onTapped: cc.clicked() }

        RowLayout {
            id: ccRow
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            anchors.leftMargin: 16
            anchors.rightMargin: 16
            spacing: 14
            Item {
                visible: cc.flagSource !== ""
                Layout.preferredWidth: 36
                Layout.preferredHeight: 36
                Image {
                    id: ccFlag
                    anchors.centerIn: parent
                    width: 30
                    height: 22
                    source: cc.flagSource
                    sourceSize.width: 60
                    sourceSize.height: 44
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                    mipmap: true
                }
                // Hairline so white flag stripes stay visible on light cards.
                Rectangle {
                    anchors.centerIn: parent
                    width: ccFlag.paintedWidth + 2
                    height: ccFlag.paintedHeight + 2
                    radius: 3
                    color: "transparent"
                    border.width: 1
                    border.color: Theme.divider
                    visible: ccFlag.status === Image.Ready
                }
            }
            Rectangle {
                visible: cc.flagSource === "" && (cc.glyph !== "" || cc.badge !== "")
                Layout.preferredWidth: 36
                Layout.preferredHeight: 36
                radius: 10
                color: cc.selected ? Theme.accent : Theme.controlFill
                border.width: cc.selected ? 0 : 1
                border.color: Theme.divider
                Behavior on color { ColorAnimation { duration: Theme.animNormal } }
                Text {
                    anchors.centerIn: parent
                    text: cc.badge !== "" ? cc.badge : cc.glyph
                    font.family: cc.badge !== "" ? Theme.fontFamily : cc.iconFont
                    font.pixelSize: cc.badge !== "" ? 13 : 16
                    font.weight: Font.DemiBold
                    color: cc.selected ? Theme.accentText : Theme.textMuted
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 3
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Text { text: cc.title; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontNormal; font.weight: Font.DemiBold }
                    Rectangle {
                        visible: cc.recommended
                        implicitWidth: recText.implicitWidth + 14
                        implicitHeight: recText.implicitHeight + 4
                        radius: height / 2
                        color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.18)
                        Text { id: recText; anchors.centerIn: parent; text: I18n.t("Рекомендуем"); color: Theme.accent; font.family: Theme.fontFamily; font.pixelSize: Math.round(11 * Theme.fontScale); font.weight: Font.DemiBold }
                    }
                }
                Text {
                    visible: cc.subtitle !== ""
                    Layout.fillWidth: true
                    text: cc.subtitle
                    wrapMode: Text.WordWrap
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSmall
                }
            }
            // radio indicator
            Rectangle {
                Layout.preferredWidth: 20
                Layout.preferredHeight: 20
                radius: 10
                color: "transparent"
                border.width: cc.selected ? 6 : 1.5
                border.color: cc.selected ? Theme.accent : Theme.textFaint
                Behavior on border.width { NumberAnimation { duration: Theme.animNormal; easing.type: Easing.OutBack } }
            }
        }
    }

    // Interface language. Switching applies live: every I18n.t() binding in
    // the flow re-evaluates when App.translations changes.
    component LanguagePicker: ColumnLayout {
        spacing: 0
        SectionLabel { text: I18n.t("Язык интерфейса") }
        Flow {
            Layout.fillWidth: true
            spacing: 8
            Repeater {
                model: App.availableLanguages
                delegate: Chip {
                    required property string modelData
                    required property int index
                    text: App.languageLabels[index]
                    selected: App.language === modelData
                    onClicked: App.setLanguage(modelData)
                }
            }
        }
    }

    // One "What's new" entry: glyph, title and a short description.
    component NoteRow: Item {
        id: nr
        property string glyph: ""
        property string title: ""
        property string text: ""
        property string iconFont: "Segoe Fluent Icons"
        property bool separated: false
        implicitHeight: nrRow.implicitHeight + 28
        Rectangle {
            visible: nr.separated
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: 16
            anchors.rightMargin: 16
            height: 1
            color: Theme.divider
        }
        RowLayout {
            id: nrRow
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            anchors.leftMargin: 16
            anchors.rightMargin: 16
            spacing: 14
            Text {
                Layout.alignment: Qt.AlignTop
                Layout.topMargin: 2
                Layout.preferredWidth: 22
                text: nr.glyph
                font.family: nr.iconFont
                font.pixelSize: 18
                color: Theme.accent
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 3
                Text { text: nr.title; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontNormal; font.weight: Font.DemiBold; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Text { text: nr.text; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall; wrapMode: Text.WordWrap; lineHeight: 1.15; Layout.fillWidth: true }
            }
        }
    }

    component Chip: Rectangle {
        id: chip
        property string text: ""
        property string dot: ""
        property bool selected: false
        signal clicked()
        implicitHeight: 34
        implicitWidth: chipRow.implicitWidth + 28
        radius: height / 2
        color: chip.selected ? Theme.accent : (chipHover.hovered ? Theme.cardHover : Theme.card)
        border.width: chip.selected ? 0 : 1
        border.color: Theme.divider
        scale: chipTap.pressed ? 0.96 : 1
        Behavior on color { ColorAnimation { duration: Theme.animNormal } }
        Behavior on scale { NumberAnimation { duration: Theme.animFast } }
        HoverHandler { id: chipHover; cursorShape: Qt.PointingHandCursor }
        TapHandler { id: chipTap; onTapped: chip.clicked() }
        Row {
            id: chipRow
            anchors.centerIn: parent
            spacing: 8
            Rectangle {
                visible: chip.dot !== ""
                width: 14; height: 14; radius: 7
                anchors.verticalCenter: parent.verticalCenter
                color: chip.dot !== "" ? chip.dot : "transparent"
                border.width: 2
                border.color: chip.selected ? Theme.accentText : Theme.flyoutBorder
            }
            Text {
                text: chip.text
                anchors.verticalCenter: parent.verticalCenter
                color: chip.selected ? Theme.accentText : Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontNormal
                font.weight: chip.selected ? Font.DemiBold : Font.Normal
            }
        }
    }

    // Own accent colour: a quiet "+" until a custom colour is picked.
    component CustomAccentDot: Item {
        id: cad
        property color tint: Theme.accent
        property bool selected: false
        signal clicked()
        width: 34; height: 34
        Rectangle {
            anchors.centerIn: parent
            width: 34; height: 34; radius: 17
            color: "transparent"
            border.width: 2
            border.color: cad.selected ? Theme.text : "transparent"
            Behavior on border.color { ColorAnimation { duration: Theme.animNormal } }
        }
        Rectangle {
            anchors.centerIn: parent
            width: cad.selected ? 24 : 26; height: width; radius: width / 2
            color: cad.selected ? cad.tint : Theme.controlFill
            border.width: cad.selected ? 0 : 1
            border.color: Theme.divider
            scale: cadTap.pressed ? 0.88 : (cadHover.hovered ? 1.08 : 1)
            Behavior on scale { NumberAnimation { duration: Theme.animFast; easing.type: Easing.OutBack } }
            Behavior on width { NumberAnimation { duration: Theme.animNormal } }
            Text {
                anchors.centerIn: parent
                text: cad.selected ? "\uE70F" : "\uE710"
                font.family: "Segoe Fluent Icons"
                font.pixelSize: cad.selected ? 10 : 11
                color: cad.selected ? Theme.accentText : Theme.textMuted
            }
        }
        HoverHandler { id: cadHover; cursorShape: Qt.PointingHandCursor }
        TapHandler { id: cadTap; onTapped: cad.clicked() }
        FluentToolTip {
            visible: cadHover.hovered
            text: I18n.t("Свой цвет")
        }
    }

    component AccentDot: Item {
        id: ad
        property color tint: "#0078D4"
        property bool selected: false
        signal clicked()
        width: 34; height: 34
        Rectangle {
            anchors.centerIn: parent
            width: 34; height: 34; radius: 17
            color: "transparent"
            border.width: 2
            border.color: ad.selected ? Theme.text : "transparent"
            Behavior on border.color { ColorAnimation { duration: Theme.animNormal } }
        }
        Rectangle {
            anchors.centerIn: parent
            width: ad.selected ? 24 : 26; height: width; radius: width / 2
            color: ad.tint
            scale: adTap.pressed ? 0.88 : (adHover.hovered ? 1.08 : 1)
            Behavior on scale { NumberAnimation { duration: Theme.animFast; easing.type: Easing.OutBack } }
            Behavior on width { NumberAnimation { duration: Theme.animNormal } }
        }
        HoverHandler { id: adHover; cursorShape: Qt.PointingHandCursor }
        TapHandler { id: adTap; onTapped: ad.clicked() }
    }

    component MiniWindow: Rectangle {
        property bool darkLook: false
        radius: 6
        color: darkLook ? "#202020" : "#F3F3F3"
        border.width: 1
        border.color: darkLook ? "#3A3A3A" : "#D6D6D6"
        Rectangle { x: 6; y: 6; width: parent.width * 0.22; height: parent.height - 12; radius: 3; color: darkLook ? "#2C2C2C" : "#FFFFFF" }
        Rectangle { x: parent.width * 0.22 + 12; y: 8; width: parent.width * 0.42; height: 6; radius: 3; color: Theme.accent }
        Rectangle { x: parent.width * 0.22 + 12; y: 20; width: parent.width * 0.62 - 18; height: 5; radius: 2.5; color: darkLook ? "#4A4A4A" : "#DADADA" }
        Rectangle { x: parent.width * 0.22 + 12; y: 30; width: parent.width * 0.46 - 18; height: 5; radius: 2.5; color: darkLook ? "#4A4A4A" : "#DADADA" }
    }

    // Mini window preview for system / light / dark.
    component ThemeCard: Rectangle {
        id: tc
        property string mode: "system"
        property string label: ""
        property bool selected: false
        signal clicked()
        implicitHeight: 112
        radius: Theme.radius + 2
        color: tcHover.hovered ? Theme.cardHover : Theme.card
        border.width: tc.selected ? 2 : 1
        border.color: tc.selected ? Theme.accent : Theme.divider
        scale: tcTap.pressed ? 0.98 : 1
        Behavior on border.color { ColorAnimation { duration: Theme.animNormal } }
        Behavior on scale { NumberAnimation { duration: Theme.animFast } }
        HoverHandler { id: tcHover; cursorShape: Qt.PointingHandCursor }
        TapHandler { id: tcTap; onTapped: tc.clicked() }

        Item {
            id: preview
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.margins: 10
            height: 62
            MiniWindow { anchors.fill: parent; darkLook: tc.mode === "dark"; visible: tc.mode !== "system" }
            Item {
                anchors.fill: parent
                visible: tc.mode === "system"
                clip: true
                MiniWindow { width: preview.width; height: preview.height; darkLook: false }
                Item {
                    x: preview.width / 2; width: preview.width / 2; height: preview.height; clip: true
                    MiniWindow { x: -preview.width / 2; width: preview.width; height: preview.height; darkLook: true }
                }
            }
        }
        Text {
            anchors.left: parent.left
            anchors.leftMargin: 12
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 11
            text: tc.label
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontNormal
            font.weight: tc.selected ? Font.DemiBold : Font.Normal
        }
        Rectangle {
            anchors.right: parent.right
            anchors.rightMargin: 12
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 11
            width: 18; height: 18; radius: 9
            color: "transparent"
            border.width: tc.selected ? 5 : 1.5
            border.color: tc.selected ? Theme.accent : Theme.textFaint
            Behavior on border.width { NumberAnimation { duration: Theme.animNormal; easing.type: Easing.OutBack } }
        }
    }

    component PaletteSwatch: Item {
        id: ps
        property string label: ""
        property color base: "#202020"
        property color surface: "#2C2C2C"
        property color tint: "#0078D4"
        property bool selected: false
        signal clicked()
        width: 92
        height: 84
        Rectangle {
            id: psBox
            width: parent.width
            height: 56
            radius: Theme.radius + 1
            color: ps.base
            border.width: ps.selected ? 2 : 1
            border.color: ps.selected ? Theme.accent : Theme.flyoutBorder
            scale: psTap.pressed ? 0.95 : (psHover.hovered ? 1.04 : 1)
            Behavior on scale { NumberAnimation { duration: Theme.animFast; easing.type: Easing.OutCubic } }
            Behavior on border.color { ColorAnimation { duration: Theme.animNormal } }
            Rectangle { x: 8; y: 8; width: parent.width - 16; height: 18; radius: 5; color: ps.surface }
            Rectangle { x: 8; y: 32; width: 30; height: 14; radius: 7; color: ps.tint }
            Rectangle { x: 44; y: 36; width: parent.width - 52; height: 6; radius: 3; color: ps.surface }
            Rectangle {
                visible: ps.selected
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: -6
                width: 20; height: 20; radius: 10
                color: Theme.accent
                Text { anchors.centerIn: parent; text: "\uE73E"; font.family: "Segoe Fluent Icons"; font.pixelSize: 10; color: Theme.accentText }
            }
        }
        Text {
            anchors.top: psBox.bottom
            anchors.topMargin: 6
            anchors.horizontalCenter: parent.horizontalCenter
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideRight
            text: ps.label
            color: ps.selected ? Theme.text : Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSmall
        }
        HoverHandler { id: psHover; cursorShape: Qt.PointingHandCursor }
        TapHandler { id: psTap; onTapped: ps.clicked() }
    }

    component SummaryRow: Rectangle {
        id: sr
        property string glyph: ""
        property string key: ""
        property string value: ""
        property string iconFont: "Segoe Fluent Icons"
        signal clicked()
        implicitHeight: 58
        radius: Theme.radius + 2
        color: srHover.hovered ? Theme.cardHover : Theme.card
        border.width: 1
        border.color: Theme.divider
        Behavior on color { ColorAnimation { duration: Theme.animFast } }
        HoverHandler { id: srHover; cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: sr.clicked() }
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 14
            anchors.rightMargin: 14
            spacing: 12
            Text { text: sr.glyph; font.family: sr.iconFont; font.pixelSize: 16; color: Theme.accent }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 1
                Text { text: sr.key; color: Theme.textFaint; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall }
                Text { text: sr.value; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontNormal; font.weight: Font.DemiBold; elide: Text.ElideRight; Layout.fillWidth: true }
            }
            Text { text: "\uE70F"; font.family: sr.iconFont; font.pixelSize: 12; color: Theme.textFaint; opacity: srHover.hovered ? 1 : 0; Behavior on opacity { NumberAnimation { duration: Theme.animFast } } }
        }
    }
}
