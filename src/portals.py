import uuid
import os
import shutil
from typing import Callable, Optional
from gi.repository import Gio, GLib

class DesktopPortalClient:
    def __init__(
        self,
        on_toggle_shortcut: Callable[[], None],
        on_shortcut_changed: Optional[Callable[[str], None]] = None
    ):
        self._on_toggle_shortcut = on_toggle_shortcut
        self._on_shortcut_changed = on_shortcut_changed
        self._dbus_conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self._session_handle: Optional[str] = None
        self._session_req_token = ""
        self._bind_req_token = ""
        self._sub_ids: list[int] = []

    def setup_global_shortcuts(self, on_failure: Callable[[], None]):
        GLib.set_prgname("io.github.Epoch5427.repeat")
        self.close_session()

        self._session_req_token = f"repeat_req_{uuid.uuid4().hex[:8]}"
        session_token = f"repeat_session_{uuid.uuid4().hex[:8]}"

        sub_id = self._dbus_conn.signal_subscribe(
            "org.freedesktop.portal.Desktop", "org.freedesktop.portal.Request", "Response",
            None, None, Gio.DBusSignalFlags.NO_MATCH_RULE,
            lambda c, s, p, i, sig, params, u: self._on_session_created(p, params, on_failure), None
        )
        self._sub_ids.append(sub_id)

        self._dbus_conn.call(
            "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.GlobalShortcuts", "CreateSession",
            GLib.Variant("(a{sv})", ({"session_handle_token": GLib.Variant("s", session_token),
                                      "handle_token": GLib.Variant("s", self._session_req_token)},)),
            GLib.VariantType.new("(o)"), Gio.DBusCallFlags.NONE, -1, None, None, None
        )

    def _on_session_created(self, path, params, on_failure):
        if not path.endswith(self._session_req_token):
            return
        response, results = params.unpack()
        if response != 0 or "session_handle" not in results:
            on_failure()
            return

        self._session_handle = results["session_handle"]

        # Listen for shortcut activation
        sub_act = self._dbus_conn.signal_subscribe(
            None, "org.freedesktop.portal.GlobalShortcuts", "Activated",
            None, None, Gio.DBusSignalFlags.NONE,
            self._on_shortcut_activated, None
        )
        self._sub_ids.append(sub_act)

        # Listen for runtime shortcut changes (e.g., changed in system settings)
        sub_chg = self._dbus_conn.signal_subscribe(
            None, "org.freedesktop.portal.GlobalShortcuts", "ShortcutsChanged",
            None, None, Gio.DBusSignalFlags.NONE,
            self._on_shortcuts_changed_signal, None
        )
        self._sub_ids.append(sub_chg)

        self._bind_req_token = f"repeat_bind_{uuid.uuid4().hex[:8]}"

        sub_bind = self._dbus_conn.signal_subscribe(
            "org.freedesktop.portal.Desktop", "org.freedesktop.portal.Request", "Response",
            None, None, Gio.DBusSignalFlags.NO_MATCH_RULE,
            self._on_bind_response, None
        )
        self._sub_ids.append(sub_bind)

        shortcut_opts = {
            "description": GLib.Variant("s", "Toggle Execution"),
            "preferred_trigger": GLib.Variant("s", "F8")
        }
        shortcuts = [("toggle_clicking", shortcut_opts)]

        self._dbus_conn.call(
            "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.GlobalShortcuts", "BindShortcuts",
            GLib.Variant("(oa(sa{sv})sa{sv})", (
                self._session_handle,
                shortcuts,
                "",
                {"handle_token": GLib.Variant("s", self._bind_req_token)}
            )),
            GLib.VariantType.new("(o)"), Gio.DBusCallFlags.NONE, -1, None, None, None
        )

    def _on_bind_response(self, conn, sender, path, iface, signal, params, udata):
        if not path.endswith(self._bind_req_token):
            return
        response, results = params.unpack()
        if response == 0 and "shortcuts" in results:
            self._parse_and_emit_trigger(results["shortcuts"])
        else:
            # User canceled, declined the portal dialog, or binding failed
            if self._on_shortcut_changed:
                self._on_shortcut_changed("")

    def _on_shortcuts_changed_signal(self, conn, sender, path, iface, signal, params, udata):
        unpacked = params.unpack()
        if len(unpacked) >= 2 and unpacked[0] == self._session_handle:
            self._parse_and_emit_trigger(unpacked[1])

    def _parse_and_emit_trigger(self, shortcuts_data):
        """Extracts the trigger_description for our toggle shortcut."""
        shortcuts = shortcuts_data.unpack() if hasattr(shortcuts_data, "unpack") else shortcuts_data
        found_trigger = ""

        for item in shortcuts:
            item = item.unpack() if hasattr(item, "unpack") else item
            if len(item) >= 2 and item[0] == "toggle_clicking":
                opts = item[1].unpack() if hasattr(item[1], "unpack") else item[1]
                # Only use what the portal explicitly assigned. Do NOT fall back to "F8"!
                trigger = opts.get("trigger_description")
                if trigger:
                    if hasattr(trigger, "unpack"):
                        trigger = trigger.unpack()
                    found_trigger = str(trigger).strip()
                break

        # If empty or not set, emits "" so the UI resets to "Unassigned"
        if self._on_shortcut_changed:
            self._on_shortcut_changed(found_trigger)

    def _on_shortcut_activated(self, conn, sender, path, iface, signal, params, udata):
        unpacked = params.unpack()
        if len(unpacked) >= 2 and unpacked[0] == self._session_handle and unpacked[1] == "toggle_clicking":
            self._on_toggle_shortcut()

    def request_screenshot(self, interactive: bool, on_result: Callable[[int, Optional[str]], None]):
        req_token = f"screenshot_{uuid.uuid4().hex[:8]}"

        def on_response(conn, sender, path, iface, signal, params, udata):
            if not path.endswith(req_token):
                return
            response, results = params.unpack()
            screenshot_path = None

            if response == 0 and "uri" in results:
                file_obj = Gio.File.new_for_uri(results["uri"])
                orig = file_obj.get_path()
                tmp_dest = os.path.join("/tmp", f"repeat_shot_{uuid.uuid4().hex[:8]}.png")

                try:
                    shutil.copyfile(orig, tmp_dest)
                    screenshot_path = tmp_dest
                    # Delete the original file that the portal created in Pictures/
                    self._cleanup_original_screenshot(file_obj, orig)
                except Exception as e:
                    print(f"[Screenshot] Failed to copy to /tmp: {e}", flush=True)
                    screenshot_path = orig

            on_result(response, screenshot_path)

        self._dbus_conn.signal_subscribe(
            "org.freedesktop.portal.Desktop", "org.freedesktop.portal.Request", "Response",
            None, None, Gio.DBusSignalFlags.NO_MATCH_RULE,
            on_response, None
        )

        self._dbus_conn.call(
            "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Screenshot", "Screenshot",
            GLib.Variant("(sa{sv})", ("", {"handle_token": GLib.Variant("s", req_token),
                                          "interactive": GLib.Variant("b", interactive)})),
            GLib.VariantType.new("(o)"), Gio.DBusCallFlags.NONE, -1, None, None, None
        )

    def _cleanup_original_screenshot(self, file_obj: Gio.File, orig_path: Optional[str]):
        """Removes the screenshot file created by the desktop portal in the user's Pictures directory."""
        # 1. Try deleting via GIO File directly
        try:
            file_obj.delete(None)
        except Exception:
            pass

        # 2. Try direct filesystem deletion
        try:
            if orig_path and os.path.exists(orig_path):
                os.remove(orig_path)
        except Exception:
            pass

        # 3. Check XDG Pictures & Screenshots directories (essential for Flatpak sandboxes)
        if orig_path:
            filename = os.path.basename(orig_path)
            pictures_dir = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)
            if not pictures_dir:
                pictures_dir = os.path.expanduser("~/Pictures")

            candidates = [
                os.path.join(pictures_dir, "Screenshots", filename),
                os.path.join(pictures_dir, filename),
                os.path.expanduser(f"~/Pictures/Screenshots/{filename}"),
                os.path.expanduser(f"~/Pictures/{filename}")
            ]

            for path in candidates:
                if os.path.exists(path):
                    try:
                        os.remove(path)
                        break
                    except Exception as e:
                        print(f"[Screenshot] Failed to delete host file: {e}", flush=True)

    def close_session(self):
        for sub_id in self._sub_ids:
            try:
                self._dbus_conn.signal_unsubscribe(sub_id)
            except Exception:
                pass
        self._sub_ids.clear()

        if self._dbus_conn and self._session_handle:
            try:
                self._dbus_conn.call_sync(
                    "org.freedesktop.portal.Desktop", self._session_handle,
                    "org.freedesktop.portal.Session", "Close",
                    None, None, Gio.DBusCallFlags.NONE, 200, None
                )
            except Exception:
                pass
            self._session_handle = None
