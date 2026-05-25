import uvicorn
import os
import asyncio
import sys
from milvusSearchMCPServer import close_search_manager, mcp
from dotenv import load_dotenv
import contextlib
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Mount, Route
from starlette.types import Receive, Scope, Send
from starlette.responses import JSONResponse
import logging
from collections.abc import AsyncIterator
import traceback
from pathlib import Path


if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())





# 创建日志记录器，命名为当前模块名
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# 从环境变量获取主机地址，HOST默认为"0.0.0.0"（监听所有网络接口）,PORT默认为8000
load_dotenv(Path(__file__).resolve().parent / ".env")
HOST = os.getenv("MCP_Server_HOST", "0.0.0.0")
PORT = int(os.getenv("MCP_Server_PORT", "8010"))


# 创建流式HTTP会话管理器，启用真正的无状态模式
session_manager = StreamableHTTPSessionManager(
    # 传入mcp应用程序实例
    app=mcp,
    # 事件存储设置为None
    event_store=None,
    # 使用流式HTTP默认JSON响应设置
    json_response=False,
    # 启用无状态模式
    stateless=True,
)


# 定义异步函数，用于处理流式HTTP请求
async def handle_streamable_http(
    # 请求的作用域
    scope: Scope,
    # 接收请求的函数
    receive: Receive,
    # 发送响应的函数
    send: Send
) -> None:
    # 调用会话管理器处理请求
    try:
        await session_manager.handle_request(scope, receive, send)
    except Exception as e:
        logger.error(f"Streamable HTTP请求处理失败: {e}")
        logger.error(traceback.format_exc())
        raise


async def health_check(request):
    return JSONResponse({
        "status": "ok",
        "mcp_url": "/mcp/",
        "host": HOST,
        "port": PORT,
    })


# 定义异步上下文管理器，用于管理应用程序生命周期
@contextlib.asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    """上下文管理器，用于管理会话管理器的生命周期"""
    # 启动会话管理器
    async with session_manager.run():
        # 记录应用程序启动日志
        logger.info("Application started with StreamableHTTP session manager!")
        try:
            # 进入生命周期，允许应用程序运行
            yield
        finally:
            # 记录应用程序关闭日志
            logger.info("Application shutting down...")
            close_search_manager()


# 创建Starlette ASGI应用程序
starlette_app = Starlette(
    # 启用调试模式
    debug=True,
    routes=[
        Route("/health", endpoint=health_check, methods=["GET"]),
        # 挂载/mcp路由，关联处理流式HTTP请求的函数
        Mount("/mcp", app=handle_streamable_http),
    ],
    # 设置生命周期管理器
    lifespan=lifespan,
)


# 定义运行服务器的函数
def run():
    # 使用uvicorn运行Starlette应用程序
    logger.info(f"Starting MCP Streamable HTTP server at http://{HOST}:{PORT}/mcp")
    uvicorn.run(starlette_app, host=HOST, port=PORT, log_level="info")



# 主程序入口
if __name__ == "__main__":
    # 运行服务器
    run()
