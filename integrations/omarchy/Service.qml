import QtQuick
import Quickshell.Io
import "Backend.js" as Backend

// Omarchy creates one service for the enabled plugin, regardless of monitor count.
Item {
    id: root
    property var shell: null
    property int lastExitCode: -1
    readonly property var settings: Backend.widgetSettings(shell ? shell.barConfig : {})
    readonly property var backendCommand: Backend.command(settings, Qt.resolvedUrl("../../scripts/omatask-backend"))

    function dispatch() {
        if (!shell || worker.running) return;
        worker.command = backendCommand.concat(["worker", "--once"]);
        worker.running = true;
    }

    IpcHandler {
        target: "local.omatask-reminders"
        function status(): string {
            return JSON.stringify({ready: root.shell !== null, running: worker.running,
                                   lastExitCode: root.lastExitCode, pollInterval: 10000});
        }
    }

    Timer {
        interval: 10000
        running: root.shell !== null
        repeat: true
        triggeredOnStart: true
        onTriggered: root.dispatch()
    }
    Process {
        id: worker
        stdout: StdioCollector {}
        stderr: StdioCollector { id: errors }
        onExited: (code) => {
            root.lastExitCode = code;
            if (code !== 0) console.warn("Omatask reminders: " + (errors.text.trim() || "backend failed"));
        }
    }
}
