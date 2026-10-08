import os
import sys
import subprocess
import threading
from gi.repository import Adw, Gtk, Gdk, Gio, GLib
from evdev import ecodes

from .models import ExecutionConfig
from .emulator import InputEmulator
from .worker import ExecutionEngine
from .portals import DesktopPortalClient
from .macro_parser import parse_macro_sequence, string_to_keycode
from .UI.key_picker import KeyPickerDialog
from .UI.macro_recorder import MacroRecorderDialog
from .UI.coordinate_picker import CoordinatePickerWindow

@Gtk.Template(resource_path='/io/github/Epoch5427/repeat/window.ui')
class RepeatWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'RepeatWindow'

    # Template Children
    primary_menu_popover = Gtk.Template.Child()
    toast_overlay = Gtk.Template.Child()
    toggle_run_btn = Gtk.Template.Child()
    toggle_key = Gtk.Template.Child()
    toggle_with = Gtk.Template.Child()
    permission_banner = Gtk.Template.Child()
    shortcut_collision_banner = Gtk.Template.Child()
    mode_switcher = Gtk.Template.Child()
    mode_stack = Gtk.Template.Child()
    carousel = Gtk.Template.Child()

    # Mode 1: Mouse
    btn_left_click = Gtk.Template.Child()
    btn_middle_click = Gtk.Template.Child()
    btn_right_click = Gtk.Template.Child()
    btn_single_click = Gtk.Template.Child()
    btn_double_click = Gtk.Template.Child()
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

    # Timing Controls
    btn_timing_delay = Gtk.Template.Child()
    btn_timing_rate = Gtk.Template.Child()
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

        # GSettings initialization
        self.settings = Gio.Settings(schema_id="io.github.Epoch5427.repeat")

        # Core Services
        self.emulator = InputEmulator()
        self.engine = ExecutionEngine(self.emulator)
        self.portal = DesktopPortalClient(
            on_toggle_shortcut=self._on_portal_toggle_received,
            on_shortcut_changed=self._on_portal_shortcut_changed
        )

        self._target_key_name = "space"
        self._delay_timeout_id = None
        self._syncing_tabs = False
        self._tray_proc: subprocess.Popen | None = None

        self._bind_settings()
        self._wire_signals()
        self._init_hardware_async()
        self._start_tray_process()

        GLib.idle_add(self._setup_portals)

    def _on_portal_shortcut_changed(self, trigger_text: str):
        """Called whenever the portal assigns, clears, or denies the shortcut."""
        def update_label():
            accel = self._sanitize_accelerator(trigger_text)
            if accel:
                self.toggle_key.set_accelerator(accel)
                self.toggle_with.set_visible(True)
            else:
                self.toggle_key.set_disabled_text("Unassigned")
                self.toggle_with.set_visible(False)
                self.toggle_key.set_accelerator("")
            return GLib.SOURCE_REMOVE

        GLib.idle_add(update_label)

    def _sanitize_accelerator(self, trigger_text: str) -> str:
        if not trigger_text:
            return ""

        text = trigger_text.strip()

        def is_valid_accel(candidate: str) -> bool:
            try:
                parsed = Gtk.accelerator_parse(candidate)
                return parsed[-2] != 0
            except Exception:
                return False

        if is_valid_accel(text):
            return text

        for prefix in ("press ", "hold ", "appuyez sur ", "drücken sie "):
            if text.lower().startswith(prefix):
                candidate = text[len(prefix):].strip()
                if is_valid_accel(candidate):
                    return candidate

        tokens = text.split()
        if tokens and is_valid_accel(tokens[-1]):
            return tokens[-1]

        return ""

    def _bind_settings(self):
        b = self.settings.bind

        # Mouse button radio restoration
        mouse_btn = self.settings.get_string("mouse-button")
        if mouse_btn == "middle":
            self.btn_middle_click.set_active(True)
        elif mouse_btn == "right":
            self.btn_right_click.set_active(True)
        else:
            self.btn_left_click.set_active(True)

        self.btn_left_click.connect("toggled", self._on_mouse_btn_toggled)
        self.btn_middle_click.connect("toggled", self._on_mouse_btn_toggled)
        self.btn_right_click.connect("toggled", self._on_mouse_btn_toggled)

        # Click Type toggle restoration & listener
        if self.settings.get_uint("click-type") == 1:
            self.btn_double_click.set_active(True)
        else:
            self.btn_single_click.set_active(True)
        self.btn_single_click.connect("toggled", self._on_click_type_toggled)
        self.btn_double_click.connect("toggled", self._on_click_type_toggled)

        # Timing Mode toggle restoration & listener
        if self.settings.get_uint("timing-mode") == 1:
            self.btn_timing_rate.set_active(True)
        else:
            self.btn_timing_delay.set_active(True)
        self.btn_timing_delay.connect("toggled", self._on_timing_mode_toggled)
        self.btn_timing_rate.connect("toggled", self._on_timing_mode_toggled)

        # Settings bindings
        b("custom-location-enabled", self.custom_location_row, "enable-expansion", Gio.SettingsBindFlags.DEFAULT)
        b("mouse-pos-x", self.mouse_pos_x, "value", Gio.SettingsBindFlags.DEFAULT)
        b("mouse-pos-y", self.mouse_pos_y, "value", Gio.SettingsBindFlags.DEFAULT)
        b("kb-action-type", self.kb_action_type_row, "selected", Gio.SettingsBindFlags.DEFAULT)
        self._target_key_name = self.settings.get_string("target-key-name")
        self.kb_shortcut_label.set_accelerator(self._target_key_name)
        b("macro-text", self.macro_sequence_row, "text", Gio.SettingsBindFlags.DEFAULT)
        b("interval-ms", self.interval_ms, "value", Gio.SettingsBindFlags.DEFAULT)
        b("rate-count", self.rate_count, "value", Gio.SettingsBindFlags.DEFAULT)
        b("rate-unit", self.rate_unit, "selected", Gio.SettingsBindFlags.DEFAULT)
        b("start-delay", self.start_delay_row, "value", Gio.SettingsBindFlags.DEFAULT)
        b("repeat-limit-enabled", self.repeat_limit, "enable-expansion", Gio.SettingsBindFlags.DEFAULT)
        b("repeat-count", self.repeat_count_row, "value", Gio.SettingsBindFlags.DEFAULT)
        b("time-limit-enabled", self.has_time_limit, "enable-expansion", Gio.SettingsBindFlags.DEFAULT)
        b("time-limit", self.time_limit_row, "value", Gio.SettingsBindFlags.DEFAULT)
        b("randomize-interval", self.randomize_interval, "enable-expansion", Gio.SettingsBindFlags.DEFAULT)
        b("spread-ms", self.random_spread_ms, "value", Gio.SettingsBindFlags.DEFAULT)
        b("duty-cycle", self.duty_cycle, "value", Gio.SettingsBindFlags.DEFAULT)

        # Active tab page
        active_idx = self.settings.get_int("active-mode")
        page = self.carousel.get_nth_page(active_idx)
        if page:
            self.carousel.scroll_to(page, False)
            names = ["mouse", "keyboard", "macro"]
            if 0 <= active_idx < len(names):
                self.mode_stack.set_visible_child_name(names[active_idx])

        self._update_timing_visibility()

    def _on_click_type_toggled(self, _):
        val = 1 if self.btn_double_click.get_active() else 0
        self.settings.set_uint("click-type", val)

    def _on_timing_mode_toggled(self, _):
        val = 1 if self.btn_timing_rate.get_active() else 0
        self.settings.set_uint("timing-mode", val)
        self._update_timing_visibility()

    def _on_mouse_btn_toggled(self, _):
        if self.btn_left_click.get_active():
            self.settings.set_string("mouse-button", "left")
        elif self.btn_middle_click.get_active():
            self.settings.set_string("mouse-button", "middle")
        elif self.btn_right_click.get_active():
            self.settings.set_string("mouse-button", "right")

    def _wire_signals(self):
        self.carousel.connect("page-changed", self._on_carousel_page_changed)
        self.mode_stack.connect("notify::visible-child-name", self._on_stack_page_changed)

        self.kb_key_button.connect("clicked", self._open_key_picker)
        self.pick_position_row.connect("activated", lambda *_: self._pick_position())
        self.record_macro_btn.connect("activated", self._open_macro_recorder)
        self.toggle_run_btn.connect("toggled", self._on_run_toggled)

        self.shortcut_collision_banner.connect("button-clicked", lambda *_: self._setup_portals())
        self.connect("close-request", self._on_close_request)

    def _init_hardware_async(self):
        def task():
            ok = self.emulator.initialize()
            GLib.idle_add(self._on_hardware_ready, ok)
        threading.Thread(target=task, daemon=True).start()

    def _on_hardware_ready(self, success: bool):
        self.permission_banner.set_revealed(not success)
        self.toggle_run_btn.set_sensitive(success)
        if not success:
            self._show_toast("Hardware permissions missing for /dev/uinput.")

    def _setup_portals(self):
        self.shortcut_collision_banner.set_revealed(False)
        self.portal.setup_global_shortcuts(
            on_failure=lambda: GLib.idle_add(self.shortcut_collision_banner.set_revealed, True)
        )
        return GLib.SOURCE_REMOVE

    def _on_portal_toggle_received(self):
        GLib.idle_add(lambda: self.toggle_run_btn.set_active(not self.toggle_run_btn.get_active()))

    def _on_run_toggled(self, btn):
        if btn.get_active():
            btn.remove_css_class("suggested-action")
            btn.add_css_class("destructive-action")
            self._start()
        else:
            btn.set_label("Start")
            btn.remove_css_class("destructive-action")
            btn.add_css_class("suggested-action")
            self._stop()

    def _build_config(self) -> ExecutionConfig:
        if self.btn_timing_delay.get_active():
            interval = int(self.interval_ms.get_value())
        else:
            cnt = max(1, int(self.rate_count.get_value()))
            divs = [1000, 60000, 3600000, 86400000]
            interval = int(divs[self.rate_unit.get_selected()] / cnt)

        # Parse target key accelerator
        all_codes = []
        if self._target_key_name:
            parsed = Gtk.accelerator_parse(self._target_key_name)
            val, mask = parsed[-2:]
            name = Gdk.keyval_name(val)
            if mask & Gdk.ModifierType.CONTROL_MASK: all_codes.append(ecodes.KEY_LEFTCTRL)
            if mask & Gdk.ModifierType.SHIFT_MASK:   all_codes.append(ecodes.KEY_LEFTSHIFT)
            if mask & Gdk.ModifierType.ALT_MASK:     all_codes.append(ecodes.KEY_LEFTALT)
            if mask & Gdk.ModifierType.SUPER_MASK:   all_codes.append(ecodes.KEY_LEFTMETA)
            code = string_to_keycode(name) if name else None
            if code: all_codes.append(code)

        btn = ecodes.BTN_LEFT if self.btn_left_click.get_active() else \
              (ecodes.BTN_MIDDLE if self.btn_middle_click.get_active() else ecodes.BTN_RIGHT)

        return ExecutionConfig(
            active_mode=int(round(self.carousel.get_position())),
            base_interval_ms=interval,
            randomize=self.randomize_interval.get_enable_expansion(),
            spread_ms=int(self.random_spread_ms.get_value()),
            duty_cycle=int(self.duty_cycle.get_value()),
            mouse_button=btn,
            click_type_idx=1 if self.btn_double_click.get_active() else 0,
            custom_location_enabled=self.custom_location_row.get_enable_expansion(),
            mouse_pos_x=int(self.mouse_pos_x.get_value()),
            mouse_pos_y=int(self.mouse_pos_y.get_value()),
            all_codes=all_codes,
            kb_action_type=self.kb_action_type_row.get_selected(),
            parsed_macro=parse_macro_sequence(self.macro_sequence_row.get_text()),
            repeat_limit_enabled=self.repeat_limit.get_enable_expansion(),
            repeat_count=int(self.repeat_count_row.get_value()),
            time_limit_enabled=self.has_time_limit.get_enable_expansion(),
            time_limit=int(self.time_limit_row.get_value())
        )

    def _start(self):
        if not self.emulator.is_ready:
            self.toggle_run_btn.set_active(False)
            self._show_toast("Virtual pointer unavailable.")
            return

        try:
            config = self._build_config()
        except ValueError as err:
            self.toggle_run_btn.set_active(False)
            self._show_alert("Macro Syntax Error", str(err))
            return

        self._set_inputs_sensitive(False)
        delay = int(self.start_delay_row.get_value())
        if delay > 0:
            self._countdown = delay
            self.toggle_run_btn.set_label(f"Starting in {self._countdown}s...")
            self._delay_timeout_id = GLib.timeout_add_seconds(1, self._run_countdown, config)
        else:
            self.toggle_run_btn.set_label("Stop")
            self.engine.start(config, on_stop_cb=self._on_worker_finished)

    def _run_countdown(self, config):
        self._countdown -= 1
        if self._countdown > 0:
            self.toggle_run_btn.set_label(f"Starting in {self._countdown}s...")
            return GLib.SOURCE_CONTINUE
        self.toggle_run_btn.set_label("Stop")
        self._delay_timeout_id = None
        self.engine.start(config, on_stop_cb=self._on_worker_finished)
        return GLib.SOURCE_REMOVE

    def _stop(self):
        if self._delay_timeout_id:
            GLib.source_remove(self._delay_timeout_id)
            self._delay_timeout_id = None
        self.engine.stop()
        self._set_inputs_sensitive(True)

    def _on_worker_finished(self, message: str):
        GLib.idle_add(self._worker_finished_ui, message)

    def _worker_finished_ui(self, message: str):
        self.toggle_run_btn.set_active(False)
        self._show_toast(message)
        return GLib.SOURCE_REMOVE

    def _start_tray_process(self):
        try:
            tray_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tray_indicator.py")
            pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            env = os.environ.copy()
            env["PYTHONPATH"] = f"{pkg_root}:{env.get('PYTHONPATH', '')}"

            self._tray_proc = subprocess.Popen(
                [sys.executable, tray_script],
                stdout=subprocess.PIPE, stdin=subprocess.PIPE, text=True, env=env
            )
            def read_pipe():
                try:
                    for line in iter(self._tray_proc.stdout.readline, ''):
                        cmd = line.strip()
                        if cmd == "show":
                            GLib.idle_add(lambda: (self.set_visible(True), self.present()))
                        elif cmd == "toggle":
                            GLib.idle_add(lambda: self.toggle_run_btn.set_active(not self.toggle_run_btn.get_active()))
                        elif cmd == "quit":
                            GLib.idle_add(self._real_quit)
                except Exception:
                    pass
            threading.Thread(target=read_pipe, daemon=True).start()
        except Exception as e:
            print(f"[Tray] Initialization failed: {e}", flush=True)

    def _on_close_request(self, _):
        if self._tray_proc and self._tray_proc.poll() is None:
            self.set_visible(False)
            return True
        self._real_quit()
        return False

    def _real_quit(self):
        self._stop()
        self.portal.close_session()
        self.emulator.close()
        if self._tray_proc:
            self._tray_proc.terminate()
        app = self.get_application()
        if app:
            app.quit()
        os._exit(0)

    def _show_toast(self, msg: str):
        self.toast_overlay.add_toast(Adw.Toast.new(msg))

    def _show_alert(self, title: str, body: str):
        dlg = Adw.MessageDialog(transient_for=self, heading=title, body=body)
        dlg.add_response("ok", "OK")
        dlg.present()

    def _on_stack_page_changed(self, stack, _):
        if self._syncing_tabs: return
        self._syncing_tabs = True
        idx = {"mouse": 0, "keyboard": 1, "macro": 2}.get(stack.get_visible_child_name(), 0)
        page = self.carousel.get_nth_page(idx)
        if page:
            self.carousel.scroll_to(page, True)
            self.settings.set_int("active-mode", idx)
        self._syncing_tabs = False

    def _on_carousel_page_changed(self, _, index):
        if self._syncing_tabs: return
        self._syncing_tabs = True
        names = ["mouse", "keyboard", "macro"]
        if 0 <= index < len(names):
            self.mode_stack.set_visible_child_name(names[index])
            self.settings.set_int("active-mode", index)
        self._syncing_tabs = False

    def _update_timing_visibility(self):
        is_delay = self.btn_timing_delay.get_active()
        self.interval_ms.set_visible(is_delay)
        self.rate_count.set_visible(not is_delay)

    def _open_key_picker(self, _):
        def cb(accel):
            self._target_key_name = accel
            self.kb_shortcut_label.set_accelerator(accel)
            self.settings.set_string("target-key-name", accel)
        KeyPickerDialog(self, cb).present()

    def _open_macro_recorder(self, _):
        def cb(seq):
            self.macro_sequence_row.set_text(seq)
            self._show_toast("Sequence updated.")
        MacroRecorderDialog(self, cb, existing_macro=self.macro_sequence_row.get_text()).present()

    def _pick_position(self):
        self.set_visible(False)

        def on_captured(response, path):
            if response == 0 and path:
                self.set_visible(True)

                def on_coords_picked(x, y):
                    self.mouse_pos_x.set_value(x)
                    self.mouse_pos_y.set_value(y)
                    self._show_toast(f"Captured Target Position: X={x}, Y={y}")

                picker = CoordinatePickerWindow(self, path, on_coords_picked)
                picker.present()
            elif not getattr(self, '_screenshot_interactive_attempted', False):
                self._screenshot_interactive_attempted = True
                self.portal.request_screenshot(True, on_captured)
            else:
                self._screenshot_interactive_attempted = False
                self.set_visible(True)
                self.present()
                self._show_toast("Coordinate capture cancelled.")

        self._screenshot_interactive_attempted = False
        GLib.timeout_add(350, lambda: (self.portal.request_screenshot(False, on_captured), GLib.SOURCE_REMOVE)[-1])

    def _set_inputs_sensitive(self, sensitive: bool):
        for widget in [self.mode_switcher, self.carousel, self.btn_left_click,
                       self.btn_middle_click, self.btn_right_click,
                       self.btn_single_click, self.btn_double_click,
                       self.custom_location_row, self.kb_key_row, self.kb_action_type_row,
                       self.macro_sequence_row, self.record_macro_btn,
                       self.btn_timing_delay, self.btn_timing_rate,
                       self.interval_ms, self.rate_count, self.start_delay_row]:
            widget.set_sensitive(sensitive)
