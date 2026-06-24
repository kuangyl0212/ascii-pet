"""Event-driven state machine for game flow management.

All game inputs (key presses, LAN messages, timers) are unified as
GameEvent objects dispatched through a StateMachine to the current
GameState, which handles the event and optionally triggers transitions.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ascii_pet.i18n import _


# ─── GameEvent hierarchy ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class GameEvent:
    """Base class for all game events."""
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class KeyEvent(GameEvent):
    """A key press event."""
    key: str = ''


@dataclass(frozen=True)
class TickEvent(GameEvent):
    """A periodic tick event."""
    delta_hours: float = 0.0


@dataclass(frozen=True)
class LanMessageEvent(GameEvent):
    """A LAN network message event."""
    msg_type: str = ''
    payload: dict = field(default_factory=dict)


@dataclass(frozen=True)
class TimeoutEvent(GameEvent):
    """A timeout event (visit, challenge, gift, trade)."""
    timeout_type: str = ''


# ─── Exceptions ───────────────────────────────────────────────────────────────


class InvalidTransition(Exception):
    """Raised when an invalid state transition is attempted."""
    pass


# ─── GameState abstract base class ────────────────────────────────────────────


class GameState(ABC):
    """Abstract base class for game states.

    Each game mode (compact, expanded, lan, etc.) is a concrete subclass
    that handles its own key presses, ticks, and LAN messages.
    """

    @property
    @abstractmethod
    def state_id(self) -> str:
        """Unique identifier for this state (e.g. 'compact', 'expanded')."""

    @abstractmethod
    def on_enter(self, game: Any, prev_state: 'GameState | None') -> None:
        """Called when entering this state."""

    @abstractmethod
    def on_exit(self, game: Any, next_state: 'GameState') -> None:
        """Called when exiting this state."""

    @abstractmethod
    def handle_key(self, game: Any, event: KeyEvent) -> tuple[str, Any]:
        """Handle a key press event. Returns (action_type, detail)."""

    @abstractmethod
    def tick(self, game: Any, event: TickEvent) -> tuple[str | None, float]:
        """Handle a tick event. Returns (message, message_time)."""

    def handle_lan_message(self, game: Any, event: LanMessageEvent) -> None:
        """Handle a LAN message event. Default: ignore."""
        pass

    def handle_timeout(self, game: Any, event: TimeoutEvent) -> None:
        """Handle a timeout event. Default: ignore."""
        pass


# ─── StateMachine orchestrator ────────────────────────────────────────────────


class StateMachine:
    """Manages state transitions and event dispatch."""

    def __init__(self, initial: GameState):
        self._current: GameState = initial
        self._transitions: dict[str, set[str]] = {}

    def add_transition(self, from_id: str, to_id: str) -> None:
        """Register a valid state transition."""
        if from_id not in self._transitions:
            self._transitions[from_id] = set()
        self._transitions[from_id].add(to_id)

    def transition_to(self, game: Any, new_state: GameState) -> None:
        """Execute a state transition with validation and hooks."""
        from_id = self._current.state_id
        to_id = new_state.state_id

        # Same state transition is a no-op
        if from_id == to_id:
            return

        # Validate transition
        if to_id not in self._transitions.get(from_id, set()):
            raise InvalidTransition(
                f"Invalid transition: {from_id} -> {to_id}"
            )

        # Execute hooks: exit first, then enter
        prev = self._current
        self._current.on_exit(game, new_state)
        self._current = new_state
        new_state.on_enter(game, prev)

    def dispatch(self, game: Any, event: GameEvent) -> Any:
        """Dispatch an event to the current state."""
        if isinstance(event, KeyEvent):
            return self._current.handle_key(game, event)
        elif isinstance(event, TickEvent):
            return self._current.tick(game, event)
        elif isinstance(event, LanMessageEvent):
            return self._current.handle_lan_message(game, event)
        elif isinstance(event, TimeoutEvent):
            return self._current.handle_timeout(game, event)
        else:
            raise TypeError(f"Unknown event type: {type(event)}")

    @property
    def current_state(self) -> GameState:
        """Current state object."""
        return self._current

    @property
    def current_state_id(self) -> str:
        """Current state ID (backward-compatible with game.mode)."""
        return self._current.state_id


# ─── Concrete state classes ──────────────────────────────────────────────────


class CompactState(GameState):
    """Compact view mode — minimal display."""

    @property
    def state_id(self) -> str:
        return 'compact'

    def on_enter(self, game: Any, prev_state: 'GameState | None') -> None:
        game.show_help = False

    def on_exit(self, game: Any, next_state: 'GameState') -> None:
        pass

    def handle_key(self, game: Any, event: KeyEvent) -> tuple[str, Any]:
        from ascii_pet.core import ANIMATIONS
        key = event.key
        now = time.time()
        if key in ('\r', '\n'):
            game.sm.transition_to(game, ExpandedState())
            return 'mode_change', 'expanded'
        if key == 'h':
            game.show_help = True
            game.sm.transition_to(game, ExpandedState())
            return 'mode_change', 'expanded'
        if key == 'c':
            return 'none', None
        if key == 'b':
            if len(game.pets_data['pets']) > 1:
                msg = game.switch_pet(-1)
                game.message = msg; game.message_time = now
                return 'pet_switch', msg
            return 'none', None
        if key == 'n':
            msg = game.switch_pet(1)
            game.message = msg; game.message_time = now
            return 'pet_switch', msg
        if key == 'w':
            msg = game.adopt_pet()
            if msg is None:
                game.sm.transition_to(game, ReleaseState())
                return 'mode_change', 'release'
            game.message = msg; game.message_time = now
            return 'action', msg
        if key == 't':
            game.sm.transition_to(game, StatsState())
            return 'mode_change', 'stats'
        if key == 'a':
            game.sm.transition_to(game, AchievementsState())
            return 'mode_change', 'achievements'
        if key == 'l':
            game.sm.transition_to(game, LanState())
            return 'mode_change', 'lan'
        if key == 'u':
            game.sm.transition_to(game, ItemsState())
            return 'mode_change', 'items'
        if key == 'f':
            msg, anim = game.handle_action('feed')
            game.message = msg; game.message_time = now; game.action_message_time = now
            if anim: game.anim_end = now + 1.5; game.anim_frames = ANIMATIONS[anim]; game.anim_idx = 0
            return 'action', msg
        if key == 'p':
            msg, anim = game.handle_action('play')
            game.message = msg; game.message_time = now; game.action_message_time = now
            if anim: game.anim_end = now + 1.5; game.anim_frames = ANIMATIONS[anim]; game.anim_idx = 0
            return 'action', msg
        if key == 's':
            msg, anim = game.handle_action('sleep')
            game.message = msg; game.message_time = now; game.action_message_time = now
            if anim: game.anim_end = now + 1.5; game.anim_frames = ANIMATIONS[anim]; game.anim_idx = 0
            return 'action', msg
        return 'none', None

    def tick(self, game: Any, event: TickEvent) -> tuple[str | None, float]:
        return None, 0


class ExpandedState(GameState):
    """Main expanded view — primary interaction mode."""

    @property
    def state_id(self) -> str:
        return 'expanded'

    def on_enter(self, game: Any, prev_state: 'GameState | None') -> None:
        # Only reset show_help if not coming from compact (where 'h' sets it True)
        if prev_state is None or prev_state.state_id != 'compact':
            game.show_help = False

    def on_exit(self, game: Any, next_state: 'GameState') -> None:
        pass

    def handle_key(self, game: Any, event: KeyEvent) -> tuple[str, Any]:
        from ascii_pet.core import ANIMATIONS
        key = event.key
        now = time.time()

        # Visit operation keys take priority when a visit is active
        if key == 'f' and game.active_visit:
            if game.remote_feed():
                game.message = _('Remote feed sent')
            else:
                game.message = _('Remote feed failed')
            game.message_time = now
            return 'action', game.message
        if key == 'p' and game.active_visit:
            if game.remote_play():
                game.message = _('Remote play sent')
            else:
                game.message = _('Remote play failed')
            game.message_time = now
            return 'action', game.message
        if key == 'e' and (game.active_visit or game.being_visited):
            if game.end_visit():
                game.message = _('Visit ended')
            else:
                game.message = _('No active visit')
            game.message_time = now
            return 'action', game.message

        if key == 'f':
            msg, anim = game.handle_action('feed')
            game.message = msg; game.message_time = now; game.action_message_time = now
            if anim: game.anim_end = now + 1.5; game.anim_frames = ANIMATIONS[anim]; game.anim_idx = 0
            return 'action', msg
        if key == 'p':
            msg, anim = game.handle_action('play')
            game.message = msg; game.message_time = now; game.action_message_time = now
            if anim: game.anim_end = now + 1.5; game.anim_frames = ANIMATIONS[anim]; game.anim_idx = 0
            return 'action', msg
        if key == 's':
            msg, anim = game.handle_action('sleep')
            game.message = msg; game.message_time = now; game.action_message_time = now
            if anim: game.anim_end = now + 1.5; game.anim_frames = ANIMATIONS[anim]; game.anim_idx = 0
            return 'action', msg
        if key == 't':
            game.sm.transition_to(game, StatsState())
            return 'mode_change', 'stats'
        if key == 'a':
            game.sm.transition_to(game, AchievementsState())
            return 'mode_change', 'achievements'
        if key == 'l':
            game.sm.transition_to(game, LanState())
            return 'mode_change', 'lan'
        if key == 'u':
            game.sm.transition_to(game, ItemsState())
            return 'mode_change', 'items'
        if key == 'c':
            game.sm.transition_to(game, CompactState())
            return 'mode_change', 'compact'
        if key in ('\r', '\n'):
            game.sm.transition_to(game, CompactState())
            return 'mode_change', 'compact'
        if key == 'e':
            return 'export', None
        if key == 'b':
            if len(game.pets_data['pets']) > 1:
                msg = game.switch_pet(-1)
                game.message = msg; game.message_time = now
                return 'pet_switch', msg
            return 'none', None
        if key == 'n':
            msg = game.switch_pet(1)
            game.message = msg; game.message_time = now
            return 'pet_switch', msg
        if key == 'w':
            msg = game.adopt_pet()
            if msg is None:
                # Max pets reached, enter release mode
                game.sm.transition_to(game, ReleaseState())
                return 'mode_change', 'release'
            game.message = msg; game.message_time = now
            return 'action', msg
        if key == 'h':
            game.show_help = not game.show_help
            return 'mode_change', game.mode
        return 'none', None

    def tick(self, game: Any, event: TickEvent) -> tuple[str | None, float]:
        return None, 0


class StatsState(GameState):
    """Stats panel view."""

    @property
    def state_id(self) -> str:
        return 'stats'

    def on_enter(self, game: Any, prev_state: 'GameState | None') -> None:
        pass

    def on_exit(self, game: Any, next_state: 'GameState') -> None:
        pass

    def handle_key(self, game: Any, event: KeyEvent) -> tuple[str, Any]:
        key = event.key
        if key == 't':
            game.sm.transition_to(game, ExpandedState())
            return 'mode_change', 'expanded'
        if key == 'a':
            game.sm.transition_to(game, AchievementsState())
            return 'mode_change', 'achievements'
        if key == 'r':
            game.sm.transition_to(game, RenameState())
            return 'mode_change', 'rename'
        if key == 'u':
            game.sm.transition_to(game, ItemsState())
            return 'mode_change', 'items'
        if key == 'c':
            game.sm.transition_to(game, CompactState())
            return 'mode_change', 'compact'
        return 'none', None

    def tick(self, game: Any, event: TickEvent) -> tuple[str | None, float]:
        return None, 0


class AchievementsState(GameState):
    """Achievements panel view."""

    @property
    def state_id(self) -> str:
        return 'achievements'

    def on_enter(self, game: Any, prev_state: 'GameState | None') -> None:
        pass

    def on_exit(self, game: Any, next_state: 'GameState') -> None:
        pass

    def handle_key(self, game: Any, event: KeyEvent) -> tuple[str, Any]:
        key = event.key
        if key == 'a':
            game.sm.transition_to(game, ExpandedState())
            return 'mode_change', 'expanded'
        if key == 't':
            game.sm.transition_to(game, StatsState())
            return 'mode_change', 'stats'
        if key == 'u':
            game.sm.transition_to(game, ItemsState())
            return 'mode_change', 'items'
        if key == 'c':
            game.sm.transition_to(game, CompactState())
            return 'mode_change', 'compact'
        return 'none', None

    def tick(self, game: Any, event: TickEvent) -> tuple[str | None, float]:
        return None, 0


class ItemsState(GameState):
    """Inventory panel view."""

    @property
    def state_id(self) -> str:
        return 'items'

    def on_enter(self, game: Any, prev_state: 'GameState | None') -> None:
        pass

    def on_exit(self, game: Any, next_state: 'GameState') -> None:
        pass

    def handle_key(self, game: Any, event: KeyEvent) -> tuple[str, Any]:
        key = event.key
        now = time.time()
        if key in ('1', '2', '3', '4', '5', '6', '7'):
            idx = int(key) - 1
            inv_list = game.get_inventory_list()
            if idx < len(inv_list):
                item_id = inv_list[idx][0]
                msg = game.use_item(item_id)
                game.message = msg; game.message_time = now
                return 'action', msg
            return 'none', None
        if key == 'c':
            game.sm.transition_to(game, ExpandedState())
            return 'mode_change', 'expanded'
        return 'none', None

    def tick(self, game: Any, event: TickEvent) -> tuple[str | None, float]:
        return None, 0


class RenameState(GameState):
    """Rename input mode — text entry for pet renaming."""

    MAX_INPUT_LENGTH = 20

    def __init__(self):
        self._input: str = ''

    @property
    def state_id(self) -> str:
        return 'rename'

    def on_enter(self, game: Any, prev_state: 'GameState | None') -> None:
        self._input = ''

    def on_exit(self, game: Any, next_state: 'GameState') -> None:
        pass

    def handle_key(self, game: Any, event: KeyEvent) -> tuple[str, Any]:
        key = event.key
        now = time.time()
        if key in ('\r', '\n'):
            new_name = self._input.strip()
            if new_name:
                msg = game.rename_pet(new_name)
                game.message = msg; game.message_time = now
                game.sm.transition_to(game, StatsState())
                return 'mode_change', 'stats'
            game.message = _('Name cannot be empty'); game.message_time = now
            return 'none', None
        if key == '\x1b':  # ESC
            game.sm.transition_to(game, StatsState())
            return 'mode_change', 'stats'
        if key == '\x08':  # backspace
            self._input = self._input[:-1]
            return 'none', None
        if len(key) == 1 and key.isprintable() and len(self._input) < self.MAX_INPUT_LENGTH:
            self._input += key
            return 'none', None
        return 'none', None

    def tick(self, game: Any, event: TickEvent) -> tuple[str | None, float]:
        return None, 0


class ReleaseState(GameState):
    """Pet release mode — select a pet to release."""

    @property
    def state_id(self) -> str:
        return 'release'

    def on_enter(self, game: Any, prev_state: 'GameState | None') -> None:
        pass

    def on_exit(self, game: Any, next_state: 'GameState') -> None:
        pass

    def handle_key(self, game: Any, event: KeyEvent) -> tuple[str, Any]:
        key = event.key
        now = time.time()
        if key in ('1', '2', '3'):
            idx = int(key) - 1
            if idx < len(game.pets_data['pets']):
                msg = game.release_pet(idx)
                game.message = msg; game.message_time = now
                game.sm.transition_to(game, ExpandedState())
                return 'action', msg
            return 'none', None
        if key == 'c':
            game.sm.transition_to(game, ExpandedState())
            return 'mode_change', 'expanded'
        return 'none', None

    def tick(self, game: Any, event: TickEvent) -> tuple[str | None, float]:
        return None, 0


# ─── Concrete game states ─────────────────────────────────────────────────────


class LanState(GameState):
    """Community Plaza mode with internal sub-state machine for LAN actions."""

    _SELECTION_SUBMODES = frozenset({
        'visit', 'challenge', 'gift', 'trade',
    })

    def __init__(self):
        self._submode: str | None = None
        self._submode_data: dict = {}
        self._page: int = 0

    @property
    def state_id(self) -> str:
        return 'lan'

    def on_enter(self, game: Any, prev_state: 'GameState | None') -> None:
        self._submode = None
        self._submode_data = {}
        self._page = 0

    def on_exit(self, game: Any, next_state: 'GameState') -> None:
        pass

    def handle_key(self, game: Any, event: KeyEvent) -> tuple[str, Any]:
        if self._submode is None:
            return self._handle_idle(game, event)
        elif self._submode in self._SELECTION_SUBMODES:
            return self._handle_selection(game, event)
        elif self._submode == 'gift_item':
            return self._handle_gift_item(game, event)
        elif self._submode == 'trade_pet':
            return self._handle_trade_pet(game, event)
        return ('none', None)

    def tick(self, game: Any, event: TickEvent) -> tuple[str | None, float]:
        return (None, 0)

    def handle_lan_message(self, game: Any, event: LanMessageEvent) -> None:
        """Handle all LAN message types."""
        from ascii_pet.protocol import (
            MSG_VISIT_REQ, MSG_VISIT_DATA, MSG_VISIT_LEAVE,
            MSG_VISIT_FEED, MSG_VISIT_PLAY, MSG_VISIT_EVENT, MSG_VISIT_END,
            MSG_CHALLENGE_REQ, MSG_CHALLENGE_ACK, MSG_CHALLENGE_RESULT,
            MSG_GIFT_ITEM, MSG_GIFT_ACK,
            MSG_TRADE_REQ, MSG_TRADE_ACK, MSG_TRADE_CONFIRM,
        )
        from ascii_pet.events import Event, apply_event

        msg_type = event.msg_type
        payload = event.payload
        now = time.time()

        if msg_type == MSG_VISIT_REQ:
            snapshot = payload.get("pet_snapshot", {})
            from_id = payload.get("from", "")
            from_username = payload.get("from_username", "?")
            game.being_visited = {"from": from_id, "start_time": now, "pet_snapshot": snapshot}
            game.visitor_pets[from_id] = snapshot
            game.message = _("{username}'s pet {name} came to visit!").format(
                username=from_username, name=snapshot.get('name', '?'))
            game.message_time = now
            game.visit_message_time = now
            # Send own pet snapshot back to initiator so both sides can see
            # both pets. The initiator stores it in visitor_pets[from_id]
            # via the MSG_VISIT_DATA handler.
            if from_id and game.lan_node:
                from ascii_pet.protocol import make_pet_snapshot
                own_snapshot = make_pet_snapshot(
                    game.state, game.lan_username or game.uid)
                # 包含受访方 node_id，让发起方用 node_id 作为 key 存储
                own_snapshot["from"] = game.lan_node.node_id
                try:
                    game.lan_node.send_to_peer(from_id, MSG_VISIT_DATA, own_snapshot)
                except Exception:
                    pass
            # 受访方切换到 ExpandedState，立即在屏幕上显示访客宠物
            game.sm.transition_to(game, ExpandedState())

        elif msg_type == MSG_VISIT_FEED:
            stat_key = 'HUNGER'
            before = game.state['stats'].get(stat_key, 0)
            result = game.handle_action('feed')
            after = game.state['stats'].get(stat_key, 0)
            delta = after - before
            from_name = payload.get("from", "?")
            if delta > 0:
                game.message = _("{name} fed your pet! {stat} {before}->{after}(+{delta})").format(
                    name=from_name, stat=stat_key, before=before, after=after, delta=delta)
            else:
                game.message = _("{name} fed your pet! {result}").format(
                    name=from_name, result=result[0])
            game.message_time = now
            game.visit_message_time = now

        elif msg_type == MSG_VISIT_PLAY:
            stat_key = 'HAPPY'
            before = game.state['stats'].get(stat_key, 0)
            result = game.handle_action('play')
            after = game.state['stats'].get(stat_key, 0)
            delta = after - before
            from_name = payload.get("from", "?")
            if delta > 0:
                game.message = _("{name} played with your pet! {stat} {before}->{after}(+{delta})").format(
                    name=from_name, stat=stat_key, before=before, after=after, delta=delta)
            else:
                game.message = _("{name} played with your pet! {result}").format(
                    name=from_name, result=result[0])
            game.message_time = now
            game.visit_message_time = now

        elif msg_type == MSG_VISIT_EVENT:
            description = payload.get("description", "")
            stat_effects = payload.get("stat_effects", {})
            event_type = payload.get("event_type", "visit_event")
            visit_evt = Event(
                event_id=event_type,
                description=description,
                effects=stat_effects,
                target='self',
                category='visit',
            )
            apply_event(game.state, visit_evt)
            game.message = _("Visit event: {desc}").format(desc=description)
            game.message_time = now
            game.visit_message_time = now

        elif msg_type == MSG_VISIT_END:
            from_id = payload.get("from", "")
            if game.active_visit:
                # Initiator side: clear visitor_pets entry for the visited
                # party so their pet no longer renders on our screen.
                target = game.active_visit.get("target", "")
                if from_id:
                    game.visitor_pets.pop(from_id, None)
                elif target:
                    # Fallback: use active_visit target when 'from' missing
                    game.visitor_pets.pop(target, None)
                game.active_visit = None
                game.message = _("Visit ended")
                game.message_time = now
            if game.being_visited:
                # 按 node_id 从 visitor_pets 中移除
                if from_id:
                    game.visitor_pets.pop(from_id, None)
                else:
                    # 兼容旧版：无 from 字段时用 being_visited 中的 from
                    sender = game.being_visited.get("from", "")
                    game.visitor_pets.pop(sender, None)
                game.being_visited = None
                game.message = _("Visit ended")
                game.message_time = now

        elif msg_type == MSG_VISIT_DATA:
            # 用 payload['from'] (node_id) 作为 key，确保存取删一致
            game.receive_visitor(payload, node_id=payload.get("from", ""))
            game.message = _("{name} came to visit!").format(name=payload.get('name', ''))
            game.message_time = now

        elif msg_type == MSG_VISIT_LEAVE:
            pet_name = payload.get("pet_name", "")
            from_id = payload.get("from", "")
            if from_id:
                game.visitor_pets.pop(from_id, None)
            else:
                # 兼容旧版：无 from 字段时按 name 查找
                for nid, v in list(game.visitor_pets.items()):
                    if v.get("name") == pet_name:
                        del game.visitor_pets[nid]
                        break

        elif msg_type == MSG_CHALLENGE_REQ:
            from_username = payload.get("from_username", "?")
            result = game.accept_challenge(payload)
            if result.get("escaped"):
                game.lan_node.send_to_peer(payload.get("from", ""), MSG_CHALLENGE_ACK, {
                    "escaped": True,
                    "reason": result.get("reason", ""),
                    "from": game.lan_node.node_id,
                    "from_username": game.lan_username or "?",
                })
                game.message = _("Your pet escaped from {username}'s challenge!").format(username=from_username)
            else:
                game.lan_node.send_to_peer(payload.get("from", ""), MSG_CHALLENGE_ACK, {
                    "escaped": False,
                    "defender_snapshot": result.get("defender_snapshot", {}),
                    "from": game.lan_node.node_id,
                    "from_username": game.lan_username or "?",
                })
                game.message = _("{username} challenges you!").format(username=from_username)
            game.message_time = now

        elif msg_type == MSG_CHALLENGE_ACK:
            if payload.get("escaped"):
                defender_username = payload.get("from_username", "?")
                game.message = _("{username} escaped!").format(username=defender_username)
                game.active_challenge = None
            else:
                from ascii_pet.battle import simulate_battle
                attacker_snapshot = game.active_challenge.get("pet_snapshot", {}) if game.active_challenge else {}
                defender_snapshot = payload.get("defender_snapshot", {})
                seed = int(time.time())
                battle_result = simulate_battle(attacker_snapshot, defender_snapshot, seed=seed)
                if battle_result["winner"] == attacker_snapshot.get("name", ""):
                    winner = "attacker"
                else:
                    winner = "defender"
                result = {
                    "winner": winner,
                    "log": battle_result["log"],
                    "hp_loss_winner": battle_result["hp_loss_winner"],
                    "hp_loss_loser": battle_result["hp_loss_loser"],
                    "attacker_snapshot": attacker_snapshot,
                    "defender_snapshot": defender_snapshot,
                    "seed": seed,
                }
                game.lan_node.send_to_peer(payload.get("from", ""), MSG_CHALLENGE_RESULT, result)
                game.apply_battle_result(result)
                game.battle_result = battle_result
                game.active_challenge = None
                attacker_name = attacker_snapshot.get("name", "?")
                defender_name = defender_snapshot.get("name", "?")
                if winner == "attacker":
                    game.message = _("You won the battle! {atk} vs {defn}").format(
                        atk=attacker_name, defn=defender_name)
                else:
                    game.message = _("You lost the battle! {atk} vs {defn}").format(
                        atk=attacker_name, defn=defender_name)
            game.message_time = now

        elif msg_type == MSG_CHALLENGE_RESULT:
            attacker_snapshot = payload.get("attacker_snapshot")
            defender_snapshot = payload.get("defender_snapshot")
            seed = payload.get("seed")
            if attacker_snapshot and defender_snapshot and seed is not None:
                from ascii_pet.battle import simulate_battle
                battle_result = simulate_battle(attacker_snapshot, defender_snapshot, seed=seed)
                game.apply_battle_result(payload)
                game.battle_result = battle_result
            else:
                game.apply_battle_result(payload)
                game.battle_result = payload
            game.active_challenge = None
            attacker_name = attacker_snapshot.get("name", "?") if attacker_snapshot else "?"
            defender_name = defender_snapshot.get("name", "?") if defender_snapshot else "?"
            if payload.get("winner") == "defender":
                game.message = _("You won the battle! {atk} vs {defn}").format(
                    atk=attacker_name, defn=defender_name)
            else:
                game.message = _("You lost the battle! {atk} vs {defn}").format(
                    atk=attacker_name, defn=defender_name)
            game.message_time = now

        elif msg_type == MSG_GIFT_ITEM:
            from_username = payload.get("from_username", "?")
            item_id = payload.get("item_id", "")
            count = payload.get("count", 1)
            result = game.receive_gift(item_id, count)
            game.lan_node.send_to_peer(payload.get("from", ""), MSG_GIFT_ACK, {
                "success": result.get("success", False),
                "from": game.lan_node.node_id,
            })
            if result.get("success"):
                from ascii_pet.core import ITEMS
                item_name = ITEMS.get(item_id, {}).get('name', item_id)
                game.message = _("Received {count} {item} from {username}!").format(
                    count=count, item=item_name, username=from_username)
            else:
                game.message = _("Inventory full!")
            game.message_time = now

        elif msg_type == MSG_GIFT_ACK:
            success = payload.get("success", False)
            game.confirm_gift_sent(success)
            if success:
                game.message = _("Gift delivered!")
            else:
                game.message = _("Gift failed - recipient's inventory is full")
            game.message_time = now

        elif msg_type == MSG_TRADE_REQ:
            game.pending_trade_req = payload
            from_username = payload.get("from_username", "?")
            game.message = _("{username} wants to trade! [y/n]").format(username=from_username)
            game.message_time = now

        elif msg_type == MSG_TRADE_ACK:
            if payload.get("accepted"):
                if game.active_trade:
                    my_index = game.active_trade["pet_index"]
                    my_pet = game.pets_data['pets'][my_index]
                    game.lan_node.send_to_peer(payload.get("from", ""), MSG_TRADE_CONFIRM, {
                        "pet_snapshot": my_pet,
                        "pet_index": my_index,
                        "from": game.lan_node.node_id,
                    })
                    game.execute_trade(payload)
                    game.message = _("Trade complete!")
                else:
                    game.message = _("Trade failed")
            else:
                game.active_trade = None
                game.message = _("Trade rejected")
            game.message_time = now

        elif msg_type == MSG_TRADE_CONFIRM:
            game.execute_trade(payload)
            game.message = _("Trade complete!")
            game.message_time = now

    # ── Idle sub-state ──

    def _check_active_block(self, game: Any) -> str | None:
        """Check if any active operation blocks starting a new one.

        Returns a block message if blocked, None if clear.
        """
        if game.active_visit:
            return _('You are visiting, cannot start a new action')
        if game.being_visited:
            return _('You are being visited, cannot start a new action')
        if game.active_challenge:
            return _('Already in a challenge')
        if game.active_gift:
            return _('Already sending a gift')
        if game.active_trade:
            return _('Already in a trade')
        return None

    def _handle_idle(self, game: Any, event: KeyEvent) -> tuple[str, Any]:
        key = event.key
        now = time.time()

        if key == 'l':
            game.sm.transition_to(game, ExpandedState())
            return 'mode_change', 'expanded'
        elif key == 'o':
            if game.lan_enabled:
                game.disable_lan()
                game.message = _('Community Plaza disconnected')
            else:
                if game.enable_lan():
                    game.message = _('Community Plaza connected')
                else:
                    game.message = _('Failed to connect to Community Plaza')
            game.message_time = now
            return 'action', game.message
        elif key == 'u':
            game.sm.transition_to(game, LanNameEditState())
            return 'mode_change', 'lan_name_edit'
        elif key == 'v':
            block_msg = self._check_active_block(game)
            if block_msg:
                game.message = block_msg
                game.message_time = now
                return 'action', game.message
            peers = game.get_lan_peers()
            if not peers:
                game.message = _('No peers to visit')
                game.message_time = now
                return 'action', game.message
            self._submode = 'visit'
            game.message = _('Select visit target')
            game.message_time = now
            return 'action', game.message
        elif key == 'c':
            block_msg = self._check_active_block(game)
            if block_msg:
                game.message = block_msg
                game.message_time = now
                return 'action', game.message
            # Daily challenge limit check
            from datetime import datetime
            today = datetime.now().date().isoformat()
            challenge_log = game.pets_data.setdefault('challenge_log', {})
            if challenge_log.get(today, 0) >= getattr(game, 'MAX_DAILY_CHALLENGES', 3):
                game.message = _('Daily challenge limit reached ({max}/day)').format(max=getattr(game, 'MAX_DAILY_CHALLENGES', 3))
                game.message_time = now
                return 'action', game.message
            peers = game.get_lan_peers()
            if not peers:
                game.message = _('No peers to challenge')
                game.message_time = now
                return 'action', game.message
            self._submode = 'challenge'
            game.message = _('Select challenge target')
            game.message_time = now
            return 'action', game.message
        elif key == 'g':
            block_msg = self._check_active_block(game)
            if block_msg:
                game.message = block_msg
                game.message_time = now
                return 'action', game.message
            peers = game.get_lan_peers()
            inv_list = game.get_inventory_list()
            if not peers:
                game.message = _('No peers or items')
                game.message_time = now
                return 'action', game.message
            if not inv_list:
                game.message = _('No items to gift')
                game.message_time = now
                return 'action', game.message
            self._submode = 'gift'
            game.message = _('Select gift target')
            game.message_time = now
            return 'action', game.message
        elif key == 't':
            block_msg = self._check_active_block(game)
            if block_msg:
                game.message = block_msg
                game.message_time = now
                return 'action', game.message
            peers = game.get_lan_peers()
            if not peers:
                game.message = _('No peers to trade')
                game.message_time = now
                return 'action', game.message
            self._submode = 'trade'
            game.message = _('Select trade target')
            game.message_time = now
            return 'action', game.message
        elif key == 'h':
            game.heal_pet()
            return 'action', game.message
        elif key == 'e':
            if game.active_visit or game.being_visited:
                if game.end_visit():
                    game.message = _('Visit ended')
                else:
                    game.message = _('No active visit')
            else:
                game.message = _('No active visit')
            game.message_time = now
            return 'action', game.message
        elif key == 'f':
            if game.active_visit:
                if game.remote_feed():
                    game.message = _('Remote feed sent')
                else:
                    game.message = _('Remote feed failed')
            else:
                game.message = _('Remote feed failed')
            game.message_time = now
            return 'action', game.message
        elif key == 'p':
            if game.active_visit:
                if game.remote_play():
                    game.message = _('Remote play sent')
                else:
                    game.message = _('Remote play failed')
            else:
                game.message = _('Remote play failed')
            game.message_time = now
            return 'action', game.message
        elif key == '[':
            if self._page > 0:
                self._page -= 1
            return ('none', None)
        elif key == ']':
            all_peers = game.get_lan_peers()
            total_pages = max(1, (len(all_peers) + 8) // 9)
            if self._page < total_pages - 1:
                self._page += 1
            return ('none', None)
        elif key == 'q':
            return ('quit', None)

        return ('none', None)

    # ── Selection sub-states (visit/challenge/gift/trade) ──

    def _handle_selection(self, game: Any, event: KeyEvent) -> tuple[str, Any]:
        key = event.key
        now = time.time()

        if key in ('q', '\x1b'):
            self._submode = None
            self._submode_data = None
            game.message = _('Cancelled')
            game.message_time = now
            return 'action', game.message

        if key in '123456789':
            idx = int(key) - 1
            peers_page, total_pages, cur_page = game.get_lan_peers_page()
            all_peers = game.get_lan_peers()

            if self._submode == 'visit':
                if idx < len(peers_page):
                    peer = peers_page[idx]
                    peer_id = peer.get('node_id', '')
                    self._submode = None
                    if game.invite_visit(peer_id):
                        game.message = _('Visiting {peer}').format(peer=peer.get("username", "?"))
                        game.message_time = now
                        game.sm.transition_to(game, ExpandedState())
                        return 'mode_change', 'expanded'
                    # invite_visit sets its own error message on failure
                else:
                    self._submode = None
                    game.message = _("Invalid selection")
                game.message_time = now
                return 'action', game.message

            elif self._submode == 'challenge':
                if idx < len(peers_page):
                    peer = peers_page[idx]
                    peer_id = peer.get('node_id', '')
                    target_username = peer.get('username', '?')
                    self._submode = None
                    if game.initiate_challenge(peer_id):
                        game.message = _("Challenging {username}...").format(username=target_username)
                        # Increment daily challenge count
                        from datetime import datetime
                        today = datetime.now().date().isoformat()
                        challenge_log = game.pets_data.setdefault('challenge_log', {})
                        challenge_log[today] = challenge_log.get(today, 0) + 1
                        game.save()
                    # initiate_challenge sets its own error message on failure
                else:
                    self._submode = None
                    game.message = _("Invalid selection")
                game.message_time = now
                return 'action', game.message

            elif self._submode == 'gift':
                if idx < len(peers_page):
                    peer = peers_page[idx]
                    self._submode_data = {'target_node_id': peer.get('node_id', '')}
                    self._submode = 'gift_item'
                    game.message = _("Select item to gift")
                else:
                    self._submode = None
                    game.message = _("Invalid selection")
                game.message_time = now
                return 'action', game.message

            elif self._submode == 'trade':
                if idx < len(peers_page):
                    peer = peers_page[idx]
                    self._submode_data = {'target_node_id': peer.get('node_id', '')}
                    self._submode = 'trade_pet'
                    game.message = _("Select pet to trade (1-3)")
                else:
                    self._submode = None
                    game.message = _("Invalid selection")
                game.message_time = now
                return 'action', game.message

        # Ignore other keys in submode
        return 'none', None

    # ── Gift item sub-state ──

    def _handle_gift_item(self, game: Any, event: KeyEvent) -> tuple[str, Any]:
        key = event.key
        now = time.time()

        if key in ('q', '\x1b'):
            self._submode = 'gift'
            # Keep _submode_data with target_node_id so user can re-select item
            game.message = _('Back to player selection')
            game.message_time = now
            return 'action', game.message

        if key in '123456789':
            idx = int(key) - 1
            inv_list = game.get_inventory_list()
            if idx < len(inv_list):
                item_id = inv_list[idx][0]
                target_id = self._submode_data.get('target_node_id', '')
                self._submode = None
                self._submode_data = None
                if game.gift_item(target_id, item_id, 1):
                    game.message = _("Gift sent, waiting for confirmation...")
                # gift_item sets its own error message on failure
            else:
                self._submode = None
                self._submode_data = None
                game.message = _("Invalid selection")
            game.message_time = now
            return 'action', game.message

        return 'none', None

    # ── Trade pet sub-state ──

    def _handle_trade_pet(self, game: Any, event: KeyEvent) -> tuple[str, Any]:
        """Handle pet selection for trade initiation."""
        key = event.key
        now = time.time()

        if key in ('q', '\x1b'):
            self._submode = None
            self._submode_data = None
            game.message = _('Cancelled')
            game.message_time = now
            return 'action', game.message

        if key in '123':
            idx = int(key) - 1
            if idx < 0 or idx >= len(game.pets_data['pets']):
                game.message = _('Invalid pet')
                game.message_time = now
                return 'action', game.message

            target_node_id = self._submode_data.get('target_node_id', '')
            self._submode = None
            self._submode_data = None
            if game.initiate_trade(target_node_id, idx):
                # Ensure active_trade is set (in case initiate_trade
                # didn't set it, e.g. in test mocks)
                if game.active_trade is None:
                    game.active_trade = {
                        "target": target_node_id,
                        "pet_index": idx,
                        "start_time": now,
                        "role": "initiator",
                    }
                game.message = _("Trade request sent, waiting for response...")
            # initiate_trade sets its own error message on failure
            game.message_time = now
            return 'action', game.message

        return 'none', None


class LanNameEditState(GameState):
    """LAN username editing mode."""

    _MAX_INPUT = 20

    def __init__(self):
        self._input: str = ''

    @property
    def state_id(self) -> str:
        return 'lan_name_edit'

    def on_enter(self, game: Any, prev_state: 'GameState | None') -> None:
        self._input = getattr(game, 'lan_username', '') or ''

    def on_exit(self, game: Any, next_state: 'GameState') -> None:
        pass

    def handle_key(self, game: Any, event: KeyEvent) -> tuple[str, Any]:
        key = event.key
        now = time.time()

        if key == '\r':  # Enter
            new_name = self._input.strip()
            if new_name:
                if game.change_lan_username(new_name):
                    game.message = _('Username changed to: {name}').format(name=game.lan_username)
                else:
                    game.message = _('Username already in use')
            else:
                game.message = _('Username cannot be empty')
            game.message_time = now
            game.sm.transition_to(game, LanState())
            return 'mode_change', 'lan'

        elif key == '\x1b':  # ESC
            game.sm.transition_to(game, LanState())
            return 'mode_change', 'lan'

        elif key == '\x08':  # Backspace
            if self._input:
                self._input = self._input[:-1]
            return ('none', None)

        elif len(key) == 1 and key.isprintable():
            if len(self._input) < self._MAX_INPUT:
                self._input += key
            return ('none', None)

        return ('none', None)

    def tick(self, game: Any, event: TickEvent) -> tuple[str | None, float]:
        return (None, 0)


# ─── DeadOverlayState ─────────────────────────────────────────────────────────


class DeadOverlayState(GameState):
    """Decorator/overlay state that wraps another state when the pet is dead.

    Intercepts action keys (f/p/s/r/d/b/n) with dead-pet-specific behavior,
    and passes all other keys through to the underlying inner state.
    """

    _DEATH_MSG = None  # Lazily initialized to avoid import-time i18n issues

    def __init__(self, inner_state: GameState):
        self._inner = inner_state

    @property
    def state_id(self) -> str:
        return self._inner.state_id

    def on_enter(self, game: Any, prev_state: 'GameState | None') -> None:
        self._inner.on_enter(game, prev_state)

    def on_exit(self, game: Any, next_state: 'GameState') -> None:
        self._inner.on_exit(game, next_state)

    def tick(self, game: Any, event: TickEvent) -> tuple[str | None, float]:
        return None, 0

    def handle_lan_message(self, game: Any, event: LanMessageEvent) -> None:
        self._inner.handle_lan_message(game, event)

    def handle_key(self, game: Any, event: KeyEvent) -> tuple[str, Any]:
        key = event.key
        now = time.time()

        # f/p/s: return death message (don't execute the action)
        if key in ('f', 'p', 's'):
            msg = _('Your pet is dead... Use a Potion to revive!')
            game.message = msg
            game.message_time = now
            return 'action', msg

        # r: use Potion to revive
        if key == 'r':
            inv = game.pets_data.get('inventory', {})
            if inv.get('potion', 0) > 0:
                msg = game.use_item('potion')
            else:
                msg = _('No Potion available!')
            game.message = msg
            game.message_time = now
            return 'action', msg

        # d: release dead pet
        if key == 'd':
            msg = game.release_pet(game.pet_idx)
            game.message = msg
            game.message_time = now
            return 'action', msg

        # b: switch pet prev
        if key == 'b':
            msg = game.switch_pet(-1)
            game.message = msg
            game.message_time = now
            return 'pet_switch', msg

        # n: switch pet next
        if key == 'n':
            msg = game.switch_pet(1)
            game.message = msg
            game.message_time = now
            return 'pet_switch', msg

        # All other keys pass through to the inner state
        return self._inner.handle_key(game, event)
