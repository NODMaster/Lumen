import QtQuick
import QtQuick.Controls.Universal
import "."

// Plain-text code editor shared by the Configs and Zapret pages:
// monospace TextArea + line-number gutter + current-line highlight +
// eased wheel scrolling.  No syntax colouring on purpose: JSON and winws2
// argument files stay fast even when they are several thousand lines long.
Rectangle {
    id: root

    property alias text: area.text
    property alias readOnly: area.readOnly
    property alias placeholderText: area.placeholderText
    property alias cursorPosition: area.cursorPosition
    property alias area: area
    property bool showLineNumbers: true
    readonly property int lineCount: Math.max(1, area.lineCount)

    function focusEditor() { area.forceActiveFocus() }
    function goToLine(line) {
        var target = Math.max(1, Math.min(line, root.lineCount))
        var pos = 0
        for (var i = 1; i < target; i++) {
            var next = area.text.indexOf("\n", pos)
            if (next < 0) break
            pos = next + 1
        }
        area.cursorPosition = pos
        area.forceActiveFocus()
    }

    radius: Theme.radiusSmall
    color: Theme.micaBase
    border.width: 1
    border.color: area.activeFocus ? Theme.accent : Theme.borderSolid
    clip: true

    property string _numbers: "1"
    function _rebuildNumbers() {
        var parts = []
        for (var i = 1; i <= root.lineCount; i++)
            parts.push(i)
        root._numbers = parts.join("\n")
    }
    onLineCountChanged: _rebuildNumbers()
    Component.onCompleted: _rebuildNumbers()

    // ---- gutter ----
    Item {
        id: gutter
        visible: root.showLineNumbers
        width: visible ? Math.max(36, numberMetrics.advanceWidth * String(root.lineCount).length + 20) : 0
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.margins: 1
        clip: true
        TextMetrics { id: numberMetrics; font: area.font; text: "0" }
        Text {
            x: 0
            width: gutter.width - 8
            y: area.topPadding - flick.contentY
            horizontalAlignment: Text.AlignRight
            font: area.font
            color: Theme.textFaint
            text: root._numbers
        }
        Rectangle {
            anchors.right: parent.right
            width: 1; height: parent.height
            color: Theme.divider
            opacity: 0.6
        }
    }

    // ---- current line ----
    Item {
        anchors.fill: flick
        clip: true
        Rectangle {
            visible: area.activeFocus && !area.readOnly
            width: parent.width
            y: area.cursorRectangle.y - flick.contentY
            height: area.cursorRectangle.height
            color: Theme.navHover
            opacity: 0.6
        }
    }

    Flickable {
        id: flick
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.right: parent.right
        anchors.left: gutter.right
        anchors.margins: 1
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickDeceleration: 5000
        maximumFlickVelocity: 3000
        pixelAligned: true
        property real wheelStep: 92
        NumberAnimation {
            id: scrollAnim
            target: flick; property: "contentY"
            duration: 320; easing.type: Easing.OutQuint
        }
        WheelHandler {
            acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
            onWheel: (ev) => {
                var maxY = Math.max(0, flick.contentHeight - flick.height)
                if (maxY <= 0) { ev.accepted = true; return }
                if (ev.pixelDelta.y !== 0) {
                    scrollAnim.stop()
                    flick.contentY = Math.max(0, Math.min(maxY, flick.contentY - ev.pixelDelta.y))
                } else {
                    var base = scrollAnim.running ? scrollAnim.to : flick.contentY
                    scrollAnim.to = Math.max(0, Math.min(maxY, base - (ev.angleDelta.y / 120) * flick.wheelStep))
                    scrollAnim.restart()
                }
                vbar.flash()
                ev.accepted = true
            }
        }

        TextArea.flickable: FluentTextArea {
            id: area
            color: Theme.text
            font.family: "Consolas"
            font.pixelSize: 13
            wrapMode: TextArea.NoWrap
            selectByMouse: true
            persistentSelection: true
            background: null
            leftPadding: 8
        }

        ScrollBar.vertical: FluentScrollBar { id: vbar }
        ScrollBar.horizontal: FluentScrollBar {}
    }
}
