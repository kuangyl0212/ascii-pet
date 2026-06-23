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

from ascii_pet import i18n

# Load ascii-pet-win.py via importlib (hyphen in filename prevents normal import)
_MOD_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'bin', 'ascii-pet-win.py')
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
        """自启动未启用时，菜单应包含显示/隐藏/自启动/备份/恢复/语言/退出及分隔符。"""
        items = ascii_pet_win.build_tray_menu_items(autostart_enabled=False)
        # 9 项: Show, Hide, sep, Autostart, sep, Backup, Restore, sep, Quit
        assert len(items) == 9
        # 第一项: Show Window
        assert items[0] == (ID_TRAY_SHOW, 'Show Window', MF_STRING)
        # 第二项: Hide Window
        assert items[1] == (ID_TRAY_HIDE, 'Hide Window', MF_STRING)
        # 第三项: 分隔符
        assert items[2][1] is None or items[2] == (0, None, MF_SEPARATOR)
        # 第四项: Auto-start on Boot（未勾选）
        assert items[3] == (ID_TRAY_AUTOSTART, 'Auto-start on Boot', MF_STRING)
        # 第五项: 分隔符
        assert items[4][1] is None or items[4] == (0, None, MF_SEPARATOR)
        # 第六项: Manual Backup
        assert items[5] == (ascii_pet_win.ID_BACKUP, 'Manual Backup', MF_STRING)
        # 第七项: Restore Save
        assert items[6][0] == ascii_pet_win.ID_RESTORE
        # 第八项: 分隔符
        assert items[7][1] is None or items[7] == (0, None, MF_SEPARATOR)
        # 第九项: Quit
        assert items[8] == (ID_TRAY_QUIT, 'Quit', MF_STRING)

    def test_tray_menu_items_autostart_enabled(self):
        """自启动已启用时，自启动项应带 MF_CHECKED 标志，其余不变。"""
        items = ascii_pet_win.build_tray_menu_items(autostart_enabled=True)
        assert len(items) == 9
        # 隐藏窗口项不变
        assert items[1] == (ID_TRAY_HIDE, 'Hide Window', MF_STRING)
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
        assert items[5] == (ascii_pet_win.ID_BACKUP, 'Manual Backup', MF_STRING)
        assert items[8] == (ID_TRAY_QUIT, 'Quit', MF_STRING)

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
            result = pet_window.dispatch_tray_command(3000)
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


# ─── Task: 存档备份/恢复菜单功能测试 ─────────────────────────────────────────

ID_BACKUP = ascii_pet_win.ID_BACKUP
ID_RESTORE = ascii_pet_win.ID_RESTORE
ID_RESTORE_START = ascii_pet_win.ID_RESTORE_START
MF_GRAYED = ascii_pet_win.MF_GRAYED


class TestBuildTrayMenuItemsBackup:
    """验证 build_tray_menu_items 包含备份/恢复菜单项。"""

    def test_build_tray_menu_items_includes_backup(self):
        """build_tray_menu_items 应包含手动备份项。"""
        items = ascii_pet_win.build_tray_menu_items(autostart_enabled=False, has_backups=True)
        backup_items = [i for i in items if i[0] == ID_BACKUP]
        assert len(backup_items) == 1
        assert backup_items[0][1] == 'Manual Backup'
        assert backup_items[0][2] & MF_GRAYED == 0  # 不应灰色

    def test_build_tray_menu_items_restore_grayed_without_backups(self):
        """无备份时恢复存档项应为灰色。"""
        items = ascii_pet_win.build_tray_menu_items(autostart_enabled=False, has_backups=False)
        restore_items = [i for i in items if i[0] == ID_RESTORE]
        assert len(restore_items) == 1
        assert restore_items[0][2] & MF_GRAYED == MF_GRAYED

    def test_build_tray_menu_items_restore_enabled_with_backups(self):
        """有备份时恢复存档项应可点击。"""
        items = ascii_pet_win.build_tray_menu_items(autostart_enabled=False, has_backups=True)
        restore_items = [i for i in items if i[0] == ID_RESTORE]
        assert len(restore_items) == 1
        assert restore_items[0][2] & MF_GRAYED == 0


class TestDispatchBackupRestore:
    """验证备份/恢复命令分发。"""

    def test_dispatch_backup_creates_backup(self, pet_window):
        """分发 ID_BACKUP 应调用 create_backup 并设置消息。"""
        with patch('ascii_pet.core.create_backup') as mock_create:
            result = pet_window.dispatch_tray_command(ID_BACKUP)
        assert result is True
        mock_create.assert_called_once()
        assert pet_window.game.message == 'Backup successful'

    def test_dispatch_backup_passes_manual_type(self, pet_window):
        """分发 ID_BACKUP 应调用 create_backup 时传入 backup_type='manual'。"""
        with patch('ascii_pet.core.create_backup') as mock_create:
            pet_window.dispatch_tray_command(ID_BACKUP)
        mock_create.assert_called_once()
        args, kwargs = mock_create.call_args
        assert kwargs.get('backup_type') == 'manual' or \
               (len(args) >= 3 and args[2] == 'manual'), \
               f'create_backup 未传入 backup_type="manual", call_args={mock_create.call_args}'

    def test_execute_menu_backup_passes_manual_type(self, pet_window):
        """execute_menu_command 中 ID_BACKUP 也应传入 backup_type='manual'。"""
        with patch('ascii_pet.core.create_backup') as mock_create:
            pet_window.execute_menu_command(ID_BACKUP)
        mock_create.assert_called_once()
        args, kwargs = mock_create.call_args
        assert kwargs.get('backup_type') == 'manual' or \
               (len(args) >= 3 and args[2] == 'manual'), \
               f'create_backup 未传入 backup_type="manual", call_args={mock_create.call_args}'

    def test_dispatch_restore_reloads_game(self, pet_window):
        """分发 ID_RESTORE_START+N 应调用 restore_from_backup 并重新加载游戏。"""
        from datetime import datetime
        fake_dt = datetime(2026, 1, 15, 10, 30, 0)
        with patch('ascii_pet.core.list_backups', return_value=[('backup_20260115_103000.json', fake_dt, 'auto')]), \
             patch('ascii_pet.core.restore_from_backup', return_value=True) as mock_restore, \
             patch.object(pet_window, '_reload_game') as mock_reload:
            result = pet_window.dispatch_tray_command(ID_RESTORE_START)
        assert result is True
        mock_restore.assert_called_once()
        mock_reload.assert_called_once()
        assert pet_window.game.message == 'Restored from backup'


class TestBackupSubmenuLabels:
    """验证恢复子菜单标签格式：[Auto/Manual] YYYY-MM-DD HH:MM:SS"""

    def test_show_tray_menu_submenu_label_format(self, pet_window):
        """show_tray_menu 子菜单标签应包含类型标注和秒数。"""
        from datetime import datetime
        fake_auto = datetime(2026, 3, 10, 14, 5, 30)
        fake_manual = datetime(2026, 3, 11, 9, 0, 15)
        backups = [
            ('auto_backup.json', fake_auto, 'auto'),
            ('manual_backup.json', fake_manual, 'manual'),
        ]
        appended_labels = []

        def fake_append_menu(menu, flags, item_id, label):
            if label and isinstance(label, str) and (label.startswith('[Auto]') or label.startswith('[Manual]')):
                appended_labels.append(label)
            return True

        with patch('ascii_pet.core.list_backups', return_value=backups), \
             patch.object(ascii_pet_win.user32, 'GetCursorPos'), \
             patch.object(ascii_pet_win.user32, 'CreatePopupMenu', return_value=2), \
             patch.object(ascii_pet_win.user32, 'AppendMenuW', side_effect=fake_append_menu), \
             patch.object(ascii_pet_win.user32, 'TrackPopupMenu', return_value=0), \
             patch.object(ascii_pet_win.user32, 'DestroyMenu'), \
             patch.object(ascii_pet_win, 'is_autostart_enabled', return_value=False), \
             patch.object(ascii_pet_win, 'refresh_autostart_cache_sync'):
            pet_window.show_tray_menu()

        assert len(appended_labels) == 2
        assert appended_labels[0] == '[Auto] 2026-03-10 14:05:30'
        assert appended_labels[1] == '[Manual] 2026-03-11 09:00:15'

    def test_show_context_menu_submenu_label_format(self, pet_window):
        """show_context_menu 子菜单标签应包含类型标注和秒数。"""
        from datetime import datetime
        fake_auto = datetime(2026, 5, 20, 8, 30, 45)
        fake_manual = datetime(2026, 5, 21, 16, 0, 0)
        backups = [
            ('auto_backup.json', fake_auto, 'auto'),
            ('manual_backup.json', fake_manual, 'manual'),
        ]
        appended_labels = []

        def fake_append_menu(menu, flags, item_id, label):
            if label and isinstance(label, str) and (label.startswith('[Auto]') or label.startswith('[Manual]')):
                appended_labels.append(label)
            return True

        with patch('ascii_pet.core.list_backups', return_value=backups), \
             patch.object(ascii_pet_win.user32, 'GetCursorPos'), \
             patch.object(ascii_pet_win.user32, 'CreatePopupMenu', return_value=2), \
             patch.object(ascii_pet_win.user32, 'AppendMenuW', side_effect=fake_append_menu), \
             patch.object(ascii_pet_win.user32, 'TrackPopupMenu', return_value=0), \
             patch.object(ascii_pet_win.user32, 'DestroyMenu'), \
             patch.object(ascii_pet_win, 'is_autostart_enabled', return_value=False), \
             patch.object(ascii_pet_win, 'refresh_autostart_cache_sync'):
            pet_window.show_context_menu(lparam=0)

        assert len(appended_labels) == 2
        assert appended_labels[0] == '[Auto] 2026-05-20 08:30:45'
        assert appended_labels[1] == '[Manual] 2026-05-21 16:00:00'


class TestBackupRestoreIds:
    """验证新 ID 常量不与现有 ID 冲突。"""

    def test_backup_and_restore_ids_are_unique(self):
        """ID_BACKUP、ID_RESTORE、ID_RESTORE_START 不应与现有 ID 冲突。"""
        existing_ids = {
            ID_TRAY_SHOW, ID_TRAY_HIDE, ID_TRAY_AUTOSTART, ID_TRAY_QUIT,
            ascii_pet_win.ID_FEED, ascii_pet_win.ID_PLAY, ascii_pet_win.ID_SLEEP,
            ascii_pet_win.ID_ADOPT, ascii_pet_win.ID_PREV_PET, ascii_pet_win.ID_NEXT_PET,
            ascii_pet_win.ID_EXPORT, ascii_pet_win.ID_COMPACT, ascii_pet_win.ID_EXPANDED,
            ascii_pet_win.ID_STATS, ascii_pet_win.ID_ACHIEVE, ascii_pet_win.ID_ITEMS,
            ascii_pet_win.ID_LAN, ascii_pet_win.ID_QUIT,
        }
        assert ID_BACKUP not in existing_ids
        assert ID_RESTORE not in existing_ids
        assert ID_RESTORE_START not in existing_ids
        assert ID_BACKUP != ID_RESTORE
        assert ID_RESTORE_START > 4999  # 确保起始值足够大以容纳子菜单

