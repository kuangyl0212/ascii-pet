"""Shared pytest fixtures for all test modules.

Ensures the i18n language is set to English before each test,
so that tests asserting English strings work regardless of system locale.
Also tracks and cleans up LAN threads leaked by PetGame instances.
"""
import gc
import os, sys
import threading
import warnings
from unittest.mock import patch

# Add src/ to path so ascii_pet package is importable
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import pytest
from ascii_pet import i18n


@pytest.fixture(autouse=True)
def _set_english_language():
    """Reset language to English before each test.

    PetGame.__init__ calls init_language(), which may detect a Chinese
    system locale and switch to Chinese. This fixture patches
    _detect_system_language to return 'en' so that init_language()
    without saved settings defaults to English instead of the system locale.
    """
    i18n.set_language('en')
    with patch.object(i18n, '_detect_system_language', return_value='en'):
        yield


def _get_lan_thread_names():
    """返回当前存活的 lan-* 线程名集合。"""
    return {t.name for t in threading.enumerate() if t.name.startswith("lan-")}


def _cleanup_all_lan_nodes():
    """遍历所有 PetGame 和 LanNode 实例，清理 LAN 线程。

    PetGame.__init__ 自动调用 enable_lan()，但测试 fixture 通常
    不在 teardown 调用 disable_lan()，导致 lan-* 线程泄漏。
    某些测试还会用 _FakeLanNode 替换 lan_node，导致真实 LanNode
    失去引用但线程仍在运行。此函数清理所有情况。
    """
    import time
    from ascii_pet.core import PetGame
    from ascii_pet.lan import LanNode
    gc.collect()
    # 清理 PetGame 实例
    for obj in gc.get_objects():
        if isinstance(obj, PetGame):
            if getattr(obj, 'lan_enabled', False) or getattr(obj, 'lan_node', None) is not None:
                try:
                    obj.disable_lan()
                except Exception:
                    pass
    # 清理所有独立的 LanNode 实例（包括被 PetGame 引用丢失的）
    for obj in gc.get_objects():
        if isinstance(obj, LanNode) and getattr(obj, 'enabled', False):
            try:
                obj.stop()
            except Exception:
                pass
    # 等待线程退出（stop() 的 join 有超时，线程可能还在退出中）
    time.sleep(0.3)


@pytest.fixture(autouse=True)
def _assert_no_lan_threads_leak(request):
    """每个测试后清理 PetGame 泄漏的 LAN 线程并检测残留泄漏。

    先调用 _cleanup_all_lan_nodes 清理所有 PetGame 实例的 LAN 线程，
    再检测是否仍有 lan-* 线程残留（说明存在非 PetGame 的 LanNode
    未正确 stop()）。
    """
    before = _get_lan_thread_names()
    yield
    # 先清理所有 PetGame 实例的 LAN 线程
    _cleanup_all_lan_nodes()
    # 再检测是否仍有残留
    after = _get_lan_thread_names()
    leaked = after - before
    if not leaked:
        return
    msg = f"测试泄漏了 lan-* 线程: {leaked}。请确保 LanNode.stop() 被调用。"
    pytest.fail(msg)
