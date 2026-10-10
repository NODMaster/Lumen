import QtQuick
import QtQuick.Controls.Universal
import "."

// Filled input with a leading glyph and a clear button: the look of the
// Servers page search box, shared by search fields and single-line inputs.
Rectangle {
    id: box
    property alias text: input.text
    property alias placeholderText: input.placeholderText
    property alias input: input
    property string glyph: "\uE721" // Search
    property int fontPixelSize: Theme.fontNormal
    property bool clearable: true
    // Report Up/Down/Escape instead of passing them on (list pickers).
    property bool navigationKeys: false
    signal accepted()
    signal editingFinished()
    signal upPressed()
    signal downPressed()
    signal escapePressed()

    function focusInput() { input.forceActiveFocus() }
    function clear() { input.text = "" }

    implicitWidth: 220
    implicitHeight: Theme.controlHeight
    radius: Theme.radiusSmall
    color: Theme.controlFill
    border.width: 1
    border.color: input.activeFocus ? Theme.accent : Theme.borderSolid
    opacity: enabled ? 1 : 0.55

    Text {
        id: glyphText
        textFormat: Text.PlainText
        anchors.left: parent.left
        anchors.leftMargin: 10
        anchors.verticalCenter: parent.verticalCenter
        text: box.glyph
        font.family: "Segoe Fluent Icons"
        font.pixelSize: 14
        color: Theme.textFaint
    }

    FluentTextField {
        id: input
        anchors.left: glyphText.right
        anchors.leftMargin: 8
        anchors.right: clearButton.visible ? clearButton.left : parent.right
        anchors.rightMargin: clearButton.visible ? 4 : 10
        anchors.verticalCenter: parent.verticalCenter
        background: null
        verticalAlignment: TextInput.AlignVCenter
        placeholderTextColor: Theme.textFaint
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: box.fontPixelSize
        selectByMouse: true
        onAccepted: box.accepted()
        onEditingFinished: box.editingFinished()
        Keys.onUpPressed: (event) => { event.accepted = box.navigationKeys; if (box.navigationKeys) box.upPressed() }
        Keys.onDownPressed: (event) => { event.accepted = box.navigationKeys; if (box.navigationKeys) box.downPressed() }
        Keys.onEscapePressed: (event) => { event.accepted = box.navigationKeys; if (box.navigationKeys) box.escapePressed() }
    }

    Text {
        id: clearButton
        visible: box.clearable && box.enabled && input.text.length > 0
        anchors.right: parent.right
        anchors.rightMargin: 10
        anchors.verticalCenter: parent.verticalCenter
        text: "\uE711" // Cancel
        font.family: "Segoe Fluent Icons"
        font.pixelSize: 10
        color: clearMouse.containsMouse ? Theme.text : Theme.textFaint
        MouseArea {
            id: clearMouse
            anchors.fill: parent
            anchors.margins: -7
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: { input.text = ""; input.forceActiveFocus() }
        }
    }
}
