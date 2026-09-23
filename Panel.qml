import Quickshell
import QtQuick
import QtQuick.Controls
import Qt.labs.folderlistmodel
import qs.Commons
import qs.Ui

// Time Machine: scheduled restic backups, with the state of the last one a
// glance away and a snapshot browser one click further.
//
// The bar shows the icon and nothing else. Bar space is scarce and the age of
// a backup is not a number anyone wants to read continuously -- you only want
// to be disturbed when something is wrong, which is what the colour is for.
// The relative time lives in the tooltip and at the top of the panel.
//
// Everything with state lives in TimeMachineStore, a singleton: a bar widget
// is instantiated once per monitor, so timers and processes declared here
// would run twice on a two-monitor setup.
Panel {
  id: root

  moduleName: "jankeesvw.time-machine"
  ipcTarget: "jankeesvw.time-machine"

  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color urgent: bar ? bar.urgent : Color.urgent
  readonly property color accent: Color.accent
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property color dimmer: Qt.darker(foreground, 2.2)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family

  // Which view the panel is showing. The restore browser reuses the same
  // KeyboardPanel and simply swaps the content, because a second window would
  // lose keyboard focus on Wayland the moment the first one closed.
  property bool browsing: false

  // The guided first run. Separate from browsing: browsing is reading history
  // and hands the keyboard to the listing, setting up is typing and hands it
  // to the form.
  property bool settingUp: false
  // The folder picker: a sub-state of setting up. The picker replaces the
  // form while it is open and hands the chosen path back to the field.
  property bool pickingRepo: false
  // What the picker is for: "repo" fills the repository field, "source"
  // adds a folder to the backup list.
  property string pickerTarget: "repo"
  // The folders to back up, edited in the setup form's list.
  property var setupSources: []
  property string pickerPath: "/run/media"
  property string setupValidationError: ""
  property string setupSchedule: "daily"
  // The password field's meaning: off, the text is the literal password (a
  // 600 key file); on, the text is a command that prints it -- pass show
  // <entry>, op read <secret>, anything that works where the backups run.
  property bool setupPassIsCommand: false
  // The setup form seeds its source list from the configuration, but the
  // status that carries the list is fetched asynchronously: the form can be
  // open before it arrives. Seed once on the first entry per panel lifetime
  // and re-seed when the fetch lands; after that the list is a draft like
  // every other field -- re-seeding on every entry would clobber folders
  // the user added but has not applied yet.
  property bool setupSeeded: false
  property bool setupEverOpened: false

  readonly property color barIconColor: {
    if (TimeMachineStore.running) return accent
    if (TimeMachineStore.failed) return urgent
    if (!TimeMachineStore.configured) return Qt.darker(barForeground, 1.9)
    return barForeground
  }

  // Panel is a bare Item with no size of its own, so without this the bar
  // hands the widget zero width -- and a zero-width widget still paints its
  // children, so it looks fine and is simply not clickable. Derive the size
  // from the content, never from a child that fills this item.
  // A failed backup gets a mark, not just a colour: colour alone is the one
  // signal a bar full of coloured glyphs cannot carry, and it is invisible to
  // anyone who does not distinguish red from the foreground.
  readonly property bool showBadge: TimeMachineStore.failed
  readonly property int badgeSize: showBadge ? Style.space(9) : 0
  readonly property int barContentWidth:
    Style.bar.iconFont + (showBadge ? badgeSize - Style.space(3) : 0)

  readonly property int barSlot: barContentWidth + Style.space(10)
  readonly property real openPanelIndicatorWidth: barContentWidth
  readonly property real openPanelIndicatorHeight: barContentWidth
  implicitWidth: bar && bar.vertical ? (bar ? bar.barSize : Style.bar.sizeHorizontal) : barSlot
  implicitHeight: bar && bar.vertical ? barSlot : (bar ? bar.barSize : Style.bar.sizeHorizontal)

  function applySettings() {
    TimeMachineStore.fontFamily = root.fontFamily
    TimeMachineStore.timeFormat = String(root.setting("timeFormat", "HH:mm"))
    TimeMachineStore.dateFormat = String(root.setting("dateFormat", "d MMM"))
  }

  // Applied on settingsChanged as well as on completion: the host assigns
  // `settings` after constructing the widget, so reading them only in
  // onCompleted means reading an empty object.
  onSettingsChanged: root.applySettings()
  Component.onCompleted: root.applySettings()

  onOpenedChanged: {
    if (!opened) {
      root.browsing = false
      // The picker is a sub-state of setting up, but the close reset above
      // did not cover it: click away while picking and the picker was still
      // visible when the panel reopened -- drawing over the main view until
      // the setup flow was re-entered.
      root.pickingRepo = false
      root.settingUp = false
      return
    }
    TimeMachineStore.refresh()
  }

  // With the key catcher blocked, nothing else claims the keyboard: the
  // listing has to take it, and give it back on the way out.
  onBrowsingChanged: {
    if (browsing) browser.takeFocus()
    else if (!settingUp) keyCatcher.forceActiveFocus()
  }

  onSettingUpChanged: {
    if (settingUp) {
      setupName.forceActiveFocus()
      // Seed only on the first entry: afterwards the source list is a draft
      // that survives closing the panel, like the name, repo and password
      // fields. Re-seeding here would wipe folders the user added but has
      // not applied yet.
      if (!root.setupEverOpened) {
        root.setupEverOpened = true
        root.setupSeeded = false
        var src = TimeMachineStore.sources && TimeMachineStore.sources.length > 0
                  ? TimeMachineStore.sources : []
        root.setupSources = src.length > 0 ? src.slice() : [Quickshell.env("HOME") || "/"]
      }
    } else if (!browsing) {
      keyCatcher.forceActiveFocus()
    }
  }

  Connections {
    target: TimeMachineStore
    function onSourcesChanged() {
      if (!root.settingUp || root.setupSeeded) return
      root.setupSeeded = true
      var src = TimeMachineStore.sources && TimeMachineStore.sources.length > 0
                ? TimeMachineStore.sources.slice() : []
      root.setupSources = src.length > 0 ? src : [Quickshell.env("HOME") || "/"]
    }
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    slotSize: root.barSlot
    // iconComponent is loaded into a square canvas of opticalSize, sized for a
    // single glyph. Widen it too, or the badge falls outside it.
    opticalSize: root.barContentWidth
    // The shared bar tooltip is a shell component, so its textFormat is not
    // ours to set: strip anything that could be read as markup before it goes
    // in. Our own strings are safe, but a destination name comes from
    // config.json and an error message comes from restic.
    tooltipText: TimeMachineStore.plain(TimeMachineStore.tooltip)

    iconComponent: Component {
      Item {
        Text {
          anchors.centerIn: parent
          text: TimeMachineStore.iconTimeMachine
          textFormat: Text.PlainText
          font.family: root.fontFamily
          font.pixelSize: Style.bar.iconFont
          renderType: Text.NativeRendering
          color: root.barIconColor

          // A slow pulse while a backup runs. Deliberately not a percentage in
          // the bar: the number would demand to be read, where the pulse only
          // says "busy" and the panel carries the detail.
          SequentialAnimation on opacity {
            running: TimeMachineStore.running
            loops: Animation.Infinite
            alwaysRunToEnd: true
            NumberAnimation { from: 1.0; to: 0.45; duration: 900; easing.type: Easing.InOutQuad }
            NumberAnimation { from: 0.45; to: 1.0; duration: 900; easing.type: Easing.InOutQuad }
          }
          onVisibleChanged: if (!TimeMachineStore.running) opacity = 1.0
        }

        // Exclamation badge, pinned to the glyph's top right.
        Rectangle {
          visible: root.showBadge
          width: root.badgeSize
          height: root.badgeSize
          radius: width / 2
          color: root.urgent
          anchors.horizontalCenter: parent.horizontalCenter
          anchors.horizontalCenterOffset: Style.bar.iconFont / 2
          anchors.verticalCenter: parent.verticalCenter
          anchors.verticalCenterOffset: -Style.bar.iconFont / 2.6

          Text {
            anchors.centerIn: parent
            text: "!"
            textFormat: Text.PlainText
            color: Color.background
            font.family: root.fontFamily
            font.pixelSize: Math.round(root.badgeSize * 0.8)
            font.bold: true
            renderType: Text.NativeRendering
          }
        }
      }
    }

    onPressed: function(buttonCode) {
      if (buttonCode === Qt.RightButton) TimeMachineStore.refresh()
      else root.toggle()
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher

    // Computed from plain property reads rather than through
    // fittedContentWidth inside the binding: that form evaluates once at open
    // and never re-runs, so the panel would keep the width of whichever view
    // happened to be showing when it opened.
    readonly property int desiredWidth:
      Style.space(root.browsing ? 460 : (root.settingUp ? 420 : 280))
    contentWidth: Math.min(desiredWidth,
                           panel.availableCardWidth > 0 ? panel.availableCardWidth : desiredWidth)
    contentHeight: panel.fittedContentHeight(
                     root.browsing ? browser.implicitHeight
                                   : (root.pickingRepo ? pickerColumn.implicitHeight
                                   : (root.settingUp ? setupColumn.implicitHeight
                                                     : mainColumn.implicitHeight)),
                     Style.space(560))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent

      // Blocked while browsing, and that is not a detail: this component bakes
      // in vim navigation -- "j", "k", "l", "h" move the cursor and "x" is
      // delete, all checked before the plain-text fallback. Typing to filter a
      // listing is impossible under it; any word containing one of those
      // letters would steer the panel instead. While browsing the listing
      // handles its own keys.
      blocked: root.browsing || root.settingUp

      // ConfirmDialog handles the mouse itself but nothing else: without this
      // an open dialog would swallow Escape and Enter, and the only way out
      // would be to reach for the trackpad. Innermost dialog first, so Escape
      // dismisses the confirmation rather than the whole panel.
      onCloseRequested: {
        if (stopConfirm.opened) stopConfirm.opened = false
        else if (root.browsing && browser.confirmOpen) browser.confirmCancel()
        else if (root.browsing && browser.filter !== "") browser.clearFilter()
        else if (root.browsing) root.browsing = false
        else if (root.pickingRepo) root.pickingRepo = false
        else if (root.settingUp) root.settingUp = false
        else root.close()
      }

      onActivateRequested: {
        if (stopConfirm.opened) {
          TimeMachineStore.stopBackup()
          stopConfirm.opened = false
        } else if (root.browsing && browser.confirmOpen) {
          browser.confirmAccept()
        }
      }

      onTabRequested: function(direction) { root.switchPanel(direction) }

      // --- main view ------------------------------------------------------

      Flickable {
        id: mainScroll
        anchors.fill: parent
        // Hidden while browsing AND while setting up: neither of those views
        // hides itself, so a setup form that forgot this line drew straight
        // over the main view -- both visible, overlapping text, unreadable.
        visible: !root.browsing && !root.settingUp
        contentWidth: width
        contentHeight: mainColumn.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        interactive: contentHeight > height
        ScrollBar.vertical: ScrollBar { policy: mainScroll.contentHeight > mainScroll.height ? ScrollBar.AlwaysOn : ScrollBar.AsNeeded }

        Column {
          id: mainColumn
          width: mainScroll.width
          spacing: 0

          // A menu, not a dashboard: a dimmed two-line status at the top, then
          // plain left-aligned actions separated by hairlines. Modelled on the
          // macOS Time Machine menu-bar item, which says what it knows in two
          // lines and then gets out of the way.

          // --- status header ---------------------------------------------

          Text {
            width: parent.width
            bottomPadding: Style.space(8)
            text: {
              if (TimeMachineStore.configInvalid) return "There is a problem with your configuration"
              if (!TimeMachineStore.configured) return "No backups are set up yet"
              if (TimeMachineStore.anyRunning) return "Backing up"
              if (TimeMachineStore.anyFailed) return "A backup failed"
              return "Backups"
            }
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            color: (TimeMachineStore.anyFailed || TimeMachineStore.configInvalid)
                   ? root.urgent : root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }

          // Only shown when the configuration itself is the problem, because
          // then there is no list to explain anything.
          Text {
            width: parent.width
            visible: text !== ""
            bottomPadding: visible ? Style.space(8) : 0
            text: {
              if (TimeMachineStore.configInvalid) return TimeMachineStore.configError
              if (!TimeMachineStore.configured) return "Set one up below and the panel walks you through it"
              return ""
            }
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            color: TimeMachineStore.configInvalid ? root.urgent : root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }

          // Every destination, always, even when there is only one. One
          // layout means the panel does not rearrange itself the day you add a
          // second drive, and "which one is active" stops being a question:
          // they all run on their own schedule and they all matter.
          Column {
            width: parent.width
            spacing: Style.space(6)
            bottomPadding: Style.space(8)

            Repeater {
              model: TimeMachineStore.destinations

              Column {
                width: parent.width
                spacing: Style.space(1)

                Item {
                  width: parent.width
                  height: Style.space(18)

                  Text {
                    anchors.left: parent.left
                    anchors.right: stateText.left
                    anchors.rightMargin: Style.space(8)
                    anchors.verticalCenter: parent.verticalCenter
                    text: TimeMachineStore.destinationLabel(modelData)
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                    color: root.foreground
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.body
                  }

                  Text {
                    id: stateText
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    text: TimeMachineStore.destinationState(modelData)
                    textFormat: Text.PlainText
                    color: TimeMachineStore.destinationFailed(modelData) ? root.urgent : root.dim
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.body
                  }
                }

                // After a failure the useful number is not how big the
                // repository is, but how old your newest good copy now is.
                Text {
                  width: parent.width
                  visible: text !== ""
                  text: TimeMachineStore.destinationDetail(modelData)
                  textFormat: Text.PlainText
                  elide: Text.ElideRight
                  color: TimeMachineStore.destinationFailed(modelData) ? root.dim : root.dimmer
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                }
              }
            }
          }

          // --- progress ----------------------------------------------------

          Rectangle {
            width: parent.width
            visible: TimeMachineStore.running
            height: visible ? Style.space(3) : 0
            radius: height / 2
            color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.15)

            Rectangle {
              height: parent.height
              radius: parent.radius
              color: root.accent
              width: {
                var pr = TimeMachineStore.progress
                if (!pr || pr.percent === undefined || pr.percent === null) return 0
                return Math.max(0, Math.min(1, Number(pr.percent))) * parent.width
              }
              Behavior on width { NumberAnimation { duration: 300 } }
            }
          }

          Text {
            width: parent.width
            visible: TimeMachineStore.running && text !== ""
            topPadding: visible ? Style.space(4) : 0
            bottomPadding: visible ? Style.space(4) : 0
            text: {
              var pr = TimeMachineStore.progress
              if (!pr || !pr.total_bytes) return ""
              return TimeMachineStore.humanBytes(pr.bytes_done) + " of "
                     + TimeMachineStore.humanBytes(pr.total_bytes)
            }
            textFormat: Text.PlainText
            elide: Text.ElideRight
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }

          // --- actions -----------------------------------------------------

          PanelSeparator { width: parent.width; foreground: root.foreground }

          MenuRow {
            width: parent.width
            visible: TimeMachineStore.configured && TimeMachineStore.unitsInstalled
            label: TimeMachineStore.anyRunning ? "Stop This Backup" : "Back Up Now"
            destructive: TimeMachineStore.anyRunning
            foreground: root.foreground
            fontFamily: root.fontFamily
            onClicked: {
              if (TimeMachineStore.anyRunning) stopConfirm.opened = true
              else if (TimeMachineStore.multiple) TimeMachineStore.startAllBackups()
              else TimeMachineStore.startBackup()
            }
          }

          // Rather than an action that silently does nothing, say what is
          // missing. This is the state every fresh install starts in.
          Text {
            width: parent.width
            visible: TimeMachineStore.configured && !TimeMachineStore.unitsInstalled
            topPadding: visible ? Style.space(6) : 0
            bottomPadding: visible ? Style.space(6) : 0
            text: "Run \u2018omarchy-time-machine install\u2019 once to enable backups"
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }

          PanelSeparator {
            width: parent.width
            foreground: root.foreground
            visible: TimeMachineStore.configured
          }

          MenuRow {
            width: parent.width
            visible: TimeMachineStore.configured
            label: "Restore Files\u2026"
            foreground: root.foreground
            fontFamily: root.fontFamily
            onClicked: {
              root.browsing = true
              if (!TimeMachineStore.snapshotsLoaded || TimeMachineStore.snapshotsStale())
                TimeMachineStore.loadSnapshots()
            }
          }

          PanelSeparator { width: parent.width; foreground: root.foreground }

          MenuRow {
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
          }
        }
      }

      // --- restore view ------------------------------------------------------

      RestoreBrowser {
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
        visible: root.settingUp && !root.pickingRepo
        contentWidth: width
        contentHeight: setupColumn.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        interactive: contentHeight > height
        // Same scrollbar treatment as the picker: visible while the form is
        // taller than the view, draggable even where the wheel is not.
        ScrollBar.vertical: ScrollBar { policy: setupScroll.contentHeight > setupScroll.height ? ScrollBar.AlwaysOn : ScrollBar.AsNeeded }

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
            text: "Folders to back up"
            textFormat: Text.PlainText
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }

          // The backup folders, one row each with a remove button. Seeded
          // with the home folder (or the existing configuration's list), so
          // the first run has something to back up.
          Repeater {
            model: root.setupSources

            delegate: Item {
              width: parent.width
              height: sourceRowBg.height

              Rectangle {
                id: sourceRowBg
                width: parent.width
                height: Math.max(pathText.implicitHeight + Style.space(6), Style.space(26))
                radius: Style.space(4)
                color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.06)
                border.width: 1
                border.color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.18)

                Text {
                  id: pathText
                  anchors.left: parent.left
                  anchors.leftMargin: Style.space(6)
                  anchors.right: removeButton.left
                  anchors.rightMargin: Style.space(4)
                  anchors.verticalCenter: parent.verticalCenter
                  text: modelData
                  textFormat: Text.PlainText
                  elide: Text.ElideMiddle
                  color: root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.bodySmall
                }

                Text {
                  id: removeButton
                  anchors.right: parent.right
                  anchors.rightMargin: Style.space(6)
                  anchors.verticalCenter: parent.verticalCenter
                  text: "\u00d7"
                  textFormat: Text.PlainText
                  color: root.dimmer
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.body
                }

                TapHandler {
                  onTapped: {
                    var i = index
                    root.setupSources = root.setupSources.filter(function(_, j) { return j !== i })
                  }
                }
              }
            }
          }

          MenuRow {
            width: parent.width
            label: "Add folder\u2026"
            foreground: root.foreground
            fontFamily: root.fontFamily
            onClicked: {
              root.pickerPath = Quickshell.env("HOME") || "/"
              root.pickerTarget = "source"
              root.pickingRepo = true
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

          Item {
            width: parent.width
            height: setupRepo.height

            TextField {
              id: setupRepo
              width: parent.width - repoBrowseButton.width - Style.space(6)
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

            // The folder picker: opens the browse view rooted at the mounted
            // drives for this user, so picking the repository is a click, not
            // a typed path.
            Rectangle {
              id: repoBrowseButton
              anchors.right: parent.right
              width: Style.space(64)
              height: parent.height
              radius: Style.space(4)
              color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.06)
              border.width: 1
              border.color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.18)

              Text {
                anchors.centerIn: parent
                text: "Browse\u2026"
                textFormat: Text.PlainText
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }

              TapHandler {
                onTapped: {
                  root.pickerPath = "/run/media/" + (Quickshell.env("USER") || "")
                  root.pickerTarget = "repo"
                  root.pickingRepo = true
                }
              }
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

          Text {
            width: parent.width
            topPadding: Style.space(6)
            bottomPadding: Style.space(2)
            text: root.setupPassIsCommand
                  ? "Command that prints the password"
                  : "Password (stored in a 600 file)"
            textFormat: Text.PlainText
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }

          TextField {
            id: setupPassword
            width: parent.width
            echoMode: root.setupPassIsCommand ? TextInput.Normal : TextInput.Password
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

          MenuRow {
            width: parent.width
            label: root.setupPassIsCommand
                   ? "Fetched with a command \u2014 click to store in a key file instead"
                   : "Stored in a key file \u2014 click to fetch with a command instead"
            foreground: root.foreground
            fontFamily: root.fontFamily
            onClicked: root.setupPassIsCommand = !root.setupPassIsCommand
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
                root.setupValidationError = root.setupPassIsCommand
                  ? "A password command is required \u2014 for example: pass show <entry> or op read <secret>"
                  : "A password is required \u2014 it is stored in a 600 file, never in the configuration"
                return
              }
              if (root.setupSources.length === 0) {
                root.setupValidationError = "At least one folder to back up is required"
                return
              }
              root.setupValidationError = ""
              TimeMachineStore.applySetup({
                name: name,
                display_name: name,
                repository: repo,
                schedule: setupSchedule,
                password: root.setupPassIsCommand ? undefined : setupPassword.text,
                password_command: root.setupPassIsCommand ? setupPassword.text.trim() : undefined,
                source: root.setupSources.slice()
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

      // --- repository folder picker -----------------------------------------

      // A fourth view: the picker replaces the setup form while it is open.
      // A FolderDialog would be a second window, and this plugin avoids second
      // windows -- keyboard focus on Wayland is lost the moment the first one
      // closes. FolderListModel lists the directory in place: click to
      // descend, Up to go back, Use this folder to hand the path to the field.
      Flickable {
        id: repoPicker
        anchors.fill: parent
        visible: root.pickingRepo
        contentWidth: width
        contentHeight: pickerColumn.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        interactive: contentHeight > height
        // Always visible while the list is taller than the view: the bar is
        // a way to scroll that works even where the wheel does not.
        ScrollBar.vertical: ScrollBar { policy: repoPicker.contentHeight > repoPicker.height ? ScrollBar.AlwaysOn : ScrollBar.AsNeeded }

        FolderListModel {
          id: repoDirs
          // Qt6's FolderListModel has showDirs, not showDirsOnly: files stay
          // in the model and the delegate hides them instead. The folder
          // property needs a file:// scheme: a bare path fails silently and
          // the model keeps listing its default -- the working directory --
          // so the user sees no folders at all. Verified against Qt 6.11:
          // a file:// URL works both at parse time and when the path changes.
          // showHidden so the picker can reach ~/.config and the rest: hidden
          // folders are backed up too, so hiding them here hides real
          // destinations.
          showDirs: true
          showHidden: true
          folder: "file://" + root.pickerPath
        }

        Column {
          id: pickerColumn
          width: repoPicker.width
          spacing: 0

          // The row MouseAreas swallow drags, and wheel events that route
          // through a layer surface do not always reach the Flickable's own
          // handling. This handler scrolls the list directly: it accepts the
          // wheel, so the Flickable never double-scrolls, and the Flickable's
          // StopAtBounds clamping still applies.
          WheelHandler {
            target: repoPicker
            property: "contentY"
            targetTransformAroundCursor: false
          }

          Text {
            width: parent.width
            bottomPadding: Style.space(4)
            text: root.pickerTarget === "source" ? "Add a folder to back up" : "Choose the repository folder"
            textFormat: Text.PlainText
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }

          Text {
            width: parent.width
            bottomPadding: Style.space(8)
            text: root.pickerPath
            textFormat: Text.PlainText
            elide: Text.ElideMiddle
            color: root.dimmer
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
          }

          // Up: the parent directory. The safety net when the default root
          // does not exist or the user went one level too far.
          MenuRow {
            width: parent.width
            label: "Up"
            foreground: root.foreground
            fontFamily: root.fontFamily
            onClicked: {
              var i = root.pickerPath.lastIndexOf("/")
              root.pickerPath = i <= 0 ? "/" : root.pickerPath.substring(0, i)
            }
          }

          Repeater {
            model: repoDirs

            delegate: MenuRow {
              width: parent.width
              visible: fileIsDir
              label: fileName
              foreground: root.foreground
              fontFamily: root.fontFamily
              onClicked: root.pickerPath = filePath
            }
          }

          MenuRow {
            width: parent.width
            label: "Use this folder"
            foreground: root.accent
            fontFamily: root.fontFamily
            onClicked: {
              if (root.pickerTarget === "source") {
                var next = root.setupSources.slice()
                if (next.indexOf(root.pickerPath) === -1) next.push(root.pickerPath)
                root.setupSources = next
              } else {
                setupRepo.text = root.pickerPath
              }
              root.pickingRepo = false
            }
          }
        }
      }
    }

    ConfirmDialog {
      id: stopConfirm
      anchors.fill: parent
      z: 10
      message: "Stop this backup? Nothing is lost, but no snapshot is created for this run."
      confirmText: "Stop"
      cancelText: "Keep running"
      fontFamily: root.fontFamily
      onConfirmed: {
        TimeMachineStore.stopBackup()
        stopConfirm.opened = false
      }
      onCanceled: stopConfirm.opened = false
    }
  }
}
