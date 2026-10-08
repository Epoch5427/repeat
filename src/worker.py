import time
import random
import threading
from typing import Callable
from .models import ExecutionConfig
from .emulator import InputEmulator

class ExecutionEngine:
    def __init__(self, emulator: InputEmulator):
        self.emulator = emulator
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._on_stop_cb: Callable[[str], None] | None = None

    def start(self, config: ExecutionConfig, on_stop_cb: Callable[[str], None]):
        self._stop_event.clear()
        self._on_stop_cb = on_stop_cb
        self._worker_thread = threading.Thread(
            target=self._run_loop,
            args=(config,),
            daemon=True
        )
        self._worker_thread.start()

    def stop(self):
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=0.2)

    def _calc_interval(self, config: ExecutionConfig) -> float:
        base = config.base_interval_ms
        if config.randomize:
            offset = random.randint(-config.spread_ms, config.spread_ms)
            base = max(1, base + offset)
        return base / 1000.0

    def _run_loop(self, config: ExecutionConfig):
        executions = 0
        start_time = time.perf_counter()
        next_time = time.perf_counter()

        while not self._stop_event.is_set():
            interval = self._calc_interval(config)

            self._dispatch_action(config)
            executions += 1

            elapsed = time.perf_counter() - start_time
            if config.repeat_limit_enabled and executions >= config.repeat_count:
                if self._on_stop_cb:
                    self._on_stop_cb(f"Completed {config.repeat_count} executions.")
                break

            if config.time_limit_enabled and elapsed >= config.time_limit:
                if self._on_stop_cb:
                    self._on_stop_cb(f"Reached time limit of {config.time_limit}s.")
                break

            next_time += interval
            sleep_time = next_time - time.perf_counter()

            if sleep_time > 0:
                if sleep_time > 0.001 and self._stop_event.wait(timeout=sleep_time - 0.0005):
                    return
                while time.perf_counter() < next_time:
                    if self._stop_event.is_set():
                        return
                    time.sleep(0)
            else:
                next_time = time.perf_counter()

    def _dispatch_action(self, config: ExecutionConfig):
        mode = config.active_mode

        if mode == 0:  # Mouse
            if config.custom_location_enabled:
                self.emulator.move_to(config.mouse_pos_x, config.mouse_pos_y)

            clicks = 2 if config.click_type_idx == 1 else 1
            hold = (config.base_interval_ms * (config.duty_cycle / 100.0)) / 1000.0

            for i in range(clicks):
                self.emulator.click(config.mouse_button, hold)
                if clicks > 1 and i < clicks - 1:
                    time.sleep(0.01)

        elif mode == 1:  # Keyboard
            if not config.all_codes:
                return
            if config.kb_action_type == 0:  # Press & Release
                hold = (config.base_interval_ms * (config.duty_cycle / 100.0)) / 1000.0
                self.emulator.write_keys(config.all_codes, 1)
                if hold > 0.0001:
                    time.sleep(hold)
                self.emulator.write_keys(config.all_codes[::-1], 0)
            elif config.kb_action_type == 1:  # Hold
                self.emulator.write_keys(config.all_codes, 1)
            elif config.kb_action_type == 2:  # Release
                self.emulator.write_keys(config.all_codes[::-1], 0)

        elif mode == 2:  # Macro
            for action in config.parsed_macro:
                if self._stop_event.is_set():
                    break
                kind = action[0]
                if kind == 'delay':
                    self._stop_event.wait(timeout=action[1])
                elif kind == 'click':
                    self.emulator.click(action[1], hold_time=0.01)
                elif kind == 'click_at':
                    self.emulator.move_to(action[2], action[3])
                    self.emulator.click(action[1], hold_time=0.01)
                elif kind == 'type':
                    for char in action[1]:
                        if self._stop_event.is_set():
                            break
                        self.emulator.type_char(char)
                        time.sleep(0.01)
                elif kind == 'combo':
                    mods, key = action[1], action[2]
                    self.emulator.write_keys(mods, 1)
                    self.emulator.click(key, hold_time=0.01)
                    self.emulator.write_keys(mods[::-1], 0)
