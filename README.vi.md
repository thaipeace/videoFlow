<div align="center">
  <img src="src/haizflow/desktop/assets/branding/haizflow-mark.png" width="96" alt="Logo HaizFlow / videoFlow">
  <h1>videoFlow (HaizFlow Edition)</h1>
  <p><strong>Ứng dụng Windows toàn diện để tải, dịch, tạo phụ đề, lồng tiếng, sản xuất bản tin tự động và biến văn bản / truyện chữ thành video AI.</strong></p>
  <p><a href="https://github.com/thaipeace/videoFlow">Repository GitHub</a> · <a href="docs/user-guide.vi.md">Hướng dẫn sử dụng</a> · <a href="docs/support.vi.md">Trợ giúp</a> · <a href="README.md">English</a></p>
</div>

## Giới thiệu

**videoFlow** (phát triển từ nền tảng HaizFlow) là giải pháp sản xuất video tự động hóa mạnh mẽ trên Windows. Ứng dụng hỗ trợ quy trình khép kín từ dịch thuật, lồng tiếng, tạo phụ đề đa ngôn ngữ cho đến **sản xuất bản tin thời sự tự động 100%** và **chuyển thể truyện chữ / bài viết thành video điện ảnh AI**.

Ứng dụng cung cấp các chế độ làm việc linh hoạt:
- **Tự động & Hàng loạt:** Xử lý hàng loạt video với các model AI nhận dạng, dịch thuật và lồng tiếng chạy offline trên máy hoặc qua cloud.
- **Trình sửa Thủ công:** Cho phép tinh chỉnh từng đoạn phụ đề, timeline âm thanh và lồng tiếng trước khi xuất bản.
- **Bản tin tự động (Daily News):** Hệ thống tin tức tự động hóa từ khâu quét nguồn RSS, biên tập kịch bản AI, dựng đồ họa truyền hình chuyên nghiệp đến tự động đăng tải lên YouTube theo lịch biểu Windows.
- **Đọc truyện AI (Article-to-Video):** Biến văn bản, tiểu thuyết, truyện ngắn thành video với giọng đọc truyền cảm, tạo hình nhân vật đồng nhất và hiệu ứng chuyển cảnh điện ảnh.

---

## Chức năng chính

| Chức năng | Bạn có thể làm gì? |
| --- | --- |
| 📰 **Bản tin tự động (Mới)** | Thu thập RSS quốc tế đa nguồn độc lập, Gemini AI biên tập kịch bản, tự động dựng video chuẩn truyền hình (Ticker, Logo VCH, Intro 3D, CTA) và hẹn giờ chạy ngầm Windows Task Scheduler đăng thẳng lên YouTube. |
| 📖 **Đọc truyện AI (Mới)** | Biến văn bản, tiểu thuyết, truyện chữ thành video với giọng đọc truyền cảm, phân cảnh AI thông minh, giữ diện mạo nhân vật 2D đồng nhất qua các cảnh và chuyển động Ken Burns mượt mà. |
| **Dịch video đa ngữ** | Nhận dạng lời nói bằng Whisper; dịch bằng HY-MT2 offline trên máy hoặc Gemini Flash. Cho phép xem trước và sửa bản dịch. |
| **Tạo phụ đề & Karaoke** | Tự động tạo phụ đề từ âm thanh gốc; chỉnh sửa nội dung, mốc thời gian, font chữ Bangers và hiệu ứng highlight karaoke bắt mắt. |
| **Lồng tiếng AI & Voice Clone** | Tạo giọng đọc tự nhiên cho văn bản đã dịch qua Edge-TTS, VieNeu hoặc OmniVoice (sao chép mẫu giọng tham chiếu). |
| **Xử lý tự động & Hàng loạt** | Áp dụng thiết lập chung cho hàng loạt video, tự động chạy nhận dạng, dịch, lồng tiếng và che phụ đề theo hàng đợi. |
| **Che phụ đề gốc (OCR)** | Dùng OCR định vị vùng chữ gốc, tự động làm mờ hoặc vá nền thông minh để che phụ đề cũ. |
| **Nhận diện nhiều người nói** | Phân nhóm người nói trong video (Speaker Diarization) và gán từng giọng đọc riêng biệt cho từng nhân vật. |
| **Tải video hàng loạt** | Phân tích liên kết video, danh sách kênh hoặc trang cá nhân công khai (hỗ trợ Douyin, YouTube, v.v.) và tải về máy. |
| **Đăng mạng xã hội** | Chuẩn bị nội dung, tiêu đề, thẻ tag và xuất bản tự động qua Zernio hoặc tích hợp YouTube Data API trực tiếp. |

---

## ✨ Tính năng mới: Bản tin tự động (Automated Daily News Broadcast Pipeline)

Hệ thống cho phép vận hành một kênh tin tức YouTube tự động 100%, không cần can thiệp thủ công hàng ngày:

### 1. Chiến lược xuất bản 3 khung giờ (4 bản tin mỗi ngày)
* **05:30 Sáng — Tin Mới (`tin_moi`, 16:9 Ngang 1080p):** Hợp nhất Thời sự Thế giới và Thể thao đỉnh cao. Phong cách truyền hình quốc tế hiện đại, intro địa cầu 3D xoay chuyển, gam màu xanh Navy `#17365D`.
* **11:30 Trưa — Shorts Tin Vui (`hope`, 9:16 Dọc):** Điểm tin phát minh khoa học, y học, năng lượng xanh và câu chuyện truyền cảm hứng (nhịp điệu 45–55 giây).
* **12:00 Trưa — Shorts Tin Độc Lạ (`viral`, 9:16 Dọc):** Tin tức kỳ thú, trào lưu mạng xã hội, tình huống hài hước dí dỏm.
* **17:30 Chiều — Tin Nóng (`tin_nong`, 16:9 Ngang 1080p):** Hợp nhất Điểm nóng Chiến sự / Địa chính trị và Đột phá Công nghệ / Bán dẫn. Phong cách phòng tác chiến quân sự, radar quét bảo mật, gam màu đỏ sẫm `#9F2028`.

### 2. Cơ chế thu thập độc lập & Bộ lọc nội dung thép
* **Thu thập riêng biệt từng chuyên mục:** Tin thời sự lấy từ Reuters, AP, BBC, NPR, DW; Tin thể thao lấy từ BBC Sport, Sky Sports; Tin chiến sự lấy từ ISW, Al Jazeera War; Tin công nghệ lấy từ The Verge, TechCrunch. Các luồng lấy tin chạy riêng biệt để đảm bảo chất lượng cao nhất trước khi AI tổng hợp.
* **Luật tối thượng 0% Tin Việt Nam:** Tự động loại bỏ mọi tin tức nội địa để giữ góc nhìn thời sự thuần quốc tế.
* **Bộ lọc thép Chiến sự:** Loại bỏ triệt để tin thể thao hoặc đời tư nghệ sĩ lọt vào bản tin quân sự.
* **Bộ lọc Thể thao 100% Bóng đá:** Tập trung trọn vẹn vào Top 5 giải VĐQG châu Âu (Ngoại Hạng Anh, La Liga, Serie A, Bundesliga, Ligue 1) + Cúp C1, câu chuyện ngôi sao (Mbappe, Haaland, Messi, CR7...) và bóng đá láng giềng khu vực (Thái Lan, Indonesia, Trung Quốc, Campuchia).

### 3. Đồ họa truyền hình & Tuân thủ YouTube YPP (Chống Reused Content)
* **Scene 0 Direct Hook:** Mở đầu trực tiếp bằng 1–2 câu kịch tính gây tò mò, xóa bỏ hoàn toàn các câu chào rập khuôn sáo rỗng.
* **Thanh Ticker cuộn chữ:** Chạy tóm tắt các dòng tin nóng dưới đáy màn hình kèm nhãn chuyên mục nổi bật.
* **Nhận diện thương hiệu:** Tích hợp logo VCH góc màn hình, watermark mờ chống đối thủ re-upload, và hoạt ảnh nút Đăng ký kênh (Subscribe CTA) kèm hiệu ứng âm thanh.
* **Thumbnail chuẩn CTR 7 ngày:** Tự động đổi màu chữ chủ đạo theo phong thủy / lịch 7 ngày trong tuần.

### 4. Vận hành tự động ngầm 100% qua Windows Task Scheduler
* Tích hợp sâu vào Windows Task Scheduler chạy ngầm bằng `pythonw.exe`.
* Hỗ trợ tự động **đánh thức máy tính từ trạng thái Sleep** (`WakeToRun = True`, `powercfg RTCWAKE = 1`).
* Tự động tải lên YouTube qua OAuth2 (tiêu đề, mô tả, hashtag, thumbnail, gắn vào playlist chuẩn).
* Công cụ chẩn đoán & tự sửa lỗi 1-click: `python scripts/check_daily_news_harness.py --repair`.

---

## ✨ Tính năng mới: Đọc truyện & Biến bài viết thành Video AI (Article-to-Video)

Module biến văn bản, tiểu thuyết hoặc bài báo bất kỳ thành video clip minh họa hoàn chỉnh:

* **Phân tích kịch bản thông minh (Story Director):** AI phân tích nội dung, chia tách câu đọc tự nhiên và chấm điểm cao trào cảm xúc (*Visual Impact Score*) để lựa chọn những khoảnh khắc đắt giá nhất sinh ảnh minh họa.
* **Kho nhân vật 2D chuẩn (Character Presets & Consistency):** Tích hợp thư viện nhân vật 2D với bộ từ khóa neo diện mạo (`prompt_anchor`), đảm bảo nhân vật chính giữ nguyên nét mặt, trang phục và phong cách qua từng cảnh quay.
* **Đa dạng phong cách đồ họa:** Hỗ trợ tạo ảnh minh họa theo nhiều phong cách: Anime 2D, Manhwa Webtoon, Tranh màu nước, Cyberpunk, Comic... qua Imagen 3 API hoặc Local Stable Diffusion.
* **Hiệu ứng chuyển động Ken Burns:** Biến ảnh tĩnh thành cảnh quay sống động với hiệu ứng lia máy (pan) và zoom chậm mượt mà bằng FFmpeg.
* **Lồng tiếng truyền cảm:** Tùy chọn giọng đọc diễn cảm qua Edge-TTS, VieNeu giọng Việt tự nhiên, hoặc nhân bản giọng nói theo mẫu có sẵn.
* **Hỗ trợ đa khung hình:** Tùy chọn xuất video chuẩn ngang **16:9** (YouTube) hoặc chuẩn dọc **9:16** (Shorts / TikTok / Reels).

---

## Hình ảnh giao diện

[Trang chủ](#trang-chủ) · [Xử lý tự động](#xử-lý-tự-động) · [Trình sửa thủ công](#trình-sửa-thủ-công) · [Bản tin tự động](#bản-tin-tự-động) · [Đọc truyện AI](#đọc-truyện-ai) · [Tải xuống](#tải-xuống) · [Đăng mạng xã hội](#đăng-mạng-xã-hội) · [Cài đặt](#cài-đặt)

### Trang chủ
Tìm dự án gần đây, lọc theo loại và tạo dự án mới.
![Trang chủ với các thẻ dự án và bộ lọc tìm kiếm](docs/images/screenshots/home-2026-10-11.png)

### Xử lý tự động
Chọn model nhận dạng, dịch và giọng đọc; thiết lập che phụ đề, âm thanh, nhạc nền và watermark.
![Trang xử lý tự động với video nguồn và các thiết lập ngôn ngữ, giọng đọc](docs/images/screenshots/automatic-2026-10-14.png)

### Trình sửa thủ công
So sánh video nguồn và kết quả, chạy từng bước độc lập, chia đoạn trên timeline Kết quả, nhập SRT và xuất phụ đề gốc hoặc đã dịch.
![Trình sửa thủ công với preview, bảng xử lý và timeline phụ đề, âm thanh](docs/images/screenshots/manual-editor-2026-10-14.png)

### Bản tin tự động (Mới)
Trung tâm quản lý sản xuất bản tin thời sự: chọn chuyên mục, thiết lập số lượng sự kiện, xem trước kịch bản, quản lý lịch trình 4 khung giờ và cấu hình xuất bản YouTube.

### Đọc truyện AI (Mới)
Không gian làm việc chuyển thể bài viết: nhập nội dung truyện, chọn giọng đọc, phong cách minh họa, chọn nhân vật 2D chuẩn và tạo video hoàn chỉnh.

### Tải xuống
Kiểm tra liên kết video, kênh hoặc âm thanh, xem trước danh sách và chọn các video cần tải (hỗ trợ Douyin, YouTube, v.v.).
![Trang tải xuống với phiên Douyin và danh sách video có thể chọn](docs/images/screenshots/downloads.png)

### Đăng mạng xã hội
Thêm video đã xử lý từ dự án vào hàng đợi và chuẩn bị bài đăng cho tài khoản đã kết nối qua Zernio hoặc YouTube.
![Trang đăng mạng xã hội với tài khoản, hàng đợi bài đăng và hộp chọn video từ dự án](docs/images/screenshots/social-publishing.png)

### Cài đặt
Chọn ngôn ngữ giao diện và chế độ CPU/GPU. Quản lý API key (Gemini, Zernio) và các gói tài nguyên AI.
![Trang cài đặt với ngôn ngữ, bộ xử lý, giữ model sẵn sàng và kiểm tra cập nhật](docs/images/screenshots/settings.png)

---

## Dịch trên máy, không cần trả phí API theo lượt

Whisper và HY-MT2 chạy trực tiếp trên máy sau khi cài gói tài nguyên, không cần API key hoặc phí dịch theo lượt gọi. Gemini Flash là lựa chọn bổ sung cho dịch thuật trực tuyến và biên tập kịch bản bản tin / truyện ngắn.

Máy không có GPU NVIDIA vẫn dùng được các lựa chọn CPU tối ưu. Với GPU NVIDIA tương thích, bạn có thể kích hoạt các model GPU để tăng tốc độ xử lý vượt trội.

---

## Hướng dẫn cài đặt & Khởi động nhanh

### Yêu cầu hệ thống
* Windows 10 (version 1809 trở lên) hoặc Windows 11 x64.
* RAM tối thiểu 16 GB.
* GPU NVIDIA (tùy chọn): Tối thiểu 4 GB VRAM để chạy các model AI tăng tốc (CUDA).

### Chạy từ mã nguồn (Dành cho Developer)
```powershell
# 1. Clone repository
git clone git@github.com:thaipeace/videoFlow.git
cd videoFlow

# 2. Khởi tạo môi trường ảo Python 3.12+
python -m venv .venv
.venv\Scripts\activate

# 3. Cài đặt các gói phụ thuộc
pip install -r requirements.txt

# 4. Khởi động ứng dụng giao diện Desktop
python haizflow_desktop.py
```

### Quản lý lịch bản tin tự động (CLI)
```powershell
# Kiểm tra sức khỏe toàn bộ luồng bản tin tự động
python scripts/check_daily_news_harness.py

# Tự động sửa chữa và đăng ký lịch Windows Task Scheduler
python scripts/check_daily_news_harness.py --repair

# Chạy thử 1 bản tin ngay lập tức (Test nhanh)
python scripts/run_daily_news.py --now --category tin_moi --quick-test
```

---

## Giấy phép và bản quyền

videoFlow kế thừa kiến trúc từ dự án HaizFlow gốc của tác giả **Mạch Hồng Hải**. Phiên bản mở rộng này bổ sung module Bản tin tự động hóa truyền hình và module Đọc truyện AI.

* Mã nguồn tuân thủ điều khoản cấp phép của dự án gốc [LICENSE](LICENSE).
* Model OmniVoice chỉ được cấp phép cho mục đích phi thương mại.
* Dự án sử dụng Qt/PySide (LGPL), FFmpeg (GPL/LGPL), Edge-TTS và các thư viện mã nguồn mở liên quan. Xem chi tiết tại [NOTICE](NOTICE) và [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
