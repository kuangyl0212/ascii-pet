"""TDD tests for Linux version feature parity with Windows version.

Covers:
  - Bug fixes (weather import, animation cursor positioning)
  - Theme system
  - New render functions (build_lan_panel, build_lan_name_edit,
    build_battle_log, build_trade_confirm, build_restore)
  - Overlays (visitor pets, visit hint, battle log, trade confirm)
  - Keyboard shortcuts (B/V/;/'/A)
  - Main loop hooks (process_lan_queues, disable_lan on exit)

Uses importlib because the module filename 'ascii-pet' contains a hyphen.
"""

import os
import sys
import time
import queue
import importlib.util
import importlib.machinery
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from ascii_pet.core import PetGame
from ascii_pet import i18n

# Load bin/ascii-pet via importlib (hyphen in filename prevents normal import).
# An explicit SourceFileLoader is required because the file has no .py extension,
# so spec_from_file_location cannot infer the loader from the suffix.
_MOD_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'bin', 'ascii-pet')
_loader = importlib.machinery.SourceFileLoader('ascii_pet_linux', _MOD_PATH)
_spec = importlib.util.spec_from_file_location('ascii_pet_linux', _MOD_PATH, loader=_loader)
ascii_pet_linux = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ascii_pet_linux)
# Register in sys.modules so unittest.mock.patch('ascii_pet_linux.X') works.
sys.modules['ascii_pet_linux'] = ascii_pet_linux


def _uid():
    """Generate a unique uid per test to avoid state collisions."""
    return f'test-linux-{int(time.time() * 1000000)}-{os.urandom(4).hex()}'


@pytest.fixture
def game(tmp_path):
    """Provide a fresh PetGame with isolated temp dir."""
    return PetGame(_uid(), data_dir=tmp_path)


class _FakeLanNode:
    """Fake LanNode that simulates network behavior without real sockets."""

    def __init__(self, username, pet_state):
        self.username = username
        self.pet_state = pet_state
        self.node_id = f'fake-node-{username}'
        self.ui_queue = queue.Queue()
        self.net_queue = queue.Queue()
        self._status = {
            'enabled': False,
            'is_master': False,
            'peer_count': 0,
            'error': None,
            'node_id': self.node_id,
        }
        self._peers = [
            {
                'node_id': 'peer-1',
                'username': 'Bob',
                'pet_summary': {'name': 'BobPet', 'species': 'cat', 'level': 3, 'hp': 80},
            },
        ]
        self.send_calls = []

    def start(self):
        self._status['enabled'] = True
        self._status['is_master'] = True
        self._status['peer_count'] = len(self._peers)
        return True

    def stop(self):
        self._status['enabled'] = False
        self._status['is_master'] = False

    def get_status(self):
        return dict(self._status)

    def get_peers(self):
        return list(self._peers)

    def send_to_peer(self, peer_node_id, msg_type, payload):
        self.send_calls.append((peer_node_id, msg_type, payload))
        return True

    def send_broadcast(self, msg_type, payload):
        return True


def _enable_lan_with_fake(game, username='alice'):
    """Enable LAN on game using _FakeLanNode. Returns the fake node."""
    fake_node = _FakeLanNode(username, game.state)
    with patch('ascii_pet.lan.LanNode', return_value=fake_node):
        game.enable_lan(username)
    return fake_node


class TestImport:
    """Verify the Linux module loads correctly."""

    def test_module_loads(self):
        assert hasattr(ascii_pet_linux, 'main')
        assert hasattr(ascii_pet_linux, 'build_compact')

    def test_weather_import_fixed(self):
        """The weather import should use ascii_pet.weather, not bare weather."""
        # Read source to verify import statement
        with open(_MOD_PATH, 'r', encoding='utf-8') as f:
            source = f.read()
        assert 'from ascii_pet.weather import' in source
        assert 'from weather import' not in source


class TestAnimationCursorBug:
    """Verify the animation cursor positioning ANSI escape is well-formed."""

    def test_animation_cursor_escape_format(self):
        """The animation redraw should position cursor with row;1H, not bare H.

        Bug: f'\\033[H{n}\\033[K' emits '\\033[H1\\033[K' which moves to home
        row and prints the digit '1' instead of positioning to row n.
        Fix: f'\\033[{n};1H\\033[K' positions cursor to row n, column 1.
        """
        with open(_MOD_PATH, 'r', encoding='utf-8') as f:
            source = f.read()
        # The buggy pattern: \033[H{...}\033[K (missing [ and ;1)
        assert '\\033[H{' not in source or '\\033[H{n}' not in source, \
            "Found buggy animation cursor escape '\\033[H{n}\\033[K'"
        # The fixed pattern should exist
        assert '\\033[{n};1H\\033[K' in source or '\\033[{len(display' in source, \
            "Expected fixed animation cursor escape with row;1H"


class TestThemeSystem:
    """Verify the Linux version supports theme switching (green/orange)."""

    def test_theme_imports_present(self):
        """Module should import THEMES, DEFAULT_THEME from core."""
        with open(_MOD_PATH, 'r', encoding='utf-8') as f:
            source = f.read()
        assert 'from ascii_pet.core import' in source
        assert 'THEMES' in source
        assert 'DEFAULT_THEME' in source

    def test_theme_functions_imported(self):
        """Module should import get_theme, set_theme, save_theme, init_theme."""
        with open(_MOD_PATH, 'r', encoding='utf-8') as f:
            source = f.read()
        assert 'get_theme' in source
        assert 'set_theme' in source
        assert 'save_theme' in source
        assert 'init_theme' in source

    def test_refresh_theme_function_exists(self):
        """_refresh_theme() should exist and set module-level color vars."""
        assert hasattr(ascii_pet_linux, '_refresh_theme')
        assert hasattr(ascii_pet_linux, 'COLOR_DIM')
        assert hasattr(ascii_pet_linux, 'COLOR_MSG')
        assert hasattr(ascii_pet_linux, 'COLOR_WHITE')
        assert hasattr(ascii_pet_linux, 'COLOR_BAR_FILL')
        assert hasattr(ascii_pet_linux, 'COLOR_BAR_EMPTY')

    def test_refresh_theme_green(self, game):
        """_refresh_theme() with green theme sets expected ANSI codes."""
        from ascii_pet.core import THEMES
        i18n.set_theme('green')
        ascii_pet_linux._refresh_theme()
        green = THEMES['green']
        assert ascii_pet_linux.COLOR_DIM == green['ansi_dim']
        assert ascii_pet_linux.COLOR_WHITE == green['ansi_white']
        assert ascii_pet_linux.COLOR_BAR_FILL == green['ansi_bar_fill']

    def test_refresh_theme_orange(self, game):
        """_refresh_theme() with orange theme sets orange ANSI codes."""
        from ascii_pet.core import THEMES
        i18n.set_theme('orange')
        ascii_pet_linux._refresh_theme()
        orange = THEMES['orange']
        assert ascii_pet_linux.COLOR_DIM == orange['ansi_dim']
        assert ascii_pet_linux.COLOR_BAR_FILL == orange['ansi_bar_fill']
        # Reset to green for other tests
        i18n.set_theme('green')
        ascii_pet_linux._refresh_theme()


class TestLanMessageLoop:
    """Verify process_lan_queues is called in tick and disable_lan on exit."""

    def test_process_lan_queues_called_in_source(self):
        """Main loop source should call game.process_lan_queues()."""
        with open(_MOD_PATH, 'r', encoding='utf-8') as f:
            source = f.read()
        assert 'process_lan_queues' in source, \
            "Expected game.process_lan_queues() call in main loop"

    def test_disable_lan_called_on_exit(self):
        """Exit cleanup should call game.disable_lan()."""
        with open(_MOD_PATH, 'r', encoding='utf-8') as f:
            source = f.read()
        assert 'disable_lan' in source, \
            "Expected game.disable_lan() call in finally block"


class TestLayouts:
    """Verify layout functions exist for lan, lan_name_edit, rename, restore."""

    def test_layout_lan_exists(self):
        assert hasattr(ascii_pet_linux, 'layout_lan')

    def test_layout_lan_name_edit_exists(self):
        assert hasattr(ascii_pet_linux, 'layout_lan_name_edit')

    def test_layout_rename_exists(self):
        assert hasattr(ascii_pet_linux, 'layout_rename')

    def test_layout_restore_exists(self):
        assert hasattr(ascii_pet_linux, 'layout_restore')

    def test_do_layout_handles_lan(self, game):
        """do_layout should dispatch 'lan' mode to layout_lan."""
        with patch.object(ascii_pet_linux, 'set_window_geometry') as mock:
            with patch.object(ascii_pet_linux, 'get_screen_size', return_value=(1920, 1080)):
                game.mode = 'lan'
                ascii_pet_linux.do_layout(game)
                assert mock.called

    def test_do_layout_handles_lan_name_edit(self, game):
        """do_layout should dispatch 'lan_name_edit' mode."""
        with patch.object(ascii_pet_linux, 'set_window_geometry') as mock:
            with patch.object(ascii_pet_linux, 'get_screen_size', return_value=(1920, 1080)):
                game.mode = 'lan_name_edit'
                ascii_pet_linux.do_layout(game)
                assert mock.called


class TestDirectionKeys:
    """Verify arrow keys switch pets (left=prev, right=next)."""

    def test_arrow_key_handling_in_source(self):
        """Source should handle arrow escape sequences for pet switching."""
        with open(_MOD_PATH, 'r', encoding='utf-8') as f:
            source = f.read()
        # Arrow keys: \x1b[D (left), \x1b[C (right)
        assert "\\x1b[D" in source or "'\\x1b[D'" in source, \
            "Expected left arrow key handling"
        assert "\\x1b[C" in source or "'\\x1b[C'" in source, \
            "Expected right arrow key handling"


class TestBuildLanPanel:
    """Verify build_lan_panel renders community plaza UI."""

    def test_build_lan_panel_exists(self):
        assert hasattr(ascii_pet_linux, 'build_lan_panel')

    def test_disconnected_state(self, game):
        """When LAN is disabled, shows 'Status: Disconnected'."""
        out = ascii_pet_linux.build_lan_panel(game)
        assert 'Disconnected' in out
        assert 'Community Plaza' in out

    def test_connected_state(self, game):
        """When LAN is enabled, shows Username and Players online."""
        _enable_lan_with_fake(game, 'alice')
        game.mode = 'lan'
        out = ascii_pet_linux.build_lan_panel(game)
        assert 'Username: alice' in out
        assert 'Players online' in out

    def test_pet_info_line(self, game):
        """Connected state shows pet info line: name | species | Lv.X | HP:X/100."""
        _enable_lan_with_fake(game, 'alice')
        game.mode = 'lan'
        out = ascii_pet_linux.build_lan_panel(game)
        assert 'Lv.' in out
        assert 'HP:' in out
        assert '/100' in out

    def test_visit_status_active(self, game):
        """When active_visit is set, shows 'Visiting' timer."""
        _enable_lan_with_fake(game, 'alice')
        game.mode = 'lan'
        game.active_visit = {
            'target': 'peer-1',
            'start_time': time.time() - 65,
            'pet_snapshot': {},
            'last_heartbeat': time.time(),
        }
        out = ascii_pet_linux.build_lan_panel(game)
        assert 'Visiting' in out
        assert '1m' in out

    def test_being_visited_status(self, game):
        """When being_visited is set, shows 'is visiting you' timer."""
        _enable_lan_with_fake(game, 'alice')
        game.mode = 'lan'
        game.being_visited = {
            'from': 'peer-1',
            'start_time': time.time() - 30,
            'pet_snapshot': {'name': 'BobPet'},
            'last_heartbeat': time.time(),
        }
        out = ascii_pet_linux.build_lan_panel(game)
        assert 'visiting you' in out

    def test_peer_list(self, game):
        """Connected state shows online players list."""
        _enable_lan_with_fake(game, 'alice')
        game.mode = 'lan'
        out = ascii_pet_linux.build_lan_panel(game)
        assert 'Bob' in out
        assert 'BobPet' in out

    def test_submode_visit(self, game):
        """In visit submode, shows 'Select visit target'."""
        _enable_lan_with_fake(game, 'alice')
        game.mode = 'lan'
        game.lan_submode = 'visit'
        out = ascii_pet_linux.build_lan_panel(game)
        assert 'Select visit target' in out

    def test_submode_challenge(self, game):
        """In challenge submode, shows 'Select challenge target'."""
        _enable_lan_with_fake(game, 'alice')
        game.mode = 'lan'
        game.lan_submode = 'challenge'
        out = ascii_pet_linux.build_lan_panel(game)
        assert 'Select challenge target' in out

    def test_submode_gift(self, game):
        """In gift submode, shows 'Select gift target'."""
        _enable_lan_with_fake(game, 'alice')
        game.mode = 'lan'
        game.lan_submode = 'gift'
        out = ascii_pet_linux.build_lan_panel(game)
        assert 'Select gift target' in out

    def test_submode_gift_item(self, game):
        """In gift_item submode, shows 'Select item to gift'."""
        _enable_lan_with_fake(game, 'alice')
        game.mode = 'lan'
        game.lan_submode = 'gift_item'
        game.add_item('apple')
        out = ascii_pet_linux.build_lan_panel(game)
        assert 'Select item to gift' in out

    def test_submode_trade(self, game):
        """In trade submode, shows 'Select trade target'."""
        _enable_lan_with_fake(game, 'alice')
        game.mode = 'lan'
        game.lan_submode = 'trade'
        out = ascii_pet_linux.build_lan_panel(game)
        assert 'Select trade target' in out

    def test_submode_trade_pet(self, game):
        """In trade_pet submode, shows 'Select pet to trade'."""
        _enable_lan_with_fake(game, 'alice')
        game.mode = 'lan'
        game.lan_submode = 'trade_pet'
        out = ascii_pet_linux.build_lan_panel(game)
        assert 'Select pet to trade' in out

    def test_idle_action_hints(self, game):
        """In idle submode with peers, shows action hints."""
        _enable_lan_with_fake(game, 'alice')
        game.mode = 'lan'
        game.lan_submode = None
        out = ascii_pet_linux.build_lan_panel(game)
        assert '[v]Visit' in out or '[v]' in out
        assert '[c]Challenge' in out or '[c]' in out

    def test_back_hint(self, game):
        """Panel should show [l]Back hint."""
        _enable_lan_with_fake(game, 'alice')
        game.mode = 'lan'
        out = ascii_pet_linux.build_lan_panel(game)
        assert '[l]Back' in out or '[l]' in out


class TestBuildLanNameEdit:
    """Verify build_lan_name_edit renders username editing panel."""

    def test_function_exists(self):
        assert hasattr(ascii_pet_linux, 'build_lan_name_edit')

    def test_renders_title(self, game):
        _enable_lan_with_fake(game, 'alice')
        out = ascii_pet_linux.build_lan_name_edit(game)
        assert 'Edit Name' in out

    def test_shows_current_name(self, game):
        _enable_lan_with_fake(game, 'alice')
        out = ascii_pet_linux.build_lan_name_edit(game)
        assert 'alice' in out
        assert 'Current name' in out

    def test_shows_input_prompt(self, game):
        _enable_lan_with_fake(game, 'alice')
        out = ascii_pet_linux.build_lan_name_edit(game)
        assert 'New name:' in out
        assert '_' in out  # cursor

    def test_shows_confirm_hint(self, game):
        _enable_lan_with_fake(game, 'alice')
        out = ascii_pet_linux.build_lan_name_edit(game)
        assert '[Enter]' in out
        assert '[ESC]' in out


class TestBuildBattleLog:
    """Verify build_battle_log renders battle result."""

    def test_function_exists(self):
        assert hasattr(ascii_pet_linux, 'build_battle_log')

    def test_renders_title_and_entries(self):
        battle_result = {
            'log': ['Turn 1: A hits B', 'Turn 2: B hits A'],
            'winner': 'AlicePet',
            'loser': 'BobPet',
            'hp_loss_winner': 10,
            'hp_loss_loser': 50,
            'xp_gained': 40,
            'leveled_up': False,
            'evolved': None,
        }
        out = ascii_pet_linux.build_battle_log(battle_result)
        assert 'Battle Log' in out
        assert 'Turn 1' in out
        assert 'Winner: AlicePet' in out
        assert 'Loser: BobPet' in out
        assert 'XP +40' in out

    def test_level_up_and_evolution(self):
        battle_result = {
            'log': [],
            'winner': 'AlicePet',
            'loser': 'BobPet',
            'hp_loss_winner': 0,
            'hp_loss_loser': 50,
            'xp_gained': 40,
            'leveled_up': True,
            'evolved': 'dragon',
        }
        out = ascii_pet_linux.build_battle_log(battle_result)
        assert 'Level Up' in out
        assert 'Evolved into dragon' in out


class TestBuildTradeConfirm:
    """Verify build_trade_confirm renders trade request dialog."""

    def test_function_exists(self):
        assert hasattr(ascii_pet_linux, 'build_trade_confirm')

    def test_renders_trade_request(self):
        trade_req = {
            'from_username': 'Bob',
            'pet_snapshot': {'name': 'BobPet', 'species': 'cat'},
        }
        out = ascii_pet_linux.build_trade_confirm(trade_req)
        assert 'Trade Request' in out
        assert 'Bob' in out
        assert 'BobPet' in out
        assert 'cat' in out
        assert '[y]Accept' in out
        assert '[n]Reject' in out


class TestOverlays:
    """Verify overlays are appended in the main redraw logic.

    These tests check that a helper function build_display_with_overlays
    exists and correctly appends visitor pets, visit hints, battle log,
    and trade confirm to the base display.
    """

    def test_build_display_with_overlays_exists(self):
        assert hasattr(ascii_pet_linux, 'build_display_with_overlays')

    def test_visitor_pets_overlay(self, game):
        """When visitor_pets is non-empty and mode is compact/expanded,
        display includes visitor sprite and [Visitor] label."""
        game.visitor_pets = {
            'peer-1': {
                'name': 'BobPet',
                'species': 'cat',
                'eye': '·',
                'hat': 'none',
                'shiny': False,
                'rarity': 'common',
                'owner': 'Bob',
            },
        }
        game.mode = 'compact'
        out = ascii_pet_linux.build_display_with_overlays(game, ascii_pet_linux.build_compact(game))
        assert 'Visitor' in out
        assert 'BobPet' in out

    def test_visit_hint_overlay(self, game):
        """When active_visit and mode is compact/expanded, display includes visit hint."""
        game.active_visit = {
            'target': 'peer-1',
            'start_time': time.time(),
            'pet_snapshot': {},
            'last_heartbeat': time.time(),
        }
        game.mode = 'compact'
        out = ascii_pet_linux.build_display_with_overlays(game, ascii_pet_linux.build_compact(game))
        assert '[e]End Visit' in out

    def test_battle_log_overlay(self, game):
        """When battle_result is set and mode is expanded/lan, display includes battle log."""
        game.battle_result = {
            'log': ['Turn 1'],
            'winner': 'A',
            'loser': 'B',
            'hp_loss_winner': 0,
            'hp_loss_loser': 50,
            'xp_gained': 10,
            'leveled_up': False,
            'evolved': None,
        }
        game.mode = 'expanded'
        out = ascii_pet_linux.build_display_with_overlays(game, ascii_pet_linux.build_expanded(game))
        assert 'Battle Log' in out

    def test_trade_confirm_overlay(self, game):
        """When pending_trade_req is set, display includes trade confirm (all modes)."""
        game.pending_trade_req = {
            'from_username': 'Bob',
            'pet_snapshot': {'name': 'BobPet', 'species': 'cat'},
        }
        game.mode = 'compact'
        out = ascii_pet_linux.build_display_with_overlays(game, ascii_pet_linux.build_compact(game))
        assert 'Trade Request' in out


class TestMainLoopWiring:
    """Verify the main redraw block handles lan/lan_name_edit modes and overlays."""

    def test_main_loop_handles_lan_mode(self):
        """Source should include 'build_lan_panel' call in redraw block."""
        with open(_MOD_PATH, 'r', encoding='utf-8') as f:
            source = f.read()
        assert 'build_lan_panel' in source
        assert "game.mode == 'lan'" in source

    def test_main_loop_handles_lan_name_edit_mode(self):
        """Source should include 'build_lan_name_edit' call in redraw block."""
        with open(_MOD_PATH, 'r', encoding='utf-8') as f:
            source = f.read()
        assert 'build_lan_name_edit' in source
        assert "game.mode == 'lan_name_edit'" in source

    def test_main_loop_calls_build_display_with_overlays(self):
        """Source should call build_display_with_overlays in redraw block."""
        with open(_MOD_PATH, 'r', encoding='utf-8') as f:
            source = f.read()
        assert 'build_display_with_overlays' in source


class TestBackupRestore:
    """Verify backup creation (B key) and restore mode (V key)."""

    @pytest.fixture(autouse=True)
    def _reset_restore_mode(self):
        """Reset platform-layer _restore_mode flag before each test."""
        ascii_pet_linux._restore_mode = False
        yield

    def test_build_restore_exists(self):
        assert hasattr(ascii_pet_linux, 'build_restore')

    def test_build_restore_shows_backups(self, game):
        """build_restore should list available backups."""
        from ascii_pet.core import create_backup
        create_backup(game.uid, game.data_dir, 'manual')
        out = ascii_pet_linux.build_restore(game)
        assert 'Restore' in out or 'restore' in out
        # Should show the backup
        assert 'Manual' in out or 'Auto' in out

    def test_build_restore_empty(self, game):
        """build_restore with no backups shows empty message."""
        out = ascii_pet_linux.build_restore(game)
        assert 'No backups' in out or 'Empty' in out or 'restore' in out.lower()

    def test_handle_backup_key_calls_create_backup(self, game):
        """handle_platform_key('B') should create a backup."""
        from unittest.mock import patch
        with patch('ascii_pet_linux.create_backup') as mock_backup:
            result = ascii_pet_linux.handle_platform_key('B', game)
            assert mock_backup.called

    def test_handle_restore_key_enters_mode(self, game):
        """handle_platform_key('V') should enter restore mode."""
        result = ascii_pet_linux.handle_platform_key('V', game)
        # Should return True indicating mode was entered
        assert result is True or result == 'restore'

    def test_handle_restore_key_exits_on_cancel(self, game):
        """In restore mode, 'c' or ESC should exit."""
        # Enter restore mode first
        ascii_pet_linux.handle_platform_key('V', game)
        # Exit with 'c'
        result = ascii_pet_linux.handle_platform_key('c', game)
        assert result is False or result == 'exit'


class TestThemeLanguageToggle:
    """Verify ; toggles theme and ' toggles language."""

    def test_theme_toggle(self, game):
        """handle_platform_key(';') should switch theme."""
        i18n.set_theme('green')
        ascii_pet_linux._refresh_theme()
        result = ascii_pet_linux.handle_platform_key(';', game)
        assert i18n.get_theme() == 'orange'
        # Toggle back
        ascii_pet_linux.handle_platform_key(';', game)
        assert i18n.get_theme() == 'green'

    def test_language_toggle(self, game):
        """handle_platform_key("'") should switch language."""
        i18n.set_language('en')
        result = ascii_pet_linux.handle_platform_key("'", game)
        assert i18n.get_language() == 'zh'
        # Toggle back
        ascii_pet_linux.handle_platform_key("'", game)
        assert i18n.get_language() == 'en'

    def test_theme_toggle_returns_none(self, game):
        """Theme toggle should return None (no mode change)."""
        result = ascii_pet_linux.handle_platform_key(';', game)
        assert result is None

    def test_language_toggle_returns_none(self, game):
        """Language toggle should return None."""
        result = ascii_pet_linux.handle_platform_key("'", game)
        assert result is None


class TestAutostart:
    """Verify A key toggles autostart via .desktop file."""

    def test_is_autostart_enabled_exists(self):
        assert hasattr(ascii_pet_linux, 'is_autostart_enabled')

    def test_set_autostart_exists(self):
        assert hasattr(ascii_pet_linux, 'set_autostart')

    def test_autostart_disabled_by_default(self, tmp_path):
        """is_autostart_enabled should return False when no .desktop file exists."""
        with patch.object(ascii_pet_linux, '_autostart_path', return_value=str(tmp_path / 'ascii-pet.desktop')):
            assert ascii_pet_linux.is_autostart_enabled() is False

    def test_set_autostart_true_creates_file(self, tmp_path):
        """set_autostart(True) should create the .desktop file."""
        desktop_path = str(tmp_path / 'ascii-pet.desktop')
        with patch.object(ascii_pet_linux, '_autostart_path', return_value=desktop_path):
            with patch.object(ascii_pet_linux, '_launcher_path', return_value='/usr/bin/ascii-pet-launcher'):
                with patch.object(ascii_pet_linux, '_icon_path', return_value='/usr/share/icons/ascii-pet.png'):
                    ascii_pet_linux.set_autostart(True)
                    assert os.path.exists(desktop_path)
                    with open(desktop_path, 'r') as f:
                        content = f.read()
                    assert 'Type=Application' in content
                    assert 'ascii-pet-launcher' in content

    def test_set_autostart_false_removes_file(self, tmp_path):
        """set_autostart(False) should delete the .desktop file."""
        desktop_path = str(tmp_path / 'ascii-pet.desktop')
        with open(desktop_path, 'w') as f:
            f.write('[Desktop Entry]')
        with patch.object(ascii_pet_linux, '_autostart_path', return_value=desktop_path):
            ascii_pet_linux.set_autostart(False)
            assert not os.path.exists(desktop_path)

    def test_handle_a_key_toggles_autostart(self, game, tmp_path):
        """handle_platform_key('A') should toggle autostart."""
        desktop_path = str(tmp_path / 'ascii-pet.desktop')
        with patch.object(ascii_pet_linux, '_autostart_path', return_value=desktop_path):
            with patch.object(ascii_pet_linux, '_launcher_path', return_value='/usr/bin/ascii-pet-launcher'):
                with patch.object(ascii_pet_linux, '_icon_path', return_value='/usr/share/icons/ascii-pet.png'):
                    # Initially disabled, A should enable
                    result = ascii_pet_linux.handle_platform_key('A', game)
                    assert os.path.exists(desktop_path)
                    # A again should disable
                    ascii_pet_linux.handle_platform_key('A', game)
                    assert not os.path.exists(desktop_path)


class TestPlatformKeyIntegration:
    """Verify platform keys and restore mode are integrated into main loop."""

    def test_handle_platform_key_called_in_main_loop(self):
        """Source should call handle_platform_key in main loop."""
        with open(_MOD_PATH, 'r', encoding='utf-8') as f:
            source = f.read()
        assert 'handle_platform_key' in source

    def test_restore_mode_layout_in_main_loop(self):
        """Source should call layout_restore when _restore_mode is True."""
        with open(_MOD_PATH, 'r', encoding='utf-8') as f:
            source = f.read()
        assert '_restore_mode' in source
        assert 'layout_restore' in source

    def test_restore_mode_render_in_main_loop(self):
        """Source should call build_restore when _restore_mode is True."""
        with open(_MOD_PATH, 'r', encoding='utf-8') as f:
            source = f.read()
        assert 'build_restore' in source


class TestMainInit:
    """Verify main() calls init_theme and _refresh_theme on startup."""

    def test_init_theme_called_in_main(self):
        """Source should call init_theme in main()."""
        with open(_MOD_PATH, 'r', encoding='utf-8') as f:
            source = f.read()
        assert 'init_theme' in source
        # Should be called in main, not just imported
        assert 'init_theme(' in source

    def test_refresh_theme_called_in_main(self):
        """Source should call _refresh_theme in main()."""
        with open(_MOD_PATH, 'r', encoding='utf-8') as f:
            source = f.read()
        assert '_refresh_theme()' in source


class TestHelpText:
    """Verify help text documents new keyboard shortcuts."""

    def test_expanded_help_includes_lan(self, game):
        """Expanded mode help should mention 'l' for LAN/Community Plaza."""
        game.show_help = True
        out = ascii_pet_linux.build_expanded(game)
        assert '[l]' in out

    def test_help_output_mentions_shortcuts(self):
        """--help output should mention new shortcuts."""
        with open(_MOD_PATH, 'r', encoding='utf-8') as f:
            source = f.read()
        # Should mention community plaza / LAN
        assert 'Community Plaza' in source or 'LAN' in source or 'lan' in source
