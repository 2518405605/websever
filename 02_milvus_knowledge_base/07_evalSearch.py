from openai import OpenAI
from pymilvus import AnnSearchRequest, Function, FunctionType, MilvusClient
import ast
import csv
import json
from collections import defaultdict
from pathlib import Path
from rag_config import (
    BASE_DIR,
    DEDUP_BY_DOC,
    EMBEDDING_MODEL,
    HYBRID_CONTENT_WEIGHT,
    HYBRID_DENSE_WEIGHT,
    HYBRID_RECALL_LIMIT,
    HYBRID_TITLE_WEIGHT,
    MILVUS_COLLECTION_NAME,
    MILVUS_DATABASE_NAME,
    MILVUS_URI,
    NEIGHBOR_CHUNK_WINDOW,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    RECALL_EVAL_CSV,
)


EVAL_CSV_PATH = Path(RECALL_EVAL_CSV)
if not EVAL_CSV_PATH.is_absolute():
    EVAL_CSV_PATH = BASE_DIR / EVAL_CSV_PATH


openai_client = OpenAI(
    base_url=OPENAI_BASE_URL,
    api_key=OPENAI_API_KEY
)
client = MilvusClient(
    uri=MILVUS_URI,
    db_name=MILVUS_DATABASE_NAME
)


def emb_text(text):
    return (
        openai_client.embeddings.create(input=text, model=EMBEDDING_MODEL)
        .data[0]
        .embedding
    )


def parse_keywords(value):
    if not value:
        return []
    try:
        parsed = ast.literal_eval(value)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except (ValueError, SyntaxError):
        pass
    return [item.strip() for item in value.split(",") if item.strip()]


def load_eval_cases():
    if not EVAL_CSV_PATH.exists():
        raise FileNotFoundError(f"评估CSV不存在: {EVAL_CSV_PATH}")

    with EVAL_CSV_PATH.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        cases = []
        for row in reader:
            cases.append({
                "id": row["id"],
                "question": row["question"],
                "expected_answer": row.get("expected_answer", ""),
                "answer_keywords": parse_keywords(row.get("answer_keywords", "")),
                "source_doc_id": row["source_doc_id"],
                "source_title": row.get("source_title", ""),
                "source_author": row.get("source_author", ""),
                "source_pubDate": row.get("source_pubDate", ""),
                "question_type": row.get("question_type", "unknown"),
                "difficulty": row.get("difficulty", "unknown"),
                "top_k_suggested": int(row.get("top_k_suggested") or 3),
            })
    return cases


def dense_search(question, limit=HYBRID_RECALL_LIMIT):
    res = client.search(
        collection_name=MILVUS_COLLECTION_NAME,
        anns_field="content_dense",
        data=[emb_text(question)],
        limit=limit,
        search_params={"metric_type": "COSINE"},
        output_fields=["docId", "chunk_index", "title", "content_chunk", "link", "pubAuthor"]
    )
    return format_hits(res[0])


def full_text_search(question, limit=HYBRID_RECALL_LIMIT):
    title_res = client.search(
        collection_name=MILVUS_COLLECTION_NAME,
        anns_field="title_sparse",
        data=[question],
        limit=limit,
        search_params={"params": {"drop_ratio_search": 0.2}},
        output_fields=["docId", "chunk_index", "title", "content_chunk", "link", "pubAuthor"]
    )
    content_res = client.search(
        collection_name=MILVUS_COLLECTION_NAME,
        anns_field="content_sparse",
        data=[question],
        limit=limit,
        search_params={"params": {"drop_ratio_search": 0.2}},
        output_fields=["docId", "chunk_index", "title", "content_chunk", "link", "pubAuthor"]
    )
    return merge_sparse_hits(title_res[0], content_res[0], limit)


def hybrid_search(question, limit=HYBRID_RECALL_LIMIT):
    dense_request = AnnSearchRequest(
        data=[emb_text(question)],
        anns_field="content_dense",
        param={"nprobe": 10, "metric_type": "COSINE"},
        limit=limit
    )
    title_request = AnnSearchRequest(
        data=[question],
        anns_field="title_sparse",
        param={"drop_ratio_search": 0.2},
        limit=limit
    )
    content_request = AnnSearchRequest(
        data=[question],
        anns_field="content_sparse",
        param={"drop_ratio_search": 0.2},
        limit=limit
    )
    weight_ranker = Function(
        name="weight",
        input_field_names=[],
        function_type=FunctionType.RERANK,
        params={
            "reranker": "weighted",
            "weights": [HYBRID_DENSE_WEIGHT, HYBRID_TITLE_WEIGHT, HYBRID_CONTENT_WEIGHT],
            "norm_score": True
        }
    )
    res = client.hybrid_search(
        collection_name=MILVUS_COLLECTION_NAME,
        reqs=[dense_request, title_request, content_request],
        ranker=weight_ranker,
        limit=limit,
        output_fields=["docId", "chunk_index", "title", "content_chunk", "link", "pubAuthor"]
    )
    return format_hits(res[0])


def should_use_hybrid(question):
    has_ascii_letter = any(char.isascii() and char.isalpha() for char in question)
    has_digit = any(char.isdigit() for char in question)
    return has_ascii_letter or has_digit


def optimized_search(question, limit=HYBRID_RECALL_LIMIT):
    if should_use_hybrid(question):
        hits = hybrid_search(question, limit=limit)
        search_source = "weighted_hybrid"
    else:
        hits = dense_search(question, limit=limit)
        search_source = "dense"

    if DEDUP_BY_DOC:
        hits = dedupe_by_doc(hits)

    if NEIGHBOR_CHUNK_WINDOW > 0:
        hits = expand_neighbor_chunks(hits, window=NEIGHBOR_CHUNK_WINDOW)

    for rank, item in enumerate(hits[:limit], start=1):
        item["rank"] = rank
        item["search_source"] = search_source
    return hits[:limit]


def format_hits(items):
    return [
        {
            "rank": rank,
            "docId": item["entity"]["docId"],
            "chunk_index": item["entity"]["chunk_index"],
            "title": item["entity"]["title"],
            "content_chunk": item["entity"]["content_chunk"],
            "link": item["entity"]["link"],
            "pubAuthor": item["entity"]["pubAuthor"],
            "score": item["distance"]
        }
        for rank, item in enumerate(items, start=1)
    ]


def merge_sparse_hits(title_hits, content_hits, limit):
    merged = {}
    for source, hits in (("title_sparse", title_hits), ("content_sparse", content_hits)):
        for rank, item in enumerate(hits, start=1):
            key = (item["entity"]["docId"], item["entity"]["chunk_index"])
            score = 1.0 / rank
            if key not in merged:
                merged[key] = {
                    "docId": item["entity"]["docId"],
                    "chunk_index": item["entity"]["chunk_index"],
                    "title": item["entity"]["title"],
                    "content_chunk": item["entity"]["content_chunk"],
                    "link": item["entity"]["link"],
                    "pubAuthor": item["entity"]["pubAuthor"],
                    "score": 0.0,
                    "source": []
                }
            merged[key]["score"] += score
            merged[key]["source"].append(source)

    ranked = sorted(merged.values(), key=lambda item: item["score"], reverse=True)[:limit]
    for rank, item in enumerate(ranked, start=1):
        item["rank"] = rank
    return ranked


def escape_filter_value(value):
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def dedupe_by_doc(hits):
    seen = set()
    deduped = []
    for item in hits:
        doc_id = item["docId"]
        if doc_id in seen:
            continue
        seen.add(doc_id)
        deduped.append(dict(item))

    for rank, item in enumerate(deduped, start=1):
        item["rank"] = rank
    return deduped


def expand_neighbor_chunks(hits, window=1):
    expanded = []
    for item in hits:
        doc_id = escape_filter_value(item["docId"])
        center = int(item["chunk_index"])
        start = max(0, center - window)
        end = center + window

        try:
            neighbors = client.query(
                collection_name=MILVUS_COLLECTION_NAME,
                filter=f'docId == "{doc_id}" and chunk_index >= {start} and chunk_index <= {end}',
                output_fields=["docId", "chunk_index", "title", "content_chunk", "link", "pubAuthor"],
                limit=2 * window + 1
            )
        except Exception:
            expanded.append(item)
            continue

        if not neighbors:
            expanded.append(item)
            continue

        neighbors = sorted(neighbors, key=lambda row: row["chunk_index"])
        merged_item = dict(item)
        merged_item["matched_chunk_index"] = center
        merged_item["expanded_chunk_indexes"] = [row["chunk_index"] for row in neighbors]
        merged_item["content_chunk"] = "\n\n".join(row["content_chunk"] for row in neighbors)
        expanded.append(merged_item)

    for rank, item in enumerate(expanded, start=1):
        item["rank"] = rank
    return expanded


def keyword_coverage(keywords, results):
    if not keywords:
        return 0.0, []

    retrieved_text = "\n".join(
        f"{item['title']}\n{item['content_chunk']}"
        for item in results
    ).lower()
    matched = [
        keyword
        for keyword in keywords
        if keyword.lower() in retrieved_text
    ]
    return len(matched) / len(keywords), matched


def evaluate_case(case, results):
    doc_ids = [item["docId"] for item in results]
    source_doc_id = case["source_doc_id"]
    rank = next(
        (index + 1 for index, doc_id in enumerate(doc_ids) if doc_id == source_doc_id),
        None
    )
    suggested_k = case["top_k_suggested"]
    keyword_score, matched_keywords = keyword_coverage(
        case["answer_keywords"],
        results[:suggested_k]
    )

    return {
        "method": case.get("method", "unknown"),
        "id": case["id"],
        "question": case["question"],
        "question_type": case["question_type"],
        "difficulty": case["difficulty"],
        "source_doc_id": source_doc_id,
        "source_title": case["source_title"],
        "expected_answer": case["expected_answer"],
        "answer_keywords": case["answer_keywords"],
        "matched_keywords": matched_keywords,
        "keyword_coverage_at_suggested_k": keyword_score,
        "top_k_suggested": suggested_k,
        "hit_at_1": rank is not None and rank <= 1,
        "hit_at_3": rank is not None and rank <= 3,
        "hit_at_5": rank is not None and rank <= 5,
        "hit_at_suggested_k": rank is not None and rank <= suggested_k,
        "rank": rank,
        "mrr": 0.0 if rank is None else 1.0 / rank,
        "results": results,
    }


def print_case_report(report):
    print("\n" + "=" * 80)
    print(f"检索方法: {report['method']}")
    print(f"{report['id']} | {report['question_type']} | {report['difficulty']}")
    print(f"问题: {report['question']}")
    print(f"标准来源: {report['source_doc_id']} | {report['source_title']}")
    print(f"命中排名: {report['rank'] if report['rank'] is not None else '未命中'}")
    print(f"建议topK: {report['top_k_suggested']} | hit@K: {report['hit_at_suggested_k']}")
    print(
        "关键词覆盖: "
        f"{report['keyword_coverage_at_suggested_k']:.2%} "
        f"{report['matched_keywords']}"
    )

    print("\n召回切片:")
    for item in report["results"][:report["top_k_suggested"]]:
        print("-" * 80)
        print(
            f"rank={item['rank']} score={item['score']} "
            f"docId={item['docId']} chunk={item['chunk_index']}"
        )
        if "matched_chunk_index" in item:
            print(
                f"matched_chunk={item['matched_chunk_index']} "
                f"expanded_chunks={item.get('expanded_chunk_indexes', [])}"
            )
        if "search_source" in item:
            print(f"search_source={item['search_source']}")
        print(f"title={item['title']}")
        print(f"author={item['pubAuthor']}")
        print(f"content_chunk={item['content_chunk']}")


def summarize(reports):
    total = len(reports)
    if total == 0:
        return {}

    summary = {
        "total": total,
        "hit@1": sum(item["hit_at_1"] for item in reports) / total,
        "hit@3": sum(item["hit_at_3"] for item in reports) / total,
        "hit@5": sum(item["hit_at_5"] for item in reports) / total,
        "hit@suggested_k": sum(item["hit_at_suggested_k"] for item in reports) / total,
        "mrr": sum(item["mrr"] for item in reports) / total,
        "keyword_coverage@suggested_k": sum(
            item["keyword_coverage_at_suggested_k"] for item in reports
        ) / total,
    }

    for group_field in ("question_type", "difficulty"):
        grouped = defaultdict(list)
        for report in reports:
            grouped[report[group_field]].append(report)
        summary[f"by_{group_field}"] = {
            name: {
                "total": len(items),
                "hit@3": sum(item["hit_at_3"] for item in items) / len(items),
                "mrr": sum(item["mrr"] for item in items) / len(items),
            }
            for name, items in grouped.items()
        }

    return summary


def main():
    cases = load_eval_cases()
    recall_limit = max(
        HYBRID_RECALL_LIMIT,
        5,
        *(case["top_k_suggested"] for case in cases)
    )
    search_methods = {
        "04_dense_vector_search": dense_search,
        "05_full_text_search": full_text_search,
        "06_weighted_hybrid_search": hybrid_search,
        "07_optimized_search": optimized_search,
    }

    all_summaries = {}

    for method_name, search_fn in search_methods.items():
        print("\n" + "#" * 80)
        print(f"开始评估: {method_name}")
        print("#" * 80)

        reports = []
        for case in cases:
            results = search_fn(case["question"], limit=recall_limit)
            case_with_method = dict(case)
            case_with_method["method"] = method_name
            report = evaluate_case(case_with_method, results)
            reports.append(report)
            print_case_report(report)

        summary = summarize(reports)
        all_summaries[method_name] = summary
        print("\n" + "=" * 80)
        print(f"{method_name} 总体评估结果")
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    compact = {
        method_name: {
            "hit@1": summary["hit@1"],
            "hit@3": summary["hit@3"],
            "hit@5": summary["hit@5"],
            "hit@suggested_k": summary["hit@suggested_k"],
            "mrr": summary["mrr"],
            "keyword_coverage@suggested_k": summary["keyword_coverage@suggested_k"],
        }
        for method_name, summary in all_summaries.items()
    }
    print("\n" + "=" * 80)
    print("三种检索方法横向对比")
    print(json.dumps(compact, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
