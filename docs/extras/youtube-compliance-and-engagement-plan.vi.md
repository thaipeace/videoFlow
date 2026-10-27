# Kế Hoạch Cải Tiến Kênh YouTube Chuẩn Hóa YPP & Đột Phá Tương Tác
## (YouTube Compliance, Anti-Reused Content & High-CTR Engagement Plan)

> **Dự án**: HaizFlow - Automated Daily News Broadcast Pipeline  
> **Kênh YouTube**: Vạn Chuyện (`@vanchuyen-102`)  
> **Playlist mục tiêu**: Bản tin thế giới (`PLOUagwqnThxE`)  
> **Mục tiêu cốt lõi**: Vượt qua rào cản kiểm duyệt YPP (chống lỗi Reused Content & Low-effort Automated Content), bảo vệ khả năng bật kiếm tiền lâu dài và tăng đột biến tỷ lệ nhấp chuột (CTR), thời lượng giữ chân người xem (Audience Retention).

---

## I. Phân Tích Thực Trạng & Nguyên Tắc "Bảo Toàn Hệ Thống"

### 1. Bản chất thuật toán kiểm duyệt YouTube (2024 - 2026)
YouTube **không cấm AI**, nhưng thuật toán AI Classifier và đội ngũ Reviewer sẽ từ chối kiếm tiền nếu video dính phải các dấu hiệu sau:
1. **Acoustic Fingerprint trùng lặp**: Giọng đọc TTS thô từ Edge-TTS (`vi-VN-NamMinhNeural` / `vi-VN-HoaiMyNeural`) không qua xử lý âm học (Equalizer/Pitch/Compressor), bị hàng vạn kênh spam dùng chung.
2. **Kịch bản "Đọc lại bài báo"**: Thiếu giá trị gia tăng (*Transformative Value*), không có câu hook sắc sảo, mở bài bằng những lời chào sáo rỗng (*"Chào mừng quý vị..."*).
3. **Thị giác tĩnh dạng slide ảnh**: Chuỗi ảnh tĩnh Wikimedia lướt nhẹ đơn điệu, phụ đề SRT chữ trắng dưới đáy màn hình như video tự động không có công sức biên tập.
4. **Tiêu đề & Thumbnail công thức nhàm chán**: Tiêu đề dài dòng chứa cụm *"Toàn Cảnh Ngày DD/MM/YYYY"* làm lu mờ tin nóng, thumbnail không kích thích trí tò mò.

### 2. Cam Kết Bảo Toàn Cấu Hình Đã Chốt (Non-Negotiable Baseline)
Toàn bộ quá trình nâng cấp cam kết **KHÔNG LÀM MẤT HOẶC SAI LỆCH** các cấu hình đã vận hành chuẩn xác:
- **Lịch tự động Windows Task Scheduler**: 
  - `05:00` (Thời sự thế giới)
  - `05:25` (Bản tin công nghệ)
  - `05:50` (Bản tin bóng đá)
  - `06:30` (Tin lạ & Nóng Shorts)
- **Cơ chế Wake PC**: Đánh thức máy tính từ trạng thái Sleep (`WakeToRun = True`).
- **Tỉ lệ khung hình (Aspect Ratio)**:
  - 3 bản tin đầu: Chuẩn ngang **16:9** (1080p).
  - Bản tin viral: Chuẩn dọc **9:16** (Shorts).
- **Xuất bản YouTube tự động**:
  - Quyền OAuth2 và token hợp lệ.
  - Chế độ hiển thị: **Công khai (Public)**.
  - Tự động gắn vào playlist: **"Bản tin thế giới"** (`PLOUagwqnThxE`).

---

## II. Lộ Trình Triển Khai 5 Giai Đoạn (Phased Implementation Plan)

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             LỘ TRÌNH 5 GIAI ĐOẠN                                 │
├─────────────────┬─────────────────┬─────────────────┬────────────────────────────┤
│  PHASE 1        │  PHASE 2        │  PHASE 3        │  PHASE 4      │  PHASE 5   │
│  AI Hook &      │  Branding Logo  │  News Ticker    │  Thumbnail &  │  Audio     │
│  Prompt Giật Gân│  & Watermark    │  Chạy Chữ Đáy   │  Tiêu Đề CTR  │  Mastering │
└─────────────────┴─────────────────┴─────────────────┴───────────────┴────────────┘
```

---

### GIAI ĐOẠN 1: Tối Ưu Kịch Bản AI & Đột Phá Lời Mở Đầu (Hook 3 Giây Đầu)

#### 1. Mục tiêu
- Xóa bỏ hoàn toàn câu chào mở đầu rập khuôn (*"Chào mừng quý vị và các bạn đã quay trở lại..."*).
- 3 - 5 giây đầu tiên đập ngay vào tai người xem một sự kiện gây sốc, kịch tính hoặc câu hỏi tò mò tột đỉnh.
- Thay đổi cấu trúc tiêu đề: Đưa từ khóa nóng nhất lên đầu, loại bỏ cụm từ dài dòng *"Toàn Cảnh Ngày"*, giữ định dạng chuẩn: `[Tin Hot / Sự Kiện Sốc Nhất] - Bản tin thế giới DD/MM/YYYY`.

#### 2. Vị trí can thiệp mã nguồn
- Tệp tin: [src/haizflow/services/daily_news.py](file:///c:/projects/HaizFlow-main/src/haizflow/services/daily_news.py) (Hàm `synthesize_news_script_with_gemini` và cấu hình prompt).

#### 3. Kỹ thuật triển khai
- **Cập nhật Persona & Quy tắc biên tập vàng cho Gemini**:
  ```python
  # Quy tắc mới trong Prompt:
  """
  QUY TẮC MỞ ĐẦU ĐỘT PHÁ (NO GREETING - DIRECT HOOK):
  - TUYỆT ĐỐI CẤM các câu chào hỏi rườm rà như: "Chào mừng quý vị...", "Xin kính chào...", "Hôm nay chúng ta cùng điểm qua...".
  - Scene 0 (Hook mở đầu) BẮT BUỘC bắt đầu ngay bằng 1-2 câu giật gân, kịch tính nhất về sự kiện chấn động nhất rạng sáng nay để giữ chân người xem ngay trong 3 giây đầu tiên!
  - Ví dụ Hook: "Một quyết định chưa từng có vừa được đưa ra tại Washington rạng sáng nay, đe dọa làm rung chuyển toàn bộ thị trường tài chính toàn cầu. Liệu đây là bước ngoặt hay khởi đầu cho một cuộc khủng hoảng mới? Cùng điểm qua những diễn biến nóng nhất ngay sau đây."
  
  QUY TẮC TIÊU ĐỀ VIDEO YOUTUBE GÂY TÒ MÒ:
  - BỎ HẲN chữ "Toàn Cảnh Ngày".
  - Cấu trúc: "[Tin Nóng/Gây Sốc Nhất Nhất Quán Dưới 8 Từ] - Bản Tin Thế Giới [Ngày/Tháng/Năm]"
  - Ví dụ chuẩn: "Cú Sốc Giá Vàng Lao Dốc - Bản Tin Thế Giới 24/10/2026"
  - Đảm bảo phần chữ giật gân nằm ở đầu để không bị che khuất trên màn hình điện thoại.
  """
  ```
- **Bổ sung trường dữ liệu trong JSON trả về của Gemini**:
  ```json
  {
    "title": "Cú Sốc Giá Vàng Lao Dốc - Bản Tin Thế Giới 24/10/2026",
    "thumbnail_hook": "SỐC: ĐÁY MỚI?",
    "ticker_summary": "Giá vàng thế giới lao dốc không phanh về đáy mới | Căng thẳng Trung Đông leo thang báo động đỏ | Siêu AI OpenAI bất ngờ công bố tính năng mới",
    "scenes": [...]
  }
  ```

#### 4. Tiêu chí nghiệm thu (Acceptance Criteria)
- [ ] Phân cảnh đầu tiên (Scene 0) không có bất kỳ chữ "Chào mừng" nào, mở đầu trực tiếp bằng tin giật gân.
- [ ] Tiêu đề video không còn chữ "Toàn Cảnh Ngày", tin hot nằm ngay đầu.
- [ ] Xuất hiện trường `thumbnail_hook` (dưới 8 từ, in hoa) và `ticker_summary` trong manifest.

---

### GIAI ĐOẠN 2: Thiết Kế Bộ Nhận Diện Branding (Logo VCH & Watermark Mờ)

#### 1. Mục tiêu
- Thêm **Logo "VCH"** chuyên nghiệp ở góc trên bên trái màn hình (Top-Left), phong cách kênh tin tức truyền hình quốc tế.
- Thêm **Watermark "Vạn Chuyện"** siêu mờ (độ trong suốt ~15-20%) ở vùng dưới màn hình, vị trí ngẫu nhiên nhẹ giữa các bản tin để chống đối thủ re-upload hàng loạt mà không gây khó chịu cho mắt người xem.

#### 2. Vị trí can thiệp mã nguồn
- Tệp tin: [src/haizflow/pipeline/slide_composer.py](file:///c:/projects/HaizFlow-main/src/haizflow/pipeline/slide_composer.py) (Module tạo layer phủ đồ họa).
- Thư mục lưu trữ asset: `runtime/resource_packs/branding/` hoặc tạo động bằng module Pillow/FFmpeg filter.

#### 3. Kỹ thuật triển khai
- **Vẽ Logo Badge "VCH"**:
  - Kích thước: `120x48 px` (cho video 1080p).
  - Vị trí: `x = 40px, y = 40px` (Top-Left, cách lề an toàn).
  - Thiết kế: Nền hộp màu đỏ tin tức (`#E50914` hoặc `#D32F2F`) với viền bo góc nhẹ (`radius=6`), chữ **"VCH"** in hoa màu trắng nổi bật, font Bold không chân (Roboto/Inter/Montserrat).
- **Vẽ Watermark Mờ "Vạn Chuyện"**:
  - Text: `VẠN CHUYỆN`
  - Alpha: `0.15` (chỉ hiển thị mờ ảo khi nhìn kỹ, không che khuất hình ảnh tư liệu).
  - Vị trí ngẫu nhiên có kiểm soát:
    - Slot 1: Góc dưới bên phải (`x = Width - text_w - 60, y = Height - 140`)
    - Slot 2: Góc dưới chính giữa (`x = (Width - text_w) / 2, y = Height - 150`)
    - Slot 3: Lệch phải vừa phải (`x = Width - text_w - 200, y = Height - 130`)
- **Tích hợp FFmpeg Filtergraph**:
  ```bash
  # Tích hợp overlay logo và watermark trực tiếp vào lệnh render slide hoặc filter concatenate
  ffmpeg -i input.mp4 -i logo_vch.png -filter_complex "[0:v][1:v]overlay=40:40[v_logo]; [v_logo]drawtext=text='VẠN CHUYỆN':fontcolor=white@0.15:fontsize=22:x=w-tw-80:y=h-130[outv]" -map "[outv]" ...
  ```

#### 4. Tiêu chí nghiệm thu
- [ ] Tất cả frame video đều có logo VCH đỏ-trắng sắc nét góc trên bên trái.
- [ ] Chữ watermark "Vạn Chuyện" hiển thị mờ trang nhã ở đáy, không gây cản trở trải nghiệm xem.
- [ ] Khung hình 16:9 và 9:16 tự động tính toán toạ độ an toàn (Safe Margin) tương ứng.

---

### GIAI ĐOẠN 3: Băng Chuyền Chạy Chữ Tin Tức (News Ticker Marquee Bar)

#### 1. Mục tiêu
- Thay thế hoàn toàn phụ đề chữ tĩnh bằng **Thanh chạy chữ tóm tắt tin tức (News Ticker)** cuộn mượt mà từ phải sang trái ở sát đáy màn hình như đài CNN, BBC, VTV24.
- Tóm tắt liên tục toàn bộ các sự kiện quan trọng trong bản tin, tạo cảm giác một hãng thông tấn chuyên nghiệp thực thụ.

#### 2. Vị trí can thiệp mã nguồn
- Tệp tin: [src/haizflow/pipeline/slide_composer.py](file:///c:/projects/HaizFlow-main/src/haizflow/pipeline/slide_composer.py).
- Tệp tin: [src/haizflow/schemas/article_video.py](file:///c:/projects/HaizFlow-main/src/haizflow/schemas/article_video.py).

#### 3. Kỹ thuật triển khai
- **Cấu trúc đồ họa Ticker Bar (Dải đáy màn hình)**:
  - Chiều cao dải băng: `60px` (đối với video 1080p).
  - Vị trí: `y = Height - 70px`.
  - **Khối cố định bên trái (Static Badge)**:
    - Nền: Đỏ đậm (`#CC0000`) hoặc Xanh đậm thương hiệu.
    - Chữ: `"TIN MỚI 24H"` hoặc `"ĐIỂM TIN"`.
    - Chiều rộng cố định: `180px`.
  - **Dải cuộn nội dung (Scrolling Area)**:
    - Nền: Đen mờ sang trọng (`rgba(10, 10, 15, 0.85)`).
    - Nội dung: Chuỗi `ticker_summary` từ Gemini (các tin nối nhau bằng dấu chấm tròn hoặc gạch đứng phát sáng ` | `).
- **Thuật toán cuộn chữ liên tục bằng FFmpeg**:
  ```
  x = 'w - mod(t * SPEED, text_total_width + w)'
  ```
  - Trong đó `SPEED = 120` px/giây (tốc độ đọc mắt người lướt qua dễ chịu nhất).
  - Dòng chữ sẽ tự động lặp lại tuần hoàn xuyên suốt video từ đầu đến cuối mà không bị đứt đoạn.

#### 4. Tiêu chí nghiệm thu
- [ ] Dưới đáy video có dải băng tin tức chạy chữ từ phải qua trái trơn tru 30fps.
- [ ] Không còn phụ đề tĩnh che giữa màn hình gây rối mắt.
- [ ] Chữ chạy rõ ràng, dễ đọc trên cả màn hình máy tính lẫn điện thoại.

---

### GIAI ĐOẠN 4: Thumbnail AI Gây Tò Mò & Tối Ưu CTR (< 8 Từ)

#### 1. Mục tiêu
- Tự động tạo ảnh Thumbnail sắc nét, có dòng chữ gây tò mò cực đại (Curiosity Hook) dựa trên trường `thumbnail_hook` do Gemini tạo ra.
- Đảm bảo chữ trên thumbnail:
  - Tối đa 6 - 8 từ.
  - Từ ngữ giật gân, khơi gợi câu hỏi mở (*"SỐC: ĐÁY MỚI?", "BƯỚC NGOẶT LỊCH SỬ?", "CÚ LỪA NGHÌN TỶ?"*).
  - Font chữ in hoa siêu đậm (Impact / Montserrat ExtraBold / Bebas Neue), màu vàng chanh hoặc trắng viền đen, đổ bóng nổi 3D.
  - Vị trí đặt chữ không bị che bởi timestamp thời lượng của YouTube (góc dưới bên phải).

#### 2. Vị trí can thiệp mã nguồn
- Tệp tin: [src/haizflow/services/daily_news.py](file:///c:/projects/HaizFlow-main/src/haizflow/services/daily_news.py) (Tạo ảnh thumbnail `thumbnail.jpg`).
- Tệp tin: [src/haizflow/services/youtube_direct.py](file:///c:/projects/HaizFlow-main/src/haizflow/services/youtube_direct.py) (Hỗ trợ upload thumbnail tự động qua YouTube API `thumbnails.set`).

#### 3. Kỹ thuật triển khai
- **Quy tắc tạo ảnh Thumbnail**:
  1. Chọn bức ảnh ấn tượng nhất trong các phân cảnh sự kiện chính (hoặc ảnh AI cinematic).
  2. Áp dụng hiệu ứng tăng độ tương phản nhẹ (+15%), vignette viền tối để tôn chủ thể.
  3. Vẽ một dải ribbon hoặc văn bản chữ lớn phía trên bên trái:
     - Dòng 1: Tag chuyên mục nhỏ: `BẢN TIN THẾ GIỚI` (hoặc `AI & TECH` / `BÓNG ĐÁ`).
     - Dòng 2 (Chữ chính): Nội dung `thumbnail_hook` (ví dụ: `SỐC: ĐÁY MỚI?`) với kích thước font ~90px, màu vàng viền đen dày.

#### 4. Tiêu chí nghiệm thu
- [ ] Tự động kết xuất file `thumbnail.jpg` đạt chuẩn YouTube (1280x720 cho 16:9).
- [ ] Chữ hook ngắn gọn dưới 8 từ, nổi bật, đọc được rõ ràng ngay cả ở kích thước xem trước thu nhỏ.

---

### GIAI ĐOẠN 5: Audio Mastering Chống Quét Giọng AI & Kiểm Thử Toàn Diện

#### 1. Mục tiêu
- Xử lý hậu kỳ file âm thanh giọng đọc trước khi mux vào video để phá vỡ hoàn toàn "dấu vân tay phổ âm" (acoustic signature) của Edge-TTS mặc định.
- Giữ vững toàn bộ lịch trình tự động trong Windows Task Scheduler và đường truyền tải lên YouTube.

#### 2. Kỹ thuật triển khai
- **Bộ lọc âm học FFmpeg Audio Filter (`af`)**:
  ```bash
  # Tinh chỉnh cao độ nhẹ ±1%, tăng độ ấm (warmth EQ) ở 250Hz và độ trong (clarity) ở 3500Hz, nén dynamic range:
  -af "asetrate=44100*1.015,aresample=44100,equalizer=f=250:width_type=o:w=1:g=2.5,equalizer=f=3500:width_type=o:w=1:g=2.0,compand=attacks=0.05:decays=0.2:points=-80/-80|-20/-10|0/-3"
  ```
- **Hòa âm BGM tinh tế**:
  - Giữ mức âm lượng nhạc nền ở mức vừa phải (5 - 8%), tự động hạ nhỏ (audio ducking) khi giọng đọc vang lên.

#### 3. Tiêu chí nghiệm thu
- [ ] Giọng đọc nghe tự nhiên, ấm áp như phòng thu truyền hình, không có cảm giác máy móc kim loại.
- [ ] Kiểm tra chạy thử nghiệm pipeline trên cả 4 thể loại (`world`, `tech`, `sports`, `viral`), xuất bản thành công không lỗi.
- [ ] Xác nhận video mới vẫn tự động chui vào playlist `Bản tin thế giới` (`PLOUagwqnThxE`).

---

## III. Ma Trận Bảo Toàn Cấu Hình Hệ Thống (Safety Matrix)

| Hạng mục cấu hình | Giá trị cam kết | Trạng thái bảo tồn |
| :--- | :--- | :---: |
| **Lịch chạy Thời sự thế giới** | `05:00` hàng ngày |  Bảo lưu 100% |
| **Lịch chạy Tin công nghệ** | `05:25` hàng ngày |  Bảo lưu 100% |
| **Lịch chạy Tin bóng đá** | `05:50` hàng ngày |  Bảo lưu 100% |
| **Lịch chạy Tin lạ Shorts** | `06:30` hàng ngày |  Bảo lưu 100% |
| **Chế độ Wake PC** | `WakeToRun = True` (Tự thức dậy khi sleep) |  Bảo lưu 100% |
| **Tỉ lệ khung hình** | 3 bản tin đầu `16:9` - Tin viral `9:16` |  Bảo lưu 100% |
| **Chế độ đăng YouTube** | Tự động đăng ở chế độ `Public` |  Bảo lưu 100% |
| **Target Playlist** | `Bản tin thế giới` (ID: `PLOUagwqnThxE`) |  Bảo lưu 100% |

---

---

## IV. Bổ Sung Kỹ Xảo: Subscribe & Bell CTA Animation & Visual Direction Harness

### 1. Animation Bấm Đăng Ký & Bấm Chuông Có Âm Thanh (Subscribe CTA)
- Xuất hiện ở phân cảnh kết thúc (Outro scene) của video.
- Thiết kế dạng Pill card thanh lịch: Avatar VCH + Tên kênh VẠN CHUYỆN + Nút ĐĂNG KÝ nhún chuyển thành ✓ ĐÃ ĐĂNG KÝ + Chuông rung lắc phát sáng.
- Đồng bộ âm thanh SFX: Tiếng click chuột đanh gọn và tiếng chuông boong/ting trong trẻo, hòa âm trực tiếp vào giọng đọc kết bài.

### 2. Định Hướng Kỹ Xảo Thị Giác & Tiết Chế Nghệ Thuật (Visual Harness)
- Tích hợp tri thức từ bộ project 703 recipes `awesome-opus5-5-videos`:
  + Tin chiến sự / địa chính trị: Góc máy hiện trường sắc nét, bản đồ phân bổ tọa độ vệ tinh.
  + Tin kinh tế / công nghệ: Minh họa trực quan dạng bảng biểu số liệu, đồ họa dữ liệu sắc nét.
  + Tin thể thao / độc lạ: Cận cảnh kịch tính, chuyển động dynamic.
- **Nguyên tắc vàng**: Phong phú, sáng tạo, minh họa trực quan nghệ thuật nhưng **tiết chế vừa phải, tuyệt đối không làm quá đà, quá lố gây mất tập trung vào thông tin cốt lõi**.

---

## V. Trạng Thái Hoàn Thành Toàn Diện (All Phases Completed)

- [x] **PHASE 1**: Hook mở đầu tin sốc (bỏ chào hỏi), đổi cấu trúc tiêu đề, sinh thumbnail hook & ticker summary.
- [x] **PHASE 2**: Logo VCH nhỏ góc trên trái + Watermark VẠN CHUYỆN siêu mờ ngẫu nhiên.
- [x] **PHASE 3**: Thanh chữ chạy tin tức (News Ticker) cuộn mượt mà ở đáy, thay thế hoàn toàn phụ đề chữ to.
- [x] **PHASE 4**: Render ảnh bìa thumbnail gây tò mò (≤ 8 từ in hoa, có nhãn chuyên mục, né ô thời lượng) + upload tự động qua YouTube API `thumbnails.set`.
- [x] **PHASE 5**: Audio mastering chuỗi EQ, compressor, room reverb, -16 LUFS và BGM sidechain ducking.
- [x] **BONUS CTA**: Subscribe & Bell animation với âm thanh SFX chân thực ở cuối video.
- [x] **VISUAL HARNESS**: Đưa nguyên tắc kỹ xảo trực quan và tiết chế nghệ thuật vào prompt harness của Gemini.

---
*Tài liệu được cập nhật và lưu trữ tại `docs/extras/youtube-compliance-and-engagement-plan.vi.md`.*
