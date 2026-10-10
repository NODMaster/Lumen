import QtQuick
import QtQuick.Controls.Universal
import "."

// FluentCombo look-alike whose drop-down starts with a search field, for long
// lists such as servers. `currentIndex` is not changed internally: bind it to
// application state and react to `activated(index)` (index into `model`).
Item {
    id: control
    property var model: []
    property string textRole: "label"
    property int currentIndex: -1
    property string placeholderText: ""
    property string searchPlaceholder: I18n.t("Поиск серверов…")
    property int popupMinWidth: 280
    readonly property int count: model ? model.length : 0
    readonly property string displayText: currentIndex >= 0 && currentIndex < count
                                          ? itemText(currentIndex) : placeholderText
    property var filtered: []
    signal activated(int index)

    implicitWidth: 220
    implicitHeight: Theme.controlHeight
    opacity: enabled ? 1 : 0.5

    function itemText(i) {
        var it = model[i]
        if (it !== null && typeof it === "object")
            return String(it[textRole] !== undefined ? it[textRole] : "")
        return String(it)
    }
    function refilter() {
        var q = search.text.trim().toLowerCase()
        var out = []
        for (var i = 0; i < count; ++i)
            if (q === "" || itemText(i).toLowerCase().indexOf(q) >= 0)
                out.push(i)
        filtered = out
        list.currentIndex = out.length > 0 ? Math.max(0, out.indexOf(currentIndex)) : -1
    }
    function choose(i) {
        popup.close()
        if (i >= 0 && i < count)
            control.activated(i)
    }
    onModelChanged: if (popup.visible) refilter()

    Rectangle {
        anchors.fill: parent
        radius: Theme.radiusSmall
        color: fieldMouse.pressed ? Theme.controlFillPressed
               : (fieldMouse.containsMouse ? Theme.controlFillHover : Theme.controlFill)
        border.width: 1
        border.color: popup.visible ? Theme.accent : Theme.borderSolid
        Behavior on color { ColorAnimation { duration: 110 } }

        Text {
            anchors.left: parent.left
            anchors.right: chevron.left
            anchors.leftMargin: 12
            anchors.rightMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            text: control.displayText
            color: control.currentIndex >= 0 ? Theme.text : Theme.textFaint
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontNormal
            elide: Text.ElideRight
        }
        Text {
            id: chevron
            anchors.right: parent.right
            anchors.rightMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            text: "\uE70D"
            font.family: "Segoe Fluent Icons"
            font.pixelSize: 12
            color: Theme.textMuted
        }
        MouseArea {
            id: fieldMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: popup.visible ? popup.close() : popup.open()
        }
    }

    Popup {
        id: popup
        // Opens upwards when the window has no room below the field.
        property bool openUp: false
        property real room: 100000
        y: openUp ? -height - 4 : control.height + 4
        x: Math.min(0, control.width - width)
        width: Math.max(control.width, control.popupMinWidth)
        padding: 6
        height: Math.min(contentColumn.implicitHeight + topPadding + bottomPadding, 380)
        onAboutToShow: {
            var winH = control.Window.height
            if (!(winH > 0)) {
                openUp = false
                room = 100000
                return
            }
            var pos = control.mapToItem(null, 0, 0)
            var below = winH - pos.y - control.height - 12
            var above = pos.y - 12
            var want = Math.min(380, control.count * 34 + Theme.controlHeight + 6 + topPadding + bottomPadding)
            openUp = below < want && above > below
            room = openUp ? above : below
        }
        onOpened: {
            search.clear()
            control.refilter()
            search.focusInput()
            if (list.currentIndex >= 0)
                list.positionViewAtIndex(list.currentIndex, ListView.Contain)
        }

        background: Rectangle {
            radius: 8
            color: Theme.flyout
            border.width: 1
            border.color: Theme.flyoutBorder
        }

        contentItem: Column {
            id: contentColumn
            spacing: 6

            SearchField {
                id: search
                width: parent.width
                placeholderText: control.searchPlaceholder
                onTextChanged: control.refilter()
                onAccepted: if (list.currentIndex >= 0) control.choose(control.filtered[list.currentIndex])
                navigationKeys: true
                onDownPressed: list.incrementCurrentIndex()
                onUpPressed: list.decrementCurrentIndex()
                onEscapePressed: popup.close()
            }

            Text {
                visible: control.filtered.length === 0
                width: parent.width
                topPadding: 6
                bottomPadding: 8
                horizontalAlignment: Text.AlignHCenter
                text: I18n.t("Ничего не найдено")
                color: Theme.textFaint
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSmall
            }

            ListView {
                id: list
                width: parent.width
                height: Math.min(contentHeight, 300,
                                 Math.max(68, popup.room - search.height - contentColumn.spacing
                                              - popup.topPadding - popup.bottomPadding))
                visible: control.filtered.length > 0
                clip: true
                model: control.filtered
                boundsBehavior: Flickable.StopAtBounds
                highlightMoveDuration: 0
                ScrollBar.vertical: FluentScrollBar {}
                delegate: ItemDelegate {
                    id: row
                    required property int index
                    required property var modelData
                    width: ListView.view.width
                    height: 34
                    padding: 0
                    hoverEnabled: true
                    onHoveredChanged: if (hovered) list.currentIndex = index
                    onClicked: control.choose(modelData)
                    contentItem: Text {
                        leftPadding: 12
                        rightPadding: 12
                        text: control.itemText(row.modelData)
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontNormal
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                    }
                    background: Rectangle {
                        anchors.fill: parent
                        anchors.margins: 2
                        radius: Theme.radiusSmall
                        color: list.currentIndex === row.index ? Theme.cardHover : "transparent"
                        Rectangle {
                            visible: row.modelData === control.currentIndex
                            width: 3
                            radius: 1.5
                            height: parent.height * 0.5
                            anchors.left: parent.left
                            anchors.leftMargin: 1
                            anchors.verticalCenter: parent.verticalCenter
                            color: Theme.accent
                        }
                    }
                }
            }
        }

        enter: Transition {
            NumberAnimation { property: "opacity"; from: 0.0; to: 1.0; duration: 90 }
        }
    }
}
