#!/usr/bin/env python3
"""TDD tests for Task 2: invite_visit failure handling.

Bug description:
- When `send_to_peer` returns False in `invite_visit`, the method returns
  False without setting any error message. The code comment says
  "invite_visit sets its own error message on failure" but it actually
  doesn't. Users get no feedback and think the app "froze".
- Additionally, the first early return (`if not self.lan_enabled or not
  self.lan_node:`) also returns False without any error message.

BDD Scenarios:

  Feature: invite_visit Failure Feedback

    Scenario: invite_visit reports error when send_to_peer fails
      Given Alice has LAN enabled and tries to visit Bob
      When send_to_peer returns False
      Then invite_visit should return False
      And game.message should be "Failed to send visit request"
      And game.active_visit should remain None

    Scenario: invite_visit reports error when LAN is not enabled
      Given Alice has LAN disabled
      When Alice tries to invite_visit a peer
      Then invite_visit should return False
      And game.message should be "LAN not enabled"
"""
import os
import sys
import time
import queue
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from ascii_pet.core import PetGame


def _uid():
    """生成每个测试唯一的 uid，避免状态冲突。"""
    return f'test-invite-fail-{int(time.time() * 1000000)}-{os.urandom(4).hex()}'


class _FakeLanNode:
    """用于测试的假 LanNode，可控制 send_to_peer 的返回值。"""

    def __init__(self, username, pet_state, send_result=True):
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
        self._send_result = send_result

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
        return self._send_result

    def send_broadcast(self, msg_type, payload):
        return True


@pytest.fixture
def game_with_lan(tmp_path):
    """提供启用了 LAN 的 PetGame（send_to_peer 默认返回 True）。"""
    uid = _uid()
    g = PetGame(uid, data_dir=tmp_path)
    fake_node = _FakeLanNode('alice', g.state, send_result=True)
    with patch('ascii_pet.lan.LanNode', return_value=fake_node):
        g.enable_lan('alice')
    return g


@pytest.fixture
def game_with_failing_send(tmp_path):
    """提供启用了 LAN 但 send_to_peer 总是返回 False 的 PetGame。"""
    uid = _uid()
    g = PetGame(uid, data_dir=tmp_path)
    fake_node = _FakeLanNode('alice', g.state, send_result=False)
    with patch('ascii_pet.lan.LanNode', return_value=fake_node):
        g.enable_lan('alice')
    return g


@pytest.fixture
def game_without_lan(tmp_path):
    """提供未启用 LAN 的 PetGame。"""
    uid = _uid()
    g = PetGame(uid, data_dir=tmp_path)
    # 不调用 enable_lan，lan_enabled 保持 False，lan_node 保持 None
    return g


# ─── BDD Scenario 1: invite_visit reports error when send_to_peer fails ───


class TestInviteVisitSendFailure:
    """当 send_to_peer 返回 False 时，invite_visit 应给出错误反馈。

    Given Alice 启用了 LAN 并尝试拜访 Bob
    When send_to_peer 返回 False
    Then invite_visit 应返回 False
    And game.message 应为 "Failed to send visit request"
    And game.active_visit 应保持为 None
    """

    def test_invite_visit_returns_false_when_send_fails(self, game_with_failing_send):
        """send_to_peer 失败时 invite_visit 应返回 False。"""
        result = game_with_failing_send.invite_visit('peer-bob')
        assert result is False, (
            "invite_visit 应在 send_to_peer 失败时返回 False"
        )

    def test_invite_visit_sets_error_message_when_send_fails(self, game_with_failing_send):
        """send_to_peer 失败时应设置错误消息 'Failed to send visit request'。"""
        game_with_failing_send.message = None
        game_with_failing_send.message_time = 0
        game_with_failing_send.invite_visit('peer-bob')
        assert game_with_failing_send.message == "Failed to send visit request", (
            f"send_to_peer 失败时应设置 message='Failed to send visit request'，"
            f"实际得到 {game_with_failing_send.message!r}"
        )

    def test_invite_visit_sets_message_time_when_send_fails(self, game_with_failing_send):
        """send_to_peer 失败时应设置 message_time 为当前时间。"""
        game_with_failing_send.message = None
        game_with_failing_send.message_time = 0
        before = time.time()
        game_with_failing_send.invite_visit('peer-bob')
        after = time.time()
        assert before <= game_with_failing_send.message_time <= after, (
            "message_time 应被设置为当前时间"
        )

    def test_invite_visit_does_not_set_active_visit_when_send_fails(self, game_with_failing_send):
        """send_to_peer 失败时不应设置 active_visit。"""
        game_with_failing_send.active_visit = None
        game_with_failing_send.invite_visit('peer-bob')
        assert game_with_failing_send.active_visit is None, (
            "send_to_peer 失败时 active_visit 应保持为 None"
        )


# ─── BDD Scenario 2: invite_visit reports error when LAN is not enabled ───


class TestInviteVisitLanDisabled:
    """当 LAN 未启用时，invite_visit 应给出错误反馈。

    Given Alice 未启用 LAN
    When Alice 尝试 invite_visit 一个 peer
    Then invite_visit 应返回 False
    And game.message 应为 "LAN not enabled"
    """

    def test_invite_visit_returns_false_when_lan_disabled(self, game_without_lan):
        """LAN 未启用时 invite_visit 应返回 False。"""
        result = game_without_lan.invite_visit('peer-bob')
        assert result is False, (
            "invite_visit 应在 LAN 未启用时返回 False"
        )

    def test_invite_visit_sets_error_message_when_lan_disabled(self, game_without_lan):
        """LAN 未启用时应设置错误消息 'LAN not enabled'。"""
        game_without_lan.message = None
        game_without_lan.message_time = 0
        game_without_lan.invite_visit('peer-bob')
        assert game_without_lan.message == "LAN not enabled", (
            f"LAN 未启用时应设置 message='LAN not enabled'，"
            f"实际得到 {game_without_lan.message!r}"
        )

    def test_invite_visit_sets_message_time_when_lan_disabled(self, game_without_lan):
        """LAN 未启用时应设置 message_time 为当前时间。"""
        game_without_lan.message = None
        game_without_lan.message_time = 0
        before = time.time()
        game_without_lan.invite_visit('peer-bob')
        after = time.time()
        assert before <= game_without_lan.message_time <= after, (
            "message_time 应被设置为当前时间"
        )
