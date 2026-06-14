#!/usr/bin/env python3
"""ASCII Desktop Pet — Windows 浮动桌面宠物 (Win32 API + ctypes)"""

import os, sys, time, ctypes
from pathlib import Path
from ctypes import windll, c_int, c_uint, c_long, c_wchar_p, byref, sizeof, create_unicode_buffer
from ctypes import wintypes, POINTER, c_void_p, c_char_p, c_size_t, memmove, c_byte

from pet_core import (
    SPECIES, RARITY_STARS, STAT_NAMES, MOODS, ACHIEVEMENTS, MAX_PETS,
    render_sprite, render_face, render_frame, export_text,
    PetGame,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Win32 颜色映射
# ═══════════════════════════════════════════════════════════════════════════════

RARITY_RGB = {
    'common':    (128, 128, 128),
    'uncommon':  (0, 200, 0),
    'rare':      (0, 200, 200),
    'epic':      (200, 0, 200),
    'legendary': (255, 215, 0),
}
MOOD_RGB = {
    'happy':   (255, 215, 0),
    'normal':  (200, 200, 200),
    'sleepy':  (128, 128, 128),
    'hungry':  (255, 80, 80),
    'excited': (200, 0, 200),
}
COLOR_DIM   = (0, 220, 50)
COLOR_MSG   = (255, 215, 0)
COLOR_WHITE = (0, 255, 65)
COLOR_BAR_FILL = (0, 200, 0)
COLOR_BAR_EMPTY = (80, 80, 80)
COLOR_HOVER_BG = (25, 25, 45)

def rgb_to_colorref(r, g, b):
    return (b << 16) | (g << 8) | r

# ═══════════════════════════════════════════════════════════════════════════════
# Win32 渲染函数 — 返回 [(text, (R,G,B)), ...] 列表
# ═══════════════════════════════════════════════════════════════════════════════

def stat_bar_text(value, width=15):
    filled = round((value / 100) * width)
    return '█' * filled, '░' * (width - filled), str(value)

def render_compact_lines(bones, frame_idx, state):
    lines = render_frame(bones, frame_idx, state.get('mood','normal'))
    return [(l, COLOR_WHITE) for l in lines]

def render_expanded_lines(state, bones, frame_idx, show_help):
    color = RARITY_RGB[state['rarity']]
    stars = RARITY_STARS[state['rarity']]
    shiny_str = ' SHINY' if state['shiny'] else ''
    mood = MOODS[state['mood']]
    mood_color = MOOD_RGB[state['mood']]
    frame = render_frame(bones, frame_idx, state.get('mood','normal'))

    lines = []
    lines.append((f'{state["name"]} {stars}{shiny_str}', color))
    lines.append((f'{state["species"]}·{state["rarity"]} [{mood["emoji"]}]', mood_color))
    lines.append((f'Lv.{state["level"]} XP:{state["xp"]}/{state["level"]*100}', COLOR_DIM))
    if state.get('evolved'):
        lines.append(('★ Evolved', color))
    try:
        from weather import format_weather_line
        weather_line = format_weather_line(state.get('weather'))
        if weather_line:
            lines.append((weather_line, COLOR_DIM))
    except ImportError:
        pass
    for row in frame:
        lines.append((f' {row}', COLOR_WHITE))
    for s in STAT_NAMES:
        v = state['stats'][s]
        filled, empty, val = stat_bar_text(v, 15)
        lines.append((f'{s[:4]}', COLOR_DIM, filled, COLOR_BAR_FILL, empty, COLOR_BAR_EMPTY, f' {val}', COLOR_WHITE))
    if show_help:
        lines.append(('[f]feed [p]play [s]sleep [w]adopt [b]prev [n]next [t]stats [a]achieve [u]items [e]export [Enter]compact [q]quit', COLOR_DIM))
    return lines

def render_stats_lines(state, bones, frame_idx, pet_idx, pet_count):
    color = RARITY_RGB[state['rarity']]
    frame = render_frame(bones, frame_idx, state.get('mood','normal'))
    from datetime import datetime
    created = datetime.fromisoformat(state['created_at'])
    days = (datetime.now() - created).days
    hours = (datetime.now() - created).total_seconds() / 3600
    evo = ' ★Evolved' if state.get('evolved') else ''

    lines = []
    lines.append((f'Stats for {state["name"]}', color))
    lines.append((f'Species: {state["species"]}', COLOR_DIM))
    lines.append((f'Face: {render_face(bones)}', COLOR_DIM))
    lines.append((f'Eye: {state["eye"]}', COLOR_DIM))
    lines.append((f'Hat: {state["hat"]}', COLOR_DIM))
    lines.append((f'Pet: {pet_idx+1}/{pet_count}{evo}', COLOR_DIM))
    lines.append(('', COLOR_DIM))
    for row in frame:
        lines.append((f' {row}', COLOR_WHITE))
    lines.append(('', COLOR_DIM))
    lines.append(('--- Activity ---', COLOR_DIM))
    lines.append((f'  Days adopted:  {days}', COLOR_DIM))
    lines.append((f'  Hours online: {hours:.1f}', COLOR_DIM))
    lines.append((f'  Feed count:   {state.get("feed_count",0)}', COLOR_DIM))
    lines.append((f'  Play count:   {state.get("play_count",0)}', COLOR_DIM))
    lines.append((f'  Sleep count:  {state.get("sleep_count",0)}', COLOR_DIM))
    lines.append((f'  Total acts:   {state["total_interactions"]}', COLOR_DIM))
    lines.append(('', COLOR_DIM))
    lines.append(('--- Growth ---', COLOR_DIM))
    lines.append((f'  Level: {state["level"]}  XP: {state["xp"]}/{state["level"]*100}', COLOR_DIM))
    lines.append((f'  Rarity: {state["rarity"]}  Shiny: {"Yes" if state["shiny"] else "No"}', COLOR_DIM))
    return lines

def render_achievements_lines(state, bones):
    color = RARITY_RGB[state['rarity']]
    unlocked = state.get('achievements', [])
    lines = []
    lines.append((f'Achievements for {state["name"]}', color))
    lines.append((f'{len(unlocked)}/{len(ACHIEVEMENTS)} unlocked', COLOR_DIM))
    lines.append(('', COLOR_DIM))
    for aid, ach in ACHIEVEMENTS.items():
        if aid in unlocked:
            lines.append((f'  {ach["icon"]} {ach["name"]}', color))
        else:
            lines.append(('  ??? Locked', COLOR_DIM))
    lines.append(('', COLOR_DIM))
    return lines

def render_items_lines(game):
    from pet_core import ITEMS, MAX_INVENTORY
    inv_list = game.get_inventory_list()
    total = sum(game.pets_data.get('inventory', {}).values())
    lines = [(f'Inventory ({total}/{MAX_INVENTORY})', COLOR_WHITE)]
    lines.append(('Select item [1-7] or [c]cancel', COLOR_DIM))
    lines.append(('', COLOR_DIM))
    if not inv_list:
        lines.append(('  Empty — items drop from random events', COLOR_DIM))
    else:
        for i, (iid, name, icon, count, desc) in enumerate(inv_list):
            lines.append((f'  {i+1}  {icon} {name} x{count}  {desc}', COLOR_WHITE))
    return lines

def render_release_lines(game):
    pets = game.get_release_list()
    lines = []
    lines.append(('Select a pet to release:', (255, 80, 80)))
    lines.append((f'Max {MAX_PETS} pets. Choose 1-3, or [c]cancel', COLOR_DIM))
    lines.append(('', COLOR_DIM))
    for idx, name, species, rarity in pets:
        color = RARITY_RGB[rarity]
        stars = RARITY_STARS[rarity]
        lines.append((f'  {idx}  {name} {species}·{rarity} {stars}', color))
    lines.append(('', COLOR_DIM))
    lines.append(('[1-3]select [c]cancel', COLOR_DIM))
    return lines

def render_death_lines(game):
    frame = render_frame(game.bones, game.frame_idx, 'normal')
    lines = []
    lines.append(('Your pet has died...', (255, 50, 50)))
    lines.append(('', COLOR_DIM))
    for row in frame:
        lines.append((f'  {row}', (100, 100, 100)))
    lines.append(('', COLOR_DIM))
    lines.append(('[f]feed, [p]play, or [s]sleep to revive', (255, 50, 50)))
    return lines

# ═══════════════════════════════════════════════════════════════════════════════
# Win32 剪贴板导出
# ═══════════════════════════════════════════════════════════════════════════════

def export_to_clipboard(text):
    CF_UNICODETEXT = 13
    kernel32 = windll.kernel32
    user32 = windll.user32
    if not user32.OpenClipboard(0): return False
    user32.EmptyClipboard()
    data = text.encode('utf-16-le') + b'\x00\x00'
    h = kernel32.GlobalAlloc(0x0042, len(data))
    p = kernel32.GlobalLock(h)
    memmove(p, data, len(data))
    kernel32.GlobalUnlock(h)
    user32.SetClipboardData(CF_UNICODETEXT, h)
    user32.CloseClipboard()
    return True

# ═══════════════════════════════════════════════════════════════════════════════
# Win32 常量
# ═══════════════════════════════════════════════════════════════════════════════

WS_POPUP       = 0x80000000
WS_VISIBLE     = 0x10000000
WS_EX_TOPMOST  = 0x00000008
WS_EX_LAYERED  = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW  = 0x00040000
LWA_COLORKEY   = 0x00000001
LWA_ALPHA      = 0x00000002

WM_PAINT       = 0x000F
WM_TIMER       = 0x0113
WM_CHAR        = 0x0102
WM_KEYDOWN     = 0x0100
WM_DESTROY     = 0x0002
WM_NCHITTEST   = 0x0084
WM_ERASEBKGND  = 0x0014
WM_LBUTTONDOWN = 0x0201
WM_NCLBUTTONDOWN = 0x00A1
WM_MOUSEMOVE   = 0x0200
WM_MOUSELEAVE  = 0x02A3
WM_CONTEXTMENU = 0x007B
WM_COMMAND     = 0x0111
WM_RBUTTONDOWN = 0x0204
WM_SIZE        = 0x0005
WM_SYSCOMMAND  = 0x0112

SC_MINIMIZE    = 0xF020
SC_RESTORE     = 0xF120

HTCAPTION      = 2
TRANSPARENT    = 1
COLOR_WINDOW   = 5

# Tray icon constants
WM_TRAYICON    = 0x0400
NIF_ICON       = 0x00000002
NIF_MESSAGE    = 0x00000001
NIF_TIP        = 0x00000004
NIM_ADD        = 0x00000000
NIM_MODIFY     = 0x00000001
NIM_DELETE     = 0x00000002

ID_TRAY_SHOW   = 2001
ID_TRAY_QUIT   = 2002

ID_FEED        = 1001
ID_PLAY        = 1002
ID_SLEEP       = 1003
ID_ADOPT       = 1004
ID_PREV_PET    = 1005
ID_NEXT_PET    = 1006
ID_EXPORT      = 1007
ID_COMPACT     = 1008
ID_EXPANDED    = 1009
ID_STATS       = 1011
ID_ACHIEVE     = 1012
ID_QUIT        = 1013

MF_STRING     = 0x00000000
MF_SEPARATOR  = 0x00000800
MF_GRAYED     = 0x00000001
MF_CHECKED    = 0x00000008
TPM_RIGHTBUTTON = 0x0002
TPM_NONOTIFY   = 0x0080
TPM_RETURNCMD  = 0x0100

# ═══════════════════════════════════════════════════════════════════════════════
# Win32 窗口实现
# ═══════════════════════════════════════════════════════════════════════════════

FONT_SIZE = 14
CHAR_W = 9
CHAR_H = 18
PADDING = 8

LAYOUT_SIZES = {
    'compact':      (18, 7),
    'expanded':     (38, 22),
    'stats':        (44, 24),
    'achievements': (44, 20),
    'items':        (44, 16),
    'release':      (44, 14),
}

user32 = windll.user32
kernel32 = windll.kernel32
gdi32 = windll.gdi32

if not hasattr(wintypes, 'LRESULT'):
    wintypes.LRESULT = ctypes.c_ssize_t
if not hasattr(wintypes, 'WPARAM'):
    wintypes.WPARAM = ctypes.c_ssize_t
if not hasattr(wintypes, 'LPARAM'):
    wintypes.LPARAM = ctypes.c_ssize_t
if not hasattr(wintypes, 'COLORREF'):
    wintypes.COLORREF = wintypes.DWORD
if not hasattr(wintypes, 'HGDIOBJ'):
    wintypes.HGDIOBJ = wintypes.HANDLE
if not hasattr(wintypes, 'HBITMAP'):
    wintypes.HBITMAP = wintypes.HANDLE
if not hasattr(wintypes, 'HFONT'):
    wintypes.HFONT = wintypes.HANDLE
if not hasattr(wintypes, 'HBRUSH'):
    wintypes.HBRUSH = wintypes.HANDLE

class RECT(ctypes.Structure):
    _fields_ = [('left', c_long), ('top', c_long), ('right', c_long), ('bottom', c_long)]

class SIZE(ctypes.Structure):
    _fields_ = [('cx', c_long), ('cy', c_long)]

class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [
        ('hdc', wintypes.HDC), ('fErase', c_int),
        ('rcPaint_left', c_long), ('rcPaint_top', c_long),
        ('rcPaint_right', c_long), ('rcPaint_bottom', c_long),
        ('fRestore', c_int), ('fIncUpdate', c_int), ('rgbReserved', c_byte * 32),
    ]

class MSG(ctypes.Structure):
    _fields_ = [
        ('hwnd', wintypes.HWND), ('message', wintypes.UINT),
        ('wParam', wintypes.WPARAM), ('lParam', wintypes.LPARAM),
        ('time', wintypes.DWORD), ('pt_x', c_long), ('pt_y', c_long),
    ]

class LOGFONTW(ctypes.Structure):
    _fields_ = [
        ('lfHeight', c_long), ('lfWidth', c_long), ('lfEscapement', c_long),
        ('lfOrientation', c_long), ('lfWeight', c_long),
        ('lfItalic', c_byte), ('lfUnderline', c_byte), ('lfStrikeOut', c_byte),
        ('lfCharSet', c_byte), ('lfOutPrecision', c_byte),
        ('lfClipPrecision', c_byte), ('lfQuality', c_byte),
        ('lfPitchAndFamily', c_byte), ('lfFaceName', ctypes.c_wchar * 32),
    ]

class TRACKMOUSEEVENT(ctypes.Structure):
    _fields_ = [
        ('cbSize', wintypes.DWORD), ('dwFlags', wintypes.DWORD),
        ('hwndTrack', wintypes.HWND), ('dwHoverTime', wintypes.DWORD),
    ]

TME_LEAVE = 0x0002

WNDPROC = ctypes.CFUNCTYPE(wintypes.LRESULT, wintypes.HWND, wintypes.UINT,
                            wintypes.WPARAM, wintypes.LPARAM)

class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ('style', c_uint), ('lpfnWndProc', WNDPROC),
        ('cbClsExtra', c_int), ('cbWndExtra', c_int),
        ('hInstance', wintypes.HINSTANCE), ('hIcon', wintypes.HICON),
        ('hCursor', wintypes.HANDLE), ('hbrBackground', wintypes.HBRUSH),
        ('lpszMenuName', c_wchar_p), ('lpszClassName', c_wchar_p),
    ]

# NOTIFYICONDATAW for system tray
class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ('cbSize', wintypes.DWORD),
        ('hWnd', wintypes.HWND),
        ('uID', wintypes.UINT),
        ('uFlags', wintypes.UINT),
        ('uCallbackMessage', wintypes.UINT),
        ('hIcon', wintypes.HICON),
        ('szTip', ctypes.c_wchar * 128),
        ('dwState', wintypes.DWORD),
        ('dwStateMask', wintypes.DWORD),
        ('szInfo', ctypes.c_wchar * 256),
        ('uTimeoutOrVersion', wintypes.UINT),
        ('szInfoTitle', ctypes.c_wchar * 64),
        ('dwInfoFlags', wintypes.DWORD),
        ('guidItem', ctypes.c_byte * 16),
        ('hBalloonIcon', wintypes.HICON),
    ]

# Shell_NotifyIconW
shell32 = ctypes.windll.shell32
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL

# API signatures
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_ssize_t, ctypes.c_ssize_t]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_ssize_t, ctypes.c_ssize_t]
user32.SendMessageW.restype = ctypes.c_ssize_t
user32.TrackMouseEvent.argtypes = [ctypes.POINTER(TRACKMOUSEEVENT)]
user32.TrackMouseEvent.restype = wintypes.BOOL
user32.FillRect.argtypes = [wintypes.HDC, ctypes.POINTER(RECT), wintypes.HBRUSH]
user32.FillRect.restype = c_int
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.MoveWindow.argtypes = [wintypes.HWND, c_int, c_int, c_int, c_int, wintypes.BOOL]
user32.InvalidateRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT), wintypes.BOOL]
user32.BeginPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PAINTSTRUCT)]
user32.BeginPaint.restype = wintypes.HDC
user32.EndPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PAINTSTRUCT)]
gdi32.CreateSolidBrush.argtypes = [wintypes.COLORREF]
gdi32.CreateSolidBrush.restype = wintypes.HBRUSH
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, c_int, c_int]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.SetTextColor.argtypes = [wintypes.HDC, wintypes.COLORREF]
gdi32.SetBkMode.argtypes = [wintypes.HDC, c_int]
gdi32.TextOutW.argtypes = [wintypes.HDC, c_int, c_int, wintypes.LPCWSTR, c_int]
gdi32.TextOutW.restype = wintypes.BOOL
gdi32.GetTextExtentPoint32W.argtypes = [wintypes.HDC, wintypes.LPCWSTR, c_int, ctypes.POINTER(SIZE)]
gdi32.GetTextExtentPoint32W.restype = wintypes.BOOL
gdi32.BitBlt.argtypes = [wintypes.HDC, c_int, c_int, c_int, c_int, wintypes.HDC, c_int, c_int, wintypes.DWORD]
gdi32.CreateFontIndirectW.argtypes = [ctypes.POINTER(LOGFONTW)]
gdi32.CreateFontIndirectW.restype = wintypes.HFONT

class ICONINFO(ctypes.Structure):
    _fields_ = [
        ('fIcon', wintypes.BOOL),
        ('xHotspot', wintypes.DWORD),
        ('yHotspot', wintypes.DWORD),
        ('hbmMask', wintypes.HBITMAP),
        ('hbmColor', wintypes.HBITMAP),
    ]

user32.CreateIconIndirect.argtypes = [ctypes.POINTER(ICONINFO)]
user32.CreateIconIndirect.restype = wintypes.HICON
user32.CreatePopupMenu.argtypes = []
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_ssize_t, wintypes.LPCWSTR]
user32.AppendMenuW.restype = wintypes.BOOL
user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, c_int, c_int, c_int, wintypes.HWND, ctypes.POINTER(RECT)]
user32.TrackPopupMenu.restype = wintypes.BOOL
user32.DestroyMenu.argtypes = [wintypes.HMENU]
user32.DestroyMenu.restype = wintypes.BOOL


class PetWindow:
    """Win32 浮动宠物窗口"""

    def __init__(self, game):
        self.game = game
        self.hwnd = None
        self.hfont = None
        self.wndproc_callback = None
        self.win_w = 0
        self.win_h = 0
        self._window_pos = None
        self.hover = False
        self.tracking_mouse = False
        self.tray_icon_id = 1
        self.tray_added = False
        self._last_pet_time = 0

    def calc_window_size(self, mode):
        lines = self.get_render_lines()
        if not lines:
            cols, rows = LAYOUT_SIZES.get(mode, (38, 22))
            return cols * CHAR_W + PADDING * 2, rows * CHAR_H + PADDING * 2
        max_chars = 0
        for line in lines:
            total = 0
            if len(line) >= 4 and len(line) % 2 == 0:
                i = 0
                while i + 1 < len(line):
                    total += len(line[i]); i += 2
            else:
                total = len(line[0])
            if total > max_chars: max_chars = total
        return max_chars * CHAR_W + PADDING * 2 + 4, len(lines) * CHAR_H + PADDING * 2 + 4

    def get_window_pos(self):
        if not self.hwnd: return None
        rect = RECT()
        user32.GetWindowRect(self.hwnd, byref(rect))
        return rect.left, rect.top

    @staticmethod
    def _clamp_pos(px, py, pw, ph, sw, sh):
        return max(0, min(px, sw - pw)), max(0, min(py, sh - ph))

    def resize_window(self, mode):
        cur = self.get_window_pos()
        if cur: self._window_pos = cur
        w, h = self.calc_window_size(mode)
        self.win_w, self.win_h = w, h
        sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        if self._window_pos:
            x, y = self._clamp_pos(self._window_pos[0], self._window_pos[1], w, h, sw, sh)
        else:
            x, y = sw - w - 20, sh - h - 60
        user32.MoveWindow(self.hwnd, x, y, w, h, True)

    def _create_tray_icon(self):
        size = 16
        hdc_screen = user32.GetDC(0)
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, size, size)
        old_bmp = gdi32.SelectObject(hdc_mem, hbmp)

        bg = gdi32.CreateSolidBrush(rgb_to_colorref(0, 0, 0))
        user32.FillRect(hdc_mem, byref(RECT(0, 0, size, size)), bg)
        gdi32.DeleteObject(bg)

        green = rgb_to_colorref(0, 255, 65)
        dark_green = rgb_to_colorref(0, 180, 45)
        white = rgb_to_colorref(255, 255, 255)

        def pixel(x, y, color):
            brush = gdi32.CreateSolidBrush(color)
            user32.FillRect(hdc_mem, byref(RECT(x, y, x+1, y+1)), brush)
            gdi32.DeleteObject(brush)

        def rect(x1, y1, x2, y2, color):
            brush = gdi32.CreateSolidBrush(color)
            user32.FillRect(hdc_mem, byref(RECT(x1, y1, x2, y2)), brush)
            gdi32.DeleteObject(brush)

        # body (blob shape)
        rect(4, 3, 12, 5, green)
        rect(3, 5, 13, 11, green)
        rect(4, 11, 12, 13, green)

        # belly highlight
        rect(5, 6, 11, 10, dark_green)

        # eyes
        pixel(5, 6, white)
        pixel(10, 6, white)

        # mouth
        pixel(7, 9, white)
        pixel(8, 9, white)

        # Create mask bitmap
        hdc_mask = gdi32.CreateCompatibleDC(hdc_screen)
        hbmp_mask = gdi32.CreateCompatibleBitmap(hdc_screen, size, size)
        old_mask = gdi32.SelectObject(hdc_mask, hbmp_mask)
        mask_brush = gdi32.CreateSolidBrush(rgb_to_colorref(255, 255, 255))
        user32.FillRect(hdc_mask, byref(RECT(0, 0, size, size)), mask_brush)
        gdi32.DeleteObject(mask_brush)

        info = ICONINFO()
        info.fIcon = True
        info.xHotspot = 0
        info.yHotspot = 0
        info.hbmMask = hbmp_mask
        info.hbmColor = hbmp
        hicon = user32.CreateIconIndirect(byref(info))

        gdi32.SelectObject(hdc_mask, old_mask)
        gdi32.DeleteObject(hbmp_mask)
        gdi32.DeleteDC(hdc_mask)
        gdi32.SelectObject(hdc_mem, old_bmp)
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(0, hdc_screen)
        return hicon

    def add_tray_icon(self):
        if self.tray_added: return
        nid = NOTIFYICONDATAW()
        nid.cbSize = sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = self.tray_icon_id
        nid.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = self._create_tray_icon()
        nid.szTip = 'ASCII Pet'
        shell32.Shell_NotifyIconW(NIM_ADD, byref(nid))
        self.tray_added = True
        self._tray_nid = nid

    def remove_tray_icon(self):
        if not self.tray_added: return
        shell32.Shell_NotifyIconW(NIM_DELETE, byref(self._tray_nid))
        self.tray_added = False

    def show_tray_menu(self):
        class POINT(ctypes.Structure):
            _fields_ = [('x', c_long), ('y', c_long)]
        pt = POINT()
        user32.GetCursorPos(byref(pt))
        hmenu = user32.CreatePopupMenu()
        user32.AppendMenuW(hmenu, MF_STRING, ID_TRAY_SHOW, '显示窗口')
        user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(hmenu, MF_STRING, ID_TRAY_QUIT, '退出')
        cmd = user32.TrackPopupMenu(hmenu, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY, pt.x, pt.y, 0, self.hwnd, None)
        user32.DestroyMenu(hmenu)
        if cmd == ID_TRAY_SHOW:
            user32.ShowWindow(self.hwnd, SC_RESTORE)
            user32.SetForegroundWindow(self.hwnd)
        elif cmd == ID_TRAY_QUIT:
            user32.DestroyWindow(self.hwnd)

    def minimize_to_tray(self):
        user32.ShowWindow(self.hwnd, 0)

    def restore_from_tray(self):
        user32.ShowWindow(self.hwnd, SC_RESTORE)
        user32.SetForegroundWindow(self.hwnd)

    def create_window(self):
        hinstance = kernel32.GetModuleHandleW(None)
        self.wndproc_callback = WNDPROC(self.wnd_proc)

        wc = WNDCLASSW()
        wc.style = 0
        wc.lpfnWndProc = self.wndproc_callback
        wc.cbClsExtra = 0; wc.cbWndExtra = 0
        wc.hInstance = hinstance; wc.hIcon = 0
        wc.hCursor = user32.LoadCursorW(0, 32512)
        wc.hbrBackground = (COLOR_WINDOW + 1)
        wc.lpszMenuName = None; wc.lpszClassName = 'AsciiPetWin'
        user32.RegisterClassW(byref(wc))

        ex_style = WS_EX_TOPMOST | WS_EX_LAYERED | WS_EX_TOOLWINDOW
        style = WS_POPUP | WS_VISIBLE
        w, h = self.calc_window_size(self.game.mode)
        self.win_w, self.win_h = w, h
        sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        x, y = sw - w - 20, sh - h - 60

        self.hwnd = user32.CreateWindowExW(ex_style, 'AsciiPetWin', 'ASCII Pet', style,
                                            x, y, w, h, 0, 0, hinstance, None)
        if not self.hwnd:
            raise RuntimeError(f'CreateWindowExW failed: {kernel32.GetLastError()}')

        user32.SetLayeredWindowAttributes(self.hwnd, rgb_to_colorref(0, 0, 0), 0, LWA_COLORKEY)

        lf = LOGFONTW()
        lf.lfHeight = -FONT_SIZE; lf.lfWidth = 0
        lf.lfEscapement = 0; lf.lfOrientation = 0; lf.lfWeight = 400
        lf.lfItalic = 0; lf.lfUnderline = 0; lf.lfStrikeOut = 0
        lf.lfCharSet = 1; lf.lfOutPrecision = 0; lf.lfClipPrecision = 0
        lf.lfQuality = 3; lf.lfPitchAndFamily = 0x31; lf.lfFaceName = 'Consolas'
        self.hfont = gdi32.CreateFontIndirectW(byref(lf))

        user32.SetTimer(self.hwnd, 1, 500, None)
        user32.ShowWindow(self.hwnd, 5)
        user32.SetForegroundWindow(self.hwnd)
        user32.SetFocus(self.hwnd)
        self.add_tray_icon()

    def wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_PAINT:
            self.on_paint(hwnd); return 0
        elif msg == WM_TIMER:
            self.on_timer(); return 0
        elif msg == WM_CHAR:
            self.on_char(wparam); return 0
        elif msg == WM_TRAYICON:
            if lparam == WM_RBUTTONDOWN:
                self.show_tray_menu()
            elif lparam == WM_LBUTTONDOWN:
                self.restore_from_tray()
            return 0
        elif msg == WM_SIZE:
            if wparam == SC_MINIMIZE:
                self.add_tray_icon()
                self.minimize_to_tray()
                return 0
        elif msg == WM_NCHITTEST:
            return 1
        elif msg == WM_LBUTTONDOWN:
            user32.ReleaseCapture()
            user32.SendMessageW(hwnd, WM_NCLBUTTONDOWN, HTCAPTION, 0); return 0
        elif msg == WM_RBUTTONDOWN:
            self.show_context_menu(lparam); return 0
        elif msg == WM_COMMAND:
            self.execute_menu_command(wparam); return 0
        elif msg == WM_MOUSEMOVE:
            if not self.tracking_mouse:
                tme = TRACKMOUSEEVENT()
                tme.cbSize = sizeof(TRACKMOUSEEVENT); tme.dwFlags = TME_LEAVE
                tme.hwndTrack = hwnd; tme.dwHoverTime = 0
                user32.TrackMouseEvent(byref(tme)); self.tracking_mouse = True
            if not self.hover:
                self.hover = True
                now = time.time()
                if now - self._last_pet_time >= 1.0:
                    self._last_pet_time = now
                    self.game.handle_pet()
                user32.SetLayeredWindowAttributes(hwnd, rgb_to_colorref(0, 0, 0), 100, LWA_COLORKEY | LWA_ALPHA)
                user32.InvalidateRect(hwnd, None, False)
            return 0
        elif msg == WM_MOUSELEAVE:
            self.tracking_mouse = False
            if self.hover:
                self.hover = False
                user32.SetLayeredWindowAttributes(hwnd, rgb_to_colorref(0, 0, 0), 255, LWA_COLORKEY)
                user32.InvalidateRect(hwnd, None, False)
            return 0
        elif msg == WM_ERASEBKGND:
            hdc = int(wparam) & 0xFFFFFFFFFFFFFFFF
            rect = RECT()
            user32.GetClientRect(hwnd, byref(rect))
            bg_color = COLOR_HOVER_BG if self.hover else (0, 0, 0)
            brush = gdi32.CreateSolidBrush(rgb_to_colorref(*bg_color))
            user32.FillRect(hdc, byref(rect), brush)
            gdi32.DeleteObject(brush); return 1
        elif msg == WM_DESTROY:
            self.remove_tray_icon()
            user32.KillTimer(hwnd, 1)
            if self.hfont: gdi32.DeleteObject(self.hfont)
            user32.PostQuitMessage(0); return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def on_timer(self):
        msg, msg_time = self.game.tick()
        if msg: self.game.message = msg; self.game.message_time = msg_time
        user32.InvalidateRect(self.hwnd, None, False)

    def show_context_menu(self, lparam):
        class POINT(ctypes.Structure):
            _fields_ = [('x', c_long), ('y', c_long)]
        pt = POINT()
        user32.GetCursorPos(byref(pt))
        hmenu = user32.CreatePopupMenu()
        is_compact = self.game.mode == 'compact'
        user32.AppendMenuW(hmenu, MF_STRING, ID_FEED, '喂食 (F)')
        user32.AppendMenuW(hmenu, MF_STRING, ID_PLAY, '玩耍 (P)')
        user32.AppendMenuW(hmenu, MF_STRING, ID_SLEEP, '睡觉 (S)')
        user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(hmenu, MF_STRING, ID_ADOPT, '领养新宠物 (W)')
        user32.AppendMenuW(hmenu, MF_STRING | (MF_GRAYED if is_compact else 0), ID_EXPORT, '导出到剪贴板 (E)')
        user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(hmenu, MF_STRING, ID_PREV_PET, '上一个宠物 (B)')
        user32.AppendMenuW(hmenu, MF_STRING, ID_NEXT_PET, '下一个宠物 (N)')
        user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(hmenu, MF_STRING | (MF_CHECKED if self.game.mode == 'compact' else 0), ID_COMPACT, '紧凑模式')
        user32.AppendMenuW(hmenu, MF_STRING | (MF_CHECKED if self.game.mode == 'expanded' else 0), ID_EXPANDED, '展开模式')
        user32.AppendMenuW(hmenu, MF_STRING | (MF_CHECKED if self.game.mode == 'stats' else 0), ID_STATS, '属性面板 (T)')
        user32.AppendMenuW(hmenu, MF_STRING | (MF_CHECKED if self.game.mode == 'achievements' else 0), ID_ACHIEVE, '成就面板 (A)')
        user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(hmenu, MF_STRING, ID_QUIT, '退出 (Q)')
        cmd = user32.TrackPopupMenu(hmenu, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY, pt.x, pt.y, 0, self.hwnd, None)
        user32.DestroyMenu(hmenu)
        if cmd: self.execute_menu_command(cmd)

    def execute_menu_command(self, cmd):
        now = time.time()
        if cmd == ID_FEED:
            msg, anim = self.game.handle_action('feed')
            self.game.message = msg; self.game.message_time = now
            if anim: self.game.anim_end = now + 1.5; self.game.anim_frames = __import__('pet_core').ANIMATIONS[anim]
        elif cmd == ID_PLAY:
            msg, anim = self.game.handle_action('play')
            self.game.message = msg; self.game.message_time = now
            if anim: self.game.anim_end = now + 1.5; self.game.anim_frames = __import__('pet_core').ANIMATIONS[anim]
        elif cmd == ID_SLEEP:
            msg, anim = self.game.handle_action('sleep')
            self.game.message = msg; self.game.message_time = now
            if anim: self.game.anim_end = now + 1.5; self.game.anim_frames = __import__('pet_core').ANIMATIONS[anim]
        elif cmd == ID_ADOPT:
            msg = self.game.adopt_pet()
            self.game.message = msg; self.game.message_time = now
        elif cmd == ID_EXPORT and self.game.mode != 'compact':
            text = export_text(self.game.state, self.game.bones, self.game.frame_idx)
            if export_to_clipboard(text):
                self.game.message = 'Copied to clipboard!'
            else:
                self.game.message = 'Failed to copy'
            self.game.message_time = now
        elif cmd == ID_PREV_PET:
            if len(self.game.pets_data['pets']) > 1:
                self.game.message = self.game.switch_pet(-1)
                self.game.message_time = now
        elif cmd == ID_NEXT_PET:
            self.game.message = self.game.switch_pet(1)
            self.game.message_time = now
        elif cmd == ID_COMPACT:
            self.game.mode = 'compact'; self.game.show_help = False; self.resize_window(self.game.mode)
        elif cmd == ID_EXPANDED:
            self.game.mode = 'expanded'; self.game.show_help = False; self.resize_window(self.game.mode)
        elif cmd == ID_STATS:
            self.game.mode = 'stats'; self.resize_window(self.game.mode)
        elif cmd == ID_ACHIEVE:
            self.game.mode = 'achievements'; self.resize_window(self.game.mode)
        elif cmd == ID_QUIT:
            user32.DestroyWindow(self.hwnd); return
        user32.InvalidateRect(self.hwnd, None, False)

    def on_char(self, wparam):
        ch = chr(wparam)
        atype, detail = self.game.handle_key(ch)
        if atype == 'quit':
            user32.DestroyWindow(self.hwnd); return
        if atype == 'mode_change':
            self.resize_window(self.game.mode)
        user32.InvalidateRect(self.hwnd, None, False)

    def get_render_lines(self):
        g = self.game
        if g.state.get('is_dead'):
            lines = render_death_lines(g)
        elif g.mode == 'compact':
            lines = render_compact_lines(g.bones, g.frame_idx, g.state)
        elif g.mode == 'expanded':
            lines = render_expanded_lines(g.state, g.bones, g.frame_idx, g.show_help)
        elif g.mode == 'stats':
            lines = render_stats_lines(g.state, g.bones, g.frame_idx, g.pet_idx, len(g.pets_data['pets']))
        elif g.mode == 'achievements':
            lines = render_achievements_lines(g.state, g.bones)
        elif g.mode == 'items':
            lines = render_items_lines(g)
        elif g.mode == 'release':
            lines = render_release_lines(g)
        else:
            lines = render_compact_lines(g.bones, g.frame_idx, g.state)
        if g.message and (g.warning_active or time.time() - g.message_time < 2):
            lines.append((f'  {g.message}', COLOR_MSG))
        if g.anim_end and time.time() < g.anim_end:
            g.anim_idx = int((time.time() * 6) % len(g.anim_frames))
            lines.append((f'  {g.anim_frames[g.anim_idx]}', COLOR_MSG))
        elif g.anim_end and time.time() >= g.anim_end:
            g.anim_end = 0
        return lines

    def on_paint(self, hwnd):
        ps = PAINTSTRUCT()
        hdc = user32.BeginPaint(hwnd, byref(ps))
        lines = self.get_render_lines()
        new_w, new_h = self.calc_window_size(self.game.mode)
        if new_w != self.win_w or new_h != self.win_h:
            cur = self.get_window_pos()
            if cur: self._window_pos = cur
            self.win_w, self.win_h = new_w, new_h
            sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
            if self._window_pos:
                x, y = self._clamp_pos(self._window_pos[0], self._window_pos[1], new_w, new_h, sw, sh)
            else:
                x, y = sw - new_w - 20, sh - new_h - 60
            user32.MoveWindow(hwnd, x, y, new_w, new_h, True)
        rect = RECT()
        user32.GetClientRect(hwnd, byref(rect))
        width, height = rect.right - rect.left, rect.bottom - rect.top
        memdc = gdi32.CreateCompatibleDC(hdc)
        hbitmap = gdi32.CreateCompatibleBitmap(hdc, width, height)
        old_bmp = gdi32.SelectObject(memdc, hbitmap)
        bg_color = COLOR_HOVER_BG if self.hover else (0, 0, 0)
        bg_brush = gdi32.CreateSolidBrush(rgb_to_colorref(*bg_color))
        user32.FillRect(memdc, byref(rect), bg_brush)
        gdi32.DeleteObject(bg_brush)
        old_font = gdi32.SelectObject(memdc, self.hfont)
        gdi32.SetBkMode(memdc, TRANSPARENT)
        y = PADDING
        for line in lines:
            x = PADDING
            if len(line) >= 4 and len(line) % 2 == 0:
                i = 0
                while i + 1 < len(line):
                    text, color = line[i], line[i + 1]
                    gdi32.SetTextColor(memdc, rgb_to_colorref(*color))
                    sz = SIZE()
                    gdi32.GetTextExtentPoint32W(memdc, text, len(text), byref(sz))
                    gdi32.TextOutW(memdc, x, y, text, len(text))
                    x += sz.cx; i += 2
            else:
                gdi32.SetTextColor(memdc, rgb_to_colorref(*line[1]))
                gdi32.TextOutW(memdc, x, y, line[0], len(line[0]))
            y += CHAR_H
        gdi32.BitBlt(hdc, 0, 0, width, height, memdc, 0, 0, 0x00CC0020)
        gdi32.SelectObject(memdc, old_font)
        gdi32.SelectObject(memdc, old_bmp)
        gdi32.DeleteObject(hbitmap)
        gdi32.DeleteDC(memdc)
        user32.EndPaint(hwnd, byref(ps))

    def run(self):
        self.create_window()
        msg = MSG()
        while user32.GetMessageW(byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(byref(msg))
            user32.DispatchMessageW(byref(msg))

# ═══════════════════════════════════════════════════════════════════════════════

def main():
    uid = os.environ.get('USERNAME', 'anon')
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg in ('--help', '-h'):
            print('  ascii-pet — Windows 浮动桌面宠物\n\n  Usage:\n'
                  '    ascii-pet-win.py              Start pet\n'
                  '    ascii-pet-win.py [username]   Specific username\n'
                  '    ascii-pet-win.py --all        Show all species\n'
                  '    ascii-pet-win.py --help       Help\n\n'
                  '  Compact mode: just the pet\n'
                  '  Expanded mode: full stats (Enter to toggle)\n'
                  '  Commands: f feed, p play, s sleep, w adopt, b prev, n next,\n'
                  '            t stats, a achieve, e export, h help, c compact, q quit')
            sys.exit(0)
        if arg == '--all':
            from pet_core import EVOLVED_BODIES
            all_species = SPECIES + list(EVOLVED_BODIES.keys())
            print(f'\n  All {len(all_species)} species:\n')
            for sp in all_species:
                fb = {'species':sp,'eye':'·','hat':'none','shiny':False,'stats':{},'rarity':'common'}
                print(f'  {sp}  {render_face(fb)}')
                for row in render_sprite(fb, 0): print(f'  {row}')
                print()
            sys.exit(0)
        uid = arg

    game = PetGame(uid)
    pet_win = PetWindow(game)
    pet_win.run()

if __name__ == '__main__':
    main()
