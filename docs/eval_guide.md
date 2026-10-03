# CiteBase Pro — Evaluation Benchmark Guide

CiteBase Pro includes an automated evaluation harness designed to systematically measure retrieval and generation quality across different RAG pipeline configurations.

---

## 📊 Core Quality Metrics

1. **Recall@k**:
   Proportion of queries where the ground-truth document is retrieved within the top $k$ candidates.
   
2. **Mean Reciprocal Rank (MRR)**:
   Measures how high the correct document appears in the ranked candidate list:
   $$\text{MRR} = \frac{1}{|Q|} \sum_{i=1}^{|Q|} \frac{1}{\text{rank}_i}$$

3. **Token F1**:
   Measures lexical token precision and recall between the predicted answer and expected ground truth.

4. **Faithfulness Score**:
   Evaluates whether claims made in the answer are supported by facts present in the retrieved context chunks.

---

## 🧪 Benchmark Configurations

Configurations live in `eval/configs/`:

| Config | Strategy | Vector Top-K | FTS Top-K | Rerank |
|---|---|---|---|---|
| `baseline.json` | Hybrid RRF | 20 | 20 | Disabled |
| `hybrid_rerank.json` | Hybrid RRF + Cross-Encoder | 25 | 25 | Enabled (ms-marco) |
| `vector_only.json` | Dense Vector | 20 | 0 | Disabled |

---

## 🏃 Running an Evaluation Benchmark

### Via API
```bash
curl -X POST "http://localhost:8000/api/v1/workspaces/{workspace_id}/eval/runs" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "name": "q3_retrieval_benchmark",
      "golden_dataset_path": "sample_dataset.jsonl",
      "hybrid_enabled": true,
      "reranker_enabled": true
    }
  }'
```

### Via Pytest
```bash
pytest tests/unit/test_eval_metrics.py -v
```
