import QtQuick
import QtQuick.Layouts
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasmoid
import org.kde.plasma.private.battery as Battery
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root
    Plasmoid.title: "BatteryBar"
    Plasmoid.icon: "battery"
    Plasmoid.backgroundHints: PlasmaCore.Types.NoBackground
    preferredRepresentation: compactRepresentation
    switchWidth: 1000
    switchHeight: 1000

    Battery.BatteryControlModel { id: battery }
    property var physicalBatteries: []
    function refreshPhysicalBatteries() {
        const found = []
        for (let i = 0; i < batteryRows.count; i++) {
            const row = batteryRows.itemAt(i)
            if (row && row.present && row.batteryType === "Battery") {
                found.push({ percent: Math.max(0, Math.min(100, row.batteryPercent)),
                             charging: row.chargeState === Battery.BatteryControlModel.Charging })
            }
        }
        physicalBatteries = found
    }
    function scheduleBatteryRefresh() { Qt.callLater(refreshPhysicalBatteries) }
    Component.onCompleted: scheduleBatteryRefresh()
    Repeater {
        id: batteryRows
        model: battery
        delegate: Item {
            property int batteryPercent: model.Percent
            property bool present: model.PluggedIn
            property string batteryType: model.Type
            property int chargeState: model.ChargeState
            visible: false
            onBatteryPercentChanged: root.scheduleBatteryRefresh()
            onPresentChanged: root.scheduleBatteryRefresh()
            onBatteryTypeChanged: root.scheduleBatteryRefresh()
            onChargeStateChanged: root.scheduleBatteryRefresh()
        }
        onItemAdded: root.scheduleBatteryRefresh()
        onItemRemoved: root.scheduleBatteryRefresh()
    }
    readonly property bool splitBatteries: showPercent && physicalBatteries.length === 2

    readonly property bool charging: battery.state === Battery.BatteryControlModel.Charging
    readonly property bool discharging: battery.state === Battery.BatteryControlModel.Discharging
    readonly property bool full: battery.state === Battery.BatteryControlModel.FullyCharged
    readonly property int percent: battery.hasBatteries ? Math.max(0, Math.min(100, battery.percent)) : -1
    readonly property color fillColor: charging ? "#398bdb" : percent < 10 && percent >= 0 ? "#e44747" : "#49c64b"
    property bool showPercent: false
    readonly property string remaining: {
        const ms = Number(battery.smoothedRemainingMsec)
        if (!Number.isFinite(ms) || ms < 60000 || ms > 172800000) return ""
        const minutes = Math.round(ms / 60000)
        return String(Math.floor(minutes / 60)).padStart(2, "0") + ":" + String(minutes % 60).padStart(2, "0")
    }
    readonly property string barLabel: percent < 0 ? "?" : showPercent ? percent + "%" : full ? "FULL" : remaining || (percent + "%")
    toolTipMainText: "BatteryBar"
    toolTipSubText: percent < 0 ? "No battery" : percent + "% · " + (full ? "Full" : charging ? "Charging" : discharging ? "Discharging" : "Not charging") + (remaining ? " · " + remaining + (charging ? " until full" : " remaining") : "")

    compactRepresentation: Item {
        implicitWidth: 84
        implicitHeight: 24
        Layout.minimumWidth: 84
        Layout.preferredWidth: 84
        Layout.fillHeight: true

        Item {
            id: barArea
            anchors.centerIn: parent
            width: 79.5
            height: Math.min(parent.height - 4, 22)
            BatteryBar {
                anchors.fill: parent
                visible: !root.splitBatteries
                percent: root.percent
                charging: root.charging
                fillColor: root.fillColor
                label: root.barLabel
            }
            Row {
                anchors.fill: parent
                spacing: 3
                visible: root.splitBatteries
                Repeater {
                    model: root.splitBatteries ? root.physicalBatteries : []
                    delegate: BatteryBar {
                        required property var modelData
                        width: (barArea.width - 3) / 2
                        height: barArea.height
                        percent: modelData.percent
                        charging: modelData.charging
                        fillColor: charging ? "#398bdb" : percent < 10 ? "#e44747" : "#49c64b"
                        label: percent + "%"
                        labelSize: 10
                    }
                }
            }
        }
        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton | Qt.MiddleButton | Qt.RightButton
            onClicked: mouse => {
                if (mouse.button === Qt.LeftButton) root.showPercent = !root.showPercent
                else if (mouse.button === Qt.RightButton) root.expanded = !root.expanded
                else root.scheduleBatteryRefresh()
            }
        }
    }

    fullRepresentation: Item {
        implicitWidth: 310
        implicitHeight: 190
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Kirigami.Units.largeSpacing
            spacing: Kirigami.Units.smallSpacing
            Text { text: "BATTERYBAR DETAILS"; font.bold: true; color: Kirigami.Theme.textColor }
            Text { text: root.percent < 0 ? "No battery detected" : root.percent + "% · " + (root.full ? "Full" : root.charging ? "Charging" : root.discharging ? "Discharging" : "Not charging"); color: Kirigami.Theme.textColor }
            Text { text: root.remaining ? root.remaining + (root.charging ? " until full" : " remaining") : "Time estimate unavailable"; color: Kirigami.Theme.textColor }
            Text { text: "Battery health: " + (battery.rowCount() > 0 ? battery.data(battery.index(0, 0), Battery.BatteryControlModel.Capacity) + "%" : "unavailable"); color: Kirigami.Theme.textColor }
            Text { text: battery.pluggedIn ? "AC adapter connected" : "On battery power"; color: Kirigami.Theme.textColor }
            Item { Layout.fillHeight: true }
        }
    }
}
