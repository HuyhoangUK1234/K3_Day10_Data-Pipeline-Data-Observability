# Changelog: Pulled Group Updates (End-to-End Implementation)

**1. Tóm tắt thay đổi**
- Pull code từ Github, cập nhật một lượng lớn file (53 files, ~30,000 dòng).
- Toàn bộ pipeline từ Ingestion, Cleaning, Evaluation, Observability đến Corruption Flow đều đã được cài đặt hoàn chỉnh và sinh ra dữ liệu thực tế.

**2. Lý do**
- Thành viên khác trong nhóm (Trần Thị Thanh Tâm) đã commit/push toàn bộ phần code được phân công và chạy test ra dữ liệu thật.
- Cập nhật source code nội bộ trên máy để đồng bộ với tiến độ của nhóm.

**3. File bị ảnh hưởng**
- Toàn bộ thư mục `data/` (đã sinh ra data ở `raw`, `clean`, `chroma`, `eval`, `quality`, `results`, `reports`).
- Tất cả các file trong `src/` đã được implement (mất toàn bộ `NotImplementedError`):
  - `src/ingestion/crossref.py`, `src/ingestion/cleaning.py`, `src/ingestion/corruption.py`
  - `src/evaluation/testset.py`
  - `src/observability/quality.py`, `src/observability/reporting.py`
  - `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py`
  - Thêm file `src/pipelines/common.py`
- Cập nhật `report/group_report.md`.

**4. Chi tiết logic**
- Thay vì chỉ có sườn bài (pseudo-code), toàn bộ các class và function nay đã chứa code Python thực thi thật.
- Workflow chạy từ fetch metadata (Crossref), làm sạch dữ liệu, tạo embeddings/ChromaDB, chấm điểm agent (Ragas, F1, Judge), giả lập lỗi (corruption) và ghi nhận vào các file Markdown/JSON.

**5. Cần lưu ý / kiểm tra**
- Dữ liệu thật đã có trong `data/clean/` và các thư mục khác, không cần phải mock data nữa.
- Cần chạy lại script hoặc test xem code của người khác có ghi đè hay làm hỏng thay đổi nào của mình không.
- Có thể dùng dữ liệu này để tiếp tục debug hoặc demo báo cáo.
