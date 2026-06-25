"""Shared pytest fixtures for all test modules.

Ensures the i18n language is set to English before each test,
so that tests asserting English strings work regardless of system locale.
Also prevents real LAN network from starting during tests, and cleans up
any leaked LAN threads.
"""
import gc
import os, sys
import threading
import warnings
from unittest.mock import patch, MagicMock

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


@pytest.fixture(autouse=True)
def _isolate_logging():
    """Prevent setup_logging() from opening log files in test temp directories.

    PetGame.__init__ calls setup_logging(data_dir), which opens a log file in
    data_dir/logs/. In tests using tempfile.TemporaryDirectory(), this open
    file handle prevents Windows from deleting the temp dir. Patch the
    setup_logging reference in core.py to a no-op so logging uses loguru's
    default stderr sink. test_log.py imports setup_logging directly from
    ascii_pet.log, so it is unaffected.
    """
    from ascii_pet import core
    from ascii_pet.log import logger as _logger
    _logger.remove()  # Clean up sinks from previous tests
    original = core.setup_logging
    core.setup_logging = lambda *a, **kw: None
    try:
        yield
    finally:
        core.setup_logging = original
        _logger.remove()  # Clean up any sinks created during this test


@pytest.fixture(autouse=True)
def _prevent_real_lan(request):
    """Prevent PetGame.__init__ from starting real LanNode during tests.

    PetGame.__init__ auto-calls enable_lan(), which creates real UDP/TCP
    sockets and spawns 3 daemon threads. This is expensive and unnecessary
    in unit tests. By patching LanNode.start to return False, enable_lan()
    gracefully fails without creating any network resources.

    Skipped for test_lan_network.py which directly tests LanNode with its
    own socket mocks.

    LAN-specific tests in test_lan_game.py override this by patching
    'ascii_pet.lan.LanNode' with their own fake node, which is unaffected
    since the entire class reference is replaced.
    """
    # test_lan_network.py directly tests LanNode with its own socket mocks
    if 'test_lan_network' in request.node.nodeid:
        yield
        return
    from ascii_pet.lan import LanNode
    with patch.object(LanNode, 'start', return_value=False):
        yield


def _get_lan_thread_names():
    """返回当前存活的 lan-* 线程名集合。"""
    return {t.name for t in threading.enumerate() if t.name.startswith("lan-")}


def _cleanup_all_lan_nodes():
    """遍历所有 PetGame 和 LanNode 实例，清理 LAN 线程。

    由于 _prevent_real_lan fixture 已阻止真实 LanNode 启动，
    大多数情况下无需执行昂贵的 gc 操作。仅当检测到 lan-* 线程
    时才进行完整清理。
    """
    # 快速检查：如果没有 lan-* 线程，跳过昂贵的 gc 操作
    if not _get_lan_thread_names():
        return
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
