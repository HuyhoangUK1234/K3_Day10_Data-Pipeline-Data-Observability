# Changelog: Add Quality Checks & Reporting Logic

**1. Tóm tắt thay đổi**
- Triển khai logic kiểm tra Data Quality và tính toán báo cáo Freshness trong `src/observability/quality.py`.
- Triển khai logic tạo file Markdown báo cáo cho Baseline Phase và so sánh Corruption/Repaired trong `src/observability/reporting.py`.

**2. Lý do**
- Hoàn thiện phần việc của Thành viên 3 (Observability) trong data pipeline.
- Giải quyết các `NotImplementedError` để pipeline có thể chạy end-to-end các phase từ đánh giá đến báo cáo.

**3. File bị ảnh hưởng**
- `src/observability/quality.py`
- `src/observability/reporting.py`

**4. Chi tiết logic**
- `quality.py`: Sử dụng `pandas` để đếm số dòng, check null và tính unique các ID, và dùng điều kiện boolean để đánh giá độ "fresh" của dữ liệu so với ngưỡng `freshness_threshold_days`. Xuất kết quả qua hàm `write_json`.
- `reporting.py`: Hàm `generate_phase1_report` sử dụng format string (`f-string`) để in Markdown tổng kết metrics cho baseline. Hàm `generate_corruption_report` in Markdown dạng table (bảng) để đối chiếu 3 cột: Baseline, Corrupted và Repaired.

**5. Cần lưu ý / kiểm tra**
- Người review/thành viên khác cần chạy thử `script/run_phase1.py` sau khi ghép đủ các phần Ingestion và Cleaning để kiểm tra xem file `.json` và file Markdown report sinh ra ở đúng thư mục `data/quality/` và `data/reports/` hay chưa.
- Kiểm tra hiển thị Markdown table ở report cuối để đảm bảo canh lề bảng đẹp.
