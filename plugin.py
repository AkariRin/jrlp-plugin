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


# 今日老婆数据库管理类
class JrlpDatabase:
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

    def get_group_today_wives(self, group: str, date: str, page: int, page_size: int) -> Tuple[List[Tuple[str, str]], int]:
        """分页查询某群今日所有老婆记录

        Args:
            group: 群号
            date: 日期 (YYYY-MM-DD格式)
            page: 页码 (从1开始)
            page_size: 每页条数

        Returns:
            (记录列表[(qq, wife), ...], 总记录数)
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # 查询总数
            cursor.execute(
                'SELECT COUNT(*) FROM jrlp WHERE "group" = ? AND date = ?',
                (group, date)
            )
            total = cursor.fetchone()[0]

            # 分页查询
            offset = (page - 1) * page_size
            cursor.execute(
                'SELECT qq, wife FROM jrlp WHERE "group" = ? AND date = ? LIMIT ? OFFSET ?',
                (group, date, page_size, offset)
            )
            records = cursor.fetchall()
            return records, total

    def upsert_wife(self, qq: str, wife: str, group: str, date: str) -> bool:
        """更新或插入老婆记录

        Args:
            qq: 用户QQ号
            wife: 老婆的QQ号
            group: 群号
            date: 日期 (YYYY-MM-DD格式)

        Returns:
            bool: True表示更新了已有记录，False表示插入了新记录
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # 检查是否存在记录
            cursor.execute(
                'SELECT id FROM jrlp WHERE qq = ? AND "group" = ? AND date = ?',
                (qq, group, date)
            )
            existing = cursor.fetchone()

            if existing:
                # 更新已有记录
                cursor.execute(
                    'UPDATE jrlp SET wife = ? WHERE qq = ? AND "group" = ? AND date = ?',
                    (wife, qq, group, date)
                )
                conn.commit()
                return True
            else:
                # 插入新记录
                cursor.execute(
                    'INSERT INTO jrlp (qq, wife, "group", date) VALUES (?, ?, ?, ?)',
                    (qq, wife, group, date)
                )
                conn.commit()
                return False


# 分页大小
QUERYALL_PAGE_SIZE = 10

class JrlpAdminCommand(BaseCommand):
    """管理员指令 - 查询和管理今日老婆"""
    command_name = "jrlp-admin"
    command_description = "今日老婆管理指令"
    command_pattern = r'^/jrlp\s+.+$'

    @staticmethod
    def _make_request(url: str, payload: dict) -> Tuple[bool, Union[dict, str]]:
        """发送HTTP POST请求到napcat"""
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

    def get_member_info(self, address: str, port: int, group_id: str, user_id: str) -> Tuple[bool, Union[dict, str]]:
        """获取单个群成员信息"""
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
        """获取群信息"""
        url = f"http://{address}:{port}/get_group_info"
        payload = {"group_id": group_id, "no_cache": False}

        success, result = self._make_request(url, payload)
        if not success:
            return False, result

        data = result.get("data")
        if data is None:
            return False, "获取群信息失败：返回数据为空"
        return True, data

    async def _handle_query(self, group_id: str, target_qq: str, user_id: str) -> str:
        """处理 query 子命令"""
        napcat_address = self.get_config("napcat.address")
        napcat_port = self.get_config("napcat.port")
        today = datetime.datetime.now().strftime("%Y-%m-%d")

        # 初始化数据库
        current_dir = Path(__file__).parent.absolute()
        db_path = current_dir / "jrlp.db"
        db = JrlpDatabase(db_path)

        # 查询老婆
        wife_qq = db.get_today_wife(target_qq, group_id, today)
        if not wife_qq:
            return f"该成员({target_qq})今日尚未抽取老婆"

        # 获取群成员昵称
        success, member_info = self.get_member_info(napcat_address, napcat_port, group_id, target_qq)
        member_name = "未知"
        if success:
            member_name = member_info.get("card") or member_info.get("nickname", "未知")

        # 获取老婆昵称
        success, wife_info = self.get_member_info(napcat_address, napcat_port, group_id, wife_qq)
        wife_name = "未知"
        if success:
            wife_name = wife_info.get("card") or wife_info.get("nickname", "未知")

        return f"{member_name}({target_qq})的老婆是{wife_name}({wife_qq})"

    async def _handle_queryall(self, group_id: str, page: int, user_id: str) -> str:
        """处理 queryall 子命令"""
        napcat_address = self.get_config("napcat.address")
        napcat_port = self.get_config("napcat.port")
        today = datetime.datetime.now().strftime("%Y-%m-%d")

        # 初始化数据库
        current_dir = Path(__file__).parent.absolute()
        db_path = current_dir / "jrlp.db"
        db = JrlpDatabase(db_path)

        # 分页查询
        records, total = db.get_group_today_wives(group_id, today, page, QUERYALL_PAGE_SIZE)
        if total == 0:
            return "该群今日暂无抽取记录"

        # 计算总页数
        total_pages = (total + QUERYALL_PAGE_SIZE - 1) // QUERYALL_PAGE_SIZE
        if page > total_pages:
            return f"页码超出范围，共{total_pages}页"

        # 获取群信息
        success, group_info = self.get_group_info(napcat_address, napcat_port, group_id)
        group_name = "未知"
        if success:
            group_name = group_info.get("group_name", "未知")

        # 构建返回消息
        lines = [f"群{group_name}({group_id})的今日老婆有："]

        for qq, wife_qq in records:
            # 获取成员昵称
            success, member_info = self.get_member_info(napcat_address, napcat_port, group_id, qq)
            member_name = "未知"
            if success:
                member_name = member_info.get("card") or member_info.get("nickname", "未知")

            # 获取老婆昵称
            success, wife_info = self.get_member_info(napcat_address, napcat_port, group_id, wife_qq)
            wife_name = "未知"
            if success:
                wife_name = wife_info.get("card") or wife_info.get("nickname", "未知")

            lines.append(f"{member_name}({qq})的老婆是{wife_name}({wife_qq})")

        lines.append(f"第{page}页/共{total_pages}页，共{total}项")
        return "\n".join(lines)

    async def _handle_override(self, group_id: str, target_qq: str, wife_qq: str, user_id: str) -> str:
        """处理 override 子命令"""
        napcat_address = self.get_config("napcat.address")
        napcat_port = self.get_config("napcat.port")
        today = datetime.datetime.now().strftime("%Y-%m-%d")

        # 初始化数据库
        current_dir = Path(__file__).parent.absolute()
        db_path = current_dir / "jrlp.db"
        db = JrlpDatabase(db_path)

        # 获取管理员昵称
        success, admin_info = self.get_member_info(napcat_address, napcat_port, group_id, user_id)
        admin_name = "未知"
        if success:
            admin_name = admin_info.get("card") or admin_info.get("nickname", "未知")

        # 获取群信息
        success, group_info = self.get_group_info(napcat_address, napcat_port, group_id)
        group_name = "未知"
        if success:
            group_name = group_info.get("group_name", "未知")

        # 获取成员昵称
        success, member_info = self.get_member_info(napcat_address, napcat_port, group_id, target_qq)
        member_name = "未知"
        if success:
            member_name = member_info.get("card") or member_info.get("nickname", "未知")

        # 获取老婆昵称
        success, wife_info = self.get_member_info(napcat_address, napcat_port, group_id, wife_qq)
        wife_name = "未知"
        if success:
            wife_name = wife_info.get("card") or wife_info.get("nickname", "未知")

        # 更新或插入
        is_update = db.upsert_wife(target_qq, wife_qq, group_id, today)
        if is_update:
            logger.info(f"{admin_name}({user_id}) 更新了 {group_name}({group_id}) 成员 {member_name}({target_qq}) 的老婆为 {wife_name}({wife_qq})")
        else:
            logger.info(f"{admin_name}({user_id}) 为 {group_name}({group_id}) 成员 {member_name}({target_qq}) 新建老婆记录为 {wife_name}({wife_qq})")

        return f"已将{member_name}({target_qq})的老婆改为{wife_name}({wife_qq})"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        # 权限校验
        user_info = self.message.message_info.user_info if self.message.message_info else None
        if not user_info:
            await self.send_text("无法获取用户信息")
            return False, "无法获取用户信息", True

        user_id = str(user_info.user_id)
        admin_list = self.get_config("admin.userlist", [])

        if user_id not in admin_list:
            await self.send_text("权限不足")
            return False, "权限不足", True

        # 解析消息内容
        message_text = self.message.processed_plain_text.strip()
        parts = message_text.split()

        if len(parts) < 2:
            await self.send_text("参数错误")
            return False, "参数错误", True

        # 获取聊天流信息判断群聊/私聊
        chat_stream = self.message.chat_stream
        stream_type = chat_api.get_stream_type(chat_stream)

        command = parts[1].lower()  # query/queryall/override

        if stream_type == "group":
            # 群聊模式：/jrlp <command> [args...]
            group_id = str(chat_stream.group_info.group_id)
            args = parts[2:]  # 第三个参数开始是功能参数
        else:
            # 私聊模式：/jrlp <command> <group_id> [args...]
            if len(parts) < 3:
                await self.send_text("参数错误：私聊模式需要指定群号")
                return False, "参数错误", True
            group_id = parts[2]
            args = parts[3:]  # 第四个参数开始是功能参数

        # 根据命令分发处理
        try:
            if command == "query":
                if len(args) < 1:
                    await self.send_text("参数错误：query需要指定群成员QQ号")
                    return False, "参数错误", True
                target_qq = args[0]
                result = await self._handle_query(group_id, target_qq, user_id)

            elif command == "queryall":
                page = 1
                if len(args) >= 1:
                    try:
                        page = int(args[0])
                        if page < 1:
                            page = 1
                    except ValueError:
                        await self.send_text("参数错误：页码必须是数字")
                        return False, "参数错误", True
                result = await self._handle_queryall(group_id, page, user_id)

            elif command == "override":
                if len(args) < 2:
                    await self.send_text("参数错误：override需要指定群成员QQ号和老婆QQ号")
                    return False, "参数错误", True
                target_qq = args[0]
                wife_qq = args[1]
                result = await self._handle_override(group_id, target_qq, wife_qq, user_id)

            else:
                await self.send_text("参数错误：未知的子命令")
                return False, "参数错误", True

            # 发送结果
            await self.send_text(result)
            return True, "执行成功", True

        except Exception as e:
            logger.error(f"执行管理命令时发生错误: {str(e)}", exc_info=True)
            await self.send_text(f"执行失败: {str(e)}")
            return False, f"执行失败: {str(e)}", True


class JrlpCommand(BaseCommand):
    command_name = "jrlp"
    command_description = "今日老婆"
    command_pattern = r'^(今日老婆|抽老婆|jrlp)$'

    @staticmethod
    def _make_request(url: str, payload: dict) -> Tuple[bool, Union[dict, str]]:
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
            return False, None, False

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
                {"type": "image", "data": {"file": f"https://q1.qlogo.cn/g?b=qq&nk={existing_wife}&s=640", "summary": "[图片]"}},
                {"type": "text", "data": {"text": self.get_config("messages.already_rolled_text").format(wife_name=wife_nickname, wife_qq=existing_wife)}}
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
        logger.info(f"{user_nickname}({user_id}) 在 {group_name}({group_id}) 抽到了 {wife_nickname}({wife_id})")

        # 发送消息
        message = [
            {"type": "at", "data": {"qq": user_id}},
            {"type": "image", "data": {"file": f"https://q1.qlogo.cn/g?b=qq&nk={wife_id}&s=640", "summary": "[图片]"}},
            {"type": "text", "data": {"text": self.get_config("messages.new_roll_text").format(wife_name=wife_nickname, wife_qq=wife_id)}}
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
    config_section_descriptions = {
        "plugin": "插件基础配置",
        "napcat": "napcat服务器配置",
        "messages": "消息文本配置",
        "admin": "管理功能配置"
    }
    config_schema = {
        "plugin": {
            "enabled": ConfigField(type=bool, default=True, description="是否启用插件"),
            "config_version": ConfigField(type=str, default="1.1.0", description="配置版本")
        },
        "napcat": {
            "address": ConfigField(type=str, default="napcat", description="napcat服务器连接地址"),
            "port": ConfigField(type=int, default=3000, description="napcat服务器端口")
        },
        "messages": {
            "already_rolled_text": ConfigField(
                type=str,
                default="你今天已经有群老婆{wife_name}({wife_qq})了，要好好对待她哦~",
                description="已抽取老婆时的提示文本，支持占位符: {wife_name} 老婆昵称, {wife_qq} 老婆QQ号"
            ),
            "new_roll_text": ConfigField(
                type=str,
                default="你今天的群老婆是:{wife_name}({wife_qq})",
                description="新抽取老婆时的提示文本，支持占位符: {wife_name} 老婆昵称, {wife_qq} 老婆QQ号"
            )
        },
        "admin": {
            "enabled": ConfigField(type=bool, default=True, description="是否启用管理功能"),
            "userlist": ConfigField(type=list, default=[], description="有管理权限的用户列表"),
        }
    }

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        return [
            (JrlpCommand.get_command_info(), JrlpCommand),
            (JrlpAdminCommand.get_command_info(), JrlpAdminCommand)
        ]
