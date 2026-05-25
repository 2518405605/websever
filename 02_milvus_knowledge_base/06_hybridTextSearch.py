from pymilvus import MilvusClient, DataType, Function, FunctionType
from pymilvus import AnnSearchRequest
from openai import OpenAI
import json
import urllib.request
import urllib.error
from rag_config import (
    EMBEDDING_MODEL,
    HYBRID_CONTENT_WEIGHT,
    HYBRID_DENSE_WEIGHT,
    HYBRID_RECALL_LIMIT,
    HYBRID_TITLE_WEIGHT,
    MILVUS_COLLECTION_NAME,
    MILVUS_DATABASE_NAME,
    MILVUS_URI,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    RERANK_TOP_N,
    RERANKER_MODEL,
    SEARCH_LIMIT,
    USE_RERANKER,
)



# 混合搜索
# 1、大模型初始化
openai_client = OpenAI(
	base_url=OPENAI_BASE_URL,
	api_key=OPENAI_API_KEY
)

# 2、实例化Milvus客户端对象
client = MilvusClient(
    uri=MILVUS_URI,
    db_name=MILVUS_DATABASE_NAME
)

# 3、定义文本embedding处理函数
def emb_text(text):
    return (
        openai_client.embeddings.create(input=text, model=EMBEDDING_MODEL)
        .data[0]
        .embedding
    )

def rerank_results(question, hits):
    if not USE_RERANKER:
        return hits[:SEARCH_LIMIT]

    documents = [
        f"标题：{hit['title']}\n作者：{hit['pubAuthor']}\n正文片段：{hit['content_chunk']}"
        for hit in hits
    ]
    if not documents:
        return []

    url = f"{OPENAI_BASE_URL.rstrip('/')}/rerank"
    payload = {
        "model": RERANKER_MODEL,
        "query": question,
        "documents": documents,
        "top_n": min(RERANK_TOP_N, len(documents)),
        "return_documents": False
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        print(f"rerank失败，使用Milvus混合检索结果: {e}")
        return hits[:SEARCH_LIMIT]

    reranked = []
    for item in result.get("results", []):
        index = item.get("index")
        if index is None or index >= len(hits):
            continue
        hit = dict(hits[index])
        hit["rerank_score"] = item.get("relevance_score")
        reranked.append(hit)

    return reranked or hits[:SEARCH_LIMIT]

# 4、混合搜索
question = "AI智能体是否能预测未来？"
# 定义第一个搜索参数 基本 ANN 搜索请求
search_param_1 = {
    "data": [emb_text(question)],
    "anns_field": "content_dense",
    "param": {"nprobe": 10, "metric_type": "COSINE"},
    "limit": HYBRID_RECALL_LIMIT,
}
# 定义第二个搜索参数 全文搜索请求
search_param_2 = {
    "data": [question],
    "anns_field": "title_sparse",
    "param": {"drop_ratio_search": 0.2},
    "limit": HYBRID_RECALL_LIMIT
}
# 定义第三个搜索参数 正文全文搜索请求
search_param_3 = {
    "data": [question],
    "anns_field": "content_sparse",
    "param": {"drop_ratio_search": 0.2},
    "limit": HYBRID_RECALL_LIMIT
}
# 在混合搜索中，每个AnnSearchRequest 只支持一个查询数据
request_1 = AnnSearchRequest(**search_param_1)
request_2 = AnnSearchRequest(**search_param_2)
request_3 = AnnSearchRequest(**search_param_3)
# 互惠排名融合（RRF）排名器是 Milvus 混合搜索的一种重新排名策略，它根据多个向量搜索路径的排名位置而不是原始相似度得分来平衡搜索结果
# RRF Ranker 专门设计用于混合搜索场景，在这种场景中，您需要平衡来自多个向量搜索路径的结果，而无需分配明确的重要性权重
RRFRanker = Function(
    name="rrf",
    input_field_names=[],
    function_type=FunctionType.RERANK,
    params={
        "reranker": "rrf",
        "k": 100
    }
)
# 加权排名器通过为每个搜索路径分配不同的重要性权重，智能地组合来自多个搜索路径的结果并确定其优先级
# 使用加权排名策略时，需要输入权重值。输入权重值的数量应与混合搜索中基本 ANN 搜索请求的数量一致
# 输入的权重值范围应为 [0,1]，数值越接近 1 表示重要性越高
WeightRanker = Function(
    name="weight",
    input_field_names=[],
    function_type=FunctionType.RERANK,
    params={
        "reranker": "weighted",
        "weights": [HYBRID_DENSE_WEIGHT, HYBRID_TITLE_WEIGHT, HYBRID_CONTENT_WEIGHT],
        # 是否在加权前对原始分数进行归一化处理
        "norm_score": True
    }
)
# 执行混合搜索
res = client.hybrid_search(
    collection_name=MILVUS_COLLECTION_NAME,
    reqs=[request_1, request_2, request_3],
    # ranker=RRFRanker,
    ranker=WeightRanker,
    limit=HYBRID_RECALL_LIMIT,
    output_fields=["docId", "chunk_index", "title", "content_chunk", "link", "pubAuthor"]
)
hits = [
    {
        "docId": item["entity"].get("docId"),
        "chunk_index": item["entity"].get("chunk_index"),
        "title": item["entity"].get("title"),
        "content_chunk": item["entity"].get("content_chunk"),
        "link": item["entity"].get("link"),
        "pubAuthor": item["entity"].get("pubAuthor"),
        "score": item["distance"],
    }
    for item in res[0]
]
print(json.dumps(rerank_results(question, hits), ensure_ascii=False, indent=2))
