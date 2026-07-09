import uuid
import threading
import random
import time
import json
import os
import sys
import subprocess
import gi
gi.require_version('Adw', '1')
from gi.repository import Adw
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import Gio
from gi.repository import GLib

import evdev
from evdev import UInput, ecodes

# Embedded background Python script to manage the tray natively without crashing GTK4
TRAY_SCRIPT = """
import sys
import gi

# Require GTK3 exclusively for this isolated background process
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

# Fallback gracefully between Ayatana and the older AppIndicator
try:
    gi.require_version('AyatanaAppIndicator3', '0.1')
    from gi.repository import AyatanaAppIndicator3 as AppIndicator
except ValueError:
    gi.require_version('AppIndicator3', '0.1')
    from gi.repository import AppIndicator3 as AppIndicator

def on_show(item):
    print("show")
    sys.stdout.flush()

def on_toggle(item):
    print("toggle")
    sys.stdout.flush()

def on_quit(item):
    print("quit")
    sys.stdout.flush()
    Gtk.main_quit()

# Initialize the indicator.
# We pass your app's exported ID. The host DE will automatically find your icon!
indicator = AppIndicator.Indicator.new(
    "repeat_tray",
    "io.github.Epoch5427.repeat",
    AppIndicator.IndicatorCategory.APPLICATION_STATUS
)
indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)

# Build the GTK3 Menu
menu = Gtk.Menu()

item_show = Gtk.MenuItem(label="Show Autoclicker")
item_show.connect('activate', on_show)
menu.append(item_show)

item_toggle = Gtk.MenuItem(label="Toggle Start/Stop")
item_toggle.connect('activate', on_toggle)
menu.append(item_toggle)

item_quit = Gtk.MenuItem(label="Quit")
item_quit.connect('activate', on_quit)
menu.append(item_quit)

menu.show_all()
indicator.set_menu(menu)

# Start the GTK loop for this subprocess
Gtk.main()
"""

class KeyPickerDialog(Gtk.Window):
    def __init__(self, parent, on_key_picked_cb):
        super().__init__(
            transient_for=parent,
            modal=True,
            title="Set Shortcut",
            default_width=450,
            default_height=350,
            resizable=False,
            hide_on_close=True
        )
        self.on_key_picked_cb = on_key_picked_cb

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        box.set_margin_top(32)
        box.set_margin_bottom(32)
        box.set_margin_start(32)
        box.set_margin_end(32)

        lbl = Gtk.Label()
        lbl.set_markup("Enter new shortcut to change <b>Target Key</b>")
        lbl.set_justify(Gtk.Justification.CENTER)
        lbl.set_wrap(True)
        box.append(lbl)

        img = Gtk.Image(icon_name="preferences-desktop-keyboard-shortcuts-symbolic")
        img.set_pixel_size(128)
        img.set_vexpand(True)
        box.append(img)

        lbl2 = Gtk.Label(label="Press Esc to cancel")
        lbl2.add_css_class("dim-label")
        lbl2.set_justify(Gtk.Justification.CENTER)
        lbl2.set_wrap(True)
        box.append(lbl2)

        self.set_child(box)

        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_ctrl)

    def _on_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            self.destroy()
            return True

        # Ignore modifiers alone
        if keyval in [Gdk.KEY_Control_L, Gdk.KEY_Control_R, Gdk.KEY_Shift_L, Gdk.KEY_Shift_R,
                      Gdk.KEY_Alt_L, Gdk.KEY_Alt_R, Gdk.KEY_Super_L, Gdk.KEY_Super_R,
                      Gdk.KEY_Meta_L, Gdk.KEY_Meta_R]:
            return False

        accel_name = Gtk.accelerator_name_with_keycode(None, keyval, keycode, state)
        if accel_name:
            self.on_key_picked_cb(accel_name)
            self.destroy()
            return True

        return False


class MacroRecorderDialog(Gtk.Window):
    def __init__(self, parent, on_macro_recorded_cb, existing_macro=""):
        super().__init__(
            transient_for=parent,
            modal=True,
            title="Record Macro",
            default_width=500,
            default_height=380,
            resizable=True,
            hide_on_close=True
        )
        self.on_macro_recorded_cb = on_macro_recorded_cb
        self.last_event_time = None
        self.is_recording = False

        # Parse existing sequence if present
        self.recorded_actions = []
        if existing_macro:
            self.recorded_actions = [x.strip() for x in existing_macro.split(",") if x.strip()]

        # Make the input window's parent rounded + add margins
        css = b"""
        .rounded-scrolled-window {
            border-radius: 12px;
            border: 1px solid rgba(128, 128, 128, 0.25);
        }
        .rounded-scrolled-window textview {
            border-radius: 12px;
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # Make header bar flat
        header_bar = Adw.HeaderBar()
        header_bar.add_css_class("flat")
        header_bar.set_show_end_title_buttons(False)
        header_bar.set_show_start_title_buttons(False)
        self.set_titlebar(header_bar)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda *args: self.destroy())
        header_bar.pack_start(cancel_btn)

        self.save_btn = Gtk.Button(label="Save")
        self.save_btn.add_css_class("suggested-action")
        self.save_btn.connect("clicked", self._on_save)
        self.save_btn.set_sensitive(False)
        header_bar.pack_end(self.save_btn)

        # Popup layout
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        main_box.set_margin_top(12)
        main_box.set_margin_bottom(16)
        main_box.set_margin_start(0)
        main_box.set_margin_end(0)

        info_label = Gtk.Label(
            label="Press keys while this window is active. They will be recorded sequentially with realistic timing delays."
        )
        info_label.set_wrap(True)
        info_label.add_css_class("dim-label")
        info_label.set_justify(Gtk.Justification.CENTER)
        info_label.set_margin_start(24)
        info_label.set_margin_end(24)
        main_box.append(info_label)

        # Display area for recorded sequence
        self.sequence_text_view = Gtk.TextView()
        self.sequence_text_view.set_editable(False)
        self.sequence_text_view.set_cursor_visible(False)
        self.sequence_text_view.set_wrap_mode(Gtk.WrapMode.WORD)

        # Padding inside the text box
        self.sequence_text_view.set_left_margin(14)
        self.sequence_text_view.set_right_margin(14)
        self.sequence_text_view.set_top_margin(14)
        self.sequence_text_view.set_bottom_margin(14)

        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_child(self.sequence_text_view)
        scrolled_window.set_vexpand(True)
        scrolled_window.set_has_frame(False)
        scrolled_window.add_css_class("rounded-scrolled-window")

        scrolled_window.set_margin_start(24)
        scrolled_window.set_margin_end(24)
        scrolled_window.set_margin_top(4)
        scrolled_window.set_margin_bottom(4)

        main_box.append(scrolled_window)

        # Primary button
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        btn_box.set_halign(Gtk.Align.CENTER)
        btn_box.set_margin_bottom(12)

        self.action_btn = Gtk.Button(label="Start Recording")
        self.action_btn.connect("clicked", self._on_action_btn_clicked)
        btn_box.append(self.action_btn)

        main_box.append(btn_box)
        self.set_child(main_box)

        # Sync existing sequence
        self._update_text_display()
        self._update_button_state()
        if self.recorded_actions:
            self.save_btn.set_sensitive(True)

        # Key controller
        self.key_controller = Gtk.EventControllerKey()
        self.key_controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(self.key_controller)

    def _update_button_state(self):
        self.action_btn.remove_css_class("suggested-action")
        self.action_btn.remove_css_class("destructive-action")

        if self.is_recording:
            self.action_btn.set_label("Stop Recording")
            self.action_btn.add_css_class("destructive-action")
        else:
            if self.recorded_actions:
                self.action_btn.set_label("Clear")
            else:
                self.action_btn.set_label("Start Recording")
                self.action_btn.add_css_class("suggested-action")

    def _on_action_btn_clicked(self, btn):
        if self.is_recording:
            # Transition to stopped
            self.is_recording = False
            self.last_event_time = None
            self._update_text_display()
            self._update_button_state()
            self.save_btn.set_sensitive(len(self.recorded_actions) > 0)
        else:
            if self.recorded_actions:
                # Transition from Stopped to Clear to Idle
                self.recorded_actions.clear()
                self.last_event_time = None
                self._update_text_display()
                self._update_button_state()
                self.save_btn.set_sensitive(False)
            else:
                # Transition to Recording
                self.is_recording = True
                self.last_event_time = None  # Reset delay computation for the very first key as this was extremely annoying
                self._show_recording_status()
                self._update_button_state()
                self.save_btn.set_sensitive(False)

    def _on_key_pressed(self, controller, keyval, keycode, state):
        if not self.is_recording:
            if keyval == Gdk.KEY_Escape:
                self.destroy()
                return True
            return False

        if keyval in [Gdk.KEY_Control_L, Gdk.KEY_Control_R, Gdk.KEY_Shift_L, Gdk.KEY_Shift_R,
                      Gdk.KEY_Alt_L, Gdk.KEY_Alt_R, Gdk.KEY_Super_L, Gdk.KEY_Super_R,
                      Gdk.KEY_Meta_L, Gdk.KEY_Meta_R]:
            return False

        now = time.perf_counter()
        if self.last_event_time is not None:
            elapsed_ms = int((now - self.last_event_time) * 1000)
            if elapsed_ms > 40:
                self.recorded_actions.append(f"delay:{elapsed_ms}")
        self.last_event_time = now

        combo_parts = []
        if state & Gdk.ModifierType.CONTROL_MASK:
            combo_parts.append("ctrl")
        if state & Gdk.ModifierType.SHIFT_MASK:
            combo_parts.append("shift")
        if state & Gdk.ModifierType.ALT_MASK:
            combo_parts.append("alt")
        if state & Gdk.ModifierType.SUPER_MASK:
            combo_parts.append("super")

        key_name = Gdk.keyval_name(keyval)
        if key_name:
            key_name_clean = key_name.lower()
            if key_name_clean == "return":
                key_name_clean = "enter"
            if key_name_clean not in combo_parts:
                combo_parts.append(key_name_clean)

        action_str = "+".join(combo_parts)
        if action_str:
            self.recorded_actions.append(action_str)
            self._show_recording_status()
            self.save_btn.set_sensitive(True)

        return True

    def _show_recording_status(self):
        buffer = self.sequence_text_view.get_buffer()
        text = ", ".join(self.recorded_actions)
        if text:
            buffer.set_text(text + " (Recording...)")
        else:
            buffer.set_text("(Recording... Press keys to begin)")

    def _update_text_display(self):
        buffer = self.sequence_text_view.get_buffer()
        buffer.set_text(", ".join(self.recorded_actions))

    def _on_save(self, btn):
        macro_str = ", ".join(self.recorded_actions)
        if macro_str:
            self.on_macro_recorded_cb(macro_str)
        self.destroy()


@Gtk.Template(resource_path='/io/github/Epoch5427/repeat/window.ui')
class RepeatWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'RepeatWindow'

    # Binding
    primary_menu_popover = Gtk.Template.Child()
    toast_overlay = Gtk.Template.Child()
    toggle_run_btn = Gtk.Template.Child()
    permission_banner = Gtk.Template.Child()
    shortcut_collision_banner = Gtk.Template.Child()

    # Layout Elements
    carousel = Gtk.Template.Child()

    # Mode 1: Mouse
    btn_left_click = Gtk.Template.Child()
    btn_middle_click = Gtk.Template.Child()
    btn_right_click = Gtk.Template.Child()
    click_type_row = Gtk.Template.Child()
    custom_location_row = Gtk.Template.Child()
    mouse_pos_x = Gtk.Template.Child()
    mouse_pos_y = Gtk.Template.Child()
    pick_position_row = Gtk.Template.Child()

    # Mode 2: Keyboard
    kb_key_row = Gtk.Template.Child()
    kb_key_button = Gtk.Template.Child()
    kb_shortcut_label = Gtk.Template.Child()
    kb_action_type_row = Gtk.Template.Child()

    # Mode 3: Macro
    macro_sequence_row = Gtk.Template.Child()
    record_macro_btn = Gtk.Template.Child()

    # Right Column: Settings & Advanced
    timing_mode = Gtk.Template.Child()
    interval_ms = Gtk.Template.Child()
    rate_count = Gtk.Template.Child()
    rate_unit = Gtk.Template.Child()
    start_delay_row = Gtk.Template.Child()
    repeat_limit = Gtk.Template.Child()
    repeat_count_row = Gtk.Template.Child()
    has_time_limit = Gtk.Template.Child()
    time_limit_row = Gtk.Template.Child()

    randomize_interval = Gtk.Template.Child()
    random_spread_ms = Gtk.Template.Child()
    duty_cycle = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        css = b"""
        .flat-dropdown button label,
        .flat-dropdown label {
          font-weight: normal;
          background-color: transparent;
        }
        .popover .menuitem,
        .popover .cellview,
        .dropdown .menuitem {
          font-weight: normal;
        }
        """

        provider = Gtk.CssProvider()
        provider.load_from_data(css)

        display = Gdk.Display.get_default()
        Gtk.StyleContext.add_provider_for_display(
            display,
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self._delay_timeout_id = None
        self._countdown_seconds = 0
        self._executions_made = 0
        self._start_time = None
        self._ui = None

        # Thread management elements
        self._worker_thread = None
        self._stop_event = None
        self._worker_config = {}

        self._dbus_conn = None
        self._session_handle = None
        self._session_sub_id = None
        self._bind_sub_id = None

        # Retry connection variables for the global shortcut portal as I can't for the life of me get it to connect on the first try'
        self._portal_attempts = 0
        self._portal_retry_timer_id = None

        # Click cooldown logic variables so user can stop the autoclicker by hovering his mouse over it even while it is running
        self._block_toggle_signal = False
        self._toggle_cooldown_active = False

        self.timing_mode.connect("notify::selected", self._on_timing_mode_changed)
        self._on_timing_mode_changed()

        self._target_key_name = "a"
        self.kb_shortcut_label.set_accelerator(self._target_key_name)
        self.kb_key_button.connect("clicked", self._show_key_picker_dialog)

        # Connect Coordinate Picker Click
        self.pick_position_row.connect("activated", self._on_pick_position_activated)

        # Asynchronously connect to evdev
        threading.Thread(target=self._async_init_uinput, daemon=True).start()

        # Local Hotkey
        self._key_controller = Gtk.EventControllerKey()
        self._key_controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(self._key_controller)

        # Global Hotkey Request
        GLib.idle_add(self._trigger_portal_setup, True)

        # Signals
        self.connect("close-request", self._on_close_request)
        self.permission_banner.connect("button-clicked", self._on_banner_button_clicked)
        self.shortcut_collision_banner.connect("button-clicked", self._on_shortcut_collision_retry)
        self.record_macro_btn.connect("activated", self._on_record_macro_activated)
        self.toggle_run_btn.connect("toggled", self._on_toggle_run_toggled)

        # Load Saved Settings
        self._load_settings()

        self._init_tray_icon()

    def _init_tray_icon(self):
        try:
            icon_path = "/app/share/icons/hicolor/256x256/apps/io.github.Epoch5427.repeat.png"

            # Launch the isolated Python process
            # ROUTE stderr to sys.stderr so any traceback prints in your terminal!
            self._tray_process = subprocess.Popen(
                [sys.executable, "-c", TRAY_SCRIPT],
                stdout=subprocess.PIPE,
                stdin=subprocess.PIPE,
                stderr=sys.stderr,
                text=True
            )

            # Spawn a non-blocking UI thread to listen for tray clicks
            threading.Thread(target=self._read_tray_stdout, daemon=True).start()
        except Exception as e:
            print(f"Failed to start system tray: {e}")

    def _read_tray_stdout(self):
        while True:
            if not hasattr(self, '_tray_process') or self._tray_process.poll() is not None:
                break
            try:
                line = self._tray_process.stdout.readline()
                if not line:
                    break
                command = line.strip()
                # Schedule command to run on GTK's main loop safely
                GLib.idle_add(self._handle_tray_command, command)
            except Exception:
                break

    def _handle_tray_command(self, command):
        if command == "show":
            self.set_visible(True)
            self.present()
        elif command == "toggle":
            is_active = self.toggle_run_btn.get_active()
            self.toggle_run_btn.set_active(not is_active)
        elif command == "quit":
            self._real_quit()
        return False

    def _async_init_uinput(self):
        try:
            capabilities = {
                ecodes.EV_KEY: [
                    ecodes.BTN_LEFT, ecodes.BTN_RIGHT, ecodes.BTN_MIDDLE
                ] + list(range(1, 128)),
                ecodes.EV_REL: [ecodes.REL_X, ecodes.REL_Y]
            }
            self._ui = UInput(capabilities, name="Repeat-Virtual-Input")
            GLib.idle_add(self._on_uinput_ready, True)
        except Exception:
            GLib.idle_add(self._on_uinput_ready, False)

    def _on_uinput_ready(self, success):
        if success:
            self.permission_banner.set_revealed(False)
            self.toggle_run_btn.set_label("Start")
            self.toggle_run_btn.set_sensitive(True)
        else:
            self._ui = None
            self.permission_banner.set_revealed(True)
            self.toggle_run_btn.set_label("Start")
            self.toggle_run_btn.set_sensitive(False)

    def _show_key_picker_dialog(self, btn):
        def on_key_picked(accel_name):
            self._target_key_name = accel_name
            self.kb_shortcut_label.set_accelerator(accel_name)

        dialog = KeyPickerDialog(self, on_key_picked)
        dialog.present()

    def _on_key_pressed(self, controller, keyval, keycode, state):
        return False

    def _on_timing_mode_changed(self, *args):
        is_delay = (self.timing_mode.get_selected() == 0)
        self.interval_ms.set_visible(is_delay)
        self.rate_count.set_visible(not is_delay)
        self.rate_unit.set_visible(not is_delay)

    # State Saving and Loading

    def _save_settings(self):
        config_dir = GLib.get_user_config_dir()
        app_dir = os.path.join(config_dir, "io.github.Epoch5427.repeat")
        os.makedirs(app_dir, exist_ok=True)
        settings_path = os.path.join(app_dir, "settings.json")

        settings = {
            'active_mode': int(round(self.carousel.get_position())),
            'left_click': self.btn_left_click.get_active(),
            'middle_click': self.btn_middle_click.get_active(),
            'right_click': self.btn_right_click.get_active(),
            'click_type_idx': self.click_type_row.get_selected(),
            'custom_location_enabled': self.custom_location_row.get_enable_expansion(),
            'mouse_pos_x': int(self.mouse_pos_x.get_value()),
            'mouse_pos_y': int(self.mouse_pos_y.get_value()),

            'target_key_name': self._target_key_name,
            'kb_action_type': self.kb_action_type_row.get_selected(),

            'macro_text': self.macro_sequence_row.get_text(),

            'timing_mode': self.timing_mode.get_selected(),
            'interval_ms': int(self.interval_ms.get_value()),
            'rate_count': int(self.rate_count.get_value()),
            'rate_unit': self.rate_unit.get_selected(),
            'start_delay': int(self.start_delay_row.get_value()),
            'repeat_limit_enabled': self.repeat_limit.get_enable_expansion(),
            'repeat_count': int(self.repeat_count_row.get_value()),
            'time_limit_enabled': self.has_time_limit.get_enable_expansion(),
            'time_limit': int(self.time_limit_row.get_value()),

            'randomize_interval': self.randomize_interval.get_enable_expansion(),
            'spread_ms': int(self.random_spread_ms.get_value()),
            'duty_cycle': int(self.duty_cycle.get_value())
        }

        try:
            with open(settings_path, 'w') as f:
                json.dump(settings, f)
        except Exception as e:
            print(f"Failed to save settings: {e}", flush=True)

    def _load_settings(self):
        config_dir = GLib.get_user_config_dir()
        settings_path = os.path.join(config_dir, "io.github.Epoch5427.repeat", "settings.json")

        if not os.path.exists(settings_path):
            return

        try:
            with open(settings_path, 'r') as f:
                settings = json.load(f)

            if 'active_mode' in settings:
                idx = settings['active_mode']
                try:
                    child = self.carousel.get_nth_page(idx)
                    if child:
                        self.carousel.scroll_to(child, False)
                except AttributeError:
                    pass

            if settings.get('left_click'):
                self.btn_left_click.set_active(True)
            elif settings.get('middle_click'):
                self.btn_middle_click.set_active(True)
            elif settings.get('right_click'):
                self.btn_right_click.set_active(True)

            if 'click_type_idx' in settings:
                self.click_type_row.set_selected(settings['click_type_idx'])
            if 'custom_location_enabled' in settings:
                self.custom_location_row.set_enable_expansion(settings['custom_location_enabled'])
            if 'mouse_pos_x' in settings:
                self.mouse_pos_x.set_value(settings['mouse_pos_x'])
            if 'mouse_pos_y' in settings:
                self.mouse_pos_y.set_value(settings['mouse_pos_y'])

            if 'target_key_name' in settings:
                self._target_key_name = settings['target_key_name']
                self.kb_shortcut_label.set_accelerator(self._target_key_name)
            if 'kb_action_type' in settings:
                self.kb_action_type_row.set_selected(settings['kb_action_type'])

            if 'macro_text' in settings:
                self.macro_sequence_row.set_text(settings['macro_text'])

            if 'timing_mode' in settings:
                self.timing_mode.set_selected(settings['timing_mode'])
                self._on_timing_mode_changed()

            if 'interval_ms' in settings:
                self.interval_ms.set_value(settings['interval_ms'])
            if 'rate_count' in settings:
                self.rate_count.set_value(settings['rate_count'])
            if 'rate_unit' in settings:
                self.rate_unit.set_selected(settings['rate_unit'])
            if 'start_delay' in settings:
                self.start_delay_row.set_value(settings['start_delay'])

            if 'repeat_limit_enabled' in settings:
                self.repeat_limit.set_enable_expansion(settings['repeat_limit_enabled'])
            if 'repeat_count' in settings:
                self.repeat_count_row.set_value(settings['repeat_count'])

            if 'time_limit_enabled' in settings:
                self.has_time_limit.set_enable_expansion(settings['time_limit_enabled'])
            if 'time_limit' in settings:
                self.time_limit_row.set_value(settings['time_limit'])

            if 'randomize_interval' in settings:
                self.randomize_interval.set_enable_expansion(settings['randomize_interval'])
            if 'spread_ms' in settings:
                self.random_spread_ms.set_value(settings['spread_ms'])
            if 'duty_cycle' in settings:
                self.duty_cycle.set_value(settings['duty_cycle'])

        except Exception as e:
            print(f"Failed to load settings: {e}", flush=True)

    # Coordinate Picker (Screenshot Overlay) in order to appease wayland + flatpak

    def _on_pick_position_activated(self, row):
        self.set_visible(False)
        GLib.timeout_add(400, self._request_portal_screenshot)

    def _request_portal_screenshot(self):
        self._screenshot_req_token = f"screenshot_req_{uuid.uuid4().hex[:8]}"

        self._screenshot_sub_id = self._dbus_conn.signal_subscribe(
            "org.freedesktop.portal.Desktop",
            "org.freedesktop.portal.Request",
            "Response",
            None,
            None,
            Gio.DBusSignalFlags.NO_MATCH_RULE,
            self._on_screenshot_response,
            None
        )

        options = {
            "handle_token": GLib.Variant("s", self._screenshot_req_token),
            "interactive": GLib.Variant("b", False),  # Skip user interaction
            "target": GLib.Variant("u", 1)           # Make screenshot fullscreen
        }

        self._dbus_conn.call(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Screenshot",
            "Screenshot",
            GLib.Variant("(sa{sv})", ("", options)),
            GLib.VariantType.new("(o)"),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            self._async_call_cb,
            None
        )
        return GLib.SOURCE_REMOVE

    def _on_screenshot_response(self, connection, sender, path, interface, signal, parameters, user_data):
        if not path.endswith(self._screenshot_req_token):
            return

        if hasattr(self, '_screenshot_sub_id') and self._screenshot_sub_id:
            self._dbus_conn.signal_unsubscribe(self._screenshot_sub_id)
            self._screenshot_sub_id = None

        response, results = parameters.unpack()
        screenshot_path = None
        if response == 0:
            uri = results.get("uri")
            if uri:
                file_obj = Gio.File.new_for_uri(uri)
                original_path = file_obj.get_path()

                import shutil
                import os
                import uuid

                original_filename = os.path.basename(original_path)
                tmp_filename = f"repeat_screenshot_{uuid.uuid4().hex[:8]}.png"
                screenshot_path = os.path.join("/tmp", tmp_filename)

                try:
                    shutil.copyfile(original_path, screenshot_path)
                except Exception as e:
                    print(f"[Screenshot] Failed to copy to /tmp: {e}", flush=True)
                    screenshot_path = original_path

                pictures_dir = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)
                if not pictures_dir:
                    pictures_dir = os.path.expanduser("~/Pictures")

                possible_paths = [
                    os.path.join(pictures_dir, "Screenshots", original_filename),
                    os.path.join(pictures_dir, original_filename)
                ]

                for path in possible_paths:
                    if os.path.exists(path):
                        try:
                            os.remove(path)
                            break
                        except Exception as delete_error:
                            print(f"[Screenshot] Failed to delete host file: {delete_error}", flush=True)

        self.set_visible(True)

        if response == 0 and screenshot_path:
            self._show_picker_window(screenshot_path, should_restore=True)
        else:
            print(f"[Screenshot] User cancelled or portal denied (Code {response})", flush=True)
            self._show_picker_window(None, should_restore=False)

    def _show_picker_window(self, screenshot_path, should_restore):
        import os

        picker_win = Gtk.Window(
            transient_for=self,
            modal=True,
            destroy_with_parent=True
        )
        picker_win.set_decorated(False)
        picker_win.fullscreen()

        overlay = Gtk.Overlay()
        picker_win.set_child(overlay)

        if screenshot_path and os.path.exists(screenshot_path):
            picture = Gtk.Picture.new_for_filename(screenshot_path)
            picture.set_can_shrink(True)
            picture.set_keep_aspect_ratio(False)
            overlay.set_child(picture)

            def on_destroy(window):
                try:
                    if os.path.exists(screenshot_path):
                        os.remove(screenshot_path)
                except Exception:
                    pass
                if should_restore:
                    self.present()
            picker_win.connect("destroy", on_destroy)
        else:
            picker_win.set_opacity(0.4)
            bg_box = Gtk.Box()
            overlay.set_child(bg_box)

            def on_destroy(window):
                if should_restore:
                    self.present()
            picker_win.connect("destroy", on_destroy)

        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            valign=Gtk.Align.CENTER,
            halign=Gtk.Align.CENTER,
            spacing=12
        )

        label = Gtk.Label(label="Click anywhere on the screen to capture coordinates.")
        label.get_style_context().add_class("title-1")

        sub_label = Gtk.Label(label="Press ESC to cancel.")
        sub_label.get_style_context().add_class("title-3")

        box_css = Gtk.CssProvider()
        box_css.load_from_data(
            b"box { background-color: rgba(30, 30, 30, 0.85); padding: 24px 36px; border-radius: 12px; border: 1px solid rgba(255, 255, 255, 0.15); }"
            b"label { color: white; text-shadow: 0 1px 3px rgba(0,0,0,0.8); }"
        )
        box.get_style_context().add_provider(box_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        label.get_style_context().add_provider(box_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        sub_label.get_style_context().add_provider(box_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        box.append(label)
        box.append(sub_label)
        overlay.add_overlay(box)

        display = Gdk.Display.get_default()
        cursor = Gdk.Cursor.new_from_name("crosshair", None)
        picker_win.set_cursor(cursor)

        click_gesture = Gtk.GestureClick()
        def on_click(gesture, n_press, x, y):
            captured_x = int(round(x))
            captured_y = int(round(y))
            self.mouse_pos_x.set_value(captured_x)
            self.mouse_pos_y.set_value(captured_y)
            picker_win.destroy()
            self._show_toast(f"Captured Target Position: X={captured_x}, Y={captured_y}")

        click_gesture.connect("released", on_click)
        click_gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        picker_win.add_controller(click_gesture)

        key_controller = Gtk.EventControllerKey()
        def on_key_pressed(controller, keyval, keycode, state):
            if keyval == Gdk.KEY_Escape:
                picker_win.destroy()
                self._show_toast("Coordinate capture cancelled.")
                return True
            return False
        key_controller.connect("key-pressed", on_key_pressed)
        picker_win.add_controller(key_controller)

        picker_win.present()

    # D-Bus Portal Implementation

    def _trigger_portal_setup(self, reset_attempts=True):
        if reset_attempts:
            self._portal_attempts = 0

        if hasattr(self, '_portal_retry_timer_id') and self._portal_retry_timer_id:
            try:
                GLib.source_remove(self._portal_retry_timer_id)
            except Exception:
                pass
            self._portal_retry_timer_id = None

        self._setup_portal_shortcuts()
        return GLib.SOURCE_REMOVE

    def _handle_portal_failure(self):
        self._portal_attempts += 1
        if self._portal_attempts < 5:
            print(f"[Portal] Connection attempt {self._portal_attempts} failed. Retrying in 1 second...", flush=True)
            self._portal_retry_timer_id = GLib.timeout_add(1000, self._trigger_portal_setup, False)
        else:
            print(f"[Portal] All {self._portal_attempts} attempts failed. Showing conflict banner.", flush=True)
            GLib.idle_add(self.shortcut_collision_banner.set_revealed, True)

    def _setup_portal_shortcuts(self):
        GLib.set_prgname("io.github.Epoch5427.repeat")
        try:
            if not self._dbus_conn:
                self._dbus_conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            else:
                self._close_portal_session()
                self._session_handle = None

            # Unsubscribe existing subscriptions to avoid duplicate event handling (probably doesn't work given the success rate on the xdg portal connections)
            if hasattr(self, '_session_sub_id') and self._session_sub_id:
                try:
                    self._dbus_conn.signal_unsubscribe(self._session_sub_id)
                except Exception:
                    pass
                self._session_sub_id = None

            if hasattr(self, '_bind_sub_id') and self._bind_sub_id:
                try:
                    self._dbus_conn.signal_unsubscribe(self._bind_sub_id)
                except Exception:
                    pass
                self._bind_sub_id = None

            self._session_req_token = f"repeat_req_{uuid.uuid4().hex[:8]}"
            session_token = f"repeat_session_{uuid.uuid4().hex[:8]}"

            self._session_sub_id = self._dbus_conn.signal_subscribe(
                "org.freedesktop.portal.Desktop",
                "org.freedesktop.portal.Request",
                "Response",
                None,
                None,
                Gio.DBusSignalFlags.NO_MATCH_RULE,
                self._on_session_created,
                None
            )

            options_dict = {
                "session_handle_token": GLib.Variant("s", session_token),
                "handle_token": GLib.Variant("s", self._session_req_token)
            }
            create_params = GLib.Variant("(a{sv})", (options_dict,))

            self._dbus_conn.call(
                "org.freedesktop.portal.Desktop",
                "/org/freedesktop/portal/desktop",
                "org.freedesktop.portal.GlobalShortcuts",
                "CreateSession",
                create_params,
                GLib.VariantType.new("(o)"),
                Gio.DBusCallFlags.NONE,
                -1,
                None,
                self._async_call_cb,
                None
            )

        except Exception as e:
            err_str = str(e)
            print(f"[Portal] Global Shortcuts initialization failed: {err_str}", flush=True)
            self._handle_portal_failure()

    def _async_call_cb(self, source_object, res, user_data):
        try:
            source_object.call_finish(res)
        except Exception as e:
            print(f"[Portal] D-Bus call raised an exception: {e}", flush=True)

    def _on_session_created(self, connection, sender, path, interface, signal, parameters, user_data):
        if not path.endswith(self._session_req_token):
            return

        if self._session_sub_id:
            self._dbus_conn.signal_unsubscribe(self._session_sub_id)
            self._session_sub_id = None

        response, results = parameters.unpack()
        if response != 0:
            error_msg = results.get("error-message", "No description provided.")
            print(f"[Portal] Session creation failed (Code {response}): {error_msg}", flush=True)
            self._handle_portal_failure()
            return

        session_handle_var = results.get("session_handle")
        if not session_handle_var:
            return

        self._session_handle = session_handle_var

        if not hasattr(self, '_shortcut_act_sub_id') or not self._shortcut_act_sub_id:
            self._shortcut_act_sub_id = self._dbus_conn.signal_subscribe(
                None,
                "org.freedesktop.portal.GlobalShortcuts",
                "Activated",
                None,
                None,
                Gio.DBusSignalFlags.NONE,
                self._on_portal_shortcut_activated,
                None
            )

        self._bind_req_token = f"repeat_bind_{str(uuid.uuid4()).replace('-', '')[:8]}"

        self._bind_sub_id = self._dbus_conn.signal_subscribe(
            "org.freedesktop.portal.Desktop",
            "org.freedesktop.portal.Request",
            "Response",
            None,
            None,
            Gio.DBusSignalFlags.NO_MATCH_RULE,
            self._on_shortcuts_bound,
            None
        )

        shortcut_opts = {
            "description": GLib.Variant("s", "Toggle Execution"),
            "preferred_trigger": GLib.Variant("s", "F8")
        }
        shortcuts = [("toggle_clicking", shortcut_opts)]

        bind_options = {
            "handle_token": GLib.Variant("s", self._bind_req_token)
        }

        bind_params = GLib.Variant(
            "(oa(sa{sv})sa{sv})",
            (self._session_handle, shortcuts, "", bind_options)
        )

        self._dbus_conn.call(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.GlobalShortcuts",
            "BindShortcuts",
            bind_params,
            GLib.VariantType.new("(o)"),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            self._async_call_cb,
            None
        )

    def _on_shortcuts_bound(self, connection, sender, path, interface, signal, parameters, user_data):
        if not path.endswith(self._bind_req_token):
            return

        if hasattr(self, '_bind_sub_id') and self._bind_sub_id:
            self._dbus_conn.signal_unsubscribe(self._bind_sub_id)
            self._bind_sub_id = None

        response, results = parameters.unpack()

        if response != 0:
            error_message = results.get("error-message", "No specific error description provided.")
            print(f"[Portal] Shortcut binding returned response code: {response}", flush=True)
            print(f"[Portal] Diagnostic results dictionary: {results}", flush=True)

            self._handle_portal_failure()
            return

        #print("[Portal] Shortcuts successfully registered and active!", flush=True) # for debugging
        self._portal_attempts = 0

    def _on_portal_shortcut_activated(self, connection, sender, path, interface, signal, parameters, user_data):
        unpacked = parameters.unpack()
        if len(unpacked) >= 2:
            session_handle = unpacked[0]
            shortcut_id = unpacked[1]
            if session_handle == self._session_handle and shortcut_id == "toggle_clicking":
                GLib.idle_add(self._trigger_portal_toggle)

    def _trigger_portal_toggle(self):
        now = time.time()
        if not hasattr(self, '_last_toggle_time') or now - self._last_toggle_time > 0.2:
            self._last_toggle_time = now
            is_active = self.toggle_run_btn.get_active()

            self.toggle_run_btn.set_active(not is_active)
            if not is_active:
                self._show_toast("Started via Global Shortcut")
            else:
                self._show_toast("Stopped via Global Shortcut")

        return False

    def _on_shortcut_collision_retry(self, banner):
        self.shortcut_collision_banner.set_revealed(False)
        self._trigger_portal_setup(True)

    # Execution Logic

    def _on_banner_button_clicked(self, banner):
        message = (
            "Because Wayland enforces strict security, autoclickers require kernel-level hardware emulation via /dev/uinput.\n\n"
            "Even as a Flatpak, your host machine must grant permission:\n\n"
            "1. Add yourself to the input group on your host machine:\n"
            "   sudo usermod -aG input $USER\n\n"
            "2. Add a udev rule on your host machine:\n"
            "   echo 'KERNEL==\"uinput\", GROUP=\"input\", MODE=\"0660\"' | sudo tee /etc/udev/rules.d/99-uinput.rules\n\n"
            "Log out and log back in for changes to take effect."
        )
        dialog = Adw.MessageDialog(transient_for=self, heading="Host Permissions Required", body=message)
        dialog.add_response("ok", "OK")
        dialog.present()

    def _on_toggle_run_toggled(self, button):
        if hasattr(self, '_block_toggle_signal') and self._block_toggle_signal:
            return

        # If cooldown is active, prevent turning it back on
        if hasattr(self, '_toggle_cooldown_active') and self._toggle_cooldown_active:
            if button.get_active():
                self._block_toggle_signal = True
                button.set_active(False)
                self._block_toggle_signal = False
            return

        if button.get_active():
            button.remove_css_class("suggested-action")
            button.add_css_class("destructive-action")
            self._start_execution()
        else:
            button.set_label("Start")
            button.remove_css_class("destructive-action")
            button.add_css_class("suggested-action")
            self._stop_execution()

            # Activate a 50ms cooldown where new ON toggles are ignored. this is done programmatically rather than using sensitivity because I didn't like the way the button flashed that way'
            self._toggle_cooldown_active = True
            def end_cooldown():
                self._toggle_cooldown_active = False
                return GLib.SOURCE_REMOVE
            GLib.timeout_add(50, end_cooldown)

    def _start_execution(self):
        if not self._ui:
            self.toggle_run_btn.set_active(False)
            self._show_toast("Virtual pointer is not connected.")
            return

        # Perform syntax validation only if macro mode is active
        active_mode = int(round(self.carousel.get_position()))
        if active_mode == 2:
            macro_text = self.macro_sequence_row.get_text()
            try:
                self._parse_macro_sequence(macro_text)
            except ValueError as e:
                self.toggle_run_btn.set_active(False)
                dialog = Adw.MessageDialog(
                    transient_for=self,
                    heading="Macro Syntax Error",
                    body=str(e)
                )
                dialog.add_response("ok", "OK")
                dialog.set_default_response("ok")
                dialog.present()
                return

        self._set_inputs_sensitive(False)
        self._executions_made = 0

        start_delay = int(self.start_delay_row.get_value())
        if start_delay > 0:
            self._countdown_seconds = start_delay
            self.toggle_run_btn.set_label(f"Starting in {self._countdown_seconds}s...")
            self._delay_timeout_id = GLib.timeout_add_seconds(1, self._run_countdown)
        else:
            self.toggle_run_btn.set_label("Stop")
            self._begin_execution_loop()

    def _run_countdown(self):
        if self._delay_timeout_id is None:
            return GLib.SOURCE_REMOVE

        self._countdown_seconds -= 1

        if self._countdown_seconds > 0:
            self.toggle_run_btn.set_label(f"Starting in {self._countdown_seconds}s...")
            return GLib.SOURCE_CONTINUE
        else:
            self.toggle_run_btn.set_label("Stop")
            self._delay_timeout_id = None
            self._begin_execution_loop()
            return GLib.SOURCE_REMOVE

    def _parse_macro_sequence(self, text):
        if not text:
            return []

        actions = []
        parts = text.split(",")
        for part in parts:
            part = part.strip()
            if not part:
                continue

            low = part.lower()

            # 1. Delay / Sleep action
            if low.startswith("delay:") or low.startswith("sleep:"):
                split_delay = low.split(":")
                if len(split_delay) < 2 or not split_delay[1]:
                    raise ValueError(f"Invalid delay format in '{part}'. Expected 'delay:ms'.")
                try:
                    ms_val = float(split_delay[1])
                    if ms_val < 0:
                        raise ValueError()
                    actions.append(('delay', ms_val / 1000.0))
                except ValueError:
                    raise ValueError(f"Invalid delay value in '{part}'. Delay must be a positive number.")
                continue

            # 2. Click action
            if low.startswith("click:"):
                subparts = low.split(":")
                if len(subparts) < 2 or not subparts[1]:
                    raise ValueError(f"Invalid click format in '{part}'. Expected 'click:button'.")

                btn_str = subparts[1]
                if btn_str not in ("left", "right", "middle"):
                    raise ValueError(f"Unknown mouse button '{btn_str}' in '{part}'. Use 'left', 'right', or 'middle'.")

                if btn_str == "right":
                    code = ecodes.BTN_RIGHT
                elif btn_str == "middle":
                    code = ecodes.BTN_MIDDLE
                else:
                    code = ecodes.BTN_LEFT

                if len(subparts) >= 4:
                    try:
                        x = int(subparts[2])
                        y = int(subparts[3])
                        if x < 0 or y < 0:
                            raise ValueError()
                        actions.append(('click_at', code, x, y))
                    except ValueError:
                        raise ValueError(f"Invalid coordinates in '{part}'. Coordinates must be positive integers.")
                elif len(subparts) == 3:
                    raise ValueError(f"Missing Y coordinate in '{part}'. Expected 'click:button:X:Y'.")
                else:
                    actions.append(('click', code))
                continue

            # 3. Text Typing
            if low.startswith("type:"):
                if len(part) < 6:
                    raise ValueError(f"Empty type sequence in '{part}'. Expected 'type:text'.")
                type_str = part[5:] # Keep original casing
                actions.append(('type', type_str))
                continue

            # 4. Keyboard press or combination
            keys = part.split("+")
            modifier_codes = []
            main_code = None

            for k in keys:
                k_clean = k.strip().lower()
                if not k_clean:
                    raise ValueError(f"Empty key segment in '{part}'.")

                if k_clean in ('ctrl', 'control'):
                    modifier_codes.append(ecodes.KEY_LEFTCTRL)
                elif k_clean == 'alt':
                    modifier_codes.append(ecodes.KEY_LEFTALT)
                elif k_clean == 'shift':
                    modifier_codes.append(ecodes.KEY_LEFTSHIFT)
                elif k_clean in ('super', 'win', 'meta'):
                    modifier_codes.append(ecodes.KEY_LEFTMETA)
                else:
                    ev_code = self._map_string_to_keycode(k_clean)
                    if ev_code is None:
                        raise ValueError(f"Unknown key name '{k.strip()}' in '{part}'.")
                    main_code = ev_code

            if main_code is None and modifier_codes:
                main_code = modifier_codes.pop()

            if main_code is not None:
                actions.append(('combo', modifier_codes, main_code))
            else:
                raise ValueError(f"No valid key specified in '{part}'.")

        return actions

    def _snapshot_config(self):
        """Safely captures all user interface inputs from the GTK main thread before worker creation."""
        if self.timing_mode.get_selected() == 0:
            base_interval = int(self.interval_ms.get_value())
        else:
            count = int(self.rate_count.get_value())
            unit_idx = self.rate_unit.get_selected()
            if unit_idx == 0:
                base_interval = int(1000 / count)
            elif unit_idx == 1:
                base_interval = int(60000 / count)
            elif unit_idx == 2:
                base_interval = int(3600000 / count)
            else:
                base_interval = int(86400000 / count)

        target_key = self._target_key_name
        all_codes = []
        if target_key:
            parsed = Gtk.accelerator_parse(target_key)
            if len(parsed) == 3:
                success, keyval, modifier_mask = parsed
                if not success:
                    keyval, modifier_mask = 0, 0
            else:
                keyval, modifier_mask = parsed

            if keyval != 0:
                key_name = Gdk.keyval_name(keyval)
                main_code = self._map_string_to_keycode(key_name) if key_name else None

                if modifier_mask & Gdk.ModifierType.CONTROL_MASK:
                    all_codes.append(ecodes.KEY_LEFTCTRL)
                if modifier_mask & Gdk.ModifierType.SHIFT_MASK:
                    all_codes.append(ecodes.KEY_LEFTSHIFT)
                if modifier_mask & Gdk.ModifierType.ALT_MASK:
                    all_codes.append(ecodes.KEY_LEFTALT)
                if modifier_mask & Gdk.ModifierType.SUPER_MASK:
                    all_codes.append(ecodes.KEY_LEFTMETA)

                if main_code is not None:
                    all_codes.append(main_code)

        macro_text = self.macro_sequence_row.get_text()

        try:
            parsed_macro = self._parse_macro_sequence(macro_text)
        except ValueError:
            parsed_macro = []

        return {
            'active_mode': int(round(self.carousel.get_position())),
            'base_interval_ms': base_interval,
            'randomize': self.randomize_interval.get_enable_expansion(),
            'spread_ms': int(self.random_spread_ms.get_value()),
            'duty_cycle': int(self.duty_cycle.get_value()),

            # Mouse Settings
            'left_click': self.btn_left_click.get_active(),
            'middle_click': self.btn_middle_click.get_active(),
            'click_type_idx': self.click_type_row.get_selected(),
            'custom_location_enabled': self.custom_location_row.get_enable_expansion(),
            'mouse_pos_x': int(self.mouse_pos_x.get_value()),
            'mouse_pos_y': int(self.mouse_pos_y.get_value()),

            # Keyboard Settings
            'all_codes': all_codes,
            'kb_action_type': self.kb_action_type_row.get_selected(),

            # Macro Settings
            'macro_text': macro_text,
            'parsed_macro': parsed_macro,

            # Limits Configuration
            'repeat_limit_enabled': self.repeat_limit.get_enable_expansion(),
            'repeat_count': int(self.repeat_count_row.get_value()),
            'time_limit_enabled': self.has_time_limit.get_enable_expansion(),
            'time_limit': int(self.time_limit_row.get_value())
        }

    def _begin_execution_loop(self):
        self._start_time = time.perf_counter()

        # Lock setting snapshot
        self._worker_config = self._snapshot_config()
        self._stop_event = threading.Event()

        # Launch the worker thread
        self._worker_thread = threading.Thread(target=self._execution_worker, daemon=True)
        self._worker_thread.start()

    def _get_worker_interval_secs(self, config):
        base = config['base_interval_ms']
        if config['randomize']:
            spread = config['spread_ms']
            offset = random.randint(-spread, spread)
            base = max(1, base + offset)
        return base / 1000.0

    def _execution_worker(self):
        config = self._worker_config
        next_time = time.perf_counter()

        while not self._stop_event.is_set():
            interval_secs = self._get_worker_interval_secs(config)

            self._perform_worker_action(config)

            self._executions_made += 1

            # Constraints checking
            elapsed = time.perf_counter() - self._start_time
            if config['repeat_limit_enabled'] and self._executions_made >= config['repeat_count']:
                GLib.idle_add(self._stop_from_worker, f"Completed {config['repeat_count']} executions.")
                break

            if config['time_limit_enabled'] and elapsed >= config['time_limit']:
                GLib.idle_add(self._stop_from_worker, f"Reached time limit of {config['time_limit']}s.")
                break

            next_time += interval_secs
            sleep_time = next_time - time.perf_counter()

            if sleep_time > 0:
                # Use OS wait for longer gaps to reduce CPU usage
                if sleep_time > 0.001:
                    if self._stop_event.wait(timeout=sleep_time - 0.0005):
                        return

                while True:
                    if time.perf_counter() >= next_time:
                        break
                    if self._stop_event.is_set():
                        return
                    time.sleep(0)
            else:
                # Prevent falling behind cascading intervals
                next_time = time.perf_counter()

    def _type_char(self, char):
        # Character map for basic key typing
        char_map = {
            ' ': (ecodes.KEY_SPACE, False),
            'a': (ecodes.KEY_A, False), 'b': (ecodes.KEY_B, False), 'c': (ecodes.KEY_C, False),
            'd': (ecodes.KEY_D, False), 'e': (ecodes.KEY_E, False), 'f': (ecodes.KEY_F, False),
            'g': (ecodes.KEY_G, False), 'h': (ecodes.KEY_H, False), 'i': (ecodes.KEY_I, False),
            'j': (ecodes.KEY_J, False), 'k': (ecodes.KEY_K, False), 'l': (ecodes.KEY_L, False),
            'm': (ecodes.KEY_M, False), 'n': (ecodes.KEY_N, False), 'o': (ecodes.KEY_O, False),
            'p': (ecodes.KEY_P, False), 'q': (ecodes.KEY_Q, False), 'r': (ecodes.KEY_R, False),
            's': (ecodes.KEY_S, False), 't': (ecodes.KEY_T, False), 'u': (ecodes.KEY_U, False),
            'v': (ecodes.KEY_V, False), 'w': (ecodes.KEY_W, False), 'x': (ecodes.KEY_X, False),
            'y': (ecodes.KEY_Y, False), 'z': (ecodes.KEY_Z, False),
            'A': (ecodes.KEY_A, True), 'B': (ecodes.KEY_B, True), 'C': (ecodes.KEY_C, True),
            'D': (ecodes.KEY_D, True), 'E': (ecodes.KEY_E, True), 'F': (ecodes.KEY_F, True),
            'G': (ecodes.KEY_G, True), 'H': (ecodes.KEY_H, True), 'I': (ecodes.KEY_I, True),
            'J': (ecodes.KEY_J, True), 'K': (ecodes.KEY_K, True), 'L': (ecodes.KEY_L, True),
            'M': (ecodes.KEY_M, True), 'N': (ecodes.KEY_N, True), 'O': (ecodes.KEY_O, True),
            'P': (ecodes.KEY_P, True), 'Q': (ecodes.KEY_Q, True), 'R': (ecodes.KEY_R, True),
            'S': (ecodes.KEY_S, True), 'T': (ecodes.KEY_T, True), 'U': (ecodes.KEY_U, True),
            'V': (ecodes.KEY_V, True), 'W': (ecodes.KEY_W, True), 'X': (ecodes.KEY_X, True),
            'Y': (ecodes.KEY_Y, True), 'Z': (ecodes.KEY_Z, True),
            '0': (ecodes.KEY_0, False), '1': (ecodes.KEY_1, False), '2': (ecodes.KEY_2, False),
            '3': (ecodes.KEY_3, False), '4': (ecodes.KEY_4, False), '5': (ecodes.KEY_5, False),
            '6': (ecodes.KEY_6, False), '7': (ecodes.KEY_7, False), '8': (ecodes.KEY_8, False),
            '9': (ecodes.KEY_9, False),
            '.': (ecodes.KEY_DOT, False), ',': (ecodes.KEY_COMMA, False),
            '-': (ecodes.KEY_MINUS, False), '=': (ecodes.KEY_EQUAL, False),
            '\n': (ecodes.KEY_ENTER, False), '\t': (ecodes.KEY_TAB, False)
        }

        if char in char_map:
            code, shift = char_map[char]
            if shift:
                self._ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 1)
                self._ui.syn()

            self._ui.write(ecodes.EV_KEY, code, 1)
            self._ui.syn()
            time.sleep(0.005)
            self._ui.write(ecodes.EV_KEY, code, 0)
            self._ui.syn()

            if shift:
                self._ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 0)
                self._ui.syn()

    def _perform_worker_action(self, config):
        if not self._ui:
            return

        active_mode = config['active_mode']

        if active_mode == 0:
            if config['left_click']:
                code = ecodes.BTN_LEFT
            elif config['middle_click']:
                code = ecodes.BTN_MIDDLE
            else:
                code = ecodes.BTN_RIGHT

            click_type_idx = config['click_type_idx']
            clicks = 2 if click_type_idx == 1 else 1

            if config['custom_location_enabled']:
                target_x = config['mouse_pos_x']
                target_y = config['mouse_pos_y']
                try:
                    self._ui.write(ecodes.EV_REL, ecodes.REL_X, -10000)
                    self._ui.write(ecodes.EV_REL, ecodes.REL_Y, -10000)
                    self._ui.syn()
                    self._ui.write(ecodes.EV_REL, ecodes.REL_X, target_x)
                    self._ui.write(ecodes.EV_REL, ecodes.REL_Y, target_y)
                    self._ui.syn()
                except Exception as e:
                    print(f"[Warning] EV_REL position translation failed: {e}")

            for _ in range(clicks):
                duty = config['duty_cycle']
                base_interval = config['base_interval_ms']
                hold_time = (base_interval * (duty / 100.0)) / 1000.0

                self._ui.write(ecodes.EV_KEY, code, 1)
                self._ui.syn()
                if hold_time > 0.0001:
                    time.sleep(hold_time)
                self._ui.write(ecodes.EV_KEY, code, 0)
                self._ui.syn()

        elif active_mode == 1:
            all_codes = config['all_codes']
            if not all_codes:
                return

            def _write_keys(codes, value):
                for c in codes:
                    self._ui.write(ecodes.EV_KEY, c, value)
                self._ui.syn()

            kb_action_type = config.get('kb_action_type', 0)

            if kb_action_type == 0:
                duty = config['duty_cycle']
                base_interval = config['base_interval_ms']
                hold_time = (base_interval * (duty / 100.0)) / 1000.0

                _write_keys(all_codes, 1)
                if hold_time > 0.0001:
                    time.sleep(hold_time)
                _write_keys(all_codes[::-1], 0)
            elif kb_action_type == 1:
                _write_keys(all_codes, 1)
            elif kb_action_type == 2:
                _write_keys(all_codes[::-1], 0)

        else:
            parsed_macro = config.get('parsed_macro', [])
            for action in parsed_macro:
                if self._stop_event.is_set():
                    break

                action_type = action[0]

                if action_type == 'delay':
                    delay_time = action[1]
                    if delay_time > 0:
                        self._stop_event.wait(timeout=delay_time)

                elif action_type == 'click':
                    code = action[1]
                    self._ui.write(ecodes.EV_KEY, code, 1)
                    self._ui.syn()
                    time.sleep(0.01)
                    self._ui.write(ecodes.EV_KEY, code, 0)
                    self._ui.syn()

                elif action_type == 'click_at':
                    code, target_x, target_y = action[1], action[2], action[3]
                    try:
                        self._ui.write(ecodes.EV_REL, ecodes.REL_X, -10000)
                        self._ui.write(ecodes.EV_REL, ecodes.REL_Y, -10000)
                        self._ui.syn()
                        self._ui.write(ecodes.EV_REL, ecodes.REL_X, target_x)
                        self._ui.write(ecodes.EV_REL, ecodes.REL_Y, target_y)
                        self._ui.syn()
                    except Exception as e:
                        print(f"[Macro] Relative cursor translation failed: {e}")

                    self._ui.write(ecodes.EV_KEY, code, 1)
                    self._ui.syn()
                    time.sleep(0.01)
                    self._ui.write(ecodes.EV_KEY, code, 0)
                    self._ui.syn()

                elif action_type == 'type':
                    type_str = action[1]
                    for char in type_str:
                        if self._stop_event.is_set():
                            break
                        self._type_char(char)
                        time.sleep(0.01)

                elif action_type == 'combo':
                    modifiers, main_code = action[1], action[2]
                    for mod in modifiers:
                        self._ui.write(ecodes.EV_KEY, mod, 1)
                    self._ui.syn()

                    self._ui.write(ecodes.EV_KEY, main_code, 1)
                    self._ui.syn()

                    time.sleep(0.01)

                    self._ui.write(ecodes.EV_KEY, main_code, 0)
                    self._ui.syn()

                    for mod in reversed(modifiers):
                        self._ui.write(ecodes.EV_KEY, mod, 0)
                    self._ui.syn()

    def _on_record_macro_activated(self, row):
        def on_macro_recorded(macro_str):
            self.macro_sequence_row.set_text(macro_str)
            self._show_toast("Sequence updated successfully.")

        current_macro = self.macro_sequence_row.get_text()
        dialog = MacroRecorderDialog(self, on_macro_recorded, existing_macro=current_macro)
        dialog.present()

    def _stop_from_worker(self, message):
        self.toggle_run_btn.set_active(False)
        self._show_toast(message)

    def _stop_execution(self):
        if hasattr(self, '_stop_event') and self._stop_event:
            self._stop_event.set()

        if self._delay_timeout_id is not None:
            GLib.source_remove(self._delay_timeout_id)
            self._delay_timeout_id = None

        self._set_inputs_sensitive(True)

    def _set_inputs_sensitive(self, sensitive):
        self.btn_left_click.set_sensitive(sensitive)
        self.btn_middle_click.set_sensitive(sensitive)
        self.btn_right_click.set_sensitive(sensitive)
        self.click_type_row.set_sensitive(sensitive)
        self.custom_location_row.set_sensitive(sensitive)

        self.kb_key_row.set_sensitive(sensitive)
        self.kb_action_type_row.set_sensitive(sensitive)

        self.macro_sequence_row.set_sensitive(sensitive)
        self.record_macro_btn.set_sensitive(sensitive)

        self.timing_mode.set_sensitive(sensitive)
        self.interval_ms.set_sensitive(sensitive)
        self.rate_count.set_sensitive(sensitive)
        self.rate_unit.set_sensitive(sensitive)
        self.start_delay_row.set_sensitive(sensitive)
        self.repeat_limit.set_sensitive(sensitive)
        self.has_time_limit.set_sensitive(sensitive)

        self.randomize_interval.set_sensitive(sensitive)
        self.duty_cycle.set_sensitive(sensitive)

    def _map_string_to_keycode(self, key_str):
        key_str = key_str.strip().upper().replace("KP_", "KP")
        aliases = {
            'CTRL': 'LEFTCTRL', 'ALT': 'LEFTALT', 'SHIFT': 'LEFTSHIFT', 'WIN': 'LEFTMETA',
            'RETURN': 'ENTER', 'BACKSPACE': 'BACKSPACE', 'ESCAPE': 'ESC',
            'PAGE_UP': 'PAGEUP', 'PAGE_DOWN': 'PAGEDOWN', 'SPACE': 'SPACE',
            'SUPER_L': 'LEFTMETA', 'SUPER_R': 'RIGHTMETA'
        }
        key_str = aliases.get(key_str, key_str)
        try:
            return getattr(ecodes, f"KEY_{key_str}")
        except AttributeError:
            return None

    def _on_close_request(self, window):
        # Check if the tray icon process is actually active and healthy
        tray_active = False
        if hasattr(self, '_tray_process') and self._tray_process:
            if self._tray_process.poll() is None:
                tray_active = True

        # Fallback: If the tray isn't working, save settings and close normally
        if not tray_active:
            self._stop_execution()
            self._close_portal_session()
            self._save_settings()
            return False # Let the default GTK handler destroy the window

        # Otherwise, minimize to tray
        self.set_visible(False)
        self._save_settings()
        return True # Stop GTK from destroying the window instance

    def _real_quit(self):
        # Actual application teardown triggered by the tray "Quit" button
        self._stop_execution()
        self._close_portal_session()
        self._save_settings()

        if hasattr(self, '_tray_process') and self._tray_process:
            self._tray_process.terminate()
            self._tray_process.wait()

        self.destroy() # Actually destroy the window to exit the application

    def _close_portal_session(self):
        if self._dbus_conn and self._session_handle:
            try:
                self._dbus_conn.call_sync(
                    "org.freedesktop.portal.Desktop",
                    self._session_handle,
                    "org.freedesktop.portal.Session",
                    "Close",
                    None,
                    None,
                    Gio.DBusCallFlags.NONE,
                    1000,
                    None
                )
            except Exception as e:
                print(f"[Portal] Failed to close session on exit: {e}", flush=True)

    def _on_kb_key_button_toggled(self, button):
        if button.get_active():
            button.add_css_class("suggested-action")
            self.kb_shortcut_label.set_accelerator("")
        else:
            button.remove_css_class("suggested-action")
            self.kb_shortcut_label.set_accelerator(self._target_key_name)

    def _show_toast(self, message):
        toast = Adw.Toast.new(message)
        self.toast_overlay.add_toast(toast)
