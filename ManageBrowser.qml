import QtQuick
import QtQuick.Controls
import qs.Commons
import qs.Ui

// Deleting a backup, one date at a time.
//
// The restore picker walks into a snapshot's files; this one stays one level
// up, because the thing being managed is the snapshot itself. The summary
// says what the backup holds, the delete row is destructive and red, and the
// confirm dialog spells out the date: two interactions from an irreversible
// operation is the right distance.
FocusScope {
  id: root

  property color foreground: Color.foreground
  property color dim: Qt.darker(foreground, 1.55)
  property color accent: Color.accent
  property color urgent: Color.urgent
  property string fontFamily: Style.font.family

  // Same confirm routing as the restore browser: ConfirmDialog brings its own
  // mouse handling but no keyboard, so Escape and Enter have to be routed in
  // from outside.
  readonly property bool confirmOpen: deleteConfirm.opened
  function confirmCancel() { deleteConfirm.opened = false }
  function confirmAccept() {
    if (root.snapshotId !== "")
      TimeMachineStore.startDelete(TimeMachineStore.browseDest, root.snapshotId)
    // Cleared before the outcome is known: on success the reload lands on the
    // newest remaining backup, and on failure the error line says why while
    // the dropdown waits for a fresh pick.
    root.snapshotId = ""
    deleteConfirm.opened = false
  }

  signal back()

  // A dedicated focus sink, and this is not ceremony. forceActiveFocus() on a
  // FocusScope hands focus to whichever child held it last, so after you touch
  // the date picker once, "give the keyboard back" would keep handing it
  // straight back to the picker. Focus goes to this item explicitly. Arrow
  // keys have nothing to walk here -- there is no listing -- and the panel's
  // key catcher is blocked while managing, so keys this does not take fall
  // through and do nothing. Escape and Enter are the two that matter.
  Item {
    id: keySink
    focus: true

    Keys.onPressed: function(event) {
      if (event.key === Qt.Key_Escape) {
        if (deleteConfirm.opened) root.confirmCancel()
        else root.back()
        event.accepted = true
      } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
        if (deleteConfirm.opened) root.confirmAccept()
        event.accepted = true
      }
    }
  }

  function takeFocus() { keySink.forceActiveFocus() }

  // Loads its own contents when it comes on screen, rather than trusting
  // whoever opened it to have done so. The click that opens this was the only
  // thing calling loadSnapshots, which meant any other route in showed two
  // empty dropdowns and nothing else.
  function ensureLoaded() {
    if (!visible) return
    if (TimeMachineStore.destinations.length === 0) return
    takeFocus()
    if (!TimeMachineStore.snapshotsLoaded && !TimeMachineStore.snapshotsBusy)
      TimeMachineStore.loadSnapshots()
  }

  onVisibleChanged: ensureLoaded()
  Component.onCompleted: ensureLoaded()

  Connections {
    target: TimeMachineStore
    function onDestinationsChanged() { root.ensureLoaded() }
  }

  property string snapshotId: ""

  function currentSnapshot() {
    for (var i = 0; i < TimeMachineStore.snapshots.length; i++)
      if (TimeMachineStore.snapshots[i].id === root.snapshotId)
        return TimeMachineStore.snapshots[i]
    return null
  }

  implicitHeight: column.implicitHeight

  // Pick the newest backup as soon as the list arrives, so the picker opens
  // on content instead of an empty frame. Also fires after a delete: the id
  // was cleared on confirm, and landing on the newest remaining backup is the
  // only sensible place to start.
  Connections {
    target: TimeMachineStore
    function onSnapshotsChanged() {
      if (root.snapshotId === "" && TimeMachineStore.snapshots.length > 0)
        root.snapshotId = String(TimeMachineStore.snapshots[0].id)
    }
  }

  Column {
    id: column
    // Anchored in width only. anchors.fill would take the height from the
    // parent as well, while the parent takes its implicitHeight from this
    // Column -- the kind of circular sizing where nothing decides the layout.
    anchors.left: parent.left
    anchors.right: parent.right
    anchors.top: parent.top
    spacing: Style.space(10)

    // --- header ------------------------------------------------------------

    Row {
      width: parent.width
      spacing: Style.space(8)

      PanelActionButton {
        anchors.verticalCenter: parent.verticalCenter
        iconText: "\uf060"   // back arrow; \u escape, see RestoreRow
        tooltipText: "Back"
        foreground: root.foreground
        fontFamily: root.fontFamily
        onClicked: root.back()
      }

      // Which destination's history this is. Only when there is a choice:
      // with one destination this would be a control with a single option,
      // which is just a label that costs a click.
      Dropdown {
        width: (parent.width - Style.space(46)) / 2
        anchors.verticalCenter: parent.verticalCenter
        visible: TimeMachineStore.destinations.length > 1
        label: ""
        showLabel: false
        foreground: root.foreground
        fontFamily: root.fontFamily
        value: TimeMachineStore.browseName
        options: {
          var list = []
          for (var i = 0; i < TimeMachineStore.destinations.length; i++) {
            var d = TimeMachineStore.destinations[i]
            list.push({ value: String(d.name),
                        label: TimeMachineStore.destinationLabel(d) })
          }
          return list
        }
        onChanged: function(value) {
          root.snapshotId = ""
          // The snapshot belonged to the destination we were looking at,
          // which is not the one being switched to. Without clearing it the
          // summary would describe a backup this destination does not have.
          TimeMachineStore.browseDestination(value)
          root.takeFocus()
        }
        onPopupOpenChanged: if (!popupOpen) root.takeFocus()
      }

      // Which backup this is about. The dropdown is the picker: pick a date,
      // read the summary, and the delete row underneath is the only thing
      // that reaches the command.
      Dropdown {
        width: TimeMachineStore.destinations.length > 1
               ? (parent.width - Style.space(46)) / 2
               : parent.width - Style.space(38)
        anchors.verticalCenter: parent.verticalCenter
        label: ""
        showLabel: false
        foreground: root.foreground
        fontFamily: root.fontFamily
        value: root.snapshotId
        options: {
          var list = []
          for (var i = 0; i < TimeMachineStore.snapshots.length; i++) {
            var s = TimeMachineStore.snapshots[i]
            list.push({ value: String(s.id), label: TimeMachineStore.shortDate(s.time) })
          }
          return list
        }
        onChanged: function(value) {
          root.snapshotId = value
          root.takeFocus()
        }

        // A Dropdown keeps activeFocus once it has been clicked, and then the
        // arrow keys steer it instead of nothing for the rest of the session.
        // Whenever it closes, for any reason, this view takes the keyboard
        // back.
        onPopupOpenChanged: if (!popupOpen) root.takeFocus()
      }
    }

    Text {
      width: parent.width
      visible: TimeMachineStore.snapshotsBusy || TimeMachineStore.snapshotsError !== ""
      text: TimeMachineStore.snapshotsBusy ? "Loading backups…" : TimeMachineStore.snapshotsError
      textFormat: Text.PlainText
      wrapMode: Text.WordWrap
      color: TimeMachineStore.snapshotsError !== "" ? root.urgent : root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
    }

    // --- summary ------------------------------------------------------------

    // What the backup holds, spelled out before the confirm asks. The date is
    // in the dropdown, but the sources it was taken from are the part worth
    // reading before committing to an irreversible delete.
    Text {
      width: parent.width
      visible: root.currentSnapshot() !== null
      text: {
        var s = root.currentSnapshot()
        if (!s) return ""
        if (s.paths && s.paths.length > 0) return s.paths.join(", ")
        return ""
      }
      textFormat: Text.PlainText
      wrapMode: Text.WrapAnywhere
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
    }

    Text {
      width: parent.width
      visible: {
        var s = root.currentSnapshot()
        return s && s.summary && s.summary.total_files_processed !== undefined
      }
      text: {
        var s = root.currentSnapshot()
        if (!s || !s.summary) return ""
        return Number(s.summary.total_files_processed).toLocaleString(Qt.locale(), "f", 0)
               + " files"
      }
      textFormat: Text.PlainText
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
    }

    // --- delete ---------------------------------------------------------------

    PanelSeparator { width: parent.width }

    MenuRow {
      width: parent.width
      visible: root.snapshotId !== "" && !TimeMachineStore.deleteBusy
      destructive: true
      label: {
        var s = root.currentSnapshot()
        return s ? "Delete this backup (" + TimeMachineStore.shortDate(s.time) + ")" : ""
      }
      foreground: root.foreground
      fontFamily: root.fontFamily
      onClicked: deleteConfirm.opened = true
    }

    // Prune rewrites the repository to reclaim the space, and on a large one
    // that takes minutes. Saying so is the difference between a busy line
    // and a wedged-looking panel.
    Text {
      width: parent.width
      visible: TimeMachineStore.deleteBusy
      topPadding: visible ? Style.space(6) : 0
      bottomPadding: visible ? Style.space(6) : 0
      text: "Deleting and pruning\u2026 this can take a few minutes"
      textFormat: Text.PlainText
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.body
    }

    Text {
      width: parent.width
      visible: TimeMachineStore.deleteError !== ""
      text: TimeMachineStore.deleteError
      textFormat: Text.PlainText
      wrapMode: Text.WrapAnywhere
      color: root.urgent
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
    }
  }

  ConfirmDialog {
    id: deleteConfirm
    anchors.fill: parent
    z: 10
    // The date and the destination are spelled out, because the one thing
    // worth confirming here is what is about to be gone for good. plain():
    // the destination name comes out of config.json, and ConfirmDialog is a
    // shell component that sets no textFormat -- its Text falls back to Qt's
    // AutoText, which renders anything tag-shaped as rich text and would
    // fetch what it points at. Same reason the bar tooltip goes through
    // plain().
    message: {
      var s = root.currentSnapshot()
      if (!s) return ""
      return "Delete the backup from " + TimeMachineStore.shortDate(s.time)
             + " from " + TimeMachineStore.plain(TimeMachineStore.destinationLabel(TimeMachineStore.browseDest))
             + "? This cannot be undone."
    }
    confirmText: "Delete"
    fontFamily: root.fontFamily
    onConfirmed: root.confirmAccept()
    onCanceled: root.confirmCancel()
  }
}
