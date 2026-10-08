import sys
import select
import threading
import ctypes
import gi

try:
    PR_SET_PDEATHSIG = 1
    SIGTERM = 15
    ctypes.CDLL(None).prctl(PR_SET_PDEATHSIG, SIGTERM)
except Exception:
    pass

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

try:
    gi.require_version('AyatanaAppIndicator3', '0.1')
    from gi.repository import AyatanaAppIndicator3 as AppIndicator
except ValueError:
    gi.require_version('AppIndicator3', '0.1')
    from gi.repository import AppIndicator3 as AppIndicator

def emit(cmd: str):
    print(cmd)
    sys.stdout.flush()

def watch_stdin():
    try:
        while True:
            r, _, _ = select.select([sys.stdin], [], [])
            if r and not sys.stdin.read(1):
                break
    except Exception:
        pass
    GLib.idle_add(Gtk.main_quit)

threading.Thread(target=watch_stdin, daemon=True).start()

indicator = AppIndicator.Indicator.new(
    "repeat_tray", "io.github.Epoch5427.repeat", AppIndicator.IndicatorCategory.APPLICATION_STATUS
)
indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)

menu = Gtk.Menu()
for label, cmd in [("Show Autoclicker", "show"), ("Toggle Start/Stop", "toggle"), ("Quit", "quit")]:
    item = Gtk.MenuItem(label=label)
    item.connect('activate', lambda _, c=cmd: emit(c))
    menu.append(item)

menu.show_all()
indicator.set_menu(menu)
Gtk.main()
