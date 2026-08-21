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

## Dữ liệu mock từ sao kê

Sau khi chạy migration, có thể tạo user demo và 20.000 giao dịch mang cấu trúc
mô tả của ba mẫu sao kê. Dòng tiền được mô phỏng theo tháng: MB nhận lương
25–30 triệu, chuyển tiền sang BIDV để chi tiêu (gồm đúng 3 triệu tiền nhà) và
chuyển phần muốn giữ sang VPBank (tài khoản thanh toán, không phải tiết kiệm).
Lần đầu chuyển từ bộ mock cũ sang mô hình này, dùng chế độ thay thế có giới hạn:

```powershell
$env:MOCK_USER_PASSWORD='SmartExpenseMock1!'
python -m scripts.seed_mock --replace-demo-data
```

Email mặc định là `demo@smartexpense.local`. Chế độ thay thế chỉ xóa dữ liệu tài
chính thuộc user này, giữ nguyên user khác và dữ liệu cấu hình dùng chung. Chạy
lại cùng tham số không nhân đôi. Dữ liệu mặc định trải từ 2024-01-01 đến
2026-08-19 và đạt đúng 20.000 dòng theo NFR-08. Có thể điều chỉnh quy mô:

```powershell
python -m scripts.seed_mock --synthetic-count 50000 --random-seed 42 `
  --start-date 2022-01-01 --end-date 2026-08-19
```

Cùng bộ tham số có thể chạy lại mà không nhân đôi. Đổi `--random-seed` sẽ tạo
một tập giao dịch khác. Ba CSV gốc chỉ được dùng làm mẫu ngôn ngữ; nếu cần nhập
nguyên văn để kiểm thử parser, truyền thêm `--include-source`.
