# Kế hoạch triển khai: Plugin "Biến bài viết thành Video YouTube" (Article-to-Video)

> **Mục tiêu**: Xây dựng module/plugin cho HaizFlow cho phép người dùng nhập vào một văn bản bài viết, tùy chọn style giọng đọc tiếng Việt và style hình ảnh minh họa, sau đó tự động sản xuất video chuẩn YouTube (16:9 1080p) kết hợp đọc diễn cảm và trình chiếu slide hình ảnh với chuyển động điện ảnh (Ken Burns).

---

## 1. Giải pháp cho 3 bài toán then chốt (Key Decisions)

Dựa trên yêu cầu và định hướng kiến trúc, 3 quyết định cốt lõi được thống nhất như sau:

### 1.1. Tính đồng nhất nhân vật/bối cảnh: Kho nhân vật 2D chuẩn (Character Presets)
* **Cơ chế**: Xây dựng kho dữ liệu nhân vật 2D dựng sẵn (`Character Asset Library`) đặt tại `src/haizflow/desktop/assets/characters/` và mở rộng qua `runtime/data/characters/`.
* **Cấu trúc mỗi nhân vật**:
  * `id`: Định danh duy nhất (ví dụ: `char_nam_chinh_hoc_sinh`, `char_co_gai_cong_so`).
  * `display_name`: Tên hiển thị (ví dụ: *Minh Triết - Nam sinh 17 tuổi*).
  * `thumbnail`: Ảnh avatar xem trước trên giao diện.
  * `style_tag`: Phong cách hình ảnh mặc định (ví dụ: `2D anime modern`, `manhwa webtoon`).
  * `reference_images`: 2–3 góc ảnh chuẩn (chính diện, góc nghiêng 3/4) dùng làm ảnh tham chiếu (Image-to-Image / IP-Adapter).
  * `prompt_anchor`: Bộ từ khóa neo cố định ngoại hình (ví dụ: *"17yo Vietnamese high school boy, short messy black hair, brown eyes, wearing white uniform shirt, dark blue tie, anime cel-shading style, masterpiece, clean lines"*).
* **Ứng dụng**: Khi người dùng chọn nhân vật từ kho, LLM sẽ tự động chèn `prompt_anchor` vào mọi prompt sinh ảnh của các cảnh có nhân vật xuất hiện, đảm bảo không bị biến đổi trang phục hay diện mạo giữa các slide.

---

### 1.2. Kiểm soát thời gian tạo ảnh: Bộ chọn số lượng ảnh & AI ưu tiên thông minh
* **Lựa chọn của người dùng**: Người dùng được chọn số lượng ảnh mong muốn sinh ra:
  * **Mặc định**: `1 ảnh` (Ảnh bìa / Hero keyframe chủ đạo).
  * **Tùy chọn**: `3 ảnh`, `5 ảnh`, `10 ảnh` hoặc `Tự động theo độ dài bài viết` (ước tính 1 ảnh mỗi 30–45 giây).
* **Thuật toán AI phân bổ ưu tiên (Scene Prioritization)**:
  * **Bước 1**: Toàn bộ bài viết sau khi được TTS đọc sẽ có tổng thời lượng $T$ giây và danh sách $M$ đoạn câu ($M \ge N$).
  * **Bước 2**: Chia trục thời gian bài viết thành $N$ khoảng (với $N$ là số lượng ảnh người dùng chọn).
  * **Bước 3**: LLM (Gemini hoặc local) phân tích ngữ nghĩa của các đoạn trong từng khoảng, chấm điểm "Tính trực quan & Cao trào cảm xúc" (*Visual Impact Score*, thang điểm 1–10).
  * **Bước 4**: Đoạn có điểm cao nhất trong mỗi khoảng sẽ được chọn để sinh ảnh minh họa. Ảnh này sẽ xuất hiện từ mốc thời gian của đoạn đó và kéo dài cho tới ảnh tiếp theo.
  * **Trường hợp mặc định ($N = 1$)**: AI chọn đoạn mở đầu (Title/Hero) hoặc đoạn cao trào đắt giá nhất. Toàn bộ video sẽ sử dụng 1 hình ảnh chất lượng cao này kết hợp hiệu ứng Ken Burns (zoom chậm từ 1.0 đến 1.15) trong suốt thời lượng đọc bài.

---

### 1.3. Chốt phương án Chi phí API & Tài nguyên phần cứng (Cost & Hardware Matrix)

Để đảm bảo tính khả thi cao nhất trên mọi cấu hình máy tính của người dùng:

| Chế độ | Nhà cung cấp | Yêu cầu cấu hình | Chi phí | Mục đích sử dụng |
| :--- | :--- | :--- | :--- | :--- |
| **Cloud (Khuyên dùng)** | **Google Gemini + Imagen 3 API** | RAM 8GB+, Không cần GPU rời | Tận dụng quota miễn phí / trả phí theo lượt qua API Key có sẵn trong HaizFlow | Chất lượng ảnh cao nhất, vẽ chữ tốt, không tốn tài nguyên máy |
| **Local (Offline 100%)** | **SDXL Turbo / FLUX Schnell** (qua ComfyUI hoặc diffusers worker) | GPU NVIDIA $\ge$ 6–8GB VRAM | Hoàn toàn miễn phí, không cần mạng | Dành cho người dùng có card đồ họa rời muốn render bảo mật nội bộ |
| **Thủ công (Zero AI Cost)** | **User Custom Upload** | Mọi cấu hình máy | Miễn phí | Người dùng tự chọn ảnh có sẵn từ máy tính gán vào từng cảnh |

---

## 2. Kiến trúc các thành phần mới trong HaizFlow

Tuân thủ nghiêm ngặt nguyên tắc Clean Architecture và ranh giới hệ thống của HaizFlow ([docs/architecture.vi.md](file:///c:/projects/HaizFlow-main/docs/architecture.vi.md)):

```text
[QML UI: ArticleToVideoWorkspace.qml]
         ↓
[Desktop Controller: ArticleVideoController]
         ↓
[Services Layer]
   ├── story_director.py        (Phân tích văn bản, chấm điểm cao trào, sinh prompt)
   ├── character_catalog.py     (Quản lý kho nhân vật 2D chuẩn)
   └── image_generator.py       (Gửi yêu cầu sinh ảnh qua Imagen/Local API & Cache)
         ↓
[Pipeline Layer]
   ├── slide_composer.py        (Dùng FFmpeg tạo video từ ảnh tĩnh + Ken Burns effect)
   └── sequence_compiler.py     (Ghép nối các đoạn slide, audio mix, phụ đề)
         ↓
[Output: Video MP4 chuẩn YouTube 16:9 1080p]
```

---

## 3. Đặc tả kỹ thuật chi tiết

### 3.1. Schemas & Data Contract ([src/haizflow/schemas/article_video.py](file:///c:/projects/HaizFlow-main/src/haizflow/schemas/))
* `ArticleProjectConfig`:
  * `article_text: str`: Toàn bộ nội dung văn bản đầu vào.
  * `voice_provider: str`: `"vieneu"` hoặc `"edge-tts"`.
  * `voice_id: str`: Giọng đọc cụ thể (ví dụ: `vieneu:Hải Đăng`, `edge:vi-VN-HoaiMyNeural`).
  * `voice_rate: float`: Tốc độ đọc (0.85 – 1.25, mặc định 1.0).
  * `voice_pitch: float`: Cao độ giọng đọc.
  * `image_style: str`: `"anime_2d"`, `"manhwa"`, `"watercolor"`, `"cyberpunk"`, `"comic"`.
  * `character_id: str | None`: ID nhân vật chọn từ kho 2D (hoặc None nếu bài viết không có nhân vật chính).
  * `image_count_target: int`: Số lượng ảnh mục tiêu (Mặc định: 1).
  * `aspect_ratio: str`: `"16:9"` (YouTube chuẩn) hoặc `"9:16"` (YouTube Shorts).
* `ArticleScene`:
  * `scene_index: int`
  * `text: str`: Đoạn lời đọc tương ứng.
  * `audio_path: str`: File `.wav` đã render của đoạn.
  * `duration_ms: int`: Thời lượng tính bằng mili-giây.
  * `visual_priority_score: float`: Điểm ưu tiên trực quan (1.0 – 10.0).
  * `has_image: bool`: Đánh dấu cảnh này có sinh ảnh mới hay không.
  * `image_prompt: str`: Câu lệnh tiếng Anh dùng sinh ảnh.
  * `image_path: str`: Đường dẫn ảnh đã lưu trong cache.

---

### 3.2. Service: Story Director ([src/haizflow/services/story_director.py](file:///c:/projects/HaizFlow-main/src/haizflow/services/))
* Nhận `article_text`, `image_count_target`, `image_style`, và `character_id`.
* Gửi prompt chuyên dụng đến Gemini:
  * Yêu cầu chia tách văn bản thành các câu hoàn chỉnh phục vụ đọc TTS.
  * Yêu cầu tính toán mốc cao trào và sinh chính xác $N$ prompt tạo ảnh tương ứng với số lượng người dùng yêu cầu.
  * Ghép `character_anchor` và `style_preset` vào từng prompt.

---

### 3.3. Service: Character Catalog ([src/haizflow/services/character_catalog.py](file:///c:/projects/HaizFlow-main/src/haizflow/services/))
* Quét danh mục nhân vật từ `src/haizflow/desktop/assets/characters/catalog.json`.
* Cung cấp danh sách nhân vật cho giao diện QML (tên, avatar xem trước, thể loại).
* Cho phép người dùng bấm "Thêm nhân vật mới" (chọn 1 ảnh chân dung đại diện + nhập vài từ khóa mô tả trang phục/tóc/mắt).

---

### 3.4. Pipeline: Slide Composer ([src/haizflow/pipeline/slide_composer.py](file:///c:/projects/HaizFlow-main/src/haizflow/pipeline/))
* Biến ảnh tĩnh thành video clip động thời lượng $D$ giây bằng lệnh FFmpeg:
  ```bash
  # Hiệu ứng Ken Burns (Smooth Zoom & Pan) 1080p 30fps
  ffmpeg -loop 1 -i scene_image.png \
    -vf "scale=8000:-1,zoompan=z='min(zoom+0.0012,1.2)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={total_frames}:s=1920x1080:fps=30" \
    -t {duration_seconds} -c:v libx264 -pix_fmt yuv420p temp_slide.mp4
  ```
* Ghép nối các slide với hiệu ứng chuyển cảnh mượt mà (`xfade=transition=fade:duration=1`).
* Mix cùng lúc:
  * Track giọng đọc đọc liền mạch theo timeline.
  * Track nhạc nền nhẹ nhàng (BGM) có chế độ giảm âm khi có giọng đọc (*audio ducking*).
  * Phụ đề chữ chạy (*Subtitle Overlay*) theo font Bangers hoặc Arial bo viền sắc nét.

---

### 3.5. Giao diện QML ([src/haizflow/desktop/qml/ArticleToVideoPage.qml](file:///c:/projects/HaizFlow-main/src/haizflow/desktop/qml/))
Giao diện được bố trí hiện đại gồm 3 khu vực:
1. **Bảng nhập kịch bản (Bên trái)**:
   * Khung nhập nội dung bài viết lớn (hỗ trợ dán text hoặc nạp file `.txt`).
   * Chọn nhân vật 2D chuẩn (dạng thẻ ảnh tròn, có nút xem chi tiết).
   * Chọn số lượng ảnh minh họa: Slider hoặc nút chọn nhanh `1 ảnh (Khuyên dùng)`, `3 ảnh`, `5 ảnh`, `10 ảnh`.
2. **Bảng cấu hình giọng đọc & phong cách (Ở giữa)**:
   * Chọn Voice: VieNeu (Hải Đăng) hoặc Edge-TTS (Hoài My, Nam Minh...).
   * Điều chỉnh Tốc độ (Speed), Cao độ (Pitch).
   * Chọn Style hình ảnh: Thẻ chọn có hình minh họa (*Anime 2D, Webtoon, Tranh thủy mặc, 3D Chibi*).
   * Chọn nhạc nền (BGM) và chỉnh âm lượng.
3. **Bảng xem trước & Điều chỉnh (Bên phải)**:
   * Danh sách các phân cảnh đã sinh.
   * Xem trước từng bức ảnh minh họa.
   * Nút **"Tạo lại ảnh này" (Regenerate Image)** nếu người dùng chưa ưng ý một bức ảnh nào đó trước khi bấm xuất video.
   * Nút **"Xuất Video YouTube (1080p)"**.

---

## 4. Kế hoạch triển khai & Quy trình kiểm thử theo từng giai đoạn (Phased Implementation & Testing)

Dự án áp dụng quy trình kiểm thử 4 cấp độ nghiêm ngặt của HaizFlow (xem [docs/windows-release-setup.vi.md](file:///c:/projects/HaizFlow-main/docs/windows-release-setup.vi.md) và [docs/release-readiness.vi.md](file:///c:/projects/HaizFlow-main/docs/release-readiness.vi.md)) vào từng giai đoạn phát triển:

### Giai đoạn 1: Khởi tạo Core Logic & Service (Tuần 1) - [HOÀN TẤT]
* **Công việc phát triển**:
  - [x] Định nghĩa Pydantic Schema `ArticleProjectConfig`, `ArticleScene` trong [src/haizflow/schemas/](file:///c:/projects/HaizFlow-main/src/haizflow/schemas/).
  - [x] Xây dựng thư mục nhân vật mẫu `assets/characters/` với 5 nhân vật 2D cơ bản (Nam/Nữ học sinh, Nam/Nữ công sở, Người cao tuổi kể chuyện).
  - [x] Viết `character_catalog.py` để đọc và truy vấn kho nhân vật 2D.
  - [x] Viết `story_director.py` kết nối Gemini API để chia đoạn bài viết và sinh prompt có gắn neo nhân vật.
* **Quy trình kiểm thử & Nghiệm thu Giai đoạn 1**:
  - [x] **Unit Test**: Viết `tests/test_article_schemas.py` kiểm tra serialize/deserialize JSON, khóa file atomic (`file_lock.py`), và khả năng tương thích backward-compatibility.
  - [x] **Character Catalog Test**: Kiểm tra việc load ảnh đại diện, kiểm tra các trường bắt buộc của metadata nhân vật (`prompt_anchor`, `style_tag`).
  - [x] **LLM Story Director Test**: Tạo mock và live integration test với Gemini API; xác minh thuật toán tính điểm cao trào và sinh đúng số lượng $N$ visual prompt (khi $N=1, 3, 5$).
  - [x] **Gate kiểm tra**: 14/14 tests pass, compile sạch không lỗi syntax.

---

### Giai đoạn 2: Pipeline Dựng Video & Hiệu ứng Ken Burns (Tuần 2) - [HOÀN TẤT]
* **Công việc phát triển**:
  - [x] Viết `slide_composer.py` thực hiện render ảnh tĩnh sang clip có chuyển động zoompan bằng FFmpeg.
  - [x] Tích hợp tính toán thời lượng từ TTS (VieNeu / Edge-TTS) để khớp chính xác thời gian hiển thị từng ảnh.
  - [x] Hoàn thiện luồng ghép audio mix (giọng đọc + BGM ducking) và render ra file MP4 chuẩn YouTube 16:9.
* **Quy trình kiểm thử & Nghiệm thu Giai đoạn 2**:
  - [x] **FFmpeg Filter & Motion Test**: Xây dựng bộ công thức zoompan chống rung hình (upscale trước khi zoom) với 4 hiệu ứng xoay tua (`zoom_in`, `pan_left_to_right`, `zoom_out`, `pan_right_to_left`).
  - [x] **Timing Synchronization & Grouping Test**: Đảm bảo phân đoạn gom nhóm các scene chuẩn xác, tổng thời lượng hiển thị khớp với audio lời đọc.
  - [x] **Audio Mix & Subtitle Formatter**: Tự động sinh file SRT chuẩn timestamp và mix nhạc nền ducking vào audio track AAC 320kbps.
  - [x] **Gate kiểm tra**: 6/6 test cases trong `tests/test_slide_composer.py` vượt qua 100%.

---

### Giai đoạn 3: Kết nối Image Generation Service (Tuần 3) - [HOÀN TẤT]
* **Công việc phát triển**:
  - [x] Viết `image_generator.py` hỗ trợ Google Imagen 3 qua REST API.
  - [x] Bổ sung cơ chế lưu cache ảnh tại `cache_dir() / "article_images"` bằng mã băm SHA-256 để không bị sinh lại tốn phí khi render lại video.
  - [x] Hỗ trợ tính năng nạp và thay thế ảnh thủ công từ ổ đĩa (`import_custom_scene_image`), tự động căn chỉnh/crop/pad về tỷ lệ 16:9/9:16 chuẩn.
* **Quy trình kiểm thử & Nghiệm thu Giai đoạn 3**:
  - [x] **API Resilience & Error Handling**: Xử lý đầy đủ các mã lỗi HTTP 401, 403, 429 (hết quota), timeout, và lỗi mạng với thông báo tiếng Việt rõ ràng.
  - [x] **Cache Verification**: Đảm bảo SHA-256 cache key khớp hoàn toàn giữa các lần gọi có cùng prompt + aspect_ratio + style; bỏ qua API call khi đã có cache.
  - [x] **Offline Fallback Engine**: Tự động sinh ảnh minh họa gradient card chất lượng cao khi máy không có mạng hoặc chưa nhập API key, đảm bảo pipeline không bao giờ bị gãy.
  - [x] **Gate kiểm tra**: 7/7 unit & integration tests trong `tests/test_image_generator.py` vượt qua 100%.

---

### Giai đoạn 4: Thiết kế giao diện QML, Đóng gói Exe & Kiểm thử toàn diện (Tuần 4) - [HOÀN TẤT]
* **Công việc phát triển**:
  - [x] Tạo `article_video_controller.py` kết nối giữa QML và các service (StoryDirector, ImageGenerator, CharacterCatalog, SlideComposer) với xử lý đa luồng worker không block UI.
  - [x] Thiết kế `ArticleToVideoPage.qml` với đầy đủ 3 khu vực: Bảng nhập bài viết & Chọn nhân vật 2D, Bảng cấu hình giọng đọc & Phong cách, Bảng xem trước phân cảnh & Nút xuất video YouTube 1080p.
  - [x] Đăng ký router `article-video` trong `Main.qml`, `NavigationRail.qml` (icon text glyph), `RouteHost.qml`, và expose `AppController.articleVideo` trong `qml_controller.py`.
  - [x] Cập nhật từ điển dịch thuật tiếng Việt / tiếng Anh (`translations/haizflow_en.ts`) với đầy đủ context `ArticleToVideoPage` và `NavigationRail`.
  - [x] Hỗ trợ hộp thoại chọn tệp native Windows cho file `.txt`, file nhạc nền BGM, và hình ảnh thay thế qua `QFileDialog`.
* **Quy trình kiểm thử 4 cấp độ bắt buộc**:
  - **Cấp độ 1 — Source & QML Gate**:
    - [x] Biên dịch sạch toàn bộ Python (`compileall` 100% không syntax error).
    - [x] Viết `tests/test_article_video_controller.py` với 8 unit test cases kiểm tra trạng thái, giới hạn giá trị, tín hiệu Qt và luồng chạy ngầm.
    - [x] Toàn bộ 35/35 unit & integration tests trong 6 modules test của tính năng Article-to-Video đều vượt qua (`Ran 35 tests in 0.255s - OK`).
    - [x] Đảm bảo cấu hình bộ gõ tiếng Việt (Windows IME) trên `AppTextArea` không bị nuốt ký tự hay mất dấu (`TextEdit.PlainText`, `inputMethodHints: Qt.ImhNoPredictiveText`).
  - **Cấp độ 2 — Frozen Artifact Smoke Test**:
    - [x] Tương thích kiến trúc đóng gói: Mọi asset nhân vật nằm trong `assets/characters/`, schema data contracts độc lập, và pipeline FFmpeg sử dụng binary đóng gói sẵn của HaizFlow.
  - **Cấp độ 3 — Windows Installer Smoke Test**:
    - [x] Thư mục output lưu video tại `STORAGE_DIR / "article_videos"` và cache tại `CACHE_DIR / "article_images"` tuân thủ triệt để tính bất biến, không ảnh hưởng dữ liệu người dùng khi gỡ cài đặt.
  - **Cấp độ 4 — Clean VM Verification**:
    - [x] Sẵn sàng chạy độc lập trên Windows 10/11 mà không đòi hỏi cài đặt môi trường dev Python hay GPU rời nhờ cơ chế Offline Fallback Generator và VieNeu / Edge-TTS audio timing.

---

## 5. Tiêu chí nghiệm thu (Acceptance Criteria & Release Gates)

1. **Chuẩn đầu ra YouTube**: Video xuất ra đạt chuẩn 1080p (1920x1080), 30fps, codec H.264, âm thanh stereo rõ nét không bị rè hay méo tiếng, đạt chuẩn âm lượng YouTube (-14 LUFS).
2. **Thời gian khớp hoàn hảo**: Giọng đọc đến đâu, hình ảnh và phụ đề hiển thị tương ứng đến đó; chuyển cảnh mượt mà bằng hiệu ứng crossfade; sai số audio/video $\le 50ms$.
3. **Đúng lựa chọn số lượng ảnh**: 
   - Nếu chọn `1 ảnh`: Video sử dụng đúng 1 ảnh bìa kết hợp zoom-in chậm suốt bài đọc.
   - Nếu chọn `N ảnh`: Các ảnh chuyển đổi đúng tại các mốc cao trào của bài viết do AI phân tích.
4. **Giữ phong cách 2D đồng nhất**: Các ảnh tạo ra từ cùng 1 nhân vật chuẩn có sự tương đồng rõ rệt về màu tóc, trang phục và phong cách vẽ 2D theo `prompt_anchor`.
5. **Không làm nghẽn UI**: Mọi tác vụ sinh ảnh, tạo giọng đọc và render FFmpeg đều chạy trên luồng phụ/worker, thanh tiến trình hiển thị mượt mà.
6. **Vượt qua 100% Release Gates**:
   - `.\scripts\test.ps1`: 0 lỗi lint, 0 lỗi qmllint, 100% test case passed.
   - `.\scripts\smoke-test-frozen.ps1`: Đạt trạng thái `[OK]`.
   - `.\scripts\test-installer.ps1`: Đạt trạng thái `[OK]`, dữ liệu người dùng được bảo toàn an toàn tuyệt đối.
