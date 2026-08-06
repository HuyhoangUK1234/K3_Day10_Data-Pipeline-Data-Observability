# Rules

Mỗi khi tạo mới hoặc chỉnh sửa code trong project này, HOẶC sau khi pull code về mà phát hiện có sự thay đổi (từ các nhánh/thành viên khác), hãy luôn tạo kèm một file changelog dạng markdown mô tả thay đổi đó, lưu vào thư mục `CHANGE_REQUEST/` ở root project (tạo thư mục này nếu chưa có). Đặt tên file theo dạng `CHANGE_REQUEST/<ngày>_<mô_tả_ngắn>.md`, ví dụ `CHANGE_REQUEST/2026-08-06_add_quality_checks.md`.

Nội dung file cần có:
1. Tóm tắt thay đổi: đã thêm/sửa/xóa gì.
2. Lý do: tại sao cần thay đổi này, giải quyết vấn đề/yêu cầu gì.
3. File bị ảnh hưởng: liệt kê đường dẫn từng file đã đổi.
4. Chi tiết logic: giải thích ngắn gọn cách hoạt động của phần code mới/sửa (đặc biệt nếu có thay đổi input/output, schema, hoặc hành vi của hàm).
5. Cần lưu ý / kiểm tra: những điều người đọc nên kiểm tra lại hoặc test trước khi merge.

Không cần viết lại toàn bộ code trong file changelog này — chỉ mô tả bằng lời để người review đọc hiểu nhanh, không cần đọc diff.

Áp dụng quy tắc này cho mọi thay đổi code từ giờ trở đi trong project. Mỗi lần thay đổi tạo 1 file riêng trong `CHANGE_REQUEST/`, không ghi đè lên file cũ.
