"""
今日老婆插件
"""
import sqlite3
import random
import datetime
import json
from pathlib import Path
from typing import Optional, Type, Tuple, List, Union
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

from src.plugin_system import (
    BaseCommand,
    BasePlugin,
    register_plugin,
    ConfigField,
    ComponentInfo,
    chat_api,
    get_logger
)

logger = get_logger("jrlp-plugin")

class JrlpDatabase:
    """今日老婆数据库管理类"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """初始化数据库表结构"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS jrlp (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    qq VARCHAR(20) NOT NULL,
                    wife VARCHAR(20) NOT NULL,
                    "group" VARCHAR(20) NOT NULL,
                    date DATE NOT NULL
                )
            ''')
            # 添加索引优化查询
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_jrlp_query 
                ON jrlp(qq, "group", date)
            ''')
            conn.commit()

    def get_today_wife(self, qq: str, group: str, date: str) -> Optional[str]:
        """查询用户今日是否已抽取老婆

        Args:
            qq: 用户QQ号
            group: 群号
            date: 日期 (YYYY-MM-DD格式)

        Returns:
            老婆的QQ号，如果未抽取过则返回None
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT wife FROM jrlp WHERE qq = ? AND "group" = ? AND date = ?',
                (qq, group, date)
            )
            result = cursor.fetchone()
            return result[0] if result else None

    def save_wife(self, qq: str, wife: str, group: str, date: str):
        """保存抽取结果

        Args:
            qq: 用户QQ号
            wife: 老婆的QQ号
            group: 群号
            date: 日期 (YYYY-MM-DD格式)
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO jrlp (qq, wife, "group", date) VALUES (?, ?, ?, ?)',
                (qq, wife, group, date)
            )
            conn.commit()


# ============ Command 类 ============

class JrlpCommand(BaseCommand):
    command_name = "jrlp"
    command_description = "今日老婆 - 在群里随机抽一位群友当一天群老婆"
    command_pattern = r'^(今日老婆|抽老婆|jrlp)$'

    def _make_request(self, url: str, payload: dict) -> Tuple[bool, Union[dict, str]]:
        """发送HTTP POST请求到napcat

        Args:
            url: 请求URL
            payload: 请求数据

        Returns:
            (True, response_data) 成功时
            (False, error_message) 失败时
        """
        try:
            data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            request = Request(
                url,
                data=data,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            with urlopen(request, timeout=10) as response:
                result = json.loads(response.read().decode('utf-8'))
                return True, result
        except HTTPError as e:
            return False, f"HTTP错误: {e.code}"
        except URLError as e:
            return False, f"网络错误: {e.reason}"
        except json.JSONDecodeError as e:
            return False, f"JSON解析错误: {e}"
        except Exception as e:
            return False, f"请求错误: {str(e)}"

    def get_group_member_list(self, address: str, port: int, group_id: str) -> Tuple[bool, Union[list, str]]:
        """获取群成员列表

        Args:
            address: napcat服务器地址
            port: napcat服务器端口
            group_id: 群号

        Returns:
            (True, member_list) 成功时返回成员列表
            (False, error_msg) 失败时返回错误信息
        """
        url = f"http://{address}:{port}/get_group_member_list"
        payload = {"group_id": group_id, "no_cache": False}

        success, result = self._make_request(url, payload)
        if not success:
            return False, result

        data = result.get("data")
        if data is None:
            return False, "获取群成员列表失败：返回数据为空"
        return True, data

    def get_member_info(self, address: str, port: int, group_id: str, user_id: str) -> Tuple[bool, Union[dict, str]]:
        """获取单个群成员信息

        Args:
            address: napcat服务器地址
            port: napcat服务器端口
            group_id: 群号
            user_id: 用户QQ号

        Returns:
            (True, member_info) 成功时返回成员信息字典
            (False, error_msg) 失败时返回错误信息
        """
        url = f"http://{address}:{port}/get_group_member_info"
        payload = {"group_id": group_id, "user_id": user_id, "no_cache": True}

        success, result = self._make_request(url, payload)
        if not success:
            return False, result

        data = result.get("data")
        if data is None:
            return False, "获取群成员信息失败：返回数据为空"
        return True, data

    def get_group_info(self, address: str, port: int, group_id: str) -> Tuple[bool, Union[dict, str]]:
        """获取群信息

        Args:
            address: napcat服务器地址
            port: napcat服务器端口
            group_id: 群号

        Returns:
            (True, group_info) 成功时返回群信息字典
            (False, error_msg) 失败时返回错误信息
        """
        url = f"http://{address}:{port}/get_group_info"
        payload = {"group_id": group_id, "no_cache": False}

        success, result = self._make_request(url, payload)
        if not success:
            return False, result

        data = result.get("data")
        if data is None:
            return False, "获取群信息失败：返回数据为空"
        return True, data

    def send_group_message(self, address: str, port: int, group_id: str, message: list) -> Tuple[bool, Optional[str]]:
        """发送群消息

        Args:
            address: napcat服务器地址
            port: napcat服务器端口
            group_id: 群号
            message: 消息段列表

        Returns:
            (True, None) 成功时
            (False, error_msg) 失败时
        """
        url = f"http://{address}:{port}/send_group_msg"
        payload = {
            "group_id": group_id,
            "message": message,
            "storage_message": False  # 按要求设为false
        }

        success, result = self._make_request(url, payload)
        if not success:
            return False, result
        return True, None

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        # 获取配置
        napcat_address = self.get_config("napcat.address")
        napcat_port = self.get_config("napcat.port")

        # 获取聊天流信息
        chat_stream = self.message.chat_stream
        stream_type = chat_api.get_stream_type(chat_stream)
        user_id = str(chat_stream.user_info.user_id)

        # 检查是否为群聊
        if stream_type != "group":
            return False, "该命令仅支持群聊环境", False

        group_id = str(chat_stream.group_info.group_id)
        today = datetime.datetime.now().strftime("%Y-%m-%d")

        # 初始化数据库
        current_dir = Path(__file__).parent.absolute()
        db_path = current_dir / "jrlp.db"
        db = JrlpDatabase(db_path)

        # 查询今日是否已抽取
        existing_wife = db.get_today_wife(user_id, group_id, today)

        if existing_wife:
            # 已抽取过，获取老婆信息并返回
            success, wife_info = self.get_member_info(napcat_address, napcat_port, group_id, existing_wife)
            if not success:
                logger.error(f"获取已抽取老婆信息失败: {wife_info}")
                return False, f"获取信息失败: {wife_info}", True

            wife_nickname = wife_info.get("card") or wife_info.get("nickname", "未知")
            message = [
                {"type": "at", "data": {"qq": user_id}},
                {"type": "text", "data": {"text": "\n"}},
                {"type": "image", "data": {"file": f"https://q1.qlogo.cn/g?b=qq&nk={existing_wife}&s=640", "summary": "[图片]"}},
                {"type": "text", "data": {"text": f"你今天已经有群老婆{wife_nickname}({existing_wife})了，要好好对待她哦~"}}
            ]

            success, error = self.send_group_message(napcat_address, napcat_port, group_id, message)
            if not success:
                logger.error(f"发送消息失败: {error}")
                return False, f"发送消息失败: {error}", True

            return True, "已返回今日老婆", True

        # 获取群成员列表
        success, member_list = self.get_group_member_list(napcat_address, napcat_port, group_id)
        if not success:
            logger.error(f"获取群成员列表失败: {member_list}")
            return False, f"获取群成员列表失败: {member_list}", True

        # 过滤掉自己
        candidates = [m for m in member_list if str(m.get("user_id")) != user_id]

        if not candidates:
            logger.warning("群成员列表为空或只有自己")
            return False, "找不到可用的群成员", True

        # 随机选择老婆
        wife_data = random.choice(candidates)
        wife_id = str(wife_data.get("user_id"))
        wife_nickname = wife_data.get("card") or wife_data.get("nickname", "未知")

        # 保存到数据库
        db.save_wife(user_id, wife_id, group_id, today)

        # 获取用户昵称和群名称用于日志
        user_nickname = "未知"
        group_name = "未知"

        # 从成员列表中获取用户昵称
        for member in member_list:
            if str(member.get("user_id")) == user_id:
                user_nickname = member.get("card") or member.get("nickname", "未知")
                break

        # 获取群信息
        success, group_info = self.get_group_info(napcat_address, napcat_port, group_id)
        if success:
            group_name = group_info.get("group_name", "未知")

        # 输出日志
        logger.info(f"[今日老婆] {user_nickname}({user_id}) 在 {group_name}({group_id}) 抽到了 {wife_nickname}({wife_id})")

        # 发送消息
        message = [
            {"type": "at", "data": {"qq": user_id}},
            {"type": "image", "data": {"file": f"https://q1.qlogo.cn/g?b=qq&nk={wife_id}&s=640", "summary": "[图片]"}},
            {"type": "text", "data": {"text": f"你今天的群老婆是:{wife_nickname}({wife_id})"}}
        ]
        success, error = self.send_group_message(napcat_address, napcat_port, group_id, message)
        if not success:
            logger.error(f"发送消息失败: {error}")
            return False, f"发送消息失败: {error}", True

        return True, "执行成功", True


# Plugin 类
@register_plugin
class JrlpPlugin(BasePlugin):
    plugin_name = "jrlp-plugin"
    enable_plugin = True
    dependencies = []
    python_dependencies = []
    config_file_name = "config.toml"
    config_schema = {
        "plugin": {
            "name": ConfigField(type=str, default="jrlp-plugin", description="插件名称"),
            "version": ConfigField(type=str, default="1.0.1", description="插件版本"),
            "enabled": ConfigField(type=bool, default=True, description="是否启用插件"),
            "config_version": ConfigField(type=str, default="1.0.0", description="配置版本")
        },
        "napcat": {
            "address": ConfigField(type=str, default="napcat", description="napcat服务器连接地址"),
            "port": ConfigField(type=int, default=3000, description="napcat服务器端口")
        }
    }

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        return [
            (JrlpCommand.get_command_info(), JrlpCommand)
        ]
