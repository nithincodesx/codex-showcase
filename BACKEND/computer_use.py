import os
import sys
import time
import logging
import subprocess
import ctypes
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from typing import Optional
from PIL import Image
from livekit.agents import llm

logger = logging.getLogger("computer-use")

# Initialize user32 and gdi32 Windows APIs
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

# DPI awareness can be optionally set at runtime if interactive
# user32.SetProcessDPIAware()


SCREENSHOTS_DIR = Path(__file__).parent / "screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)

# --- Windows CTypes Structures for SendInput ---
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
INPUT_HARDWARE = 2

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))
    ]

class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUT_UNION)]

# Virtual key map for common desktop hotkeys
VK_MAP = {
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "space": 0x20,
    "backspace": 0x08,
    "delete": 0x2E,
    "escape": 0x1B,
    "esc": 0x1B,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "shift": 0x10,
    "win": 0x5B,
    "windows": 0x5B,
    "f1": 0x70,
    "f2": 0x71,
    "f3": 0x72,
    "f4": 0x73,
    "f5": 0x74,
    "f6": 0x75,
    "f7": 0x76,
    "f8": 0x77,
    "f9": 0x78,
    "f10": 0x79,
    "f11": 0x7A,
    "f12": 0x7B,
}

# Media & system virtual keys (Windows multimedia controls)
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3

def _get_active_window_title() -> str:
    hwnd = user32.GetForegroundWindow()
    length = user32.GetWindowTextLengthW(hwnd)
    if length > 0:
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        return buff.value
    return "Unknown Window"

def _get_cursor_pos() -> tuple[int, int]:
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

def _get_screen_dimensions() -> tuple[int, int]:
    w = user32.GetSystemMetrics(0)
    h = user32.GetSystemMetrics(1)
    return w, h

def _send_unicode_char(char: str):
    code = ord(char)
    inp_down = INPUT()
    inp_down.type = INPUT_KEYBOARD
    inp_down.union.ki.wVk = 0
    inp_down.union.ki.wScan = code
    inp_down.union.ki.dwFlags = KEYEVENTF_UNICODE
    
    inp_up = INPUT()
    inp_up.type = INPUT_KEYBOARD
    inp_up.union.ki.wVk = 0
    inp_up.union.ki.wScan = code
    inp_up.union.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
    
    inputs = (INPUT * 2)(inp_down, inp_up)
    user32.SendInput(2, inputs, ctypes.sizeof(INPUT))

def _press_vk_key(vk_code: int):
    # Key down
    inp_down = INPUT()
    inp_down.type = INPUT_KEYBOARD
    inp_down.union.ki.wVk = vk_code
    inp_down.union.ki.wScan = 0
    inp_down.union.ki.dwFlags = 0
    # Key up
    inp_up = INPUT()
    inp_up.type = INPUT_KEYBOARD
    inp_up.union.ki.wVk = vk_code
    inp_up.union.ki.wScan = 0
    inp_up.union.ki.dwFlags = KEYEVENTF_KEYUP

    inputs = (INPUT * 2)(inp_down, inp_up)
    user32.SendInput(2, inputs, ctypes.sizeof(INPUT))

def _capture_screen_to_file(filepath: Path) -> bool:
    """Captures the screen using PowerShell Graphics.CopyFromScreen or Pillow fallback."""
    ps_code = f"""
Add-Type -AssemblyName System.Windows.Forms,System.Drawing
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$graphics = [System.Drawing.Graphics]::FromImage($bmp)
$graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
$bmp.Save('{filepath.as_posix()}', [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bmp.Dispose()
"""
    try:
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_code], capture_output=True, text=True, timeout=10)
        if res.returncode == 0 and filepath.exists() and filepath.stat().st_size > 0:
            return True
    except Exception as e:
        logger.warning(f"PowerShell screenshot capture encountered error: {e}")

    # Fallback to Pillow ImageGrab
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab(all_screens=True)
        img.save(filepath, "PNG")
        return True
    except Exception as e:
        logger.error(f"Pillow ImageGrab failed: {e}")
        return False


# --- LLM Function Tools ---

@llm.function_tool
def take_screenshot(analyze: bool = True, prompt: str = "Describe what is on screen") -> str:
    """Take a full screenshot of the computer screen and optionally analyze its visual contents.
    
    Args:
        analyze: Whether to analyze the visual contents using AI vision.
        prompt: Question or prompt to guide the visual analysis of the screen.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"screenshot_{timestamp}.png"
    filepath = SCREENSHOTS_DIR / filename
    latest_path = SCREENSHOTS_DIR / "latest.png"

    success = _capture_screen_to_file(filepath)
    if not success:
        return "Failed to capture screenshot."

    # Also keep a copy at latest.png for easy reference
    try:
        import shutil
        shutil.copyfile(filepath, latest_path)
    except Exception:
        pass

    w, h = _get_screen_dimensions()
    active_win = _get_active_window_title()
    summary = f"Screenshot saved at {filepath.name} ({w}x{h} px). Active window: '{active_win}'."

    if analyze:
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if api_key:
            try:
                from google import genai
                client = genai.Client(api_key=api_key)
                img = Image.open(filepath)
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[img, prompt]
                )
                analysis_text = response.text.strip() if response.text else "No visual description generated."
                return f"{summary}\n\nVisual Screen Analysis:\n{analysis_text}"
            except Exception as e:
                logger.warning(f"Gemini vision analysis failed: {e}")
                return f"{summary}\n(Visual analysis unavailable: {e})"
    
    return summary


@llm.function_tool
def mouse_move(x: int, y: int) -> str:
    """Move the mouse cursor to the given (x, y) coordinates on the screen.
    
    Args:
        x: Horizontal coordinate in pixels (0 is left).
        y: Vertical coordinate in pixels (0 is top).
    """
    w, h = _get_screen_dimensions()
    target_x = max(0, min(x, w - 1))
    target_y = max(0, min(y, h - 1))
    user32.SetCursorPos(target_x, target_y)
    return f"Moved cursor to ({target_x}, {target_y})."


@llm.function_tool
def mouse_click(button: str = "left", click_type: str = "single", x: Optional[int] = None, y: Optional[int] = None) -> str:
    """Click the mouse button at the current cursor position or specified coordinates.
    
    Args:
        button: Which button to click: 'left', 'right', or 'middle'.
        click_type: Click style: 'single', 'double', or 'triple'.
        x: Optional horizontal coordinate to move to before clicking.
        y: Optional vertical coordinate to move to before clicking.
    """
    if x is not None and y is not None:
        mouse_move(x, y)
        time.sleep(0.05)

    btn = button.lower().strip()
    if btn == "right":
        down_flag, up_flag = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
    elif btn == "middle":
        down_flag, up_flag = MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP
    else:
        down_flag, up_flag = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP

    count = 1
    if click_type == "double":
        count = 2
    elif click_type == "triple":
        count = 3

    for i in range(count):
        user32.mouse_event(down_flag, 0, 0, 0, 0)
        time.sleep(0.02)
        user32.mouse_event(up_flag, 0, 0, 0, 0)
        if i < count - 1:
            time.sleep(0.05)

    cur_x, cur_y = _get_cursor_pos()
    return f"Executed {click_type} {btn} click at ({cur_x}, {cur_y})."


@llm.function_tool
def mouse_drag(start_x: int, start_y: int, end_x: int, end_y: int, button: str = "left") -> str:
    """Drag the mouse cursor from start coordinates to end coordinates.
    
    Args:
        start_x: Starting horizontal position.
        start_y: Starting vertical position.
        end_x: Ending horizontal position.
        end_y: Ending vertical position.
        button: Which button to hold: 'left' or 'right'.
    """
    mouse_move(start_x, start_y)
    time.sleep(0.05)

    down_flag = MOUSEEVENTF_RIGHTDOWN if button.lower() == "right" else MOUSEEVENTF_LEFTDOWN
    up_flag = MOUSEEVENTF_RIGHTUP if button.lower() == "right" else MOUSEEVENTF_LEFTUP

    user32.mouse_event(down_flag, 0, 0, 0, 0)
    time.sleep(0.05)

    steps = 15
    for i in range(1, steps + 1):
        inter_x = int(start_x + (end_x - start_x) * (i / steps))
        inter_y = int(start_y + (end_y - start_y) * (i / steps))
        user32.SetCursorPos(inter_x, inter_y)
        time.sleep(0.01)

    time.sleep(0.05)
    user32.mouse_event(up_flag, 0, 0, 0, 0)
    return f"Dragged mouse from ({start_x}, {start_y}) to ({end_x}, {end_y})."


@llm.function_tool
def mouse_scroll(amount: int = -3, direction: str = "down") -> str:
    """Scroll the mouse wheel up or down.
    
    Args:
        amount: Number of scroll ticks (default 3).
        direction: 'up' or 'down'.
    """
    ticks = abs(amount) if amount != 0 else 3
    delta = -120 * ticks if direction.lower() == "down" else 120 * ticks
    user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, delta, 0)
    return f"Scrolled mouse {direction} by {ticks} clicks."


@llm.function_tool
def type_text(text: str, press_enter: bool = False) -> str:
    """Type a string of text into the active window or focused input element.
    
    Args:
        text: The text string to type.
        press_enter: Whether to press Enter after typing.
    """
    for ch in text:
        _send_unicode_char(ch)
        time.sleep(0.005)

    if press_enter:
        time.sleep(0.05)
        _press_vk_key(VK_MAP["enter"])

    return f"Typed {len(text)} characters into active window (press_enter={press_enter})."


@llm.function_tool
def press_key(key: str) -> str:
    """Press a key or keyboard shortcut combination.
    
    Args:
        key: Key name or combination (e.g., 'enter', 'tab', 'escape', 'ctrl+c', 'ctrl+v', 'alt+tab', 'win', 'win+d').
    """
    parts = [p.strip().lower() for p in key.split("+") if p.strip()]
    if not parts:
        return "No key specified."

    # Identify modifier keys and primary key
    down_keys = []
    for part in parts:
        if part in VK_MAP:
            vk = VK_MAP[part]
        elif len(part) == 1 and part.isalnum():
            vk = ord(part.upper())
        else:
            vk = 0
        
        if vk:
            # Key down
            inp = INPUT()
            inp.type = INPUT_KEYBOARD
            inp.union.ki.wVk = vk
            inp.union.ki.dwFlags = 0
            user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
            down_keys.append(vk)
            time.sleep(0.02)

    time.sleep(0.05)

    # Key up in reverse order
    for vk in reversed(down_keys):
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.union.ki.wVk = vk
        inp.union.ki.dwFlags = KEYEVENTF_KEYUP
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        time.sleep(0.01)

    return f"Pressed key shortcut '{key}'."


@llm.function_tool
def open_app_or_url(target: str) -> str:
    """Open an application, file, or web URL.
    
    Args:
        target: Application name, executable path, or website URL (e.g., 'notepad', 'calc', 'chrome', 'https://youtube.com').
    """
    target = target.strip()
    try:
        if target.startswith("http://") or target.startswith("https://"):
            import webbrowser
            webbrowser.open(target)
            return f"Opened website: {target}"
        
        # Try os.startfile for Windows shell associations
        os.startfile(target)
        return f"Launched target: {target}"
    except Exception as e:
        try:
            subprocess.Popen(target, shell=True)
            return f"Started process: {target}"
        except Exception as sub_err:
            return f"Failed to open '{target}': {sub_err}"


@llm.function_tool
def get_screen_and_cursor_info() -> str:
    """Get the screen resolution, current mouse cursor coordinates, and active window title."""
    w, h = _get_screen_dimensions()
    cx, cy = _get_cursor_pos()
    title = _get_active_window_title()
    return f"Screen: {w}x{h} px | Cursor: ({cx}, {cy}) | Active Window: '{title}'"


@llm.function_tool
def run_terminal_command(command: str) -> str:
    """Execute a shell or PowerShell command on the computer and return the output.
    
    Args:
        command: Command string to execute.
    """
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=15,
        )
        out = proc.stdout.strip()
        err = proc.stderr.strip()
        result = []
        if out:
            result.append(out[:1500] + ("\n...[truncated]" if len(out) > 1500 else ""))
        if err:
            result.append(f"STDERR:\n{err[:500]}")
        if not result:
            result.append(f"Command executed with exit code {proc.returncode}.")
        return "\n".join(result)
    except subprocess.TimeoutExpired:
        return "Command timed out after 15 seconds."
    except Exception as e:
        return f"Failed to execute command: {e}"


@llm.function_tool
def media_control(action: str) -> str:
    """Control media playback using Windows multimedia transport keys.

    Works across Spotify, YouTube, and most media players.

    Args:
        action: One of 'play', 'pause', 'next', 'prev'/'previous', 'stop'.
    """
    mapping = {
        "play": VK_MEDIA_PLAY_PAUSE,
        "pause": VK_MEDIA_PLAY_PAUSE,
        "next": VK_MEDIA_NEXT_TRACK,
        "prev": VK_MEDIA_PREV_TRACK,
        "previous": VK_MEDIA_PREV_TRACK,
        "stop": VK_MEDIA_STOP,
    }
    vk = mapping.get(action.lower())
    if vk is None:
        return f"Unknown media action '{action}'."
    _press_vk_key(vk)
    return f"Media action '{action}' executed."


@llm.function_tool
def volume_control(action: str, value: int | None = None) -> str:
    """Control the system volume.

    Args:
        action: One of 'mute', 'unmute', 'up', 'down', 'set'.
        value: Target volume 0-100 when action='set' (approximate, ~2% per key press).
    """
    a = action.lower()
    if a == "mute":
        _press_vk_key(VK_VOLUME_MUTE)
        return "System volume muted."
    if a == "unmute":
        _press_vk_key(VK_VOLUME_MUTE)
        return "System volume unmuted."
    if a == "up":
        _press_vk_key(VK_VOLUME_UP)
        return "Volume increased."
    if a == "down":
        _press_vk_key(VK_VOLUME_DOWN)
        return "Volume decreased."
    if a == "set" and value is not None:
        target = max(0, min(int(value), 100))
        presses = max(1, target // 2)
        key = VK_VOLUME_UP if target >= 50 else VK_VOLUME_DOWN
        for _ in range(presses):
            _press_vk_key(key)
            time.sleep(0.02)
        return f"Volume set to approximately {target}%."
    return f"Unknown volume action '{action}'."


@llm.function_tool
def system_control(action: str) -> str:
    """Perform Windows system-level actions.

    Args:
        action: One of 'lock', 'sleep', 'restart', 'shutdown'.
    """
    a = action.lower()
    if a == "lock":
        user32.LockWorkStation()
        return "Workstation locked."
    if a == "sleep":
        subprocess.Popen(["rundll32", "powrprof.dll,SetSuspendState", "0,1,0"])
        return "System going to sleep."
    if a == "restart":
        subprocess.Popen(["shutdown", "/r", "/t", "10"])
        return "Restart scheduled in 10 seconds."
    if a == "shutdown":
        subprocess.Popen(["shutdown", "/s", "/t", "10"])
        return "Shutdown scheduled in 10 seconds."
    return f"Unknown system action '{action}'."


@llm.function_tool
def wait_seconds(seconds: float = 1.0) -> str:
    """Pause execution for a brief moment to allow UI animations or pages to load.
    
    Args:
        seconds: Duration in seconds to wait (maximum 10s).
    """
    dur = max(0.1, min(seconds, 10.0))
    time.sleep(dur)
    return f"Waited for {dur:.1f} seconds."


COMPUTER_USE_TOOLS = [
    take_screenshot,
    mouse_move,
    mouse_click,
    mouse_drag,
    mouse_scroll,
    type_text,
    press_key,
    open_app_or_url,
    get_screen_and_cursor_info,
    run_terminal_command,
    media_control,
    volume_control,
    system_control,
    wait_seconds,
]
