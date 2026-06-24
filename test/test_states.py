"""Tests for game event system and state machine (TDD)."""

import time
import pytest
from dataclasses import FrozenInstanceError


# ─── Task 1: GameEvent event system ──────────────────────────────────────────


class TestGameEvent:
    """Test GameEvent base class and its subclasses."""

    def test_game_event_is_frozen_dataclass(self):
        from ascii_pet.states import GameEvent
        with pytest.raises(FrozenInstanceError):
            GameEvent(timestamp=1.0).timestamp = 2.0

    def test_game_event_has_timestamp(self):
        from ascii_pet.states import GameEvent
        before = time.time()
        evt = GameEvent()
        after = time.time()
        assert before <= evt.timestamp <= after

    def test_game_event_custom_timestamp(self):
        from ascii_pet.states import GameEvent
        evt = GameEvent(timestamp=42.0)
        assert evt.timestamp == 42.0


class TestKeyEvent:
    """Test KeyEvent event class."""

    def test_key_event_carries_key(self):
        from ascii_pet.states import KeyEvent
        evt = KeyEvent(key='f')
        assert evt.key == 'f'

    def test_key_event_default_key_empty(self):
        from ascii_pet.states import KeyEvent
        evt = KeyEvent()
        assert evt.key == ''

    def test_key_event_is_frozen(self):
        from ascii_pet.states import KeyEvent
        evt = KeyEvent(key='f')
        with pytest.raises(FrozenInstanceError):
            evt.key = 'g'

    def test_key_event_inherits_timestamp(self):
        from ascii_pet.states import KeyEvent
        evt = KeyEvent(key='f', timestamp=10.0)
        assert evt.timestamp == 10.0
        assert evt.key == 'f'

    def test_key_event_is_game_event(self):
        from ascii_pet.states import KeyEvent, GameEvent
        evt = KeyEvent(key='f')
        assert isinstance(evt, GameEvent)


class TestTickEvent:
    """Test TickEvent event class."""

    def test_tick_event_carries_delta_hours(self):
        from ascii_pet.states import TickEvent
        evt = TickEvent(delta_hours=0.5)
        assert evt.delta_hours == 0.5

    def test_tick_event_default_delta_zero(self):
        from ascii_pet.states import TickEvent
        evt = TickEvent()
        assert evt.delta_hours == 0.0

    def test_tick_event_is_frozen(self):
        from ascii_pet.states import TickEvent
        evt = TickEvent(delta_hours=0.5)
        with pytest.raises(FrozenInstanceError):
            evt.delta_hours = 1.0

    def test_tick_event_is_game_event(self):
        from ascii_pet.states import TickEvent, GameEvent
        assert isinstance(TickEvent(), GameEvent)


class TestLanMessageEvent:
    """Test LanMessageEvent event class."""

    def test_lan_message_event_carries_msg_type(self):
        from ascii_pet.states import LanMessageEvent
        evt = LanMessageEvent(msg_type='VISIT_REQ')
        assert evt.msg_type == 'VISIT_REQ'

    def test_lan_message_event_carries_payload(self):
        from ascii_pet.states import LanMessageEvent
        payload = {'from': 'node1', 'pet_snapshot': {'name': 'Fluffy'}}
        evt = LanMessageEvent(msg_type='VISIT_REQ', payload=payload)
        assert evt.payload == payload

    def test_lan_message_event_default_empty(self):
        from ascii_pet.states import LanMessageEvent
        evt = LanMessageEvent()
        assert evt.msg_type == ''
        assert evt.payload == {}

    def test_lan_message_event_is_frozen(self):
        from ascii_pet.states import LanMessageEvent
        evt = LanMessageEvent(msg_type='X')
        with pytest.raises(FrozenInstanceError):
            evt.msg_type = 'Y'

    def test_lan_message_event_is_game_event(self):
        from ascii_pet.states import LanMessageEvent, GameEvent
        assert isinstance(LanMessageEvent(), GameEvent)


class TestTimeoutEvent:
    """Test TimeoutEvent event class."""

    def test_timeout_event_carries_type(self):
        from ascii_pet.states import TimeoutEvent
        evt = TimeoutEvent(timeout_type='visit')
        assert evt.timeout_type == 'visit'

    def test_timeout_event_default_empty(self):
        from ascii_pet.states import TimeoutEvent
        evt = TimeoutEvent()
        assert evt.timeout_type == ''

    def test_timeout_event_is_frozen(self):
        from ascii_pet.states import TimeoutEvent
        evt = TimeoutEvent(timeout_type='visit')
        with pytest.raises(FrozenInstanceError):
            evt.timeout_type = 'challenge'

    def test_timeout_event_is_game_event(self):
        from ascii_pet.states import TimeoutEvent, GameEvent
        assert isinstance(TimeoutEvent(), GameEvent)


# ─── Task 2: GameState base class and StateMachine ───────────────────────────


class TestGameState:
    """Test GameState abstract base class."""

    def test_cannot_instantiate_abstract(self):
        from ascii_pet.states import GameState
        with pytest.raises(TypeError):
            GameState()

    def test_concrete_subclass_has_state_id(self):
        from ascii_pet.states import GameState

        class DummyState(GameState):
            @property
            def state_id(self) -> str:
                return 'dummy'

            def on_enter(self, game, prev_state):
                pass

            def on_exit(self, game, next_state):
                pass

            def handle_key(self, game, event):
                return 'none', None

            def tick(self, game, event):
                return None, 0

        s = DummyState()
        assert s.state_id == 'dummy'

    def test_default_handle_lan_message_is_noop(self):
        from ascii_pet.states import GameState

        class DummyState(GameState):
            @property
            def state_id(self):
                return 'dummy'

            def on_enter(self, game, prev_state):
                pass

            def on_exit(self, game, next_state):
                pass

            def handle_key(self, game, event):
                return 'none', None

            def tick(self, game, event):
                return None, 0

        s = DummyState()
        # Should not raise
        s.handle_lan_message(None, None)


class TestStateMachine:
    """Test StateMachine orchestrator."""

    def _make_state(self, sid):
        from ascii_pet.states import GameState

        class S(GameState):
            @property
            def state_id(self):
                return sid

            def on_enter(self, game, prev_state):
                pass

            def on_exit(self, game, next_state):
                pass

            def handle_key(self, game, event):
                return 'none', None

            def tick(self, game, event):
                return None, 0

        return S()

    def test_initial_state(self):
        from ascii_pet.states import StateMachine
        initial = self._make_state('compact')
        sm = StateMachine(initial)
        assert sm.current_state_id == 'compact'

    def test_current_state_object(self):
        from ascii_pet.states import StateMachine
        initial = self._make_state('compact')
        sm = StateMachine(initial)
        assert sm.current_state is initial

    def test_add_transition_and_valid_transition(self):
        from ascii_pet.states import StateMachine
        compact = self._make_state('compact')
        expanded = self._make_state('expanded')
        sm = StateMachine(compact)
        sm.add_transition('compact', 'expanded')
        sm.transition_to(None, expanded)
        assert sm.current_state_id == 'expanded'

    def test_invalid_transition_raises(self):
        from ascii_pet.states import StateMachine, InvalidTransition
        compact = self._make_state('compact')
        lan = self._make_state('lan')
        sm = StateMachine(compact)
        # No transition registered
        with pytest.raises(InvalidTransition):
            sm.transition_to(None, lan)

    def test_on_exit_called_before_on_enter(self):
        from ascii_pet.states import StateMachine, GameState

        call_order = []

        class StateA(GameState):
            @property
            def state_id(self):
                return 'a'

            def on_enter(self, game, prev_state):
                call_order.append(('enter_a', prev_state))

            def on_exit(self, game, next_state):
                call_order.append(('exit_a', next_state))

            def handle_key(self, game, event):
                return 'none', None

            def tick(self, game, event):
                return None, 0

        class StateB(GameState):
            @property
            def state_id(self):
                return 'b'

            def on_enter(self, game, prev_state):
                call_order.append(('enter_b', prev_state))

            def on_exit(self, game, next_state):
                call_order.append(('exit_b', next_state))

            def handle_key(self, game, event):
                return 'none', None

            def tick(self, game, event):
                return None, 0

        a = StateA()
        b = StateB()
        sm = StateMachine(a)
        sm.add_transition('a', 'b')
        sm.transition_to(None, b)

        assert call_order[0][0] == 'exit_a'
        assert call_order[1][0] == 'enter_b'

    def test_dispatch_key_event(self):
        from ascii_pet.states import StateMachine, GameState, KeyEvent

        class StateA(GameState):
            @property
            def state_id(self):
                return 'a'

            def on_enter(self, game, prev_state):
                pass

            def on_exit(self, game, next_state):
                pass

            def handle_key(self, game, event):
                return 'action', event.key

            def tick(self, game, event):
                return None, 0

        a = StateA()
        sm = StateMachine(a)
        result = sm.dispatch(None, KeyEvent(key='f'))
        assert result == ('action', 'f')

    def test_dispatch_tick_event(self):
        from ascii_pet.states import StateMachine, GameState, TickEvent

        class StateA(GameState):
            @property
            def state_id(self):
                return 'a'

            def on_enter(self, game, prev_state):
                pass

            def on_exit(self, game, next_state):
                pass

            def handle_key(self, game, event):
                return 'none', None

            def tick(self, game, event):
                return 'tick_msg', event.timestamp

        a = StateA()
        sm = StateMachine(a)
        result = sm.dispatch(None, TickEvent(delta_hours=0.5))
        assert result[0] == 'tick_msg'

    def test_dispatch_lan_message_event(self):
        from ascii_pet.states import StateMachine, GameState, LanMessageEvent

        received = []

        class StateA(GameState):
            @property
            def state_id(self):
                return 'a'

            def on_enter(self, game, prev_state):
                pass

            def on_exit(self, game, next_state):
                pass

            def handle_key(self, game, event):
                return 'none', None

            def tick(self, game, event):
                return None, 0

            def handle_lan_message(self, game, event):
                received.append(event.msg_type)

        a = StateA()
        sm = StateMachine(a)
        sm.dispatch(None, LanMessageEvent(msg_type='VISIT_REQ'))
        assert received == ['VISIT_REQ']

    def test_dispatch_timeout_event(self):
        from ascii_pet.states import StateMachine, GameState, TimeoutEvent

        received = []

        class StateA(GameState):
            @property
            def state_id(self):
                return 'a'

            def on_enter(self, game, prev_state):
                pass

            def on_exit(self, game, next_state):
                pass

            def handle_key(self, game, event):
                return 'none', None

            def tick(self, game, event):
                return None, 0

            def handle_timeout(self, game, event):
                received.append(event.timeout_type)

        a = StateA()
        sm = StateMachine(a)
        sm.dispatch(None, TimeoutEvent(timeout_type='visit'))
        assert received == ['visit']

    def test_bidirectional_transition(self):
        from ascii_pet.states import StateMachine
        compact = self._make_state('compact')
        expanded = self._make_state('expanded')
        sm = StateMachine(compact)
        sm.add_transition('compact', 'expanded')
        sm.add_transition('expanded', 'compact')
        sm.transition_to(None, expanded)
        assert sm.current_state_id == 'expanded'
        sm.transition_to(None, compact)
        assert sm.current_state_id == 'compact'

    def test_same_state_transition_is_noop(self):
        from ascii_pet.states import StateMachine, GameState

        enter_count = [0]

        class StateA(GameState):
            @property
            def state_id(self):
                return 'a'

            def on_enter(self, game, prev_state):
                enter_count[0] += 1

            def on_exit(self, game, next_state):
                pass

            def handle_key(self, game, event):
                return 'none', None

            def tick(self, game, event):
                return None, 0

        a = StateA()
        sm = StateMachine(a)
        sm.add_transition('a', 'a')
        # Transitioning to same state should be a no-op
        sm.transition_to(None, a)
        assert enter_count[0] == 0


# ─── Task 3: Concrete state classes ──────────────────────────────────────────


# Helper: mock game object for testing states in isolation

from unittest.mock import MagicMock
from ascii_pet.states import (
    StateMachine, GameState, KeyEvent, TickEvent,
    CompactState, ExpandedState, StatsState,
    AchievementsState, ItemsState, RenameState, ReleaseState,
    LanState,
)


def _make_mock_game(initial_state_id='expanded'):
    """Create a mock game object with a StateMachine and all transitions registered."""
    game = MagicMock()
    game.show_help = False
    game.message = ''
    game.message_time = 0.0
    game.state = {
        'is_dead': False,
        'stats': {'HUNGER': 50, 'HAPPY': 50, 'ENERGY': 50},
        'name': 'TestPet',
    }
    game.pets_data = {
        'pets': [
            {'name': 'Pet1', 'species': 'cat', 'rarity': 'common'},
            {'name': 'Pet2', 'species': 'dog', 'rarity': 'uncommon'},
            {'name': 'Pet3', 'species': 'blob', 'rarity': 'rare'},
        ],
        'inventory': {'apple': 2, 'toy': 1},
    }
    game.active_visit = None
    game.being_visited = None
    game.remote_feed.return_value = True
    game.remote_play.return_value = True
    game.end_visit.return_value = True

    game.handle_action.return_value = ('action_msg', None)
    game.switch_pet.return_value = 'switched_msg'
    game.adopt_pet.return_value = 'adopted_msg'
    game.rename_pet.return_value = 'renamed_msg'
    game.release_pet.return_value = 'released_msg'
    game.use_item.return_value = 'used_msg'
    game.get_inventory_list.return_value = [
        ('apple', 'Apple', '🍎', 2, 'Restores 30 hunger'),
        ('toy', 'Toy', '🎾', 1, 'Restores 30 happiness'),
    ]

    # Build state machine with all transitions
    states = {
        'compact': CompactState(),
        'expanded': ExpandedState(),
        'stats': StatsState(),
        'achievements': AchievementsState(),
        'items': ItemsState(),
        'rename': RenameState(),
        'release': ReleaseState(),
        'lan': LanState(),
    }
    sm = StateMachine(states[initial_state_id])

    # Register all valid transitions
    # compact <-> expanded
    sm.add_transition('compact', 'expanded')
    sm.add_transition('expanded', 'compact')
    # expanded -> stats, achievements, lan, items, release
    sm.add_transition('expanded', 'stats')
    sm.add_transition('expanded', 'achievements')
    sm.add_transition('expanded', 'lan')
    sm.add_transition('expanded', 'items')
    sm.add_transition('expanded', 'release')
    # stats -> expanded, achievements, rename
    sm.add_transition('stats', 'expanded')
    sm.add_transition('stats', 'achievements')
    sm.add_transition('stats', 'rename')
    # achievements -> expanded
    sm.add_transition('achievements', 'expanded')
    # items -> expanded
    sm.add_transition('items', 'expanded')
    # lan -> expanded, lan_name_edit
    sm.add_transition('lan', 'expanded')
    sm.add_transition('lan', 'lan_name_edit')
    sm.add_transition('lan_name_edit', 'lan')
    # rename -> stats
    sm.add_transition('rename', 'stats')
    # release -> expanded
    sm.add_transition('release', 'expanded')

    game.sm = sm
    game._states = states
    return game


# ─── TestCompactState ────────────────────────────────────────────────────────


class TestCompactState:

    def test_state_id(self):
        s = CompactState()
        assert s.state_id == 'compact'

    def test_enter_key_transitions_to_expanded(self):
        game = _make_mock_game('compact')
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='\r'))
        assert game.sm.current_state_id == 'expanded'

    def test_h_key_transitions_to_expanded_with_show_help(self):
        game = _make_mock_game('compact')
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='h'))
        assert game.sm.current_state_id == 'expanded'
        assert game.show_help is True

    def test_c_key_is_noop(self):
        game = _make_mock_game('compact')
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='c'))
        assert game.sm.current_state_id == 'compact'
        assert result == ('none', None)

    def test_tick_returns_none(self):
        game = _make_mock_game('compact')
        s = game.sm.current_state
        result = s.tick(game, TickEvent(delta_hours=0.5))
        assert result == (None, 0)

    def test_on_enter_and_exit_are_noop(self):
        game = _make_mock_game('compact')
        s = game.sm.current_state
        # Should not raise
        s.on_enter(game, None)
        s.on_exit(game, CompactState())


# ─── TestExpandedState ───────────────────────────────────────────────────────


class TestExpandedState:

    def test_state_id(self):
        s = ExpandedState()
        assert s.state_id == 'expanded'

    def test_f_key_feeds_pet(self):
        game = _make_mock_game('expanded')
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='f'))
        game.handle_action.assert_called_once_with('feed')

    def test_p_key_plays_pet(self):
        game = _make_mock_game('expanded')
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='p'))
        game.handle_action.assert_called_once_with('play')

    def test_s_key_sleeps_pet(self):
        game = _make_mock_game('expanded')
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='s'))
        game.handle_action.assert_called_once_with('sleep')

    def test_t_key_transitions_to_stats(self):
        game = _make_mock_game('expanded')
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='t'))
        assert game.sm.current_state_id == 'stats'

    def test_a_key_transitions_to_achievements(self):
        game = _make_mock_game('expanded')
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='a'))
        assert game.sm.current_state_id == 'achievements'

    def test_l_key_transitions_to_lan(self):
        """'l' key should attempt transition to lan state."""
        game = _make_mock_game('expanded')
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='l'))
        assert game.sm.current_state_id == 'lan'

    def test_u_key_transitions_to_items(self):
        game = _make_mock_game('expanded')
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='u'))
        assert game.sm.current_state_id == 'items'

    def test_c_key_transitions_to_compact(self):
        game = _make_mock_game('expanded')
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='c'))
        assert game.sm.current_state_id == 'compact'

    def test_enter_key_transitions_to_compact(self):
        game = _make_mock_game('expanded')
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='\r'))
        assert game.sm.current_state_id == 'compact'

    def test_e_key_exports(self):
        game = _make_mock_game('expanded')
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='e'))
        assert result == ('export', None)

    def test_b_key_switches_pet_prev(self):
        game = _make_mock_game('expanded')
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='b'))
        game.switch_pet.assert_called_once_with(-1)

    def test_n_key_switches_pet_next(self):
        game = _make_mock_game('expanded')
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='n'))
        game.switch_pet.assert_called_once_with(1)

    def test_w_key_adopts_pet(self):
        game = _make_mock_game('expanded')
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='w'))
        game.adopt_pet.assert_called_once()

    def test_h_key_toggles_help_on(self):
        game = _make_mock_game('expanded')
        game.show_help = False
        s = game.sm.current_state
        s.handle_key(game, KeyEvent(key='h'))
        assert game.show_help is True

    def test_h_key_toggles_help_off(self):
        game = _make_mock_game('expanded')
        game.show_help = True
        s = game.sm.current_state
        s.handle_key(game, KeyEvent(key='h'))
        assert game.show_help is False

    def test_tick_returns_none(self):
        game = _make_mock_game('expanded')
        s = game.sm.current_state
        result = s.tick(game, TickEvent(delta_hours=0.5))
        assert result == (None, 0)


# ─── TestStatsState ──────────────────────────────────────────────────────────


class TestStatsState:

    def test_state_id(self):
        s = StatsState()
        assert s.state_id == 'stats'

    def test_t_key_transitions_to_expanded(self):
        game = _make_mock_game('stats')
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='t'))
        assert game.sm.current_state_id == 'expanded'

    def test_a_key_transitions_to_achievements(self):
        game = _make_mock_game('stats')
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='a'))
        assert game.sm.current_state_id == 'achievements'

    def test_r_key_transitions_to_rename(self):
        game = _make_mock_game('stats')
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='r'))
        assert game.sm.current_state_id == 'rename'

    def test_tick_returns_none(self):
        game = _make_mock_game('stats')
        s = game.sm.current_state
        result = s.tick(game, TickEvent(delta_hours=0.5))
        assert result == (None, 0)


# ─── TestAchievementsState ──────────────────────────────────────────────────


class TestAchievementsState:

    def test_state_id(self):
        s = AchievementsState()
        assert s.state_id == 'achievements'

    def test_a_key_transitions_to_expanded(self):
        game = _make_mock_game('achievements')
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='a'))
        assert game.sm.current_state_id == 'expanded'

    def test_tick_returns_none(self):
        game = _make_mock_game('achievements')
        s = game.sm.current_state
        result = s.tick(game, TickEvent(delta_hours=0.5))
        assert result == (None, 0)


# ─── TestItemsState ──────────────────────────────────────────────────────────


class TestItemsState:

    def test_state_id(self):
        s = ItemsState()
        assert s.state_id == 'items'

    def test_number_keys_use_items(self):
        """Keys '1'-'7' should use items by index from inventory list."""
        game = _make_mock_game('items')
        # Set up inventory list with 3 items
        game.get_inventory_list.return_value = [
            ('apple', 'Apple', '🍎', 2, 'Restores 30 hunger'),
            ('toy', 'Toy', '🎾', 1, 'Restores 30 happiness'),
            ('bed', 'Bed', '🛏', 1, 'Restores 30 energy'),
        ]
        s = game.sm.current_state

        # Key '1' → use item at index 0 (apple)
        s.handle_key(game, KeyEvent(key='1'))
        game.use_item.assert_called_with('apple')

        # Key '2' → use item at index 1 (toy)
        s.handle_key(game, KeyEvent(key='2'))
        game.use_item.assert_called_with('toy')

        # Key '3' → use item at index 2 (bed)
        s.handle_key(game, KeyEvent(key='3'))
        game.use_item.assert_called_with('bed')

    def test_number_key_beyond_inventory_is_noop(self):
        """Key for index beyond inventory list length should be no-op."""
        game = _make_mock_game('items')
        game.get_inventory_list.return_value = [
            ('apple', 'Apple', '🍎', 2, 'Restores 30 hunger'),
        ]
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='5'))
        assert result == ('none', None)
        game.use_item.assert_not_called()

    def test_c_key_transitions_to_expanded(self):
        game = _make_mock_game('items')
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='c'))
        assert game.sm.current_state_id == 'expanded'

    def test_tick_returns_none(self):
        game = _make_mock_game('items')
        s = game.sm.current_state
        result = s.tick(game, TickEvent(delta_hours=0.5))
        assert result == (None, 0)


# ─── TestRenameState ─────────────────────────────────────────────────────────


class TestRenameState:

    def test_state_id(self):
        s = RenameState()
        assert s.state_id == 'rename'

    def test_enter_confirms_rename(self):
        game = _make_mock_game('rename')
        s = game.sm.current_state
        # Type some chars first
        s.handle_key(game, KeyEvent(key='A'))
        s.handle_key(game, KeyEvent(key='l'))
        s.handle_key(game, KeyEvent(key='i'))
        s.handle_key(game, KeyEvent(key='c'))
        s.handle_key(game, KeyEvent(key='e'))
        # Confirm with Enter
        result = s.handle_key(game, KeyEvent(key='\r'))
        game.rename_pet.assert_called_once_with('Alice')
        assert game.sm.current_state_id == 'stats'

    def test_enter_with_empty_input_is_noop(self):
        game = _make_mock_game('rename')
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='\r'))
        game.rename_pet.assert_not_called()
        assert result == ('none', None)

    def test_esc_cancels_to_stats(self):
        game = _make_mock_game('rename')
        s = game.sm.current_state
        # Type something
        s.handle_key(game, KeyEvent(key='B'))
        s.handle_key(game, KeyEvent(key='o'))
        s.handle_key(game, KeyEvent(key='b'))
        # Cancel with ESC
        result = s.handle_key(game, KeyEvent(key='\x1b'))
        assert game.sm.current_state_id == 'stats'
        game.rename_pet.assert_not_called()

    def test_backspace_deletes_last_char(self):
        game = _make_mock_game('rename')
        s = game.sm.current_state
        s.handle_key(game, KeyEvent(key='A'))
        s.handle_key(game, KeyEvent(key='B'))
        s.handle_key(game, KeyEvent(key='\x08'))  # backspace
        # Confirm - should only have 'A'
        s.handle_key(game, KeyEvent(key='\r'))
        game.rename_pet.assert_called_once_with('A')

    def test_printable_chars_append_to_buffer(self):
        game = _make_mock_game('rename')
        s = game.sm.current_state
        for ch in 'Hello':
            s.handle_key(game, KeyEvent(key=ch))
        s.handle_key(game, KeyEvent(key='\r'))
        game.rename_pet.assert_called_once_with('Hello')

    def test_max_length_20(self):
        """Input buffer should not exceed 20 characters."""
        game = _make_mock_game('rename')
        s = game.sm.current_state
        # Type 25 characters
        for ch in 'A' * 25:
            s.handle_key(game, KeyEvent(key=ch))
        s.handle_key(game, KeyEvent(key='\r'))
        # Should be capped at 20
        game.rename_pet.assert_called_once_with('A' * 20)

    def test_on_enter_resets_input_buffer(self):
        game = _make_mock_game('rename')
        s = game.sm.current_state
        # Type something
        s.handle_key(game, KeyEvent(key='X'))
        # Re-enter the state (simulating transition)
        s.on_enter(game, None)
        # Input buffer should be reset
        s.handle_key(game, KeyEvent(key='\r'))
        game.rename_pet.assert_not_called()

    def test_tick_returns_none(self):
        game = _make_mock_game('rename')
        s = game.sm.current_state
        result = s.tick(game, TickEvent(delta_hours=0.5))
        assert result == (None, 0)


# ─── TestReleaseState ────────────────────────────────────────────────────────


class TestReleaseState:

    def test_state_id(self):
        s = ReleaseState()
        assert s.state_id == 'release'

    def test_number_keys_release_pet(self):
        """Keys '1'-'3' should release pet by index (0-based)."""
        game = _make_mock_game('release')
        s = game.sm.current_state

        # Key '1' → release pet index 0
        result = s.handle_key(game, KeyEvent(key='1'))
        game.release_pet.assert_called_with(0)

    def test_key_2_releases_index_1(self):
        game = _make_mock_game('release')
        s = game.sm.current_state
        s.handle_key(game, KeyEvent(key='2'))
        game.release_pet.assert_called_with(1)

    def test_key_3_releases_index_2(self):
        game = _make_mock_game('release')
        s = game.sm.current_state
        s.handle_key(game, KeyEvent(key='3'))
        game.release_pet.assert_called_with(2)

    def test_c_key_cancels_to_expanded(self):
        game = _make_mock_game('release')
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='c'))
        assert game.sm.current_state_id == 'expanded'

    def test_tick_returns_none(self):
        game = _make_mock_game('release')
        s = game.sm.current_state
        result = s.tick(game, TickEvent(delta_hours=0.5))
        assert result == (None, 0)


# ─── Task 4: DeadOverlayState ─────────────────────────────────────────────────


class TestDeadOverlayState:
    """Test DeadOverlayState decorator/overlay for dead pets."""

    def _make_inner_state(self, sid='compact'):
        """Create a minimal concrete GameState for use as inner state."""
        from ascii_pet.states import GameState

        class InnerState(GameState):
            def __init__(self):
                self.entered = False
                self.exited = False
                self.lan_received = []

            @property
            def state_id(self):
                return sid

            def on_enter(self, game, prev_state):
                self.entered = True

            def on_exit(self, game, next_state):
                self.exited = True

            def handle_key(self, game, event):
                return 'inner_action', event.key

            def tick(self, game, event):
                return 'inner_tick', 1.0

            def handle_lan_message(self, game, event):
                self.lan_received.append(event.msg_type)

        return InnerState()

    def _make_mock_game(self, has_potion=True):
        """Create a mock game object with required attributes."""
        class MockGame:
            def __init__(self, has_potion):
                self.pet_idx = 0
                self.pets_data = {
                    'inventory': {'potion': 1 if has_potion else 0},
                    'pets': [{'name': 'TestPet'}, {'name': 'OtherPet'}],
                }
                self.state = {'is_dead': True}
                self.message = ''
                self.message_time = 0.0
                self._use_item_result = 'Pet revived!'
                self._release_result = 'Pet released.'
                self._switch_result = 'Switched pet.'

            def use_item(self, item_id):
                return self._use_item_result

            def release_pet(self, index):
                return self._release_result

            def switch_pet(self, direction):
                return self._switch_result

        return MockGame(has_potion)

    # --- Construction and delegation ---

    def test_state_id_delegates_to_inner(self):
        from ascii_pet.states import DeadOverlayState
        inner = self._make_inner_state('expanded')
        overlay = DeadOverlayState(inner)
        assert overlay.state_id == 'expanded'

    def test_on_enter_delegates_to_inner(self):
        from ascii_pet.states import DeadOverlayState
        inner = self._make_inner_state()
        overlay = DeadOverlayState(inner)
        game = self._make_mock_game()
        overlay.on_enter(game, None)
        assert inner.entered is True

    def test_on_exit_delegates_to_inner(self):
        from ascii_pet.states import DeadOverlayState
        inner = self._make_inner_state()
        overlay = DeadOverlayState(inner)
        game = self._make_mock_game()
        overlay.on_exit(game, None)
        assert inner.exited is True

    def test_tick_returns_none_zero(self):
        """Dead pets don't tick — always returns (None, 0)."""
        from ascii_pet.states import DeadOverlayState
        inner = self._make_inner_state()
        overlay = DeadOverlayState(inner)
        game = self._make_mock_game()
        from ascii_pet.states import TickEvent
        result = overlay.tick(game, TickEvent(delta_hours=0.5))
        assert result == (None, 0)

    def test_handle_lan_message_delegates_to_inner(self):
        from ascii_pet.states import DeadOverlayState, LanMessageEvent
        inner = self._make_inner_state()
        overlay = DeadOverlayState(inner)
        game = self._make_mock_game()
        overlay.handle_lan_message(game, LanMessageEvent(msg_type='VISIT_REQ'))
        assert inner.lan_received == ['VISIT_REQ']

    # --- Key handling: intercepted keys ---

    def test_feed_key_returns_death_message(self):
        from ascii_pet.states import DeadOverlayState, KeyEvent
        inner = self._make_inner_state()
        overlay = DeadOverlayState(inner)
        game = self._make_mock_game()
        result = overlay.handle_key(game, KeyEvent(key='f'))
        assert result[0] == 'action'
        assert 'dead' in result[1].lower() or 'Potion' in result[1]

    def test_play_key_returns_death_message(self):
        from ascii_pet.states import DeadOverlayState, KeyEvent
        inner = self._make_inner_state()
        overlay = DeadOverlayState(inner)
        game = self._make_mock_game()
        result = overlay.handle_key(game, KeyEvent(key='p'))
        assert result[0] == 'action'
        assert 'dead' in result[1].lower() or 'Potion' in result[1]

    def test_sleep_key_returns_death_message(self):
        from ascii_pet.states import DeadOverlayState, KeyEvent
        inner = self._make_inner_state()
        overlay = DeadOverlayState(inner)
        game = self._make_mock_game()
        result = overlay.handle_key(game, KeyEvent(key='s'))
        assert result[0] == 'action'
        assert 'dead' in result[1].lower() or 'Potion' in result[1]

    def test_revive_key_with_potion(self):
        """Pressing 'r' with a Potion uses it and returns revive message."""
        from ascii_pet.states import DeadOverlayState, KeyEvent
        inner = self._make_inner_state()
        overlay = DeadOverlayState(inner)
        game = self._make_mock_game(has_potion=True)
        result = overlay.handle_key(game, KeyEvent(key='r'))
        assert result[0] == 'action'
        assert result[1] == 'Pet revived!'

    def test_revive_key_without_potion(self):
        """Pressing 'r' without a Potion returns 'No Potion available!'."""
        from ascii_pet.states import DeadOverlayState, KeyEvent
        inner = self._make_inner_state()
        overlay = DeadOverlayState(inner)
        game = self._make_mock_game(has_potion=False)
        result = overlay.handle_key(game, KeyEvent(key='r'))
        assert result[0] == 'action'
        assert 'No Potion' in result[1]

    def test_release_key_releases_dead_pet(self):
        """Pressing 'd' releases the dead pet."""
        from ascii_pet.states import DeadOverlayState, KeyEvent
        inner = self._make_inner_state()
        overlay = DeadOverlayState(inner)
        game = self._make_mock_game()
        result = overlay.handle_key(game, KeyEvent(key='d'))
        assert result[0] == 'action'
        assert result[1] == 'Pet released.'

    def test_prev_pet_key(self):
        """Pressing 'b' switches to previous pet."""
        from ascii_pet.states import DeadOverlayState, KeyEvent
        inner = self._make_inner_state()
        overlay = DeadOverlayState(inner)
        game = self._make_mock_game()
        result = overlay.handle_key(game, KeyEvent(key='b'))
        assert result[0] == 'pet_switch'
        assert result[1] == 'Switched pet.'

    def test_next_pet_key(self):
        """Pressing 'n' switches to next pet."""
        from ascii_pet.states import DeadOverlayState, KeyEvent
        inner = self._make_inner_state()
        overlay = DeadOverlayState(inner)
        game = self._make_mock_game()
        result = overlay.handle_key(game, KeyEvent(key='n'))
        assert result[0] == 'pet_switch'
        assert result[1] == 'Switched pet.'

    # --- Key handling: pass-through keys ---

    def test_mode_keys_pass_through(self):
        """Mode switching keys (l, u, a, t, c, h, Enter) pass through to inner."""
        from ascii_pet.states import DeadOverlayState, KeyEvent
        inner = self._make_inner_state()
        overlay = DeadOverlayState(inner)
        game = self._make_mock_game()
        for key in ('l', 'u', 'a', 't', 'c', 'h', '\r'):
            result = overlay.handle_key(game, KeyEvent(key=key))
            assert result == ('inner_action', key), f"Key '{key}' should pass through"

    def test_quit_key_passes_through(self):
        """'q' key passes through to inner state."""
        from ascii_pet.states import DeadOverlayState, KeyEvent
        inner = self._make_inner_state()
        overlay = DeadOverlayState(inner)
        game = self._make_mock_game()
        result = overlay.handle_key(game, KeyEvent(key='q'))
        assert result == ('inner_action', 'q')

    def test_unknown_key_passes_through(self):
        """Any other key passes through to inner state."""
        from ascii_pet.states import DeadOverlayState, KeyEvent
        inner = self._make_inner_state()
        overlay = DeadOverlayState(inner)
        game = self._make_mock_game()
        result = overlay.handle_key(game, KeyEvent(key='x'))
        assert result == ('inner_action', 'x')

    # --- Message and message_time side effects ---

    def test_intercepted_key_sets_game_message(self):
        """Intercepted keys should set game.message and game.message_time."""
        from ascii_pet.states import DeadOverlayState, KeyEvent
        inner = self._make_inner_state()
        overlay = DeadOverlayState(inner)
        game = self._make_mock_game()
        overlay.handle_key(game, KeyEvent(key='f'))
        assert game.message != ''
        assert game.message_time > 0

    def test_revive_sets_game_message(self):
        """Reviving with potion sets game.message."""
        from ascii_pet.states import DeadOverlayState, KeyEvent
        inner = self._make_inner_state()
        overlay = DeadOverlayState(inner)
        game = self._make_mock_game(has_potion=True)
        overlay.handle_key(game, KeyEvent(key='r'))
        assert game.message == 'Pet revived!'
        assert game.message_time > 0


# ─── Task 5: LanState and LanNameEditState ────────────────────────────────────


class _MockLanNode:
    """Mock LAN node for testing LanState.handle_lan_message()."""

    def __init__(self):
        self.node_id = 'local_node'
        self._sent = []  # list of (peer_id, msg_type, payload)

    def send_to_peer(self, peer_id, msg_type, payload):
        self._sent.append((peer_id, msg_type, payload))
        return True


class _MockGame:
    """Mock game object for LanState / LanNameEditState tests."""

    def __init__(self):
        from ascii_pet.states import StateMachine, GameState

        class _DummyState(GameState):
            @property
            def state_id(self):
                return 'compact'

            def on_enter(self, game, prev_state):
                pass

            def on_exit(self, game, next_state):
                pass

            def handle_key(self, game, event):
                return 'none', None

            def tick(self, game, event):
                return None, 0

        self.sm = StateMachine(LanState())
        # Register transitions used by LanState / LanNameEditState
        self.sm.add_transition('compact', 'expanded')
        self.sm.add_transition('compact', 'lan')
        self.sm.add_transition('expanded', 'compact')
        self.sm.add_transition('expanded', 'lan')
        self.sm.add_transition('lan', 'expanded')
        self.sm.add_transition('lan', 'lan_name_edit')
        self.sm.add_transition('lan_name_edit', 'lan')

        # LAN state
        self.lan_enabled = False
        self.lan_username = 'Player1'

        # Active sessions
        self.active_visit = None
        self.being_visited = None
        self.active_challenge = None
        self.active_gift = None
        self.active_trade = None

        # Pet data
        self.pets_data = {
            'pets': [{'name': 'MyPet', 'species': 'cat', 'rarity': 'common', 'level': 1}],
            'inventory': {'apple': 3, 'toy': 1},
        }
        self.pet_idx = 0
        self.state = {
            'is_dead': False,
            'stats': {'HUNGER': 50, 'HAPPY': 50, 'ENERGY': 50},
            'name': 'TestPet',
            'hp': 100,
            'level': 1,
        }

        # Messages
        self.message = ''
        self.message_time = 0
        self.visit_message_time = 0

        # Visitor tracking
        self.visitor_pets = []

        # Battle result
        self.battle_result = None

        # Pending trade
        self.pending_trade_req = None

        # LAN node mock
        self.lan_node = _MockLanNode()

        # Track method calls
        self._calls = []

    # ── LAN control ──
    def enable_lan(self):
        self._calls.append(('enable_lan',))
        self.lan_enabled = True
        return True

    def disable_lan(self):
        self._calls.append(('disable_lan',))
        self.lan_enabled = False
        return True

    def change_lan_username(self, name):
        self._calls.append(('change_lan_username', name))
        self.lan_username = name
        return True

    # ── LAN actions ──
    def invite_visit(self, peer_id):
        self._calls.append(('invite_visit', peer_id))
        self.active_visit = {'target': peer_id, 'start_time': time.time(), 'pet_snapshot': {}}
        return True

    def initiate_challenge(self, peer_id):
        self._calls.append(('initiate_challenge', peer_id))
        self.active_challenge = {
            'target': peer_id,
            'start_time': time.time(),
            'pet_snapshot': {
                'name': 'TestPet', 'level': 1, 'hp': 100,
                'attack': 10, 'defense': 10, 'speed': 10,
                'skills': ['tackle'],
            },
            'role': 'attacker',
        }
        return True

    def gift_item(self, peer_id, item_id, count=1):
        self._calls.append(('gift_item', peer_id, item_id, count))
        # Simulate real gift_item: set active_gift
        self.active_gift = {
            'target': peer_id,
            'item_id': item_id,
            'count': count,
            'start_time': time.time(),
        }
        return True

    def initiate_trade(self, peer_id, pet_idx):
        self._calls.append(('initiate_trade', peer_id, pet_idx))
        return True

    def heal_pet(self):
        self._calls.append(('heal_pet',))
        return True

    def end_visit(self):
        self._calls.append(('end_visit',))
        return True

    def remote_feed(self):
        self._calls.append(('remote_feed',))
        return True

    def remote_play(self):
        self._calls.append(('remote_play',))
        return True

    # ── Data accessors ──
    def get_lan_peers(self):
        return [
            {'node_id': 'peer1', 'username': 'Alice'},
            {'node_id': 'peer2', 'username': 'Bob'},
            {'node_id': 'peer3', 'username': 'Carol'},
        ]

    def get_lan_peers_page(self, page=0):
        peers = self.get_lan_peers()
        return (peers, 1, page)

    def get_inventory_list(self):
        return [
            ('apple', 'Apple', '🍎', 3, 'A juicy apple'),
            ('toy', 'Toy', '🧸', 1, 'A fun toy'),
        ]

    # ── LAN message handling helpers ──
    def handle_action(self, action):
        """Mock handle_action for visit feed/play."""
        if action == 'feed':
            self.state['stats']['HUNGER'] = min(100, self.state['stats']['HUNGER'] + 30)
            return ('Fed!', None)
        if action == 'play':
            self.state['stats']['HAPPY'] = min(100, self.state['stats']['HAPPY'] + 30)
            return ('Played!', None)
        return ('Done!', None)

    def receive_visitor(self, snapshot):
        self.visitor_pets.append(snapshot)

    def accept_challenge(self, challenge_req):
        """Mock accept_challenge: always accept."""
        return {"escaped": False, "defender_snapshot": {"name": "DefenderPet", "level": 1}}

    def apply_battle_result(self, result):
        self._calls.append(('apply_battle_result', result))

    def receive_gift(self, item_id, count):
        return {"success": True}

    def confirm_gift_sent(self, success):
        self._calls.append(('confirm_gift_sent', success))
        # Simulate real confirm_gift_sent: deduct item on success, clear active_gift
        if self.active_gift:
            if success:
                # Deduct item from inventory
                inv = self.pets_data.setdefault('inventory', {})
                item_id = self.active_gift['item_id']
                count = self.active_gift['count']
                inv[item_id] = max(0, inv.get(item_id, 0) - count)
                if inv[item_id] <= 0:
                    del inv[item_id]
            self.active_gift = None

    def execute_trade(self, payload):
        self._calls.append(('execute_trade', payload))
        # Simulate real execute_trade: replace pet and clear active_trade
        if self.active_trade:
            my_index = self.active_trade["pet_index"]
            received_pet = payload.get("pet_snapshot", {})
            if my_index < len(self.pets_data['pets']):
                self.pets_data['pets'][my_index] = received_pet
            self.active_trade = None

    def accept_trade(self, trade_req, pet_index, accepted=True):
        self._calls.append(('accept_trade', trade_req, pet_index, accepted))
        return True

    def get_lan_peers(self):
        return [
            {'node_id': f'peer{i}', 'username': f'User{i}'} for i in range(1, 12)
        ]

    def get_lan_peers_page(self):
        all_peers = self.get_lan_peers()
        page_size = 9
        total_pages = max(1, (len(all_peers) + page_size - 1) // page_size)
        start = 0 * page_size  # page 0
        end = start + page_size
        return (all_peers[start:end], total_pages, 0)

    def save(self):
        pass


class TestLanState:
    """Test LanState class."""

    def _make_lan_state(self):
        from ascii_pet.states import LanState
        return LanState()

    def _make_game(self):
        return _MockGame()

    # ── Basic properties ──

    def test_state_id(self):
        lan = self._make_lan_state()
        assert lan.state_id == 'lan'

    def test_default_submode_is_idle(self):
        lan = self._make_lan_state()
        assert lan._submode is None

    def test_default_page_is_zero(self):
        lan = self._make_lan_state()
        assert lan._page == 0

    def test_on_enter_resets_submode(self):
        lan = self._make_lan_state()
        game = self._make_game()
        lan._submode = 'visit'
        lan.on_enter(game, None)
        assert lan._submode is None

    def test_on_enter_resets_page(self):
        lan = self._make_lan_state()
        game = self._make_game()
        lan._page = 5
        lan.on_enter(game, None)
        assert lan._page == 0

    # ── Idle sub-state key handling ──

    def test_idle_l_transitions_to_expanded(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.sm.transition_to(game, lan)
        result = lan.handle_key(game, KeyEvent(key='l'))
        assert result == ('mode_change', 'expanded')

    def test_idle_o_toggles_lan_on(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.lan_enabled = False
        lan.handle_key(game, KeyEvent(key='o'))
        assert ('enable_lan',) in game._calls

    def test_idle_o_toggles_lan_off(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.lan_enabled = True
        lan.handle_key(game, KeyEvent(key='o'))
        assert ('disable_lan',) in game._calls

    def test_idle_u_transitions_to_lan_name_edit(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        result = lan.handle_key(game, KeyEvent(key='u'))
        assert result == ('mode_change', 'lan_name_edit')

    def test_idle_v_enters_visit_select(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        result = lan.handle_key(game, KeyEvent(key='v'))
        assert lan._submode == 'visit'

    def test_idle_v_blocked_if_active_visit(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_visit = True
        result = lan.handle_key(game, KeyEvent(key='v'))
        assert lan._submode is None

    def test_idle_v_blocked_if_active_challenge(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_challenge = True
        result = lan.handle_key(game, KeyEvent(key='v'))
        assert lan._submode is None

    def test_idle_c_enters_challenge_select(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        result = lan.handle_key(game, KeyEvent(key='c'))
        assert lan._submode == 'challenge'

    def test_idle_c_blocked_if_active_visit(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_visit = True
        result = lan.handle_key(game, KeyEvent(key='c'))
        assert lan._submode is None

    def test_idle_c_blocked_if_active_challenge(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_challenge = True
        result = lan.handle_key(game, KeyEvent(key='c'))
        assert lan._submode is None

    def test_idle_g_enters_gift_select(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        result = lan.handle_key(game, KeyEvent(key='g'))
        assert lan._submode == 'gift'

    def test_idle_g_blocked_if_active_gift(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_gift = True
        result = lan.handle_key(game, KeyEvent(key='g'))
        assert lan._submode is None

    def test_idle_t_enters_trade_select(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        result = lan.handle_key(game, KeyEvent(key='t'))
        assert lan._submode == 'trade'

    def test_idle_t_blocked_if_active_trade(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_trade = True
        result = lan.handle_key(game, KeyEvent(key='t'))
        assert lan._submode is None

    def test_idle_h_calls_heal_pet(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        lan.handle_key(game, KeyEvent(key='h'))
        assert ('heal_pet',) in game._calls

    def test_idle_e_calls_end_visit(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        lan.handle_key(game, KeyEvent(key='e'))
        # end_visit is called and sets a message
        assert game.message_time > 0

    def test_idle_f_calls_remote_feed_when_active_visit(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_visit = True
        lan.handle_key(game, KeyEvent(key='f'))
        assert ('remote_feed',) in game._calls

    def test_idle_f_ignored_without_active_visit(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_visit = None
        result = lan.handle_key(game, KeyEvent(key='f'))
        assert ('remote_feed',) not in game._calls

    def test_idle_p_calls_remote_play_when_active_visit(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_visit = True
        lan.handle_key(game, KeyEvent(key='p'))
        assert ('remote_play',) in game._calls

    def test_idle_p_ignored_without_active_visit(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_visit = None
        lan.handle_key(game, KeyEvent(key='p'))
        assert ('remote_play',) not in game._calls

    def test_idle_bracket_left_page_up(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        lan._page = 2
        lan.handle_key(game, KeyEvent(key='['))
        assert lan._page == 1

    def test_idle_bracket_right_page_down(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        lan._page = 0
        lan.handle_key(game, KeyEvent(key=']'))
        assert lan._page == 1

    def test_idle_page_not_below_zero(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        lan._page = 0
        lan.handle_key(game, KeyEvent(key='['))
        assert lan._page == 0

    def test_idle_q_returns_quit(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        result = lan.handle_key(game, KeyEvent(key='q'))
        assert result == ('quit', None)

    # ── Selection sub-states: visit_select ──

    def test_visit_select_number_calls_invite_visit(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        lan._submode = 'visit'
        lan.handle_key(game, KeyEvent(key='1'))
        assert ('invite_visit', 'peer1') in game._calls
        assert lan._submode is None

    def test_visit_select_q_returns_to_idle(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        lan._submode = 'visit'
        lan.handle_key(game, KeyEvent(key='q'))
        assert lan._submode is None

    def test_visit_select_esc_returns_to_idle(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        lan._submode = 'visit'
        lan.handle_key(game, KeyEvent(key='\x1b'))
        assert lan._submode is None

    def test_visit_select_invalid_number_ignored(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        lan._submode = 'visit'
        # Page 0 has 9 peers, so digit '9' selects index 8 which is valid
        # Use a page with fewer peers to test invalid digit
        game.get_lan_peers_page = lambda: (game.get_lan_peers()[:2], 1, 0)
        result = lan.handle_key(game, KeyEvent(key='3'))
        assert lan._submode is None
        assert 'Invalid' in game.message

    # ── Selection sub-states: challenge_select ──

    def test_challenge_select_number_calls_initiate_challenge(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        lan._submode = 'challenge'
        lan.handle_key(game, KeyEvent(key='2'))
        assert ('initiate_challenge', 'peer2') in game._calls
        assert lan._submode is None

    def test_challenge_select_q_returns_to_idle(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        lan._submode = 'challenge'
        lan.handle_key(game, KeyEvent(key='q'))
        assert lan._submode is None

    # ── Selection sub-states: gift_select ──

    def test_gift_select_number_stores_target_and_enters_gift_item(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        lan._submode = 'gift'
        lan.handle_key(game, KeyEvent(key='1'))
        assert lan._submode == 'gift_item'
        assert lan._submode_data.get('target_node_id') == 'peer1'

    def test_gift_select_q_returns_to_idle(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        lan._submode = 'gift'
        lan.handle_key(game, KeyEvent(key='q'))
        assert lan._submode is None

    # ── Sub-state: gift_item ──

    def test_gift_item_number_calls_gift_item(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        lan._submode = 'gift_item'
        lan._submode_data = {'target_node_id': 'peer1'}
        lan.handle_key(game, KeyEvent(key='1'))
        # First item in inventory is 'apple'
        assert ('gift_item', 'peer1', 'apple', 1) in game._calls

    def test_gift_item_sets_active_gift(self):
        """After selecting an item, active_gift should be set with gift data."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        lan._submode = 'gift_item'
        lan._submode_data = {'target_node_id': 'peer1'}
        lan.handle_key(game, KeyEvent(key='1'))
        assert game.active_gift is not None
        assert game.active_gift['target'] == 'peer1'
        assert game.active_gift['item_id'] == 'apple'
        assert game.active_gift['count'] == 1

    def test_gift_item_returns_to_idle_after_sending(self):
        """After selecting an item, submode should return to idle."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        lan._submode = 'gift_item'
        lan._submode_data = {'target_node_id': 'peer1'}
        lan.handle_key(game, KeyEvent(key='1'))
        assert lan._submode is None

    def test_gift_item_shows_waiting_message(self):
        """After sending a gift, message should say 'waiting for confirmation'."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        lan._submode = 'gift_item'
        lan._submode_data = {'target_node_id': 'peer1'}
        lan.handle_key(game, KeyEvent(key='1'))
        assert 'waiting' in game.message.lower() or 'confirm' in game.message.lower()

    def test_gift_item_q_returns_to_gift_submode(self):
        """ESC/q in gift_item should return to gift submode (player selection), NOT idle."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        lan._submode = 'gift_item'
        lan._submode_data = {'target_node_id': 'peer1'}
        lan.handle_key(game, KeyEvent(key='q'))
        assert lan._submode == 'gift'
        assert lan._submode_data.get('target_node_id') == 'peer1'

    def test_gift_item_esc_returns_to_gift_submode(self):
        """ESC in gift_item should return to gift submode (player selection), NOT idle."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        lan._submode = 'gift_item'
        lan._submode_data = {'target_node_id': 'peer1'}
        lan.handle_key(game, KeyEvent(key='\x1b'))
        assert lan._submode == 'gift'
        assert lan._submode_data.get('target_node_id') == 'peer1'

    # ── Selection sub-states: trade_select ──

    def test_trade_select_number_calls_initiate_trade(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        lan._submode = 'trade'
        lan.handle_key(game, KeyEvent(key='1'))
        assert ('initiate_trade', 'peer1', 0) in game._calls
        assert lan._submode is None

    def test_trade_select_q_returns_to_idle(self):
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        lan._submode = 'trade'
        lan.handle_key(game, KeyEvent(key='q'))
        assert lan._submode is None

    # ── Tick ──

    def test_tick_returns_none_zero(self):
        from ascii_pet.states import TickEvent
        lan = self._make_lan_state()
        game = self._make_game()
        result = lan.tick(game, TickEvent())
        assert result == (None, 0)

    # ── on_exit ──

    def test_on_exit_noop(self):
        lan = self._make_lan_state()
        game = self._make_game()
        # Should not raise
        lan.on_exit(game, None)


class TestLanNameEditState:
    """Test LanNameEditState class."""

    def _make_state(self):
        from ascii_pet.states import LanNameEditState
        return LanNameEditState()

    def _make_game(self):
        return _MockGame()

    # ── Basic properties ──

    def test_state_id(self):
        state = self._make_state()
        assert state.state_id == 'lan_name_edit'

    def test_default_input_empty(self):
        state = self._make_state()
        assert state._input == ''

    def test_on_enter_resets_input(self):
        state = self._make_state()
        game = self._make_game()
        state._input = 'OldName'
        state.on_enter(game, None)
        # on_enter now initializes from game.lan_username
        assert state._input == 'Player1'

    # ── Key handling ──

    def test_printable_char_appended(self):
        from ascii_pet.states import KeyEvent
        state = self._make_state()
        game = self._make_game()
        state.handle_key(game, KeyEvent(key='A'))
        assert state._input == 'A'

    def test_multiple_chars_appended(self):
        from ascii_pet.states import KeyEvent
        state = self._make_state()
        game = self._make_game()
        state.handle_key(game, KeyEvent(key='A'))
        state.handle_key(game, KeyEvent(key='l'))
        state.handle_key(game, KeyEvent(key='i'))
        state.handle_key(game, KeyEvent(key='c'))
        state.handle_key(game, KeyEvent(key='e'))
        assert state._input == 'Alice'

    def test_max_20_chars(self):
        from ascii_pet.states import KeyEvent
        state = self._make_state()
        game = self._make_game()
        for ch in 'abcdefghijklmnopqrst':
            state.handle_key(game, KeyEvent(key=ch))
        # 20 chars already, next should be ignored
        state.handle_key(game, KeyEvent(key='u'))
        assert len(state._input) == 20
        assert state._input == 'abcdefghijklmnopqrst'

    def test_backspace_deletes_last_char(self):
        from ascii_pet.states import KeyEvent
        state = self._make_state()
        game = self._make_game()
        state._input = 'Ab'
        state.handle_key(game, KeyEvent(key='\x08'))  # Backspace
        assert state._input == 'A'

    def test_backspace_on_empty_input_is_noop(self):
        from ascii_pet.states import KeyEvent
        state = self._make_state()
        game = self._make_game()
        state.handle_key(game, KeyEvent(key='\x08'))
        assert state._input == ''

    def test_enter_confirms_name(self):
        from ascii_pet.states import KeyEvent
        state = self._make_state()
        game = self._make_game()
        state._input = 'NewName'
        result = state.handle_key(game, KeyEvent(key='\r'))
        assert result == ('mode_change', 'lan')
        assert ('change_lan_username', 'NewName') in game._calls

    def test_enter_with_empty_input_transitions_without_call(self):
        from ascii_pet.states import KeyEvent
        state = self._make_state()
        game = self._make_game()
        result = state.handle_key(game, KeyEvent(key='\r'))
        assert result == ('mode_change', 'lan')
        # Should not call change_lan_username with empty name
        assert not any(c[0] == 'change_lan_username' for c in game._calls)

    def test_esc_cancels(self):
        from ascii_pet.states import KeyEvent
        state = self._make_state()
        game = self._make_game()
        state._input = 'Discarded'
        result = state.handle_key(game, KeyEvent(key='\x1b'))
        assert result == ('mode_change', 'lan')
        # Should NOT call change_lan_username
        assert not any(c[0] == 'change_lan_username' for c in game._calls)

    # ── Tick ──

    def test_tick_returns_none_zero(self):
        from ascii_pet.states import TickEvent
        state = self._make_state()
        game = self._make_game()
        result = state.tick(game, TickEvent())
        assert result == (None, 0)

    # ── on_exit ──

    def test_on_exit_noop(self):
        state = self._make_state()
        game = self._make_game()
        state.on_exit(game, None)


# ─── Task 6: LanState.handle_lan_message() ────────────────────────────────────


class TestLanStateHandleLanMessage:
    """Test LanState.handle_lan_message() for all LAN message types."""

    def _make_lan_state(self):
        from ascii_pet.states import LanState
        return LanState()

    def _make_game(self):
        return _MockGame()

    def _make_event(self, msg_type, payload=None):
        from ascii_pet.states import LanMessageEvent
        return LanMessageEvent(msg_type=msg_type, payload=payload or {})

    # ── VISIT_REQ ──

    def test_visit_req_sets_being_visited(self):
        lan = self._make_lan_state()
        game = self._make_game()
        snapshot = {'name': 'Fluffy', 'species': 'cat'}
        event = self._make_event('visit_req', {
            'from': 'peer1', 'from_username': 'Alice', 'pet_snapshot': snapshot,
        })
        lan.handle_lan_message(game, event)
        assert game.being_visited is not None
        assert game.being_visited['from'] == 'peer1'
        assert game.being_visited['pet_snapshot'] == snapshot

    def test_visit_req_appends_visitor_pet(self):
        lan = self._make_lan_state()
        game = self._make_game()
        snapshot = {'name': 'Fluffy', 'species': 'cat'}
        event = self._make_event('visit_req', {
            'from': 'peer1', 'from_username': 'Alice', 'pet_snapshot': snapshot,
        })
        lan.handle_lan_message(game, event)
        assert snapshot in game.visitor_pets

    def test_visit_req_sets_message(self):
        lan = self._make_lan_state()
        game = self._make_game()
        snapshot = {'name': 'Fluffy', 'species': 'cat'}
        event = self._make_event('visit_req', {
            'from': 'peer1', 'from_username': 'Alice', 'pet_snapshot': snapshot,
        })
        lan.handle_lan_message(game, event)
        assert 'Fluffy' in game.message
        assert game.message_time > 0

    # ── VISIT_FEED ──

    def test_visit_feed_executes_local_feed(self):
        lan = self._make_lan_state()
        game = self._make_game()
        before = game.state['stats']['HUNGER']
        event = self._make_event('visit_feed', {'from': 'Alice'})
        lan.handle_lan_message(game, event)
        assert game.state['stats']['HUNGER'] > before

    def test_visit_feed_sets_message(self):
        lan = self._make_lan_state()
        game = self._make_game()
        event = self._make_event('visit_feed', {'from': 'Alice'})
        lan.handle_lan_message(game, event)
        assert 'Alice' in game.message
        assert game.message_time > 0

    # ── VISIT_PLAY ──

    def test_visit_play_executes_local_play(self):
        lan = self._make_lan_state()
        game = self._make_game()
        before = game.state['stats']['HAPPY']
        event = self._make_event('visit_play', {'from': 'Bob'})
        lan.handle_lan_message(game, event)
        assert game.state['stats']['HAPPY'] > before

    def test_visit_play_sets_message(self):
        lan = self._make_lan_state()
        game = self._make_game()
        event = self._make_event('visit_play', {'from': 'Bob'})
        lan.handle_lan_message(game, event)
        assert 'Bob' in game.message
        assert game.message_time > 0

    # ── VISIT_EVENT ──

    def test_visit_event_applies_effects(self):
        lan = self._make_lan_state()
        game = self._make_game()
        before_happy = game.state['stats']['HAPPY']
        event = self._make_event('visit_event', {
            'event_type': 'play_together',
            'description': 'Pets played together!',
            'stat_effects': {'happy': 15},
        })
        lan.handle_lan_message(game, event)
        assert game.state['stats']['HAPPY'] > before_happy

    def test_visit_event_sets_message(self):
        lan = self._make_lan_state()
        game = self._make_game()
        event = self._make_event('visit_event', {
            'event_type': 'play_together',
            'description': 'Pets played together!',
            'stat_effects': {'happy': 15},
        })
        lan.handle_lan_message(game, event)
        assert 'Pets played together!' in game.message

    # ── VISIT_END ──

    def test_visit_end_clears_active_visit(self):
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_visit = {'target': 'peer1', 'start_time': 0}
        event = self._make_event('visit_end', {})
        lan.handle_lan_message(game, event)
        assert game.active_visit is None
        assert 'ended' in game.message.lower()

    def test_visit_end_clears_being_visited(self):
        lan = self._make_lan_state()
        game = self._make_game()
        game.being_visited = {'from': 'peer1', 'pet_snapshot': {'name': 'Fluffy'}}
        game.visitor_pets = [{'name': 'Fluffy'}]
        event = self._make_event('visit_end', {})
        lan.handle_lan_message(game, event)
        assert game.being_visited is None
        assert len(game.visitor_pets) == 0

    # ── VISIT_DATA (legacy) ──

    def test_visit_data_calls_receive_visitor(self):
        lan = self._make_lan_state()
        game = self._make_game()
        snapshot = {'name': 'OldPet'}
        event = self._make_event('visit_data', snapshot)
        lan.handle_lan_message(game, event)
        assert snapshot in game.visitor_pets

    def test_visit_data_sets_message(self):
        lan = self._make_lan_state()
        game = self._make_game()
        event = self._make_event('visit_data', {'name': 'OldPet'})
        lan.handle_lan_message(game, event)
        assert 'OldPet' in game.message

    # ── VISIT_LEAVE (legacy) ──

    def test_visit_leave_removes_visitor_by_name(self):
        lan = self._make_lan_state()
        game = self._make_game()
        game.visitor_pets = [{'name': 'Fluffy'}, {'name': 'Spot'}]
        event = self._make_event('visit_leave', {'pet_name': 'Fluffy'})
        lan.handle_lan_message(game, event)
        assert len(game.visitor_pets) == 1
        assert game.visitor_pets[0]['name'] == 'Spot'

    # ── CHALLENGE_REQ ──

    def test_challenge_req_sends_ack(self):
        lan = self._make_lan_state()
        game = self._make_game()
        event = self._make_event('challenge_req', {
            'from': 'peer1', 'from_username': 'Alice',
        })
        lan.handle_lan_message(game, event)
        # Should have sent a CHALLENGE_ACK
        assert len(game.lan_node._sent) == 1
        peer_id, msg_type, payload = game.lan_node._sent[0]
        assert peer_id == 'peer1'
        assert msg_type == 'challenge_ack'

    def test_challenge_req_sets_message(self):
        lan = self._make_lan_state()
        game = self._make_game()
        event = self._make_event('challenge_req', {
            'from': 'peer1', 'from_username': 'Alice',
        })
        lan.handle_lan_message(game, event)
        assert game.message_time > 0

    # ── CHALLENGE_ACK (escaped) ──

    def test_challenge_ack_escaped_clears_challenge(self):
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_challenge = {'target': 'peer1', 'pet_snapshot': {'name': 'MyPet'}}
        event = self._make_event('challenge_ack', {
            'escaped': True, 'from': 'peer1',
        })
        lan.handle_lan_message(game, event)
        assert game.active_challenge is None
        assert 'escaped' in game.message.lower() or 'Escaped' in game.message

    # ── CHALLENGE_ACK (not escaped) ──

    def test_challenge_ack_not_escaped_simulates_battle(self):
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_challenge = {
            'target': 'peer1',
            'pet_snapshot': {'name': 'MyPet', 'level': 1, 'hp': 100, 'attack': 10, 'defense': 10, 'speed': 10, 'skills': ['tackle']},
        }
        event = self._make_event('challenge_ack', {
            'escaped': False,
            'defender_snapshot': {'name': 'DefPet', 'level': 1, 'hp': 100, 'attack': 10, 'defense': 10, 'speed': 10, 'skills': ['tackle']},
            'from': 'peer1',
        })
        lan.handle_lan_message(game, event)
        # Should have sent a CHALLENGE_RESULT
        assert len(game.lan_node._sent) == 1
        peer_id, msg_type, payload = game.lan_node._sent[0]
        assert peer_id == 'peer1'
        assert msg_type == 'challenge_result'
        # battle_result should be set
        assert game.battle_result is not None
        assert game.message_time > 0

    # ── CHALLENGE_RESULT ──

    def test_challenge_result_applies_battle_result(self):
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_challenge = {'role': 'defender', 'target': 'peer1'}
        event = self._make_event('challenge_result', {
            'winner': 'defender',
            'attacker_snapshot': {'name': 'AtkPet', 'level': 1, 'hp': 100, 'attack': 10, 'defense': 10, 'speed': 10, 'skills': ['tackle']},
            'defender_snapshot': {'name': 'DefPet', 'level': 1, 'hp': 100, 'attack': 10, 'defense': 10, 'speed': 10, 'skills': ['tackle']},
            'seed': 42,
            'hp_loss_winner': 0,
            'hp_loss_loser': 25,
        })
        lan.handle_lan_message(game, event)
        assert game.battle_result is not None
        assert game.message_time > 0

    # ── GIFT_ITEM ──

    def test_gift_item_receives_and_sends_ack(self):
        lan = self._make_lan_state()
        game = self._make_game()
        event = self._make_event('gift_item', {
            'from': 'peer1', 'from_username': 'Alice', 'item_id': 'apple', 'count': 1,
        })
        lan.handle_lan_message(game, event)
        # Should have sent a GIFT_ACK
        assert len(game.lan_node._sent) == 1
        peer_id, msg_type, payload = game.lan_node._sent[0]
        assert peer_id == 'peer1'
        assert msg_type == 'gift_ack'
        assert 'Alice' in game.message or 'apple' in game.message

    # ── GIFT_ACK ──

    def test_gift_ack_success_calls_confirm_gift_sent(self):
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_gift = {
            'target': 'peer1', 'item_id': 'apple', 'count': 1, 'start_time': time.time(),
        }
        event = self._make_event('gift_ack', {'success': True, 'from': 'peer1'})
        lan.handle_lan_message(game, event)
        assert ('confirm_gift_sent', True) in game._calls

    def test_gift_ack_success_deducts_item_from_sender(self):
        """GIFT_ACK success=True should deduct the item from sender's inventory."""
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_gift = {
            'target': 'peer1', 'item_id': 'apple', 'count': 1, 'start_time': time.time(),
        }
        before_count = game.pets_data['inventory']['apple']
        event = self._make_event('gift_ack', {'success': True, 'from': 'peer1'})
        lan.handle_lan_message(game, event)
        assert game.pets_data['inventory']['apple'] == before_count - 1

    def test_gift_ack_success_clears_active_gift(self):
        """GIFT_ACK success=True should clear active_gift."""
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_gift = {
            'target': 'peer1', 'item_id': 'apple', 'count': 1, 'start_time': time.time(),
        }
        event = self._make_event('gift_ack', {'success': True, 'from': 'peer1'})
        lan.handle_lan_message(game, event)
        assert game.active_gift is None

    def test_gift_ack_success_shows_delivered_message(self):
        """GIFT_ACK success=True should show 'Gift delivered!' message."""
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_gift = {
            'target': 'peer1', 'item_id': 'apple', 'count': 1, 'start_time': time.time(),
        }
        event = self._make_event('gift_ack', {'success': True, 'from': 'peer1'})
        lan.handle_lan_message(game, event)
        assert 'delivered' in game.message.lower()

    def test_gift_ack_failure_does_not_deduct_item(self):
        """GIFT_ACK success=False should NOT deduct item from sender's inventory."""
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_gift = {
            'target': 'peer1', 'item_id': 'apple', 'count': 1, 'start_time': time.time(),
        }
        before_count = game.pets_data['inventory']['apple']
        event = self._make_event('gift_ack', {'success': False, 'from': 'peer1'})
        lan.handle_lan_message(game, event)
        assert game.pets_data['inventory']['apple'] == before_count

    def test_gift_ack_failure_clears_active_gift(self):
        """GIFT_ACK success=False should still clear active_gift."""
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_gift = {
            'target': 'peer1', 'item_id': 'apple', 'count': 1, 'start_time': time.time(),
        }
        event = self._make_event('gift_ack', {'success': False, 'from': 'peer1'})
        lan.handle_lan_message(game, event)
        assert game.active_gift is None

    def test_gift_ack_failure_shows_failure_message(self):
        """GIFT_ACK success=False should show inventory full message."""
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_gift = {
            'target': 'peer1', 'item_id': 'apple', 'count': 1, 'start_time': time.time(),
        }
        event = self._make_event('gift_ack', {'success': False, 'from': 'peer1'})
        lan.handle_lan_message(game, event)
        assert 'inventory' in game.message.lower() or 'full' in game.message.lower() or 'failed' in game.message.lower()

    # ── TRADE_REQ ──

    def test_trade_req_stores_pending_and_sets_message(self):
        lan = self._make_lan_state()
        game = self._make_game()
        event = self._make_event('trade_req', {
            'from': 'peer1', 'from_username': 'Alice',
        })
        lan.handle_lan_message(game, event)
        assert game.pending_trade_req is not None
        assert 'Alice' in game.message
        assert game.message_time > 0

    # ── TRADE_ACK (accepted) ──

    def test_trade_ack_accepted_sends_confirm_and_executes(self):
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_trade = {'target': 'peer1', 'pet_index': 0}
        game.pets_data = {'pets': [{'name': 'MyPet'}]}
        event = self._make_event('trade_ack', {
            'accepted': True, 'from': 'peer1', 'pet_snapshot': {'name': 'TheirPet'},
        })
        lan.handle_lan_message(game, event)
        # Should have sent TRADE_CONFIRM
        assert len(game.lan_node._sent) == 1
        peer_id, msg_type, payload = game.lan_node._sent[0]
        assert msg_type == 'trade_confirm'
        # Should have called execute_trade
        assert any(c[0] == 'execute_trade' for c in game._calls)

    # ── TRADE_ACK (rejected) ──

    def test_trade_ack_rejected_clears_trade(self):
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_trade = {'target': 'peer1', 'pet_index': 0}
        event = self._make_event('trade_ack', {
            'accepted': False, 'from': 'peer1',
        })
        lan.handle_lan_message(game, event)
        assert game.active_trade is None
        assert 'rejected' in game.message.lower() or 'Rejected' in game.message

    # ── TRADE_CONFIRM ──

    def test_trade_confirm_executes_trade(self):
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_trade = {'target': 'peer1', 'pet_index': 0}
        event = self._make_event('trade_confirm', {
            'pet_snapshot': {'name': 'TheirPet'}, 'from': 'peer1',
        })
        lan.handle_lan_message(game, event)
        assert any(c[0] == 'execute_trade' for c in game._calls)
        assert 'complete' in game.message.lower() or 'Complete' in game.message

    # ── Unknown message type ──

    def test_unknown_message_type_is_noop(self):
        lan = self._make_lan_state()
        game = self._make_game()
        event = self._make_event('unknown_type', {})
        # Should not raise
        lan.handle_lan_message(game, event)
        assert game.message == ''  # no message set


# ─── Challenge flow integration tests ────────────────────────────────────────


class TestChallengeFlow:
    """Test the full challenge flow: initiate → ACK → battle result.

    These tests verify that after the state machine refactoring,
    the challenge flow works end-to-end.
    """

    def _make_lan_state(self):
        from ascii_pet.states import LanState
        return LanState()

    def _make_game(self):
        return _MockGame()

    def _make_event(self, msg_type, payload=None):
        from ascii_pet.states import LanMessageEvent
        return LanMessageEvent(msg_type=msg_type, payload=payload or {})

    # ── Fix 1: Challenge selection sets active_challenge and shows progress ──

    def test_challenge_select_sets_active_challenge_on_success(self):
        """After selecting a challenge target, game.active_challenge should be set."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        lan._submode = 'challenge'
        # initiate_challenge in _MockGame returns True but does NOT set active_challenge
        # The _handle_selection code should set it after a successful initiate_challenge
        lan.handle_key(game, KeyEvent(key='2'))
        assert game.active_challenge is not None

    def test_challenge_select_shows_progress_message(self):
        """After selecting a challenge target, message should indicate challenge in progress."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        lan._submode = 'challenge'
        lan.handle_key(game, KeyEvent(key='2'))
        assert game.message is not None
        assert 'progress' in game.message.lower() or 'Challenge' in game.message

    def test_challenge_select_stays_in_lan_idle(self):
        """After selecting a challenge target, submode should be None (idle), not expanded."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        lan._submode = 'challenge'
        lan.handle_key(game, KeyEvent(key='2'))
        assert lan._submode is None

    # ── Fix 2: CHALLENGE_ACK (not escaped) triggers battle ──

    def test_challenge_ack_triggers_battle_and_sends_result(self):
        """When CHALLENGE_ACK with escaped=False arrives, battle is simulated
        and CHALLENGE_RESULT is sent to the opponent."""
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_challenge = {
            'target': 'peer1',
            'start_time': time.time(),
            'pet_snapshot': {
                'name': 'MyPet', 'level': 1, 'hp': 100,
                'attack': 10, 'defense': 10, 'speed': 10,
                'skills': ['tackle'],
            },
            'role': 'attacker',
        }
        event = self._make_event('challenge_ack', {
            'escaped': False,
            'defender_snapshot': {
                'name': 'DefPet', 'level': 1, 'hp': 100,
                'attack': 10, 'defense': 10, 'speed': 10,
                'skills': ['tackle'],
            },
            'from': 'peer1',
        })
        lan.handle_lan_message(game, event)
        # Should have sent CHALLENGE_RESULT
        assert len(game.lan_node._sent) == 1
        peer_id, msg_type, payload = game.lan_node._sent[0]
        assert msg_type == 'challenge_result'
        assert 'winner' in payload

    def test_challenge_ack_applies_battle_result(self):
        """When CHALLENGE_ACK with escaped=False arrives, apply_battle_result is called."""
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_challenge = {
            'target': 'peer1',
            'start_time': time.time(),
            'pet_snapshot': {
                'name': 'MyPet', 'level': 1, 'hp': 100,
                'attack': 10, 'defense': 10, 'speed': 10,
                'skills': ['tackle'],
            },
            'role': 'attacker',
        }
        event = self._make_event('challenge_ack', {
            'escaped': False,
            'defender_snapshot': {
                'name': 'DefPet', 'level': 1, 'hp': 100,
                'attack': 10, 'defense': 10, 'speed': 10,
                'skills': ['tackle'],
            },
            'from': 'peer1',
        })
        lan.handle_lan_message(game, event)
        # apply_battle_result should have been called
        assert any(c[0] == 'apply_battle_result' for c in game._calls)

    def test_challenge_ack_sets_battle_result(self):
        """When CHALLENGE_ACK with escaped=False arrives, game.battle_result is set."""
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_challenge = {
            'target': 'peer1',
            'start_time': time.time(),
            'pet_snapshot': {
                'name': 'MyPet', 'level': 1, 'hp': 100,
                'attack': 10, 'defense': 10, 'speed': 10,
                'skills': ['tackle'],
            },
            'role': 'attacker',
        }
        event = self._make_event('challenge_ack', {
            'escaped': False,
            'defender_snapshot': {
                'name': 'DefPet', 'level': 1, 'hp': 100,
                'attack': 10, 'defense': 10, 'speed': 10,
                'skills': ['tackle'],
            },
            'from': 'peer1',
        })
        lan.handle_lan_message(game, event)
        assert game.battle_result is not None

    def test_challenge_ack_clears_active_challenge(self):
        """When CHALLENGE_ACK with escaped=False arrives, game.active_challenge is cleared."""
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_challenge = {
            'target': 'peer1',
            'start_time': time.time(),
            'pet_snapshot': {
                'name': 'MyPet', 'level': 1, 'hp': 100,
                'attack': 10, 'defense': 10, 'speed': 10,
                'skills': ['tackle'],
            },
            'role': 'attacker',
        }
        event = self._make_event('challenge_ack', {
            'escaped': False,
            'defender_snapshot': {
                'name': 'DefPet', 'level': 1, 'hp': 100,
                'attack': 10, 'defense': 10, 'speed': 10,
                'skills': ['tackle'],
            },
            'from': 'peer1',
        })
        lan.handle_lan_message(game, event)
        assert game.active_challenge is None

    # ── Fix 3: CHALLENGE_RESULT for the challenged (defender) party ──

    def test_challenge_result_defender_re_simulates_battle(self):
        """When CHALLENGE_RESULT arrives for the defender, battle is re-simulated locally."""
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_challenge = {
            'role': 'defender',
            'target': 'peer1',
            'start_time': time.time(),
            'pet_snapshot': {
                'name': 'DefPet', 'level': 1, 'hp': 100,
                'attack': 10, 'defense': 10, 'speed': 10,
                'skills': ['tackle'],
            },
        }
        event = self._make_event('challenge_result', {
            'winner': 'defender',
            'attacker_snapshot': {
                'name': 'AtkPet', 'level': 1, 'hp': 100,
                'attack': 10, 'defense': 10, 'speed': 10,
                'skills': ['tackle'],
            },
            'defender_snapshot': {
                'name': 'DefPet', 'level': 1, 'hp': 100,
                'attack': 10, 'defense': 10, 'speed': 10,
                'skills': ['tackle'],
            },
            'seed': 42,
            'hp_loss_winner': 5,
            'hp_loss_loser': 25,
        })
        lan.handle_lan_message(game, event)
        # battle_result should be set (from local re-simulation)
        assert game.battle_result is not None

    def test_challenge_result_defender_applies_result(self):
        """When CHALLENGE_RESULT arrives for the defender, apply_battle_result is called."""
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_challenge = {
            'role': 'defender',
            'target': 'peer1',
            'start_time': time.time(),
            'pet_snapshot': {
                'name': 'DefPet', 'level': 1, 'hp': 100,
                'attack': 10, 'defense': 10, 'speed': 10,
                'skills': ['tackle'],
            },
        }
        event = self._make_event('challenge_result', {
            'winner': 'defender',
            'attacker_snapshot': {
                'name': 'AtkPet', 'level': 1, 'hp': 100,
                'attack': 10, 'defense': 10, 'speed': 10,
                'skills': ['tackle'],
            },
            'defender_snapshot': {
                'name': 'DefPet', 'level': 1, 'hp': 100,
                'attack': 10, 'defense': 10, 'speed': 10,
                'skills': ['tackle'],
            },
            'seed': 42,
            'hp_loss_winner': 5,
            'hp_loss_loser': 25,
        })
        lan.handle_lan_message(game, event)
        assert any(c[0] == 'apply_battle_result' for c in game._calls)

    def test_challenge_result_defender_clears_active_challenge(self):
        """When CHALLENGE_RESULT arrives for the defender, active_challenge is cleared."""
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_challenge = {
            'role': 'defender',
            'target': 'peer1',
            'start_time': time.time(),
            'pet_snapshot': {
                'name': 'DefPet', 'level': 1, 'hp': 100,
                'attack': 10, 'defense': 10, 'speed': 10,
                'skills': ['tackle'],
            },
        }
        event = self._make_event('challenge_result', {
            'winner': 'defender',
            'attacker_snapshot': {
                'name': 'AtkPet', 'level': 1, 'hp': 100,
                'attack': 10, 'defense': 10, 'speed': 10,
                'skills': ['tackle'],
            },
            'defender_snapshot': {
                'name': 'DefPet', 'level': 1, 'hp': 100,
                'attack': 10, 'defense': 10, 'speed': 10,
                'skills': ['tackle'],
            },
            'seed': 42,
            'hp_loss_winner': 5,
            'hp_loss_loser': 25,
        })
        lan.handle_lan_message(game, event)
        assert game.active_challenge is None

    # ── Fix 4: battle_result dismissal in handle_key ──

    def test_battle_result_dismissed_by_any_key(self):
        """When battle_result is set, any key press should clear it."""
        from ascii_pet.core import PetGame
        import tempfile
        from pathlib import Path
        # Create a real PetGame with a temp directory
        with tempfile.TemporaryDirectory() as tmpdir:
            game = PetGame(uid='test-challenge-dismiss', data_dir=Path(tmpdir))
            game.battle_result = {'winner': 'MyPet', 'log': [], 'hp_loss_winner': 0, 'hp_loss_loser': 25}
            result = game.handle_key('x')
            assert game.battle_result is None
            assert result == ('action', 'dismiss')

    # ── Fix 5: Challenge timeout ──

    def test_challenge_timeout_clears_active_challenge(self):
        """_tick_challenge_timeout should clear active_challenge after 30 seconds."""
        from ascii_pet.core import PetGame
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            game = PetGame(uid='test-challenge-timeout', data_dir=Path(tmpdir))
            game.active_challenge = {
                'target': 'peer1',
                'start_time': time.time() - 31,  # 31 seconds ago
                'pet_snapshot': {'name': 'MyPet'},
                'role': 'attacker',
            }
            game._tick_challenge_timeout()
            assert game.active_challenge is None
            assert game.message is not None

    def test_challenge_timeout_not_triggered_within_30s(self):
        """_tick_challenge_timeout should NOT clear active_challenge within 30 seconds."""
        from ascii_pet.core import PetGame
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            game = PetGame(uid='test-challenge-notimeout', data_dir=Path(tmpdir))
            game.active_challenge = {
                'target': 'peer1',
                'start_time': time.time() - 10,  # 10 seconds ago
                'pet_snapshot': {'name': 'MyPet'},
                'role': 'attacker',
            }
            game._tick_challenge_timeout()
            assert game.active_challenge is not None


# ─── Visit flow integration tests ────────────────────────────────────────────


class TestVisitAutoSwitch:
    """Test that visit selection auto-transitions to ExpandedState.

    After a successful invite_visit, the game should:
    1. Set game.active_visit (done by invite_visit in core.py)
    2. Auto-transition to ExpandedState so the user can interact
    """

    def _make_lan_state(self):
        from ascii_pet.states import LanState
        return LanState()

    def _make_game(self):
        return _MockGame()

    def test_visit_select_auto_transitions_to_expanded(self):
        """After successful invite_visit, should auto-transition to ExpandedState."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        lan._submode = 'visit'
        result = lan.handle_key(game, KeyEvent(key='1'))
        assert game.sm.current_state_id == 'expanded'
        assert result == ('mode_change', 'expanded')

    def test_visit_select_sets_active_visit(self):
        """After successful invite_visit, game.active_visit should be set."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        lan._submode = 'visit'
        lan.handle_key(game, KeyEvent(key='1'))
        assert game.active_visit is not None
        assert game.active_visit.get('target') == 'peer1'

    def test_visit_select_stays_in_lan_on_failure(self):
        """If invite_visit fails, should stay in LanState (not transition)."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        # Make invite_visit fail
        game.invite_visit = lambda peer_id: False
        lan._submode = 'visit'
        result = lan.handle_key(game, KeyEvent(key='1'))
        assert game.sm.current_state_id == 'lan'
        assert result[0] == 'action'

    def test_visit_select_invalid_number_stays_in_lan(self):
        """Invalid selection should stay in LanState."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.get_lan_peers_page = lambda: (game.get_lan_peers()[:2], 1, 0)
        lan._submode = 'visit'
        result = lan.handle_key(game, KeyEvent(key='9'))
        assert game.sm.current_state_id == 'lan'


class TestExpandedStateVisitKeys:
    """Test that ExpandedState handles visit operation keys when a visit is active.

    When game.active_visit is set:
    - 'f' key → remote_feed (not local feed)
    - 'p' key → remote_play (not local play)
    - 'e' key → end_visit (not export)

    When game.being_visited is set:
    - 'e' key → end_visit
    """

    def test_f_key_calls_remote_feed_when_active_visit(self):
        """When active_visit exists, 'f' key should call remote_feed."""
        game = _make_mock_game('expanded')
        game.active_visit = {'target': 'peer1', 'start_time': time.time()}
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='f'))
        game.remote_feed.assert_called_once()
        game.handle_action.assert_not_called()

    def test_f_key_calls_normal_feed_without_active_visit(self):
        """Without active_visit, 'f' key should call handle_action('feed')."""
        game = _make_mock_game('expanded')
        game.active_visit = None
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='f'))
        game.handle_action.assert_called_once_with('feed')
        game.remote_feed.assert_not_called()

    def test_p_key_calls_remote_play_when_active_visit(self):
        """When active_visit exists, 'p' key should call remote_play."""
        game = _make_mock_game('expanded')
        game.active_visit = {'target': 'peer1', 'start_time': time.time()}
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='p'))
        game.remote_play.assert_called_once()
        game.handle_action.assert_not_called()

    def test_p_key_calls_normal_play_without_active_visit(self):
        """Without active_visit, 'p' key should call handle_action('play')."""
        game = _make_mock_game('expanded')
        game.active_visit = None
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='p'))
        game.handle_action.assert_called_once_with('play')
        game.remote_play.assert_not_called()

    def test_e_key_calls_end_visit_when_active_visit(self):
        """When active_visit exists, 'e' key should call end_visit."""
        game = _make_mock_game('expanded')
        game.active_visit = {'target': 'peer1', 'start_time': time.time()}
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='e'))
        game.end_visit.assert_called_once()

    def test_e_key_calls_end_visit_when_being_visited(self):
        """When being_visited exists, 'e' key should call end_visit."""
        game = _make_mock_game('expanded')
        game.being_visited = {'from': 'peer1', 'start_time': time.time()}
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='e'))
        game.end_visit.assert_called_once()

    def test_e_key_exports_without_visit(self):
        """Without active_visit or being_visited, 'e' key should export."""
        game = _make_mock_game('expanded')
        game.active_visit = None
        game.being_visited = None
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='e'))
        assert result == ('export', None)
        game.end_visit.assert_not_called()

    def test_remote_feed_sets_message(self):
        """Remote feed should set game.message."""
        game = _make_mock_game('expanded')
        game.active_visit = {'target': 'peer1', 'start_time': time.time()}
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='f'))
        assert game.message_time > 0
        assert result[0] == 'action'

    def test_remote_play_sets_message(self):
        """Remote play should set game.message."""
        game = _make_mock_game('expanded')
        game.active_visit = {'target': 'peer1', 'start_time': time.time()}
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='p'))
        assert game.message_time > 0
        assert result[0] == 'action'

    def test_end_visit_sets_message(self):
        """End visit should set game.message."""
        game = _make_mock_game('expanded')
        game.active_visit = {'target': 'peer1', 'start_time': time.time()}
        s = game.sm.current_state
        result = s.handle_key(game, KeyEvent(key='e'))
        assert game.message_time > 0
        assert result[0] == 'action'


# ─── Trade flow integration tests ─────────────────────────────────────────────


class TestTradeFlow:
    """Test the full trade flow: initiate → ACK → CONFIRM.

    These tests verify that after the state machine refactoring,
    the trade flow works end-to-end.
    """

    def _make_lan_state(self):
        from ascii_pet.states import LanState
        return LanState()

    def _make_game(self):
        return _MockGame()

    def _make_event(self, msg_type, payload=None):
        from ascii_pet.states import LanMessageEvent
        return LanMessageEvent(msg_type=msg_type, payload=payload or {})

    # ── Fix 1: Trade selection sets active_trade and shows progress ──

    def test_trade_select_sets_active_trade_on_success(self):
        """After selecting a trade target, game.active_trade should be set."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        lan._submode = 'trade'
        # initiate_trade in _MockGame returns True but does NOT set active_trade
        # The _handle_selection code should set it after a successful initiate_trade
        lan.handle_key(game, KeyEvent(key='1'))
        assert game.active_trade is not None
        assert game.active_trade.get('target') == 'peer1'
        assert game.active_trade.get('pet_index') == 0
        assert game.active_trade.get('role') == 'initiator'

    def test_trade_select_message_includes_waiting(self):
        """After selecting a trade target, message should indicate waiting for response."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        lan._submode = 'trade'
        lan.handle_key(game, KeyEvent(key='1'))
        assert game.message is not None
        assert 'waiting' in game.message.lower() or 'Waiting' in game.message

    def test_trade_select_returns_to_idle(self):
        """After selecting a trade target, submode should be None (idle)."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        lan._submode = 'trade'
        lan.handle_key(game, KeyEvent(key='1'))
        assert lan._submode is None

    # ── Fix 2: TRADE_ACK(accepted=True) sends CONFIRM and executes trade ──

    def test_trade_ack_accepted_sends_trade_confirm(self):
        """When TRADE_ACK with accepted=True arrives, TRADE_CONFIRM should be sent."""
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_trade = {'target': 'peer1', 'pet_index': 0, 'start_time': time.time(), 'role': 'initiator'}
        event = self._make_event('trade_ack', {
            'accepted': True, 'from': 'peer1', 'pet_snapshot': {'name': 'TheirPet'},
        })
        lan.handle_lan_message(game, event)
        # Should have sent TRADE_CONFIRM
        assert len(game.lan_node._sent) == 1
        peer_id, msg_type, payload = game.lan_node._sent[0]
        assert peer_id == 'peer1'
        assert msg_type == 'trade_confirm'
        assert 'pet_snapshot' in payload

    def test_trade_ack_accepted_executes_trade(self):
        """When TRADE_ACK with accepted=True arrives, execute_trade should be called."""
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_trade = {'target': 'peer1', 'pet_index': 0, 'start_time': time.time(), 'role': 'initiator'}
        event = self._make_event('trade_ack', {
            'accepted': True, 'from': 'peer1', 'pet_snapshot': {'name': 'TheirPet'},
        })
        lan.handle_lan_message(game, event)
        assert any(c[0] == 'execute_trade' for c in game._calls)

    def test_trade_ack_accepted_clears_active_trade(self):
        """When TRADE_ACK with accepted=True arrives, active_trade should be cleared."""
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_trade = {'target': 'peer1', 'pet_index': 0, 'start_time': time.time(), 'role': 'initiator'}
        event = self._make_event('trade_ack', {
            'accepted': True, 'from': 'peer1', 'pet_snapshot': {'name': 'TheirPet'},
        })
        lan.handle_lan_message(game, event)
        assert game.active_trade is None

    def test_trade_ack_accepted_shows_complete_message(self):
        """When TRADE_ACK with accepted=True arrives, message should indicate completion."""
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_trade = {'target': 'peer1', 'pet_index': 0, 'start_time': time.time(), 'role': 'initiator'}
        event = self._make_event('trade_ack', {
            'accepted': True, 'from': 'peer1', 'pet_snapshot': {'name': 'TheirPet'},
        })
        lan.handle_lan_message(game, event)
        assert 'complete' in game.message.lower() or 'Complete' in game.message

    # ── Fix 3: TRADE_ACK(accepted=False) clears trade state ──

    def test_trade_ack_rejected_clears_active_trade(self):
        """When TRADE_ACK with accepted=False arrives, active_trade should be cleared."""
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_trade = {'target': 'peer1', 'pet_index': 0, 'start_time': time.time(), 'role': 'initiator'}
        event = self._make_event('trade_ack', {
            'accepted': False, 'from': 'peer1',
        })
        lan.handle_lan_message(game, event)
        assert game.active_trade is None

    def test_trade_ack_rejected_shows_rejected_message(self):
        """When TRADE_ACK with accepted=False arrives, message should indicate rejection."""
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_trade = {'target': 'peer1', 'pet_index': 0, 'start_time': time.time(), 'role': 'initiator'}
        event = self._make_event('trade_ack', {
            'accepted': False, 'from': 'peer1',
        })
        lan.handle_lan_message(game, event)
        assert 'rejected' in game.message.lower() or 'Rejected' in game.message

    # ── Fix 4: TRADE_CONFIRM executes the trade ──

    def test_trade_confirm_executes_trade(self):
        """When TRADE_CONFIRM arrives, execute_trade should be called."""
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_trade = {'target': 'peer1', 'pet_index': 0, 'start_time': time.time(), 'role': 'receiver'}
        event = self._make_event('trade_confirm', {
            'pet_snapshot': {'name': 'TheirPet'}, 'from': 'peer1',
        })
        lan.handle_lan_message(game, event)
        assert any(c[0] == 'execute_trade' for c in game._calls)

    def test_trade_confirm_clears_active_trade(self):
        """When TRADE_CONFIRM arrives, active_trade should be cleared."""
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_trade = {'target': 'peer1', 'pet_index': 0, 'start_time': time.time(), 'role': 'receiver'}
        event = self._make_event('trade_confirm', {
            'pet_snapshot': {'name': 'TheirPet'}, 'from': 'peer1',
        })
        lan.handle_lan_message(game, event)
        assert game.active_trade is None

    def test_trade_confirm_shows_complete_message(self):
        """When TRADE_CONFIRM arrives, message should indicate completion."""
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_trade = {'target': 'peer1', 'pet_index': 0, 'start_time': time.time(), 'role': 'receiver'}
        event = self._make_event('trade_confirm', {
            'pet_snapshot': {'name': 'TheirPet'}, 'from': 'peer1',
        })
        lan.handle_lan_message(game, event)
        assert 'complete' in game.message.lower() or 'Complete' in game.message

    # ── Fix 5: Trade timeout ──

    def test_trade_timeout_clears_active_trade(self):
        """check_trade_timeout should clear active_trade after 30 seconds."""
        from ascii_pet.core import PetGame
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            game = PetGame(uid='test-trade-timeout', data_dir=Path(tmpdir))
            game.active_trade = {
                'target': 'peer1',
                'pet_index': 0,
                'start_time': time.time() - 31,  # 31 seconds ago
                'role': 'initiator',
            }
            game.check_trade_timeout()
            assert game.active_trade is None
            assert game.message is not None

    def test_trade_timeout_not_triggered_within_30s(self):
        """check_trade_timeout should NOT clear active_trade within 30 seconds."""
        from ascii_pet.core import PetGame
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            game = PetGame(uid='test-trade-notimeout', data_dir=Path(tmpdir))
            game.active_trade = {
                'target': 'peer1',
                'pet_index': 0,
                'start_time': time.time() - 10,  # 10 seconds ago
                'role': 'initiator',
            }
            game.check_trade_timeout()
            assert game.active_trade is not None

    # ── Fix 6: pending_trade_req y/n handling ──

    def test_pending_trade_req_y_accepts_trade(self):
        """When pending_trade_req is set, pressing 'y' should accept the trade."""
        from ascii_pet.core import PetGame
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            game = PetGame(uid='test-trade-accept', data_dir=Path(tmpdir))
            game.pending_trade_req = {
                'from': 'peer1',
                'from_username': 'Alice',
                'pet_snapshot': {'name': 'TheirPet'},
            }
            # We need a lan_node mock for accept_trade to work
            game.lan_node = _MockLanNode()
            game.lan_enabled = True
            result = game.handle_key('y')
            assert game.pending_trade_req is None
            assert 'accept' in game.message.lower() or 'Accept' in game.message

    def test_pending_trade_req_n_rejects_trade(self):
        """When pending_trade_req is set, pressing 'n' should reject the trade."""
        from ascii_pet.core import PetGame
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            game = PetGame(uid='test-trade-reject', data_dir=Path(tmpdir))
            game.pending_trade_req = {
                'from': 'peer1',
                'from_username': 'Alice',
                'pet_snapshot': {'name': 'TheirPet'},
            }
            # We need a lan_node mock for accept_trade to work
            game.lan_node = _MockLanNode()
            game.lan_enabled = True
            result = game.handle_key('n')
            assert game.pending_trade_req is None
            assert 'reject' in game.message.lower() or 'Reject' in game.message


# ─── Task 6: Mutual exclusion logic ──────────────────────────────────────────


class TestLanMutualExclusion:
    """Test that v/c/g/t keys check ALL five active states before entering a submode.

    Each of the four operations (visit, challenge, gift, trade) must check:
    - active_visit
    - being_visited
    - active_challenge
    - active_gift
    - active_trade

    If any is set, the operation should be blocked with an appropriate message.
    """

    def _make_lan_state(self):
        from ascii_pet.states import LanState
        return LanState()

    def _make_game(self):
        return _MockGame()

    # ── 'v' key: visit ──

    def test_v_blocked_if_active_gift(self):
        """'v' should be blocked when active_gift is set."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_gift = {'target': 'peer1', 'item_id': 'apple', 'count': 1, 'start_time': time.time()}
        result = lan.handle_key(game, KeyEvent(key='v'))
        assert lan._submode is None
        assert game.message_time > 0

    def test_v_blocked_if_active_trade(self):
        """'v' should be blocked when active_trade is set."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_trade = {'target': 'peer1', 'pet_index': 0, 'start_time': time.time(), 'role': 'initiator'}
        result = lan.handle_key(game, KeyEvent(key='v'))
        assert lan._submode is None
        assert game.message_time > 0

    def test_v_blocked_if_being_visited(self):
        """'v' should be blocked when being_visited is set."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.being_visited = {'from': 'peer1', 'start_time': time.time(), 'pet_snapshot': {}}
        result = lan.handle_key(game, KeyEvent(key='v'))
        assert lan._submode is None
        assert game.message_time > 0

    def test_v_blocked_shows_message_for_active_visit(self):
        """'v' blocked by active_visit should show 'visiting' message."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_visit = {'target': 'peer1', 'start_time': time.time()}
        result = lan.handle_key(game, KeyEvent(key='v'))
        assert 'visit' in game.message.lower()

    def test_v_blocked_shows_message_for_being_visited(self):
        """'v' blocked by being_visited should show 'being visited' message."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.being_visited = {'from': 'peer1', 'start_time': time.time(), 'pet_snapshot': {}}
        result = lan.handle_key(game, KeyEvent(key='v'))
        assert 'visit' in game.message.lower()

    def test_v_blocked_shows_message_for_active_challenge(self):
        """'v' blocked by active_challenge should show 'challenge' message."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_challenge = {'target': 'peer1', 'start_time': time.time(), 'pet_snapshot': {}, 'role': 'attacker'}
        result = lan.handle_key(game, KeyEvent(key='v'))
        assert 'challenge' in game.message.lower()

    def test_v_blocked_shows_message_for_active_gift(self):
        """'v' blocked by active_gift should show 'gift' message."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_gift = {'target': 'peer1', 'item_id': 'apple', 'count': 1, 'start_time': time.time()}
        result = lan.handle_key(game, KeyEvent(key='v'))
        assert 'gift' in game.message.lower()

    def test_v_blocked_shows_message_for_active_trade(self):
        """'v' blocked by active_trade should show 'trade' message."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_trade = {'target': 'peer1', 'pet_index': 0, 'start_time': time.time(), 'role': 'initiator'}
        result = lan.handle_key(game, KeyEvent(key='v'))
        assert 'trade' in game.message.lower()

    # ── 'c' key: challenge ──

    def test_c_blocked_if_active_gift(self):
        """'c' should be blocked when active_gift is set."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_gift = {'target': 'peer1', 'item_id': 'apple', 'count': 1, 'start_time': time.time()}
        result = lan.handle_key(game, KeyEvent(key='c'))
        assert lan._submode is None
        assert game.message_time > 0

    def test_c_blocked_if_active_trade(self):
        """'c' should be blocked when active_trade is set."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_trade = {'target': 'peer1', 'pet_index': 0, 'start_time': time.time(), 'role': 'initiator'}
        result = lan.handle_key(game, KeyEvent(key='c'))
        assert lan._submode is None
        assert game.message_time > 0

    def test_c_blocked_shows_message_for_active_visit(self):
        """'c' blocked by active_visit should show 'visiting' message."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_visit = {'target': 'peer1', 'start_time': time.time()}
        result = lan.handle_key(game, KeyEvent(key='c'))
        assert 'visit' in game.message.lower()

    def test_c_blocked_shows_message_for_being_visited(self):
        """'c' blocked by being_visited should show 'being visited' message."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.being_visited = {'from': 'peer1', 'start_time': time.time(), 'pet_snapshot': {}}
        result = lan.handle_key(game, KeyEvent(key='c'))
        assert 'visit' in game.message.lower()

    def test_c_blocked_shows_message_for_active_challenge(self):
        """'c' blocked by active_challenge should show 'challenge' message."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_challenge = {'target': 'peer1', 'start_time': time.time(), 'pet_snapshot': {}, 'role': 'attacker'}
        result = lan.handle_key(game, KeyEvent(key='c'))
        assert 'challenge' in game.message.lower()

    def test_c_blocked_shows_message_for_active_gift(self):
        """'c' blocked by active_gift should show 'gift' message."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_gift = {'target': 'peer1', 'item_id': 'apple', 'count': 1, 'start_time': time.time()}
        result = lan.handle_key(game, KeyEvent(key='c'))
        assert 'gift' in game.message.lower()

    def test_c_blocked_shows_message_for_active_trade(self):
        """'c' blocked by active_trade should show 'trade' message."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_trade = {'target': 'peer1', 'pet_index': 0, 'start_time': time.time(), 'role': 'initiator'}
        result = lan.handle_key(game, KeyEvent(key='c'))
        assert 'trade' in game.message.lower()

    # ── 'g' key: gift ──

    def test_g_blocked_if_active_trade(self):
        """'g' should be blocked when active_trade is set."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_trade = {'target': 'peer1', 'pet_index': 0, 'start_time': time.time(), 'role': 'initiator'}
        result = lan.handle_key(game, KeyEvent(key='g'))
        assert lan._submode is None
        assert game.message_time > 0

    def test_g_blocked_shows_message_for_active_visit(self):
        """'g' blocked by active_visit should show 'visiting' message."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_visit = {'target': 'peer1', 'start_time': time.time()}
        result = lan.handle_key(game, KeyEvent(key='g'))
        assert 'visit' in game.message.lower()

    def test_g_blocked_shows_message_for_being_visited(self):
        """'g' blocked by being_visited should show 'being visited' message."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.being_visited = {'from': 'peer1', 'start_time': time.time(), 'pet_snapshot': {}}
        result = lan.handle_key(game, KeyEvent(key='g'))
        assert 'visit' in game.message.lower()

    def test_g_blocked_shows_message_for_active_challenge(self):
        """'g' blocked by active_challenge should show 'challenge' message."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_challenge = {'target': 'peer1', 'start_time': time.time(), 'pet_snapshot': {}, 'role': 'attacker'}
        result = lan.handle_key(game, KeyEvent(key='g'))
        assert 'challenge' in game.message.lower()

    def test_g_blocked_shows_message_for_active_gift(self):
        """'g' blocked by active_gift should show 'gift' message."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_gift = {'target': 'peer1', 'item_id': 'apple', 'count': 1, 'start_time': time.time()}
        result = lan.handle_key(game, KeyEvent(key='g'))
        assert 'gift' in game.message.lower()

    def test_g_blocked_shows_message_for_active_trade(self):
        """'g' blocked by active_trade should show 'trade' message."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_trade = {'target': 'peer1', 'pet_index': 0, 'start_time': time.time(), 'role': 'initiator'}
        result = lan.handle_key(game, KeyEvent(key='g'))
        assert 'trade' in game.message.lower()

    # ── 't' key: trade ──

    def test_t_blocked_if_active_gift(self):
        """'t' should be blocked when active_gift is set."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_gift = {'target': 'peer1', 'item_id': 'apple', 'count': 1, 'start_time': time.time()}
        result = lan.handle_key(game, KeyEvent(key='t'))
        assert lan._submode is None
        assert game.message_time > 0

    def test_t_blocked_shows_message_for_active_visit(self):
        """'t' blocked by active_visit should show 'visiting' message."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_visit = {'target': 'peer1', 'start_time': time.time()}
        result = lan.handle_key(game, KeyEvent(key='t'))
        assert 'visit' in game.message.lower()

    def test_t_blocked_shows_message_for_being_visited(self):
        """'t' blocked by being_visited should show 'being visited' message."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.being_visited = {'from': 'peer1', 'start_time': time.time(), 'pet_snapshot': {}}
        result = lan.handle_key(game, KeyEvent(key='t'))
        assert 'visit' in game.message.lower()

    def test_t_blocked_shows_message_for_active_challenge(self):
        """'t' blocked by active_challenge should show 'challenge' message."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_challenge = {'target': 'peer1', 'start_time': time.time(), 'pet_snapshot': {}, 'role': 'attacker'}
        result = lan.handle_key(game, KeyEvent(key='t'))
        assert 'challenge' in game.message.lower()

    def test_t_blocked_shows_message_for_active_gift(self):
        """'t' blocked by active_gift should show 'gift' message."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_gift = {'target': 'peer1', 'item_id': 'apple', 'count': 1, 'start_time': time.time()}
        result = lan.handle_key(game, KeyEvent(key='t'))
        assert 'gift' in game.message.lower()

    def test_t_blocked_shows_message_for_active_trade(self):
        """'t' blocked by active_trade should show 'trade' message."""
        from ascii_pet.states import KeyEvent
        lan = self._make_lan_state()
        game = self._make_game()
        game.active_trade = {'target': 'peer1', 'pet_index': 0, 'start_time': time.time(), 'role': 'initiator'}
        result = lan.handle_key(game, KeyEvent(key='t'))
        assert 'trade' in game.message.lower()
