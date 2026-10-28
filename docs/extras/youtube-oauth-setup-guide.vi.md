# 🔐 HƯỚNG DẪN CẤU HÌNH YOUTUBE OAUTH & CẬP NHẬT GITHUB SECRETS

> **Mục tiêu**: Hướng dẫn chi tiết cách tạo tài khoản Google Cloud OAuth, sử dụng công cụ `scripts/setup_youtube_auth.py` để kết nối kênh YouTube, và đưa khóa xác thực lên GitHub Actions để quy trình tự động xuất bản video hoạt động trơn tru.

---

## 1. Tổng Quan

Để GitHub Actions (hoặc máy chủ đám mây) có thể thay mặt bạn tự động đăng tải video lên kênh YouTube mà không cần đăng nhập thủ công, hệ thống sử dụng giao thức **OAuth 2.0** chuẩn mực của Google.

Hệ thống cung cấp sẵn một công cụ dòng lệnh chuyên dụng:
```powershell
python scripts/setup_youtube_auth.py
```
Công cụ này sẽ:
1. Nạp thông tin Client ID & Client Secret của Google Cloud.
2. Tự động mở trình duyệt để bạn cấp quyền cho kênh YouTube.
3. Nhận mã callback và sinh ra `youtube_token.json` (chứa `access_token` và `refresh_token`).
4. In sẵn 2 khối JSON được đóng khung rõ ràng để bạn sao chép và dán thẳng vào GitHub Secrets.

---

## 2. Chuẩn Bị Trên Google Cloud Console (Làm 1 Lần)

Nếu bạn chưa có tệp `client_secret.json` hoặc cần lấy lại từ tài khoản Google Cloud:

### Bước 2.1: Bật YouTube Data API v3
1. Truy cập [Google Cloud Console](https://console.cloud.google.com/).
2. Chọn dự án (Project) của bạn hoặc tạo mới.
3. Vào mục **APIs & Services** $\rightarrow$ **Library**.
4. Tìm kiếm từ khóa **"YouTube Data API v3"** $\rightarrow$ Bấm nút **Enable (Bật)**.

### Bước 2.2: Cấu hình Màn hình đồng ý OAuth (OAuth consent screen)
1. Vào **APIs & Services** $\rightarrow$ **OAuth consent screen**.
2. Chọn loại người dùng: **External (Bên ngoài)** $\rightarrow$ Bấm **Create**.
3. Điền **App name** (ví dụ: `VideoFlow Publisher`), nhập email hỗ trợ của bạn.
4. Ở mục **Scopes (Phạm vi)**: Bạn có thể để mặc định hoặc thêm scope `.../auth/youtube.upload`.
5. Ở mục **Test users (Người dùng thử nghiệm)**:
   * Bấm **+ ADD USERS**.
   * Nhập chính địa chỉ Gmail quản lý kênh YouTube của bạn.
   * Bấm **Save and continue**.

> [!IMPORTANT]
> ### 💡 Bí quyết để Token DÙNG VĨNH VIỄN (Không bị hết hạn sau 7 ngày)
> Mặc định, Google để trạng thái ứng dụng là **Testing**. Ở chế độ này, mọi Refresh Token sẽ **tự động bị thu hồi sau đúng 7 ngày** (gây ra lỗi `invalid_grant` khi chạy trên CI).
> * Để khắc phục, tại trang **OAuth consent screen**, nhìn mục **Publishing status**:
> * Bấm nút **"PUBLISH APP" (Công bố ứng dụng)** $\rightarrow$ Chọn **Confirm**.
> * *(Dù Google có hiển thị cảnh báo "Needs verification", bạn cứ an tâm bỏ qua vì ứng dụng này là cho cá nhân bạn tự sử dụng)*.
> * Sau khi chuyển sang **In production**, token sẽ **dùng vĩnh viễn** mà không bao giờ bị hết hạn định kỳ.

### Bước 2.3: Tạo và Tải về OAuth Client ID
1. Vào **APIs & Services** $\rightarrow$ **Credentials** (Thông tin xác thực).
2. Bấm **+ CREATE CREDENTIALS** $\rightarrow$ Chọn **OAuth client ID**.
3. Mục **Application type**: Chọn **Desktop app** (Ứng dụng cho máy tính để bàn).
4. Đặt tên (ví dụ: `VideoFlow Desktop Uploader`) $\rightarrow$ Bấm **Create**.
5. Nhìn vào danh sách **OAuth 2.0 Client IDs**:
   * Bấm vào biểu tượng **Tải xuống (Download JSON - hình mũi tên chỉ xuống ⬇️)** ở ngoài cùng bên phải của dòng client vừa tạo.
   * Lưu tệp này về máy (thường có tên dạng `client_secret_xxxxxxxx.json`).

---

## 3. Chạy Script Kết Nối YouTube Trên Máy Tính

Mở PowerShell tại thư mục dự án `videoFlow`:

### Cách 1: Chạy trực tiếp và kéo thả file JSON (Khuyên dùng)
```powershell
python scripts/setup_youtube_auth.py
```
Script sẽ hiện thông báo hỏi đường dẫn file. Bạn chỉ cần **kéo thả tệp `client_secret_xxxx.json` vào cửa sổ PowerShell** rồi bấm **Enter**.

### Cách 2: Truyền đường dẫn file qua tham số
```powershell
python scripts/setup_youtube_auth.py --client-secret-file "C:\path\to\client_secret_xxxx.json"
```

### Cách 3: Nhập trực tiếp Client ID & Client Secret
```powershell
python scripts/setup_youtube_auth.py --client-id "YOUR_CLIENT_ID.apps.googleusercontent.com" --client-secret "YOUR_CLIENT_SECRET"
```

### Cách 4: Kiểm tra nhanh trạng thái token hiện tại (Check-only)
```powershell
python scripts/setup_youtube_auth.py --check-only
```
Nếu đã xác thực thành công, lệnh này sẽ in ra:
```text
[OK] Đã kết nối kênh: Tên Kênh Của Bạn (ID: UCxxxxxxxxxxxxxx)
```

---

## 4. Quá Trình Đăng Nhập & Cấp Quyền

1. Khi script chạy, trình duyệt mặc định trên máy tính của bạn sẽ tự động bật lên link xác thực của Google.
2. Chọn đúng tài khoản Google sở hữu kênh YouTube của bạn.
3. Nếu Google hiện cảnh báo *"Google hasn’t verified this app"*:
   * Bấm vào dòng chữ nhỏ **Advanced (Nâng cao)** ở góc dưới.
   * Bấm tiếp vào **Go to VideoFlow Publisher (unsafe)**.
4. Tích chọn cấp quyền quản lý video YouTube $\rightarrow$ Bấm **Continue (Tiếp tục)**.
5. Trình duyệt sẽ hiện trang thông báo *"Xác thực hoàn tất! Bạn có thể đóng tab này"*.
6. Quay lại màn hình terminal, bạn sẽ thấy thông báo:
   ```text
   [OK] ĐĂNG NHẬP THÀNH CÔNG!
   -> Kênh đã kết nối: Tên Kênh Của Bạn (ID: UCxxxxxxxxxxxxxx)
   ```

---

## 5. Cập Nhật Secrets Lên GitHub Actions

Ngay sau khi đăng nhập thành công, script sẽ tự động in sẵn **2 khối JSON**:

1. Truy cập vào trang quản lý Secret trên GitHub Repo của bạn:  
   👉 **[https://github.com/thaipeace/videoFlow/settings/secrets/actions](https://github.com/thaipeace/videoFlow/settings/secrets/actions)**

2. Cập nhật lần lượt 2 Secret:

### Secret 1: `YOUTUBE_TOKEN_JSON`
* Bấm **New repository secret** (hoặc bấm biểu tượng bút chì để Update nếu đã có).
* **Name**: `YOUTUBE_TOKEN_JSON`
* **Secret**: Sao chép toàn bộ khối JSON thứ nhất được in trong terminal dán vào $\rightarrow$ Bấm **Add secret / Update secret**.

### Secret 2: `YOUTUBE_CLIENT_SECRET_JSON`
* Bấm **New repository secret** (hoặc biểu tượng bút chì để Update nếu đã có).
* **Name**: `YOUTUBE_CLIENT_SECRET_JSON`
* **Secret**: Sao chép toàn bộ khối JSON thứ hai được in trong terminal dán vào $\rightarrow$ Bấm **Add secret / Update secret**.

### Secret 3: `GEMINI_API_KEY`
* Đảm bảo khóa Google Gemini API Key của bạn (`AIzaSy...`) đã có trong danh sách Secrets.

---

## 6. Xử Lý Các Sự Cố Thường Gặp (Troubleshooting)

### 1. Lỗi `invalid_grant` (Token has been expired or revoked)
* **Nguyên nhân**: OAuth App trên Google Cloud vẫn đang ở chế độ **Testing**, làm token hết hạn sau 7 ngày; hoặc bạn vừa đổi mật khẩu tài khoản Google.
* **Cách khắc phục**:
  1. Vào [OAuth consent screen](https://console.cloud.google.com/apis/credentials/consent) và bấm **PUBLISH APP** để chuyển sang **In production**.
  2. Chạy lại `python scripts/setup_youtube_auth.py` trên máy để lấy token mới.
  3. Cập nhật lại giá trị mới vào Secret `YOUTUBE_TOKEN_JSON` trên GitHub.

### 2. Video đã upload thành công nhưng không thấy trên trang chủ kênh
* **Nguyên nhân**: Dự án Google Cloud chưa được xác minh thương mại nên YouTube tự động gắn cờ video ở chế độ **Private (Riêng tư)** để kiểm duyệt.
* **Cách khắc phục**:
  * Vào [YouTube Studio](https://studio.youtube.com/) $\rightarrow$ Chọn mục **Nội dung (Content)**.
  * Bạn sẽ thấy video vừa đăng đang ở trạng thái *Riêng tư (Khóa)*. Chỉ cần bấm chuyển sang **Công khai (Public)** là người xem có thể thấy ngay.

### 3. Lỗi `quotaExceeded` (HTTP 403)
* **Nguyên nhân**: Mỗi ngày Google Cloud cấp 10,000 units miễn phí. 1 lần upload video tiêu tốn 1,600 units. Nếu bạn test upload quá 6 lần/ngày, Google sẽ tạm khóa API upload trong ngày đó.
* **Cách khắc phục**: Hạn mức sẽ tự động được reset lại vào **00:00 giờ Thái Bình Dương (PST)**, tương đương **14:00 hoặc 15:00 chiều giờ Việt Nam**.

