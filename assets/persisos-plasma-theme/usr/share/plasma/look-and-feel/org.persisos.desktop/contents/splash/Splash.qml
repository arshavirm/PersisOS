import QtQuick 2.15
import org.kde.plasma.core 2.0 as PlasmaCore

Rectangle {
    id: root
    color: "#1b1d1f"

    // ksplashqml sets this property as it progresses through
    // the well-known startup stages.
    property int stage

    onStageChanged: {
        if (stage === 1) {
            logoAnim.running = true
        }
    }

    Image {
        id: logo
        source: "images/logo-white.svg"
        sourceSize.width: 180
        sourceSize.height: 180
        width: 180
        height: 180
        anchors.centerIn: parent
        opacity: 0
        scale: 0.92
        smooth: true

        SequentialAnimation {
            id: logoAnim
            running: false
            NumberAnimation {
                targets: [logo]
                properties: "opacity"
                from: 0
                to: 1
                duration: 600
                easing.type: Easing.InOutQuad
            }
        }
        NumberAnimation on scale {
            from: 0.92
            to: 1
            duration: 600
            easing.type: Easing.OutCubic
            running: true
        }
    }

    Text {
        anchors.top: logo.bottom
        anchors.topMargin: 24
        anchors.horizontalCenter: logo.horizontalCenter
        text: "PersisOS"
        color: "#ffffff"
        font.pointSize: 16
        font.letterSpacing: 2
        opacity: 0.9
    }

    // Simple busy indicator: three dots that pulse in sequence
    Row {
        id: dots
        anchors.top: parent.verticalCenter
        anchors.topMargin: 150
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: 10

        Repeater {
            model: 3
            Rectangle {
                width: 8
                height: 8
                radius: 4
                color: "#e8a15a"
                opacity: 0.3

                SequentialAnimation on opacity {
                    loops: Animation.Infinite
                    running: true
                    PauseAnimation { duration: index * 200 }
                    NumberAnimation { to: 1; duration: 400 }
                    NumberAnimation { to: 0.3; duration: 400 }
                    PauseAnimation { duration: (2 - index) * 200 }
                }
            }
        }
    }
}
