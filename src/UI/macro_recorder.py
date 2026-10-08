import time
from typing import Callable, List, Optional
from gi.repository import Adw, Gtk, Gdk

MACRO_DIALOG_CSS = b"""
.rounded-scrolled-window {
    border-radius: 12px;
    border: 1px solid rgba(128, 128, 128, 0.25);
}
.rounded-scrolled-window textview {
    border-radius: 12px;
}
.record-area-active {
    border: 2px solid @accent_color;
}
"""

class MacroRecorderDialog(Gtk.Window):
    def __init__(
        self,
        parent: Gtk.Window,
        on_macro_recorded_cb: Callable[[str], None],
        existing_macro: str = ""
    ):
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
        self.last_event_time: Optional[float] = None
        self.is_recording = False

        self.recorded_actions: List[str] = [
            x.strip() for x in existing_macro.split(",") if x.strip()
        ] if existing_macro else []

        self._apply_styling()
        self._build_ui()
        self._setup_event_listeners()

        self._update_text_display()
        self._update_button_state()
        if self.recorded_actions:
            self.save_btn.set_sensitive(True)

    def _apply_styling(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(MACRO_DIALOG_CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _build_ui(self):
        header_bar = Adw.HeaderBar()
        header_bar.add_css_class("flat")
        header_bar.set_show_end_title_buttons(False)
        header_bar.set_show_start_title_buttons(False)
        self.set_titlebar(header_bar)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda *_: self.destroy())
        header_bar.pack_start(cancel_btn)

        self.save_btn = Gtk.Button(label="Save")
        self.save_btn.add_css_class("suggested-action")
        self.save_btn.connect("clicked", self._on_save)
        self.save_btn.set_sensitive(False)
        header_bar.pack_end(self.save_btn)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        main_box.set_margin_top(12)
        main_box.set_margin_bottom(16)

        info_label = Gtk.Label(
            label="Type keys or click inside the box below while recording. "
                  "Actions and realistic delays are captured."
        )
        info_label.set_wrap(True)
        info_label.add_css_class("dim-label")
        info_label.set_justify(Gtk.Justification.CENTER)
        info_label.set_margin_start(24)
        info_label.set_margin_end(24)
        main_box.append(info_label)

        self.sequence_text_view = Gtk.TextView()
        self.sequence_text_view.set_editable(False)
        self.sequence_text_view.set_cursor_visible(False)
        self.sequence_text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.sequence_text_view.set_vexpand(True)
        self.sequence_text_view.set_hexpand(True)
        self.sequence_text_view.set_left_margin(14)
        self.sequence_text_view.set_right_margin(14)
        self.sequence_text_view.set_top_margin(14)
        self.sequence_text_view.set_bottom_margin(14)

        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_child(self.sequence_text_view)
        self.scrolled_window.set_vexpand(True)
        self.scrolled_window.set_has_frame(False)
        self.scrolled_window.add_css_class("rounded-scrolled-window")
        self.scrolled_window.set_margin_start(24)
        self.scrolled_window.set_margin_end(24)
        self.scrolled_window.set_margin_top(4)
        self.scrolled_window.set_margin_bottom(4)
        main_box.append(self.scrolled_window)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        btn_box.set_halign(Gtk.Align.CENTER)
        btn_box.set_margin_bottom(12)

        self.action_btn = Gtk.Button(label="Start Recording")
        self.action_btn.connect("clicked", self._on_action_btn_clicked)
        btn_box.append(self.action_btn)
        main_box.append(btn_box)

        self.set_child(main_box)

    def _setup_event_listeners(self):
        # Keyboard listener
        self.key_controller = Gtk.EventControllerKey()
        self.key_controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(self.key_controller)

        # Mouse listener over typing/recording region
        self.click_controller = Gtk.GestureClick()
        self.click_controller.set_button(0)  # Catch left, middle, right
        self.click_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.click_controller.connect("pressed", self._on_text_view_clicked)
        self.sequence_text_view.add_controller(self.click_controller)

    def _update_button_state(self):
        self.action_btn.remove_css_class("suggested-action")
        self.action_btn.remove_css_class("destructive-action")

        if self.is_recording:
            self.action_btn.set_label("Stop Recording")
            self.action_btn.add_css_class("destructive-action")
            self.scrolled_window.add_css_class("record-area-active")
        else:
            self.scrolled_window.remove_css_class("record-area-active")
            if self.recorded_actions:
                self.action_btn.set_label("Clear")
            else:
                self.action_btn.set_label("Start Recording")
                self.action_btn.add_css_class("suggested-action")

    def _on_action_btn_clicked(self, _):
        if self.is_recording:
            self.is_recording = False
            self.last_event_time = None
            self._update_text_display()
            self._update_button_state()
            self.save_btn.set_sensitive(len(self.recorded_actions) > 0)
        else:
            if self.recorded_actions:
                self.recorded_actions.clear()
                self.last_event_time = None
                self._update_text_display()
                self._update_button_state()
                self.save_btn.set_sensitive(False)
            else:
                self.is_recording = True
                self.last_event_time = None
                self._show_recording_status()
                self._update_button_state()
                self.save_btn.set_sensitive(False)

    def _record_delay_if_needed(self):
        now = time.perf_counter()
        if self.last_event_time is not None:
            elapsed_ms = int((now - self.last_event_time) * 1000)
            if elapsed_ms > 40:
                self.recorded_actions.append(f"delay:{elapsed_ms}")
        self.last_event_time = now

    def _on_text_view_clicked(self, gesture, n_press, x, y):
        if not self.is_recording:
            return

        button = gesture.get_current_button()
        btn_map = {1: "left", 2: "middle", 3: "right"}
        btn_name = btn_map.get(button)
        if not btn_name:
            return

        self._record_delay_if_needed()
        self.recorded_actions.append(f"click:{btn_name}")
        self._show_recording_status()
        self.save_btn.set_sensitive(True)

        gesture.set_state(Gtk.EventSequenceState.CLAIMED)

    def _on_key_pressed(self, controller, keyval: int, keycode: int, state: Gdk.ModifierType) -> bool:
        if not self.is_recording:
            if keyval == Gdk.KEY_Escape:
                self.destroy()
                return True
            return False

        # Ignore bare modifier presses
        ignored_modifiers = [
            Gdk.KEY_Control_L, Gdk.KEY_Control_R,
            Gdk.KEY_Shift_L,   Gdk.KEY_Shift_R,
            Gdk.KEY_Alt_L,     Gdk.KEY_Alt_R,
            Gdk.KEY_Super_L,   Gdk.KEY_Super_R,
            Gdk.KEY_Meta_L,    Gdk.KEY_Meta_R
        ]
        if keyval in ignored_modifiers:
            return False

        self._record_delay_if_needed()

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
            clean = key_name.lower()
            if clean == "return":
                clean = "enter"
            if clean not in combo_parts:
                combo_parts.append(clean)

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
            buffer.set_text(f"{text} (Recording... click inside box or press keys)")
        else:
            buffer.set_text("(Recording... Click inside this box or press keys to begin)")

    def _update_text_display(self):
        buffer = self.sequence_text_view.get_buffer()
        buffer.set_text(", ".join(self.recorded_actions))

    def _on_save(self, _):
        macro_str = ", ".join(self.recorded_actions)
        if macro_str:
            self.on_macro_recorded_cb(macro_str)
        self.destroy()
