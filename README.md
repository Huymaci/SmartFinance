# SmartFinance

Flask API triển khai toàn bộ Use Case priority **Must** trong SRS SmartFinance v2. UC-10 (chia sẻ trạng thái) chưa triển khai vì priority là **Should**.

## Phạm vi theo Actor

- **Guest:** UC-01 đăng ký, privacy notice, đăng nhập và khóa 15 phút sau 5 lần sai.
- **User:** UC-02 hồ sơ/export/yêu cầu xóa; UC-03 tài khoản tiền; UC-04 giao dịch và custom category; UC-05 preview CSV/XLSX; UC-06 conflict/confirm/error report; UC-07 budget/Safe-to-Spend; UC-08 alert; UC-09 statistics.
- **Admin:** UC-11 quản trị user/import config/operations/audit với administrative blindness.

## Chạy ứng dụng

Yêu cầu Python 3.11 và MySQL 8.0.16+ (khuyến nghị Docker).

1. Sao chép `.env.example` thành `.env`, thay toàn bộ giá trị mẫu và đặt thêm `MYSQL_PASSWORD`, `MYSQL_ROOT_PASSWORD` trong shell nếu dùng Compose.
2. Cài dependency: `python -m pip install -r requirements.txt`.
3. Khởi động MySQL: `docker compose up -d mysql`.
4. Chạy migration: `python -m alembic upgrade head`.
5. Seed category, 3 bank template, rules và Admin: `python -m scripts.seed`.
6. Chạy ứng dụng: `python run.py`.
7. Mở `http://127.0.0.1:5000` — Flask phục vụ cả giao diện và API cùng origin.

Giao diện tự lấy CSRF token và gửi kèm mọi POST/PUT/PATCH/DELETE. Session cookie dùng `HttpOnly`, `SameSite=Lax` và timeout nhàn rỗi 30 phút. Ở production, đặt `HTTPS_ENABLED=true` sau reverse proxy HTTPS để bật chuyển hướng HTTPS và cờ cookie `Secure`; local mặc định dùng HTTP để có thể đăng nhập mà không cần chứng chỉ tự ký.

## Giao diện v1

Frontend tại `frontend/` đã kết nối các API cho đăng ký/đăng nhập, tài khoản tiền, giao dịch, import sao kê và xử lý trùng, ngân sách, Safe-to-Spend, cảnh báo, dashboard và thống kê. UC-10 chia sẻ và màn hình Admin chưa nằm trong giao diện người dùng v1; các API Admin vẫn giữ nguyên.

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest --cov=app --cov-report=term-missing -q
```

Unit/component suite dùng SQLite in-memory để chạy độc lập. Các bằng chứng đặc thù MySQL (collation, FK/check constraint, `DATETIME(6)`, `BINARY(32)`) phải chạy thêm trên MySQL; migration có thể kiểm tra không kết nối bằng:

```powershell
$env:DATABASE_URL='mysql+pymysql://user:pass@host/db?charset=utf8mb4'
.\.venv\Scripts\python.exe -m alembic upgrade head --sql
```

Nightly alert job: `python -m scripts.nightly`.
