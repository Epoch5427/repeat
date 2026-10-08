from dataclasses import dataclass
from typing import List, Tuple, Optional

@dataclass(frozen=True)
class ExecutionConfig:
    active_mode: int              # 0: Mouse, 1: Keyboard, 2: Macro
    base_interval_ms: int
    randomize: bool
    spread_ms: int
    duty_cycle: int

    # Mouse Settings
    mouse_button: int             # ecodes.BTN_LEFT, etc.
    click_type_idx: int          # 0: Single, 1: Double
    custom_location_enabled: bool
    mouse_pos_x: int
    mouse_pos_y: int

    # Keyboard Settings
    all_codes: List[int]
    kb_action_type: int          # 0: Press/Release, 1: Hold, 2: Release

    # Macro Settings
    parsed_macro: List[Tuple]

    # Limits
    repeat_limit_enabled: bool
    repeat_count: int
    time_limit_enabled: bool
    time_limit: int
