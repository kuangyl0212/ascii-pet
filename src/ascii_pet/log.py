"""统一日志模块，基于 loguru。

提供全局 logger 单例和 setup_logging() 初始化函数。
日志文件存放于 data_dir/logs/ascii-pet.log，支持轮转/保留/压缩。

使用方式：
    from ascii_pet.log import logger, setup_logging
    setup_logging(data_dir=...)  # 初始化（通常在 PetGame.__init__ 中调用）
    logger.info("message")       # 各模块直接使用全局单例
"""
import sys
from pathlib import Path

from loguru import logger

__all__ = ['logger', 'setup_logging']

_LOG_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} [{level:<7}] "
    "{name}:{function}:{line} | {message}"
)


def setup_logging(data_dir=None, level="INFO", console=True):
    """初始化日志配置。

    Args:
        data_dir: 数据目录路径（字符串或 Path）。None 时回退到 _default_data_dir()。
        level: 文件 sink 日志级别，默认 "INFO"。
        console: 是否添加终端 sink（stderr，WARNING 级别，彩色）。

    Returns:
        loguru logger 实例
    """
    # 幂等：先清除旧 sink
    logger.remove()

    # 探测 data_dir
    if data_dir is None:
        try:
            from ascii_pet.core import _default_data_dir
            data_dir = _default_data_dir()
        except Exception:
            data_dir = None

    # 配置文件 sink
    if data_dir is not None:
        try:
            log_dir = Path(data_dir) / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "ascii-pet.log"
            logger.add(
                str(log_file),
                rotation="1 MB",
                retention=5,
                compression="zip",
                enqueue=True,
                level=level,
                format=_LOG_FORMAT,
                encoding="utf-8",
            )
        except Exception as e:
            # 降级：仅终端 sink（此时 warning 无 sink 接收，但不抛异常）
            # 先添加终端 sink 再记录降级原因
            if console and sys.stderr is not None:
                logger.add(
                    sys.stderr,
                    level="WARNING",
                    format=_LOG_FORMAT,
                    colorize=True,
                )
            logger.warning(f"Failed to configure file sink: {e}, falling back to console only")
            return logger

    # 配置终端 sink（--noconsole 模式下 sys.stderr 为 None，需跳过）
    if console and sys.stderr is not None:
        logger.add(
            sys.stderr,
            level="WARNING",
            format=_LOG_FORMAT,
            colorize=True,
        )

    return logger
