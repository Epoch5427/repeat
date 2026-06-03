<p align="center">
  <img src="https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/repeat/main/data/icons/io.github.YOUR_GITHUB_USERNAME.repeat.svg" width="128" height="128" alt="Repeat Icon">
</p>

<h1 align="center">Repeat</h1>

<p align="center">
  <strong>A modern, high-precision, Wayland-first autoclicker and macro sequencer for Linux.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/GTK-4-blue?logo=gnome&logoColor=white" alt="GTK4">
  <img src="https://img.shields.io/badge/Libadwaita-1-blue" alt="Libadwaita">
  <img src="https://img.shields.io/badge/License-GPLv3-green" alt="GPLv3 License">
</p>

---

## 📸 Screenshots

<p align="center">
  <img src="https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/repeat/main/screenshots/main.png" width="800" alt="Repeat Main Interface">
  <br>
  <em>The main mouse settings and timing configuration panel.</em>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/repeat/main/screenshots/recorder.png" width="500" alt="Repeat Macro Recorder Dialog">
  <br>
  <em>The interactive macro recorder captures raw physical delays dynamically.</em>
</p>

---

## ✨ Features

- **Mouse Emulation**: Left, middle, or right clicking with single or double-click triggers. Emulate clicks at your current cursor position or map exact target coordinates.
- **Keyboard Input**: Target specific keys with action modes like "Press and Release", "Hold Key down", or "Release Key".
- **Advanced Macro Sequencer**: 
  - Construct automated input chains mixing keys, coordinates, mouse clicks, and strings (`type:text`).
  - Includes an **Interactive Recorder** that measures the actual human delay between your physical keystrokes (e.g., `delay:120, ctrl+c, delay:450, v`).
- **Timing & Precision Engine**: 
  - Run clickers using "Delay" (milliseconds between clicks) or "Rate" (clicks per second, minute, or hour).
  - High-precision OS wait loop with spin-yielding keeps microsecond-level accuracy.
  - Option to randomize interval speeds slightly to emulate human interaction.
- **Strict Execution Limits**: Set limits based on overall loop iteration counts or strict time durations.
- **Wayland Global Hotkeys**: Utilizes the Desktop Shortcuts Portal to safely register a global toggle shortcut (**F8**) that functions in the background on Wayland without compromising system security.

---

## ⚠️ Wayland Host Prerequisites

Because Wayland enforces strict boundaries between applications, software cannot directly intercept or inject user input. Repeat solves this securely by utilizing kernel-level virtual hardware emulation via `/dev/uinput` to dispatch events.

If you are running on Wayland (or using the Flatpak version), you must grant your user account access to the host machine's `/dev/uinput` interface:

1. **Add yourself to the `input` group** on your host machine:
   ```bash
   sudo usermod -aG input $USER
   ```

2. **Add a udev rule** to allow members of the input group write access to `/dev/uinput`:
   ```bash
   echo 'KERNEL=="uinput", GROUP="input", MODE="0660"' | sudo tee /etc/udev/rules.d/99-uinput.rules
   ```

3. **Log out and log back in** (or reboot your system) for these group permission changes to take effect.

---

## Development & Building

Repeat is built using Python, GTK4, Libadwaita, and Meson. 

### Local Building with GNOME Builder
1. Install **GNOME Builder** from your software repository or Flathub.
2. Clone this repository and open the directory in Builder.
3. Click the **Run** button at the top to compile dependencies and launch the application.

### Building manually via Flatpak
If you want to compile the Flatpak manifest manually:
```bash
flatpak-builder --force-clean build-dir io.github.YOUR_GITHUB_USERNAME.repeat.json
flatpak-builder --run build-dir io.github.YOUR_GITHUB_USERNAME.repeat.json repeat
```

---

## License

Repeat is open-source software licensed under the **GPL-3.0-or-later** license. See the `LICENSE` file for more details.
```
