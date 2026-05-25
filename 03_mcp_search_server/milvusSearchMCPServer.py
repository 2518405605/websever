import logging
import atexit
import time
from mcp.server.lowlevel import Server
from mcp.types import Resource, Tool, TextContent
from mixTextSearch import MilvusSearchManager
from dotenv import load_dotenv
import os
from pathlib import Path





# 日志相关配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("rag_mcp_server")

# 从环境变量获取配置参数
load_dotenv(Path(__file__).resolve().parent / ".env")

# 实例化Server
mcp = Server("rag_mcp_server")
_search_manager = None


def get_search_manager() -> MilvusSearchManager:
    """复用进程级搜索管理器，避免每次工具调用都创建新连接。"""
    global _search_manager
    if _search_manager is None:
        logger.info("初始化全局Milvus搜索管理器")
        _search_manager = MilvusSearchManager(
            milvus_uri=os.getenv("MILVUS_URI", "http://localhost:19530"),
            db_name=os.getenv("MILVUS_DATABASE_NAME", "milvus_database"),
            chat_base_url=os.getenv("CHAT_BASE_URL", os.getenv("LLM_BASE_URL", "https://nangeai.top/v1")),
            chat_api_key=os.getenv("CHAT_API_KEY", os.getenv("LLM_API_KEY", "")),
            embedding_base_url=os.getenv("EMBEDDING_BASE_URL", os.getenv("LLM_BASE_URL", "https://nangeai.top/v1")),
            embedding_api_key=os.getenv("EMBEDDING_API_KEY", os.getenv("LLM_API_KEY", ""))
        )
    return _search_manager


def close_search_manager() -> None:
    global _search_manager
    if _search_manager is not None:
        _search_manager.close()
        _search_manager = None


atexit.register(close_search_manager)


def infer_search_type(query_text: str) -> str:
    """未显式指定搜索方式时，根据查询特征选择较快的默认搜索。"""
    sparse_keywords = [
        "招聘", "邮箱", "投递", "工作地点", "地点", "地址", "电话",
        "作者", "发布者", "标题", "链接", "时间", "日期", "编号",
    ]
    if any(keyword in query_text for keyword in sparse_keywords):
        return "sparse"
    return "hybrid"


# 声明 list_tools 函数为一个列出工具的接口
# 列出可用的 MySQL 工具
@mcp.list_tools()
async def list_tools() -> list[Tool]:
    logger.info("Listing tools...")
    # 函数返回一个列表，其中包含一个 Tool 对象
    # 每个 Tool 对象代表一个工具，其属性定义了工具的功能和输入要求
    return [
        Tool(
            # 工具的名称
            name="search_documents",
            # 工具的描述
            description=(
                "在本地Milvus RAG知识库中检索文章和文档内容。"
                "当用户询问知识库中的事实、观点、方法、列表、时间、作者、文章内容或需要引用资料时使用。"
                "支持dense语义搜索、sparse关键词/全文搜索、hybrid混合搜索。"
                "问题包含明确标题、作者、人名、机构名、日期、邮箱、地点、招聘等精确关键词时优先使用sparse；"
                "概念性、同义表达或语义理解问题使用dense或hybrid；不确定时使用hybrid。"
            ),
            # 定义了工具的输入模式（Schema），用于描述输入数据的格式和要求
            inputSchema={
                # 定义输入为一个 JSON 对象
                "type": "object",
                # 定义输入对象的属性
                "properties": {
                    # 指明此属性存储要执行搜索的内容
                    "query_text": {
                        "type": "string",
                        "description": "执行搜索的内容"
                    },
                    # 指明此属性存储要执行的过滤条件内容
                    "filter_query": {
                        "type": "string",
                        "default": "##None##",
                        "description": "过滤条件的自然语言描述内容,默认值为##None##。如:文章发布时间在2025年9月3号到5号之间的文章,作者是新智元的文档"
                    },
                    # 指明此属性存储要执行搜索的类型
                    "search_type": {
                        "type": "string",
                        "enum": ["dense", "sparse", "hybrid"],
                        "default": "hybrid",
                        "description": "可选dense、sparse、hybrid。dense适合语义相似搜索；sparse适合标题、作者、人名、机构名、日期、邮箱、地点、招聘等精确关键词；hybrid结合语义和关键词，不确定时使用hybrid。"
                    },
                    # 指明此属性存储要执行搜索返回结果的数量
                    "limit": {
                        "type": "number",
                        "default": 2,
                        "description": "结果返回的数量,默认值为2"
                        # "description": "Number of results,default 2"
                    }
                },
                # 只强制要求查询内容，其余参数使用默认值
                "required": ["query_text"]
            }
        )
    ]


# 声明 call_tool 函数为一个工具调用的接口
# 根据传入的工具名称和参数执行相应的搜索
# name: 工具的名称（字符串），指定要调用的工具
# arguments: 一个字典，包含工具所需的参数
@mcp.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    # 检查工具名称 name 是否是 search_documents
    # 如果 query_text 为空或未提供，抛出 ValueError 异常，提示用户必须提供查询语句
    if name != "search_documents":
        raise ValueError(f"Unknown tool: {name}")

    query_text = arguments.get("query_text")
    search_type = arguments.get("search_type")
    if not search_type:
        search_type = infer_search_type(query_text or "")
        logger.info("未指定search_type，根据查询自动选择: %s", search_type)
    limit = int(arguments.get("limit", 2))
    filter_query = arguments.get("filter_query", "##None##")
    if not query_text:
        raise ValueError("Query is required")
    if search_type not in {"dense", "sparse", "hybrid"}:
        raise ValueError("Search type must be one of dense, sparse, hybrid")
    if limit <= 0:
        raise ValueError("Limit must be greater than 0")

    try:
        call_start_time = time.perf_counter()
        search_manager = get_search_manager()

        # 执行混合搜索示例
        filter_result = search_manager.search_with_filter(
            collection_name=os.getenv("MILVUS_COLLECTION_NAME", "my_collection_demo_chunked"),
            query_text=query_text,
            filter_query=filter_query,
            search_type=search_type,
            limit=limit
        )
        logger.info("search_documents工具执行耗时: %.2fs", time.perf_counter() - call_start_time)
        if filter_result["success"]:
            print(f"✅ 过滤搜索成功")
            print(f"结果数量: {filter_result['total_results']}")

            if filter_result["results"] and len(filter_result["results"]) > 0:
                filtered_items = [
                    (
                        res.entity.get("title", ""),
                        res.entity.get("content_chunk", ""),
                        res.entity.get("link", ""),
                        res.entity.get("pubAuthor", ""),
                        res.entity.get("pubDate", ""),
                        res.distance
                    ) for res in filter_result["results"][0]
                ]

                # 将过滤搜索结果拼接成字符串
                filtered_result_string = ""
                for idx, item in enumerate(filtered_items, 1):
                    title, content_chunk, link, pubAuthor, pubDate, distance = item
                    record = (
                        f"过滤文章{idx}:\n"
                        f"文章标题: {title}\n"
                        f"文章内容片段: {content_chunk[:100]}...\n"
                        f"文章原始链接: {link}\n"
                        f"文章发布者: {pubAuthor}\n"
                        f"文章发布时间: {pubDate}\n"
                    )
                    filtered_result_string += record
                print(f"过滤搜索结果:\n{filtered_result_string}")
                # 返回一个包含查询结果的 TextContent 对象
                return [TextContent(type="text", text=filtered_result_string)]
            return [TextContent(type="text", text="\n未检索到相关结果")]
        else:
            print(f"❌ 过滤搜索失败: {filter_result['error']}")
            if "suggestions" in filter_result:
                print(f"   建议查询: {filter_result['suggestions']}")
            # 返回一个包含查询结果的 TextContent 对象
            return [TextContent(type="text", text="\n未检索到相关结果")]

    except Exception as e:
        logger.error(f"主程序执行异常: {e}")
        print("程序异常终止。")
        return [TextContent(type="text", text="\n主程序执行异常，程序异常终止")]

if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport="streamable_http")
