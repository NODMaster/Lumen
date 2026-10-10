import QtQuick
import QtQuick.Controls.Universal
import QtQuick.Layouts
import App 1.0
import "."

// Zapret (winws2) page.
//   editing == false -> presets: list (left) + details/preview (right),
//                       "run together with server" bindings below
//   editing == true  -> preset editor (name / description / arguments)
Item {
    id: page

    property var presets: []
    property string selected: ""
    property bool running: false
    property string activePreset: ""
    property string filter: ""
    property string previewText: ""
    property var bindings: []
    property var serverOptions: []
    readonly property var selectedInfo: _find(page.presets, page.selected)
    readonly property var visiblePresets: _filtered(page.presets, page.filter)
    readonly property string bindNodeId: serverOptions.length > 0
        ? serverOptions[Math.min(bindServerCombo.chosen, serverOptions.length - 1)].value : ""
    readonly property var bindChoices: bindNodeId !== "" ? App.zapretBindingChoices(bindNodeId) : []

    // editor state
    property bool editing: false
    property bool editIsNew: false
    property string editOrigName: ""
    property string editSavedDesc: ""
    property string editSavedContent: ""
    readonly property bool editDirty: page.editing && (nameField.text.trim() !== page.editOrigName
        || descField.text.trim() !== page.editSavedDesc || contentArea.text !== page.editSavedContent)
    readonly property string nameError: _nameError(nameField.text)

    component FluentField: FluentTextField {
        Layout.fillWidth: true
        implicitHeight: Theme.controlHeight
        leftPadding: 10; rightPadding: 10; topPadding: 0; bottomPadding: 0
        color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontNormal
        selectByMouse: true
        verticalAlignment: TextInput.AlignVCenter
        background: Rectangle {
            radius: Theme.radiusSmall; color: Theme.controlFill
            border.width: 1; border.color: parent.activeFocus ? Theme.accent : Theme.borderSolid
        }
    }

    component SectionTitle: Text {
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontStrong
        font.weight: Font.DemiBold
        elide: Text.ElideRight
    }

    component Hint: Text {
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSmall
        wrapMode: Text.WordWrap
    }

    function _find(list, name) {
        for (var i = 0; i < list.length; ++i)
            if (list[i].name === name)
                return list[i]
        return null
    }

    function _filtered(list, query) {
        var q = (query || "").trim().toLowerCase()
        if (q === "")
            return list
        return list.filter(function(p) {
            return p.name.toLowerCase().indexOf(q) >= 0
                || (p.description || "").toLowerCase().indexOf(q) >= 0
        })
    }

    function _nameError(text) {
        var name = (text || "").trim()
        if (name === "")
            return I18n.t("Укажите имя пресета")
        if (/[\\\/:*?"<>|]/.test(name))
            return I18n.t("Недопустимые символы в имени")
        return ""
    }

    function _argCount(text) {
        var count = 0
        var lines = (text || "").split("\n")
        for (var i = 0; i < lines.length; ++i) {
            var line = lines[i].trim()
            if (line !== "" && line.charAt(0) !== "#")
                count++
        }
        return count
    }

    function refresh() {
        presets = App.zapretPresets()
        if (!_find(presets, selected))
            selected = presets.length > 0 ? presets[0].name : ""
        previewText = selected !== "" ? App.readPreset(selected) : ""
    }

    function refreshBindings() {
        bindings = App.zapretServerBindings()
        serverOptions = App.zapretServerOptions()
    }

    function syncStatus() {
        var s = App.zapretStatus()
        running = !!s.running
        activePreset = s.preset || ""
    }

    function selectPreset(name) {
        if (name === selected)
            return
        selected = name
        previewText = name !== "" ? App.readPreset(name) : ""
    }

    function startSelected() {
        if (selected !== "")
            App.startZapret(selected)
    }

    // Double-click in the list: run the preset (or switch to it).
    function activatePreset(name) {
        if (name === "")
            return
        selectPreset(name)
        if (!(running && activePreset === name))
            App.startZapret(name)
    }

    function openEditor(name) {
        editIsNew = (name === "")
        editOrigName = name
        nameField.text = name
        var info = name === "" ? null : _find(presets, name)
        editSavedDesc = info ? (info.description || "") : ""
        editSavedContent = name === "" ? "" : App.readPreset(name)
        descField.text = editSavedDesc
        contentArea.text = editSavedContent
        var parts = []
        if (info && info.created) parts.push(I18n.t("Создан: ") + info.created)
        if (info && info.modified) parts.push(I18n.t("Изменён: ") + info.modified)
        metaText.text = parts.join("  ·  ")
        editing = true
        Qt.callLater(function() { if (page.editIsNew) nameField.forceActiveFocus(); else contentArea.focusEditor() })
    }

    function saveEditor() {
        if (nameError !== "")
            return
        var nm = nameField.text.trim()
        var ok = true
        if (!editIsNew && editOrigName !== "" && nm !== editOrigName)
            ok = App.saveRenamedPreset(editOrigName, nm, descField.text.trim(), contentArea.text)
        else
            App.savePreset(nm, descField.text.trim(), contentArea.text)
        if (!ok)
            return
        editing = false
        selected = nm
        previewText = App.readPreset(nm)
    }

    function closeEditor() {
        if (editDirty)
            discardDialog.open()
        else
            editing = false
    }

    Component.onCompleted: { refresh(); syncStatus(); refreshBindings() }
    onVisibleChanged: if (visible) { refresh(); syncStatus(); refreshBindings() }

    Connections {
        target: App
        function onZapretState(s) {
            page.running = !!s.running
            page.activePreset = s.preset || ""
            page.refreshBindings()
        }
        function onZapretPresetsChanged() { page.refresh(); page.refreshBindings() }
        function onZapretBindingsChanged() { page.refreshBindings() }
        function onSelectionChanged() { page.serverOptions = App.zapretServerOptions() }
    }

    Shortcut {
        sequences: [StandardKey.Save]
        enabled: page.visible && page.editing
        onActivated: page.saveEditor()
    }

    FluentDialog {
        id: deleteDialog
        width: 440
        title: I18n.t("Удалить пресет?")
        okText: I18n.t("Удалить")
        onAccepted: if (page.selected !== "") App.deletePreset(page.selected)
        contentItem: Text {
            text: I18n.t("Пресет «{name}» будет удалён без возможности восстановления.", { name: page.selected })
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontNormal
            wrapMode: Text.WordWrap
        }
    }

    FluentDialog {
        id: discardDialog
        width: 440
        title: I18n.t("Несохранённые изменения")
        okText: I18n.t("Отменить изменения")
        onAccepted: page.editing = false
        contentItem: Text {
            text: I18n.t("Изменения в пресете не сохранены. Закрыть редактор без сохранения?")
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontNormal
            wrapMode: Text.WordWrap
        }
    }

    // ════════════════ PRESETS VIEW ════════════════
    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.spacing
        visible: !page.editing

        // ---- header ----
        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            Text {
                text: I18n.t("Zapret")
                color: Theme.text; font.family: Theme.fontFamily
                font.pixelSize: Theme.fontTitle; font.weight: Font.DemiBold
            }
        }

        Hint {
            Layout.fillWidth: true
            text: I18n.t("Zapret запускает winws2.exe с выбранным пресетом аргументов, чтобы обходить DPI-замедления YouTube, Discord и других сервисов. Работает независимо от VPN/прокси и требует прав администратора.")
        }

        Rectangle {
            Layout.fillWidth: true
            visible: !App.isAdmin
            implicitHeight: adminRow.implicitHeight + 16
            radius: Theme.radiusSmall
            color: Qt.rgba(Theme.warning.r, Theme.warning.g, Theme.warning.b, 0.12)
            border.width: 1
            border.color: Qt.rgba(Theme.warning.r, Theme.warning.g, Theme.warning.b, 0.35)
            RowLayout {
                id: adminRow
                anchors.fill: parent
                anchors.margins: 8
                anchors.leftMargin: 12
                spacing: 8
                Text { text: "\uE7BA"; font.family: "Segoe Fluent Icons"; font.pixelSize: 14; color: Theme.warning }
                Text {
                    Layout.fillWidth: true
                    text: I18n.t("Lumen запущен без прав администратора — Zapret не сможет запуститься.")
                    color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall
                    wrapMode: Text.WordWrap
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Theme.spacing

            // ---- preset list ----
            Card {
                Layout.preferredWidth: Math.max(250, Math.min(340, page.width * 0.32))
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
                        SearchField {
                            id: searchField
                            Layout.fillWidth: true
                            placeholderText: I18n.t("Поиск пресета")
                            onTextChanged: page.filter = text
                        }
                        AccentButton { kind: "ghost"; glyph: "\uE710"; iconOnly: true; tip: I18n.t("Новый пресет"); onClicked: page.openEditor("") }
                        AccentButton {
                            kind: "ghost"; glyph: "\uE8B5"; iconOnly: true
                            tip: I18n.t("Импорт из файла")
                            onClicked: { var n = App.importZapretPreset(); if (n) page.selectPreset(n) }
                        }
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.divider }

                    ListView {
                        id: presetList
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.margins: 4
                        clip: true
                        spacing: 2
                        model: page.visiblePresets
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: FluentScrollBar { id: presetListVbar }

                        delegate: Rectangle {
                            id: presetRow
                            width: ListView.view.width
                            height: 50
                            readonly property bool isActive: page.running && modelData.name === page.activePreset
                            readonly property bool isSel: modelData.name === page.selected
                            radius: Theme.radiusSmall
                            color: isSel ? Theme.cardHover : (rowMouse.containsMouse ? Theme.navHover : "transparent")

                            Rectangle {
                                visible: presetRow.isSel
                                width: 3; height: 18; radius: 1.5
                                anchors.left: parent.left
                                anchors.verticalCenter: parent.verticalCenter
                                color: Theme.accent
                            }
                            MouseArea {
                                id: rowMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                onClicked: page.selectPreset(modelData.name)
                                onDoubleClicked: page.activatePreset(modelData.name)
                            }
                            ColumnLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 12
                                anchors.rightMargin: 10
                                anchors.topMargin: 6
                                anchors.bottomMargin: 6
                                spacing: 1
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 6
                                    Rectangle {
                                        visible: presetRow.isActive
                                        width: 8; height: 8; radius: 4
                                        color: Theme.success
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        text: modelData.name
                                        elide: Text.ElideRight
                                        color: presetRow.isActive ? Theme.success : Theme.text
                                        font.family: Theme.fontFamily; font.pixelSize: Theme.fontNormal
                                        font.weight: presetRow.isSel || presetRow.isActive ? Font.DemiBold : Font.Normal
                                    }
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: modelData.description !== "" ? modelData.description
                                        : I18n.t("Аргументов: {count}", { count: modelData.argCount })
                                    elide: Text.ElideRight
                                    color: Theme.textMuted
                                    font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall
                                }
                            }
                        }

                        Column {
                            anchors.centerIn: parent
                            width: parent.width - 32
                            spacing: 6
                            visible: presetList.count === 0
                            Text {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: "\uE945"; font.family: "Segoe Fluent Icons"; font.pixelSize: 28
                                color: Theme.textFaint
                            }
                            Text {
                                width: parent.width
                                horizontalAlignment: Text.AlignHCenter
                                wrapMode: Text.WordWrap
                                text: page.presets.length === 0 ? I18n.t("Нет пресетов Zapret") : I18n.t("Ничего не найдено")
                                color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontNormal
                            }
                            Text {
                                visible: page.presets.length === 0
                                width: parent.width
                                horizontalAlignment: Text.AlignHCenter
                                wrapMode: Text.WordWrap
                                text: I18n.t("Создайте пресет или импортируйте файл аргументов winws2.")
                                color: Theme.textFaint; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall
                            }
                        }
                    }

                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.divider }
                    Text {
                        Layout.fillWidth: true
                        Layout.margins: 10
                        text: I18n.t("Пресетов: {count}", { count: page.presets.length })
                        color: Theme.textFaint; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: Theme.spacing

                // ---- selected preset ----
                Card {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    padding: 0
                    hoverable: false

                    Text {
                        anchors.centerIn: parent
                        visible: page.selectedInfo === null
                        text: I18n.t("Выберите пресет в списке")
                        color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontNormal
                    }

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 0
                        visible: page.selectedInfo !== null

                        RowLayout {
                            Layout.fillWidth: true
                            Layout.margins: 14
                            spacing: 8
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2
                                SectionTitle {
                                    Layout.fillWidth: true
                                    text: page.selectedInfo ? page.selectedInfo.name : ""
                                }
                                Hint {
                                    Layout.fillWidth: true
                                    visible: text !== ""
                                    text: page.selectedInfo ? (page.selectedInfo.description || "") : ""
                                    maximumLineCount: 2
                                    elide: Text.ElideRight
                                }
                                Text {
                                    text: page.selectedInfo
                                        ? I18n.t("Аргументов: {count}", { count: page.selectedInfo.argCount })
                                          + (page.selectedInfo.modified ? "  ·  " + I18n.t("Изменён: ") + page.selectedInfo.modified : "")
                                        : ""
                                    color: Theme.textFaint; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall
                                }
                            }
                            AccentButton {
                                kind: "ghost"; glyph: "\uE74D"; iconOnly: true
                                tip: I18n.t("Удалить")
                                onClicked: deleteDialog.open()
                            }
                            AccentButton {
                                kind: "ghost"; glyph: "\uE70F"
                                text: I18n.t("Изменить")
                                onClicked: page.openEditor(page.selected)
                            }
                            AccentButton {
                                id: runButton
                                kind: page.running ? "danger" : "accent"
                                glyph: page.running ? "\uE71A" : "\uE768"
                                text: page.running ? I18n.t("Остановить") : I18n.t("Запустить")
                                onClicked: page.running ? App.stopZapret() : page.startSelected()
                            }
                        }
                        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.divider }
                        CodeEditor {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.margins: 10
                            readOnly: true
                            text: page.previewText
                        }
                    }
                }

                // ---- run together with a server ----
                Card {
                    Layout.fillWidth: true
                    padding: 14
                    hoverable: false
                    ColumnLayout {
                        width: parent.width
                        spacing: 8

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8
                            Text { text: "\uE71B"; font.family: "Segoe Fluent Icons"; font.pixelSize: 16; color: Theme.textMuted }
                            SectionTitle { text: I18n.t("Запуск вместе с сервером") }
                            Text {
                                text: "\uE946"; font.family: "Segoe Fluent Icons"; font.pixelSize: 13
                                color: bindInfoHover.hovered ? Theme.textMuted : Theme.textFaint
                                HoverHandler { id: bindInfoHover }
                                FluentToolTip {
                                    visible: bindInfoHover.hovered
                                    width: Math.min(implicitWidth, 380)
                                    text: I18n.t("Стратегия или пресет работают только для IP и порта сервера, пока вы к нему подключены. Смена во время подключения переподключает сервер.")
                                }
                            }
                            Item { Layout.fillWidth: true }
                        }

                        ListView {
                            id: bindingList
                            Layout.fillWidth: true
                            Layout.preferredHeight: Math.min(count, 4) * 40
                            visible: count > 0
                            clip: true
                            interactive: count > 4
                            boundsBehavior: Flickable.StopAtBounds
                            model: page.bindings
                            ScrollBar.vertical: FluentScrollBar {}
                            delegate: RowLayout {
                                width: ListView.view.width
                                height: 40
                                spacing: 8
                                Text {
                                    text: modelData.missingNode ? "\uE7BA" : (modelData.active ? "\uE73E" : "\uE968")
                                    font.family: "Segoe Fluent Icons"; font.pixelSize: 14
                                    color: modelData.missingNode ? Theme.warning : (modelData.active ? Theme.success : Theme.textMuted)
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: modelData.name
                                    elide: Text.ElideRight
                                    color: modelData.missingNode ? Theme.textMuted : Theme.text
                                    font.family: Theme.fontFamily; font.pixelSize: Theme.fontNormal
                                }
                                Text {
                                    visible: modelData.missingPreset
                                    text: I18n.t("Пресет не найден")
                                    color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall
                                }
                                Rectangle {
                                    visible: modelData.strategyMode && modelData.kindTitle !== ""
                                    implicitWidth: kindText.implicitWidth + 12
                                    implicitHeight: 20
                                    radius: 4
                                    color: Theme.controlFill
                                    border.width: 1; border.color: Theme.borderSolid
                                    Text {
                                        id: kindText
                                        anchors.centerIn: parent
                                        text: modelData.kindTitle
                                        color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall
                                    }
                                }
                                SearchCombo {
                                    visible: !modelData.missingNode
                                    Layout.preferredWidth: 260
                                    model: modelData.choices
                                    currentIndex: modelData.choiceIndex
                                    placeholderText: modelData.placeholder
                                    popupMinWidth: 360
                                    searchPlaceholder: I18n.t("Поиск стратегий…")
                                    onActivated: (index) => App.setZapretServerBinding(modelData.nodeId, modelData.choices[index].value)
                                }
                                AccentButton {
                                    kind: "ghost"; glyph: "\uE711"; iconOnly: true
                                    tip: I18n.t("Убрать привязку")
                                    onClicked: App.removeZapretServerBinding(modelData.nodeId)
                                }
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8
                            SearchCombo {
                                id: bindServerCombo
                                property int chosen: 0
                                Layout.fillWidth: true
                                enabled: page.serverOptions.length > 0
                                model: page.serverOptions
                                currentIndex: page.serverOptions.length > 0 ? Math.min(chosen, page.serverOptions.length - 1) : -1
                                placeholderText: I18n.t("Все серверы уже привязаны")
                                onActivated: (index) => chosen = index
                                onModelChanged: chosen = 0
                            }
                            SearchCombo {
                                id: bindChoiceCombo
                                property int chosen: 0
                                Layout.preferredWidth: 260
                                enabled: page.bindChoices.length > 0
                                model: page.bindChoices
                                currentIndex: page.bindChoices.length > 0 ? Math.min(chosen, page.bindChoices.length - 1) : -1
                                popupMinWidth: 360
                                searchPlaceholder: I18n.t("Поиск стратегий…")
                                onActivated: (index) => chosen = index
                                onModelChanged: chosen = 0
                            }
                            AccentButton {
                                kind: "ghost"; glyph: "\uE710"
                                text: I18n.t("Привязать")
                                enabled: page.bindNodeId !== "" && page.bindChoices.length > 0
                                onClicked: {
                                    var choice = page.bindChoices[bindChoiceCombo.currentIndex]
                                    if (page.bindNodeId !== "" && choice)
                                        App.setZapretServerBinding(page.bindNodeId, choice.value)
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // ════════════════ EDITOR VIEW ════════════════
    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.spacing
        visible: page.editing

        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            AccentButton { kind: "ghost"; glyph: "\uE72B"; iconOnly: true; tip: I18n.t("Назад к списку"); onClicked: page.closeEditor() }
            Text {
                Layout.fillWidth: true
                text: page.editIsNew ? I18n.t("Новый пресет") : (I18n.t("Редактирование: ") + page.editOrigName)
                elide: Text.ElideRight
                color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontTitle; font.weight: Font.DemiBold
            }
            AccentButton { kind: "ghost"; text: I18n.t("Отмена"); onClicked: page.closeEditor() }
            AccentButton {
                kind: "accent"; glyph: "\uE74E"
                text: I18n.t("Сохранить")
                tip: "Ctrl+S"
                enabled: page.nameError === ""
                onClicked: page.saveEditor()
            }
        }

        Card {
            Layout.fillWidth: true
            padding: 14
            hoverable: false
            GridLayout {
                width: parent.width
                columns: 2
                columnSpacing: 10
                rowSpacing: 10
                Text { text: I18n.t("Название:"); color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontNormal; Layout.preferredWidth: 90 }
                FluentField { id: nameField; placeholderText: I18n.t("Имя пресета") }
                Item { Layout.preferredWidth: 90; visible: nameErrorText.visible }
                Text {
                    id: nameErrorText
                    visible: page.editing && page.nameError !== "" && nameField.text !== ""
                    text: page.nameError
                    color: Theme.danger; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall
                }
                Text { text: I18n.t("Описание:"); color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontNormal; Layout.preferredWidth: 90 }
                FluentField { id: descField; placeholderText: I18n.t("Краткое описание (необязательно)") }
            }
        }

        Card {
            Layout.fillWidth: true
            Layout.fillHeight: true
            padding: 0
            hoverable: false
            ColumnLayout {
                anchors.fill: parent
                spacing: 0
                CodeEditor {
                    id: contentArea
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.margins: 10
                    Layout.bottomMargin: 0
                    placeholderText: I18n.t("Аргументы winws2, по одному на строку.\nСтроки с # — комментарии.")
                }
                RowLayout {
                    Layout.fillWidth: true
                    Layout.margins: 10
                    spacing: 8
                    Text {
                        id: metaText
                        text: ""
                        visible: text !== ""
                        color: Theme.textFaint; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall
                    }
                    Item { Layout.fillWidth: true }
                    Text {
                        visible: page.editDirty
                        text: I18n.t("Изменено")
                        color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall
                    }
                    Text {
                        text: I18n.t("Аргументов: {count}", { count: page._argCount(contentArea.text) })
                        color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall
                    }
                }
            }
        }
    }
}
