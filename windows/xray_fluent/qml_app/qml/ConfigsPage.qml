import QtQuick
import QtQuick.Controls.Universal
import QtQuick.Layouts
import App 1.0
import "."

// Raw sing-box / xray config editor.
//   header  : title + core switch
//   source  : active config file and template (with import/reset)
//   editor  : file toolbar, code editor with line numbers, status bar
Item {
    id: page

    property string core: "singbox"

    // ---- live per-core editor state -------------------------------------
    property var cache: ({})          // core -> snapshot (preserves unsaved edits)
    property bool loaded: false
    property string fileLabel: "--"
    property string templateLabel: "--"
    property bool hasTemplate: false
    property var configItems: []
    property var templateItems: []
    property string activeConfig: ""
    property string activeTemplate: ""
    property string statusLevel: ""
    property string statusMessage: ""
    property string savedText: ""
    readonly property bool dirty: editor.text !== page.savedText
    readonly property int errorLine: _errorLine(page.statusLevel, page.statusMessage)

    property var _pendingAction: null

    component StyledCombo: FluentCombo {}

    component FieldLabel: Text {
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontNormal
        Layout.preferredWidth: 72
        elide: Text.ElideRight
    }

    function _indexOfValue(items, value) {
        for (var i = 0; i < items.length; i++)
            if (items[i].value === value)
                return i
        return 0
    }

    function _labels(items) {
        var out = []
        for (var i = 0; i < items.length; i++)
            out.push(items[i].label)
        return out
    }

    function _levelColor(level) {
        return level === "success" ? Theme.success
             : level === "warning" ? Theme.warning
             : level === "error" ? Theme.danger
             : Theme.textMuted
    }

    function _levelGlyph(level) {
        return level === "success" ? "\uE73E"
             : level === "warning" ? "\uE7BA"
             : level === "error" ? "\uEA39"
             : "\uE946"
    }

    // JSON errors from the bridge mention the line: "строка 12" / "line 12".
    function _errorLine(level, message) {
        if (level !== "error" || !message)
            return 0
        var m = /(?:строк[аеи]|line)\s*:?\s*(\d+)/i.exec(message)
        return m ? parseInt(m[1]) : 0
    }

    function _syncCombos() {
        configCombo.currentIndex = page.configItems.length > 0
            ? _indexOfValue(page.configItems, page.activeConfig) : 0
        templateCombo.currentIndex = page.templateItems.length > 0
            ? _indexOfValue(page.templateItems, page.activeTemplate) : 0
    }

    // Full editor state coming from build_state() on the bridge.
    function _ingest(st) {
        if (!st)
            return
        page.fileLabel = (st.fileLabel && st.fileLabel.length) ? st.fileLabel : "--"
        page.templateLabel = (st.templateLabel && st.templateLabel.length) ? st.templateLabel : "--"
        page.hasTemplate = st.hasTemplate === true
        page.configItems = st.configItems || []
        page.templateItems = st.templateItems || []
        page.activeConfig = st.activeConfig || ""
        page.activeTemplate = st.activeTemplate || ""
        page.statusLevel = st.statusLevel || ""
        page.statusMessage = st.statusMessage || ""
        editor.text = st.text || ""
        page.savedText = editor.text
        page.loaded = true
        _syncCombos()
    }

    // Lighter status-only result (validate / apply).
    function _ingestStatus(st) {
        if (!st)
            return
        page.statusLevel = st.statusLevel || ""
        page.statusMessage = st.statusMessage || ""
        if (st.fileLabel && st.fileLabel.length)
            page.fileLabel = st.fileLabel
    }

    function _snapshot() {
        return {
            "text": editor.text, "savedText": page.savedText,
            "statusLevel": page.statusLevel, "statusMessage": page.statusMessage,
            "fileLabel": page.fileLabel, "templateLabel": page.templateLabel,
            "hasTemplate": page.hasTemplate, "configItems": page.configItems,
            "templateItems": page.templateItems, "activeConfig": page.activeConfig,
            "activeTemplate": page.activeTemplate, "loaded": page.loaded
        }
    }

    function _applySnapshot(s) {
        page.fileLabel = s.fileLabel
        page.templateLabel = s.templateLabel
        page.hasTemplate = s.hasTemplate
        page.configItems = s.configItems
        page.templateItems = s.templateItems
        page.activeConfig = s.activeConfig
        page.activeTemplate = s.activeTemplate
        page.statusLevel = s.statusLevel
        page.statusMessage = s.statusMessage
        page.savedText = s.savedText
        page.loaded = s.loaded
        editor.text = s.text
        _syncCombos()
    }

    function loadCore(c) {
        _ingest(App.loadConfig(c))
    }

    function switchCore(c) {
        if (c === page.core)
            return
        page.cache[page.core] = _snapshot()
        page.core = c
        if (page.cache[c] !== undefined) {
            _applySnapshot(page.cache[c])
            if (!page.loaded)
                loadCore(c)
        } else {
            loadCore(c)
        }
    }

    // ---- discard confirmation -------------------------------------------
    function _guard(action) {
        if (page.dirty) {
            page._pendingAction = action
            confirmOverlay.visible = true
        } else {
            action()
        }
    }
    function _confirmYes() {
        confirmOverlay.visible = false
        var a = page._pendingAction
        page._pendingAction = null
        if (a)
            a()
    }
    function _confirmNo() {
        confirmOverlay.visible = false
        page._pendingAction = null
    }

    // ---- actions ---------------------------------------------------------
    function doSelectConfig(index) {
        var item = page.configItems[index]
        if (!item) { _syncCombos(); return }
        _guard(function() { _ingest(App.selectConfig(page.core, item.value)) })
    }
    function doSelectTemplate(index) {
        var item = page.templateItems[index]
        if (!item) { _syncCombos(); return }
        _guard(function() { _ingest(App.selectTemplate(page.core, item.value)) })
    }
    function doImportTemplate() {
        _guard(function() {
            var st = App.importTemplate(page.core)
            if (st && st.cancelled === true)
                return
            _ingest(st)
        })
    }
    function doReset() {
        if (!page.hasTemplate)
            return
        _guard(function() { _ingest(App.resetConfig(page.core)) })
    }
    function doRevert() {
        editor.text = page.savedText
    }
    function doSave() {
        _ingest(App.saveConfig(page.core, editor.text, page.savedText))
    }
    function doValidate() {
        _ingestStatus(App.validateConfig(page.core, editor.text))
    }
    function doFormat() {
        var parsed
        try {
            parsed = JSON.parse(editor.text)
        } catch (e) {
            // Let the bridge report the exact position of the error.
            doValidate()
            return
        }
        var formatted = JSON.stringify(parsed, null, 2)
        if (formatted !== editor.text) {
            editor.text = formatted
            page.statusLevel = "info"
            page.statusMessage = I18n.t("JSON отформатирован — не забудьте сохранить")
        }
    }
    function doApply() {
        var st = App.applyConfig(page.core, editor.text, page.savedText)
        _ingestStatus(st)
        if (st && st.statusLevel !== "error")
            page.savedText = editor.text
    }

    Component.onCompleted: if (!page.loaded) loadCore(page.core)

    Shortcut {
        sequences: [StandardKey.Save]
        enabled: page.visible && page.loaded && !confirmOverlay.visible
        onActivated: page.doSave()
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.spacing

        // ---- header: title + core switch ----
        RowLayout {
            Layout.fillWidth: true
            spacing: 12
            Text {
                text: I18n.t("Конфиги")
                color: Theme.text; font.family: Theme.fontFamily
                font.pixelSize: Theme.fontTitle; font.weight: Font.DemiBold
            }
            Item { Layout.fillWidth: true }
            Rectangle {
                implicitWidth: coreRow.implicitWidth + 6
                implicitHeight: 34
                radius: Theme.radiusSmall
                color: Theme.controlFill
                border.width: 1; border.color: Theme.borderSolid
                Row {
                    id: coreRow
                    anchors.centerIn: parent
                    spacing: 2
                    Repeater {
                        model: [{ key: "singbox", label: "sing-box" }, { key: "xray", label: "Xray" }]
                        delegate: Rectangle {
                            width: 104; height: 28
                            readonly property bool active: page.core === modelData.key
                            radius: Theme.radiusSmall - 1
                            color: active ? Theme.card : (coreTabMouse.containsMouse ? Theme.navHover : "transparent")
                            border.width: active ? 1 : 0
                            border.color: Theme.borderSolid
                            Behavior on color { ColorAnimation { duration: Theme.animations ? 120 : 0 } }
                            Text {
                                anchors.centerIn: parent
                                text: modelData.label
                                font.family: Theme.fontFamily; font.pixelSize: Theme.fontNormal
                                font.weight: parent.active ? Font.DemiBold : Font.Normal
                                color: parent.active ? Theme.text : Theme.textMuted
                            }
                            MouseArea {
                                id: coreTabMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: page.switchCore(modelData.key)
                            }
                        }
                    }
                }
            }
        }

        // ---- source: config file + template ----
        Card {
            Layout.fillWidth: true
            padding: 14
            hoverable: false
            GridLayout {
                width: parent.width
                columns: 3
                columnSpacing: 10
                rowSpacing: 10

                FieldLabel { text: I18n.t("Конфиг") }
                StyledCombo {
                    id: configCombo
                    enabled: page.configItems.length > 0
                    Layout.fillWidth: true
                    model: page.configItems.length > 0 ? page._labels(page.configItems) : [I18n.t("Нет конфигов")]
                    onActivated: page.doSelectConfig(configCombo.currentIndex)
                }
                AccentButton {
                    kind: "ghost"
                    glyph: "\uE838"
                    text: I18n.t("Папка")
                    tip: I18n.t("Открыть папку конфигов")
                    onClicked: App.openConfigDirectory(page.core)
                }

                FieldLabel { text: I18n.t("Шаблон") }
                StyledCombo {
                    id: templateCombo
                    enabled: page.templateItems.length > 0
                    Layout.fillWidth: true
                    model: page.templateItems.length > 0 ? page._labels(page.templateItems) : [I18n.t("Шаблон не выбран")]
                    onActivated: page.doSelectTemplate(templateCombo.currentIndex)
                }
                RowLayout {
                    spacing: 6
                    AccentButton {
                        kind: "ghost"; glyph: "\uE8B5"
                        text: I18n.t("Импорт")
                        tip: I18n.t("Импорт шаблона")
                        enabled: page.loaded
                        onClicked: page.doImportTemplate()
                    }
                    AccentButton {
                        kind: "ghost"; glyph: "\uE777"; iconOnly: true
                        tip: I18n.t("Сбросить к шаблону")
                        enabled: page.loaded && page.hasTemplate
                        onClicked: page.doReset()
                    }
                }
            }
        }

        // ---- editor ----
        Card {
            Layout.fillWidth: true
            Layout.fillHeight: true
            padding: 0
            hoverable: false
            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                RowLayout {
                    Layout.fillWidth: true
                    Layout.margins: 10
                    spacing: 6
                    Text {
                        text: "\uE8A5"
                        font.family: "Segoe Fluent Icons"; font.pixelSize: 16
                        color: Theme.textMuted
                    }
                    Text {
                        text: page.fileLabel
                        color: Theme.text; font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontNormal; font.weight: Font.DemiBold
                        elide: Text.ElideMiddle
                        Layout.maximumWidth: 320
                    }
                    Rectangle {
                        visible: page.dirty
                        radius: 9; implicitHeight: 18
                        implicitWidth: dirtyText.implicitWidth + 14
                        color: Qt.rgba(Theme.warning.r, Theme.warning.g, Theme.warning.b, 0.16)
                        Text {
                            id: dirtyText
                            anchors.centerIn: parent
                            text: I18n.t("Изменено")
                            color: Theme.warning
                            font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall
                        }
                    }
                    Item { Layout.fillWidth: true }
                    AccentButton {
                        kind: "ghost"; glyph: "\uE7A7"; iconOnly: true
                        tip: I18n.t("Отменить несохранённые правки")
                        enabled: page.loaded && page.dirty
                        onClicked: page.doRevert()
                    }
                    AccentButton {
                        kind: "ghost"; glyph: "\uE8E5"; iconOnly: true
                        tip: I18n.t("Форматировать JSON")
                        enabled: page.loaded && editor.text.length > 0
                        onClicked: page.doFormat()
                    }
                    AccentButton {
                        kind: "ghost"; glyph: "\uE73E"
                        text: I18n.t("Проверить")
                        enabled: page.loaded
                        onClicked: page.doValidate()
                    }
                    AccentButton {
                        kind: "ghost"; glyph: "\uE74E"
                        text: I18n.t("Сохранить")
                        tip: "Ctrl+S"
                        enabled: page.loaded
                        onClicked: page.doSave()
                    }
                    AccentButton {
                        kind: "accent"; glyph: "\uE768"
                        text: I18n.t("Применить")
                        tip: I18n.t("Сохранить и перезапустить ядро с этим конфигом")
                        enabled: page.loaded
                        onClicked: page.doApply()
                    }
                }

                CodeEditor {
                    id: editor
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.leftMargin: 10
                    Layout.rightMargin: 10
                    placeholderText: "Raw " + (page.core === "singbox" ? "sing-box" : "xray") + ".json"
                }

                // ---- status bar ----
                RowLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: 12
                    Layout.rightMargin: 12
                    Layout.topMargin: 8
                    Layout.bottomMargin: 8
                    spacing: 8
                    Text {
                        visible: page.statusMessage !== ""
                        text: page._levelGlyph(page.statusLevel)
                        font.family: "Segoe Fluent Icons"; font.pixelSize: 14
                        color: page._levelColor(page.statusLevel)
                    }
                    Text {
                        Layout.fillWidth: true
                        text: page.statusMessage !== "" ? page.statusMessage
                            : (page.dirty ? I18n.t("Есть несохранённые изменения") : "")
                        color: page.statusMessage !== "" ? page._levelColor(page.statusLevel) : Theme.textMuted
                        font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall
                        elide: Text.ElideRight
                        maximumLineCount: 1
                    }
                    AccentButton {
                        visible: page.errorLine > 0
                        kind: "ghost"
                        text: I18n.t("К строке {line}", { line: page.errorLine })
                        onClicked: editor.goToLine(page.errorLine)
                    }
                    Text {
                        text: I18n.t("Строк: {count}", { count: editor.lineCount })
                        color: Theme.textFaint
                        font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall
                    }
                }
            }
        }
    }

    // ---- discard-confirmation modal overlay -----------------------------
    Rectangle {
        id: confirmOverlay
        anchors.fill: parent
        visible: false
        z: 100
        color: "#80000000"
        MouseArea { anchors.fill: parent; onClicked: {} }   // swallow clicks
        Rectangle {
            anchors.centerIn: parent
            width: Math.min(420, parent.width - 80)
            height: contentCol.implicitHeight + 40
            radius: Theme.radius
            color: Theme.flyout
            border.width: 1; border.color: Theme.flyoutBorder
            ColumnLayout {
                id: contentCol
                anchors.fill: parent
                anchors.margins: 20
                spacing: 16
                Text {
                    text: I18n.t("Несохранённые изменения")
                    color: Theme.text; font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontStrong; font.weight: Font.DemiBold
                    Layout.fillWidth: true; wrapMode: Text.WordWrap
                }
                Text {
                    text: I18n.t("В текущем редакторе есть несохранённые изменения. Отменить их и продолжить?")
                    color: Theme.textMuted; font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontNormal
                    Layout.fillWidth: true; wrapMode: Text.WordWrap
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Item { Layout.fillWidth: true }
                    AccentButton { kind: "ghost"; text: I18n.t("Отмена"); onClicked: page._confirmNo() }
                    AccentButton { kind: "danger"; text: I18n.t("Отменить изменения"); onClicked: page._confirmYes() }
                }
            }
        }
    }
}
