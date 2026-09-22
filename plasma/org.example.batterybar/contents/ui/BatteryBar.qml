import QtQuick

Item {
    id: root
    required property int percent
    required property bool charging
    required property color fillColor
    required property string label
    property int labelSize: 12

    Canvas {
        id: bar
        anchors.fill: parent
        readonly property real bodyWidth: width - 5
        readonly property real innerWidth: bodyWidth - 4
        readonly property real filledWidth: innerWidth * (root.charging ? 1 : Math.max(0, root.percent) / 100)
        onPaint: {
            const ctx = getContext("2d")
            ctx.reset()
            const h = height
            ctx.fillStyle = "#24282d"
            ctx.fillRect(1, 1, bodyWidth - 2, h - 2)
            ctx.fillStyle = root.fillColor
            ctx.fillRect(2, 2, filledWidth, h - 4)
            const shade = ctx.createLinearGradient(0, 1, 0, h - 1)
            shade.addColorStop(0, "rgba(0, 0, 0, 0.42)")
            shade.addColorStop(0.22, "rgba(0, 0, 0, 0.08)")
            shade.addColorStop(0.50, "rgba(255, 255, 255, 0.10)")
            shade.addColorStop(0.78, "rgba(0, 0, 0, 0.08)")
            shade.addColorStop(1, "rgba(0, 0, 0, 0.42)")
            ctx.fillStyle = shade
            ctx.fillRect(2, 2, innerWidth, h - 4)
            ctx.strokeStyle = "#d8dee9"
            ctx.lineWidth = 1
            ctx.strokeRect(0.5, 0.5, bodyWidth - 1, h - 1)
            ctx.fillStyle = "#d8dee9"
            ctx.fillRect(bodyWidth, h * 0.30, 4, h * 0.40)
        }
        Connections {
            target: root
            function onPercentChanged() { bar.requestPaint() }
            function onFillColorChanged() { bar.requestPaint() }
            function onChargingChanged() { bar.requestPaint() }
        }
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()

        Item {
            id: filledTextClip
            x: 2
            y: 2
            width: bar.filledWidth
            height: bar.height - 4
            clip: true
            Text {
                x: (bar.bodyWidth - width) / 2 - filledTextClip.x
                anchors.verticalCenter: parent.verticalCenter
                text: root.label
                font.family: "DejaVu Sans Mono"
                font.pixelSize: root.labelSize
                font.bold: true
                color: root.charging || root.percent < 10 ? "#ffffff" : "#0b0d0e"
            }
        }
        Item {
            id: emptyTextClip
            x: 2 + bar.filledWidth
            y: 2
            width: bar.innerWidth - bar.filledWidth
            height: bar.height - 4
            clip: true
            Text {
                x: (bar.bodyWidth - width) / 2 - emptyTextClip.x
                anchors.verticalCenter: parent.verticalCenter
                text: root.label
                font.family: "DejaVu Sans Mono"
                font.pixelSize: root.labelSize
                font.bold: true
                color: "#ffffff"
            }
        }
    }
}
