import logging
import asyncio
import sys
import importlib
from concurrent_log_handler import ConcurrentRotatingFileHandler
from pydantic import BaseModel, Field
import time
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import uuid

lc_load = importlib.import_module("langchain_core.load.load")
from langchain_core.load.load import Reviver

_original_warn_deprecated = lc_load.warn_deprecated


def _ignore_allowed_objects_warning(*args, **kwargs):
    message = kwargs.get("message", "")
    if "allowed_objects" in message:
        return None
    return _original_warn_deprecated(*args, **kwargs)


lc_load.warn_deprecated = _ignore_allowed_objects_warning
import langgraph.checkpoint.serde.jsonplus as jsonplus_serde
lc_load.warn_deprecated = _original_warn_deprecated
from langgraph.graph import END, StateGraph, MessagesState
from langgraph.prebuilt import create_react_agent, tools_condition
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.store.postgres import AsyncPostgresStore
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages.utils import count_tokens_approximately, trim_messages
import uvicorn
from contextlib import asynccontextmanager
import redis.asyncio as redis
import json
from datetime import timedelta, datetime
from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row
from utils.config import Config
from utils.llms import get_llm
from utils.tools import get_tools


jsonplus_serde.LC_REVIVER = Reviver(allowed_objects="core")


if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())




# 设置日志基本配置，级别为DEBUG或INFO
logger = logging.getLogger(__name__)
# 设置日志器级别为DEBUG
logger.setLevel(logging.DEBUG)
# logger.setLevel(logging.INFO)
logger.handlers = []  # 清空默认处理器
# 使用ConcurrentRotatingFileHandler
handler = ConcurrentRotatingFileHandler(
    # 日志文件
    Config.LOG_FILE,
    # 日志文件最大允许大小为5MB，达到上限后触发轮转
    maxBytes = Config.MAX_BYTES,
    # 在轮转时，最多保留3个历史日志文件
    backupCount = Config.BACKUP_COUNT
)
# 设置处理器级别为DEBUG
handler.setLevel(logging.DEBUG)
handler.setFormatter(logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
))
logger.addHandler(handler)

MAX_STORED_MESSAGE_CHARS = 2000
MAX_STORED_MESSAGES = 12


def truncate_text(value: Any, max_chars: int = MAX_STORED_MESSAGE_CHARS) -> Any:
    if isinstance(value, str) and len(value) > max_chars:
        return value[:max_chars] + f"...[truncated {len(value) - max_chars} chars]"
    return value


def compact_message_for_storage(message: Any) -> Dict[str, Any]:
    """压缩 LangChain 消息，避免 Redis/API 响应保存完整工具结果和大段元数据。"""
    compact = {
        "type": message.__class__.__name__,
        "content": truncate_text(getattr(message, "content", "")),
        "id": getattr(message, "id", None),
    }

    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        compact["tool_calls"] = tool_calls

    tool_call_id = getattr(message, "tool_call_id", None)
    if tool_call_id:
        compact["tool_call_id"] = tool_call_id

    name = getattr(message, "name", None)
    if name:
        compact["name"] = name

    response_metadata = getattr(message, "response_metadata", None)
    if response_metadata:
        compact["response_metadata"] = {
            "token_usage": response_metadata.get("token_usage"),
            "model_name": response_metadata.get("model_name"),
            "finish_reason": response_metadata.get("finish_reason"),
        }

    return compact


def compact_agent_result_for_storage(result: Dict[str, Any]) -> Dict[str, Any]:
    """只保留前端/会话状态需要的信息，避免把完整 LangGraph state 存进 Redis。"""
    compact = {}
    if "__interrupt__" in result:
        compact["__interrupt__"] = result["__interrupt__"]

    messages = result.get("messages", [])
    if messages:
        compact["messages"] = [
            compact_message_for_storage(message)
            for message in messages[-MAX_STORED_MESSAGES:]
        ]
        compact["message_count"] = len(messages)

    return compact


# 定义数据模型 客户端发起的运行智能体的请求数据
class AgentRequest(BaseModel):
    # 用户唯一标识
    user_id: str
    # 会话唯一标识
    session_id: str
    # 用户的问题
    query: str
    # 系统提示词
    system_message: Optional[str] = "你会使用工具来帮助用户。如果工具使用被拒绝，请提示用户。"

# 定义数据模型 客户端发起的写入长期记忆的请求数据
class LongMemRequest(BaseModel):
    # 用户唯一标识
    user_id: str
    # 写入的内容
    memory_info: str

# 定义数据模型 运行智能体后返回的响应数据
class AgentResponse(BaseModel):
    # 会话唯一标识
    session_id: str
    # 三个状态：interrupted, completed, error
    status: str
    # 时间戳
    timestamp: float = Field(default_factory=lambda: time.time())
    # error时的提示消息
    message: Optional[str] = None
    # completed时的结果消息
    result: Optional[Dict[str, Any]] = None
    # interrupted时的中断消息
    interrupt_data: Optional[Dict[str, Any]] = None

# 定义数据模型 客户端发起的恢复智能体运行的中断反馈请求数据
class InterruptResponse(BaseModel):
    # 用户唯一标识
    user_id: str
    # 会话唯一标识
    session_id: str
    # 响应类型：accept(允许调用), edit(调整工具参数，此时args中携带修改后的调用参数), response(直接反馈信息，此时args中携带修改后的调用参数)，reject(不允许调用)
    response_type: str
    # 如果是edit, response类型，可能需要额外的参数
    args: Optional[Dict[str, Any]] = None

# 定义数据模型 系统内的会话状态响应数据
class SystemInfoResponse(BaseModel):
    # 当前系统内会话总数
    sessions_count: int
    # 系统内当前活跃的用户和会话
    active_users: Optional[Dict[str, Any]] = None

# 定义数据模型 所有会话ID响应数据
class SessionInfoResponse(BaseModel):
    # 当前用户的所有session_id
    session_ids: List[str]

# 定义数据模型 当前最近一次更新的会话ID响应
class ActiveSessionInfoResponse(BaseModel):
    # 最近一次更新的会话ID
    active_session_id: str

# 定义数据模型 会话状态详情响应数据
class SessionStatusResponse(BaseModel):
    # 用户唯一标识
    user_id: str
    # 会话唯一标识
    session_id: Optional[str] = None
    # 状态：not_found, idle, running, interrupted, completed, error
    status: str
    # error时的提示消息
    message: Optional[str] = None
    # 上次查询
    last_query: Optional[str] = None
    # 上次更新时间
    last_updated: Optional[float] = None
    # 上次响应
    last_response: Optional[AgentResponse] = None


# 实现redis相关方法 支持多用户多会话
class RedisSessionManager:
    # 初始化 RedisSessionManager 实例
    # 配置 Redis 连接参数和默认会话超时时间
    def __init__(self, redis_host: str, redis_port: int, redis_db: int, session_timeout: int):
        # 创建 Redis 客户端连接
        self.redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            decode_responses=True
        )
        # 设置默认会话过期时间（秒）
        self.session_timeout = session_timeout

    # 关闭 Redis 连接
    async def close(self):
        # 异步关闭 Redis 客户端连接
        await self.redis_client.aclose()

    # 创建指定用户的新会话
    # 存储结构：session:{user_id}:{session_id} = {
    #   "session_id": session_id,
    #   "status": "idle|running|interrupted|completed|error",
    #   "last_response": AgentResponse,
    #   "last_query": str,
    #   "last_updated": timestamp
    # }
    async def create_session(self, user_id: str, session_id: Optional[str] = None, status: str = "active",
                            last_query: Optional[str] = None, last_response: Optional['AgentResponse'] = None,
                            last_updated: Optional[float] = None, ttl: Optional[int] = None) -> str:
        # 如果未提供 session_id，生成新的 UUID
        if session_id is None:
            session_id = str(uuid.uuid4())
        # 如果未提供最后更新时间，设置为 0 秒
        if last_updated is None:
            last_updated = str(timedelta(seconds=0))
        # 使用提供的 TTL 或默认的 session_timeout
        effective_ttl = ttl if ttl is not None else self.session_timeout

        # 构造会话数据结构
        session_data = {
            "session_id": session_id,
            "status": status,
            "last_response": last_response.model_dump() if isinstance(last_response, BaseModel) else last_response,
            "last_query": last_query,
            "last_updated": last_updated
        }

        # 将会话数据存储到 Redis，使用 JSON 序列化，并设置过期时间
        await self.redis_client.set(
            f"session:{user_id}:{session_id}",
            json.dumps(session_data, default=lambda o: o.__dict__ if not hasattr(o, 'model_dump') else o.model_dump()),
            ex=effective_ttl
        )
        # 将 session_id 添加到用户的会话列表中
        await self.redis_client.sadd(f"user_sessions:{user_id}", session_id)
        # 返回新创建的 session_id
        return session_id

    # 更新指定用户的特定会话数据
    async def update_session(self, user_id: str, session_id: str, status: Optional[str] = None,
                            last_query: Optional[str] = None, last_response: Optional['AgentResponse'] = None,
                            last_updated: Optional[float] = None, ttl: Optional[int] = None) -> bool:
        # 检查会话是否存在
        if await self.redis_client.exists(f"session:{user_id}:{session_id}"):
            # 获取当前会话数据
            current_data = await self.get_session(user_id, session_id)
            if not current_data:
                return False
            # 更新提供的字段
            if status is not None:
                current_data["status"] = status
            if last_response is not None:
                if isinstance(last_response, BaseModel):
                    current_data["last_response"] = last_response.model_dump()
                else:
                    current_data["last_response"] = last_response
            if last_query is not None:
                current_data["last_query"] = last_query
            if last_updated is not None:
                current_data["last_updated"] = last_updated
            # 使用提供的 TTL 或默认的 session_timeout
            effective_ttl = ttl if ttl is not None else self.session_timeout
            # 将更新后的数据重新存储到 Redis，并设置新的过期时间
            await self.redis_client.set(
                f"session:{user_id}:{session_id}",
                json.dumps(current_data,
                           default=lambda o: o.__dict__ if not hasattr(o, 'model_dump') else o.model_dump()),
                ex=effective_ttl
            )
            # 更新成功返回 True
            return True
        # 会话不存在返回 False
        return False

    # 获取指定用户当前会话ID的状态数据
    async def get_session(self, user_id: str, session_id: str) -> Optional[dict]:
        # 从 Redis 获取会话数据
        session_data = await self.redis_client.get(f"session:{user_id}:{session_id}")
        # 如果会话不存在，返回 None
        if not session_data:
            return None
        # 解析 JSON 数据
        session = json.loads(session_data)
        # 处理 last_response 字段，尝试转换为 AgentResponse 对象
        if session and "last_response" in session:
            if session["last_response"] is not None:
                try:
                    session["last_response"] = AgentResponse(**session["last_response"])
                except Exception as e:
                    # 记录转换失败的错误日志
                    logger.error(f"转换 last_response 失败: {e}")
                    session["last_response"] = None
        # 返回会话数据
        return session

    # 获取指定用户下的当前激活的会话ID
    async def get_user_active_session_id(self, user_id: str) -> str | None:
        # 在查询前清理指定用户的无效会话
        await self.cleanup_user_sessions(user_id)

        # 获取用户的所有 session_id
        session_ids = await self.redis_client.smembers(f"user_sessions:{user_id}")

        # 初始化最新会话信息
        latest_session_id = None
        latest_timestamp = -1  # 使用负值确保任何有效时间戳都更大

        # 遍历每个 session_id，获取会话数据
        for session_id in session_ids:
            session = await self.get_session(user_id, session_id)
            if session:
                last_updated = session.get('last_updated')
                # 过滤掉 last_updated 为 "0:00:00" 的记录
                if isinstance(last_updated, str) and last_updated == "0:00:00":
                    continue
                # 确保 last_updated 是数字（时间戳）
                if isinstance(last_updated, (int, float)) and last_updated > latest_timestamp:
                    latest_timestamp = last_updated
                    latest_session_id = session_id

        # 返回最新会话ID，如果没有有效会话则返回 None
        return latest_session_id

    # 获取指定用户下的所有 session_id
    async def get_all_session_ids(self, user_id: str) -> List[str]:
        # 在查询前清理指定用户的无效会话，确保返回的 session_id 都是有效的
        await self.cleanup_user_sessions(user_id)
        # 从 Redis 获取用户的所有 session_id
        session_ids = await self.redis_client.smembers(f"user_sessions:{user_id}")
        # 将集合转换为列表并返回
        return list(session_ids)

    # 获取系统内所有用户下的所有 session_id
    async def get_all_users_session_ids(self) -> Dict[str, List[str]]:
        # 清理所有用户的无效会话
        await self.cleanup_all_sessions()
        # 初始化结果字典
        result = {}
        # 遍历所有 user_sessions:* 键
        async for key in self.redis_client.scan_iter("user_sessions:*"):
            # 提取用户 ID
            user_id = key.split(":", 1)[1]
            # 获取该用户的所有 session_id
            session_ids = await self.redis_client.smembers(f"user_sessions:{user_id}")
            # 如果集合非空，将用户 ID 和 session_id 列表存入结果字典
            if session_ids:
                result[user_id] = list(session_ids)
        # 返回所有用户及其 session_id
        return result

    # 获取指定用户ID的所有会话状态详情数据
    async def get_all_user_sessions(self, user_id: str) -> List[dict]:
        # 初始化会话列表
        sessions = []
        # 获取用户的所有 session_id
        session_ids = await self.redis_client.smembers(f"user_sessions:{user_id}")
        # 遍历每个 session_id，获取会话数据
        for session_id in session_ids:
            session = await self.get_session(user_id, session_id)
            if session:
                sessions.append(session)
        # 返回所有会话数据
        return sessions

    # 检查指定用户ID是否在 Redis 中
    async def user_id_exists(self, user_id: str) -> bool:
        # 在查询前清理指定用户的无效会话
        await self.cleanup_user_sessions(user_id)
        # 检查是否存在 user_sessions:{user_id} 键
        return (await self.redis_client.exists(f"user_sessions:{user_id}")) > 0

    # 检查指定用户ID的特定 session_id 是否存在
    async def session_id_exists(self, user_id: str, session_id: str) -> bool:
        # 在查询前清理指定用户的无效会话
        await self.cleanup_user_sessions(user_id)
        # 检查指定用户的特定会话是否存在
        return (await self.redis_client.exists(f"session:{user_id}:{session_id}")) > 0

    # 获取所有会话数量
    async def get_session_count(self) -> int:
        # 清理所有用户的无效会话
        await self.cleanup_all_sessions()
        # 初始化计数器
        count = 0
        # 遍历所有 session:* 键
        async for _ in self.redis_client.scan_iter("session:*"):
            count += 1
        # 返回会话总数
        return count

    # 清理指定用户的无效会话
    async def cleanup_user_sessions(self, user_id: str) -> None:
        # 获取用户会话集合中的所有 session_id
        session_ids = await self.redis_client.smembers(f"user_sessions:{user_id}")
        # 遍历每个 session_id，检查对应的会话键是否存在
        for session_id in session_ids:
            if not await self.redis_client.exists(f"session:{user_id}:{session_id}"):
                # 如果会话键已过期或不存在，从集合中移除 session_id
                await self.redis_client.srem(f"user_sessions:{user_id}", session_id)
                logger.info(f"Removed expired session_id {session_id} for user {user_id}")
        # 如果集合为空，删除集合
        if not await self.redis_client.scard(f"user_sessions:{user_id}"):
            await self.redis_client.delete(f"user_sessions:{user_id}")
            logger.info(f"Deleted empty user_sessions collection for user {user_id}")

    # 清理所有用户的无效会话
    async def cleanup_all_sessions(self) -> None:
        # 遍历所有 user_sessions:* 键
        async for key in self.redis_client.scan_iter("user_sessions:*"):
            # 提取用户 ID
            user_id = key.split(":", 1)[1]
            # 获取用户会话集合中的所有 session_id
            session_ids = await self.redis_client.smembers(f"user_sessions:{user_id}")
            # 遍历每个 session_id，检查对应的会话键是否存在
            for session_id in session_ids:
                if not await self.redis_client.exists(f"session:{user_id}:{session_id}"):
                    # 如果会话键已过期或不存在，从集合中移除 session_id
                    await self.redis_client.srem(f"user_sessions:{user_id}", session_id)
                    logger.info(f"Removed expired session_id {session_id} for user {user_id}")
            # 如果集合为空，删除集合
            if not await self.redis_client.scard(f"user_sessions:{user_id}"):
                await self.redis_client.delete(f"user_sessions:{user_id}")
                logger.info(f"Deleted empty user_sessions collection for user {user_id}")

    # 删除指定用户的特定会话
    async def delete_session(self, user_id: str, session_id: str) -> bool:
        # 从用户会话列表中移除 session_id
        await self.redis_client.srem(f"user_sessions:{user_id}", session_id)
        # 删除会话数据并返回是否成功
        return (await self.redis_client.delete(f"session:{user_id}:{session_id}")) > 0

# 解析state消息列表进行格式化展示
async def parse_messages(messages: List[Any]) -> None:
    """
    解析消息列表，打印 HumanMessage、AIMessage 和 ToolMessage 的详细信息

    Args:
        messages: 包含消息的列表，每个消息是一个对象
    """
    print("=== 消息解析结果 ===")
    for idx, msg in enumerate(messages, 1):
        print(f"\n消息 {idx}:")
        # 获取消息类型
        msg_type = msg.__class__.__name__
        print(f"类型: {msg_type}")
        # 提取消息内容
        content = getattr(msg, 'content', '')
        print(f"内容: {content if content else '<空>'}")
        # 处理附加信息
        additional_kwargs = getattr(msg, 'additional_kwargs', {})
        if additional_kwargs:
            print("附加信息:")
            for key, value in additional_kwargs.items():
                if key == 'tool_calls' and value:
                    print("  工具调用:")
                    for tool_call in value:
                        print(f"    - ID: {tool_call['id']}")
                        print(f"      函数: {tool_call['function']['name']}")
                        print(f"      参数: {tool_call['function']['arguments']}")
                else:
                    print(f"  {key}: {value}")
        # 处理 ToolMessage 特有字段
        if msg_type == 'ToolMessage':
            tool_name = getattr(msg, 'name', '')
            tool_call_id = getattr(msg, 'tool_call_id', '')
            print(f"工具名称: {tool_name}")
            print(f"工具调用 ID: {tool_call_id}")
        # 处理 AIMessage 的工具调用和元数据
        if msg_type == 'AIMessage':
            tool_calls = getattr(msg, 'tool_calls', [])
            if tool_calls:
                print("工具调用:")
                for tool_call in tool_calls:
                    print(f"  - 名称: {tool_call['name']}")
                    print(f"    参数: {tool_call['args']}")
                    print(f"    ID: {tool_call['id']}")
            # 提取元数据
            metadata = getattr(msg, 'response_metadata', {})
            if metadata:
                print("元数据:")
                token_usage = metadata.get('token_usage', {})
                print(f"  令牌使用: {token_usage}")
                print(f"  模型名称: {metadata.get('model_name', '未知')}")
                print(f"  完成原因: {metadata.get('finish_reason', '未知')}")
        # 打印消息 ID
        msg_id = getattr(msg, 'id', '未知')
        print(f"消息 ID: {msg_id}")
        print("-" * 50)

# 处理智能体返回结果 可能是中断，也可能是最终结果
def get_pending_tool_call(messages: List[Any]) -> Optional[Dict[str, Any]]:
    """查找还没有对应 ToolMessage 的工具调用。"""
    completed_tool_call_ids = {
        getattr(message, "tool_call_id", None)
        for message in messages
        if getattr(message, "tool_call_id", None)
    }

    for message in reversed(messages):
        tool_calls = getattr(message, "tool_calls", None)
        if not tool_calls:
            continue
        for tool_call in tool_calls:
            if tool_call.get("id") not in completed_tool_call_ids:
                return tool_call
    return None


def build_tool_review_interrupt_data(tool_call: Dict[str, Any]) -> Dict[str, Any]:
    tool_name = tool_call.get("name", "unknown_tool")
    tool_args = tool_call.get("args", {})
    return {
        "interrupt_type": "tool_review",
        "action_request": {
            "action": tool_name,
            "args": tool_args,
            "id": tool_call.get("id")
        },
        "description": (
            f"准备调用 {tool_name} 工具：\n"
            f"- 参数为: {tool_args}\n\n"
            "是否允许继续？\n"
            "输入 'yes' 接受工具调用\n"
            "输入 'no' 拒绝工具调用\n"
            "输入 'edit' 修改工具参数后调用工具\n"
            "输入 'response' 不调用工具，直接反馈信息"
        )
    }


def get_action_request_from_session(session: Dict[str, Any]) -> Dict[str, Any]:
    last_response = session.get("last_response")
    if isinstance(last_response, AgentResponse):
        interrupt_data = last_response.interrupt_data or {}
    elif isinstance(last_response, dict):
        interrupt_data = last_response.get("interrupt_data") or {}
    else:
        interrupt_data = {}

    action_request = interrupt_data.get("action_request")
    if not action_request:
        raise ValueError("当前中断会话缺少待审批的工具调用信息")
    if not action_request.get("id"):
        raise ValueError("当前中断会话缺少 tool_call_id，请重新开启新会话后再试")
    return action_request


async def invoke_tool_directly(tool_name: str, tool_args: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> str:
    tool = app.state.tools_by_name.get(tool_name)
    if tool is None:
        raise ValueError(f"未知工具: {tool_name}")
    result = await tool.ainvoke(tool_args, config=config)
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, default=str)


async def agent_node(state: MessagesState) -> Dict[str, Any]:
    response = await app.state.llm_with_tools.ainvoke(state["messages"])
    return {"messages": [response]}


async def build_review_tool_message(
        tool_call: Dict[str, Any],
        review_response: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
) -> ToolMessage:
    response_type = review_response.get("type")
    tool_name = tool_call.get("name", "unknown_tool")
    original_args = tool_call.get("args", {})
    tool_call_id = tool_call.get("id")

    if response_type == "accept":
        tool_result = await invoke_tool_directly(tool_name, original_args, config=config)
        content = f"工具返回结果:\n{tool_result}"
    elif response_type == "edit":
        edited_args = review_response.get("args", {}).get("args", original_args)
        tool_result = await invoke_tool_directly(tool_name, edited_args, config=config)
        content = (
            "用户审批时修改了工具参数。\n"
            f"原始参数: {json.dumps(original_args, ensure_ascii=False)}\n"
            f"修改后参数: {json.dumps(edited_args, ensure_ascii=False)}\n"
            f"工具返回结果:\n{tool_result}"
        )
    elif response_type == "reject":
        content = "用户拒绝了本次工具调用。请不要假装已经检索，直接说明工具调用被拒绝，并基于已有信息回答或请求用户补充。"
    elif response_type == "response":
        user_feedback = review_response.get("args")
        content = f"用户选择不调用工具，并给出了反馈: {user_feedback}"
    else:
        raise ValueError(f"不支持的审批响应类型: {response_type}")

    return ToolMessage(
        content=content,
        name=tool_name,
        tool_call_id=tool_call_id
    )


def create_human_review_agent(llm_chat, tools, checkpointer, store):
    app.state.llm_with_tools = llm_chat.bind_tools(tools)
    workflow = StateGraph(MessagesState)
    workflow.add_node("agent", agent_node)
    workflow.set_entry_point("agent")
    workflow.add_edge("agent", END)
    return workflow.compile(checkpointer=checkpointer, store=store)


async def process_agent_result(
        session_id: str,
        result: Dict[str, Any],
        user_id: Optional[str] = None
) -> AgentResponse:
    """
    处理智能体执行结果，统一处理中断和结果

    Args:
        session_id: 会话ID
        result: 智能体执行结果
        user_id: 用户ID，如果提供，将更新会话状态

    Returns:
        AgentResponse: 标准化的响应对象
    """
    response = None

    try:
        messages = result.get("messages", [])
        # 检查是否有中断
        if "__interrupt__" in result:
            raw_interrupt = result["__interrupt__"][0]
            interrupt_data = raw_interrupt.value
            if not isinstance(interrupt_data, dict):
                interrupt_data = {}

            latest_tool_call = get_pending_tool_call(messages)
            if latest_tool_call and "action_request" not in interrupt_data:
                interrupt_data.update(build_tool_review_interrupt_data(latest_tool_call))

            if "interrupt_type" not in interrupt_data:
                interrupt_data["interrupt_type"] = "tool_review"
            # 返回中断信息
            response = AgentResponse(
                session_id=session_id,
                status="interrupted",
                interrupt_data=interrupt_data
            )
            logger.info("当前触发工具调用中断: session_id=%s status=%s", session_id, response.status)
        elif pending_tool_call := get_pending_tool_call(messages):
            response = AgentResponse(
                session_id=session_id,
                status="interrupted",
                interrupt_data=build_tool_review_interrupt_data(pending_tool_call)
            )
            logger.info("检测到待审批工具调用: session_id=%s tool=%s", session_id, pending_tool_call.get("name"))
        # 如果没有中断，返回最终结果
        else:
            compact_result = compact_agent_result_for_storage(result)
            response = AgentResponse(
                session_id=session_id,
                status="completed",
                result=compact_result
            )
            logger.info(
                "最终智能体回复结果: session_id=%s status=%s message_count=%s",
                session_id,
                response.status,
                compact_result.get("message_count", 0),
            )

    except Exception as e:
        response = AgentResponse(
            session_id=session_id,
            status="error",
            message=f"处理智能体结果时出错: {str(e)}"
        )
        logger.error(f"处理智能体结果时出错:{response}")

    # 若会话存在，更新会话状态
    exists = await app.state.session_manager.session_id_exists(user_id, session_id)
    if exists:
        status = response.status
        last_query = None
        last_response = response
        last_updated = time.time()
        ttl = Config.TTL
        await app.state.session_manager.update_session(user_id, session_id, status, last_query, last_response, last_updated, ttl)

    return response

# 修剪聊天历史以满足 token 数量或消息数量的限制
def trimmed_messages_hook(state):
    trimmed_messages = trim_messages(
        messages=state["messages"],
        max_tokens=20,
        strategy="last",
        token_counter=len,
        start_on="human",
        # include_system=True,
        allow_partial=False
    )
    return {"llm_input_messages": trimmed_messages}

# 读取指定用户长期记忆中的内容
async def read_long_term_info(user_id :str):
    """
    读取指定用户长期记忆中的内容

    Args:
        user_id: 用户的唯一标识

    Returns:
        Dict[str, Any]: 包含记忆内容和状态的响应
    """
    try:
        # 指定命名空间
        namespace = ("memories", user_id)

        # 搜索记忆内容
        memories = await app.state.store.asearch(namespace, query="")

        # 处理查询结果
        if memories is None:
            raise HTTPException(
                status_code=500,
                detail="查询返回无效结果，可能是存储系统错误。"
            )

        # 提取并拼接记忆内容
        long_term_info = " ".join(
            [d.value["data"] for d in memories if isinstance(d.value, dict) and "data" in d.value]
        ) if memories else ""

        # 记录查询成功的日志
        logger.info(f"成功获取用户ID: {user_id} 的长期记忆，内容长度: {len(long_term_info)} 字符")

        # 返回结构化响应
        return {
            "success": True,
            "user_id": user_id,
            "long_term_info": long_term_info,
            "message": "长期记忆获取成功" if long_term_info else "未找到长期记忆内容"
        }

    except Exception as e:
        # 处理其他未预期的错误
        logger.error(f"获取用户ID: {user_id} 的长期记忆时发生意外错误: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"获取长期记忆失败: {str(e)}"
        )

# 写入指定用户长期记忆内容
async def write_long_term_info(user_id :str, memory_info :str):
    """
    指定用户写入长期记忆内容

    Args:
        user_id: 用户的唯一标识
        memory_info: 要保存的记忆内容

    Returns:
        Dict[str, Any]: 包含成功状态和存储记忆ID的结果
    """
    try:
        # 生成命名空间和唯一记忆ID
        namespace = ("memories", user_id)
        memory_id = str(uuid.uuid4())
        # 存储数据到指定命名空间
        result = await app.state.store.aput(
            namespace=namespace,
            key=memory_id,
            value={"data": memory_info}
        )
        # 记录存储成功的日志
        logger.info(f"成功为用户ID: {user_id} 存储记忆，记忆ID: {memory_id}")
        # 返回存储成功的响应
        return {
            "success": True,
            "memory_id": memory_id,
            "message": "记忆存储成功"
        }

    except Exception as e:
        # 处理其他未预期的错误
        logger.error(f"存储用户ID: {user_id} 的记忆时发生意外错误: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"存储记忆失败: {str(e)}"
        )


# 生命周期函数 app应用初始化函数
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        # 实例化异步Redis会话管理器 并存储为单实例
        app.state.session_manager = RedisSessionManager(
            Config.REDIS_HOST,
            Config.REDIS_PORT,
            Config.REDIS_DB,
            Config.SESSION_TIMEOUT
        )
        logger.info("Redis初始化成功")

        # 创建Chat模型
        llm_chat, llm_embedding = get_llm(Config.LLM_TYPE)
        app.state.llm_chat = llm_chat
        logger.info("Chat模型初始化成功")

        # 创建数据库连接池 动态连接池根据负载调整连接池大小
        async with AsyncConnectionPool(
                conninfo=Config.DB_URI,
                min_size=Config.MIN_SIZE,
                max_size=Config.MAX_SIZE,
                kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row}
        ) as pool:
            # 短期记忆 初始化checkpointer，并初始化表结构
            checkpoint_serde = JsonPlusSerializer()
            app.state.checkpointer = AsyncPostgresSaver(pool, serde=checkpoint_serde)
            await app.state.checkpointer.setup()
            logger.info("短期记忆Checkpointer初始化成功")

            # 长期记忆 初始化store，并初始化表结构
            app.state.store = AsyncPostgresStore(pool)
            await app.state.store.setup()
            logger.info("长期记忆store初始化成功")

            # 获取工具列表
            tools = await get_tools()
            app.state.tools_by_name = {tool.name: tool for tool in tools}

            # 创建ReAct Agent 并存储为单实例
            app.state.agent = create_human_review_agent(
                llm_chat=llm_chat,
                tools=tools,
                checkpointer=app.state.checkpointer,
                store=app.state.store
            )
            logger.info("Agent初始化成功")

            logger.info("服务完成初始化并启动服务")
            yield

    except Exception as e:
        logger.error(f"初始化失败: {str(e)}")
        raise RuntimeError(f"服务初始化失败: {str(e)}")

    # 清理资源
    finally:
        # 关闭Redis连接
        await app.state.session_manager.close()
        # 关闭PostgreSQL连接池
        await pool.close()
        logger.info("关闭服务并完成资源清理")

# 实例化app 并使用生命周期上下文管理器进行app初始化
app = FastAPI(
    title="Agent智能体后端API接口服务",
    description="基于LangGraph提供AI Agent服务",
    lifespan=lifespan
)

# API接口:运行智能体并返回大模型结果或中断数据
@app.post("/agent/invoke", response_model=AgentResponse)
async def invoke_agent(request: AgentRequest):
    logger.info(f"调用/agent/invoke接口，运行智能体并返回大模型结果或中断数据，接受到前端用户请求:{request}")
    # 获取用户请求中的user_id和session_id
    user_id = request.user_id
    session_id = request.session_id

    # 调用函数获取长期记忆
    result = await read_long_term_info(user_id)
    # 检查返回结果是否成功
    if result.get("success", False):
        long_term_info = result.get("long_term_info")
        # 若获取到的内容不为空 则将记忆内容拼接到系统提示词中
        if long_term_info:
            system_message = f"{request.system_message}我的附加信息有:{long_term_info}"
            logger.info(f"获取用户偏好配置数据，system_message的信息为:{system_message}")
        # 若获取到的内容为空，则直接使用系统提示词
        else:
            system_message = request.system_message
            logger.info(f"未获取到用户偏好配置数据，system_message的信息为:{system_message}")
    else:
        system_message = request.system_message
        logger.info(f"未获取到用户偏好配置数据，system_message的信息为:{system_message}")

    # 判断当前用户会话是否存在
    exists = await app.state.session_manager.session_id_exists(user_id, session_id)

    # 若用户会话不存在 则创建新会话
    if not exists:
        status = "idle"
        last_query = None
        last_response = None
        last_updated = time.time()
        ttl = Config.TTL
        # 创建会话并存储到redis中
        await app.state.session_manager.create_session(user_id, session_id, status, last_query, last_response, last_updated, ttl)

    # 新请求统一更新会话信息
    status = "running"
    last_query = request.query
    last_response = None
    last_updated = time.time()
    ttl = Config.TTL
    await app.state.session_manager.update_session(user_id, session_id, status, last_query, last_response, last_updated, ttl)

    # 构造智能体输入消息体
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": request.query}
    ]

    try:
        # 先调用智能体
        result = await app.state.agent.ainvoke({"messages": messages}, config={"configurable": {"thread_id": session_id}})
        # 将返回的messages进行格式化输出 方便查看调试
        await parse_messages(result['messages'])

        # 再处理结果并更新会话状态
        return await process_agent_result(session_id, result, user_id)

    except Exception as e:
        # 异常处理
        error_response = AgentResponse(
            session_id=session_id,
            status="error",
            message=f"处理请求时出错: {str(e)}"
        )
        logger.exception("处理请求时出错: %s", error_response)

        # 更新会话状态
        status = "error"
        last_query = None
        last_response = error_response
        last_updated = time.time()
        ttl = Config.TTL
        await app.state.session_manager.update_session(user_id, session_id, status, last_query, last_response, last_updated, ttl)

        return error_response

# API接口:恢复被中断的智能体运行并等待运行完成或再次中断
@app.post("/agent/resume", response_model=AgentResponse)
async def resume_agent(response: InterruptResponse):
    logger.info(f"调用/agent/resume接口，恢复被中断的智能体运行并等待运行完成或再次中断，接受到前端用户请求:{response}")
    # 获取用户请求中的user_id和session_id
    user_id = response.user_id
    session_id = response.session_id

    # 判断当前用户会话是否存在
    exists = await app.state.session_manager.session_id_exists(user_id, session_id)
    # 若用户不存在 则抛出异常
    if not exists:
        logger.error(f"status_code=404,用户会话 {user_id}:{session_id} 不存在")
        raise HTTPException(status_code=404, detail=f"用户会话 {user_id}:{session_id} 不存在")

    # 检查会话状态是否为中断 若不是中断则抛出异常
    session = await app.state.session_manager.get_session(user_id, session_id)
    status = session.get("status")
    if status != "interrupted":
        logger.error(f"status_code=400,会话当前状态为 {status}，无法恢复非中断状态的会话")
        raise HTTPException(status_code=400, detail=f"会话当前状态为 {status}，无法恢复非中断状态的会话")

    # 更新会话状态
    status = "running"
    last_query = None
    last_response = None
    last_updated = time.time()
    ttl = Config.TTL
    await app.state.session_manager.update_session(user_id, session_id, status, last_query, last_response, last_updated, ttl)

    try:
        command_data = {"type": response.response_type}
        if response.args is not None:
            command_data["args"] = response.args

        action_request = get_action_request_from_session(session)
        tool_call = {
            "name": action_request.get("action"),
            "args": action_request.get("args", {}),
            "id": action_request.get("id"),
            "type": "tool_call",
        }
        config = {"configurable": {"thread_id": session_id}}
        tool_message = await build_review_tool_message(tool_call, command_data, config=config)

        await app.state.agent.aupdate_state(config, {"messages": [tool_message]})
        result = await app.state.agent.ainvoke({}, config=config)
        # 将返回的messages进行格式化输出 方便查看调试
        await parse_messages(result['messages'])
        # 再处理结果并更新会话状态
        return await process_agent_result(session_id, result, user_id)

    except Exception as e:
        # 异常处理
        error_response = AgentResponse(
            session_id=session_id,
            status="error",
            message=f"恢复执行时出错: {str(e)}"
        )
        logger.exception("恢复执行时出错: %s", error_response)

        # 更新会话状态
        status = "error"
        last_query = None
        last_response = error_response
        last_updated = time.time()
        ttl = Config.TTL
        await app.state.session_manager.update_session(user_id, session_id, status, last_query, last_response, last_updated, ttl)

        return error_response

# API接口:获取指定用户当前会话的状态数据
@app.get("/agent/status/{user_id}/{session_id}", response_model=SessionStatusResponse)
async def get_agent_status(user_id: str, session_id: str):
    logger.info(f"调用/agent/status/接口，获取指定用户当前会话的状态数据，接受到前端用户请求:{user_id}:{session_id}")

    # 判断当前用户会话是否存在
    exists = await app.state.session_manager.session_id_exists(user_id, session_id)

    # 若会话不存在 构造SessionStatusResponse对象
    if not exists:
        logger.error(f"用户 {user_id}:{session_id} 的会话不存在")
        return SessionStatusResponse(
            user_id=user_id,
            session_id=session_id,
            status="not_found",
            message=f"用户 {user_id}:{session_id} 的会话不存在"
        )

    # 若会话存在 构造SessionStatusResponse对象
    session = await app.state.session_manager.get_session(user_id, session_id)
    response = SessionStatusResponse(
        user_id=user_id,
        session_id=session_id,
        status=session.get("status"),
        last_query=session.get("last_query"),
        last_updated=session.get("last_updated"),
        last_response=session.get("last_response")
    )
    logger.info(f"返回当前用户的会话状态:{response}")
    return response

# API接口:获取指定用户当前最近一次更新的会话ID
@app.get("/agent/active/sessionid/{user_id}", response_model=ActiveSessionInfoResponse)
async def get_agent_active_sessionid(user_id: str):
    logger.info(f"调用/agent/active/sessionid/接口，获取指定用户当前最近一次更新的会话ID，接受到前端用户请求:{user_id}")

    # 判断当前用户是否存在
    exists = await app.state.session_manager.user_id_exists(user_id)

    # 若用户不存在 构造ActiveSessionInfoResponse对象
    if not exists:
        logger.error(f"用户 {user_id} 的会话不存在")
        return ActiveSessionInfoResponse(
            active_session_id=""
        )

    # 若会话存在 构造ActiveSessionInfoResponse对象
    response = ActiveSessionInfoResponse(
        active_session_id=await app.state.session_manager.get_user_active_session_id(user_id)
    )

    logger.info(f"返回当前用户的激活的会话ID:{response}")
    return response

# API接口:获取指定用户的所有会话ID
@app.get("/agent/sessionids/{user_id}", response_model=SessionInfoResponse)
async def get_agent_sessionids(user_id: str):
    logger.info(f"调用/agent/sessionids/接口，获取指定用户的所有会话ID，接受到前端用户请求:{user_id}")

    # 判断当前用户是否存在
    exists = await app.state.session_manager.user_id_exists(user_id)

    # 若用户不存在 构造SessionInfoResponse对象
    if not exists:
        logger.error(f"用户 {user_id} 的会话不存在")
        return SessionInfoResponse(
            session_ids=[]
        )

    # 若会话存在 构造SessionInfoResponse对象
    response = SessionInfoResponse(
        session_ids=await app.state.session_manager.get_all_session_ids(user_id)
    )

    logger.info(f"返回当前用户的所有会话ID:{response}")
    return response

# API接口:获取当前系统内全部的会话状态信息
@app.get("/system/info", response_model=SystemInfoResponse)
async def get_system_info():
    logger.info(f"调用/system/info接口，获取当前系统内全部的会话状态信息")
    # 构造SystemInfoResponse对象
    response = SystemInfoResponse(
        # 当前系统内会话总数
        sessions_count=await app.state.session_manager.get_session_count(),
        # 系统内当前活跃的用户和会话
        active_users=await app.state.session_manager.get_all_users_session_ids()
    )
    logger.info(f"返回当前系统状态信息:{response}")
    return response

# API接口:删除指定用户当前会话
@app.delete("/agent/session/{user_id}/{session_id}")
async def delete_agent_session(user_id: str, session_id: str):
    logger.info(f"调用/agent/session/接口，删除指定用户当前会话，接受到前端用户请求:{user_id}:{session_id}")
    # 判断当前用户会话是否存在
    exists = await app.state.session_manager.session_id_exists(user_id, session_id)
    # 如果不存在 则抛出异常
    if not exists:
        logger.error(f"status_code=404,用户 {user_id}:{session_id} 的会话不存在")
        raise HTTPException(status_code=404, detail=f"用户会话 {user_id}:{session_id} 不存在")

    # 如果存在 则删除会话
    await app.state.session_manager.delete_session(user_id, session_id)
    response = {
        "status": "success",
        "message": f"用户 {user_id}:{session_id} 的会话已删除"
    }
    logger.info(f"用户会话已经删除:{response}")
    return response

# API接口:写入指定用户的长期记忆
@app.post("/agent/write/longterm")
async def write_long_term(request: LongMemRequest):
    logger.info(f"调用/agent/write/long_term接口，写入指定用户的长期记忆，接受到前端用户请求:{request}")

    user_id = request.user_id
    memory_info = request.memory_info

    # 判断当前用户会话是否存在
    exists = await app.state.session_manager.user_id_exists(user_id)
    # 如果不存在 则抛出异常
    if not exists:
        logger.error(f"status_code=404,用户 {user_id} 不存在")
        raise HTTPException(status_code=404, detail=f"用户会话 {user_id} 不存在")

    # 写入指定用户长期记忆内容
    result = await write_long_term_info(user_id, memory_info)

    # 检查返回结果是否成功
    if result.get("success", False):
        # 构造成功响应
        return {
            "status": "success",
            "memory_id": result.get("memory_id"),
            "message": result.get("message", "记忆存储成功")
        }
    else:
        # 处理非成功返回结果
        raise HTTPException(
            status_code=500,
            detail="记忆存储失败，返回结果未包含成功状态"
        )



# 启动服务器
if __name__ == "__main__":
    uvicorn.run(app, host=Config.HOST, port=Config.PORT)
