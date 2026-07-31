"""
存储后端（MySQL 唯一）
=====================

个人数据（待办 / 笔记 / 提醒）与历史会话统一使用 MySQL 持久化。首次连接
自动建库建表，并自动迁移旧版 .agent_personal/ 与 .agent_history/ 下的存量
数据（仅一次性迁移）。

- create_personal_manager() → personal_mysql.MySQLPersonalManager
- create_session_store()     → history.MySQLSessionStore

MySQL 不可用时（pymysql 未安装 / 连接失败 / 配置错误）直接抛 RuntimeError
终止启动，绝不静默降级，避免数据写错地方。

独立成模块是为了避免 personal.py 与 personal_mysql.py 互相导入造成循环依赖：
    storage → personal_mysql（延迟导入）→ personal（纯函数）
    storage → history（MySQLSessionStore，延迟导入）
"""

from history import MySQLSessionStore
from personal_mysql import MySQLPersonalManager


def create_personal_manager() -> MySQLPersonalManager:
    """创建个人数据（待办 / 笔记 / 提醒）的 MySQL 管理器。

    首次实例化会自动建库建表，并把旧版 .agent_personal/ 下的存量数据
    一次性迁移进库。

    Raises:
        RuntimeError: MySQL 初始化失败（连接失败 / pymysql 未安装 /
            配置错误）时抛出，提示调用方修复后重试。
    """
    try:
        from dotenv import load_dotenv

        _ = load_dotenv()  # 幂等：已加载过的环境变量不会被覆盖
    except Exception:  # noqa: BLE001
        pass
    try:
        return MySQLPersonalManager()
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(
            "MySQL 存储初始化失败（" + type(e).__name__ + ": " + str(e) + "）。\n"
            + "本程序要求必须使用 MySQL 存储。请检查：\n"
            + "  1) pymysql 是否安装：pip install pymysql\n"
            + "  2) MySQL 服务是否启动（默认 127.0.0.1:3306）\n"
            + "  3) .env 中 MYSQL_HOST / MYSQL_PORT / MYSQL_USER / "
            + "MYSQL_PASSWORD / MYSQL_DATABASE 是否正确"
        ) from e


def create_session_store() -> MySQLSessionStore:
    """创建历史会话的 MySQL 存储。

    首次实例化会自动建库建表，并把旧版 .agent_history/ 下的存量数据
    一次性迁移进库。

    Raises:
        RuntimeError: MySQL 初始化失败（连接失败 / pymysql 未安装 /
            配置错误）时抛出，提示调用方修复后重试。
    """
    try:
        from dotenv import load_dotenv

        _ = load_dotenv()  # 幂等：已加载过的环境变量不会被覆盖
    except Exception:  # noqa: BLE001
        pass
    try:
        return MySQLSessionStore()
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(
            "MySQL 历史会话存储初始化失败（" + type(e).__name__ + ": " + str(e) + "）。\n"
            + "本程序要求必须使用 MySQL 存储。请检查：\n"
            + "  1) pymysql 是否安装：pip install pymysql\n"
            + "  2) MySQL 服务是否启动（默认 127.0.0.1:3306）\n"
            + "  3) .env 中 MYSQL_HOST / MYSQL_PORT / MYSQL_USER / "
            + "MYSQL_PASSWORD / MYSQL_DATABASE 是否正确"
        ) from e
