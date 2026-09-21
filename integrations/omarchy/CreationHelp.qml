pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls as Controls
import qs.Commons
import qs.Ui
import "CreationHelpData.js" as HelpData

Flickable {
    id: root
    signal exampleChosen(string value)
    contentHeight: content.implicitHeight
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    function scrollBy(amount) { contentY = Math.max(0, Math.min(Math.max(0, contentHeight - height), contentY + amount)); }

    Controls.ScrollBar.vertical: Controls.ScrollBar {
        policy: Controls.ScrollBar.AsNeeded
        contentItem: Rectangle { implicitWidth: Style.space(4); radius: width / 2; color: Color.accent; opacity: 0.65 }
    }
    Column {
        id: content
        width: root.width - Style.space(14)
        spacing: Style.space(20)
        Repeater {
            model: HelpData.sections
            delegate: Column {
                id: section
                required property var modelData
                width: content.width
                spacing: Style.space(8)
                Text {
                    width: parent.width
                    text: section.modelData.title
                    textFormat: Text.PlainText
                    color: Color.accent
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                    font.bold: true
                    wrapMode: Text.Wrap
                }
                Text {
                    width: parent.width
                    text: section.modelData.body
                    textFormat: Text.PlainText
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.bodySmall
                    wrapMode: Text.Wrap
                }
                Repeater {
                    model: section.modelData.examples || []
                    delegate: Column {
                        id: example
                        required property string modelData
                        width: section.width
                        spacing: Style.space(5)
                        Text {
                            width: parent.width
                            text: example.modelData
                            textFormat: Text.PlainText
                            color: Color.foreground
                            font.family: Style.font.family
                            font.pixelSize: Style.font.bodySmall
                            wrapMode: Text.Wrap
                        }
                        Button {
                            text: "Insert example"
                            fontSize: Style.font.bodySmall
                            bordered: true
                            tooltipText: "Replace the input with this example. Press Enter to create the task."
                            onClicked: root.exampleChosen(example.modelData)
                        }
                    }
                }
            }
        }
    }
}
