# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                                                                                                                                                  |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Họ và tên       | Trần Thị Thanh Tâm                                                                                                                                      |
| MSSV               | 2A202601267                                                                                                                                                |
| Khóa/Lớp         | K3                                                                                                                                                         |
| Tên nhóm         | B2                                                                                                                                                         |
| Vai trò chính    | Cleaning & test-set owner                                                                                                                                  |
| Repository         | [github.com/HuyhoangUK1234/K3_Day10_Data-Pipeline-Data-Observability.git](https://github.com/HuyhoangUK1234/K3_Day10_Data-Pipeline-Data-Observability.git)  |
| Ngày hoàn thành | 2026-08-06                                                                                                                                                 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable       | File/hàm phụ trách                                                                                          | Input nhận vào                          | Output bàn giao                                                  | Trạng thái |
| ------------------------ | -------------------------------------------------------------------------------------------------------------- | ----------------------------------------- | ----------------------------------------------------------------- | ------------ |
| Cleaning & data modeling | `src/ingestion/cleaning.py` — `build_clean_dataframe`, `build_text_for_embedding`, `compute_age_days` | `list[PaperRecord]` từ `crossref.py` | `data/clean/papers_clean.csv` + `.json` (24 dòng × 16 cột) | Hoàn thành |
| Evaluation set           | `src/evaluation/testset.py` — `build_test_set`, `_select_papers`                                        | Cleaned DataFrame                         | `data/eval/test_set.json` (20 câu hỏi)                        | Hoàn thành |

Phần việc của tôi nằm giữa hai đầu phụ thuộc: nhận `PaperRecord` từ owner ingestion, và bàn giao
schema cột cho owner observability (`quality.py` đọc `age_days`, `summary`, `title`), owner corruption
(`corruption.py` sửa các cột này rồi ghi lại), cùng phần index có sẵn (`index.py` đọc 9 cột cố định).

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động                                                                         | Thành viên/module được hỗ trợ     | Kết quả                                                                       |
| ------------------------------------------------------------------------------------ | ---------------------------------------- | ------------------------------------------------------------------------------- |
| Export`build_text_for_embedding` thành hàm public để corruption flow gọi lại | Owner corruption (`corruption.py:161`) | Corruption thực sự đến được vector store; nếu không, metrics đứng im |
| Chuẩn hoá ngày phát hành để freshness có ý nghĩa                           | Owner observability (`quality.py`)     | `future_dated_rows = 0`, dải tuổi 3–183 ngày                              |
|                                                                                      |                                          |                                                                                 |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện                        | File/hàm/artifact liên quan             | Kết quả bàn giao              | Cách xác minh                                                                                   |
| -------------------------------------------------- | ----------------------------------------- | -------------------------------- | ------------------------------------------------------------------------------------------------- |
| Định nghĩa contract 16 cột cho cleaned dataset | `cleaning.py::CLEAN_COLUMNS`            | `papers_clean.json`            | `python -c "import json; print(len(json.load(open('data/clean/papers_clean.json'))[0]))"` → 16 |
| Lọc record không hợp lệ và dedupe kép        | `cleaning.py::build_clean_dataframe`    | 24 raw → 24 clean, 0 trùng     | `paper_id_unique` và `title_unique` PASS trong `data/quality/baseline_quality.json`        |
| Ghép`text_for_embedding` từ 5 trường         | `cleaning.py::build_text_for_embedding` | Cột`text_for_embedding`       | `text_for_embedding_not_empty` PASS (0 vi phạm)                                                |
| Tính`age_days` có dấu                         | `cleaning.py::compute_age_days`         | Cột`age_days`                 | `freshness_report.json`: min 3, median 21.5, max 183, `future_dated_rows` = 0                 |
| Sinh 20 câu hỏi 4 loại có ground truth         | `testset.py::build_test_set`            | `data/eval/test_set.json`      | `python script/run_phase1.py` → `retrieval_hit_rate` = 1.0000 ở baseline                    |
| Chọn paper trải đều corpus                     | `testset.py::_select_papers`            | 5 paper ở index 0, 4, 9, 14, 19 | Corruption xoá 3 bài mới nhất chỉ ảnh hưởng 4/20 câu, không phải 12/20                 |

**Một output cụ thể phần việc của tôi tạo ra:**

`data/clean/papers_clean.json` — 24 dòng × 16 cột. Đây là artifact mà **cả ba trạng thái** của bài lab
đều xuất phát từ đó: baseline index trực tiếp từ nó, corrupted là bản đã bị phá của nó, và repaired
được dựng lại bằng đúng hàm `build_clean_dataframe` của tôi từ raw snapshot. Bằng chứng repair đúng
là `papers_clean_repaired.json` giống `papers_clean.json` **byte-for-byte** (cùng 104 493 bytes) —
điều này chỉ đạt được khi hàm cleaning tất định, không phụ thuộc thứ tự dict hay random.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Hai vấn đề tách biệt.

**Cleaning:** Crossref trả về dữ liệu thô không dùng trực tiếp được — abstract là JATS XML bị escape,
tác giả nằm rải trong `given`/`family`, ngày tháng ở 5 trường khác nhau và có thể forward-date, nhiều
record thiếu abstract hoặc trùng nhau. Cần biến nó thành một bảng có schema ổn định mà 4 module khác
đọc được, đồng thời phải tất định để repair tái tạo được y hệt.

**Test set:** cần bộ câu hỏi có ground truth để đo chất lượng agent. Nhưng ground truth phải khớp
chính xác cách `qa.py` trả lời, nếu không metric sẽ đo sai — thấp không phải vì agent kém mà vì câu
hỏi viết sai.

### Cách triển khai

**Cleaning — 4 tầng lọc trong một vòng lặp:**

1. Chuẩn hoá text (`normalize_whitespace`), DOI viết thường làm `paper_id`, cắt ngày về 10 ký tự.
2. Loại record không dùng được: thiếu DOI, title < 10 ký tự, summary < 80 ký tự, ngày không parse
   được. Ngưỡng 80 ký tự vì abstract ngắn hơn thế thường là rác kiểu "Abstract not available".
3. Dedupe **kép**: theo `paper_id` và theo `title.lower()`. Trùng DOI là lỗi loader; trùng title mà
   khác DOI là preprint + bản chính thức của cùng một bài — cả hai đều làm nhiễu retrieval.
4. Điền mặc định (`"Unknown"`, `"Uncategorized"`) thay vì để rỗng, vì ChromaDB metadata không nhận
   `None` và ground truth rỗng sẽ làm `_token_f1` trả 0 vô lý.

Cuối cùng sort ngày giảm dần. Đây **không phải thẩm mỹ**: corruption bước 1 xoá `df.head(3)` =
3 bài mới nhất, nên thứ tự này quyết định corruption đánh vào đâu.

**`text_for_embedding` ghép 5 trường** thay vì chỉ abstract:

```
Title: ... / Authors: ... / Categories: ... / Published: ... / Summary: ...
```

Vì test set có câu hỏi về tác giả và ngày. Nếu chỉ embed abstract, câu "Who authored the paper titled
X?" không có tín hiệu nào để retrieval bám vào.

**Test set — template phải khớp từ khoá của `qa.py`.** Đọc `retrieval/qa.py::_extract_answer` thấy nó
trả lời bằng **trích xuất theo từ khoá**, không sinh văn bản:

| Câu hỏi chứa     | `qa.py` trả về          |
| ------------------- | --------------------------- |
| `who authored`    | `authors_joined`          |
| `when was`        | `published`               |
| `what categories` | `categories_joined`       |
| còn lại           | `first_sentence(summary)` |

Nên `QUESTION_TEMPLATES` phải chứa đúng các cụm đó. Đổi "Who authored" thành "Who wrote" là câu hỏi
rơi xuống nhánh mặc định và `token_f1` tụt về gần 0.

Thêm nữa, `qa.py:33` bắt title trong dấu nháy đơn bằng `re.search(r"'([^']+)'", question)` để kích
hoạt exact lookup. Nên title phải nằm trong `'...'`, và paper có dấu nháy trong tiêu đề phải bị loại
(`_select_papers` dòng 25) vì nó phá regex.

**`_select_papers` trải đều** thay vì `head(5)`: `step = len(records)/wanted` → chọn index 0, 4, 9,
14, 19. Nếu lấy 5 bài đầu thì corruption xoá 3 bài mới nhất sẽ giết 3/5 paper = 60% test set, delta
bị thổi phồng và không đo được gì.

### Input, output và contract

| Thành phần                   | Mô tả                                                                                                                                                                                                                               |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Input                          | `cleaning`: `list[PaperRecord]` (11 trường) + `run_date`. `testset`: cleaned DataFrame                                                                                                                                      |
| Output                         | `cleaning`: DataFrame 16 cột theo `CLEAN_COLUMNS`. `testset`: `list[dict]` với `id`, `question_type`, `question`, `ground_truth`, `ground_truth_doc_ids`                                                          |
| Module phụ thuộc             | `ingestion/crossref.py` (schema `PaperRecord`), `core/utils.py` (`normalize_whitespace`, `compact_join`, `first_sentence`)                                                                                                |
| Module sử dụng output        | `retrieval/index.py` (9 cột), `observability/quality.py` (`age_days`, `summary`, `title`), `ingestion/corruption.py` (sửa cột rồi gọi lại `build_text_for_embedding`), `evaluation/metrics.py` (đọc test set) |
| Điều kiện lỗi cần xử lý | DataFrame rỗng → trả về df có đủ cột thay vì`KeyError`; < 4 document → `raise ValueError`; test set rỗng do thiếu cột → `raise` thay vì để `statistics.mean()` chết với thông báo khó hiểu             |

### Cách xác minh

```bash
python script/run_phase1.py
python -c "import json; d=json.load(open('data/clean/papers_clean.json')); print(len(d),'rows', len(d[0]),'cols')"
python -c "import json; t=json.load(open('data/eval/test_set.json')); print(len(t),'questions', sorted({q['question_type'] for q in t}))"
```

- **Kết quả mong đợi:** 24 dòng × 16 cột; 20 câu hỏi thuộc 4 loại; `retrieval_hit_rate` = 1.0 ở
  baseline (nếu thấp hơn nghĩa là ground truth không khớp cách `qa.py` trả lời).
- **Kết quả thực tế:** đúng như trên — 24 rows / 16 cols, 20 câu hỏi
  `['authors','categories','date','summary']`, `retrieval_hit_rate` = 1.0000, `mean_token_f1` = 1.0000.
- **Artifact/log:** `data/clean/papers_clean.json`, `data/eval/test_set.json`,
  `data/results/baseline_metrics.json`, `data/quality/baseline_quality.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** `text_for_embedding` là cột được embed. Câu hỏi: viết logic ghép nó inline trong
  `build_clean_dataframe`, hay tách thành hàm public riêng?
- **Các phương án đã cân nhắc:**
  1. Inline trong vòng lặp cleaning — ngắn gọn, ít API bề mặt.
  2. Tách thành hàm public `build_text_for_embedding(row: dict) -> str` — thêm một hàm để bảo trì.
  3. Để corruption flow tự viết lại logic ghép của riêng nó — tách biệt hoàn toàn, nhưng nhân đôi code.
- **Phương án đã chọn:** phương án 2.
- **Lý do:** corruption flow sửa `summary`, `title`, `published` rồi phải **dựng lại**
  `text_for_embedding`. Với phương án 1, corruption sẽ để lại cột cũ → embedding không đổi →
  corruption không bao giờ chạm tới vector store → mọi metric đứng im và cả bài lab vô nghĩa. Với
  phương án 3, hai bản logic sẽ trôi khỏi nhau và repaired dataset không còn giống baseline
  byte-for-byte, làm mất bằng chứng repair đúng.
- **Bằng chứng quyết định phù hợp:** sau khi corruption gọi lại hàm này
  (`corruption.py:161`), `mean_token_f1` giảm 1.0000 → 0.7593 và `retrieval_hit_rate` giảm
  1.0000 → 0.8000. Nếu cột không được dựng lại, cả hai đã giữ nguyên 1.0000. Đồng thời
  `papers_clean_repaired.json` khớp `papers_clean.json` byte-for-byte vì cả hai đi qua đúng một hàm.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** không có exception. `data/quality/freshness_report.json` ghi
  `"latest_published": "2028-06-15"` nhưng `"max_age_days": 0` và `"median_age_days": 0.0` — toàn bộ
  24 bài đều "0 ngày tuổi" trong khi ngày xuất bản nằm ở tương lai. Báo cáo tự mâu thuẫn.
- **Lệnh hoặc bước tái hiện:** `python script/run_phase1.py` rồi mở
  `data/quality/freshness_report.json` và `data/reports/phase1_report.md` mục 4.
- **Nguyên nhân gốc:** hai lỗi chồng nhau. (1) Tạp chí forward-date số báo — một bài đăng online năm
  2026 mang `issued = 2028`; bản đầu của tôi lấy thẳng trường `published`/`issued` nên nhận ngày
  tương lai. (2) `compute_age_days` viết `max((run_date - published_date).days, 0)`, nên tuổi âm bị
  ép về 0 và **giấu hoàn toàn** vấn đề (1) sau một con số hợp lệ giả.
- **Cách xử lý:** ba thay đổi. Trong `crossref.py::_published_date`, chọn **ngày gần nhất đã thực sự
  xảy ra** trong `published-online / published / issued / published-print / created` thay vì lấy
  trường đầu tiên tìm thấy. Trong `cleaning.py::compute_age_days`, bỏ `max(..., 0)` để tuổi có dấu, và
  trả `None` thay vì sentinel `-1` khi không parse được (vì `-1` sẽ lẫn với tuổi âm thật). Bàn giao
  cho owner observability thêm check `published_not_in_future` để lộ ra nếu tái diễn.
- **Cách xác minh sau khi sửa:** `REFRESH_SOURCE=1 python script/run_phase1.py` → `freshness_report.json`
  cho `future_dated_rows` = 0, `latest_published` = 2026-08-03, `oldest_published` = 2026-02-04,
  `age_days` 3–183 ngày. Dải ngày giờ nằm hoàn toàn trong quá khứ và nhất quán với `max_age_days`.
- **Điều học được:** một phép "làm sạch" phòng thủ như `max(x, 0)` có thể **che mất** lỗi dữ liệu thay
  vì xử lý nó. Giá trị bất thường (tuổi âm) chính là tín hiệu quan sát được; ép nó về giá trị hợp lệ
  là làm mù luôn tầng observability ở phía sau. Nguyên tắc rút ra: cleaning nên **loại bỏ hoặc đánh
  dấu** dữ liệu sai, không nên **im lặng sửa** nó thành trông-có-vẻ-đúng.

## 7. Hiểu biết về luồng end-to-end

**Câu trả lời:**

**1. Dữ liệu đi từ Crossref đến vector index thế nào?** `crossref.py` gọi `/works` với query + filter
`from-pub-date` và `has-abstract:true`, xin dư 72 rows (vì parse sẽ loại bớt), retry backoff trên
429/503, lưu payload thô vào `data/raw/crossref_response.json` rồi parse thành `PaperRecord` lưu vào
`crossref_records.json`. `cleaning.py` nhận list đó, lọc/dedupe/chuẩn hoá và ghép `text_for_embedding`,
xuất ra `papers_clean.json`. `index.py` embed cột đó bằng MiniLM-L6-v2 và nạp vào ChromaDB với
record ID `{paper_id}::{index}`.

**2. Evaluation set và ground-truth doc IDs đo retrieval/answer quality ra sao?** Mỗi sample mang
`ground_truth_doc_ids = [paper_id]`. `metrics.py` tính `retrieval_hit` = có ít nhất một trong top-4
document trả về khớp danh sách đó — đo **retrieval**. Riêng `token_f1` so câu trả lời với
`ground_truth` — đo **answer**. Tách hai chỉ số này quan trọng: retrieval có thể đúng mà câu trả lời
vẫn sai (khi summary bị blank), và đó chính là điều corruption phơi bày.

**3. Quality checks khác freshness monitoring ở điểm nào?** Quality checks trả lời "dữ liệu có **đúng**
không" — thiếu trường, trùng ID, summary quá ngắn. Freshness trả lời "dữ liệu có **mới** không" —
`age_days` so với ngưỡng 180. Một dataset có thể pass toàn bộ quality mà vẫn stale, và ngược lại.
Nhóm còn tách `severity`: freshness là `warning` chứ không phải `critical`, vì nguồn chậm cập nhật
không phải vi phạm schema.

**4. Vì sao phải dùng cùng test set cho cả ba trạng thái?** Nếu sinh lại test set từ dataset corrupted
thì ground truth được tạo từ chính dữ liệu sai — agent sẽ "đúng" với dữ liệu lỗi và metric không giảm.
Phép so sánh mất hoàn toàn ý nghĩa. Nên `phase1.py` chỉ sinh test set khi file chưa tồn tại hoặc có
`REFRESH_TEST_SET=1`; cả ba lần `evaluate_pipeline` đều đọc cùng đường dẫn `data/eval/test_set.json`.

**5. Repair thành công dựa trên artifact và metric nào?** Ba bằng chứng cùng lúc: (a)
`papers_clean_repaired.json` giống `papers_clean.json` byte-for-byte; (b) `repaired_quality.json` quay
lại PASS 10/11 với 0 critical failure; (c) cả 4 metric trong `repaired_metrics.json` trở về đúng mức
baseline. Quan trọng: repair đọc lại `data/raw/crossref_records.json` — snapshot mà corruption không
chạm tới — chứ không vá dữ liệu hỏng.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal          |     Baseline |           Corrupted |     Repaired | Nhận xét của cá nhân                                                                  |
| ---------------------- | -----------: | ------------------: | -----------: | ------------------------------------------------------------------------------------------ |
| `retrieval_hit_rate` |       1.0000 |              0.8000 |       1.0000 | 4/20 câu mất document ground truth — đúng 1 paper trong test set bị xoá             |
| `mean_token_f1`      |       1.0000 |              0.7593 |       1.0000 | Giảm mạnh hơn hit rate: retrieval còn đúng nhưng nội dung đã hỏng               |
| `judge_accuracy`     |       1.0000 |              0.7500 |       1.0000 | **Heuristic fallback**, chưa có LLM provider lúc chạy                            |
| `mean_judge_score`   |       5.0000 |              4.0000 |       5.0000 | Như trên                                                                                 |
| Quality checks         |   PASS 10/11 | **FAIL 6/11** |   PASS 10/11 | 3 critical failure mới:`paper_id_unique`, `summary_not_empty`, `summary_min_length` |
| Freshness status       | STALE (1/24) |        STALE (4/23) | STALE (1/24) | Nhãn không đổi nhưng số liệu đổi rõ — xem ghi chú bên dưới                  |

### Kết luận từ số liệu

1. **Xoá 3 bản ghi mới nhất** (`corruption_log.json`, bước `drop_latest_records`) → 3 document biến
   mất khỏi collection `papers-corrupted` → 4/20 câu có `retrieval_hit = false` trong
   `corrupted_answers.json` → `retrieval_hit_rate` 1.0000 → 0.8000.
2. **Repair từ raw snapshot** → `repaired_quality.json` về PASS 10/11 với 0 critical failure và
   `stale_rows` về 1/24 → cả 4 metric trong `repaired_metrics.json` phục hồi 100% về mức baseline.

**Corruption nào ảnh hưởng rõ nhất?** Xét theo từng metric thì khác nhau. Với `retrieval_hit_rate`,
**xoá bản ghi** là thủ phạm duy nhất — 3 document không còn trong index thì không cách nào retrieve
được. Nhưng với `mean_token_f1`, **blank + noise summary** mới nặng hơn: token F1 giảm 0.2407 trong
khi hit rate chỉ giảm 0.2000, nghĩa là có câu retrieval **vẫn đúng** nhưng trả lời sai vì nội dung đã
hỏng. Đây là kịch bản nguy hiểm nhất trong thực tế: hệ thống trông vẫn "tìm đúng tài liệu" nên không
ai nghi ngờ, mà câu trả lời lại sai.

**Kết quả nào khác kỳ vọng?** Tôi tưởng freshness status sẽ chuyển từ FRESH sang STALE và đó sẽ là
bằng chứng đẹp nhất. Thực tế baseline **đã** STALE sẵn: có 1 bài `age_days` = 183, vượt ngưỡng 180
đúng 3 ngày. Giả thuyết ban đầu của tôi là bug trong `compute_age_days`, nhưng kiểm tra bằng
`python -c "...sort by age_days..."` thì thấy bài đó có `published` = 2026-02-04 thật — filter Crossref
`from-pub-date` áp lên ngày pub của Crossref (có thể forward-date), còn tôi quy về ngày thực tế đã
phát hành nên bài này rơi ra ngoài cửa sổ 180 ngày. Đây là phát hiện đúng của quality layer, không
phải lỗi code. Kết luận rút ra: bằng chứng cho tác động của corruption phải đọc ở **số liệu**
(`stale_rows` 1 → 4 → 1, `oldest_published` 2026-02-04 → 2022-03-21 → 2026-02-04), không phải ở nhãn
status.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. **Về data pipeline:** schema cột không phải chi tiết nội bộ mà là **hợp đồng** giữa các module.
   Trong bài này 4 module đọc cột do tôi định nghĩa; đổi tên một cột là gãy dây chuyền. Tương tự,
   những cột **dẫn xuất** như `text_for_embedding` phải có một hàm duy nhất sinh ra nó, nếu không mọi
   thao tác sửa dữ liệu ở downstream sẽ để lại trạng thái không nhất quán.
2. **Về data quality/observability:** làm sạch phòng thủ có thể che mất lỗi. `max(age_days, 0)` biến
   một dữ liệu bất thường thành con số hợp lệ trông rất bình thường, và tầng observability phía sau
   mất luôn khả năng phát hiện. Cleaning nên loại bỏ hoặc đánh dấu, không nên im lặng sửa.
3. **Về ảnh hưởng của data đến RAG agent:** chất lượng dữ liệu tác động qua **hai kênh độc lập** —
   retrieval (document còn tồn tại và tìm được không) và generation (nội dung document có đúng không).
   Số liệu cho thấy kênh thứ hai âm thầm hơn: `mean_token_f1` giảm 0.2407 trong khi
   `retrieval_hit_rate` chỉ giảm 0.2000, tức là có trường hợp tìm đúng tài liệu mà vẫn trả lời sai.

### Nếu có thêm thời gian

Test set hiện tại có điểm yếu tôi tự nhận: `ground_truth` sinh từ **đúng những trường mà `qa.py`
trích xuất ra**, tạo thành vòng lặp khép kín, nên baseline chạm trần 1.0000 theo thiết kế chứ không
phải vì agent giỏi. Tôi sẽ thêm một nhóm câu hỏi **paraphrase** (diễn đạt lại, không chứa từ khoá
`who authored`/`when was`) và **multi-hop** (so sánh hai paper), rồi báo cáo hai bộ metric tách riêng.
Cách đo cải thiện: nếu baseline trên nhóm câu hỏi mới thấp hơn 1.0000 rõ rệt thì test set đã thoát
khỏi vòng lặp khép kín và bắt đầu đo được năng lực thật; đồng thời so delta corruption giữa hai nhóm
để biết loại câu hỏi nào nhạy hơn với chất lượng dữ liệu.

## 10. Cam kết của thành viên

- [X] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [X] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [X] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [X] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [X] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [X] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên: Trần Thị Thanh Tâm**
**Ngày xác nhận:** 2026/08/06
