import os
from typing import Callable
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk

class CoordinatePickerWindow(Gtk.Window):
    def __init__(self, parent: Gtk.Window, screenshot_path: str, on_picked_cb: Callable[[int, int], None]):
        super().__init__(
            transient_for=parent,
            modal=True,
            destroy_with_parent=True
        )
        self.screenshot_path = screenshot_path
        self.on_picked_cb = on_picked_cb

        self.set_decorated(False)
        self.fullscreen()

        overlay = Gtk.Overlay()
        self.set_child(overlay)

        # Display the captured screenshot across the entire screen
        if self.screenshot_path and os.path.exists(self.screenshot_path):
            picture = Gtk.Picture.new_for_filename(self.screenshot_path)
            picture.set_can_shrink(True)
            picture.set_keep_aspect_ratio(False)
            overlay.set_child(picture)
        else:
            self.set_opacity(0.4)
            overlay.set_child(Gtk.Box())

        self.connect("destroy", self._on_destroy)

        # Center instruction banner
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            valign=Gtk.Align.CENTER,
            halign=Gtk.Align.CENTER,
            spacing=12
        )
        box.add_css_class("picker-banner-box")

        label = Gtk.Label(label="Click anywhere on the screen to capture coordinates.")
        label.add_css_class("title-1")

        sub_label = Gtk.Label(label="Press ESC to cancel.")
        sub_label.add_css_class("title-3")

        box.append(label)
        box.append(sub_label)
        overlay.add_overlay(box)

        # Set crosshair cursor
        cursor = Gdk.Cursor.new_from_name("crosshair", None)
        self.set_cursor(cursor)

        # Capture click
        click_gesture = Gtk.GestureClick()
        click_gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        click_gesture.connect("released", self._on_clicked)
        self.add_controller(click_gesture)

        # Capture ESC to cancel
        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_controller)

        self._apply_styling()

    def _apply_styling(self):
        css = b"""
        .picker-banner-box {
            background-color: rgba(30, 30, 30, 0.85);
            padding: 24px 36px;
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.15);
        }
        .picker-banner-box label {
            color: white;
            text-shadow: 0 1px 3px rgba(0, 0, 0, 0.8);
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _on_clicked(self, gesture, n_press, x, y):
        captured_x = int(round(x))
        captured_y = int(round(y))
        self.on_picked_cb(captured_x, captured_y)
        self.destroy()

    def _on_key_pressed(self, controller, keyval: int, keycode: int, state: Gdk.ModifierType) -> bool:
        if keyval == Gdk.KEY_Escape:
            self.destroy()
            return True
        return False

    def _on_destroy(self, window):
        try:
            if self.screenshot_path and os.path.exists(self.screenshot_path):
                os.remove(self.screenshot_path)
        except Exception:
            pass
        parent = self.get_transient_for()
        if parent:
            parent.present()
