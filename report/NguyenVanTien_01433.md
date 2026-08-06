# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                                                                 |
| ------------------ | ------------------------------------------------------------------------- |
| Họ và tên       | Nguyễn Văn Tiến                                                        |
| MSSV               | 2A202601433                                                               |
| Khóa/Lớp         | K3                                                                        |
| Tên nhóm         | B2                                                                        |
| Vai trò chính    | Thành viên 5 — Pipeline integration & evidence owner                   |
| Repository         | https://github.com/VinUni-AI20k/K3_Day10_Data-Pipeline-Data-Observability |
| Ngày hoàn thành | 2026-08-06                                                                |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable                           | File/hàm phụ trách                                                                       | Input nhận vào                                              | Output bàn giao                                                                    | Trạng thái |
| -------------------------------------------- | ------------------------------------------------------------------------------------------- | ------------------------------------------------------------- | ----------------------------------------------------------------------------------- | ------------ |
| Verification layer                           | `src/pipelines/verification.py`, `script/verify_artifacts.py` (16 check, exit code 0/1) | Toàn bộ artifact trong`data/`, `report/group_report.md` | `data/reports/verification_report.json`, `report/evidence/verify_artifacts.log` | Hoàn thành |
| Tái hiện pipeline end-to-end               | `script/run_phase1.py`, `script/run_corruption_flow.py`                                 | Repo ở commit`097200d`, `.venv` sạch                    | `report/evidence/run_phase1.log`, `report/evidence/run_corruption_flow.log`     | Hoàn thành |
| Đối chiếu report với artifact            | `report/group_report.md` mục 7, 8, 10                                                    | Metrics/quality/freshness JSON                                | Xác nhận 12 số liệu công bố khớp`data/results/`                            | Hoàn thành |
| Kiểm chứng chính verifier (negative test) | `report/group_report.md` (sửa tạm rồi hoàn tác)                                      | Một giá trị sai cố ý                                     | `report/evidence/verify_negative_test.log`                                        | Hoàn thành |

**Phân định ownership cho rõ ràng:** bảng phân công trong `report/README.md` giao cho Thành viên 5 hai file `src/pipelines/phase1.py` và `src/pipelines/corruption_flow.py`. Hai file đó đã được nhóm hoàn thành trước khi tôi vào việc, nên tôi **không nhận ownership code của chúng**. Phần tôi trực tiếp thực hiện là nửa còn lại của vai trò mà `report/README.md` mô tả: *"chịu trách nhiệm kỹ thuật cho orchestration, reproducibility và kiểm tra sự nhất quán giữa report với artifact"* — cụ thể là lớp verification, việc tái hiện toàn bộ flow trên một máy khác, và việc đối chiếu từng con số trong báo cáo với artifact thật.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động                                             | Thành viên/module được hỗ trợ | Kết quả                                                                                                                    |
| -------------------------------------------------------- | ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------- |
| Kiểm tra chéo toàn bộ metrics của nhóm             | Module evaluation và observability  | 15/16 check PASS, 0 critical failure —`data/reports/verification_report.json`                                             |
| Phát hiện artifact không khả chuyển giữa các máy | Module embedding/index               | 3 file trong`data/embeddings/` lưu absolute path; đã báo dưới dạng WARN, chưa sửa vì thuộc module người khác |
| Bổ sung lệnh xác minh vào tài liệu nhóm           | `report/group_report.md`           | Thêm`python script/verify_artifacts.py` vào mục "Cách tái hiện kết quả"                                            |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện                             | File/hàm/artifact liên quan                | Kết quả bàn giao                                                      | Cách xác minh                                                                  |
| ------------------------------------------------------- | -------------------------------------------- | ------------------------------------------------------------------------ | -------------------------------------------------------------------------------- |
| Chạy lại pha 1 trên máy độc lập từ raw snapshot | `script/run_phase1.py`                     | exit 0; 24 raw → 24 clean rows;`retrieval_hit_rate` 1.0000            | `report/evidence/run_phase1.log`                                               |
| Chạy lại pha 2 và so sánh 3 trạng thái            | `script/run_corruption_flow.py`            | exit 0; 24 → 23 dòng; corrupted 0.8000 / repaired 1.0000               | `report/evidence/run_corruption_flow.log`                                      |
| Viết verifier 16 check có exit code                   | `src/pipelines/verification.py`            | 15 PASS, 1 WARN, 0 FAIL                                                  | `python script/verify_artifacts.py`; `data/reports/verification_report.json` |
| Chứng minh verifier thật sự bắt lỗi                | `report/evidence/verify_negative_test.log` | Tiêm sai một số → exit 1 kèm thông báo chỉ đúng chỗ           | So`verify_artifacts.log` (exit 0) với `verify_negative_test.log` (exit 1)   |
| So artifact chạy lại với artifact nhóm đã commit  | `git diff` trên `data/`                 | Chỉ khác`generated_at` và `persist_path`; mọi metric giống hệt | `git diff data/results/baseline_metrics.json` không có thay đổi            |

Một output cụ thể mà phần việc của tôi tạo ra:

`data/reports/verification_report.json` — file máy đọc được liệt kê 16 check kèm trạng thái và chi tiết. Trước đó `report/README.md` mục 7 ghi rõ *"Repo hiện không cung cấp test hoặc grader tự động làm tiêu chí pass cuối cùng"*, nên việc xác minh phụ thuộc hoàn toàn vào người đọc dò tay. File này biến bước dò tay đó thành một lệnh có exit code, dùng được cả trong CI.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Hai flow của nhóm chạy exit 0 không chứng minh được bài làm đúng. Một pipeline có thể chạy trót lọt mà vẫn sai theo ba cách mà bản thân nó không phát hiện được:

1. Test set bị sinh lại từ dataset đã hỏng, khiến ground truth lấy từ chính dữ liệu lỗi và mọi so sánh mất nghĩa.
2. Repair "sửa" trên dataset hỏng thay vì tái tạo từ raw, tức là che lỗi chứ không phục hồi.
3. Báo cáo ghi một con số, artifact chứa con số khác — người chấm mở file JSON ra là lệch.

Không có cơ chế nào trong `phase1.py` hay `corruption_flow.py` bắt được ba trường hợp này, vì chúng là ràng buộc *giữa* các lần chạy và *giữa* code với tài liệu, không nằm trong một lần chạy đơn lẻ.

### Cách triển khai

`src/pipelines/verification.py` gom 16 assertion thành 9 nhóm. Vài check đáng nói:

**Frozen test set (`check_frozen_test_set`).** Không so kích thước file mà lấy "vân tay" của evaluation set: tập các cặp `(id, question)` đã sắp xếp, rồi so vân tay đó giữa `test_set.json` và cả ba file `*_answers.json`. So theo nội dung câu hỏi nên vẫn bắt được trường hợp file có đúng 20 câu nhưng nội dung đã đổi.

**Repair fidelity (`check_repair_fidelity`).** So sánh cấu trúc dữ liệu đã parse của `papers_clean.json` và `papers_clean_repaired.json`. Nếu repair thật sự chạy lại `build_clean_dataframe` trên raw snapshot thì hai file phải bằng nhau tuyệt đối; chỉ cần chúng lệch một dòng là repair đã đụng vào dataset hỏng.

**Report ↔ artifact (`check_report_matches_artifacts`).** Đọc `group_report.md`, dò các dòng bảng Markdown bắt đầu bằng tên metric, rồi so ba số đầu tiên với ba file metrics JSON, sai số cho phép 1e-4. Điểm cần xử lý: mỗi tên metric xuất hiện ở nhiều bảng trong báo cáo, nên hàm `_markdown_metric_row` duyệt toàn bộ dòng khớp và chỉ giữ dòng đầu tiên có ba ô đầu đều là số — đó mới là bảng so sánh ba trạng thái.

**Phân biệt FAIL và WARN.** Tôi giữ đúng quy ước mà module quality của nhóm đã dùng: chỉ những vi phạm phá vỡ tính đúng đắn của bài làm mới là critical và làm exit code khác 0. Việc artifact lưu absolute path là vấn đề khả chuyển, không phải sai kết quả, nên nó ra WARN.

Verifier dùng `load_settings()` từ `src/core/config.py` để lấy đường dẫn, không hard-code đường dẫn nào — đúng contract chung ghi ở `report/README.md` mục 6.

### Input, output và contract

| Thành phần                   | Mô tả                                                                                                                                         |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Input                          | Toàn bộ`data/` (raw, clean, embeddings, eval, results, quality, reports) và `report/group_report.md`                                     |
| Output                         | `data/reports/verification_report.json`; stdout dạng `[PASS]/[FAIL]/[WARN]`; exit code 0 khi không có critical failure, 1 khi có        |
| Module phụ thuộc             | `core.config.load_settings` (đường dẫn), `core.utils.read_json`, `pipelines.common.step` (định dạng in)                            |
| Module sử dụng output        | Không module nào — verifier là lá của đồ thị phụ thuộc, nên thêm nó không thể làm hỏng flow của các thành viên khác      |
| Điều kiện lỗi cần xử lý | Artifact thiếu (báo FAIL thay vì ném exception); ô bảng Markdown không phải số; console Windows không in được ký tự tiếng Việt |

### Cách xác minh

```powershell
python script/run_phase1.py
python script/run_corruption_flow.py
python script/verify_artifacts.py
```

- **Kết quả mong đợi:** ba lệnh cùng exit 0; verifier báo 0 critical failure và ghi `verification_report.json`.
- **Kết quả thực tế:** exit 0 / 0 / 0. Verifier: **15/16 check PASS, 0 FAIL, 1 WARN**. Warning là `artifacts_are_portable`.
- **Artifact/log:** `report/evidence/run_phase1.log`, `report/evidence/run_corruption_flow.log`, `report/evidence/verify_artifacts.log`, `data/reports/verification_report.json`. Không file nào chứa secret; verifier có sẵn một check quét pattern API key trên `report/` và `data/reports/`.

Về reproducibility: tôi chạy lại toàn bộ trên máy của mình rồi `git diff` thư mục `data/` so với artifact nhóm đã commit. Khác biệt duy nhất là trường `generated_at` và `persist_path`. Riêng `data/results/baseline_metrics.json`, `corrupted_metrics.json`, `repaired_metrics.json` **không xuất hiện trong `git diff`** — tức là byte-for-byte giống hệt bản nhóm nộp. Đây là bằng chứng mạnh nhất cho tính tái hiện: cùng raw snapshot và cùng seed thì cho ra cùng con số, trên một máy khác.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** cần chứng minh bài làm đúng, trong khi nhóm đã code xong và tôi không nên sửa module của người khác.
- **Các phương án đã cân nhắc:**
  1. Viết unit test cho từng module (`pytest` trên `cleaning.py`, `quality.py`, ...).
  2. Viết một verifier chạy trên artifact đầu ra, tách rời khỏi code các module.
  3. Chỉ đọc artifact bằng tay và ghi nhận xét vào báo cáo.
- **Phương án đã chọn:** phương án 2.
- **Lý do:** unit test kiểm tra *hàm*, nhưng ba rủi ro thật của bài lab này đều là ràng buộc *giữa các lần chạy* — cùng test set cho ba trạng thái, repaired phải tái tạo từ raw, báo cáo phải khớp artifact. Không unit test nào của một module đơn lẻ bắt được chúng. Verifier trên artifact bắt được cả ba, lại không import gì từ `cleaning.py`/`quality.py` nên không khoá chữ ký hàm của các thành viên khác — họ vẫn refactor được mà không làm gãy test của tôi. Phương án 3 bị loại vì không lặp lại được và không có exit code.
- **Bằng chứng quyết định phù hợp:** verifier phát hiện được một vấn đề thật mà cả hai flow chạy exit 0 vẫn bỏ qua — 3 file embedding manifest lưu absolute path của máy người chạy. Ngoài ra negative test cho thấy nó bắt đúng sai lệch report/artifact.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:**

```text
UnicodeEncodeError: 'charmap' codec can't encode character 'ả' in position 69: character maps to <undefined>
```

- **Lệnh tái hiện:** `python script/verify_artifacts.py` trên Windows PowerShell, ở lần chạy đầu tiên của verifier.
- **Nguyên nhân gốc:** hai lỗi chồng lên nhau. Lỗi hiển thị là console Windows dùng codepage cp1252, không mã hoá được ký tự tiếng Việt. Nhưng lý do chuỗi tiếng Việt lọt vào thông báo lỗi mới là gốc: hàm dò bảng Markdown của tôi dùng `re.search`, chỉ lấy dòng khớp **đầu tiên**. Tên `retrieval_hit_rate` xuất hiện sớm hơn ở bảng "Baseline metrics" (mục 7) — bảng đó chỉ có 2 cột và ô thứ ba là câu diễn giải tiếng Việt. Verifier đọc nhầm bảng, cố ép câu tiếng Việt thành số, rồi in câu đó ra trong thông báo lỗi.
- **Cách xử lý:** đổi `re.search` thành `re.finditer` và chỉ chấp nhận dòng có ba ô đầu đều parse được thành `float`, tức là bảng so sánh ba trạng thái. Thêm `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` ở đầu `main()` để console không chết vì tiếng Việt.
- **Cách xác minh sau khi sửa:** chạy lại → exit 0, `[PASS] report_matches_artifacts: 12 reported numbers match data/results/`. Sau đó tôi tiêm một giá trị sai (`mean_token_f1` corrupted đổi 0.7593 thành 0.9100) và chạy lại: exit 1 kèm `report says 0.9100, artifact says 0.7593`, đúng metric đúng trạng thái. Đã hoàn tác bằng `git checkout -- report/group_report.md`.
- **Điều học được:** một verifier chưa từng fail thì chưa chứng minh được gì. Phải cố ý làm nó fail một lần mới biết nó đang thật sự kiểm tra. Bài học thứ hai: khi parse tài liệu, đừng nhận dòng khớp đầu tiên — hãy nhận dòng khớp *đúng hình dạng* mình cần.

## 7. Hiểu biết về luồng end-to-end

**1. Dữ liệu đi từ Crossref đến vector index như thế nào?**

`crossref.py` gọi `/works` với query và filter `from-pub-date`, có retry/backoff, lưu nguyên response vào `data/raw/crossref_response.json` và bản đã parse vào `crossref_records.json`. `cleaning.py` nhận list record đó, bỏ bản ghi thiếu DOI/title/abstract hợp lệ, normalize whitespace và JATS entity, dedupe theo DOI và title, tính `age_days` có dấu, rồi ghép 5 trường thành `text_for_embedding`. Chỉ chuỗi này được embed bằng `all-MiniLM-L6-v2` và nạp vào ChromaDB. Điểm tôi thấy quan trọng nhất khi kiểm tra tích hợp: `build_text_for_embedding` phải được gọi lại sau mọi thao tác sửa dữ liệu, nếu không thì corruption sẽ nằm trong CSV mà không bao giờ đến được vector store, và cả pha 2 sẽ đo ra 0 thay đổi.

**2. Evaluation set và ground-truth document IDs dùng để đo retrieval/answer quality ra sao?**

`testset.py` sinh 20 câu hỏi từ 5 paper × 4 loại (`summary`, `authors`, `date`, `categories`). Mỗi câu mang theo `ground_truth` (câu trả lời đúng) và `ground_truth_doc_ids` (DOI của paper sinh ra nó). Hai thứ đó đo hai tầng khác nhau: `ground_truth_doc_ids` so với `retrieved_doc_ids` cho ra `retrieval_hit_rate` — tầng tìm kiếm; `ground_truth` so với `answer` cho ra `token_f1` và điểm judge — tầng trả lời. Tách hai tầng là cần thiết, vì retrieval đúng mà trả lời sai là một loại hỏng hoàn toàn khác với retrieval sai.

**3. Quality checks khác freshness monitoring ở điểm nào?**

Quality check hỏi "dữ liệu này có hợp lệ không" — thiếu trường, trùng khoá, title quá ngắn, summary rỗng. Đó là thuộc tính nội tại của dataset, đúng/sai rõ ràng, nên vi phạm ở mức critical thì chặn pipeline. Freshness hỏi "dữ liệu này còn mới không" — một tín hiệu về *nguồn*, không phải về schema. Dataset baseline của nhóm có 1 dòng 183 ngày tuổi, vượt ngưỡng 180: dữ liệu vẫn hoàn toàn hợp lệ, chỉ là hơi cũ. Vì vậy nhóm để freshness ở mức warning. Nếu để critical, pipeline sẽ đỏ mỗi khi Crossref chậm ra bài mới, và cảnh báo đó sẽ nhanh chóng bị bỏ qua.

**4. Vì sao phải dùng cùng test set cho baseline, corrupted và repaired?**

Vì ground truth được sinh **từ chính dataset**. Nếu sinh lại test set trên dataset đã hỏng, ground truth của câu hỏi về ngày tháng sẽ lấy đúng cái ngày đã bị đẩy lùi 1500 ngày — agent trả lời theo dữ liệu hỏng sẽ được chấm là *đúng*, và `retrieval_hit_rate` có thể vẫn 1.0000 trên một corpus đã nát. Phép so sánh khi đó không đo tác động của corruption nữa mà đo sự tự nhất quán của dữ liệu hỏng. Pipeline chỉ sinh test set khi file chưa tồn tại hoặc khi đặt `REFRESH_TEST_SET=1`; check `frozen_test_set` trong verifier của tôi so vân tay `(id, question)` giữa ba file answers để bảo đảm điều kiện này thật sự được giữ, chứ không chỉ tin vào ý định của code.

**5. Repair được xem là thành công dựa trên artifact và metric nào?**

Bốn bằng chứng, theo thứ tự từ mạnh đến yếu. Thứ nhất, dữ liệu: `papers_clean_repaired.json` bằng đúng `papers_clean.json`, 24/24 dòng — repair tái tạo từ `data/raw/crossref_records.json` bằng chính `build_clean_dataframe`, không đụng vào dataset hỏng. Thứ hai, quality: `repaired_quality.json` trở lại PASS 10/11 và danh sách `critical_failed_checks` rỗng. Thứ ba, freshness: `stale_rows` về lại 1, `oldest_published` từ 2022-03-21 về 2026-02-04. Thứ tư, metrics: cả bốn chỉ số về đúng mức baseline. Tôi xếp dữ liệu lên trước metrics vì metrics có thể trùng khớp một cách tình cờ, còn dataset bằng nhau tuyệt đối thì không.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal          |     Baseline |    Corrupted |     Repaired | Nhận xét của cá nhân                                                      |
| ---------------------- | -----------: | -----------: | -----------: | ------------------------------------------------------------------------------ |
| `retrieval_hit_rate` |       1.0000 |       0.8000 |       1.0000 | Đúng 4/20 câu miss, và cả 4 đều thuộc 3 paper bị xoá                 |
| `mean_token_f1`      |       1.0000 |       0.7593 |       1.0000 | Giảm sâu hơn hit rate — có câu retrieve đúng nhưng vẫn trả lời sai |
| `judge_accuracy`     |       1.0000 |       0.7500 |       1.0000 | 15/20 = 0.75; là heuristic token-overlap, không phải LLM judge              |
| `mean_judge_score`   |       5.0000 |       4.0000 |       5.0000 | Cùng 5 câu bị chấm sai như trên                                          |
| Quality checks         |   PASS 10/11 |    FAIL 6/11 |   PASS 10/11 | 3 critical failure mới trên bản corrupted                                   |
| Freshness status       | STALE (1/24) | STALE (4/23) | STALE (1/24) | Nhãn không đổi; bằng chứng nằm ở số liệu, không ở nhãn            |

### Kết luận từ số liệu

1. **Corruption → quality signal → agent metric.** Xoá 3 bản ghi mới nhất (`corruption_log.json`, bước `drop_latest_records`, có `affected_paper_ids`) làm 3 document ground truth biến mất khỏi collection `papers-corrupted` → 4 câu `summary-000`, `authors-001`, `date-002`, `categories-003` có `retrieval_hit = false` trong `corrupted_answers.json` → `retrieval_hit_rate` 1.0000 → 0.8000.
2. **Repair → quality signal phục hồi → agent metric phục hồi.** Rebuild từ `data/raw/crossref_records.json` khôi phục đủ 24 dòng → `repaired_quality.json` về PASS 10/11 với `critical_failed_checks` rỗng, `freshness_report_repaired.json` về `stale_rows` = 1 → cả bốn metric về đúng mức baseline, và verifier xác nhận sai lệch dưới 1e-4 (`repair_restores_metrics`).

**Corruption nào ảnh hưởng rõ nhất và vì sao?**

Drop 3 bản ghi mới nhất. Lý do là nó tấn công tầng thấp nhất của pipeline: document biến mất khỏi index thì không tầng nào phía sau cứu được. Blank summary hay truncate title chỉ làm *nội dung* xấu đi — agent vẫn tìm đúng tài liệu và vẫn có cơ hội trả lời đúng phần nào. Số liệu ủng hộ điều này: 4 câu bị drop có `token_f1` lần lượt 0.187, 0.0, 0.0, 0.0, tức gần như mất trắng; trong khi `summary-012` bị hỏng nội dung thì vẫn `retrieval_hit = true`.

**Kết quả nào khác với kỳ vọng ban đầu?**

Tôi kỳ vọng `mean_token_f1` giảm xấp xỉ `retrieval_hit_rate`, vì nghĩ hai chỉ số cùng phản ánh 4 câu bị mất document. Thực tế `mean_token_f1` giảm 0.2407 còn `retrieval_hit_rate` giảm 0.2000. Giả thuyết của tôi là có thêm câu bị hỏng ở tầng trả lời chứ không phải tầng tìm kiếm. Tôi kiểm tra bằng cách đọc `corrupted_answers.json` và lọc các câu có `token_f1 < 1.0`: ra 5 câu, nhiều hơn 4 câu miss retrieval đúng một câu — `summary-012`, `retrieval_hit = true` nhưng `token_f1 = 0.0`, tức là câu này thuộc nhóm bị blank/noise summary. Cộng lại: (15 × 1.0 + 0.187 + 0 + 0 + 0 + 0) / 20 = 0.7593, khớp chính xác con số trong `corrupted_metrics.json`. Kết luận: hai corruption khác nhau tấn công hai tầng khác nhau, và đúng vì thế mà `mean_token_f1` phải giảm nhiều hơn `retrieval_hit_rate`.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. **Về data pipeline:** giá trị của raw snapshot nằm ở chỗ nó bất biến. Repair của bài lab này chỉ đáng tin vì `data/raw/crossref_records.json` không bị bước nào ghi đè — nên `papers_clean_repaired.json` mới bằng đúng `papers_clean.json`. Nếu pipeline ghi đè raw ở mỗi lần chạy thì không còn điểm nào để quay về, và mọi thao tác "sửa" sẽ chỉ là đoán.
2. **Về data quality/observability:** phân biệt critical với warning quan trọng ngang việc viết ra check. Nếu freshness bị đặt critical, dataset baseline hoàn toàn hợp lệ của nhóm đã FAIL chỉ vì một bài báo 183 ngày tuổi. Một hệ thống cảnh báo cái gì cũng đỏ thì tương đương không có cảnh báo.
3. **Về ảnh hưởng của data đến RAG agent:** dữ liệu hỏng làm agent hỏng theo nhiều tầng, và mỗi tầng cần một metric riêng để nhìn thấy. Nếu chỉ theo dõi `retrieval_hit_rate`, nhóm sẽ hoàn toàn bỏ sót `summary-012` — câu mà agent tìm đúng tài liệu rồi trả lời sai hoàn toàn.

### Nếu có thêm thời gian

Chạy corruption flow với nhiều seed thay vì mỗi seed `20251006`. Hiện delta `retrieval_hit_rate` = −0.2000 đến từ đúng một lần bốc ngẫu nhiên trên corpus 24 paper, mà 3 paper bị xoá lại tình cờ nằm trong 5 paper được dùng sinh câu hỏi — một seed khác có thể cho delta 0. Cách đo cải thiện: chạy 10 seed, báo cáo trung bình ± độ lệch chuẩn của từng delta; nếu độ lệch lớn thì kết luận "corruption làm giảm 0.2" phải được phát biểu lại thành một khoảng, không phải một con số.

## 10. Cam kết của thành viên

- [X] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [X] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [X] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [X] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [X] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [X] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Nguyễn Văn Tiến
**Ngày xác nhận:** 2026-08-06
