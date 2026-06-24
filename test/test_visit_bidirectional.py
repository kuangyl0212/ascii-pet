#!/usr/bin/env python3
"""TDD tests for bidirectional visit flow fixes.

Bug description:
- visitor_pets key is inconsistent: sometimes node_id, sometimes username (owner)
  导致清理失败：存的时候用 owner (用户名)，删的时候用 from (node_id)
- 受访方收到 MSG_VISIT_REQ 后不切换到 ExpandedState，看不到访客宠物
- MSG_VISIT_DATA 回发时缺少 from 字段，发起方无法用 node_id 作为 key 存储

Fix plan:
- Task 1: 统一 visitor_pets key 为 node_id
  - receive_visitor 接受 node_id 参数
  - MSG_VISIT_DATA handler 传 payload["from"] 作为 node_id
- Task 3: 受访方收到 MSG_VISIT_REQ 后自动切换到 ExpandedState
- Task 4: MSG_VISIT_DATA 回发包含 from 字段（受访方 node_id）

BDD Scenarios:

  Feature: Bidirectional Visit Flow Fixes

    Scenario: receive_visitor 用 node_id 作为 key
      Given 一个 owner='bob-username' 的宠物快照
      When 调用 receive_visitor(snapshot, node_id='peer-bob-node-id')
      Then visitor_pets 应以 'peer-bob-node-id' 为 key 存储快照
      And 不应以 'bob-username' 为 key 存储

    Scenario: MSG_VISIT_DATA handler 用 payload['from'] 作为 key
      Given 一个 from='peer-bob' owner='bob-username' 的 MSG_VISIT_DATA
      When 游戏处理 MSG_VISIT_DATA
      Then visitor_pets 应以 'peer-bob' 为 key 存储
      And 不应以 'bob-username' 为 key 存储

    Scenario: 受访方收到 VISIT_REQ 后切换到 ExpandedState
      Given 游戏处于 CompactState
      When 游戏收到 MSG_VISIT_REQ
      Then 游戏应切换到 ExpandedState

    Scenario: MSG_VISIT_DATA 回发包含 from 字段
      Given 游戏收到来自 Alice 的 MSG_VISIT_REQ
      When 游戏回发 MSG_VISIT_DATA
      Then MSG_VISIT_DATA payload 应包含 'from' 字段
      And 'from' 字段应为受访方的 node_id

    Scenario: visitor_pets 存取删使用同一 key（node_id）
      Given 收到 from='peer-bob' 的 MSG_VISIT_DATA（按 node_id 存储）
      When 收到 from='peer-bob' 的 MSG_VISIT_END（按 node_id 删除）
      Then visitor_pets 中 'peer-bob' 条目应被移除
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
    make_pet_snapshot,
)


def _uid():
    """生成唯一 uid 避免状态冲突。"""
    return f'test-visit-bidir-{int(time.time() * 1000000)}-{os.urandom(4).hex()}'


def _make_snapshot(name='VisitorPet', owner='visitor-owner', species='cat'):
    """构建最小宠物快照 dict，匹配 make_pet_snapshot 输出。"""
    return {
        'name': name,
        'species': species,
        'rarity': 'common',
        'level': 1,
        'shiny': False,
        'eye': '·',
        'hat': 'none',
        'mood': 'normal',
        'owner': owner,
        'hp': 100,
        'attack': 0,
        'defense': 0,
        'speed': 0,
        'skills': [],
    }


class _FakeLanNode:
    """测试用假 LanNode，无需真实网络。"""

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
        self._peers = []
        self.send_calls = []

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
        return True

    def send_broadcast(self, msg_type, payload):
        return True


@pytest.fixture
def game(tmp_path):
    """提供全新 PetGame，隔离临时目录并启用 LAN。"""
    uid = _uid()
    g = PetGame(uid, data_dir=tmp_path)
    fake_node = _FakeLanNode('alice', g.state)
    with patch('ascii_pet.lan.LanNode', return_value=fake_node):
        g.enable_lan('alice')
    return g


# ─── Task 1: receive_visitor 接受 node_id 参数 ───


class TestReceiveVisitorWithNodeId:
    """receive_visitor 应接受可选的 node_id 参数，并用其作为 visitor_pets
    的 key，而不是 snapshot['owner']。

    Given 一个 owner='bob-username' 的宠物快照
    When 调用 receive_visitor(snapshot, node_id='peer-bob-node-id')
    Then visitor_pets 应以 'peer-bob-node-id' 为 key 存储快照
    """

    def test_receive_visitor_uses_node_id_as_key(self, game):
        """提供 node_id 时，应以其作为 key。"""
        snap = _make_snapshot(name='Buddy', owner='bob-username')
        game.receive_visitor(snap, node_id='peer-bob-node-id')

        assert 'peer-bob-node-id' in game.visitor_pets
        assert game.visitor_pets['peer-bob-node-id']['name'] == 'Buddy'

    def test_receive_visitor_node_id_takes_precedence_over_owner(self, game):
        """node_id 应优先于 snapshot['owner'] 作为 key。"""
        snap = _make_snapshot(name='Buddy', owner='bob-username')
        game.receive_visitor(snap, node_id='peer-bob-node-id')

        assert 'peer-bob-node-id' in game.visitor_pets
        assert 'bob-username' not in game.visitor_pets

    def test_receive_visitor_empty_node_id_falls_back_to_owner(self, game):
        """空 node_id 应回退到 snapshot['owner']，保持向后兼容。"""
        snap = _make_snapshot(name='Buddy', owner='bob-username')
        game.receive_visitor(snap, node_id='')

        assert 'bob-username' in game.visitor_pets


# ─── Task 1: MSG_VISIT_DATA handler 用 payload['from'] 作为 key ───


class TestVisitDataHandlerUsesFromAsKey:
    """MSG_VISIT_DATA handler 应使用 payload['from'] (node_id) 作为
    visitor_pets 的 key，而不是 payload['owner'] (用户名)。

    Given 一个 from='peer-bob' owner='bob-username' 的 MSG_VISIT_DATA
    When 游戏处理 MSG_VISIT_DATA
    Then visitor_pets 应以 'peer-bob' 为 key 存储
    And 不应以 'bob-username' 为 key 存储
    """

    def test_visit_data_uses_from_field_as_key(self, game):
        """MSG_VISIT_DATA handler 应用 payload['from'] 作为 key。"""
        bob_snapshot = _make_snapshot(name='BobPet', owner='bob-username')
        bob_snapshot['from'] = 'peer-bob'

        game.lan_node.ui_queue.put({
            'type': MSG_VISIT_DATA,
            'payload': bob_snapshot,
        })

        game.process_lan_queues()

        assert 'peer-bob' in game.visitor_pets, (
            "MSG_VISIT_DATA 应以 'from' (node_id) 为 key 存储快照"
        )
        assert 'bob-username' not in game.visitor_pets, (
            "MSG_VISIT_DATA 有 'from' 时不应使用 'owner' (用户名) 作为 key"
        )


# ─── Task 3: 受访方收到 VISIT_REQ 后切换到 ExpandedState ───


class TestVisitedPartySwitchesToExpanded:
    """当受访方收到 MSG_VISIT_REQ 时，应自动切换到 ExpandedState，
    这样访客宠物就能立即在屏幕上显示。

    Given 游戏处于 CompactState
    When 游戏收到 MSG_VISIT_REQ
    Then 游戏应切换到 ExpandedState
    """

    def test_visit_req_transitions_to_expanded(self, game):
        """MSG_VISIT_REQ 应导致切换到 ExpandedState。"""
        assert game.mode == 'compact', "游戏应从 compact 模式开始"

        alice_snapshot = _make_snapshot(name='AlicePet', owner='peer-alice')
        game.lan_node.ui_queue.put({
            'type': MSG_VISIT_REQ,
            'payload': {
                'from': 'peer-alice',
                'from_username': 'Alice',
                'pet_snapshot': alice_snapshot,
            },
        })

        game.process_lan_queues()

        assert game.mode == 'expanded', (
            "收到 VISIT_REQ 后游戏应切换到 expanded 模式"
        )


# ─── Task 4: MSG_VISIT_DATA 回发包含 from 字段 ───


class TestVisitDataReplyIncludesFromField:
    """当受访方回发 MSG_VISIT_DATA 时，payload 应包含 'from' 字段，
    其值为受访方的 node_id，这样发起方就能用正确的 key 存储快照。

    Given 游戏收到来自 Alice 的 MSG_VISIT_REQ
    When 游戏回发 MSG_VISIT_DATA
    Then MSG_VISIT_DATA payload 应包含 'from' 字段
    And 'from' 字段应为受访方的 node_id
    """

    def test_visit_data_reply_contains_from_field(self, game):
        """MSG_VISIT_DATA 回发应包含 'from' 字段。"""
        alice_snapshot = _make_snapshot(name='AlicePet', owner='peer-alice')
        game.lan_node.ui_queue.put({
            'type': MSG_VISIT_REQ,
            'payload': {
                'from': 'peer-alice',
                'from_username': 'Alice',
                'pet_snapshot': alice_snapshot,
            },
        })

        game.process_lan_queues()

        data_calls = [c for c in game.lan_node.send_calls if c[1] == MSG_VISIT_DATA]
        assert len(data_calls) == 1
        _, _, payload = data_calls[0]
        assert 'from' in payload, (
            "MSG_VISIT_DATA 回发应包含 'from' 字段"
        )

    def test_visit_data_reply_from_is_visited_party_node_id(self, game):
        """MSG_VISIT_DATA 的 'from' 字段应为受访方的 node_id。"""
        alice_snapshot = _make_snapshot(name='AlicePet', owner='peer-alice')
        game.lan_node.ui_queue.put({
            'type': MSG_VISIT_REQ,
            'payload': {
                'from': 'peer-alice',
                'from_username': 'Alice',
                'pet_snapshot': alice_snapshot,
            },
        })

        game.process_lan_queues()

        data_calls = [c for c in game.lan_node.send_calls if c[1] == MSG_VISIT_DATA]
        assert len(data_calls) == 1
        _, _, payload = data_calls[0]
        assert payload.get('from') == game.lan_node.node_id, (
            f"MSG_VISIT_DATA 'from' 应为受访方 node_id "
            f"{game.lan_node.node_id!r}, 实际为 {payload.get('from')!r}"
        )


# ─── 集成: visitor_pets 存取删使用同一 key（node_id） ───


class TestVisitorPetsKeyConsistency:
    """visitor_pets 在存储和删除时应使用同一 key (node_id)。
    这是核心 bug：存储用 owner (用户名)，删除用 from (node_id)，导致清理失败。

    Given 收到 from='peer-bob' 的 MSG_VISIT_DATA（按 node_id 存储）
    When 收到 from='peer-bob' 的 MSG_VISIT_END（按 node_id 删除）
    Then visitor_pets 中 'peer-bob' 条目应被移除
    """

    def test_store_and_delete_use_same_node_id_key(self, game):
        """存储 (MSG_VISIT_DATA) 和删除 (MSG_VISIT_END) 应使用同一 node_id key。"""
        # 存储：收到 from='peer-bob' 的 MSG_VISIT_DATA
        bob_snapshot = _make_snapshot(name='BobPet', owner='bob-username')
        bob_snapshot['from'] = 'peer-bob'
        game.lan_node.ui_queue.put({
            'type': MSG_VISIT_DATA,
            'payload': bob_snapshot,
        })
        game.process_lan_queues()

        assert 'peer-bob' in game.visitor_pets, (
            "MSG_VISIT_DATA 后，快照应以 'from' (node_id) 为 key 存储"
        )

        # 设置 active_visit 以便 MSG_VISIT_END handler 清理
        game.active_visit = {
            'target': 'peer-bob',
            'start_time': time.time(),
            'pet_snapshot': _make_snapshot(name='AlicePet'),
        }

        # 删除：收到 from='peer-bob' 的 MSG_VISIT_END
        game.lan_node.ui_queue.put({
            'type': MSG_VISIT_END,
            'payload': {'reason': 'manual', 'from': 'peer-bob'},
        })
        game.process_lan_queues()

        assert 'peer-bob' not in game.visitor_pets, (
            "MSG_VISIT_END 后，应按 node_id 移除 visitor_pets 条目"
        )
