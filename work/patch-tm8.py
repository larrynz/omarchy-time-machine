#!/usr/bin/env python3
import sys

def rep(path, old, new, name):
    with open(path) as f:
        src = f.read()
    n = src.count(old)
    if n != 1:
        print(f"FAIL {name}: found {n} occurrences in {path}"); sys.exit(1)
    with open(path, "w") as f:
        f.write(src.replace(old, new))
    print(f"ok   {name}")

STORE = "TimeMachineStore.qml"
PANEL = "Panel.qml"

# --- store: the guided setup ----------------------------------------------------
rep(STORE,
r'''  function openLog() {
    if (!lastRun || !lastRun.log_file) return
    logProc.command = ["xdg-open", String(lastRun.log_file)]
    logProc.running = true
  }

  Process { id: logProc }''',
r'''  function openLog() {
    if (!lastRun || !lastRun.log_file) return
    logProc.command = ["xdg-open", String(lastRun.log_file)]
    logProc.running = true
  }

  Process { id: logProc }

  // --- guided setup ---------------------------------------------------------

  // The setup screen runs one command: apply-setup reads its document on
  // stdin, validates it against the same rules the units will get, and does
  // everything a first run needs -- config, key, repository, timers. The
  // password travels inside the document, on stdin, never on a command line:
  // a command line is readable by any process on the machine, stdin is not.
  // write() drops its data when the process is not running yet, so the
  // document is written on the started signal, not before.
  property bool setupBusy: false
  property string setupError: ""
  property string setupDone: ""
  property string setupPendingDoc: ""

  function applySetup(doc) {
    if (setupBusy) return
    setupBusy = true
    setupError = ""
    setupDone = ""
    setupPendingDoc = JSON.stringify(doc)
    applyProc.command = [root.cli, "apply-setup"]
    applyProc.running = true
  }

  Process {
    id: applyProc
    onStarted: write(setupPendingDoc)
    stdout: StdioCollector {
      onStreamFinished: {
        // The install step prints systemctl's timer table, which wrapped at
        // panel width is unreadable. Keep the lines that say what happened,
        // drop the table, keep the final line that says it worked.
        var t = text
        var i = t.indexOf("Next run:")
        if (i !== -1) {
          var j = t.indexOf("Setup complete")
          t = t.substring(0, i) + (j !== -1 ? t.substring(j) : "")
        }
        root.setupDone = t.trim()
      }
    }
    stderr: StdioCollector {
      onStreamFinished: if (text !== "") root.setupError = text
    }
    onFinished: function(exitCode, exitStatus) {
      root.setupBusy = false
      root.refresh()
    }
  }''',
"store: applySetup + applyProc")

# --- panel: state + wiring -------------------------------------------------------
rep(PANEL,
r'''  property bool browsing: false''',
r'''  property bool browsing: false

  // The guided first run. Separate from browsing: browsing is reading history
  // and hands the keyboard to the listing, setting up is typing and hands it
  // to the form.
  property bool settingUp: false''',
"panel: settingUp state")

rep(PANEL,
r'''  onOpenedChanged: {
    if (!opened) {
      root.browsing = false
      return
    }
    TimeMachineStore.refresh()
  }''',
r'''  onOpenedChanged: {
    if (!opened) {
      root.browsing = false
      root.settingUp = false
      return
    }
    TimeMachineStore.refresh()
  }''',
"panel: reset settingUp on close")

rep(PANEL,
r'''  onBrowsingChanged: {
    if (browsing) browser.takeFocus()
    else keyCatcher.forceActiveFocus()
  }''',
r'''  onBrowsingChanged: {
    if (browsing) browser.takeFocus()
    else if (!settingUp) keyCatcher.forceActiveFocus()
  }

  onSettingUpChanged: {
    if (settingUp) setupName.forceActiveFocus()
    else if (!browsing) keyCatcher.forceActiveFocus()
  }''',
"panel: focus handoff for the setup view")

rep(PANEL,
r'''      blocked: root.browsing''',
r'''      blocked: root.browsing || root.settingUp''',
"panel: keyCatcher blocked while setting up")

rep(PANEL,
r'''      onCloseRequested: {
        if (stopConfirm.opened) stopConfirm.opened = false
        else if (root.browsing && browser.confirmOpen) browser.confirmCancel()
        else if (root.browsing && browser.filter !== "") browser.clearFilter()
        else if (root.browsing) root.browsing = false
        else root.close()
      }''',
r'''      onCloseRequested: {
        if (stopConfirm.opened) stopConfirm.opened = false
        else if (root.browsing && browser.confirmOpen) browser.confirmCancel()
        else if (root.browsing && browser.filter !== "") browser.clearFilter()
        else if (root.browsing) root.browsing = false
        else if (root.settingUp) root.settingUp = false
        else root.close()
      }''',
"panel: Escape backs out of the setup view")

rep(PANEL,
r'''    readonly property int desiredWidth: Style.space(root.browsing ? 460 : 280)''',
r'''    readonly property int desiredWidth:
      Style.space(root.browsing ? 460 : (root.settingUp ? 420 : 280))''',
"panel: width for the setup view")

rep(PANEL,
r'''    contentHeight: panel.fittedContentHeight(
                     root.browsing ? browser.implicitHeight : mainColumn.implicitHeight,
                     Style.space(560))''',
r'''    contentHeight: panel.fittedContentHeight(
                     root.browsing ? browser.implicitHeight
                                   : (root.settingUp ? setupColumn.implicitHeight
                                                     : mainColumn.implicitHeight),
                     Style.space(560))''',
"panel: height for the setup view")

# --- panel: the setup view --------------------------------------------------------
rep(PANEL,
r'''      RestoreBrowser {
        id: browser
        anchors.fill: parent
        visible: root.browsing
        foreground: root.foreground
        dim: root.dim
        accent: root.accent
        urgent: root.urgent
        fontFamily: root.fontFamily
        onBack: root.browsing = false
      }
    }''',
r'''      RestoreBrowser {
        id: browser
        anchors.fill: parent
        visible: root.browsing
        foreground: root.foreground
        dim: root.dim
        accent: root.accent
        urgent: root.urgent
        fontFamily: root.fontFamily
        onBack: root.browsing = false
      }

      // --- setup view --------------------------------------------------------

      // The guided first run. The old path was "open config.json in your
      // editor", which is how all six setup snags happened: each was caught
      // too late or pointed at the wrong fix. This form asks the same
      // questions where the user is, and runs one command that validates
      // everything against the same rules the units will get and refuses
      // loudly before anything is written.
      Flickable {
        id: setupScroll
        anchors.fill: parent
        visible: root.settingUp
        contentWidth: width
        contentHeight: setupColumn.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        interactive: contentHeight > height
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        Column {
          id: setupColumn
          width: setupScroll.width
          spacing: 0

          Text {
            width: parent.width
            bottomPadding: Style.space(8)
            text: "Set up backups"
            textFormat: Text.PlainText
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }

          Text {
            width: parent.width
            bottomPadding: Style.space(8)
            text: "One destination, one repository, one schedule. The password is stored in a 600 file next to the configuration, never in the configuration itself."
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            color: root.dimmer
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }

          Text {
            width: parent.width
            bottomPadding: Style.space(2)
            text: "Name"
            textFormat: Text.PlainText
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }

          TextField {
            id: setupName
            width: parent.width
            placeholderText: "backup"
            font.family: root.fontFamily
            font.pixelSize: Style.font.body
            color: root.foreground
            placeholderTextColor: root.dimmer
            selectByMouse: true
            background: Rectangle {
              color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.06)
              radius: Style.space(4)
              border.width: 1
              border.color: setupName.activeFocus ? root.accent
                            : Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.18)
            }
          }

          Text {
            width: parent.width
            topPadding: Style.space(6)
            bottomPadding: Style.space(2)
            text: "Repository"
            textFormat: Text.PlainText
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }

          TextField {
            id: setupRepo
            width: parent.width
            placeholderText: "/run/media/\u2026/restic"
            font.family: root.fontFamily
            font.pixelSize: Style.font.body
            color: root.foreground
            placeholderTextColor: root.dimmer
            selectByMouse: true
            background: Rectangle {
              color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.06)
              radius: Style.space(4)
              border.width: 1
              border.color: setupRepo.activeFocus ? root.accent
                            : Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.18)
            }
          }

          Text {
            width: parent.width
            topPadding: Style.space(6)
            bottomPadding: Style.space(2)
            text: "Password"
            textFormat: Text.PlainText
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }

          TextField {
            id: setupPassword
            width: parent.width
            echoMode: TextInput.Password
            font.family: root.fontFamily
            font.pixelSize: Style.font.body
            color: root.foreground
            selectByMouse: true
            background: Rectangle {
              color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.06)
              radius: Style.space(4)
              border.width: 1
              border.color: setupPassword.activeFocus ? root.accent
                            : Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.18)
            }
          }

          Text {
            width: parent.width
            topPadding: Style.space(6)
            bottomPadding: Style.space(2)
            text: "Schedule"
            textFormat: Text.PlainText
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }

          MenuRow {
            width: parent.width
            label: setupSchedule + " \u2014 click to change"
            foreground: root.foreground
            fontFamily: root.fontFamily
            onClicked: {
              var presets = ["daily", "weekly", "monthly", "hourly", "manual"]
              var i = presets.indexOf(setupSchedule)
              setupSchedule = presets[(i + 1) % presets.length]
            }
          }

          PanelSeparator { width: parent.width; foreground: root.foreground }

          Text {
            width: parent.width
            visible: root.setupValidationError !== ""
            topPadding: visible ? Style.space(6) : 0
            bottomPadding: visible ? Style.space(6) : 0
            text: root.setupValidationError
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            color: root.urgent
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }

          Text {
            width: parent.width
            visible: TimeMachineStore.setupError !== ""
            topPadding: visible ? Style.space(6) : 0
            bottomPadding: visible ? Style.space(6) : 0
            text: TimeMachineStore.plain(TimeMachineStore.setupError)
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            color: root.urgent
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }

          Text {
            width: parent.width
            visible: TimeMachineStore.setupBusy
            topPadding: Style.space(4)
            bottomPadding: Style.space(4)
            text: "Applying \u2014 creating the repository and switching on the schedule\u2026"
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }

          Text {
            width: parent.width
            visible: !TimeMachineStore.setupBusy && TimeMachineStore.setupDone !== ""
                     && root.setupValidationError === "" && TimeMachineStore.setupError === ""
            text: TimeMachineStore.plain(TimeMachineStore.setupDone)
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }

          MenuRow {
            width: parent.width
            label: "Apply"
            foreground: root.foreground
            fontFamily: root.fontFamily
            onClicked: {
              if (TimeMachineStore.setupBusy) return
              var name = setupName.text.trim()
              var repo = setupRepo.text.trim()
              if (name === "" || !/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(name)) {
                root.setupValidationError =
                  "Name must start with a letter or digit, and contain only letters, digits, dashes, dots and underscores"
                return
              }
              if (repo === "") {
                root.setupValidationError = "A repository path is required"
                return
              }
              if (setupPassword.text === "") {
                root.setupValidationError =
                  "A password is required \u2014 it is stored in a 600 file, never in the configuration"
                return
              }
              root.setupValidationError = ""
              TimeMachineStore.applySetup({
                name: name,
                display_name: name,
                repository: repo,
                schedule: setupSchedule,
                password: setupPassword.text
              })
            }
          }

          MenuRow {
            width: parent.width
            label: "Cancel"
            foreground: root.foreground
            fontFamily: root.fontFamily
            onClicked: root.settingUp = false
          }
        }
      }
    }''',
"panel: the setup view")

# --- panel: the entry point + the hint --------------------------------------------
rep(PANEL,
r'''          MenuRow {
            width: parent.width
            label: (TimeMachineStore.configured || TimeMachineStore.configInvalid)
                   ? "Open Configuration\u2026" : "Create Configuration\u2026"
            foreground: root.foreground
            fontFamily: root.fontFamily
            onClicked: {
              if (TimeMachineStore.configured || TimeMachineStore.configInvalid)
                TimeMachineStore.openConfig()
              else TimeMachineStore.createConfig()
              root.close()
            }
          }''',
r'''          MenuRow {
            width: parent.width
            label: (TimeMachineStore.configured || TimeMachineStore.configInvalid)
                   ? "Open Configuration\u2026" : "Set Up Backups\u2026"
            foreground: root.foreground
            fontFamily: root.fontFamily
            onClicked: {
              if (TimeMachineStore.configured || TimeMachineStore.configInvalid) {
                TimeMachineStore.openConfig()
                root.close()
              } else {
                root.settingUp = true
              }
            }
          }''',
"panel: the setup entry point")

rep(PANEL,
r'''              if (!TimeMachineStore.configured) return "Create one below and it opens in your editor"''',
r'''              if (!TimeMachineStore.configured) return "Set one up below and the panel walks you through it"''',
"panel: the unconfigured hint")

# --- panel: the validation-error property ------------------------------------------
rep(PANEL,
r'''  // The guided first run. Separate from browsing: browsing is reading history
  // and hands the keyboard to the listing, setting up is typing and hands it
  // to the form.
  property bool settingUp: false''',
r'''  // The guided first run. Separate from browsing: browsing is reading history
  // and hands the keyboard to the listing, setting up is typing and hands it
  // to the form.
  property bool settingUp: false
  property string setupValidationError: ""
  property string setupSchedule: "daily"''',
"panel: setupValidationError property")

print("all edits applied")
