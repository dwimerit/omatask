pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Backend.js" as Backend

// View/interaction adapter only: the Python engine owns every task rule.
Panel {
    id: root
    moduleName: "local.omatask"
    manageIpc: false

    readonly property var backendCommand: Backend.command(settings, Qt.resolvedUrl("../../scripts/omatask-backend"))
    readonly property bool vertical: bar ? bar.vertical : false
    property var summary: ({count: 0, overdue: 0})
    property var tasks: []
    property string view: "today"
    property string query: ""
    property string mode: "add"
    property string targetId: ""
    property string error: ""
    property string loadError: ""
    property string message: ""
    property bool loaded: false
    property bool refreshPending: false
    property bool closeAfterAdd: false
    property var detail: null
    property bool helpShown: false
    property var deleteTarget: null
    readonly property var selected: list.currentIndex >= 0 && list.currentIndex < tasks.length ? tasks[list.currentIndex] : null
    readonly property string screenName: button.QsWindow.window && button.QsWindow.window.screen ? button.QsWindow.window.screen.name : ""
    readonly property bool busy: mutation.running
    readonly property var views: ["today", "tomorrow", "upcoming", "overdue", "all", "completed", "recurring"]
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight

    function baseArgs() {
        return backendCommand.concat(["--json"]);
    }
    function refresh() {
        if (poll.running || mutation.running) { refreshPending = true; return; }
        refreshPending = false;
        poll.requestView = view;
        poll.requestQuery = query;
        poll.command = baseArgs().concat(["widget", view, "--query=" + query]);
        poll.running = true;
    }
    function refreshAll() {
        let widgets = bar && typeof bar.moduleWidgets === "function" ? bar.moduleWidgets(moduleName) : [root];
        for (let i = 0; i < widgets.length; ++i) widgets[i].refresh();
    }
    function open() {
        closeAfterAdd = false;
        root.controller.show();
        refresh();
        Qt.callLater(function() { editor.forceActiveFocus(); });
    }
    function quick() {
        root.open();
        closeAfterAdd = true;
        beginInput("add", "");
    }
    function changeView(value) {
        view = value;
        helpShown = false;
        detail = null;
        list.currentIndex = -1;
        refresh();
    }
    function beginInput(kind, value) {
        if (busy) return;
        if (kind === "delete") { requestDelete(selected); return; }
        mode = kind;
        helpShown = false;
        detail = null;
        targetId = selected ? selected.id : "";
        editor.text = value || "";
        error = "";
        editor.forceActiveFocus();
        editor.selectAll();
    }
    function exitSearch() {
        query = "";
        mode = "add";
        editor.text = "";
        error = "";
        message = "";
        refresh();
        keys.forceActiveFocus();
    }
    function runCommand(args, operation) {
        if (busy) return;
        error = "";
        message = "";
        mutation.operation = operation;
        mutation.command = baseArgs().concat(args);
        mutation.running = true;
    }
    function submit() {
        let value = editor.text.trim();
        if (mode === "search") {
            query = value;
            refresh();
            keys.forceActiveFocus();
            return;
        }
        if (!value && mode !== "project" && mode !== "tags") return;
        if (mode === "add") runCommand(["add", "--", value], "add");
        else if (mode === "edit") runCommand(["edit", targetId, "--title=" + value], "edit");
        else if (mode === "project") runCommand(["edit", targetId, "--project=" + value], "edit");
        else if (mode === "tags") {
            let args = ["edit", targetId, "--clear-tags"];
            if (value) value.split(/\s+/).forEach(t => args.push("--tag=" + t.replace(/^#/, "")));
            runCommand(args, "edit");
        }
        else if (mode === "snooze") runCommand(["snooze", targetId, value], "snooze");
    }
    function selectTask(index) {
        list.currentIndex = index;
        keys.forceActiveFocus();
    }
    function toggleHelp() {
        if (deleteTarget) return;
        helpShown = !helpShown;
        if (helpShown) {
            creationHelp.contentY = 0;
            keys.forceActiveFocus();
        } else editor.forceActiveFocus();
    }
    function requestDelete(task) {
        if (!task || busy) return;
        deleteTarget = {id: task.id, title: task.title};
        deleteDialog.selectedIndex = 0;
        error = "";
        keys.forceActiveFocus();
    }
    onOpenedChanged: if (!opened) { deleteTarget = null; helpShown = false; }
    function taskAction(action) {
        if (!selected || busy) return;
        if (action === "show") runCommand(["show", selected.id], "show");
        else if (action === "priority") {
            let values = ["low", "normal", "high", "urgent"];
            runCommand(["edit", selected.id, "--priority", values[(values.indexOf(selected.priority) + 1) % 4]], "edit");
        } else runCommand([action, selected.id], action);
    }
    function focusList(delta) {
        if (tasks.length) list.currentIndex = Math.max(0, Math.min(tasks.length - 1, list.currentIndex + delta));
        list.positionViewAtIndex(list.currentIndex, ListView.Contain);
        keys.forceActiveFocus();
    }
    function launchTui() {
        let args = backendCommand.slice();
        args.push("ui", view);
        Quickshell.execDetached(["omarchy", "launch", "tui"].concat(args));
        root.close();
    }

    // Per-output diagnostics; shell summon/toggle routes the UI to the focused output.
    IpcHandler {
        enabled: root.screenName !== ""
        target: "local.omatask-" + root.screenName
        function refresh(): void { root.refresh(); }
        function quick(): void { root.quick(); }
        function rowRect(taskId: string): string {
            let index = root.tasks.findIndex(t => t.id === taskId);
            let item = index >= 0 ? list.itemAtIndex(index) : null;
            if (!item) return "null";
            let point = item.mapToItem(null, 0, 0);
            let remove = item.deleteButtonItem;
            let removePoint = remove.mapToItem(null, remove.width / 2, remove.height / 2);
            return JSON.stringify({x: point.x, y: point.y, width: item.width, height: item.height,
                deleteX: removePoint.x, deleteY: removePoint.y});
        }
        function status(): string {
            return JSON.stringify({screen: root.screenName, opened: root.opened, loaded: root.loaded,
                busy: root.busy, error: root.error || root.loadError, detailShown: root.detail !== null, helpShown: root.helpShown,
                helpScroll: creationHelp.contentY, helpHeight: creationHelp.contentHeight, count: root.summary.count, overdue: root.summary.overdue,
                view: root.view, query: root.query, rows: root.tasks.length,
                selectedId: root.selected ? root.selected.id : null,
                mode: root.mode, inputFocused: editor.activeFocus, listFocused: keys.activeFocus,
                deleteConfirm: root.deleteTarget !== null, deleteTargetId: root.deleteTarget ? root.deleteTarget.id : null,
                rect: {x: popup.cardOrigin.x, y: popup.cardOrigin.y, width: popup.contentWidth, height: popup.contentHeight}});
        }
    }
    Process {
        id: poll
        property string requestView: ""
        property string requestQuery: ""
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    let data = JSON.parse(this.text);
                    root.summary = data.summary;
                    root.loaded = true;
                    root.loadError = "";
                    if (poll.requestView === root.view && poll.requestQuery === root.query && JSON.stringify(root.tasks) !== JSON.stringify(data.tasks)) {
                        let previous = root.selected ? root.selected.id : "";
                        let index = list.currentIndex;
                        root.tasks = data.tasks;
                        let found = root.tasks.findIndex(t => t.id === previous);
                        list.currentIndex = found >= 0 ? found : (index >= 0 ? Math.min(index, root.tasks.length - 1) : -1);
                    }
                } catch (e) { root.loadError = "Unable to read tasks. Check Omatask installation."; }
            }
        }
        stderr: StdioCollector { id: pollError }
        onExited: (code, status) => {
            if (code !== 0) root.loadError = pollError.text.trim() || "Omatask could not start.";
            if (root.refreshPending) Qt.callLater(root.refresh);
        }
    }
    Process {
        id: mutation
        property string operation: ""
        stdout: StdioCollector { id: result }
        stderr: StdioCollector { id: commandError }
        onExited: (code, status) => {
            if (code !== 0) {
                root.error = commandError.text.trim() || "Command failed. Your input was kept.";
                return;
            }
            if (operation === "show") {
                try { root.detail = JSON.parse(result.text); }
                catch (e) { root.error = "Unable to read task details."; }
                keys.forceActiveFocus();
                return;
            }
            root.detail = null;
            root.helpShown = false;
            root.deleteTarget = null;
            root.message = operation === "add" ? "Task created" : "Saved";
            editor.text = "";
            root.mode = "add";
            root.refreshAll();
            if (operation === "add" && root.closeAfterAdd) root.close();
            else if (operation === "add") editor.forceActiveFocus();
            else keys.forceActiveFocus();
        }
    }
    Timer {
        interval: root.opened ? 3000 : 10000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: root.refresh()
    }
    WidgetButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        text: root.loadError ? "Tasks: !" : (!root.loaded ? "Tasks: …" : (root.vertical ? String(root.summary.count) : "Tasks: " + root.summary.count) + (root.summary.overdue ? " · " + root.summary.overdue + "!" : ""))
        active: root.summary.overdue > 0
        tooltipText: root.error || root.loadError || (root.summary.count + " today · " + root.summary.overdue + " overdue\nLeft: tasks · Right: quick add · Middle: terminal")
        onPressed: function(b) {
            if (b === Qt.RightButton) root.quick();
            else if (b === Qt.MiddleButton) root.launchTui();
            else root.toggle();
        }
    }
    KeyboardPanel {
        id: popup
        bar: root.bar
        owner: root
        anchorItem: button
        open: root.opened
        focusTarget: editor
        contentWidth: popup.fittedContentWidth(Style.space(610))
        contentHeight: popup.cappedContentHeight(Style.space(540))

        Item {
            id: keys
            anchors.fill: parent
            focus: true
            Keys.onPressed: function(event) {
                if (root.deleteTarget) {
                    if (!root.busy) deleteDialog.handleKey(event);
                    event.accepted = true;
                    return;
                }
                if (editor.activeFocus) return;
                if (event.key === Qt.Key_F1 || event.text === "?") { root.toggleHelp(); event.accepted = true; return; }
                if (root.helpShown) {
                    if (event.key === Qt.Key_Escape) root.toggleHelp();
                    else if (event.key === Qt.Key_Down || event.text === "j") creationHelp.scrollBy(Style.space(45));
                    else if (event.key === Qt.Key_Up || event.text === "k") creationHelp.scrollBy(-Style.space(45));
                    else if (event.key === Qt.Key_PageDown || event.key === Qt.Key_Space) creationHelp.scrollBy(creationHelp.height * 0.85);
                    else if (event.key === Qt.Key_PageUp) creationHelp.scrollBy(-creationHelp.height * 0.85);
                    else if (event.key === Qt.Key_Home) creationHelp.contentY = 0;
                    else if (event.key === Qt.Key_End) creationHelp.scrollBy(creationHelp.contentHeight);
                    else if (event.key === Qt.Key_Tab) editor.forceActiveFocus();
                    event.accepted = true;
                    return;
                }
                if (event.key === Qt.Key_Escape) {
                    if (root.detail) root.detail = null;
                    else if (root.mode === "search" || root.query) root.exitSearch();
                    else root.close();
                } else if (event.key === Qt.Key_Down || event.text === "j") root.focusList(1);
                else if (event.key === Qt.Key_Up || event.text === "k") root.focusList(-1);
                else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) root.taskAction("show");
                else if (event.text === "a") root.beginInput("add", "");
                else if (event.text === "/") root.beginInput("search", root.query);
                else if (event.text === "d") root.taskAction("done");
                else if (event.text === "c") root.taskAction("cancel");
                else if (event.text === "r") root.taskAction("reopen");
                else if (event.text === "p") root.taskAction("priority");
                else if (event.text === "e" && root.selected) root.beginInput("edit", root.selected.title);
                else if (event.text === "m" && root.selected) root.beginInput("project", root.selected.project);
                else if (event.text === "t" && root.selected) root.beginInput("tags", root.selected.tags.join(" "));
                else if (event.text === "s" && root.selected) root.beginInput("snooze", "10m");
                else if ((event.key === Qt.Key_Delete || ["x", "X", "ч", "Ч"].indexOf(event.text) !== -1) && root.selected) root.requestDelete(root.selected);
                else if (event.text === "f" || event.key === Qt.Key_Tab) root.changeView(root.views[(root.views.indexOf(root.view) + 1) % root.views.length]);
                else if (event.text === "o") root.launchTui();
                else return;
                event.accepted = true;
            }
            Column {
                id: content
                anchors.fill: parent
                spacing: Style.space(12)
                Row {
                    width: parent.width
                    height: Style.space(30)
                    Text {
                        width: parent.width - Style.space(120)
                        anchors.verticalCenter: parent.verticalCenter
                        text: root.helpShown ? "CREATE A TASK  /  HELP" : "TASKS  /  " + root.view.toUpperCase()
                        textFormat: Text.PlainText
                        color: Color.foreground
                        font.family: Style.font.family
                        font.pixelSize: Style.font.body
                        font.bold: true
                    }
                    PanelActionButton { iconText: "+"; tooltipText: "New task (a)"; onClicked: root.beginInput("add", "") }
                    PanelActionButton { iconText: "⌕"; tooltipText: "Search (/)"; onClicked: root.beginInput("search", root.query) }
                    PanelActionButton { iconText: "?"; tooltipText: "Task creation help (F1)"; onClicked: root.toggleHelp() }
                    PanelActionButton { iconText: "×"; tooltipText: "Close (Esc)"; onClicked: root.close() }
                }
                Flow {
                    width: parent.width
                    spacing: Style.space(8)
                    Repeater {
                        model: root.views
                        delegate: Rectangle {
                            id: viewChip
                            required property string modelData
                            height: Style.space(26)
                            width: viewText.implicitWidth + Style.space(12)
                            radius: Style.cornerRadius
                            color: root.view === viewChip.modelData ? Style.selectionFillFor(Color.foreground, Color.accent) : "transparent"
                            Text {
                                id: viewText
                                anchors.centerIn: parent
                                text: viewChip.modelData.charAt(0).toUpperCase() + viewChip.modelData.slice(1)
                                color: root.view === viewChip.modelData ? Color.accent : Color.foreground
                                font.family: Style.font.family
                                font.pixelSize: Style.font.bodySmall
                            }
                            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: { root.changeView(viewChip.modelData); keys.forceActiveFocus(); } }
                        }
                    }
                }
                TextField {
                    id: editor
                    width: parent.width
                    enabled: !root.busy && !root.deleteTarget
                    placeholderText: ({add: "New task · / to search · tomorrow 18:00 #work !high", search: "Search title and description…",
                        edit: "Task title", project: "Project", tags: "Tags separated by spaces",
                        snooze: "10m / 30m / 1h / evening / tomorrow"})[root.mode]
                    Keys.onPressed: function(event) {
                        if (event.key === Qt.Key_F1 || (event.key === Qt.Key_Escape && root.helpShown)) {
                            root.toggleHelp(); event.accepted = true;
                        } else if (event.text === "/" && root.mode === "add" && editor.text.length === 0 &&
                                   !(event.modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier))) {
                            root.beginInput("search", root.query); event.accepted = true;
                        } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                            root.submit(); event.accepted = true;
                        } else if (event.key === Qt.Key_Escape) {
                            if (root.mode === "search") root.exitSearch();
                            else if (root.mode !== "add") { root.mode = "add"; editor.text = ""; }
                            else if (!editor.text) root.close();
                            keys.forceActiveFocus();
                            event.accepted = true;
                        } else if (event.key === Qt.Key_Down || event.key === Qt.Key_Tab) {
                            root.focusList(0); event.accepted = true;
                        }
                    }
                }
                Text {
                    width: parent.width
                    visible: text !== ""
                    text: root.error || root.loadError || (root.busy ? "Saving…" : root.query ? "Search: " + root.query + "  · / then Enter clears" : root.message)
                    textFormat: Text.PlainText
                    color: root.error || root.loadError ? Color.urgent : Color.accent
                    font.family: Style.font.family
                    font.pixelSize: Style.font.bodySmall
                    wrapMode: Text.Wrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                }
                Item {
                    width: parent.width
                    height: Math.max(Style.space(100), content.height - y - footer.implicitHeight - Style.space(12))
                    ListView {
                        id: list
                        anchors.fill: parent
                        clip: true
                        visible: !root.detail && !root.helpShown
                        model: root.tasks
                        currentIndex: -1
                        spacing: Style.space(4)
                        boundsBehavior: Flickable.StopAtBounds
                        delegate: Rectangle {
                            id: taskRow
                            property alias deleteButtonItem: deleteButton
                            required property var modelData
                            required property int index
                            width: ListView.view.width
                            height: Style.space(64)
                            radius: Style.cornerRadius
                            color: list.currentIndex === taskRow.index ? Style.selectionFillFor(Color.foreground, Color.accent) : "transparent"
                            border.width: list.currentIndex === taskRow.index ? Math.max(1, Style.space(2)) : 0
                            border.color: Color.accent
                            MouseArea {
                                anchors.fill: parent
                                onClicked: root.selectTask(taskRow.index)
                                onDoubleClicked: { list.currentIndex = taskRow.index; root.taskAction("show"); }
                            }
                            Column {
                                anchors.left: parent.left
                                anchors.right: rowActions.left
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.margins: Style.space(10)
                                spacing: Style.space(5)
                                Text {
                                    width: parent.width
                                    text: taskRow.modelData.title
                                    textFormat: Text.PlainText
                                    color: Color.foreground
                                    font.family: Style.font.family
                                    font.pixelSize: Style.font.body
                                    elide: Text.ElideRight
                                }
                                Text {
                                    width: parent.width
                                    text: taskRow.modelData.due_label + " · " + taskRow.modelData.priority + (taskRow.modelData.recurrence ? " · ↻" : "") +
                                        (taskRow.modelData.daily_reminder_label ? " · " + taskRow.modelData.daily_reminder_label : "") +
                                        (taskRow.modelData.status !== "active" ? " · " + taskRow.modelData.status : "") +
                                        (taskRow.modelData.project ? " · " + taskRow.modelData.project : "") +
                                        (taskRow.modelData.progress.total ? " · " + taskRow.modelData.progress.done + "/" + taskRow.modelData.progress.total : "") +
                                        (taskRow.modelData.tags.length ? " · #" + taskRow.modelData.tags.join(" #") : "")
                                    textFormat: Text.PlainText
                                    color: taskRow.modelData.overdue ? Color.urgent : Qt.darker(Color.foreground, 1.45)
                                    font.family: Style.font.family
                                    font.pixelSize: Style.font.bodySmall
                                    elide: Text.ElideRight
                                }
                            }
                            Row {
                                id: rowActions
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.rightMargin: Style.space(8)
                                spacing: Style.space(6)
                                PanelActionButton {
                                    iconText: taskRow.modelData.status === "active" ? "✓" : "↶"
                                    tooltipText: taskRow.modelData.status === "active" ? "Complete (d)" : "Reopen (r)"
                                    enabled: !root.busy
                                    onClicked: { root.selectTask(taskRow.index); root.taskAction(taskRow.modelData.status === "active" ? "done" : "reopen"); }
                                }
                                Button {
                                    id: deleteButton
                                    text: "Delete"
                                    fontSize: Style.font.bodySmall
                                    foreground: Color.urgent
                                    bordered: true
                                    enabled: !root.busy
                                    tooltipText: "Delete task (Delete / x)"
                                    onClicked: { root.selectTask(taskRow.index); root.requestDelete(taskRow.modelData); }
                                }
                            }
                        }
                    }
                    Text {
                        anchors.centerIn: parent
                        visible: !root.detail && !root.helpShown && root.tasks.length === 0
                        text: root.loaded ? "No tasks in this view.\nPress a to add a task." : "Loading tasks…"
                        color: Qt.darker(Color.foreground, 1.4)
                        font.family: Style.font.family
                        font.pixelSize: Style.font.body
                        horizontalAlignment: Text.AlignHCenter
                    }
                    Flickable {
                        anchors.fill: parent
                        visible: root.detail !== null && !root.helpShown
                        contentHeight: detailText.implicitHeight
                        clip: true
                        Text {
                            id: detailText
                            width: parent.width
                            text: root.detail ? root.detail.title + "\n\n" + (root.detail.description || "No description") +
                                "\n\nStatus: " + root.detail.status + " · " + root.detail.priority +
                                "\nCompleted: " + root.detail.completed_count + " · Remaining: " + (root.detail.remaining_count === null ? "—" : root.detail.remaining_count) +
                                "\nNext: " + (root.detail.next_occurrence || "—") +
                                (root.detail.daily_reminders && root.detail.daily_reminders.length ? "\n\nDaily reminders: " + root.detail.daily_reminders.join(", ") : "") +
                                "\n\n" + root.detail.subtasks.map(s => (s.done ? "✓ " : "□ ") + s.title).join("\n") +
                                "\n\nEsc returns to list · o opens the full editor" : ""
                            textFormat: Text.PlainText
                            wrapMode: Text.Wrap
                            color: Color.foreground
                            font.family: Style.font.family
                            font.pixelSize: Style.font.body
                        }
                    }
                    CreationHelp {
                        id: creationHelp
                        anchors.fill: parent
                        visible: root.helpShown
                        onExampleChosen: value => root.beginInput("add", value)
                    }
                }
                Text {
                    id: footer
                    width: parent.width
                    text: root.helpShown ? "↑↓ / PgUp / PgDn scroll · Tab input\nEsc / F1 close help · Enter creates the task after inserting an example" :
                        "a add · / search · ↑↓ select · d done · s snooze\nDelete remove · e edit · f view · F1 help · o terminal" +
                        (!root.detail && (root.mode === "search" || (root.query && !editor.activeFocus)) ? " · Esc exits search" : "")
                    color: Qt.darker(Color.foreground, 1.5)
                    font.family: Style.font.family
                    font.pixelSize: Style.font.caption
                    textFormat: Text.PlainText
                    wrapMode: Text.Wrap
                }
            }
            ConfirmDialog {
                id: deleteDialog
                anchors.fill: parent
                z: 100
                opened: root.deleteTarget !== null
                enabled: !root.busy
                message: root.deleteTarget ? "Delete “" + root.deleteTarget.title + "”?\nIts history and reminders will also be removed." + (root.error ? "\n\n" + root.error : "") : ""
                cancelText: "Cancel"
                confirmText: "Delete"
                onCanceled: { root.deleteTarget = null; keys.forceActiveFocus(); }
                onConfirmed: if (root.deleteTarget) root.runCommand(["delete", root.deleteTarget.id], "delete")
            }
        }
    }
}
