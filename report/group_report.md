# Group Report — Day 10: Data Pipeline & Data Observability

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
| 5 | [Nếu có] | [MSSV] | [Vai trò] | [File, hàm hoặc artifact] |

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
```

Cờ tùy chọn: `REFRESH_SOURCE=1` để fetch lại Crossref, `REFRESH_TEST_SET=1` để sinh lại test set,
`RUN_RAGAS=1` để bật Ragas.

### Kết quả tái hiện

| Lệnh | Trạng thái | Thời điểm chạy gần nhất | Bằng chứng |
| --- | --- | --- | --- |
| Baseline pipeline | Thành công (exit 0) | 2026-08-06T03:38Z | `data/reports/phase1_report.md`, `data/results/baseline_metrics.json` |
| Corruption flow | Thành công (exit 0) | 2026-08-06T03:41Z | `data/reports/corruption_report.md`, `data/results/corruption_log.json` |

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

## 12. Giới hạn và hướng cải thiện

| Giới hạn hiện tại | Ảnh hưởng | Hướng cải thiện có thể kiểm chứng |
| --- | --- | --- |
| Chưa cấu hình LLM provider | `judge_accuracy`/`mean_judge_score` là heuristic token-overlap, không phải LLM judge; agent demo bị skip | Điền `GOOGLE_API_KEY` vào `.env`, chạy lại và so sánh judge metrics giữa hai chế độ |
| Ground truth sinh từ chính trường được index | Baseline chạm trần 1.0000, không đo được khả năng tổng quát hóa | Thêm câu hỏi paraphrase/multi-hop mà `qa.py` không trả lời được bằng trích xuất trực tiếp |
| Ragas chưa chạy | Thiếu faithfulness/context precision | `RUN_RAGAS=1` sau khi có LLM provider |
| Corpus 24 paper | Metric nhạy với từng câu (1 câu = 5%) | Tăng `max_results`, đánh giá độ ổn định của delta |
| Chỉ một seed corruption | Chưa biết delta ổn định tới đâu | Chạy nhiều seed, báo cáo trung bình ± độ lệch |

## 13. Checklist trước khi nộp

- [ ] Thông tin nhóm và repository chính xác.
- [ ] Phân công khớp với module, artifact và kết quả thực tế.
- [x] Lệnh tái hiện đã được chạy lại trên phiên bản dùng để nộp.
- [x] Baseline, corrupted và repaired dùng cùng evaluation set.
- [x] Bảng metrics khớp với các file trong `data/results/`.
- [x] Quality/freshness conclusions khớp với `data/quality/`.
- [x] Các đường dẫn báo cáo và artifact truy cập được.
- [ ] Mỗi thành viên đã hoàn thành báo cáo vai trò riêng.
- [x] Không có `.env`, API key, token hoặc secret trong source, report, log hay ảnh.
