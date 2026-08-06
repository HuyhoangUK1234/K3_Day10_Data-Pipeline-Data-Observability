# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Nguyễn Duy Hải Bằng |
| MSSV | 2A202601225 |
| Khóa/Lớp | K3 |
| Tên nhóm | [Tên nhóm] |
| Vai trò chính | Thành viên 1 — Source Ingestion |
| Repository | https://github.com/HuyhoangUK1234/K3_Day10_Data-Pipeline-Data-Observability |
| Ngày hoàn thành | 2026-08-06 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Fetch dữ liệu từ Crossref | `src/ingestion/crossref.py` — `fetch_source_records`, `_request_with_retry` | Query + filter trong `Settings` | `data/raw/crossref_response.json` | Hoàn thành |
| Parse payload về schema chung | `parse_crossref_payload`, `_strip_markup`, `_authors`, `_categories`, `_pdf_url` | Payload JSON thô | `data/raw/crossref_records.json` (24 record) | Hoàn thành |
| Chuẩn hóa ngày xuất bản | `_published_date`, `_updated_date`, `_date_from_parts` | Các node `date-parts` của Crossref | Trường `published`/`updated` dạng ISO | Hoàn thành |
| Đọc lại snapshot raw cho repair | `load_raw_records` | `crossref_records.json` | `list[PaperRecord]` cho corruption flow | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Debug freshness report bị sai (`latest_published` = 2028 nhưng `max_age_days` = 0) | Observability owner — `src/observability/quality.py` | Truy ra nguyên nhân nằm ở phía ingestion (Crossref forward-date ngày issue), sửa `_published_date`; sau đó `future_dated_rows` = 0 |
| Giữ nguyên `data/raw/crossref_records.json` làm nguồn repair | Corruption owner — `src/ingestion/corruption.py` | Repaired dataset trùng byte-for-byte với baseline (104 493 bytes) |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Gọi Crossref `/works` có retry/backoff | `_request_with_retry` | `crossref_response.json` (1.04 MB, 72 items) | `python script/run_phase1.py` với `REFRESH_SOURCE=1` |
| Lọc record đủ chất lượng | `parse_crossref_payload` | 70/72 item hợp lệ, giữ 24 theo `max_results` | Đếm phần tử trong hai file `data/raw/` |
| Ép ngày về ngày đã thực sự phát hành | `_published_date` | Dải ngày 2026-02-04 → 2026-08-03 | `data/quality/freshness_report.json` |

Output cụ thể mà phần việc của em tạo ra: `data/raw/crossref_records.json` — 24 record theo đúng schema `PaperRecord`, là đầu vào duy nhất của bước cleaning và cũng là nguồn dùng để repair ở pha 2.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Crossref trả JSON rất "bẩn" so với những gì pipeline cần: abstract là JATS XML bị escape, nhiều bản ghi không có abstract hoặc không có DOI, và ngày tháng thì mỗi publisher ghi một kiểu. Nếu bê nguyên xuống bước cleaning thì mọi lỗi dữ liệu sẽ lộ ra ở cuối pipeline, lúc đó rất khó biết lỗi từ đâu.

### Cách triển khai

Em over-fetch gấp 3 lần `max_results` (72 rows) vì biết chắc bước parse sẽ loại bớt, rồi mới cắt xuống 24. Request bọc trong vòng retry 5 lần, exponential backoff 1→16s, chỉ retry với 429/500/502/503/504 và lỗi mạng — các lỗi 4xx khác thì fail luôn cho nhanh. Header có User-Agent mô tả rõ theo convention polite pool của Crossref.

Phần parse: unescape HTML entity rồi strip tag XML để lấy abstract sạch, bỏ luôn tiền tố "Abstract:" mà nhiều publisher hay chèn. Record bị loại nếu thiếu DOI, trùng DOI, title < 10 ký tự hoặc summary < 80 ký tự — lọc ngay tại đây để bước sau chỉ nhận dữ liệu đúng hình dạng.

Phần khó nhất là ngày. Crossref forward-date ngày issue (bài đăng 2026 có thể ghi `issued` = 2028), nên em duyệt qua 5 ứng viên `published-online / published / issued / published-print / created` và chọn ngày **gần nhất đã thực sự xảy ra** so với hôm nay. Nếu không có ứng viên nào hợp lệ thì bỏ record luôn thay vì đoán. Ngoài ra `date-parts` hay thiếu ngày/tháng nên em clamp tháng về 1–12, ngày về 1–31 và fallback về mùng 1 nếu ngày không tồn tại (kiểu 31/2).

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | `Settings` (`source_query`, `source_filter`, `max_results`) → params gọi `https://api.crossref.org/works` |
| Output | `list[PaperRecord]` 11 trường + 2 file JSON trong `data/raw/` |
| Module phụ thuộc | `core.config.Settings`, `core.utils` (`normalize_whitespace`, `compact_join`, `read_json`, `write_json`) |
| Module sử dụng output | `src/ingestion/cleaning.py`, `src/ingestion/corruption.py` (repair đọc qua `load_raw_records`) |
| Điều kiện lỗi cần xử lý | Rate limit 429, lỗi 5xx, timeout, JSON không parse được, thiếu DOI/title/abstract, `date-parts` rỗng hoặc sai, forward-dated |

### Cách xác minh

```bash
REFRESH_SOURCE=1 python script/run_phase1.py
```

- **Kết quả mong đợi:** ghi được raw response, parse ra đúng 24 record, không có record nào forward-dated.
- **Kết quả thực tế:** `GET ... rows=72`, parse 70 record hợp lệ, giữ 24; `freshness_report.json` cho `future_dated_rows` = 0, `age_days` từ 3 đến 183.
- **Artifact/log:** `data/raw/crossref_response.json`, `data/raw/crossref_records.json`, `data/quality/freshness_report.json`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** chọn trường nào làm `published` khi Crossref trả về nhiều ngày mâu thuẫn nhau.
- **Các phương án đã cân nhắc:** (1) lấy thẳng `issued` như tài liệu Crossref gợi ý; (2) lấy ngày nhỏ nhất trong các ứng viên; (3) lấy ngày lớn nhất nhưng đã thực sự xảy ra tính đến ngày chạy.
- **Phương án đã chọn:** phương án 3.
- **Lý do:** phương án 1 kéo theo ngày 2028 làm `age_days` âm và freshness mất ý nghĩa hoàn toàn. Phương án 2 an toàn nhưng lại làm bài báo trông cũ hơn thực tế (thường rơi vào `created` — ngày đăng ký DOI). Phương án 3 phản ánh đúng "ngày bài báo thực sự đọc được", vẫn có fallback cho trường hợp mọi ngày đều ở tương lai.
- **Bằng chứng quyết định phù hợp:** `future_dated_rows` = 0, `latest_published` = 2026-08-03, `min_age_days` = 3 — hợp lý với filter `from-pub-date:2026-02-07`.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng:** `freshness_report.json` ghi `latest_published` = 2028-06-15 nhưng `max_age_days` = 0, cả 24 dòng đều "0 ngày tuổi" — báo cáo tự mâu thuẫn.
- **Lệnh tái hiện:** `REFRESH_SOURCE=1 python script/run_phase1.py` rồi mở `data/quality/freshness_report.json`.
- **Nguyên nhân gốc:** ingestion lấy thẳng `issued` mà không kiểm tra ngày tương lai, còn `compute_age_days` lại clamp về 0 bằng `max(delta, 0)`. Hai chỗ cộng lại khiến ngày tương lai bị giấu sau một số 0 giả thay vì báo lỗi.
- **Cách xử lý:** viết lại `_published_date` để chọn ngày gần nhất đã xảy ra; bỏ clamp trong `compute_age_days` để `age_days` có dấu; thêm check `published_not_in_future` để nếu lỗi tái diễn thì quality layer bắt được.
- **Cách xác minh sau khi sửa:** chạy lại pipeline, `future_dated_rows` = 0, dải ngày 2026-02-04 → 2026-08-03.
- **Điều học được:** đừng bao giờ "sửa" dữ liệu xấu bằng cách clamp giá trị — làm vậy là xóa bằng chứng. Phải để nó lộ ra rồi xử lý ở đúng tầng, ở đây là tầng ingestion.

## 7. Hiểu biết về luồng end-to-end

1. Ingestion gọi Crossref, lưu raw response và parse thành 24 `PaperRecord`. Cleaning normalize, dedupe, tính `age_days` và ghép `text_for_embedding`. Chuỗi đó được embed bằng `all-MiniLM-L6-v2` và nạp vào ChromaDB (cosine), document ID là DOI.
2. Test set gồm 20 câu (4 loại × 5 paper), mỗi câu mang theo `ground_truth_doc_ids` là DOI của paper sinh ra nó. Retrieval được chấm bằng việc DOI đó có nằm trong top-4 hay không; câu trả lời chấm bằng token-F1 và judge.
3. Quality check soi *hình dạng* dữ liệu tại một thời điểm (thiếu, trùng, quá ngắn) và fail cứng khi vi phạm critical. Freshness soi *độ mới* — dữ liệu vẫn hợp lệ hoàn toàn nhưng đã cũ — nên chỉ là warning chứ không chặn pipeline.
4. Vì nếu sinh lại test set từ dataset đã hỏng thì ground truth cũng lấy từ dữ liệu hỏng, agent sẽ "đúng" với dữ liệu sai và mọi so sánh vô nghĩa. Test set phải đóng băng cho cả ba lần chạy.
5. Repair thành công khi repaired dataset dựng lại từ `data/raw/crossref_records.json` trùng với baseline (cùng 24 dòng, cùng kích thước file), quality trở lại PASS 10/11 và cả 4 metric về đúng mức baseline.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| --- | ---: | ---: | ---: | --- |
| `retrieval_hit_rate` | 1.0000 | 0.8000 | 1.0000 | Đúng 3 record bị drop ở bước corruption là 3 document ground truth |
| `mean_token_f1` | 1.0000 | 0.7593 | 1.0000 | Summary rỗng/nhiễu — tức phần abstract em parse — ảnh hưởng trực tiếp |
| `judge_accuracy` | 1.0000 | 0.7500 | 1.0000 | Heuristic fallback, chưa có LLM provider |
| `mean_judge_score` | 5.0000 | 4.0000 | 5.0000 | Như trên |
| Quality checks | PASS 10/11 | FAIL 6/11 | PASS 10/11 | 3 critical failure: `paper_id_unique`, `summary_not_empty`, `summary_min_length` |
| Freshness status | STALE (1/24) | STALE (4/23) | STALE (1/24) | Status không đổi, nhưng `stale_rows` 1 → 4 và `oldest_published` lùi về 2022-03-21 |

### Kết luận từ số liệu

1. Drop 3 bản ghi mới nhất → 3 document ground truth biến mất khỏi collection `papers-corrupted` → `retrieval_hit_rate` 1.0000 → 0.8000 (4/20 câu `retrieval_hit = false`).
2. Rebuild từ `data/raw/crossref_records.json` → quality về PASS 10/11 và `stale_rows` về 1 → cả 4 metric phục hồi 100%.

Corruption ảnh hưởng rõ nhất là **drop 3 bản ghi mới nhất**, vì nó không làm hỏng dữ liệu mà xóa hẳn dữ liệu — retrieval không còn gì để tìm. Các corruption khác chỉ làm câu trả lời lệch chứ document vẫn nằm trong index.

Kết quả khác kỳ vọng: em nghĩ freshness status sẽ chuyển từ FRESH sang STALE khi bị corrupt, nhưng baseline vốn đã STALE sẵn vì có 1 bài `age_days` = 183 — chỉ vượt ngưỡng 180 đúng 3 ngày. Kiểm tra lại trong `freshness_report.json` thì thấy bằng chứng nằm ở *số liệu* (`stale_rows`, `oldest_published`) chứ không phải ở nhãn status.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Snapshot raw phải bất biến. Nhờ `data/raw/crossref_records.json` không bị corruption chạm vào mà repair mới tái tạo được đúng baseline thay vì vá lỗi.
2. Lỗi dữ liệu nên bị chặn ở tầng gần nguồn nhất. Lọc DOI/title/abstract ngay lúc parse rẻ hơn nhiều so với đi truy ngược từ metric cuối pipeline.
3. Một trường bị parse sai ở ingestion (ngày xuất bản) có thể làm hỏng luôn cả một tín hiệu observability ở tận cuối — vấn đề ở tầng nào phải sửa ở tầng đó.

### Nếu có thêm thời gian

Em sẽ thêm test cho `_published_date` với payload cố định: forward-dated, `date-parts` thiếu ngày/tháng, ngày không tồn tại như 31/2. Đo bằng việc chạy test thấy pass mà không cần gọi mạng — hiện tại muốn kiểm tra logic ngày vẫn phải fetch thật.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Nguyễn Duy Hải Bằng
**Ngày xác nhận:** 2026-08-06
