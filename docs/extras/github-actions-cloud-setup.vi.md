# ☁️ HƯỚNG DẪN CẤU HÌNH BẢN TIN CHẠY TỰ ĐỘNG TRÊN GITHUB ACTIONS (SERVERLESS CRON)

> **Mục tiêu**: Giúp bạn chạy toàn bộ luồng tạo video và đăng tải YouTube hoàn toàn tự động trên đám mây (Cloud Serverless) của GitHub, không cần mở máy tính cá nhân hay lo máy bị tắt nguồn.

---

## 1. Cơ Chế Hoạt Động

* Workflow nằm tại: [`.github/workflows/daily_news.yml`](file:///c:/projects/HaizFlow-main/.github/workflows/daily_news.yml)
* Sử dụng máy ảo Ubuntu cực mạnh của GitHub (4 vCPU, 16 GB RAM, có sẵn FFmpeg & Python).
* **Hoàn toàn miễn phí** (chỉ tốn ~350 phút/tháng trên 2,000 phút miễn phí hàng tháng của GitHub).
* **4 Khung giờ tự động mỗi ngày (Tính theo giờ Việt Nam UTC+7):**
  1. **05:30 Sáng:** Bản tin **Tin Mới** (`tin_moi`, 16:9 Ngang 1080p).
  2. **11:30 Trưa:** Shorts **Tin Vui** (`hope`, 9:16 Dọc).
  3. **12:00 Trưa:** Shorts **Tin Độc Lạ** (`viral`, 9:16 Dọc).
  4. **17:30 Chiều:** Bản tin **Tin Nóng** (`tin_nong`, 16:9 Ngang 1080p).

---

## 2. Các Bước Cài Đặt Secrets Trên GitHub (Chỉ Làm 1 Lần)

Để GitHub Actions có quyền gọi AI Gemini và đăng video lên kênh YouTube của bạn, hãy thêm 3 Secrets bảo mật:

1. Truy cập vào Repository của bạn: [https://github.com/thaipeace/videoFlow](https://github.com/thaipeace/videoFlow)
2. Bấm vào **Settings** (tab bánh răng ở góc trên bên phải) $\rightarrow$ **Secrets and variables** $\rightarrow$ **Actions**.
3. Bấm nút xanh **New repository secret** để thêm lần lượt 3 secrets:

### Secret 1: `GEMINI_API_KEY`
* **Name**: `GEMINI_API_KEY`
* **Secret**: Dán khóa Google Gemini API Key của bạn (bắt đầu bằng `AIzaSy...`).

### Secret 2: `YOUTUBE_TOKEN_JSON`
* **Name**: `YOUTUBE_TOKEN_JSON`
* **Secret**: Mở tệp `runtime/data/youtube_token.json` trên máy tính của bạn, sao chép toàn bộ nội dung JSON (chứa `access_token` và `refresh_token`) rồi dán vào đây.

### Secret 3: `YOUTUBE_CLIENT_SECRET_JSON`
* **Name**: `YOUTUBE_CLIENT_SECRET_JSON`
* **Secret**: Mở tệp `runtime/data/youtube_client_secret.json` trên máy tính của bạn, sao chép toàn bộ nội dung JSON rồi dán vào đây.

### Secret 4 (Tùy chọn): `GDRIVE_WEBHOOK_URL`
* **Name**: `GDRIVE_WEBHOOK_URL`
* **Secret**: Đã được cấu hình mặc định sẵn Webhook Google Apps Script của bạn. Nếu sau này bạn đổi Webhook folder khác, chỉ cần nhập link URL Webhook mới vào đây.

---

## 3. Cách Bấm Chạy Thử Ngay Lập Tức Trên Web (Manual Trigger)

Bất kỳ lúc nào muốn chạy thử một bản tin mà không cần đợi đến giờ:

1. Vào tab **Actions** trên GitHub: [https://github.com/thaipeace/videoFlow/actions](https://github.com/thaipeace/videoFlow/actions)
2. Chọn workflow **"Automated Daily News Broadcast Pipeline"** ở danh sách bên trái.
3. Bấm vào nút **Run workflow** ở góc phải:
   * **Chủ đề bản tin**: Chọn `'tin_moi'`, `'hope'`, `'viral'`, `'tin_nong'` hoặc `'auto'`.
   * **Tự động đăng tải lên YouTube**: Tích chọn `true` (hoặc `false` nếu chỉ muốn xuất video kiểm tra).
   * **Chế độ test nhanh**: Tích chọn `true` nếu muốn test luồng render cực nhanh trong 10 giây với mock data.
4. Bấm **Run workflow**.

---

## 4. Lưu Trữ Tự Động & Không Gây Rác Repo Git

Hệ thống được thiết kế theo nguyên tắc **Zero-Pollution Git**:
1. **Không lưu video MP4 hay ảnh tạm vào Git**: Video sau khi xuất bản sẽ được đẩy thẳng lên YouTube.
2. **Kịch bản biên tập (Editorial Scripts / Proof-of-Work)**:
   * Mỗi lần chạy xong một bản tin, toàn bộ kịch bản và bản chứng minh nguồn tin gốc sẽ được tự động đồng bộ đẩy vào **Google Drive** của bạn qua Google Apps Script Webhook.
   * Hoàn toàn không commit file văn bản kịch bản vào Git, giúp lịch sử Git luôn sạch đẹp, dung lượng nhẹ.
3. **GitHub Artifacts**:
   * Các file nhật ký chạy (log), manifest và bản nháp tạm thời được lưu tại mục **Artifacts** của lượt chạy GitHub Actions và sẽ **tự động xóa sau 3 ngày**, không làm đầy bộ nhớ lưu trữ.
