from typing import Callable
from gi.repository import Gtk, Gdk

class KeyPickerDialog(Gtk.Window):
    def __init__(self, parent: Gtk.Window, on_key_picked_cb: Callable[[str], None]):
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

        self._build_ui()
        self._setup_events()

    def _build_ui(self):
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

    def _setup_events(self):
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_ctrl)

    def _on_key_pressed(self, controller, keyval: int, keycode: int, state: Gdk.ModifierType) -> bool:
        if keyval == Gdk.KEY_Escape:
            self.destroy()
            return True

        # Ignore solitary modifier presses
        ignored_modifiers = [
            Gdk.KEY_Control_L, Gdk.KEY_Control_R,
            Gdk.KEY_Shift_L,   Gdk.KEY_Shift_R,
            Gdk.KEY_Alt_L,     Gdk.KEY_Alt_R,
            Gdk.KEY_Super_L,   Gdk.KEY_Super_R,
            Gdk.KEY_Meta_L,    Gdk.KEY_Meta_R
        ]
        if keyval in ignored_modifiers:
            return False

        accel_name = Gtk.accelerator_name_with_keycode(None, keyval, keycode, state)
        if accel_name:
            self.on_key_picked_cb(accel_name)
            self.destroy()
            return True

        return False
