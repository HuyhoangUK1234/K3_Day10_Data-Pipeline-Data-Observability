# Individual Report - Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Huỳnh Hoàng Việt |
| MSSV | 2A202601105 |
| Khóa/Lớp | K3 |
| Tên nhóm | B2 |
| Repository | `E:\VinAI\K3_Day10_Data-Pipeline-Data-Observability` |
| Ngày hoàn thành | 2026-08-06 |
| Vai trò chính | Corruption & Repair (`src/ingestion/corruption.py`) |

## 2. Vai trò và phạm vi công việc

Vai trò của tôi trong dự án là phụ trách phần **Corruption & Repair**. Phần này nằm ở Pha 2 của pipeline, sau khi nhóm đã có baseline dataset sạch, embedding index, evaluation set và quality/freshness reports. Nhiệm vụ chính của tôi là tạo lỗi dữ liệu có kiểm soát, đo tác động của lỗi đó lên RAG agent, rồi repair bằng cách rebuild lại dữ liệu từ raw snapshot.

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Data corruption simulator | `src/ingestion/corruption.py` - `corrupt_clean_dataframe` | Clean DataFrame từ `data/clean/papers_clean.json` | Corrupted DataFrame, `data/results/corruption_log.json` | Hoàn thành |
| Corruption traceability | `src/ingestion/corruption.py` | Các row được chọn để làm lỗi | Log có seed, số dòng trước/sau, từng step và DOI bị ảnh hưởng | Hoàn thành |
| Rebuild derived columns | `src/ingestion/corruption.py` | `title`, `summary`, `published`, `updated`, `age_days` sau corruption | `title_chars`, `summary_chars`, `text_for_embedding` được tính lại | Hoàn thành |
| Repair từ raw snapshot | `src/pipelines/corruption_flow.py` | `data/raw/crossref_records.json` | `data/clean/papers_clean_repaired.csv/json` | Hoàn thành |
| Comparison report | `data/reports/corruption_report.md` | Metrics/quality/freshness của baseline, corrupted, repaired | Báo cáo so sánh 3 trạng thái | Hoàn thành |

Ngoài module chính, tôi cũng kiểm tra phần tích hợp với observability để đảm bảo lỗi dữ liệu được phát hiện qua quality checks và freshness signals, không chỉ làm thay đổi file dữ liệu một cách hình thức.

## 3. Kết quả chạy dự án

Tôi đã tạo môi trường ảo `.venv`, cài dependencies bằng `pip install -e .`, sau đó chạy lại đầy đủ hai pipeline bằng Python trong môi trường ảo.

Lệnh đã chạy:

```powershell
.\.venv\Scripts\python.exe script\run_phase1.py
.\.venv\Scripts\python.exe script\run_corruption_flow.py
```

Kết quả chạy baseline:

| Hạng mục | Kết quả |
| --- | --- |
| Thời điểm report | `2026-08-06T04:54:35.446147+00:00` |
| Raw records | 24 |
| Clean rows | 24 |
| Evaluation samples | 20 |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Chroma collection | `papers-baseline` với 24 documents |
| LLM provider | Chưa cấu hình `GOOGLE_API_KEY`, dùng heuristic fallback judge |
| Baseline quality | PASS 10/11 |
| Baseline freshness | STALE, 1/24 stale rows |

Kết quả chạy corruption/repair flow:

| Hạng mục | Kết quả |
| --- | --- |
| Thời điểm corruption report | `2026-08-06T04:56:21.388726+00:00` |
| Baseline rows | 24 |
| Corrupted rows | 23 |
| Repaired rows | 24 |
| Corrupted quality | FAIL 6/11 |
| Repaired quality | PASS 10/11 |
| Corrupted freshness | STALE, 4/23 stale rows |
| Repaired freshness | STALE, 1/24 stale rows |

Các artifact chính được sinh/cập nhật:

| Artifact | Ý nghĩa |
| --- | --- |
| `data/reports/phase1_report.md` | Báo cáo baseline sau khi chạy Pha 1 |
| `data/reports/corruption_report.md` | Báo cáo so sánh baseline/corrupted/repaired |
| `data/results/baseline_metrics.json` | Metrics của baseline |
| `data/results/corrupted_metrics.json` | Metrics sau corruption |
| `data/results/repaired_metrics.json` | Metrics sau repair |
| `data/results/corruption_log.json` | Log chi tiết các lỗi được tiêm vào dữ liệu |
| `data/quality/baseline_quality.json` | Quality checks của baseline |
| `data/quality/corrupted_quality.json` | Quality checks của corrupted dataset |
| `data/quality/repaired_quality.json` | Quality checks của repaired dataset |
| `data/quality/freshness_report*.json` | Freshness reports cho ba trạng thái |

## 4. Phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Baseline pipeline cho kết quả tốt trên dữ liệu sạch, nhưng điều đó chưa chứng minh pipeline có thể phát hiện và phục hồi khi dữ liệu bị lỗi. Trong hệ thống RAG, lỗi dữ liệu có thể làm retriever không lấy được document đúng hoặc làm agent trả lời sai dù code agent không đổi. Vì vậy phần Corruption & Repair cần tạo ra các lỗi giống lỗi production, chạy lại index/evaluation, rồi chứng minh repair đưa chất lượng về mức baseline.

### Cách triển khai trong `corruption.py`

Hàm `corrupt_clean_dataframe(df, output_log_path)` nhận cleaned DataFrame, copy dữ liệu và áp dụng các corruption steps với seed cố định `20251006` để kết quả có thể tái lập. Các row bị lỗi được chọn không trùng nhau giữa các nhóm chính bằng helper `_pick`.

| Corruption step | Cách tạo lỗi | Số record | Mô phỏng failure mode |
| --- | --- | ---: | --- |
| `drop_latest_records` | Xóa 3 paper mới nhất | 3 | Incremental load bị cắt, thiếu dữ liệu mới |
| `blank_summary` | Gán `summary = ""` | 3 | Abstract extractor không lấy được nội dung |
| `inject_summary_noise` | Chèn HTML/boilerplate/noise vào summary | 3 | Parser để lọt markup hoặc text rác |
| `truncate_title` | Cắt title còn 12 ký tự | 3 | Cột downstream quá ngắn làm mất title |
| `stale_publication_date` | Lùi `published`, `updated` 1500 ngày và tăng `age_days` | 3 | Backfill ghi sai ngày xuất bản |
| `duplicate_rows` | Append lại 2 dòng đầu | 2 | Loader replay một phần batch |

Sau khi sửa dữ liệu, code tính lại `title_chars`, `summary_chars` và đặc biệt là `text_for_embedding`. Đây là điểm quan trọng vì vector store dùng `text_for_embedding` để build embedding. Nếu không rebuild cột này, corruption ở `title` hoặc `summary` có thể không thật sự ảnh hưởng đến retrieval.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | Clean DataFrame có `paper_id`, `title`, `summary`, `published`, `updated`, `age_days`, `text_for_embedding` |
| Output | Corrupted DataFrame và JSON log tại `data/results/corruption_log.json` |
| Điều kiện lỗi | Nếu DataFrame rỗng thì raise `ValueError` |
| Module phụ thuộc | `ingestion.cleaning.build_text_for_embedding`, `core.utils.now_utc`, `core.utils.write_json` |
| Module dùng output | `src/pipelines/corruption_flow.py`, `retrieval.index.LocalEmbeddingIndex`, `evaluation.metrics.evaluate_pipeline`, `observability.quality` |

## 5. Corruption log thực tế

Artifact: `data/results/corruption_log.json`  
Generated at: `2026-08-06T04:56:04.720595+00:00`  
Seed: `20251006`  
Input rows: 24  
Output rows: 23  
Net row change: -1

| Step | Count | Affected paper IDs |
| --- | ---: | --- |
| `drop_latest_records` | 3 | `10.61838/jhrlp.213`, `10.61838/jhrlp.268`, `10.61838/jafci.485` |
| `blank_summary` | 3 | `10.26634/javr.4.1.1116`, `10.32738/jeppm-2025-345`, `10.22158/eltls.v8n3p21` |
| `inject_summary_noise` | 3 | `10.7256/2453-8922.2027.1.81187`, `10.61838/jtesd.399`, `10.15294/jvce.v11i2.45302` |
| `truncate_title` | 3 | `10.61838/kman.jrmde.372`, `10.26634/javr.4.1.1273`, `10.11116/9789461667755` |
| `stale_publication_date` | 3 | `10.26634/javr.4.1.11309`, `10.21462/jeltl.v10i3.1648`, `10.26877/jipmat.v11i1.2279` |
| `duplicate_rows` | 2 | `10.61838/kman.jrmde.372`, `10.61838/kman.ijes.1520` |

Log này giúp truy vết chính xác paper nào bị lỗi ở bước nào. Điều này quan trọng khi giải thích vì sao quality checks fail và vì sao một số câu hỏi trong evaluation bị giảm điểm.

## 6. Phân tích metrics

Cả ba trạng thái được đánh giá trên cùng frozen test set gồm 20 câu hỏi, nên thay đổi metrics có thể quy cho chất lượng dataset thay vì do test set khác nhau.

| Metric | Baseline | Corrupted | Repaired | Corrupted vs baseline | Repaired vs baseline | Nhận xét |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `retrieval_hit_rate` | 1.0000 | 0.8000 | 1.0000 | -0.2000 | +0.0000 | Missing records làm retriever mất ground-truth docs |
| `mean_token_f1` | 1.0000 | 0.7593 | 1.0000 | -0.2407 | +0.0000 | Summary rỗng/noisy và date sai làm answer lệch ground truth |
| `judge_accuracy` | 1.0000 | 0.7500 | 1.0000 | -0.2500 | +0.0000 | Heuristic judge phát hiện chất lượng câu trả lời giảm |
| `mean_judge_score` | 5.0000 | 4.0000 | 5.0000 | -1.0000 | +0.0000 | Corrupted state giảm 1 điểm trung bình |

Kết luận: corruption làm giảm cả 4/4 metrics. Repair từ raw snapshot phục hồi cả 4/4 metrics về đúng mức baseline.

## 7. Phân tích data quality và freshness

### Data quality

| State | Result | Passed / total | Critical failures | Warnings |
| --- | --- | ---: | --- | --- |
| Baseline | PASS | 10/11 | Không có | `freshness_within_threshold` |
| Corrupted | FAIL | 6/11 | `paper_id_unique`, `summary_not_empty`, `summary_min_length` | `title_unique`, `freshness_within_threshold` |
| Repaired | PASS | 10/11 | Không có | `freshness_within_threshold` |

Corrupted dataset fail đúng các check liên quan đến corruption đã tạo: duplicate rows làm fail `paper_id_unique` và warning `title_unique`; blank summary làm fail `summary_not_empty` và `summary_min_length`; stale date làm warning freshness xấu đi.

### Freshness

| State | Status | Latest published | Oldest published | Stale rows | Stale ratio | Max age days |
| --- | --- | --- | --- | ---: | ---: | ---: |
| Baseline | STALE | 2026-08-03 | 2026-02-04 | 1/24 | 0.0417 | 183 |
| Corrupted | STALE | 2026-07-30 | 2022-03-21 | 4/23 | 0.1739 | 1599 |
| Repaired | STALE | 2026-08-03 | 2026-02-04 | 1/24 | 0.0417 | 183 |

Một điểm cần lưu ý là status đều là STALE, nhưng corrupted vẫn xấu hơn baseline rõ ràng. Bằng chứng nằm ở observed values: stale rows tăng từ 1 lên 4, stale ratio tăng từ 0.0417 lên 0.1739, và oldest published bị kéo lùi về 2022-03-21. Sau repair, các giá trị này quay lại đúng baseline.

## 8. Quyết định kỹ thuật quan trọng

Quyết định quan trọng nhất là **repair bằng cách rebuild từ raw snapshot**, không vá trực tiếp trên corrupted dataset.

| Nội dung | Phân tích |
| --- | --- |
| Bối cảnh | Corrupted dataset bị nhiều lỗi cùng lúc: thiếu records, duplicate rows, summary lỗi, title bị cắt, date stale |
| Phương án 1 | Viết rule-based repair để sửa từng lỗi trong corrupted dataset |
| Phương án 2 | Đọc lại `data/raw/crossref_records.json` và chạy lại `build_clean_dataframe` |
| Phương án chọn | Phương án 2 |
| Lý do | Raw snapshot là nguồn đáng tin cậy hơn corrupted dataset; rebuild giúp giữ cùng cleaning contract với baseline |
| Bằng chứng | Repaired rows = 24, quality PASS 10/11, metrics quay lại baseline 1.0000/1.0000/1.0000/5.0000 |

Cách này cũng tránh việc repair chỉ “đoán” lại dữ liệu đã mất. Với lỗi `drop_latest_records`, nếu document đã bị xóa khỏi corrupted dataset thì sửa tại chỗ không đủ đáng tin cậy; rebuild từ raw mới là cách phục hồi đúng.

## 9. Lỗi hoặc blocker đã xử lý

### Blocker kỹ thuật trong corruption

- Triệu chứng: Nếu sửa `title` hoặc `summary` nhưng không tính lại `text_for_embedding`, vector index có thể vẫn dùng nội dung cũ.
- Nguyên nhân gốc: `text_for_embedding` là cột derived được tạo từ metadata và summary.
- Cách xử lý: Sau mọi corruption step, rebuild `title_chars`, `summary_chars`, `text_for_embedding` cho toàn bộ DataFrame.
- Cách xác minh: Sau khi chạy corrupted index, metrics giảm rõ: `retrieval_hit_rate = 0.8000`, `mean_token_f1 = 0.7593`.
- Bài học: Khi pipeline có derived fields phục vụ embedding/model, mọi thay đổi ở source fields phải kéo theo việc rebuild derived fields.

### Blocker khi chạy project

- Triệu chứng ban đầu: Chạy `python script\run_phase1.py` bằng Python hệ thống bị lỗi `ModuleNotFoundError: No module named 'pipelines'`.
- Nguyên nhân: Project chưa được cài editable vào environment.
- Cách xử lý: Tạo `.venv`, nâng cấp pip, cài dependencies bằng `python -m pip install -e .`.
- Lỗi phụ: Lần cài đầu bị Windows `WinError 32` do file trong `langsmith` đang bị process giữ; chạy lại pip install lần hai thì thành công.
- Cách xác minh: Import được `datasets`, `chromadb`, `sentence_transformers`, `pipelines.phase1` và chạy thành công cả `run_phase1.py` lẫn `run_corruption_flow.py`.

## 10. Hiểu biết về luồng end-to-end

Dữ liệu đi từ Crossref API vào `data/raw/` dưới dạng raw response/raw records. Sau đó cleaning chuẩn hóa thành `data/clean/papers_clean.json`, tạo các trường như `paper_id`, `title`, `summary`, `published`, `age_days` và `text_for_embedding`. Từ cleaned dataset, pipeline build embedding bằng `sentence-transformers/all-MiniLM-L6-v2` và lưu vào ChromaDB. Evaluation set đông băng trong `data/eval/test_set.json` gồm 20 câu hỏi, mỗi câu có ground-truth document IDs để đo retrieval hit rate và answer quality.

Quality checks kiểm tra tính đầy đủ, duy nhất và hợp lệ của dataset, ví dụ null, duplicate, summary length, text_for_embedding. Freshness monitoring kiểm tra tính thời gian của dữ liệu qua `latest_published`, `oldest_published`, `stale_rows`, `age_days`. Hai nhóm signal này bổ sung cho nhau: quality bắt lỗi cấu trúc/nội dung, freshness bắt lỗi độ mới dữ liệu.

Phải dùng cùng test set cho baseline, corrupted và repaired vì nếu sinh lại test set trên corrupted dataset thì ground truth sẽ thay đổi theo dữ liệu lỗi. Khi đó không thể kết luận metric giảm là do corruption. Trong lần chạy này, cả ba trạng thái đều dùng 20 samples giống nhau, nên so sánh là công bằng.

Repair được xem là thành công vì dữ liệu repaired quay lại 24 rows, không còn critical quality failures, freshness quay về mức baseline, và 4 metrics agent đều phục hồi về baseline.

## 11. Kết luận cá nhân

Corruption ảnh hưởng mạnh nhất đến retrieval là `drop_latest_records`, vì nó xóa hẳn document khỏi corpus. Khi ground-truth document không còn trong ChromaDB collection, retriever không thể lấy đúng document dù agent hoặc LLM có tốt đến đâu. Điều này thể hiện qua `retrieval_hit_rate` giảm từ 1.0000 xuống 0.8000.

Các corruption liên quan đến `summary` và `published` ảnh hưởng rõ đến answer quality. Summary rỗng/noisy làm context kém chất lượng, còn stale publication date làm câu trả lời dạng date sai. Điều này kéo `mean_token_f1` xuống 0.7593 và `judge_accuracy` xuống 0.7500.

Repair thành công vì pipeline không vá từng lỗi trên corrupted data, mà rebuild từ raw snapshot đáng tin cậy. Sau repair, chất lượng agent quay lại baseline: `retrieval_hit_rate = 1.0000`, `mean_token_f1 = 1.0000`, `judge_accuracy = 1.0000`, `mean_judge_score = 5.0000`.

## 12. Điều học được và hướng cải thiện

Ba điều tôi học được:

1. Data observability chỉ có ý nghĩa khi corruption scenario đủ gần với lỗi production thật.
2. Không nên chỉ nhìn nhãn PASS/FAIL; cần đọc observed values như duplicate count, stale rows, max age days.
3. Với RAG, chất lượng dữ liệu là một phần trực tiếp của chất lượng agent; thiếu hoặc sai dữ liệu làm retrieval và answer quality giảm ngay.

Nếu có thêm thời gian, tôi sẽ mở rộng corruption runner để chạy nhiều seed và báo cáo trung bình cộng độ lệch của metrics. Như vậy nhóm có thể biết loại corruption nào gây tác động ổn định nhất, thay vì chỉ dựa trên một seed cố định.

## 13. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc Corruption & Repair của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module `corruption.py`.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc thành viên khác.

**Họ và tên:** Huỳnh Hoàng Việt  
**Ngày xác nhận:** 2026-08-06
