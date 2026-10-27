# 🛡️ HAIZFLOW DAILY NEWS - BỘ KHUNG QUY CHUẨN VẬN HÀNH & SỬA LỖI (OPERATIONAL HARNESS)
*(Tài liệu quy chuẩn gốc & Sổ tay chẩn đoán - Cập nhật: 25/10/2026)*

> **MỤC ĐÍCH CỦA TÀI LIỆU NÀY**:  
> Đây là **Single Source of Truth (Harness Chuẩn)** ghi lại toàn bộ cấu hình, luồng kích hoạt lịch biểu, quy tắc biên tập và cơ chế xuất bản lên YouTube của HaizFlow Daily News.  
> **"Nếu hệ thống bị trật, mất config hoặc không tự động đăng lên YouTube, mở tài liệu này ra hoặc chạy script chẩn đoán là biết chính xác cách khôi phục trong 30 giây."**

---

## I. BẢNG QUY CHIẾU CẤU HÌNH GỐC (GOLDEN CONFIGURATION BASELINE)

File cấu hình hệ thống nằm tại:  
📂 **`runtime/data/daily_news_settings.json`**

### 1. Nội Dung Chuẩn Nguyên Bản (Golden JSON)
```json
{
  "selected_category": "tin_moi",
  "max_topics": 8,
  "aspect_ratio": "16:9",
  "voice_id": "vi-VN-NamMinhNeural",
  "detail_level": "standard",
  "bgm_enabled": true,
  "bgm_volume": 0.08,
  "auto_upload_youtube": true,
  "auto_upload_facebook": false,
  "youtube_privacy": "public",
  "auto_add_to_playlist": true,
  "youtube_playlist_tin_moi": "Bản tin thế giới",
  "youtube_playlist_hope": "Bản tin thế giới",
  "youtube_playlist_viral": "Bản tin thế giới",
  "youtube_playlist_tin_nong": "Bản tin thế giới",
  "schedule_time": "05:30",
  "schedule_wake_up": true,
  "schedules": {
    "tin_moi": {
      "time": "05:30",
      "wake_up": true
    },
    "hope": {
      "time": "11:30",
      "wake_up": true
    },
    "viral": {
      "time": "12:00",
      "wake_up": true
    },
    "tin_nong": {
      "time": "17:30",
      "wake_up": true
    }
  }
}
```

### 2. Ý Nghĩa Các Trường Trọng Yếu
- `auto_upload_youtube: true` -> **BẮT BUỘC BẬT** để pipeline tự động xuất bản sau khi render xong.
- `youtube_privacy: "public"` -> Chế độ công khai ngay khi đăng tải.
- `auto_add_to_playlist: true` -> Tự động đưa video vào danh sách phát tương ứng (`Bản tin thế giới`).
- `bgm_volume: 0.08` -> Âm lượng nhạc nền 8%, nhẹ nhàng và không lấn át giọng đọc BTV.
- `schedules` -> Bản đồ định thời 4 bản tin theo 3 khung giờ chiến lược (Sáng 05:30, Trưa 11:30 & 12:00, Chiều 17:30).

---

## II. BỘ KHUNG KÍCH HOẠT LỊCH BIỂU (WINDOWS TASK SCHEDULER HARNESS)

Hệ thống sử dụng **Windows Task Scheduler** với tiến trình chạy ngầm không cửa sổ `pythonw.exe`.

### 1. Danh Sách 4 Tác Vụ Chuẩn
| STT | Khung giờ | Bản tin | Tên Task trong Windows | Định dạng | Sự kiện | Tham số lệnh |
| :---: | :---: | :--- | :--- | :---: | :---: | :--- |
| 1 | **05:30** | **Tin mới (`tin_moi`)**<br>*(Thế giới + Thể thao)* | `HaizFlow_DailyNews_tin_moi` | 16:9 | 8 tin | `--now --category tin_moi --aspect-ratio 16:9 --max-topics 8 --youtube` |
| 2 | **11:30** | **Tin vui (`hope`)**<br>*(Phát minh & Y khoa)* | `HaizFlow_DailyNews_hope` | 9:16 (Shorts) | 7 tin | `--now --category hope --aspect-ratio 9:16 --max-topics 7 --youtube` |
| 3 | **12:00** | **Tin độc lạ (`viral`)**<br>*(Kỳ thú & Hài hước)* | `HaizFlow_DailyNews_viral` | 9:16 (Shorts) | 8 tin | `--now --category viral --aspect-ratio 9:16 --max-topics 8 --youtube` |
| 4 | **17:30** | **Tin nóng (`tin_nong`)**<br>*(Chiến sự + Công nghệ)* | `HaizFlow_DailyNews_tin_nong` | 16:9 | 8 tin | `--now --category tin_nong --aspect-ratio 16:9 --max-topics 8 --youtube` |

### 2. Đường Dẫn Lệnh Thực Thi Mẫu
```powershell
"C:\projects\HaizFlow-main\.venv\Scripts\pythonw.exe" "C:\projects\HaizFlow-main\scripts\run_daily_news.py" --now --category <category> --aspect-ratio <ar> --max-topics <n> --youtube
```

---

## III. BỘ KHUNG KẾT NỐI YOUTUBE (YOUTUBE INTEGRATION HARNESS)

1. **Tài nguyên kết nối**:
   - Client Secret: `runtime/data/youtube_client_secret.json`
   - OAuth 2.0 Token: `runtime/data/youtube_token.json` (chứa `refresh_token` để tự động làm mới access token vĩnh viễn).
2. **Kênh YouTube xuất bản mục tiêu**:
   - **Tên kênh**: `Vạn Chuyện`
   - **Channel ID**: `UCoim2HeyULY_qaYf7b97_dw`
3. **Quy trình xuất bản tự động**:
   - Sau khi file `.mp4` được render, hàm kiểm tra cờ `should_upload_yt`.
   - Nếu bật, gọi `haizflow.services.youtube_direct.upload_video_to_youtube(...)`.
   - Tải video lên, đặt thumbnail từ file `thumbnail.jpg`, gán vào playlist `Bản tin thế giới`, và cập nhật thông tin link vào `social_publish_manifest.json`.

---

## IV. BỘ KHUNG BIÊN TẬP NỘI DUNG & BỘ LỌC THÉP (EDITORIAL HARNESS)

1. **Luật tối thượng - 0% Tin Việt Nam**:
   - Mọi chuyên mục đều chạy qua `is_vietnam_related()`. Nếu phát hiện từ khóa trong nước, bài viết lập tức bị loại bỏ.
2. **Hạn ngạch đa vùng địa lý (Multi-region Quota)**:
   - Tối thiểu 40% đến 50% sự kiện bắt buộc đến từ các quốc gia láng giềng được người Việt quan tâm: **Trung Quốc, Đông Nam Á (ASEAN), Nga, Nhật Bản, Hàn Quốc**.
   - 50% còn lại là các điểm nóng quốc tế (Mỹ, Châu Âu, Trung Đông, toàn cầu).
3. **Bộ lọc thép Chiến sự (`is_strict_war_news`)**:
   - Ngăn chặn triệt để tình trạng tin thể thao (bóng đá Anh, Chelsea, Arsenal...) hoặc đời tư nhân vật (Vanessa Trump) lọt vào bản tin Chiến sự.
4. **Bộ lọc Thể thao 100% Bóng đá đỉnh cao (`is_non_football_news`)**:
   - Chỉ giữ bóng đá: Ngoại Hạng Anh, Serie A, Bundesliga, La Liga, Ligue 1, Cúp C1, câu chuyện ngôi sao (Mbappe, Haaland, Messi, Ronaldo...) và bóng đá khu vực (Thái Lan, Indo, Trung Quốc, Campuchia). Loại bỏ tuyệt đối các môn thể thao khác (bóng rổ, cricket, F1, v.v.).

---

## V. SỔ TAY CHẨN ĐOÁN & SỬA LỖI TRONG 30 GIÂY ("NẾU TRẬT BIẾT ĐƯỜNG SỬA")

| Hiện tượng lỗi (Symptom) | Nguyên nhân gốc (Root Cause) | Cách sửa & Lệnh khắc phục nhanh |
| :--- | :--- | :--- |
| **1. Buổi sáng không thấy video tự sinh** | Task Scheduler bị tắt hoặc Windows tắt nguồn/ngủ sâu không bật wake up | Chạy lệnh kiểm tra: <br>`schtasks /Query /TN HaizFlow_DailyNews_world`<br>Nếu mất task, tạo lại bằng lệnh mục VI. |
| **2. Video sinh ra nhưng không up lên YouTube** | Thiếu cờ `--youtube` trong lệnh gọi hoặc file `daily_news_settings.json` bị đặt `auto_upload_youtube: false` | Mở `daily_news_settings.json` kiểm tra `"auto_upload_youtube": true`.<br>Hoặc chạy lại task với cờ `--youtube`. |
| **3. Báo lỗi `YouTubeAuthError: Chưa kết nối tài khoản YouTube`** | File `youtube_token.json` bị mất hoặc token Google bị thu hồi quyền | Chạy công cụ đăng nhập lại Google:<br>`.venv\Scripts\python.exe -m haizflow.services.youtube_direct --login` |
| **4. File `daily_news_settings.json` bị mất / lỗi cú pháp** | Bị ghi đè nhầm hoặc hỏng file JSON | Chạy script chẩn đoán tự động sửa lỗi:<br>`.venv\Scripts\python.exe scripts/check_daily_news_harness.py --repair` |
| **5. Gemini không tổng hợp được tin tức (bị rơi về Offline fallback)** | Gemini API Key bị mất khỏi Windows Credential Manager | Chạy lệnh kiểm tra key:<br>`.venv\Scripts\python.exe scripts/check_daily_news_harness.py` |
| **6. Bản tin chiến sự lẫn tin bóng đá hoặc thời sự** | Danh sách feed chiến sự bị sửa nhầm sang feed tổng hợp | Kiểm tra hàm `is_strict_war_news()` trong `daily_news.py`. |

---

## VI. BỘ LỆNH KHÔI PHỤC TOÀN BỘ LỊCH TRÌNH 1-CLICK (ONE-CLICK RESTORE)

Nếu bất kỳ lúc nào toàn bộ lịch biểu trong Windows Task Scheduler bị xóa hoặc mất cấu hình, hãy mở PowerShell tại thư mục dự án và chạy lần lượt các lệnh sau:

```powershell
# 1. Kích hoạt môi trường Python
$env:PYTHONIOENCODING="utf-8"

# 2. Khôi phục 4 Task theo chiến lược chuẩn (Tự động gỡ bỏ task cũ và đặt lịch chuẩn)
.venv\Scripts\python.exe scripts/manage_schedule.py --clean-legacy
.venv\Scripts\python.exe scripts/manage_schedule.py --category tin_moi  --time 05:30 --aspect-ratio 16:9 --max-topics 8 --wake --youtube
.venv\Scripts\python.exe scripts/manage_schedule.py --category hope      --time 11:30 --aspect-ratio 9:16 --max-topics 7 --wake --youtube
.venv\Scripts\python.exe scripts/manage_schedule.py --category viral     --time 12:00 --aspect-ratio 9:16 --max-topics 8 --wake --youtube
.venv\Scripts\python.exe scripts/manage_schedule.py --category tin_nong  --time 17:30 --aspect-ratio 16:9 --max-topics 8 --wake --youtube

# Hoặc 1 lệnh tự động kiểm tra và sửa toàn diện:
.venv\Scripts\python.exe scripts/check_daily_news_harness.py --repair
```

---

## VII. CÔNG CỤ CHẨN ĐOÁN TOÀN DIỆN (HARNESS HEALTH CHECK SCRIPT)

Bất kỳ lúc nào bạn muốn kiểm tra sức khỏe của luồng tự động từ đầu đến cuối, chỉ cần chạy 1 dòng lệnh duy nhất:

```powershell
.venv\Scripts\python.exe scripts/check_daily_news_harness.py
```

Script sẽ tự động quét:
1. File cấu hình `daily_news_settings.json` (tự động tạo lại nếu mất).
2. Kiểm tra kết nối tới kênh YouTube và trạng thái Token Google.
3. Kiểm tra tính hợp lệ của Google Gemini Flash API Key.
4. Kiểm tra sự tồn tại và tham số lệnh của cả 6 Task trong Windows Task Scheduler.
5. In ra bảng kết quả màu sắc trực quan (XANH = Tốt, ĐỎ = Cần sửa kèm hướng dẫn).

---

## VIII. BỘ QUY CHUẨN THIẾT KẾ THUMBNAIL THEO CHỦ ĐỀ & 7 NGÀY TRONG TUẦN (THUMBNAIL THEMING HARNESS)

Hệ thống tạo Thumbnail tự động áp dụng quy tắc nhận diện thương hiệu nhất quán, chuyên nghiệp và có chiều sâu nội dung.

### 1. Hệ Thống 7 Theme Màu Chữ Thumbnail Cho 7 Ngày Trong Tuần (Chỉ áp dụng cho Video 16:9)
- **Quy tắc phối màu**: Chữ gồm 2 màu trắng và màu chủ đạo. Phần màu trắng (`#FFFFFF`) luôn giữ nguyên cho các dòng sau; phần màu chủ đạo (dòng đầu / hook chính) sẽ tự động thay đổi theo thứ trong tuần:

| Thứ trong tuần | Tên Theme | Mã Màu Hex | Mã RGB | Triết lý & Định hướng nội dung |
| :---: | :--- | :---: | :---: | :--- |
| **Thứ Hai** | **Thanh Mộc** | `#2E8B57` | `(46, 139, 87)` | Xanh ngọc · Khởi đầu, sinh trưởng, những tin mới và xu hướng mới. |
| **Thứ Ba** | **Xích Hỏa** | `#C62828` | `(198, 40, 40)` | Đỏ son · Tin nóng, thời sự, sự kiện đáng chú ý. |
| **Thứ Tư** | **Hoàng Thổ** | `#D4A72C` | `(212, 167, 44)` | Vàng đất · Kinh tế, đời sống, những câu chuyện thiết thực. |
| **Thứ Năm** | **Bạch Kim** | `#C4C9D0` | `(196, 201, 208)` | Bạc trắng · Công nghệ, khoa học, khám phá và sáng tạo. |
| **Thứ Sáu** | **Huyền Thủy** | `#202A44` | `(32, 42, 68)` | Đen xanh đêm · Bí ẩn, điều tra, hồ sơ và những chuyện chưa có lời giải. |
| **Thứ Bảy** | **Lam Ảnh** | `#4169A1` | `(65, 105, 161)` | Xanh chàm · Game, phim ảnh, giải trí, thế giới giả tưởng. |
| **Chủ Nhật** | **Vàng Nắng Cà Phê** | `#F4C95D` | `(244, 201, 93)` | Ấm áp, thư thái, tích cực. |

### 2. Bảng Màu Tiêu Đề Bản Tin (Category Bulletin / Title Banner Color Palette)
Áp dụng cho thanh tiêu đề trên Thumbnail (cả Video 16:9 và nhãn viên thuốc của Shorts 9:16):

| Chuyên mục | Tiêu đề hiển thị | Mã Màu Hex | Mã RGB | Tính chất & Ngôn ngữ thiết kế |
| :--- | :--- | :---: | :---: | :--- |
| **Thời sự (`world`)** | `BẢN TIN THỜI SỰ` | `#17365D` | `(23, 54, 93)` | Xanh navy — nghiêm túc, đáng tin cậy, chuyên nghiệp. |
| **Công nghệ (`tech`)** | `BẢN TIN CÔNG NGHỆ` | `#087F8C` | `(8, 127, 140)` | Xanh teal — hiện đại, kỹ thuật số, đổi mới. |
| **Chiến sự (`war`)** | `BẢN TIN CHIẾN SỰ` | `#9F2028` | `(159, 32, 40)` | Đỏ sẫm — khẩn cấp, mạnh mẽ, dễ nhận diện (không dùng đỏ neon). |
| **Thể thao (`sports`)** | `BẢN TIN BÓNG ĐÁ` | `#176B3A` | `(23, 107, 58)` | Xanh sân cỏ — thể thao, năng lượng, cạnh tranh. |
| **Tin lạ (`viral`)** | `TIN NÓNG & ĐỘC LẠ` | `#663399` | `(102, 51, 153)` | Tím đậm — khác biệt, dí dỏm, hơi kỳ quặc. |
| **Tin vui (`hope`)** | `TIN VUI` | `#B85C00` | `(184, 92, 0)` | Cam đất — ấm áp, tích cực, tạo cảm giác thân thiện. |

