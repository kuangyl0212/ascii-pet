"""Pytest tests for Windows tray menu configuration and command dispatch.

Covers TDD for adding '隐藏窗口' (Hide Window) to the tray menu:
  - build_tray_menu_items(autostart_enabled): pure function returning menu items
  - PetWindow.dispatch_tray_command(cmd): command dispatcher returning bool

Uses importlib because the module filename 'ascii-pet-win.py' contains a hyphen.
"""

import sys
import os
import importlib.util
from unittest.mock import MagicMock, patch

import pytest

import i18n

# Load ascii-pet-win.py via importlib (hyphen in filename prevents normal import)
_MOD_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ascii-pet-win.py')
_spec = importlib.util.spec_from_file_location('ascii_pet_win', _MOD_PATH)
ascii_pet_win = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ascii_pet_win)

PetWindow = ascii_pet_win.PetWindow

# Re-export constants for test readability
ID_TRAY_SHOW = ascii_pet_win.ID_TRAY_SHOW
ID_TRAY_HIDE = ascii_pet_win.ID_TRAY_HIDE
ID_TRAY_AUTOSTART = ascii_pet_win.ID_TRAY_AUTOSTART
ID_TRAY_QUIT = ascii_pet_win.ID_TRAY_QUIT
MF_STRING = ascii_pet_win.MF_STRING
MF_SEPARATOR = ascii_pet_win.MF_SEPARATOR
MF_CHECKED = ascii_pet_win.MF_CHECKED


@pytest.fixture
def pet_window():
    """提供不创建真实窗口的 PetWindow 实例（game 为 MagicMock）。"""
    game = MagicMock()
    return PetWindow(game)


# ─── Task 1: build_tray_menu_items 配置测试 ─────────────────────────────────

class TestBuildTrayMenuItems:
    """验证托盘菜单项配置纯函数。"""

    def test_tray_menu_items_autostart_disabled(self):
        """自启动未启用时，菜单应包含显示/隐藏/自启动/退出四项及两个分隔符。"""
        i18n.set_language('zh')
        items = ascii_pet_win.build_tray_menu_items(autostart_enabled=False)
        # 6 项: 显示, 隐藏, 分隔符, 自启动, 分隔符, 退出
        assert len(items) == 6
        # 第一项: 显示窗口
        assert items[0] == (ID_TRAY_SHOW, '显示窗口', MF_STRING)
        # 第二项: 隐藏窗口
        assert items[1] == (ID_TRAY_HIDE, '隐藏窗口', MF_STRING)
        # 第三项: 分隔符
        assert items[2][1] is None or items[2] == (0, None, MF_SEPARATOR)
        # 第四项: 开机自启动（未勾选）
        assert items[3] == (ID_TRAY_AUTOSTART, '开机自启动', MF_STRING)
        # 第五项: 分隔符
        assert items[4][1] is None or items[4] == (0, None, MF_SEPARATOR)
        # 第六项: 退出
        assert items[5] == (ID_TRAY_QUIT, '退出', MF_STRING)

    def test_tray_menu_items_autostart_enabled(self):
        """自启动已启用时，自启动项应带 MF_CHECKED 标志，其余不变。"""
        i18n.set_language('zh')
        items = ascii_pet_win.build_tray_menu_items(autostart_enabled=True)
        assert len(items) == 6
        # 隐藏窗口项不变
        assert items[1] == (ID_TRAY_HIDE, '隐藏窗口', MF_STRING)
        # 自启动项带勾选
        autostart_item = items[3]
        assert autostart_item[0] == ID_TRAY_AUTOSTART
        assert autostart_item[2] & MF_CHECKED == MF_CHECKED

    def test_tray_menu_items_english(self):
        """English language should return English labels."""
        i18n.set_language('en')
        items = ascii_pet_win.build_tray_menu_items(autostart_enabled=False)
        assert items[0] == (ID_TRAY_SHOW, 'Show Window', MF_STRING)
        assert items[1] == (ID_TRAY_HIDE, 'Hide Window', MF_STRING)
        assert items[3] == (ID_TRAY_AUTOSTART, 'Auto-start on Boot', MF_STRING)
        assert items[5] == (ID_TRAY_QUIT, 'Quit', MF_STRING)

    def test_tray_hide_id_is_2004(self):
        """ID_TRAY_HIDE 应为 2004，与现有常量不冲突。"""
        assert ID_TRAY_HIDE == 2004
        assert ID_TRAY_HIDE != ID_TRAY_SHOW
        assert ID_TRAY_HIDE != ID_TRAY_QUIT
        assert ID_TRAY_HIDE != ID_TRAY_AUTOSTART


# ─── Task 3: dispatch_tray_command 命令分发测试 ──────────────────────────────

class TestDispatchTrayCommand:
    """验证托盘菜单命令分发。"""

    def test_dispatch_hide_calls_minimize(self, pet_window):
        """分发 ID_TRAY_HIDE 应调用 minimize_to_tray() 一次并返回 True。"""
        with patch.object(pet_window, 'minimize_to_tray') as mock_minimize:
            result = pet_window.dispatch_tray_command(ID_TRAY_HIDE)
        assert result is True
        mock_minimize.assert_called_once_with()

    def test_dispatch_unknown_returns_false(self, pet_window):
        """分发未知命令应返回 False，不触发任何窗口操作。"""
        with patch.object(pet_window, 'minimize_to_tray') as mock_minimize, \
             patch.object(pet_window, 'restore_from_tray') as mock_restore:
            result = pet_window.dispatch_tray_command(9999)
        assert result is False
        mock_minimize.assert_not_called()
        mock_restore.assert_not_called()

    def test_dispatch_show_uses_valid_sw_command(self, pet_window):
        """分发 ID_TRAY_SHOW 应使用有效的 SW_* nCmdShow 值（5=SW_SHOW 或 9=SW_RESTORE）。

        SC_RESTORE=0xF120 是 WM_SYSCOMMAND 的 wParam，不是 ShowWindow 的有效 nCmdShow，
        窗口被 SW_HIDE 隐藏后无法用该值恢复显示。
        """
        pet_window.hwnd = 12345  # fake hwnd
        with patch.object(ascii_pet_win.user32, 'ShowWindow') as mock_show, \
             patch.object(ascii_pet_win.user32, 'SetForegroundWindow'):
            result = pet_window.dispatch_tray_command(ID_TRAY_SHOW)
        assert result is True
        mock_show.assert_called_once()
        ncmdshow = mock_show.call_args[0][1]
        assert ncmdshow in (1, 5, 9), (
            f'无效的 nCmdShow: {ncmdshow} (应为 SW_SHOWNORMAL=1/SW_SHOW=5/SW_RESTORE=9，'
            f'而非 SC_RESTORE=0xF120)'
        )

    def test_restore_from_tray_uses_valid_sw_command(self, pet_window):
        """restore_from_tray() 也应使用有效的 SW_* nCmdShow 值。"""
        pet_window.hwnd = 12345
        with patch.object(ascii_pet_win.user32, 'ShowWindow') as mock_show, \
             patch.object(ascii_pet_win.user32, 'SetForegroundWindow'):
            pet_window.restore_from_tray()
        mock_show.assert_called_once()
        ncmdshow = mock_show.call_args[0][1]
        assert ncmdshow in (1, 5, 9), (
            f'无效的 nCmdShow: {ncmdshow} (应为 SW_SHOWNORMAL=1/SW_SHOW=5/SW_RESTORE=9)'
        )

