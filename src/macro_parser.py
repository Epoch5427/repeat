from evdev import ecodes

KEY_ALIASES = {
    'CTRL': 'LEFTCTRL', 'CONTROL': 'LEFTCTRL', 'ALT': 'LEFTALT',
    'SHIFT': 'LEFTSHIFT', 'WIN': 'LEFTMETA', 'SUPER': 'LEFTMETA', 'META': 'LEFTMETA',
    'RETURN': 'ENTER', 'BACKSPACE': 'BACKSPACE', 'ESCAPE': 'ESC',
    'PAGE_UP': 'PAGEUP', 'PAGE_DOWN': 'PAGEDOWN', 'SPACE': 'SPACE',
    'SUPER_L': 'LEFTMETA', 'SUPER_R': 'RIGHTMETA',
    'CONTROL_L': 'LEFTCTRL', 'CONTROL_R': 'RIGHTCTRL',
    'ALT_L': 'LEFTALT', 'ALT_R': 'RIGHTALT',
    'SHIFT_L': 'LEFTSHIFT', 'SHIFT_R': 'RIGHTSHIFT',
    'CAPS_LOCK': 'CAPSLOCK', 'NUM_LOCK': 'NUMLOCK', 'SCROLL_LOCK': 'SCROLLLOCK',
    'PERIOD': 'DOT', 'COMMA': 'COMMA', 'SLASH': 'SLASH', 'BACKSLASH': 'BACKSLASH',
    'SEMICOLON': 'SEMICOLON', 'APOSTROPHE': 'APOSTROPHE', 'GRAVE': 'GRAVE',
    'MINUS': 'MINUS', 'EQUAL': 'EQUAL',
    'BRACKETLEFT': 'LEFTBRACE', 'BRACKETRIGHT': 'RIGHTBRACE'
}

def string_to_keycode(key_str: str):
    clean = key_str.strip().upper().replace("KP_", "KP")
    mapped = KEY_ALIASES.get(clean, clean)
    return getattr(ecodes, f"KEY_{mapped}", None)

def parse_macro_sequence(text: str) -> list:
    if not text:
        return []

    actions = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue

        low = part.lower()

        if low.startswith(("delay:", "sleep:")):
            chunks = low.split(":")
            if len(chunks) < 2 or not chunks[1]:
                raise ValueError(f"Invalid delay in '{part}'. Expected 'delay:ms'.")
            try:
                ms_val = float(chunks[1])
                if ms_val < 0:
                    raise ValueError()
                actions.append(('delay', ms_val / 1000.0))
            except ValueError:
                raise ValueError(f"Invalid delay '{part}'. Must be positive number.")
            continue

        if low.startswith("click:"):
            sub = low.split(":")
            if len(sub) < 2 or not sub[1]:
                raise ValueError(f"Invalid click format in '{part}'. Expected 'click:button'.")

            btn_map = {"left": ecodes.BTN_LEFT, "middle": ecodes.BTN_MIDDLE, "right": ecodes.BTN_RIGHT}
            code = btn_map.get(sub[1])
            if code is None:
                raise ValueError(f"Unknown mouse button '{sub[1]}' in '{part}'.")

            if len(sub) >= 4:
                try:
                    actions.append(('click_at', code, int(sub[2]), int(sub[3])))
                except ValueError:
                    raise ValueError(f"Invalid coordinates in '{part}'. Must be positive integers.")
            elif len(sub) == 3:
                raise ValueError(f"Missing Y coordinate in '{part}'. Expected 'click:button:X:Y'.")
            else:
                actions.append(('click', code))
            continue

        if low.startswith("type:"):
            if len(part) < 6:
                raise ValueError(f"Empty type sequence in '{part}'.")
            actions.append(('type', part[5:]))
            continue

        keys = part.split("+")
        modifiers, main_code = [], None
        for k in keys:
            clean_k = k.strip().lower()
            if not clean_k:
                raise ValueError(f"Empty key segment in '{part}'.")

            if clean_k in ('ctrl', 'control'):
                modifiers.append(ecodes.KEY_LEFTCTRL)
            elif clean_k == 'alt':
                modifiers.append(ecodes.KEY_LEFTALT)
            elif clean_k == 'shift':
                modifiers.append(ecodes.KEY_LEFTSHIFT)
            elif clean_k in ('super', 'win', 'meta'):
                modifiers.append(ecodes.KEY_LEFTMETA)
            else:
                code = string_to_keycode(clean_k)
                if code is None:
                    raise ValueError(f"Unknown key name '{k.strip()}' in '{part}'.")
                main_code = code

        if main_code is None and modifiers:
            main_code = modifiers.pop()

        if main_code is not None:
            actions.append(('combo', modifiers, main_code))
        else:
            raise ValueError(f"No valid key specified in '{part}'.")

    return actions
