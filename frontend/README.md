# SmartFinance UI prototype

Frontend v1 dựa trên `SRS-SmartFinance-v2-slim.md`, được Flask phục vụ cùng origin và kết nối trực tiếp với JSON API.

## Chạy thử

Chạy từ thư mục gốc dự án:

```powershell
python run.py
```

Sau đó truy cập `http://127.0.0.1:5000`. Không mở `index.html` trực tiếp vì session và CSRF cần Flask backend.

## Phạm vi giao diện

- Dashboard và Safe-to-Spend (UC-09, FR-17, FR-21)
- Danh sách, tìm kiếm và form thêm giao dịch (UC-04)
- Upload và preview sao kê, trạng thái lỗi/trùng (UC-05, UC-06)
- Ngân sách theo danh mục (UC-07)
- Hộp thư cảnh báo có lý do và hành động đề xuất (UC-08)
- Thống kê danh mục và xu hướng 12 tháng (UC-09)

`app.js` dùng session cookie và CSRF token của Flask. UI có trạng thái rỗng/lỗi, định dạng ngày Việt Nam và VND; không còn dùng mock data cho các màn hình vận hành.

## Ngôn ngữ

Nút `VI | EN` có ở màn hình xác thực và header ứng dụng. Dictionary nằm trong `i18n.js`; lựa chọn được lưu tại `localStorage` với key `smartfinance-language` và mặc định là `vi`. Nội dung do người dùng hoặc backend trả về như tên, email, tên tài khoản, mô tả giao dịch và nội dung cảnh báo không bị dịch hay thay đổi.
