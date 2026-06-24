#!/usr/bin/env python3
"""TDD 端到端测试：两个 PetGame 实例之间的完整拜访流程。

测试场景：
1. 完整拜访流程（发起→双方进入→结束→双方退出，发起方结束）
2. 受访方结束拜访
3. visitor_pets key 一致性验证

实现方式：
使用 _MessageBus 模拟网络消息传递。两个 PetGame 实例共享一个
_MessageBus。当一个 game 调用 lan_node.send_to_peer(target, msg_type,
payload) 时，消息被放入对方的 ui_queue。调用 game.process_lan_queues()
处理队列消息。

BDD Scenarios:

  Feature: End-to-End Visit Flow

    Scenario: 完整拜访流程（发起方结束）
      Given 发起方 A 和受访方 B 两个 PetGame 实例通过 _MessageBus 互联
      When A 调用 invite_visit(B 的 node_id)
      And B 处理消息队列
      Then B 的 being_visited 被设置（from=A_node_id）
      And B 的 visitor_pets[A_node_id] 存储 A 的宠物快照
      And B 回发 MSG_VISIT_DATA（含 from=B_node_id）
      And B 切换到 ExpandedState
      When A 处理消息队列
      Then A 的 visitor_pets[B_node_id] 存储 B 的宠物快照
      And 双方都有两只宠物（自己的 + 对方的）
      When A 调用 end_visit()
      And B 处理消息队列
      Then 双方都回到空闲状态

    Scenario: 受访方结束拜访
      Given 拜访已建立
      When B 调用 end_visit()
      And A 处理消息队列
      Then 双方都回到空闲状态

    Scenario: visitor_pets key 一致性
      Given 拜访已建立
      Then A 的 visitor_pets key 是 B_node_id（不是用户名）
      And B 的 visitor_pets key 是 A_node_id（不是用户名）
      When 拜访结束
      Then 双方 visitor_pets 都为空（key 一致所以能正确删除）
"""
import os
import sys
import time
import queue
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from ascii_pet.core import PetGame
from ascii_pet.protocol import (
    MSG_VISIT_REQ, MSG_VISIT_DATA, MSG_VISIT_END,
)


def _uid(prefix):
    """生成唯一 uid 避免状态冲突。"""
    return f'test-visit-e2e-{prefix}-{int(time.time() * 1000000)}-{os.urandom(4).hex()}'


class _MessageBus:
    """模拟网络消息总线。

    两个 _FakeLanNode 共享一个 _MessageBus。当一个节点调用
    send_to_peer(target, msg_type, payload) 时，消息被放入目标节点的
    ui_queue，目标节点通过 process_lan_queues() 处理。
    """

    def __init__(self):
        self._nodes = {}  # node_id -> _FakeLanNode

    def register(self, node):
        """注册一个节点到总线。"""
        self._nodes[node.node_id] = node

    def deliver(self, target_node_id, msg_type, payload):
        """将消息投递到目标节点的 ui_queue。返回 True 表示投递成功。"""
        target = self._nodes.get(target_node_id)
        if target is None:
            return False
        target.ui_queue.put({'type': msg_type, 'payload': payload})
        return True


class _FakeLanNode:
    """测试用假 LanNode，通过 _MessageBus 与其他节点通信。"""

    def __init__(self, username, pet_state, node_id, bus):
        self.username = username
        self.pet_state = pet_state
        self.node_id = node_id
        self._bus = bus
        self.ui_queue = queue.Queue()
        self.net_queue = queue.Queue()
        self._status = {
            'enabled': False,
            'is_master': False,
            'peer_count': 0,
            'error': None,
            'node_id': self.node_id,
        }
        self._peers = []
        self.send_calls = []
        # 注册到总线
        self._bus.register(self)

    def start(self):
        self._status['enabled'] = True
        self._status['is_master'] = True
        return True

    def stop(self):
        self._status['enabled'] = False

    def get_status(self):
        return dict(self._status)

    def get_peers(self):
        return list(self._peers)

    def send_to_peer(self, peer_node_id, msg_type, payload):
        self.send_calls.append((peer_node_id, msg_type, payload))
        return self._bus.deliver(peer_node_id, msg_type, payload)

    def send_broadcast(self, msg_type, payload):
        return True


def _make_game(tmp_path, prefix, username, node_id, bus):
    """创建一个 PetGame 实例，并用连接到 bus 的 _FakeLanNode 替换真实 LanNode。"""
    uid = _uid(prefix)
    data_dir = tmp_path / prefix
    data_dir.mkdir(exist_ok=True)
    g = PetGame(uid, data_dir=data_dir)
    fake_node = _FakeLanNode(username, g.state, node_id, bus)
    with patch('ascii_pet.lan.LanNode', return_value=fake_node):
        g.enable_lan(username)
    return g


@pytest.fixture
def two_games(tmp_path):
    """创建两个互联的 PetGame 实例（Alice 和 Bob），共享一个 _MessageBus。

    返回 (alice, bob) 元组。Alice 的 node_id 为 'node-alice'，
    Bob 的 node_id 为 'node-bob'。
    """
    bus = _MessageBus()
    alice = _make_game(tmp_path, 'alice', 'Alice', 'node-alice', bus)
    bob = _make_game(tmp_path, 'bob', 'Bob', 'node-bob', bus)
    return alice, bob


def _establish_visit(alice, bob):
    """辅助函数：建立拜访关系。

    Alice 发起拜访 Bob，Bob 处理消息，Alice 处理消息。
    建立后双方都应能看到对方的宠物。
    """
    assert alice.invite_visit('node-bob') is True
    bob.process_lan_queues()
    alice.process_lan_queues()


# ─── Scenario 1: 完整拜访流程（发起方结束）───


class TestFullVisitFlowInitiatorEnds:
    """完整拜访流程：发起→双方进入→结束→双方退出（发起方结束）。

    Given 发起方 A 和受访方 B 两个 PetGame 实例通过 _MessageBus 互联
    When A 调用 invite_visit(B 的 node_id)
    And B 处理消息队列
    Then B 的 being_visited 被设置
    And B 的 visitor_pets[A_node_id] 存储 A 的宠物快照
    And B 回发 MSG_VISIT_DATA（含 from=B_node_id）
    And B 切换到 ExpandedState
    When A 处理消息队列
    Then A 的 visitor_pets[B_node_id] 存储 B 的宠物快照
    And 双方都有两只宠物（自己的 + 对方的）
    When A 调用 end_visit()
    And B 处理消息队列
    Then 双方都回到空闲状态
    """

    def test_complete_flow_initiator_ends(self, two_games):
        """完整拜访流程：发起→双方进入→结束→双方退出（发起方结束）。"""
        alice, bob = two_games

        # 1. Alice 发起拜访 Bob
        assert alice.invite_visit('node-bob') is True
        assert alice.active_visit is not None
        assert alice.active_visit['target'] == 'node-bob'

        # 2. Bob 处理 MSG_VISIT_REQ
        bob.process_lan_queues()
        assert bob.being_visited is not None
        assert bob.being_visited['from'] == 'node-alice'
        assert 'node-alice' in bob.visitor_pets
        assert bob.visitor_pets['node-alice']['name'] == alice.state['name']
        assert bob.mode == 'expanded'
        # Bob 应回发 MSG_VISIT_DATA（含 from=B_node_id）
        data_calls = [c for c in bob.lan_node.send_calls if c[1] == MSG_VISIT_DATA]
        assert len(data_calls) == 1
        assert data_calls[0][2].get('from') == 'node-bob'

        # 3. Alice 处理 MSG_VISIT_DATA
        alice.process_lan_queues()
        assert 'node-bob' in alice.visitor_pets
        assert alice.visitor_pets['node-bob']['name'] == bob.state['name']

        # 4. 验证双方都有访客宠物（自己的 + 对方的）
        assert len(alice.visitor_pets) == 1
        assert len(bob.visitor_pets) == 1

        # 5. Alice 结束拜访
        assert alice.end_visit() is True
        assert alice.active_visit is None
        assert 'node-bob' not in alice.visitor_pets

        # 6. Bob 处理 MSG_VISIT_END
        bob.process_lan_queues()
        assert bob.being_visited is None
        assert 'node-alice' not in bob.visitor_pets

        # 7. 验证双方都回到空闲状态
        assert alice.active_visit is None
        assert alice.being_visited is None
        assert alice.visitor_pets == {}
        assert bob.active_visit is None
        assert bob.being_visited is None
        assert bob.visitor_pets == {}

    def test_alice_active_visit_set_after_invite(self, two_games):
        """A 调用 invite_visit 后，A 的 active_visit 应被设置。"""
        alice, bob = two_games
        assert alice.invite_visit('node-bob') is True
        assert alice.active_visit is not None
        assert alice.active_visit['target'] == 'node-bob'

    def test_bob_being_visited_set_after_processing(self, two_games):
        """B 处理 MSG_VISIT_REQ 后，being_visited 应被设置。"""
        alice, bob = two_games
        alice.invite_visit('node-bob')
        bob.process_lan_queues()
        assert bob.being_visited is not None
        assert bob.being_visited['from'] == 'node-alice'

    def test_bob_visitor_pets_stores_alice_snapshot(self, two_games):
        """B 的 visitor_pets 应以 A_node_id 为 key 存储 A 的宠物快照。"""
        alice, bob = two_games
        alice.invite_visit('node-bob')
        bob.process_lan_queues()
        assert 'node-alice' in bob.visitor_pets
        assert bob.visitor_pets['node-alice']['name'] == alice.state['name']

    def test_bob_sends_visit_data_with_from_field(self, two_games):
        """B 应回发 MSG_VISIT_DATA，且 payload 包含 from=B_node_id。"""
        alice, bob = two_games
        alice.invite_visit('node-bob')
        bob.process_lan_queues()
        data_calls = [c for c in bob.lan_node.send_calls if c[1] == MSG_VISIT_DATA]
        assert len(data_calls) == 1
        _, _, payload = data_calls[0]
        assert payload.get('from') == 'node-bob'

    def test_bob_switches_to_expanded_state(self, two_games):
        """B 收到 MSG_VISIT_REQ 后应切换到 ExpandedState。"""
        alice, bob = two_games
        alice.invite_visit('node-bob')
        bob.process_lan_queues()
        assert bob.mode == 'expanded'

    def test_alice_visitor_pets_stores_bob_snapshot(self, two_games):
        """A 处理 MSG_VISIT_DATA 后，visitor_pets 应以 B_node_id 为 key 存储 B 的快照。"""
        alice, bob = two_games
        alice.invite_visit('node-bob')
        bob.process_lan_queues()
        alice.process_lan_queues()
        assert 'node-bob' in alice.visitor_pets
        assert alice.visitor_pets['node-bob']['name'] == bob.state['name']

    def test_both_sides_have_one_visitor_pet(self, two_games):
        """双方都应有一只访客宠物（自己的 + 对方的 = 两只）。"""
        alice, bob = two_games
        _establish_visit(alice, bob)
        assert len(alice.visitor_pets) == 1
        assert len(bob.visitor_pets) == 1

    def test_both_idle_after_initiator_ends(self, two_games):
        """发起方结束后，双方都应回到空闲状态。"""
        alice, bob = two_games
        _establish_visit(alice, bob)
        alice.end_visit()
        bob.process_lan_queues()
        # Alice 状态
        assert alice.active_visit is None
        assert alice.being_visited is None
        assert alice.visitor_pets == {}
        # Bob 状态
        assert bob.active_visit is None
        assert bob.being_visited is None
        assert bob.visitor_pets == {}


# ─── Scenario 2: 受访方结束拜访 ───


class TestFullVisitFlowVisitedPartyEnds:
    """完整拜访流程：受访方结束拜访。

    Given 拜访已建立
    When B 调用 end_visit()
    And A 处理消息队列
    Then 双方都回到空闲状态
    """

    def test_complete_flow_visited_party_ends(self, two_games):
        """完整拜访流程：受访方结束。"""
        alice, bob = two_games

        # 建立拜访
        _establish_visit(alice, bob)
        assert alice.active_visit is not None
        assert bob.being_visited is not None
        assert 'node-bob' in alice.visitor_pets
        assert 'node-alice' in bob.visitor_pets

        # Bob 结束拜访
        assert bob.end_visit() is True
        assert bob.being_visited is None
        assert 'node-alice' not in bob.visitor_pets

        # Alice 处理 MSG_VISIT_END
        alice.process_lan_queues()
        assert alice.active_visit is None
        assert 'node-bob' not in alice.visitor_pets

        # 验证双方都回到空闲状态
        assert alice.active_visit is None
        assert alice.being_visited is None
        assert alice.visitor_pets == {}
        assert bob.active_visit is None
        assert bob.being_visited is None
        assert bob.visitor_pets == {}

    def test_bob_end_visit_clears_bob_state(self, two_games):
        """B 调用 end_visit() 后，B 的 being_visited 和 visitor_pets 应清除。"""
        alice, bob = two_games
        _establish_visit(alice, bob)
        bob.end_visit()
        assert bob.being_visited is None
        assert 'node-alice' not in bob.visitor_pets

    def test_alice_clears_state_after_receiving_visit_end(self, two_games):
        """A 收到 MSG_VISIT_END 后，active_visit 和 visitor_pets 应清除。"""
        alice, bob = two_games
        _establish_visit(alice, bob)
        bob.end_visit()
        alice.process_lan_queues()
        assert alice.active_visit is None
        assert 'node-bob' not in alice.visitor_pets

    def test_both_idle_after_visited_party_ends(self, two_games):
        """受访方结束后，双方都应回到空闲状态。"""
        alice, bob = two_games
        _establish_visit(alice, bob)
        bob.end_visit()
        alice.process_lan_queues()
        # Alice 状态
        assert alice.active_visit is None
        assert alice.being_visited is None
        assert alice.visitor_pets == {}
        # Bob 状态
        assert bob.active_visit is None
        assert bob.being_visited is None
        assert bob.visitor_pets == {}


# ─── Scenario 3: visitor_pets key 一致性验证 ───


class TestVisitorPetsKeyConsistency:
    """visitor_pets key 一致性验证：存取删使用同一 node_id key。

    Given 拜访已建立
    Then A 的 visitor_pets key 是 B_node_id（不是用户名）
    And B 的 visitor_pets key 是 A_node_id（不是用户名）
    When 拜访结束
    Then 双方 visitor_pets 都为空（key 一致所以能正确删除）
    """

    def test_alice_visitor_pets_key_is_bob_node_id(self, two_games):
        """A 的 visitor_pets key 应为 B_node_id，不是用户名 'Bob'。"""
        alice, bob = two_games
        _establish_visit(alice, bob)
        assert 'node-bob' in alice.visitor_pets
        assert 'Bob' not in alice.visitor_pets

    def test_bob_visitor_pets_key_is_alice_node_id(self, two_games):
        """B 的 visitor_pets key 应为 A_node_id，不是用户名 'Alice'。"""
        alice, bob = two_games
        _establish_visit(alice, bob)
        assert 'node-alice' in bob.visitor_pets
        assert 'Alice' not in bob.visitor_pets

    def test_keys_consistent_store_and_delete_initiator_ends(self, two_games):
        """存取删使用同一 key：发起方结束时双方 visitor_pets 都应为空。"""
        alice, bob = two_games
        _establish_visit(alice, bob)
        # 验证 key 一致
        assert 'node-bob' in alice.visitor_pets
        assert 'node-alice' in bob.visitor_pets
        # 结束拜访
        alice.end_visit()
        bob.process_lan_queues()
        # key 一致所以能正确删除
        assert alice.visitor_pets == {}
        assert bob.visitor_pets == {}

    def test_keys_consistent_store_and_delete_visited_party_ends(self, two_games):
        """存取删使用同一 key：受访方结束时双方 visitor_pets 都应为空。"""
        alice, bob = two_games
        _establish_visit(alice, bob)
        # 验证 key 一致
        assert 'node-bob' in alice.visitor_pets
        assert 'node-alice' in bob.visitor_pets
        # 结束拜访
        bob.end_visit()
        alice.process_lan_queues()
        # key 一致所以能正确删除
        assert alice.visitor_pets == {}
        assert bob.visitor_pets == {}
