import time
from typing import Optional
from evdev import UInput, ecodes

CHAR_MAP = {
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

class InputEmulator:
    def __init__(self):
        self._ui: Optional[UInput] = None

    def initialize(self) -> bool:
        caps = {
            ecodes.EV_KEY: [ecodes.BTN_LEFT, ecodes.BTN_RIGHT, ecodes.BTN_MIDDLE] + list(range(1, 256)),
            ecodes.EV_REL: [ecodes.REL_X, ecodes.REL_Y]
        }
        try:
            self._ui = UInput(caps, name="Repeat-Virtual-Input")
            return True
        except Exception:
            try:
                caps[ecodes.EV_KEY] = [ecodes.BTN_LEFT, ecodes.BTN_RIGHT, ecodes.BTN_MIDDLE] + list(range(1, 128))
                self._ui = UInput(caps, name="Repeat-Virtual-Input")
                return True
            except Exception as e:
                print(f"[Emulator] Failed to init UInput: {e}", flush=True)
                self._ui = None
                return False

    @property
    def is_ready(self) -> bool:
        return self._ui is not None

    def close(self):
        if self._ui:
            try:
                self._ui.close()
            except Exception:
                pass
            self._ui = None

    def move_to(self, x: int, y: int):
        if not self._ui:
            return
        # Compensate for relative movement by pulling cursor to origin then offset
        self._ui.write(ecodes.EV_REL, ecodes.REL_X, -65535)
        self._ui.write(ecodes.EV_REL, ecodes.REL_Y, -65535)
        self._ui.syn()
        self._ui.write(ecodes.EV_REL, ecodes.REL_X, x)
        self._ui.write(ecodes.EV_REL, ecodes.REL_Y, y)
        self._ui.syn()

    def click(self, code: int, hold_time: float = 0.0):
        if not self._ui:
            return
        self._ui.write(ecodes.EV_KEY, code, 1)
        self._ui.syn()
        if hold_time > 0.0001:
            time.sleep(hold_time)
        self._ui.write(ecodes.EV_KEY, code, 0)
        self._ui.syn()

    def write_keys(self, codes: list, value: int):
        if not self._ui:
            return
        for c in codes:
            self._ui.write(ecodes.EV_KEY, c, value)
        self._ui.syn()

    def type_char(self, char: str):
        if not self._ui or char not in CHAR_MAP:
            return
        code, shift = CHAR_MAP[char]
        if shift:
            self._ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 1)
            self._ui.syn()

        self.click(code, hold_time=0.005)

        if shift:
            self._ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 0)
            self._ui.syn()
