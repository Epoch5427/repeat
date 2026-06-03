<p align="center">
  <img src="data/icons/hicolor/scalable/apps/com.epoch.repeat.svg" width="128" height="128" alt="Repeat Icon">
</p>

<h1 align="center">Repeat</h1>

<p align="center">
  <strong>Wayland-First Autoclicker</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/GTK-4-blue?logo=gnome&logoColor=white" alt="GTK4">
  <img src="https://img.shields.io/badge/Libadwaita-1-blue" alt="Libadwaita">
  <img src="https://img.shields.io/badge/License-GPLv3-green" alt="GPLv3 License">
</p>

---

<p align="center">
  <img width="1020" height="750" alt="Light Mode" src="https://github.com/user-attachments/assets/3145d7c6-7884-43cb-a8e5-11f7c13f887f" />
  <br>
  <em>The main mouse settings and timing configuration panel.</em>
</p>

<p align="center">
  <img width="1020" height="750" alt="Dark Mode" src="https://github.com/user-attachments/assets/98f0fae3-6ff7-4904-8ecd-8b066c96606e" />
  <br>
  <em>The main keyboard settings and timing configuration panel.</em>
</p>

---

## Features

- **Mouse Emulation**: Left, middle, or right clicking with single or double-click triggers. Emulate clicks at your current cursor position or map exact target coordinates.
- **Modern GTK4 Interface**: The autoclicker comes stacked with a modern and simple GTK4 interface.
- **Keyboard Input**: Target specific keys with action modes like "Press and Release", "Hold Key down", or "Release Key".
- **Macro Sequencer**: 
  - Construct automated input chains mixing keys, coordinates, mouse clicks, and strings (`type:text`).
  - Includes an **Interactive Recorder** that measures the actual human delay between your physical keystrokes (e.g., `delay:120, ctrl+c, delay:450, v`).
- **Timing Engine**: 
  - Run clickers using "Delay" (milliseconds between clicks) or "Rate" (clicks per second, minute, or hour).
  - Option to randomize interval speeds slightly to emulate human interaction.
- **Execution Limits**: Set limits based on overall loop iteration counts or time durations.
- **Wayland Global Hotkeys**: Utilizes the Desktop Shortcuts Portal to safely register a global toggle shortcut (**F8**) that functions in the background on Wayland.

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
flatpak-builder --user --install builddir io.github.Epoch5427.repeat.json --force-clean
flatpak-builder --run builddir io.github.Epoch5427.repeat.json repeat
```

---

## License

Repeat is open-source software licensed under the **GPL-3.0-or-later** license. See the `LICENSE` file for more details.
