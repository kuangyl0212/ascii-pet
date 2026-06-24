"""Event-driven state machine for game flow management.

All game inputs (key presses, LAN messages, timers) are unified as
GameEvent objects dispatched through a StateMachine to the current
GameState, which handles the event and optionally triggers transitions.
"""

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
            game.visitor_pets.append(snapshot)
            game.message = _("{username}'s pet {name} came to visit!").format(
                username=from_username, name=snapshot.get('name', '?'))
            game.message_time = now
            game.visit_message_time = now

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
            if game.active_visit:
                game.active_visit = None
                game.message = _("Visit ended")
                game.message_time = now
            if game.being_visited:
                snap = game.being_visited.get("pet_snapshot", {})
                snap_name = snap.get("name", "")
                for i, v in enumerate(game.visitor_pets):
                    if v.get("name", "") == snap_name:
                        game.visitor_pets.pop(i)
                        break
                game.being_visited = None
                game.message = _("Visit ended")
                game.message_time = now

        elif msg_type == MSG_VISIT_DATA:
            game.receive_visitor(payload)
            game.message = _("{name} came to visit!").format(name=payload.get('name', ''))
            game.message_time = now

        elif msg_type == MSG_VISIT_LEAVE:
            pet_name = payload.get("pet_name", "")
            for i, v in enumerate(game.visitor_pets):
                if v.get("name") == pet_name:
                    game.visitor_pets.pop(i)
                    break

        elif msg_type == MSG_CHALLENGE_REQ:
            from_username = payload.get("from_username", "?")
            result = game.accept_challenge(payload)
            if result.get("escaped"):
                game.lan_node.send_to_peer(payload.get("from", ""), MSG_CHALLENGE_ACK, {
                    "escaped": True,
                    "reason": result.get("reason", ""),
                    "from": game.lan_node.node_id,
                })
                game.message = _("Your pet escaped!")
            else:
                game.lan_node.send_to_peer(payload.get("from", ""), MSG_CHALLENGE_ACK, {
                    "escaped": False,
                    "defender_snapshot": result.get("defender_snapshot", {}),
                    "from": game.lan_node.node_id,
                })
                game.message = _("{username} challenges you!").format(username=from_username)
            game.message_time = now

        elif msg_type == MSG_CHALLENGE_ACK:
            if payload.get("escaped"):
                game.message = _("Opponent escaped!")
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
                if winner == "attacker":
                    game.message = _("You won the battle!")
                else:
                    game.message = _("You lost the battle!")
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
            if payload.get("winner") == "defender":
                game.message = _("You won the battle!")
            else:
                game.message = _("You lost the battle!")
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
                game.message = _("Received {count} {item} from {username}!").format(
                    count=count, item=item_id, username=from_username)
            else:
                game.message = _("Inventory full!")
            game.message_time = now

        elif msg_type == MSG_GIFT_ACK:
            success = payload.get("success", False)
            game.confirm_gift_sent(success)

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
            if not game.active_visit and not game.active_challenge and not game.being_visited:
                peers = game.get_lan_peers()
                if not peers:
                    game.message = _('No peers to visit')
                    game.message_time = now
                    return 'action', game.message
                self._submode = 'visit'
                game.message = _('Select visit target')
                game.message_time = now
                return 'action', game.message
            return ('none', None)
        elif key == 'c':
            if not game.active_visit and not game.being_visited:
                if game.active_challenge:
                    game.message = _('Already in a challenge')
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
            return ('none', None)
        elif key == 'g':
            if not game.active_gift and not game.active_visit and not game.active_challenge and not game.being_visited:
                if game.active_gift:
                    game.message = _('Already gifting')
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
            return ('none', None)
        elif key == 't':
            if not game.active_trade and not game.active_visit and not game.active_challenge and not game.being_visited:
                if game.active_trade:
                    game.message = _('Already trading')
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
            return ('none', None)
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
                    self._submode = None
                    if game.initiate_challenge(peer_id):
                        game.message = _("Challenge initiated!")
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
                    peer_id = peer.get('node_id', '')
                    self._submode = None
                    if game.initiate_trade(peer_id, game.pet_idx):
                        game.message = _("Trade request sent!")
                    # initiate_trade sets its own error message on failure
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
            self._submode = None
            self._submode_data = None
            game.message = _('Cancelled')
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
                    game.message = _("Gift sent!")
                # gift_item sets its own error message on failure
            else:
                self._submode = None
                self._submode_data = None
                game.message = _("Invalid selection")
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
