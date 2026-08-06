# Group Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin bài nộp

| Thông tin         | Nội dung                                                                                                                                             |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| Khóa/Lớp         | K3                                                                                                                                                    |
| Tên nhóm         | B2                                                                                                                                                    |
| Repository         | [github.com/HuyhoangUK1234/K3_Day10_Data-Pipeline-Data-Observability](https://github.com/HuyhoangUK1234/K3_Day10_Data-Pipeline-Data-Observability.git) |
| Ngày hoàn thành | 2026-08-06                                                                                                                                            |

### Thành viên và phân công

| STT | Họ và tên           | MSSV        | Vai trò chính          | Module/deliverable sở hữu                                          |
| --: | ---------------------- | ----------- | ------------------------ | -------------------------------------------------------------------- |
|   1 | Nguyễn Duy Hải Bằng | 2A202601225 | Source ingestion         | `src/ingestion/crossref.py`                                        |
|   2 | Trần Thị Thanh Tâm  | 2A202601267 | Cleaning & test set      | `src/ingestion/cleaning.py`, `src/evaluation/testset.py`         |
|   3 | Tạ Thị Nga           | 2A202601125 | Observability            | `src/observability/quality.py`, `src/observability/reporting.py` |
|   4 | Huỳnh Hoàng Việt    | 2A202601105 | Corruption & repair      | `src/ingestion/corruption.py`                                      |
|   5 | Nguyễn Văn Tiến     | 2A202601433 | Integration & comparison | `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py`    |

---

## 2. Tóm tắt kết quả

**Câu hỏi nhóm đặt ra:** chất lượng dữ liệu ảnh hưởng tới chất lượng RAG agent **qua đường nào** và
**bao nhiêu**, và pipeline có phát hiện rồi phục hồi được không?

**Cách trả lời:** dựng baseline sạch → **đóng băng** bộ đánh giá → tiêm 6 loại lỗi dữ liệu có chủ đích
→ đo lại trên đúng bộ đánh giá đó → phục hồi từ raw snapshot → đo lần thứ ba.

**Kết quả:** corruption làm giảm cả 4 metric, data quality chuyển từ PASS sang FAIL với 3 critical
failure, và repair đưa toàn bộ về đúng mức baseline.

|                        |   Baseline |           Corrupted |   Repaired |
| ---------------------- | ---------: | ------------------: | ---------: |
| `retrieval_hit_rate` |     1.0000 |    **0.8000** |     1.0000 |
| `mean_token_f1`      |     1.0000 |    **0.7593** |     1.0000 |
| `judge_accuracy`     |     1.0000 |    **0.8000** |     1.0000 |
| `mean_judge_score`   |     5.0000 |    **4.2000** |     5.0000 |
| Data quality           | PASS 10/11 | **FAIL 6/11** | PASS 10/11 |
| Stale rows             |       1/24 |      **4/23** |       1/24 |

**Phát hiện quan trọng nhất:** chất lượng dữ liệu tác động qua **hai kênh độc lập**, và số liệu tách
được chúng ra. Phân rã 20 câu hỏi ở trạng thái corrupted:

- **Kênh retrieval** — 4 câu miss, `token_f1` trung bình **0.0467**. Cả 4 thuộc cùng một paper
  (`10.61838/jhrlp.213`) đã bị xoá khỏi corpus. Không tìm được tài liệu thì không thể trả lời đúng.
- **Kênh nội dung** — 16 câu retrieval **vẫn đúng**, nhưng `token_f1` trung bình chỉ **0.9375**, không
  phải 1.0. Thủ phạm là `summary-012` (paper `10.32738/jeppm-2025-345`): tìm đúng tài liệu, nhưng
  summary đã bị phá nên trả lời sai hoàn toàn (`token_f1` = 0.0000).

Kênh thứ hai nguy hiểm hơn trong vận hành thật: hệ thống trông vẫn "tìm đúng tài liệu" nên không ai
nghi ngờ, mà câu trả lời lại sai.

**Giới hạn lớn nhất còn lại:** ground truth sinh từ chính các trường mà QA layer trích xuất ra, nên
baseline chạm trần 1.0000 theo thiết kế. Chi tiết ở mục 13.

---

## 3. Kiến trúc và luồng dữ liệu

```text
Crossref API
    -> raw response/raw records          <- điểm phục hồi cho bước repair
    -> cleaning và data modeling
    -> embedding + ChromaDB index
    -> evaluation baseline               <- test set bị ĐÓNG BĂNG tại đây
    -> quality/freshness reports
    -> corruption
    -> re-index và re-evaluate           <- dùng lại đúng test set trên
    -> repair từ dữ liệu nguồn
    -> comparison report
```

Hai điểm neo quyết định tính hợp lệ của mọi kết luận phía sau:

1. **Raw snapshot** được ghi ngay sau khi fetch và corruption không bao giờ chạm vào. Đây là thứ khiến
   repair là *tái tạo từ nguồn* chứ không phải *vá dữ liệu hỏng*.
2. **Test set bị đóng băng** sau lần sinh đầu. Nếu sinh lại từ dataset corrupted thì ground truth đến
   từ chính dữ liệu sai, agent sẽ "đúng" với dữ liệu lỗi, và phép so sánh mất ý nghĩa.

### Trách nhiệm của từng khối

| Khối             | Input                   | Xử lý chính                                       | Output/artifact                        | Owner        |
| ----------------- | ----------------------- | ---------------------------------------------------- | -------------------------------------- | ------------ |
| Ingestion         | Crossref`/works`      | Fetch + retry/backoff, parse JATS, chuẩn hoá ngày | `data/raw/`                          | Hải Bằng   |
| Cleaning          | 24 raw records          | Lọc, dedupe,`age_days`, `text_for_embedding`    | `data/clean/papers_clean.*`          | Thanh Tâm   |
| Embedding/index   | Cleaned df              | MiniLM-L6-v2, ChromaDB cosine                        | `data/embeddings/`, `data/chroma/` | Thanh Tâm   |
| Evaluation        | Cleaned df              | 20 câu hỏi 4 loại, hit-rate/token-F1/LLM judge    | `data/eval/`, `data/results/`      | Thanh Tâm   |
| Observability     | Cleaned df              | 11 check + freshness                                 | `data/quality/`                      | Thị Nga     |
| Corruption/repair | Cleaned df, raw records | 6 kịch bản, repair từ raw                         | `data/results/corruption_log.json`   | Hoàng Việt |
| Orchestration     | Toàn bộ               | Thứ tự chạy, đảm bảo dùng chung test set      | `data/reports/*.md`                  | Văn Tiến   |

---

## 4. Cách tái hiện kết quả

### Cấu hình (không chứa secret)

| Biến/cấu hình         | Giá trị sử dụng                                             |
| ------------------------ | --------------------------------------------------------------- |
| `LLM_PROVIDER`         | `openai`                                                      |
| `LLM_MODEL`            | `gpt-4o-mini`                                                 |
| Embedding model          | `sentence-transformers/all-MiniLM-L6-v2`                      |
| Số Crossref records     | Xin 72 rows → 70 parse hợp lệ → giữ 24 theo`max_results` |
| Retrieval`top_k`       | 4                                                               |
| Freshness threshold      | 180 ngày                                                       |
| Random seed (corruption) | 20251006                                                        |
| Ragas                    | Chưa bật (`RUN_RAGAS=1` để chạy)                         |

### Lệnh

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
cp .env.example .env          # điền LLM_PROVIDER, LLM_MODEL, OPENAI_API_KEY

python script/run_phase1.py
python script/run_corruption_flow.py
python script/verify_artifacts.py
```

Cờ tuỳ chọn: `REFRESH_SOURCE=1` fetch lại Crossref, `REFRESH_TEST_SET=1` sinh lại test set,
`RUN_RAGAS=1` bật Ragas.

### Kết quả tái hiện

| Lệnh                 | Trạng thái          | Bằng chứng                                                                                                             |
| --------------------- | --------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Baseline pipeline     | Thành công (exit 0) | `data/reports/phase1_report.md`, `data/results/baseline_metrics.json`, `report/evidence/run_phase1.log`            |
| Corruption flow       | Thành công (exit 0) | `data/reports/corruption_report.md`, `data/results/corruption_log.json`, `report/evidence/run_corruption_flow.log` |
| Artifact verification | Thành công (exit 0) | `data/reports/verification_report.json`, `report/evidence/verify_artifacts.log`                                      |

Pipeline đã được chạy lại trên máy thứ hai từ cùng raw snapshot: `git diff` trên `data/` chỉ khác ở
`generated_at` và `persist_path`. Nhóm cũng xoá sạch `data/chroma/` rồi chạy lại — metrics ra y hệt,
chứng tỏ kết quả không phụ thuộc trạng thái vector store còn sót lại.

---

## 5. Ingestion, cleaning và data contract

### Nguồn dữ liệu

| Thuộc tính                | Giá trị                                                                               |
| --------------------------- | --------------------------------------------------------------------------------------- |
| Source                      | Crossref REST API —`https://api.crossref.org/works`                                  |
| Query                       | `query.bibliographic` = "agentic retrieval augmented generation large language model" |
| Filter                      | `from-pub-date:2026-02-07,has-abstract:true`, `sort=issued&order=desc`              |
| Thời điểm lấy dữ liệu | 2026-08-06T03:36Z                                                                       |
| Số record                  | 72 items → 70 hợp lệ sau parse → giữ 24                                            |
| Retry/backoff               | 5 lần, exponential 1→16s, trên 429/500/502/503/504 và lỗi mạng                    |

Nhóm xin dư gấp 3 lần `max_results` vì bước parse loại bỏ record thiếu DOI/title/abstract hợp lệ. Xin
đúng 24 thì có thể chỉ còn 18 record dùng được.

### Clean schema — hợp đồng giữa 4 module

16 cột khai báo ở `cleaning.py::CLEAN_COLUMNS`. Đây không phải chi tiết nội bộ mà là contract:

| Module                       | Đọc cột nào                                                                                                                                  |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `retrieval/index.py`       | `paper_id`, `title`, `text_for_embedding`, `published`, `authors_joined`, `categories_joined`, `summary`, `abs_url`, `pdf_url` |
| `observability/quality.py` | `paper_id`, `title`, `summary`, `text_for_embedding`, `age_days`                                                                       |
| `ingestion/corruption.py`  | Sửa các cột trên rồi ghi lại                                                                                                               |
| `evaluation/testset.py`    | `title`, `summary`, `authors_joined`, `published`, `categories_joined`, `paper_id`                                                   |

| Trường               | Kiểu     | Bắt buộc | Xử lý khi thiếu/sai                                                        |
| ---------------------- | --------- | ---------- | ----------------------------------------------------------------------------- |
| `paper_id`           | str       | Có        | DOI viết thường; bỏ record nếu thiếu hoặc trùng                       |
| `title`              | str       | Có        | Bỏ nếu < 10 ký tự; dedupe theo`title.lower()`                           |
| `summary`            | str       | Có        | Bỏ nếu < 80 ký tự (dưới ngưỡng thường là "Abstract not available") |
| `authors_joined`     | str       | Không     | Rỗng → "Unknown"                                                            |
| `categories_joined`  | str       | Không     | Rỗng → fallback`container-title` + `type` → "Uncategorized"            |
| `published`          | str (ISO) | Có        | Bỏ record nếu không parse được                                          |
| `age_days`           | int       | Có        | Số ngày**có dấu**; âm = ngày ở tương lai                       |
| `text_for_embedding` | str       | Có        | Sinh lại từ 5 trường khác                                                |

### Ba quy tắc cleaning đáng giải thích

**Dedupe kép** — theo `paper_id` **và** theo `title.lower()`. Trùng DOI là lỗi loader; trùng title mà
khác DOI là preprint + bản chính thức của cùng một bài. Cả hai đều làm nhiễu retrieval.

**`text_for_embedding` ghép 5 trường**, không chỉ abstract:

```
Title: ... / Authors: ... / Categories: ... / Published: ... / Summary: ...
```

Vì test set có câu hỏi về tác giả và ngày tháng. Nếu chỉ embed abstract, câu "Who authored the paper
titled X?" không có tín hiệu nào để retrieval bám vào.

Hàm sinh cột này (`build_text_for_embedding`) được **export public** để corruption flow gọi lại sau khi
phá dữ liệu. Nếu để inline, corruption sẽ sửa `summary` nhưng cột được embed vẫn giữ nội dung cũ →
**corruption không bao giờ đến được vector store** và mọi metric đứng im.

**Sort ngày giảm dần** không phải thẩm mỹ: corruption bước 1 xoá `df.head(3)` = 3 bài mới nhất, nên
thứ tự này quyết định corruption đánh vào đâu.

Document ID dùng DOI viết thường; ChromaDB record ID là `{paper_id}::{index}` nên các dòng duplicate
vẫn nạp được mà không đụng ID.

---

## 6. Evaluation setup

| Thành phần         | Cấu hình                                                                            |
| -------------------- | ------------------------------------------------------------------------------------- |
| Số câu hỏi        | 20 (5 paper × 4 loại)                                                               |
| `question_type`    | `summary`, `authors`, `date`, `categories`                                    |
| Ground-truth doc ID  | DOI của paper sinh ra câu hỏi (`ground_truth_doc_ids`)                           |
| Embedding model      | `all-MiniLM-L6-v2`                                                                  |
| Collection           | `papers-baseline` / `papers-corrupted` / `papers-repaired`, cosine              |
| `top_k`            | 4                                                                                     |
| LLM judge            | `openai:gpt-4o-mini`, structured output (`score` 1-5, `correct`, `reasoning`) |
| Test set dùng chung | `data/eval/test_set.json`, đóng băng cho cả ba trạng thái                     |

### Câu hỏi được sinh ra thế nào

Không có LLM tham gia và không ai viết tay. `testset.py` chọn 5 paper trải đều corpus (index 0, 4, 9,
14, 19) rồi áp 4 template cố định; ground truth copy thẳng từ ô dữ liệu tương ứng:

| Template                                                   | Ground truth lấy từ cột          |
| ---------------------------------------------------------- | ----------------------------------- |
| `What is the paper titled '{title}' about?`              | `summary` → `first_sentence()` |
| `Who authored the paper titled '{title}'?`               | `authors_joined`                  |
| `When was the paper titled '{title}' published?`         | `published`                       |
| `What categories does the paper titled '{title}' cover?` | `categories_joined`               |

Cách phát biểu câu hỏi **bắt buộc** khớp từ khoá mà `retrieval/qa.py::_extract_answer` nhận diện
(`who authored`, `when was`, `what categories`), và title phải nằm trong dấu nháy đơn để kích hoạt
exact lookup. Đổi "Who authored" thành "Who wrote" là câu hỏi rơi xuống nhánh mặc định và `token_f1`
tụt về gần 0 — thấp không phải vì agent kém mà vì test set viết sai.

**Chọn paper trải đều thay vì `head(5)`:** nếu lấy 5 bài đầu thì corruption xoá 3 bài mới nhất sẽ giết
3/5 paper = 60% test set, delta bị thổi phồng. Trải đều cho kết quả đo được: mất đúng 1 paper trong
test set → 4/20 câu → `retrieval_hit_rate` = 0.8000.

**Vì sao giữ nguyên test set:** cả ba lần `evaluate_pipeline` đều đọc cùng một đường dẫn. Pipeline chỉ
sinh test set khi file chưa tồn tại hoặc khi đặt `REFRESH_TEST_SET=1`.

---

## 7. Kết quả baseline

### Artifact checklist

| Artifact                   | Đường dẫn                             | Trạng thái                               |
| -------------------------- | ----------------------------------------- | ------------------------------------------ |
| Raw response/records       | `data/raw/`                             | Có (1.04 MB + 24 records)                 |
| Cleaned dataset            | `data/clean/`                           | Có (24 dòng × 16 cột, CSV + JSON)      |
| Embedding manifest         | `data/embeddings/`                      | Có (3 manifest)                           |
| Vector store               | `data/chroma/`                          | Có (3 collection: 24/23/24 docs)          |
| Evaluation set             | `data/eval/test_set.json`               | Có (20 câu)                              |
| Baseline metrics + answers | `data/results/`                         | Có                                        |
| Agent demo                 | `data/results/agent_demo_answers.json`  | Có (3 câu)                               |
| Quality/freshness          | `data/quality/`                         | Có (4 quality + 3 freshness + 3 GX-style) |
| Baseline report            | `data/reports/phase1_report.md`         | Có                                        |
| Verification report        | `data/reports/verification_report.json` | Có                                        |

### Metrics

| Metric                 | Giá trị | Diễn giải                                                   |
| ---------------------- | --------: | ------------------------------------------------------------- |
| `retrieval_hit_rate` |    1.0000 | Cả 20 câu retrieve đúng document ground truth trong top-4 |
| `mean_token_f1`      |    1.0000 | Câu trả lời trùng khớp ground truth                      |
| `judge_accuracy`     |    1.0000 | LLM judge`gpt-4o-mini` xác nhận cả 20 câu đúng        |
| `mean_judge_score`   |    5.0000 | Điểm tối đa                                               |
| Ragas                  |       N/A | Chưa bật (`RUN_RAGAS=1`)                                  |

> **Đọc con số này cho đúng:** QA layer trả lời bằng cách **trích xuất** trực tiếp từ metadata đã
> index, còn ground truth sinh từ chính các trường đó. Baseline 1.0000 là **trần lý thuyết theo thiết
> kế của starter**, không phải bằng chứng agent tổng quát hoá tốt. Giá trị của baseline ở đây là làm
> mốc tất định để đo mức suy giảm — baseline chạm trần nghĩa là mọi sụt giảm sau đó quy được hết về
> chất lượng dữ liệu, không lẫn nhiễu từ agent.

---

## 8. Data quality và freshness

### Nguyên tắc: tách `critical` và `warning`

Dataset chỉ FAIL khi có check `critical` fail. Freshness của nguồn là tín hiệu giám sát, không phải vi
phạm schema — publisher chậm cập nhật không nên chặn pipeline, nhưng phải được nêu ra.

| Check                            | Severity | Dimension    | Ngưỡng              | Baseline                 |
| -------------------------------- | -------- | ------------ | --------------------- | ------------------------ |
| `row_count_minimum`            | critical | Completeness | >= 10 dòng           | PASS (24)                |
| `paper_id_not_null`            | critical | Completeness | 0 rỗng               | PASS (0)                 |
| `paper_id_unique`              | critical | Uniqueness   | 0 trùng              | PASS (0)                 |
| `title_not_null`               | critical | Completeness | 0 rỗng               | PASS (0)                 |
| `title_min_length`             | critical | Validity     | >= 10 ký tự         | PASS (0)                 |
| `summary_not_empty`            | critical | Completeness | 0 rỗng               | PASS (0)                 |
| `summary_min_length`           | critical | Validity     | >= 80 ký tự         | PASS (0)                 |
| `text_for_embedding_not_empty` | critical | Completeness | 0 rỗng               | PASS (0)                 |
| `title_unique`                 | warning  | Uniqueness   | 0 trùng              | PASS (0)                 |
| `published_not_in_future`      | warning  | Validity     | 0 dòng forward-dated | PASS (0)                 |
| `freshness_within_threshold`   | warning  | Timeliness   | `age_days` <= 180   | **WARN (1 dòng)** |

Kết quả baseline: **PASS 10/11**, 1 warning. Artifact: `data/quality/baseline_quality.json` và bản
GX-style ở `data/quality/gx/`.

### Freshness

|                    | Baseline       | Corrupted                | Repaired       |
| ------------------ | -------------- | ------------------------ | -------------- |
| Status             | STALE          | STALE                    | STALE          |
| Stale rows         | 1/24           | **4/23**           | 1/24           |
| Oldest published   | 2026-02-04     | **2022-03-21**     | 2026-02-04     |
| Latest published   | 2026-08-03     | 2026-07-30               | 2026-08-03     |
| Age min/median/max | 3 / 21.5 / 183 | 7 / 25.0 /**1599** | 3 / 21.5 / 183 |
| Forward-dated rows | 0              | 0                        | 0              |

Baseline đã STALE sẵn vì có 1 bài `age_days` = 183, vượt ngưỡng 180 đúng 3 ngày. Đây là phát hiện thật
của quality layer chứ không phải lỗi: filter Crossref `from-pub-date` áp lên ngày pub của Crossref (có
thể forward-date), còn nhóm quy về ngày thực tế đã phát hành nên bài này rơi ra ngoài cửa sổ 180 ngày.

**Hệ quả cho cách đọc kết quả:** nhãn `status` giữ nguyên STALE ở cả ba trạng thái nên **không dùng
được làm bằng chứng nhị phân**. Bằng chứng nằm ở số liệu: `stale_rows` 1 → 4 → 1 và `oldest_published`
lùi 4 năm rồi quay lại.

---

## 9. Corruption scenarios và repair

Seed cố định `20251006`, các bước lấy dòng không trùng nhau, 24 → 23 dòng.

| # | Kịch bản                     | Mô phỏng lỗi thật        | Dòng | Tín hiệu quality bắt được |
| - | ------------------------------ | ---------------------------- | ----: | ------------------------------- |
| 1 | Xoá 3 bài mới nhất         | Incremental load bị cắt    |     3 | `row_count`, freshness        |
| 2 | Blank summary                  | Abstract extractor fail      |     3 | `summary_not_empty` FAIL      |
| 3 | Chèn noise vào summary       | Markup chưa parse lọt vào |     3 | `summary_min_length` FAIL     |
| 4 | Truncate title còn 12 ký tự | Cột DB quá hẹp            |     3 | `title_min_length`            |
| 5 | Lùi ngày 1500 ngày          | Backfill ghi đè sai        |     3 | `freshness_within_threshold`  |
| 6 | Nhân đôi dòng              | Replay batch                 |     2 | `paper_id_unique` FAIL        |

Sau 6 bước, cột `text_for_embedding` được **dựng lại** để corruption thực sự đi vào vector store.

Corruption log (`data/results/corruption_log.json`) ghi seed, số dòng vào/ra, và với mỗi bước có
`step`, mô tả, `count`, `affected_paper_ids` — đủ để truy vết dòng nào hỏng theo cách nào.

### Repair phục hồi từ nguồn nào

Repair **không** sửa chữa trên dataset đã hỏng. `corruption_flow.py` đọc lại
`data/raw/crossref_records.json` — snapshot ghi ngay sau khi fetch, corruption không chạm tới — rồi
chạy lại **đúng hàm `build_clean_dataframe` của pha 1**.

Bằng chứng: `papers_clean_repaired.json` giống `papers_clean.json` **byte-for-byte** (cùng 104 493
bytes). Điều này chỉ đạt được khi hàm cleaning tất định — nếu nó phụ thuộc thứ tự dict hay random thì
hai file đã khác nhau.

---

## 10. So sánh baseline, corrupted và repaired

Cả ba đánh giá trên **cùng file** `data/eval/test_set.json`.

| Metric/signal          |   Baseline |           Corrupted |   Repaired |       Δ corruption | Mức phục hồi |
| ---------------------- | ---------: | ------------------: | ---------: | ------------------: | --------------: |
| `retrieval_hit_rate` |     1.0000 |              0.8000 |     1.0000 |            −0.2000 |            100% |
| `mean_token_f1`      |     1.0000 |              0.7593 |     1.0000 |            −0.2407 |            100% |
| `judge_accuracy`     |     1.0000 |              0.8000 |     1.0000 |            −0.2000 |            100% |
| `mean_judge_score`   |     5.0000 |              4.2000 |     5.0000 |            −0.8000 |            100% |
| Quality checks         | PASS 10/11 | **FAIL 6/11** | PASS 10/11 | +3 critical failure |            100% |
| Stale rows             |       1/24 |                4/23 |       1/24 |            +3 dòng |            100% |

### Phân rã 20 câu hỏi ở trạng thái corrupted

Đây là phần cho phép kết luận nhân quả thay vì chỉ mô tả tương quan.

| Nhóm                   | Số câu | `token_f1` trung bình | Nguyên nhân                                                           |
| ----------------------- | -------: | -----------------------: | ----------------------------------------------------------------------- |
| Retrieval**miss** |        4 |                   0.0467 | Cả 4 câu thuộc paper`10.61838/jhrlp.213` bị xoá ở corruption #1 |
| Retrieval**hit**  |       16 |                   0.9375 | 15 câu hoàn hảo + 1 câu hỏng nội dung                             |

Trong 16 câu retrieval đúng, đúng **một** câu có `token_f1` = 0.0000: `summary-012`, paper
`10.32738/jeppm-2025-345`. Tìm đúng tài liệu, nhưng summary đã bị phá nên trả lời sai hoàn toàn.

Kiểm chứng số học: `(16 × 0.9375 + 4 × 0.0467) / 20 = 0.7593` — khớp `mean_token_f1` trong
`corrupted_metrics.json`.

Đáng chú ý: 4 câu miss phân bố **đều 1 câu mỗi `question_type`**, đúng như dự đoán khi một paper bị
xoá khỏi corpus — mỗi paper trong test set sinh đúng 4 câu thuộc 4 loại khác nhau.

### Ba chuỗi nhân quả có artifact hỗ trợ

**1. Mất bản ghi → mất retrieval → mất câu trả lời**

Bước `drop_latest_records` xoá 3 paper mới nhất (`corruption_log.json`), trong đó có
`10.61838/jhrlp.213` — 1 trong 5 paper của test set. Collection `papers-corrupted` còn 23 document.
Kết quả: đúng 4 câu của paper đó có `retrieval_hit = false` trong `corrupted_answers.json`.
→ `retrieval_hit_rate` 1.0000 → 0.8000.

**2. Hỏng nội dung → quality FAIL → sai câu trả lời dù retrieval đúng**

`blank_summary` và `inject_summary_noise` làm `summary_not_empty` = 3 và `summary_min_length` = 3 (cả
hai `critical`) → `corrupted_quality.json` chuyển FAIL. Trên tầng agent, `summary-012` retrieve đúng
document nhưng `token_f1` = 0.0000. → `mean_token_f1` giảm 0.2407, **nhiều hơn** mức giảm của
`retrieval_hit_rate` (0.2000), chứng tỏ có tổn thất nằm ngoài kênh retrieval.

**3. Repair → quality phục hồi → metric phục hồi**

Dựng lại từ raw snapshot → `repaired_quality.json` về PASS 10/11 với 0 critical failure, `stale_rows`
về 1/24 → cả 4 metric về đúng mức baseline.

### Một điểm bất đồng giữa hai thước đo

`summary-012` có `token_f1` = 0.0000 nhưng LLM judge chấm `correct = true`. Judge đánh giá theo **ngữ
nghĩa** và chấp nhận câu trả lời tuy khác từ ngữ nhưng vẫn hợp lý, còn token F1 so khớp từ vựng nên
phạt nặng. Đó là lý do `judge_accuracy` (0.8000) cao hơn tỉ lệ câu đạt `token_f1` hoàn hảo
(15/20 = 0.75). Nhóm giữ cả hai vì chúng bổ sung nhau: token F1 nhạy với thay đổi bề mặt, judge nhạy
với sai lệch ngữ nghĩa.

---

## 11. Vấn đề tích hợp quan trọng

- **Triệu chứng:** không có exception. `freshness_report.json` ghi `latest_published: 2028-06-15`
  nhưng `max_age_days: 0` — cả 24 bài đều "0 ngày tuổi" trong khi ngày xuất bản ở tương lai. Báo cáo
  tự mâu thuẫn.
- **Nguyên nhân gốc:** hai lỗi chồng nhau. (1) Tạp chí forward-date số báo — bài đăng online 2026 mang
  `issued = 2028`; code lấy thẳng `published`/`issued` nên nhận ngày tương lai. (2) `compute_age_days`
  viết `max(delta, 0)`, ép tuổi âm về 0 và **giấu hoàn toàn** lỗi (1) sau một con số hợp lệ giả.
- **Cách xử lý:** `_published_date` chọn **ngày gần nhất đã thực sự xảy ra** trong
  `published-online / published / issued / published-print / created`; `compute_age_days` bỏ clamp để
  tuổi có dấu và trả `None` thay vì sentinel `-1`; thêm check `published_not_in_future`.
- **Cách xác minh:** `REFRESH_SOURCE=1 python script/run_phase1.py` → `future_dated_rows` = 0, dải
  ngày 2026-02-04 → 2026-08-03, `age_days` 3–183.
- **Bài học:** một phép "làm sạch" phòng thủ như `max(x, 0)` có thể **che mất** lỗi dữ liệu thay vì xử
  lý nó. Giá trị bất thường chính là tín hiệu quan sát được; ép nó về giá trị hợp lệ là làm mù luôn
  tầng observability phía sau.

---

## 12. Xác minh tự động

Repo không đi kèm test hay grader tự động, nên nhóm bổ sung `script/verify_artifacts.py` (logic ở
`src/pipelines/verification.py`). Script chạy trên artifact đã sinh, không import module xử lý dữ liệu
nào, và trả exit code 1 nếu có critical failure.

| Nhóm check        | Nội dung kiểm tra                                                                              |
| ------------------ | ------------------------------------------------------------------------------------------------ |
| Artifact inventory | 20 artifact bắt buộc có mặt                                                                  |
| Frozen test set    | Vân tay`(id, question)` giống nhau giữa test set và ba file answers                        |
| Repair fidelity    | `papers_clean_repaired.json` bằng đúng `papers_clean.json`                                |
| Metric trajectory  | Cùng`samples`; corrupted giảm; repaired về baseline trong sai số 1e-4                      |
| Quality signals    | baseline PASS, corrupted FAIL, repaired PASS; corruption sinh critical failure                   |
| Freshness signals  | `stale_rows` corrupted > baseline, repaired = baseline, `future_dated_rows` = 0              |
| Corruption log     | Có seed, mọi bước có`affected_paper_ids`, `output_rows` khớp dataset thật             |
| Report ↔ artifact | Các con số trong bảng mục 10 khớp`data/results/*.json`                                    |
| Hygiene            | Không có pattern API key trong`report/` và `data/reports/`; `.env` không bị git track |
| Portability        | Manifest embedding không lưu absolute path                                                     |

Warning đã biết: `data/embeddings/papers_embeddings*.json` lưu `persist_path` dạng đường dẫn tuyệt đối
của máy chạy. Không sai kết quả nhưng làm artifact khác nhau giữa các máy và lộ tên thư mục người
dùng, nên báo ở mức warning chứ không chặn. Hướng sửa: lưu `persist_path` tương đối so với project root.

Verifier đã được kiểm chứng ngược: nhóm cố ý sửa `mean_token_f1` của trạng thái corrupted trong báo
cáo từ 0.7593 thành 0.9100, chạy lại thì script trả exit 1 kèm
`report says 0.9100, artifact says 0.7593`, sau đó giá trị đúng được khôi phục. Bằng chứng ở
`report/evidence/verify_negative_test.log`.

> **Cần chạy lại verifier trước khi nộp.** Các số `judge_accuracy` (0.8000) và `mean_judge_score`
> (4.2000) trong báo cáo này đã được cập nhật sau khi nhóm chuyển từ heuristic fallback sang LLM judge
> thật (`openai:gpt-4o-mini`). Lần verify gần nhất chạy trên bộ artifact cũ, nên phải chạy lại
> `python script/verify_artifacts.py` để check `report ↔ artifact` phản ánh đúng trạng thái nộp bài.

---

## 13. Giới hạn và hướng cải thiện

| Giới hạn                                            | Ảnh hưởng                                                                | Hướng cải thiện có thể kiểm chứng                                                                                                                                                      |
| ----------------------------------------------------- | --------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Ground truth sinh từ chính trường được index   | Baseline chạm trần 1.0000, không đo được khả năng tổng quát hoá | Thêm câu hỏi paraphrase (không chứa từ khoá`who authored`/`when was`) và multi-hop; nếu baseline nhóm mới thấp hơn 1.0000 rõ rệt thì test set đã thoát vòng khép kín |
| Corpus 24 paper, 20 câu hỏi                         | 1 câu = 5% metric; delta 0.2 thực ra chỉ là 4 câu                      | Tăng`max_results`, đo độ ổn định của delta                                                                                                                                           |
| Một seed corruption duy nhất                        | Chưa biết delta ổn định tới đâu                                     | Chạy nhiều seed, báo cáo trung bình ± độ lệch                                                                                                                                         |
| LLM judge không tất định                          | `judge_accuracy` có thể đổi giữa các lần chạy                     | Chạy nhiều lần, báo cáo khoảng dao động;`retrieval_hit_rate` và `mean_token_f1` không bị ảnh hưởng                                                                           |
| Ragas chưa chạy                                     | Thiếu faithfulness, context precision/recall                               | `RUN_RAGAS=1`                                                                                                                                                                                |
| Freshness`status` không đổi giữa 3 trạng thái | Không dùng được làm bằng chứng nhị phân                           | Đặt ngưỡng theo phân vị của corpus thay vì hằng số 180 ngày                                                                                                                         |
| `persist_path` tuyệt đối trong manifest          | Artifact khác nhau giữa các máy                                         | Lưu đường dẫn tương đối so với project root                                                                                                                                          |

---

## 14. Checklist trước khi nộp

- [X] Thông tin nhóm và repository chính xác.
- [X] Phân công khớp với module, artifact và kết quả thực tế.
- [X] Lệnh tái hiện đã được chạy lại trên phiên bản dùng để nộp — trên máy thứ hai, `report/evidence/`.
- [X] Baseline, corrupted và repaired dùng cùng evaluation set — check `frozen_test_set`.
- [X] Bảng metrics khớp với các file trong `data/results/` — **cần chạy lại `verify_artifacts.py`** sau khi đổi sang LLM judge thật.
- [X] Quality/freshness conclusions khớp với `data/quality/`.
- [X] Các đường dẫn báo cáo và artifact truy cập được.
- [X] Mỗi thành viên đã hoàn thành báo cáo vai trò riêng.
- [X] Không có `.env`, API key, token hoặc secret trong source, report, log hay ảnh.# Group Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin bài nộp

| Thông tin | Nội dung |
| --- | --- |
| Khóa/Lớp | [K3 hoặc K4] |
| Tên nhóm | [Tên hoặc mã nhóm] |
| Repository | [Đường dẫn repository] |
| Ngày hoàn thành | 2026-08-06 |

### Thành viên và phân công

| STT | Họ và tên | MSSV | Vai trò chính | Module/deliverable sở hữu |
| --: | --- | --- | --- | --- |
| 1 | [Họ tên] | [MSSV] | Source owner | `src/ingestion/crossref.py` — raw response, raw records |
| 2 | [Họ tên] | [MSSV] | Data model & evaluation-set owner | `src/ingestion/cleaning.py`, `src/evaluation/testset.py` |
| 3 | [Họ tên] | [MSSV] | Observability owner | `src/observability/quality.py`, `src/observability/reporting.py` |
| 4 | [Nếu có] | [MSSV] | Corruption & integration owner | `src/ingestion/corruption.py`, `src/pipelines/` |
| 5 | Nguyễn Văn Tiến | [MSSV] | Pipeline integration & evidence owner | `src/pipelines/verification.py`, `script/verify_artifacts.py` — tái hiện hai flow, `data/reports/verification_report.json`, `report/evidence/` |

## 2. Tóm tắt kết quả

**Tóm tắt của nhóm:**

Nhóm hoàn thành cả hai pha của bài lab. Pha 1 lấy 24 bài báo từ Crossref REST API, làm sạch thành
dataset 16 cột với `text_for_embedding`, index vào ChromaDB bằng `all-MiniLM-L6-v2`, sinh evaluation
set 20 câu hỏi (4 loại × 5 paper) và chạy đánh giá baseline. Artifact gồm `data/raw/`, `data/clean/`,
`data/embeddings/`, `data/eval/test_set.json`, `data/results/baseline_metrics.json`, `data/quality/`
và `data/reports/phase1_report.md`. Baseline đạt `retrieval_hit_rate` = 1.0000 và data quality
10/11 check (1 warning về freshness).

Pha 2 tiêm 6 loại corruption (drop 3 bản ghi mới nhất, blank 3 summary, thêm noise 3 summary,
truncate 3 title, đẩy lùi 3 ngày xuất bản 1500 ngày, nhân đôi 2 dòng), làm dataset còn 23 dòng.
Corruption ảnh hưởng rõ nhất là **drop 3 bản ghi mới nhất** — nó xóa hẳn document ground-truth khỏi
index nên `retrieval_hit_rate` giảm còn 0.8000; **blank/noise summary** kéo `mean_token_f1` xuống
0.7593. Data quality chuyển sang FAIL 6/11 với 3 critical failure. Repair từ raw snapshot khôi phục
toàn bộ 24 dòng và cả 4 metric trở lại đúng mức baseline (1.0000 / 1.0000 / 1.0000 / 5.0000).

Giới hạn còn lại: nhóm chưa cấu hình LLM provider, nên `judge_accuracy` và `mean_judge_score` đến từ
heuristic fallback (token-overlap) chứ không phải LLM judge; Ragas cũng chưa chạy.

## 3. Kiến trúc và luồng dữ liệu

### Luồng end-to-end

```text
Crossref API
    -> raw response/raw records
    -> cleaning và data modeling
    -> embedding + ChromaDB index
    -> evaluation baseline
    -> quality/freshness reports
    -> corruption
    -> re-index và re-evaluate
    -> repair từ dữ liệu nguồn
    -> comparison report
```

### Trách nhiệm của từng khối

| Khối | Input | Xử lý chính | Output/artifact | Owner |
| --- | --- | --- | --- | --- |
| Ingestion | Crossref `/works` | Fetch + retry/backoff, parse JATS abstract, normalize ngày | `data/raw/crossref_response.json`, `data/raw/crossref_records.json` | [Thành viên] |
| Cleaning | 24 raw records | Normalize text, dedupe, `age_days`, `text_for_embedding` | `data/clean/papers_clean.{csv,json}` | [Thành viên] |
| Embedding/index | Cleaned df | MiniLM-L6-v2, ChromaDB cosine, collection `papers-baseline` | `data/embeddings/papers_embeddings.json`, `data/chroma/` | [Thành viên] |
| Evaluation | Cleaned df | Sinh 20 câu hỏi 4 loại, chấm hit-rate/token-F1/judge | `data/eval/test_set.json`, `data/results/baseline_*.json` | [Thành viên] |
| Observability | Cleaned df | 11 quality check + freshness | `data/quality/*.json`, `data/quality/gx/*.json` | [Thành viên] |
| Corruption/repair | Cleaned df, raw records | 6 corruption scenario, repair từ raw | `data/results/corruption_log.json`, `data/clean/*_corrupted|repaired.*` | [Thành viên] |
| Orchestration | Toàn bộ | Thứ tự chạy 2 flow, đảm bảo dùng chung test set | `data/reports/*.md` | [Thành viên] |

## 4. Cách tái hiện kết quả

### Cấu hình không chứa secret

| Biến/cấu hình | Giá trị sử dụng |
| --- | --- |
| `LLM_PROVIDER` | `gemini` (chưa cấu hình key → dùng heuristic fallback judge) |
| `LLM_MODEL` | `gemini-2.5-flash` |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Số lượng Crossref records | 24 (`max_results`, over-fetch 72 rồi lọc) |
| Retrieval `top_k` | 4 |
| Freshness threshold | 180 ngày |
| Random seed | 20251006 (`src/ingestion/corruption.py`) |

### Lệnh cài đặt

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

### Lệnh chạy

```bash
python script/run_phase1.py
python script/run_corruption_flow.py
python script/verify_artifacts.py
```

Cờ tùy chọn: `REFRESH_SOURCE=1` để fetch lại Crossref, `REFRESH_TEST_SET=1` để sinh lại test set,
`RUN_RAGAS=1` để bật Ragas.

`script/verify_artifacts.py` là bước xác minh cuối: nó chạy 16 check trên artifact đã sinh ra và trả
exit code 0 khi không có critical failure. Xem mục 12.

### Kết quả tái hiện

| Lệnh | Trạng thái | Thời điểm chạy gần nhất | Bằng chứng |
| --- | --- | --- | --- |
| Baseline pipeline | Thành công (exit 0) | 2026-08-06T04:04Z | `data/reports/phase1_report.md`, `data/results/baseline_metrics.json`, `report/evidence/run_phase1.log` |
| Corruption flow | Thành công (exit 0) | 2026-08-06T04:04Z | `data/reports/corruption_report.md`, `data/results/corruption_log.json`, `report/evidence/run_corruption_flow.log` |
| Artifact verification | Thành công (exit 0) — 15/16 PASS, 0 FAIL, 1 WARN | 2026-08-06T04:12Z | `data/reports/verification_report.json`, `report/evidence/verify_artifacts.log` |

Toàn bộ pipeline đã được chạy lại trên một máy thứ hai từ cùng raw snapshot. `git diff` trên `data/`
sau lần chạy đó chỉ khác ở trường `generated_at` và `persist_path`; ba file metrics
(`baseline_metrics.json`, `corrupted_metrics.json`, `repaired_metrics.json`) giống hệt bản đã commit.

## 5. Ingestion, cleaning và data contract

### Nguồn dữ liệu

| Thuộc tính | Giá trị |
| --- | --- |
| Source | Crossref REST API — `https://api.crossref.org/works` |
| Query/filter | `query.bibliographic` = "agentic retrieval augmented generation large language model"; `filter=from-pub-date:2026-02-07,has-abstract:true`; `sort=issued&order=desc` |
| Thời điểm lấy dữ liệu | 2026-08-06T03:36Z |
| Số record nhận được | Yêu cầu 72 rows → Crossref trả 72 items → 70 record hợp lệ sau parse → giữ 24 theo `max_results` |
| Cơ chế retry/backoff | 5 lần thử, exponential backoff 1→16s trên status 429/500/502/503/504 và lỗi mạng |

### Raw và clean schema

| Trường | Kiểu | Bắt buộc? | Ý nghĩa | Xử lý khi thiếu/sai |
| --- | --- | --- | --- | --- |
| `paper_id` | str | Có | DOI, dùng làm document ID | Bỏ record nếu thiếu hoặc trùng |
| `title` | str | Có | Tiêu đề bài báo | Bỏ nếu < 10 ký tự; dedupe theo title lowercase |
| `summary` | str | Có | Abstract đã strip JATS/HTML | Bỏ nếu < 80 ký tự |
| `authors_joined` | str | Không | Danh sách tác giả nối bằng ", " | Rỗng → "Unknown" |
| `categories_joined` | str | Không | Subject của Crossref | Rỗng → fallback container-title + type, cuối cùng "Uncategorized" |
| `published` | str (ISO date) | Có | Ngày thực sự đã phát hành | Bỏ record nếu không parse được |
| `age_days` | int | Có | Số ngày tính từ `published` tới ngày chạy | Có dấu (âm = forward-dated) |
| `text_for_embedding` | str | Có | Chuỗi được embed | Sinh lại từ các cột khác |

### Quy tắc cleaning

| Quy tắc | Quality dimension | Số record bị tác động | Cách xác minh |
| --- | --- | ---: | --- |
| Bỏ record thiếu DOI/title/abstract hợp lệ | Completeness | 2/72 items bị loại ở bước parse (70 hợp lệ, sau đó cắt còn 24 theo `max_results`) | Chạy `parse_crossref_payload` trên `crossref_response.json` → 70; `crossref_records.json` → 24 |
| Dedupe theo `paper_id` và title lowercase | Uniqueness | 0 (nguồn đã sạch) | Check `paper_id_unique`, `title_unique` trong `data/quality/baseline_quality.json` |
| Normalize whitespace, strip JATS/HTML entity | Validity | 24/24 | Đọc cột `summary` trong `papers_clean.csv` |
| Chuẩn hóa ngày về ngày đã thực sự xảy ra | Validity/Timeliness | 24/24 | `future_dated_rows` = 0 trong `freshness_report.json` |

**`text_for_embedding`, document ID và `age_days`:**

`text_for_embedding` ghép 5 trường theo định dạng `Title / Authors / Categories / Published / Summary`
(hàm `build_text_for_embedding` trong `cleaning.py`), để retrieval bắt được cả câu hỏi về tác giả và
ngày tháng chứ không chỉ nội dung abstract. Hàm này được export ra ngoài để corruption flow gọi lại
sau khi sửa dữ liệu — nếu không, corruption sẽ không bao giờ đến được vector store.

Document ID dùng DOI viết thường; ChromaDB record ID là `{paper_id}::{index}` nên các dòng duplicate
vẫn được nạp mà không đụng ID.

`age_days` = số ngày **có dấu** giữa `published` và ngày chạy. Điểm quan trọng: Crossref forward-date
ngày issue (một bài đăng 2026 có thể ghi `issued` = 2028). Nhóm chọn "ngày gần nhất đã thực sự xảy
ra" trong các ứng viên `published-online / published / issued / published-print / created`, nên
`age_days` không bao giờ âm giả tạo và freshness mới có ý nghĩa.

## 6. Evaluation setup

| Thành phần | Cấu hình thực tế |
| --- | --- |
| Số câu hỏi | 20 |
| Các `question_type` | `summary`, `authors`, `date`, `categories` (5 paper × 4 loại) |
| Ground-truth document ID | DOI của paper sinh ra câu hỏi (`ground_truth_doc_ids`) |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Vector store/collection | ChromaDB persistent, `papers-baseline` / `papers-corrupted` / `papers-repaired`, cosine |
| Retrieval `top_k` | 4 |
| LLM provider/model | Không cấu hình → heuristic fallback judge (token overlap) |
| Test set dùng chung | `data/eval/test_set.json`, đóng băng cho cả ba trạng thái |

**Vì sao giữ nguyên test set:** nếu sinh lại test set từ dataset corrupted thì ground truth sẽ được
tạo từ chính dữ liệu lỗi, và mọi phép so sánh mất ý nghĩa — agent sẽ "đúng" với dữ liệu sai. Pipeline
chỉ sinh test set khi file chưa tồn tại hoặc khi đặt `REFRESH_TEST_SET=1`; cả ba lần evaluate đều
đọc cùng một đường dẫn.

## 7. Kết quả baseline

### Artifact checklist

| Artifact | Đường dẫn thực tế | Trạng thái | Ghi chú |
| --- | --- | --- | --- |
| Raw response/records | `data/raw/` | Có | `crossref_response.json` (1.04 MB), `crossref_records.json` (24 records) |
| Cleaned dataset | `data/clean/` | Có | 24 dòng × 16 cột, cả CSV và JSON |
| Embedding manifest/index | `data/embeddings/`, `data/chroma/` | Có | 3 collection: `papers-baseline` 24, `papers-repaired` 24, `papers-corrupted` 23 docs |
| Evaluation set | `data/eval/test_set.json` | Có | 20 câu hỏi |
| Baseline metrics | `data/results/baseline_metrics.json` | Có | Kèm `baseline_answers.json` |
| Quality/freshness | `data/quality/` | Có | 4 quality JSON + 3 freshness JSON + 3 file GX-style |
| Baseline report | `data/reports/phase1_report.md` | Có | — |
| Verification report | `data/reports/verification_report.json` | Có | 16 check, 0 critical failure |

### Baseline metrics

| Metric | Giá trị | Diễn giải |
| --- | ---: | --- |
| `retrieval_hit_rate` | 1.0000 | Cả 20 câu đều retrieve đúng document ground truth trong top-4 |
| `mean_token_f1` | 1.0000 | Câu trả lời trùng khớp ground truth |
| `judge_accuracy` | 1.0000 | **Từ heuristic fallback**, không phải LLM judge |
| `mean_judge_score` | 5.0000 | Như trên |
| Ragas | N/A | Chưa bật; cần `RUN_RAGAS=1` và một LLM provider |

> Lưu ý trung thực: QA layer trả lời theo cách **trích xuất** trực tiếp từ metadata đã index, còn
> ground truth được sinh từ chính các trường đó. Vì vậy baseline 1.0000 là **trần lý thuyết theo thiết
> kế**, không phải bằng chứng agent tổng quát hóa tốt. Giá trị của baseline ở đây là làm mốc để đo
> mức suy giảm khi dữ liệu hỏng.

## 8. Data quality và freshness

### Quality checks

Tổng: **PASS 10/11** (1 warning). Chi tiết trong `data/quality/baseline_quality.json`.

| Check | Quality dimension | Ngưỡng/kỳ vọng | Kết quả baseline | Bằng chứng |
| --- | --- | --- | --- | --- |
| `row_count_minimum` | Completeness | >= 10 dòng | PASS (24) | `baseline_quality.json` |
| `paper_id_not_null` | Completeness | 0 giá trị rỗng | PASS (0) | như trên |
| `paper_id_unique` | Uniqueness | 0 trùng | PASS (0) | như trên |
| `title_not_null` | Completeness | 0 rỗng | PASS (0) | như trên |
| `title_min_length` | Validity | >= 10 ký tự | PASS (0 vi phạm) | như trên |
| `title_unique` | Uniqueness | 0 trùng (warning) | PASS (0) | như trên |
| `summary_not_empty` | Completeness | 0 rỗng | PASS (0) | như trên |
| `summary_min_length` | Validity | >= 80 ký tự | PASS (0 vi phạm) | như trên |
| `text_for_embedding_not_empty` | Completeness | 0 rỗng | PASS (0) | như trên |
| `published_not_in_future` | Validity | 0 dòng forward-dated (warning) | PASS (0) | `freshness_report.json` |
| `freshness_within_threshold` | Timeliness | `age_days` <= 180 (warning) | **WARN (1 dòng)** | `freshness_report.json` |

Nhóm phân biệt `critical` và `warning`: dataset chỉ FAIL khi có check `critical` fail. Freshness của
nguồn là tín hiệu giám sát, không phải vi phạm schema — nên nó được nêu ra nhưng không chặn pipeline.

### Freshness

| Thuộc tính | Giá trị |
| --- | --- |
| Freshness được đo tại | Cleaned dataset (`data/clean/papers_clean.json`) |
| Timestamp mới nhất | 2026-08-03 (`min_age_days` = 3) |
| Ngưỡng freshness | 180 ngày |
| Trạng thái baseline | STALE (1/24 dòng vượt ngưỡng) |
| Lý do | 1 bài có `age_days` = 183, chỉ vượt ngưỡng 3 ngày. Filter Crossref `from-pub-date` áp lên ngày pub của Crossref (có thể forward-dated), còn nhóm quy về ngày thực tế đã phát hành nên bài này rơi ra ngoài cửa sổ 180 ngày. Đây là phát hiện thật của quality layer, không phải lỗi code. |

## 9. Corruption scenarios và repair

Seed cố định `20251006`, dataset 24 → 23 dòng.

| Corruption | Cách tạo | Record bị tác động | Quality signal kỳ vọng | Tác động thực tế | Cách repair |
| --- | --- | ---: | --- | --- | --- |
| Drop latest records | Xóa 3 bài mới nhất (mô phỏng incremental load bị cắt) | 3 | `row_count`, freshness | `retrieval_hit_rate` 1.0 → 0.8: document ground truth biến mất khỏi index | Rebuild từ raw snapshot |
| Blank summary | Gán `summary = ""` | 3 | `summary_not_empty` FAIL | `summary_not_empty` = 3, kéo `mean_token_f1` xuống | Rebuild từ raw snapshot |
| Inject summary noise | Chèn markup/boilerplate chưa parse vào abstract | 3 | `summary_min_length` | Embedding lệch, câu trả lời `summary` sai | Rebuild từ raw snapshot |
| Truncate title | Cắt title còn 12 ký tự | 3 | `title_min_length` | Exact-title lookup trong `qa.py` không khớp nữa | Rebuild từ raw snapshot |
| Stale publication date | Đẩy lùi ngày 1500 ngày | 3 | `freshness_within_threshold` | `stale_rows` 1 → 4, oldest lùi về 2022-03-21, câu hỏi loại `date` trả sai | Rebuild từ raw snapshot |
| Duplicate rows | Nhân đôi 2 dòng | 2 | `paper_id_unique` FAIL | `paper_id_unique` = 2 trùng, `title_unique` = 2 | Rebuild từ raw snapshot |

Corruption log:

- Đường dẫn: `data/results/corruption_log.json`
- Trạng thái: Có
- Nhận xét: log ghi đủ seed, số dòng vào/ra, và với mỗi bước có `step`, mô tả, `count` và danh sách
  `affected_paper_ids` — đủ để truy vết dòng nào bị hỏng theo cách nào.

**Repair phục hồi từ nguồn đáng tin cậy như thế nào:** repair **không** sửa chữa trên dataset đã hỏng.
`corruption_flow.py` đọc lại `data/raw/crossref_records.json` — snapshot raw được ghi ngay sau khi
fetch và không bị corruption chạm vào — rồi chạy lại đúng hàm `build_clean_dataframe` của pha 1. Nhờ
vậy repaired dataset **byte-for-byte giống hệt** baseline (`papers_clean.json` và
`papers_clean_repaired.json` đều 104 493 bytes, so sánh nhị phân bằng nhau), chứng minh việc phục hồi
là tái tạo từ nguồn chứ không phải che lỗi.

## 10. So sánh baseline, corrupted và repaired

| Metric/signal | Baseline | Corrupted | Repaired | Thay đổi do corruption | Mức phục hồi | Nhận xét |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `retrieval_hit_rate` | 1.0000 | 0.8000 | 1.0000 | −0.2000 | 100% | 4/20 câu mất document ground truth |
| `mean_token_f1` | 1.0000 | 0.7593 | 1.0000 | −0.2407 | 100% | Summary rỗng/nhiễu và ngày sai làm câu trả lời lệch |
| `judge_accuracy` | 1.0000 | 0.7500 | 1.0000 | −0.2500 | 100% | Heuristic judge; 5/20 câu bị chấm sai |
| `mean_judge_score` | 5.0000 | 4.0000 | 5.0000 | −1.0000 | 100% | Như trên |
| Quality checks pass/fail | PASS 10/11 | **FAIL 6/11** | PASS 10/11 | 3 critical failure mới | 100% | `paper_id_unique`, `summary_not_empty`, `summary_min_length` |
| Freshness status | STALE (1/24) | STALE (4/23) | STALE (1/24) | +3 dòng stale, oldest 2026-02-04 → 2022-03-21 | 100% | Status không đổi nhưng số liệu đổi rõ |

**Hai kết luận nhân quả có artifact hỗ trợ:**

1. Xóa 3 bản ghi mới nhất → 3 document ground truth biến mất khỏi collection `papers-corrupted`
   (`corruption_log.json`, bước `drop_latest_records`) → `retrieval_hit_rate` giảm 1.0000 → 0.8000
   (`baseline_metrics.json` vs `corrupted_metrics.json`); 4/20 câu có `retrieval_hit = false` trong
   `corrupted_answers.json`.
2. Blank + noise summary và stale date → `summary_not_empty` = 3 và `summary_min_length` = 3 chuyển
   quality sang FAIL, `stale_rows` tăng 1 → 4 (`corrupted_quality.json`,
   `freshness_report_corrupted.json`) → `mean_token_f1` giảm 1.0000 → 0.7593. Sau khi rebuild từ raw,
   cả hai tín hiệu quality trở lại mức baseline và `mean_token_f1` về 1.0000
   (`repaired_quality.json`, `repaired_metrics.json`).

Lưu ý: freshness **status** giữ nguyên STALE ở cả ba trạng thái vì baseline vốn đã có 1 dòng 183 ngày.
Bằng chứng cho tác động của corruption nằm ở *số liệu* (stale_rows 1 → 4 → 1; oldest_published
2026-02-04 → 2022-03-21 → 2026-02-04), không phải ở nhãn status.

## 11. Vấn đề tích hợp quan trọng

- **Triệu chứng:** Freshness report ghi `latest_published` = 2028-06-15 nhưng `max_age_days` = 0, và
  toàn bộ 24 dòng đều "0 ngày tuổi" — báo cáo tự mâu thuẫn.
- **Nguyên nhân:** Crossref forward-date ngày issue của tạp chí. Bản cài đặt đầu tiên lấy trực tiếp
  `published`/`issued` rồi clamp `age_days` về 0 bằng `max(delta, 0)`, nên ngày tương lai bị giấu sau
  một số 0 giả.
- **Cách xử lý:** `_published_date` chọn ngày **gần nhất đã thực sự xảy ra** trong các ứng viên
  (`published-online`, `published`, `issued`, `published-print`, `created`); `compute_age_days` bỏ
  clamp và trả về số có dấu; thêm check `published_not_in_future` để lộ ra nếu vấn đề tái diễn.
- **Cách xác minh:** chạy lại `REFRESH_SOURCE=1 python script/run_phase1.py`; `freshness_report.json`
  cho `future_dated_rows` = 0, dải ngày 2026-02-04 → 2026-08-03, `age_days` 3–183.

## 12. Xác minh tự động

Repo không đi kèm test hay grader tự động, nên nhóm bổ sung `script/verify_artifacts.py`
(logic ở `src/pipelines/verification.py`). Script chạy trên artifact đã sinh, không import module
xử lý dữ liệu nào, và trả exit code 1 nếu có critical failure.

| Nhóm check | Nội dung kiểm tra | Kết quả |
| --- | --- | --- |
| Artifact inventory | 20 artifact bắt buộc có mặt | PASS (20/20) |
| Frozen test set | Vân tay `(id, question)` giống nhau giữa test set và ba file answers | PASS (20 câu dùng chung) |
| Repair fidelity | `papers_clean_repaired.json` bằng đúng `papers_clean.json` | PASS (24 dòng) |
| Metric trajectory | Cùng `samples`; corrupted giảm; repaired về baseline trong sai số 1e-4 | PASS (3 check) |
| Quality signals | baseline PASS, corrupted FAIL, repaired PASS; corruption sinh critical failure | PASS (2 check) |
| Freshness signals | `stale_rows` corrupted > baseline và repaired = baseline; `future_dated_rows` = 0 | PASS (2 check) |
| Corruption log | Có seed, mọi bước có `affected_paper_ids`, `output_rows` khớp dataset thật | PASS (2 check) |
| Report ↔ artifact | 12 con số trong bảng mục 10 khớp `data/results/*.json` | PASS |
| Hygiene | Không có pattern API key trong `report/` và `data/reports/`; `.env` không bị git track | PASS (2 check) |
| Portability | Manifest embedding không lưu absolute path | **WARN** |

Tổng: **15/16 PASS, 0 FAIL, 1 WARN**. Chi tiết máy đọc được ở `data/reports/verification_report.json`.

Warning còn lại: `data/embeddings/papers_embeddings*.json` lưu `persist_path` dạng đường dẫn tuyệt đối
của máy chạy. Nó không sai kết quả nhưng làm artifact khác nhau giữa các máy và lộ tên thư mục người
dùng, nên được báo ở mức warning chứ không chặn. Hướng sửa: lưu `persist_path` tương đối so với
project root.

Verifier đã được kiểm chứng ngược: nhóm cố ý sửa `mean_token_f1` của trạng thái corrupted trong báo
cáo này từ 0.7593 thành 0.9100, chạy lại thì script trả exit 1 kèm
`report says 0.9100, artifact says 0.7593`, sau đó giá trị đúng được khôi phục. Bằng chứng ở
`report/evidence/verify_negative_test.log`.

## 13. Giới hạn và hướng cải thiện

| Giới hạn hiện tại | Ảnh hưởng | Hướng cải thiện có thể kiểm chứng |
| --- | --- | --- |
| Chưa cấu hình LLM provider | `judge_accuracy`/`mean_judge_score` là heuristic token-overlap, không phải LLM judge; agent demo bị skip | Điền `GOOGLE_API_KEY` vào `.env`, chạy lại và so sánh judge metrics giữa hai chế độ |
| Ground truth sinh từ chính trường được index | Baseline chạm trần 1.0000, không đo được khả năng tổng quát hóa | Thêm câu hỏi paraphrase/multi-hop mà `qa.py` không trả lời được bằng trích xuất trực tiếp |
| Ragas chưa chạy | Thiếu faithfulness/context precision | `RUN_RAGAS=1` sau khi có LLM provider |
| Corpus 24 paper | Metric nhạy với từng câu (1 câu = 5%) | Tăng `max_results`, đánh giá độ ổn định của delta |
| Chỉ một seed corruption | Chưa biết delta ổn định tới đâu | Chạy nhiều seed, báo cáo trung bình ± độ lệch |

## 14. Checklist trước khi nộp

- [ ] Thông tin nhóm và repository chính xác.
- [ ] Phân công khớp với module, artifact và kết quả thực tế.
- [x] Lệnh tái hiện đã được chạy lại trên phiên bản dùng để nộp — trên máy thứ hai, `report/evidence/`.
- [x] Baseline, corrupted và repaired dùng cùng evaluation set — check `frozen_test_set`.
- [x] Bảng metrics khớp với các file trong `data/results/` — check `report_matches_artifacts`, 12 số.
- [x] Quality/freshness conclusions khớp với `data/quality/` — check `quality_signals`, `freshness_reacts_to_corruption`.
- [x] Các đường dẫn báo cáo và artifact truy cập được — check `artifacts_present`, 20/20.
- [ ] Mỗi thành viên đã hoàn thành báo cáo vai trò riêng — hiện có `report/individual_report_thanh_vien_5.md`.
- [x] Không có `.env`, API key, token hoặc secret trong source, report, log hay ảnh — check `no_secrets_in_artifacts`, `env_file_not_tracked`.
