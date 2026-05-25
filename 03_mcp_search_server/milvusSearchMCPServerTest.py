from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession
import asyncio
import traceback
import httpx


def local_httpx_client_factory(headers=None, timeout=None, auth=None):
    return httpx.AsyncClient(
        headers=headers,
        timeout=timeout,
        auth=auth,
        trust_env=False
    )



# Author:@南哥AGI研习社 (B站 or YouTube 搜索“南哥AGI研习社”)


async def run():
    try:
        print("1. 正在连接 MCP Streamable HTTP 服务...")
        async with streamablehttp_client(
            url="http://127.0.0.1:8010/mcp/",
            httpx_client_factory=local_httpx_client_factory
        ) as (read_stream, write_stream, get_session_id_callback):
            async with ClientSession(read_stream, write_stream) as session:
                print("2. 正在 initialize...")
                capabilities = await session.initialize()
                print(f"initialize 成功: {capabilities.capabilities}/n/n")

                print("3. 正在 list_tools...")
                tools = await session.list_tools()
                print(f"list_tools 成功: {tools}/n/n")

                print("4. 正在 call_tool search_documents...")
                result = await session.call_tool("search_documents", {
                    "query_text": "全球AI百强榜发布,第一是谁？",
                    "filter_query": "##None##",
                    "search_type": "hybrid",
                    "limit": 2
                })
                print(f"call_tool 成功: {result}")
    except BaseException as exc:
        print("测试失败，异常如下：")
        exceptions = getattr(exc, "exceptions", None)
        if exceptions:
            for index, sub_exc in enumerate(exceptions, 1):
                print(f"--- 子异常 {index} ---")
                traceback.print_exception(type(sub_exc), sub_exc, sub_exc.__traceback__)
        else:
            traceback.print_exception(type(exc), exc, exc.__traceback__)


if __name__ == "__main__":
    # 使用 asyncio 启动异步的 run() 函数
    asyncio.run(run())
