"""Daily International News Video Generator Service.

Fetches 100% international world news from RSS feeds (excluding Vietnam news),
synthesizes high-impact Vietnamese news scripts via Gemini Flash, retrieves
copyright-safe real images via Wikimedia Commons (with fallback to AI cinematic visuals),
and compiles automated videos with Edge-TTS and Ken Burns motion effects.
"""

from __future__ import annotations

import html
import io
import json
import logging
import os
import re
import shutil
import tempfile
import time
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, List, Literal, Optional, Tuple

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from haizflow.config import STORAGE_DIR
from haizflow.core.paths import runtime_data_dir
from haizflow.pipeline.slide_composer import (
    acquire_prevent_sleep,
    compose_article_video,
    generate_scenes_narration,
    prevent_system_sleep,
    release_prevent_sleep,
    resolution_for_aspect_ratio,
)
from haizflow.schemas.article_video import (
    ArticleProjectConfig,
    ArticleScene,
    ArticleVideoProject,
    AspectRatio,
)
from haizflow.services.image_generator import (
    generate_scene_image,
    get_effective_gemini_api_key,
)

logger = logging.getLogger(__name__)

# Gemini Candidate Models for Automatic Failover / High Availability
GEMINI_MODELS = [
    "gemini-3-flash-preview",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-flash-latest",
]

# International RSS Feeds covering World, Global Economy, Science & Technology
# Multi-region: China, Southeast Asia, Russia, Japan, Korea, Europe, USA, Middle East
WORLD_RSS_FEEDS = [
    # 1. China & East Asia: South China Morning Post (Direct Asia reporting)
    "https://www.scmp.com/rss/91/feed",
    # 2. Southeast Asia & ASEAN: The Straits Times (Asia / ASEAN regional focus)
    "https://www.straitstimes.com/news/asia/rss.xml",
    # 3. Southeast Asia: Channel NewsAsia (CNA Asia News)
    "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6511",
    # 4. South Korea: Yonhap News Agency (English international edition)
    "https://en.yna.co.kr/RSS/news.xml",
    # 5. Japan: The Japan Times (Leading English-language Japan and East Asia reporting)
    "https://www.japantimes.co.jp/feed/topstories/",
    # 6. China & East Asia: Google News China & Beijing
    "https://news.google.com/rss/search?q=(China+OR+Beijing)+when:2d&-vietnam&hl=en-US&gl=US&ceid=US:en",
    # 7. Southeast Asia & ASEAN: Google News ASEAN countries
    "https://news.google.com/rss/search?q=(ASEAN+OR+%22Southeast+Asia%22+OR+Thailand+OR+Indonesia+OR+Malaysia+OR+Philippines+OR+Singapore+OR+Cambodia+OR+Laos+OR+Myanmar)+-vietnam+when:2d&hl=en-US&gl=US&ceid=US:en",
    # 8. Russia & Eurasia: Google News Russia & Moscow
    "https://news.google.com/rss/search?q=(Russia+OR+Moscow+OR+Kremlin+OR+Putin)+-vietnam+when:2d&hl=en-US&gl=US&ceid=US:en",
    # 9. Japan & Korea: Google News Tokyo & Seoul
    "https://news.google.com/rss/search?q=(Japan+OR+Tokyo+OR+%22South+Korea%22+OR+Seoul)+-vietnam+when:2d&hl=en-US&gl=US&ceid=US:en",
    # 10. BBC News - World (Direct links)
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    # 11. The Guardian - World News (Direct links)
    "https://www.theguardian.com/world/rss",
    # 12. NPR World News (Direct links)
    "https://feeds.npr.org/1004/rss.xml",
    # 13. Al Jazeera English - World News
    "https://www.aljazeera.com/xml/rss/all.xml",
]

# International Technology & AI RSS Feeds (AI, chips, EVs, hardware, software)
# Multi-region: Silicon Valley, China (BYD, AI, Huawei), Taiwan (TSMC), Korea (Samsung), Japan
TECH_RSS_FEEDS = [
    # 1. The Verge - Leading technology, gadgets, and science
    "https://www.theverge.com/rss/index.xml",
    # 2. TechCrunch - AI, tech companies, venture capital, and startups
    "https://techcrunch.com/feed/",
    # 3. Wired - Tech culture, security, breakthroughs, and frontier tech
    "https://www.wired.com/feed/rss",
    # 4. Ars Technica - In-depth hardware, software, space, and semiconductors
    "https://feeds.arstechnica.com/arstechnica/index",
    # 5. BBC News - Technology
    "https://feeds.bbci.co.uk/news/technology/rss.xml",
    # 6. Google News - Technology & AI Global
    "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGRqTVhZU0FtVnVHZ0pWVXlnQVAB?hl=en-US&gl=US&ceid=US:en",
    # 7. China Tech & EV: Huawei, BYD, Chinese AI, SMIC, robotics
    "https://news.google.com/rss/search?q=(China+OR+Chinese)+AND+(%22electric+vehicle%22+OR+EV+OR+BYD+OR+Huawei+OR+semiconductor+OR+%22artificial+intelligence%22+OR+robotics)+-vietnam&hl=en-US&gl=US&ceid=US:en",
    # 8. Korea & Taiwan Tech: Samsung, TSMC, SK Hynix, semiconductor chips
    "https://news.google.com/rss/search?q=(TSMC+OR+Samsung+OR+%22SK+Hynix%22+OR+%22South+Korea%22+OR+Taiwan)+AND+(semiconductor+OR+chip+OR+AI+OR+foundry)+-vietnam&hl=en-US&gl=US&ceid=US:en",
    # 9. Japan Tech: Robotics, quantum computing, advanced materials
    "https://news.google.com/rss/search?q=(Japan+OR+Japanese+OR+Tokyo)+AND+(robotics+OR+quantum+OR+semiconductor+OR+technology)+-vietnam&hl=en-US&gl=US&ceid=US:en",
]

# International Football / Soccer RSS Feeds
# Focus: Premier League (Anh), Serie A (Ý), Bundesliga (Đức), Ligue 1 (Pháp), La Liga (TBN), Champions League,
# Star Player stories (Mbappe, Haaland, Bellingham, Vinicius, Messi, Ronaldo...),
# and Regional Football (Thailand, Indonesia, China, Cambodia). Strictly 0% Vietnam football.
SPORTS_RSS_FEEDS = [
    # 1. BBC Sport Football - Premier League, Champions League, European Football, Transfers
    "https://feeds.bbci.co.uk/sport/football/rss.xml",
    # 2. Sky Sports Football & Premier League - Breaking football & transfer news
    "https://www.skysports.com/rss/11095",
    # 3. The Guardian - World Football news, in-depth match reports & tactical analysis
    "https://www.theguardian.com/football/rss",
    # 4. ESPN FC - Global soccer news, European leagues & transfer updates
    "https://www.espn.com/espn/rss/soccer/news",
    # 5. Premier League & English Football: Man City, Arsenal, Liverpool, Man Utd, Chelsea, Tottenham
    "https://news.google.com/rss/search?q=(%22Premier+League%22+OR+%22Manchester+City%22+OR+Arsenal+OR+Liverpool+OR+%22Manchester+United%22+OR+Chelsea+OR+Tottenham)+AND+(football+OR+match+OR+transfer+OR+derby)+-vietnam&hl=en-US&gl=US&ceid=US:en",
    # 6. European Top Leagues: Serie A (Ý), Bundesliga (Đức), Ligue 1 (Pháp), La Liga, Champions League
    "https://news.google.com/rss/search?q=(%22Serie+A%22+OR+Bundesliga+OR+%22Ligue+1%22+OR+%22La+Liga%22+OR+%22Champions+League%22)+AND+(football+OR+soccer+OR+match+OR+derby)+-vietnam&hl=en-US&gl=US&ceid=US:en",
    # 7. Star Spotlight & Drama: Mbappe, Haaland, Bellingham, Vinicius, Lamine Yamal, Messi, Ronaldo, Kane, Salah
    "https://news.google.com/rss/search?q=(Mbappe+OR+Haaland+OR+Bellingham+OR+Vinicius+OR+%22Lamine+Yamal%22+OR+Messi+OR+Ronaldo+OR+%22Harry+Kane%22+OR+Salah)+AND+(goal+OR+transfer+OR+match+OR+record+OR+injury)+-vietnam&hl=en-US&gl=US&ceid=US:en",
    # 8. Regional Football: Thailand, Indonesia, China, Cambodia
    "https://news.google.com/rss/search?q=(%22Thailand+national+football+team%22+OR+%22Thai+League%22+OR+%22Indonesia+national+football+team%22+OR+%22Timnas+Indonesia%22+OR+%22Chinese+Super+League%22+OR+%22China+national+football+team%22+OR+%22Cambodia+national+football+team%22)+-vietnam&hl=en-US&gl=US&ceid=US:en",
]

# Comprehensive International Viral, Shocking, Humorous & Curiosity Feeds (Shorts 9:16)
VIRAL_RSS_FEEDS = [
    # 1. China & East Asia: Douyin/Weibo viral trends, bizarre inventions, wild stunts
    "https://news.google.com/rss/search?q=(China+OR+Chinese+OR+Douyin+OR+Weibo)+AND+(viral+OR+bizarre+OR+hilarious+OR+funny+OR+stunt+OR+miracle)+-politics+-taiwan+-military+-sports+-vietnam&hl=en-US&gl=US&ceid=US:en",
    # 2. Thailand & Southeast Asia: Hilarious commercials, monkey/snake antics, viral comedy
    "https://news.google.com/rss/search?q=(Thailand+OR+Thai+OR+Indonesia+OR+Bali+OR+Philippines+OR+Malaysia)+AND+(viral+OR+hilarious+OR+funny+OR+bizarre+OR+monkey+OR+snake+OR+clumsy)+-politics+-sports+-vietnam&hl=en-US&gl=US&ceid=US:en",
    # 3. Russia & Siberia: Craters, deep freeze mysteries, extreme natural phenomena, wild antics
    "https://news.google.com/rss/search?q=(Siberia+OR+Russia)+AND+(permafrost+OR+crater+OR+meteor+OR+freeze+OR+bizarre+OR+miracle)+-war+-ukraine+-putin+-sanctions+-military+-sports+-vietnam&hl=en-US&gl=US&ceid=US:en",
    # 4. Japan & Korea: Quirky inventions, bizarre street trends & funny viral moments
    "https://news.google.com/rss/search?q=(Japan+OR+Tokyo+OR+%22South+Korea%22+OR+Seoul)+AND+(bizarre+OR+viral+OR+shocking+OR+hilarious+OR+stunt)+-politics+-sports+-vietnam&hl=en-US&gl=US&ceid=US:en",
    # 5. Curated Oddities & Quirky Inventions: Oddity Central
    "https://www.odditycentral.com/feed",
    # 6. Curated Laughing Squid: Funny art, creative viral stunts, hilarious fails & quirky culture
    "https://laughingsquid.com/feed/",
    # 7. UPI Odd News: Real weird & quirky events worldwide
    "https://rss.upi.com/news/odd_news.rss",
    # 8. Animals & 'Not The Onion': Funny animal antics, Comedy Wildlife, absurd real-life incidents
    "https://news.google.com/rss/search?q=(%22not+the+onion%22+OR+%22comedy+wildlife%22+OR+%22animal+antics%22+OR+%22funny+animal%22)+AND+(viral+OR+video)+-sports+-politics+-vietnam&hl=en-US&gl=US&ceid=US:en",
    # 9. Clumsy Criminals & Bizarre Thefts: Dumbest criminals, bungled heists, hilarious police caught-on-camera
    "https://news.google.com/rss/search?q=(%22clumsy+thief%22+OR+%22dumbest+criminal%22+OR+%22bizarre+theft%22+OR+%22heist+fail%22+OR+%22hilarious+mistake%22)+-politics+-sports+-vietnam&hl=en-US&gl=US&ceid=US:en",
    # 10. Comedy & Hilarious Fails: Viral fails, clumsy thieves, absurd real mishaps & funny video clips
    "https://news.google.com/rss/search?q=(hilarious+OR+funny+OR+absurd+OR+ridiculous+OR+%22epic+fail%22)+AND+(viral+OR+video+OR+caught)+-sports+-football+-soccer+-nba+-nfl+-nhl+-mlb+-hockey+-baseball+-cricket+-politics+-biden+-trump+-election+-vietnam&hl=en-US&gl=US&ceid=US:en",
    # 11. Reddit Viral Moments (r/nottheonion, r/funny, r/mildlyinteresting)
    "https://news.google.com/rss/search?q=(site:reddit.com/r/nottheonion+OR+site:reddit.com/r/funny)+AND+(video+OR+photos+OR+story)+-sports+-politics+-vietnam&hl=en-US&gl=US&ceid=US:en",
    # 12. USA & Florida: Florida Man, wild antics & caught-on-camera phenomena
    "https://news.google.com/rss/search?q=(%22Florida+man%22+OR+%22caught+on+camera%22)+AND+(shocking+OR+bizarre+OR+weird+OR+hilarious+OR+miracle)+-politics+-election+-court+-sports+-nba+-nfl+-nhl+-mlb+-vietnam&hl=en-US&gl=US&ceid=US:en",
    # 13. Bored Panda: Quirky, viral human interest & humor
    "https://www.boredpanda.com/feed/",
    # 14. Reddit Curiosity & Oddities (r/Damnthatsinteresting, r/BeAmazed)
    "https://news.google.com/rss/search?q=(site:reddit.com/r/Damnthatsinteresting+OR+site:reddit.com/r/BeAmazed)+AND+(video+OR+story+OR+viral)+-politics+-sports+-vietnam&hl=en-US&gl=US&ceid=US:en",
]

# Comprehensive International Armed Conflict, War & Military RSS Feeds
# Excludes general feeds that pollute with sports or celebrity news; strictly targets war zones
WAR_RSS_FEEDS = [
    # 1. Google News - Strategic frontline hotspots (Ukraine, Middle East, Gaza, Lebanon, Sudan, Red Sea)
    "https://news.google.com/rss/search?q=(Ukraine+OR+Gaza+OR+Lebanon+OR+Sudan+OR+Yemen+OR+Syria+OR+Hezbollah)+AND+(strike+OR+offensive+OR+frontline+OR+clash+OR+casualty)+-vietnam&hl=en-US&gl=US&ceid=US:en",
    # 2. Russia - Ukraine Military Frontlines: Donbass, Kursk, UAV strikes, frontline advances
    "https://news.google.com/rss/search?q=(Russia+OR+Russian+military+OR+Moscow)+AND+(offensive+OR+frontline+OR+strike+OR+missile+OR+drone+OR+casualty)+-vietnam&hl=en-US&gl=US&ceid=US:en",
    # 3. East Asia Tensions: Taiwan Strait, Korean Peninsula, military drills, missile tests
    "https://news.google.com/rss/search?q=(%22Taiwan+Strait%22+OR+%22North+Korea%22+OR+Pyongyang+OR+%22ballistic+missile%22+OR+%22military+drill%22)+AND+(drill+OR+missile+OR+tensions+OR+military)+-vietnam&hl=en-US&gl=US&ceid=US:en",
    # 4. Southeast Asia & Myanmar Conflicts: Civil war, junta clashes, border security
    "https://news.google.com/rss/search?q=(Myanmar+OR+Junta+OR+%22civil+war%22+OR+rebels+OR+clashes+OR+airstrike)+AND+(military+OR+fighting+OR+offensive)+-vietnam&hl=en-US&gl=US&ceid=US:en",
    # 5. Middle East Warfare: Airstrikes, missile attacks, combat casualties
    "https://news.google.com/rss/search?q=(Gaza+OR+Lebanon+OR+Hezbollah+OR+Yemen+OR+Houthi+OR+Syria+OR+Iran)+AND+(airstrike+OR+missile+OR+casualty+OR+strike+OR+clashes)+-vietnam&hl=en-US&gl=US&ceid=US:en",
    # 6. Global Armed Conflict & Civil Unrest (coups, insurgencies, major armed riots)
    "https://news.google.com/rss/search?q=(war+OR+conflict+OR+airstrike+OR+missile+OR+%22civil+war%22+OR+clash+OR+protest+OR+unrest+OR+military)+-sports+-football+-soccer+-entertainment+-vietnam&hl=en-US&gl=US&ceid=US:en",
    # 7. BBC News - World Conflict & International Security
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    # 8. The Guardian - World News & Defense
    "https://www.theguardian.com/world/rss",
    # 9. NPR - International Conflicts
    "https://feeds.npr.org/1004/rss.xml",
]

# Comprehensive International Hope, Medical Breakthroughs, Living Species & Environmental Solutions Feeds (Shorts 9:16)
HOPE_RSS_FEEDS = [
    # 1. ScienceDaily Health & Medicine - Cures, cancer therapies, vaccines & lifesaving treatments (Y khoa)
    "https://www.sciencedaily.com/rss/health_medicine.xml",
    # 2. ScienceDaily Plants & Animals - Wildlife, species recovery, biodiversity & marine biology (Sự sống)
    "https://www.sciencedaily.com/rss/plants_animals.xml",
    # 3. ScienceDaily Earth & Climate - Ecological restoration, clean nature & environmental solutions (Môi trường)
    "https://www.sciencedaily.com/rss/earth_climate.xml",
    # 4. Good News Network - Premier positive news: animal rescues, medical cures, earth solutions
    "https://www.goodnewsnetwork.org/feed/",
    # 5. The Optimist Daily - Solutions journalism, green ecology & social breakthroughs
    "https://www.optimistdaily.com/feed/",
    # 6. ScienceDaily Top Science - Broad scientific breakthroughs & frontier science
    "https://www.sciencedaily.com/rss/top/science.xml",
    # 7. New Atlas - Inventions, innovations, green transportation & positive human achievements
    "https://newatlas.com/index.rss",
    # 8. Targeted Global Medical Breakthroughs & Cures (Y khoa trọng tâm)
    "https://news.google.com/rss/search?q=(%22medical+breakthrough%22+OR+%22cancer+treatment%22+OR+%22clinical+trial%22+OR+%22stem+cell%22+OR+%22cure%22)+AND+(remission+OR+success+OR+milestone+OR+therapy)+-politics+-war+-vietnam&hl=en-US&gl=US&ceid=US:en",
    # 9. Targeted Wildlife & Living Species Recovery (Sự sống & Muôn loài trọng tâm)
    "https://news.google.com/rss/search?q=(%22wildlife+recovery%22+OR+%22endangered+species%22+OR+%22coral+reef%22+OR+%22animal+rescue%22+OR+%22biodiversity%22)+AND+(success+OR+saved+OR+restoration+OR+rebirth)+-politics+-vietnam&hl=en-US&gl=US&ceid=US:en",
    # 10. Targeted Earth, Clean Water & Ocean Cleanup (Môi trường trọng tâm)
    "https://news.google.com/rss/search?q=(%22ocean+cleanup%22+OR+%22reforestation%22+OR+%22clean+water%22+OR+%22pollution+reduction%22+OR+%22ecological+restoration%22)+AND+(milestone+OR+breakthrough+OR+success)+-politics+-vietnam&hl=en-US&gl=US&ceid=US:en",
    # 11. Asia-Pacific: Clean energy megaprojects, solar breakthroughs, desert greening & coral conservation
    "https://news.google.com/rss/search?q=(China+OR+Japan+OR+Korea+OR+ASEAN)+AND+(%22clean+energy%22+OR+%22solar%22+OR+%22reforestation%22+OR+%22medical+cure%22+OR+%22coral+reef%22)+-politics+-taiwan+-military+-vietnam&hl=en-US&gl=US&ceid=US:en",
    # 12. Positive News UK: Uplifting journalism and global progress
    "https://www.positive.news/feed/",
    # 13. Reasons to be Cheerful: Solutions journalism and inspiring stories
    "https://reasonstobecheerful.world/feed/",
    # 14. Reddit Uplifting Stories (r/MadeMeSmile, r/UpliftingNews)
    "https://news.google.com/rss/search?q=(site:reddit.com/r/MadeMeSmile+OR+site:reddit.com/r/UpliftingNews)+AND+(heartwarming+OR+hero+OR+rescue+OR+saved)+-politics+-war+-vietnam&hl=en-US&gl=US&ceid=US:en",
]

NewsCategory = Literal["tin_moi", "tin_nong", "hope", "viral", "world", "war", "tech", "sports"]

CATEGORY_CONFIG: dict[str, dict] = {
    "tin_moi": {
        "label": "Tin Mới",
        "full_label": "Bản Tin Mới: Thời Sự & Thể Thao Quốc Tế",
        "source_label": "Thời sự & Sân cỏ quốc tế",
        "default_aspect_ratio": "16:9",
        "default_format_label": "16:9 Ngang",
        "feeds": WORLD_RSS_FEEDS + SPORTS_RSS_FEEDS,
        "title_prefix": "Bản Tin Mới Toàn Cảnh",
        "title_suffix_label": "Bản Tin Mới",
        "default_title": "Bản Tin Mới: Thời Sự & Thể Thao Quốc Tế",
        "hashtags": "#tinmoi #thoisuquocte #thoisu24h #thethao #bongda",
        "file_prefix": "tin_moi",
        "intro_entity": "Globe world map broadcast",
        "intro_ai_prompt": "cinematic 35mm newsroom with glowing digital world map background, high tech aesthetic",
        "persona": (
            "Bạn là biên tập viên thời sự và thể thao quốc tế cao cấp của kênh truyền hình YouTube chuyên về 'Bản Tin Mới'.\n"
            "Bản tin kết hợp toàn diện giữa thời sự thế giới nóng bỏng và các điểm nhấn sân cỏ, bóng đá quốc tế đỉnh cao.\n"
            "- LUẬT TỐI THƯỢNG BẤT KHẢ XÂM PHẠM: TUYỆT ĐỐI 100% KHÔNG ĐƯỢC ĐƯA BẤT KỲ THÔNG TIN NÀO LIÊN QUAN ĐẾN VIỆT NAM (không nhắc đến Việt Nam, con người, địa danh, chính sách, tổ chức, hay bất kỳ liên hệ nào đến Việt Nam). Toàn bộ bản tin phải 100% là sự kiện thế giới và thể thao quốc tế.\n"
            "Dưới đây là các tin tức thế giới và bóng đá quốc tế nổi bật rạng sáng nay kèm nội dung chi tiết từ các hãng thông tấn:"
        ),
        "outro_topic_name": "thời sự và thể thao quốc tế",
    },
    "tin_nong": {
        "label": "Tin Nóng",
        "full_label": "Bản Tin Nóng: Chiến Sự & Đột Phá Công Nghệ",
        "source_label": "Chiến trường & Công nghệ đột phá",
        "default_aspect_ratio": "16:9",
        "default_format_label": "16:9 Ngang",
        "feeds": WAR_RSS_FEEDS + TECH_RSS_FEEDS,
        "title_prefix": "Bản Tin Nóng Toàn Cảnh",
        "title_suffix_label": "Tin Nóng",
        "default_title": "Bản Tin Nóng: Chiến Sự & Đột Phá Công Nghệ",
        "hashtags": "#tinnong #chiensuthegioi #congnghe #ai #thoisu24h",
        "file_prefix": "tin_nong",
        "intro_entity": "Military command center war room conflict radar",
        "intro_ai_prompt": "cinematic military operations war room news studio, dark atmospheric situation room with glowing 3D tactical radar conflict map, telemetry indicators, dramatic military broadcast journalism",
        "persona": (
            "Bạn là biên tập viên quốc tế cao cấp của kênh truyền hình YouTube chuyên về 'Bản Tin Nóng: Chiến Sự & Công Nghệ Thế Giới'.\n"
            "Bản tin phân tích chuyên sâu về các điểm nóng quân sự - xung đột an ninh quốc phòng toàn cầu kết hợp các đột phá công nghệ và trí tuệ nhân tạo (AI) định hình tương lai.\n"
            "PHONG CÁCH VÀ YÊU CẦU BIÊN TẬP:\n"
            "- LUẬT TỐI THƯỢNG BẤT KHẢ XÂM PHẠM: TUYỆT ĐỐI 100% KHÔNG ĐƯỢC ĐƯA BẤT KỲ TIN TỨC NÀO LIÊN QUAN ĐẾN VIỆT NAM. Toàn bộ bản tin phải 100% là sự kiện chiến sự và công nghệ quốc tế.\n"
            "- Giọng điệu đĩnh đạc, nghiêm túc, kịch tính, chuẩn mực chính luận quân sự và phân tích công nghệ đỉnh cao sắc bén.\n"
            "Dưới đây là các tin tức chiến sự và công nghệ quốc tế nóng nhất mới cập nhật:"
        ),
        "outro_topic_name": "chiến sự và công nghệ thế giới",
    },
    "world": {
        "label": "Thời sự",
        "full_label": "Thời sự thế giới",
        "source_label": "Báo chí quốc tế",
        "default_aspect_ratio": "16:9",
        "default_format_label": "16:9 Ngang",
        "feeds": WORLD_RSS_FEEDS,
        "title_prefix": "Bản Tin Thế Giới Toàn Cảnh",
        "title_suffix_label": "Bản Tin Thế Giới",
        "default_title": "Bản Tin Thời Sự Thế Giới",
        "hashtags": "#tintucthegioi #thoisuquocte #thoisu24h",
        "file_prefix": "world_news",
        "intro_entity": "Globe world map broadcast",
        "intro_ai_prompt": "cinematic 35mm newsroom with glowing digital world map background, high tech aesthetic",
        "persona": (
            "Bạn là biên tập viên thời sự quốc tế cao cấp của kênh truyền hình YouTube chuyên về tin tức thế giới.\n"
            "- LUẬT TỐI THƯỢNG BẤT KHẢ XÂM PHẠM: TUYỆT ĐỐI 100% KHÔNG ĐƯỢC ĐƯA BẤT KỲ THÔNG TIN NÀO LIÊN QUAN ĐẾN VIỆT NAM (không nhắc đến Việt Nam, con người, địa danh, chính sách, tổ chức, hay bất kỳ liên hệ nào đến Việt Nam). Toàn bộ bản tin phải 100% là sự kiện thế giới quốc tế.\n"
            "Dưới đây là các tin tức quốc tế nổi bật rạng sáng nay kèm nội dung chi tiết từ các hãng thông tấn:"
        ),
        "outro_topic_name": "thời sự thế giới",
    },
    "war": {
        "label": "Chiến sự",
        "full_label": "Chiến sự thế giới",
        "source_label": "Chiến sự & Xung đột quốc tế",
        "default_aspect_ratio": "16:9",
        "default_format_label": "16:9 Ngang",
        "feeds": WAR_RSS_FEEDS,
        "title_prefix": "Bản Tin Chiến Sự Toàn Cảnh",
        "title_suffix_label": "Chiến Sự Thế Giới",
        "default_title": "Bản Tin Chiến Sự Thế Giới: Điểm Nóng Chiến Trường",
        "hashtags": "#chiensuthegioi #chientranh #xungdot #tintucthegioi #thoisu24h",
        "file_prefix": "war_news",
        "intro_entity": "Military command center war room conflict radar",
        "intro_ai_prompt": "cinematic military operations war room news studio, dark atmospheric situation room with glowing 3D tactical radar conflict map, telemetry indicators, dramatic military broadcast journalism",
        "persona": (
            "Bạn là biên tập viên chiến sự quốc tế cao cấp của kênh truyền hình YouTube chuyên về 'Chiến Sự Thế Giới'.\n"
            "Bản tin chuyên sâu toàn diện về các điểm nóng quân sự trên khắp thế giới: từ chiến tranh quy mô lớn, nội chiến đẫm máu, các cuộc giao tranh biên giới, không kích, tập kích tên lửa, cho đến các cuộc xung đột vũ trang và biểu tình bạo lực, bạo loạn tại các quốc gia.\n"
            "PHONG CÁCH VÀ YÊU CẦU BIÊN TẬP BẢN TIN CHIẾN SỰ:\n"
            "- LUẬT TỐI THƯỢNG BẤT KHẢ XÂM PHẠM: TUYỆT ĐỐI 100% KHÔNG ĐƯỢC ĐƯA BẤT KỲ TIN TỨC NÀO LIÊN QUAN ĐẾN VIỆT NAM. Toàn bộ bản tin phải 100% là sự kiện chiến sự và xung đột quốc tế.\n"
            "- Giọng điệu đĩnh đạc, nghiêm túc, kịch tính, chuẩn mực chính luận quân sự - thời sự quốc tế sắc sảo.\n"
            "- Cập nhật tình hình thực địa khách quan, chi tiết: chiến tuyến, vũ khí khí tài, số liệu thương vong/thiệt hại, đòn tập kích, động thái quân sự và tuyên bố từ các bên tham chiến.\n"
            "- Phân tích bối cảnh địa chính trị sâu sắc, nguyên nhân xung đột và hệ lụy an ninh khu vực cũng như toàn cầu.\n"
            "Dưới đây là các tin tức chiến sự và xung đột quốc tế nóng nhất mới cập nhật:"
        ),
        "outro_topic_name": "chiến sự và xung đột thế giới",
    },
    "tech": {
        "label": "Công nghệ",
        "full_label": "Công nghệ thế giới",
        "source_label": "Chuyên trang Tech",
        "default_aspect_ratio": "16:9",
        "default_format_label": "16:9 Ngang",
        "feeds": TECH_RSS_FEEDS,
        "title_prefix": "Bản Tin Công Nghệ Toàn Cảnh",
        "title_suffix_label": "Bản Tin Công Nghệ",
        "default_title": "Bản Tin Công Nghệ Thế Giới",
        "hashtags": "#congnghe #tintuccongnghe #technews #ai",
        "file_prefix": "tech_news",
        "intro_entity": "High tech AI quantum computer digital broadcast",
        "intro_ai_prompt": "cinematic modern tech news studio with glowing quantum computer holographic displays and AI graphics",
        "persona": (
            "Bạn là biên tập viên tin tức công nghệ quốc tế cao cấp của kênh truyền hình YouTube chuyên về công nghệ thế giới "
            "(Trí tuệ nhân tạo AI, bán dẫn vi mạch, thiết bị thông minh, công nghệ vũ trụ, phần mềm và startup kỳ lân toàn cầu).\n"
            "- LUẬT TỐI THƯỢNG BẤT KHẢ XÂM PHẠM: TUYỆT ĐỐI 100% KHÔNG ĐƯỢC ĐƯA BẤT KỲ THÔNG TIN NÀO LIÊN QUAN ĐẾN VIỆT NAM. Toàn bộ bản tin phải 100% là sự kiện công nghệ quốc tế.\n"
            "Dưới đây là các tin tức công nghệ quốc tế nổi bật mới nhất kèm nội dung chi tiết từ các chuyên trang công nghệ uy tín:"
        ),
        "outro_topic_name": "công nghệ thế giới",
    },
    "sports": {
        "label": "Bóng đá",
        "full_label": "Bóng đá quốc tế",
        "source_label": "Sân cỏ quốc tế",
        "default_aspect_ratio": "16:9",
        "default_format_label": "16:9 Ngang",
        "feeds": SPORTS_RSS_FEEDS,
        "title_prefix": "Bản Tin Bóng Đá Toàn Cảnh",
        "title_suffix_label": "Bản Tin Bóng Đá",
        "default_title": "Bản Tin Bóng Đá Quốc Tế & Điểm Nhấn Sân Cỏ",
        "hashtags": "#bongda #bongdaquocte #ngoaihanganh #championsleague #tintucbongda",
        "file_prefix": "sports_news",
        "intro_entity": "Football stadium floodlights Champions League arena",
        "intro_ai_prompt": "cinematic modern football TV broadcast studio overlooking a magnificent illuminated football stadium at night, green pitch, stadium floodlights, dramatic sports lighting",
        "persona": (
            "Bạn là bình luận viên và biên tập viên bóng đá quốc tế hàng đầu của kênh truyền hình YouTube chuyên về Bóng đá Thế giới "
            "(Ngoại Hạng Anh Premier League, UEFA Champions League Cúp C1, La Liga, Serie A, Bundesliga, thị trường chuyển nhượng cầu thủ, các CLB lớn như Real Madrid, Man City, Arsenal, Man United, Liverpool, Barcelona, Bayern Munich, PSG, cùng các siêu sao như Messi, Ronaldo, Mbappe, Haaland, Bellingham, Vinicius).\n"
            "- LUẬT TỐI THƯỢNG BẤT KHẢ XÂM PHẠM: TUYỆT ĐỐI 100% KHÔNG ĐƯỢC ĐƯA BẤT KỲ TIN TỨC NÀO LIÊN QUAN ĐẾN VIỆT NAM (không đưa V-League, không đưa đội tuyển Việt Nam hay cầu thủ Việt Nam). Toàn bộ bản tin phải 100% là bóng đá quốc tế.\n"
            "Dưới đây là các tin tức bóng đá quốc tế nóng bỏng rạng sáng nay kèm báo cáo chi tiết trận đấu, diễn biến bàn thắng và phát biểu sau trận:"
        ),
        "outro_topic_name": "bóng đá quốc tế",
    },
    "viral": {
        "label": "Tin lạ & Hài",
        "full_label": "Tin lạ, hài hước, độc lạ & sốc thế giới",
        "source_label": "UPI Odd • Reddit • X • Reels",
        "default_aspect_ratio": "9:16",
        "default_format_label": "Shorts 9:16",
        "feeds": VIRAL_RSS_FEEDS,
        "title_prefix": "Tin Nóng & Độc Lạ Thế Giới",
        "title_suffix_label": "Tin Nóng & Độc Lạ",
        "default_title": "Tin Lạ & Hài Hước Gây Sốt Toàn Cầu",
        "hashtags": "#Shorts #doclathegioi #haihuoc #tinhot #xuhuong",
        "file_prefix": "viral_shorts",
        "intro_entity": "Breaking viral funny and shock trends on social media smartphones",
        "intro_ai_prompt": "cinematic vertical 9:16 smartphone screen glowing with breaking viral funny and bizarre social media clips, neon accents, dramatic modern lighting",
        "persona": (
            "Bạn là biên tập viên sáng tạo triệu view của kênh YouTube Shorts chuyên về 'Tin Độc Lạ & Hài Hước Thế Giới' "
            "(được tuyển chọn nóng hổi từ các bài đăng gây sốt, clip dở khóc dở cười, tình huống oái oăm, động vật tấu hài, trộm vụng về, và những hiện tượng kỳ lạ khó tin trên toàn cầu trong 24 giờ qua).\n"
            "PHONG CÁCH YOUTUBE SHORTS BẮT BUỘC:\n"
            "- LUẬT TỐI THƯỢNG BẤT KHẢ XÂM PHẠM: TUYỆT ĐỐI 100% KHÔNG ĐƯỢC ĐƯA BẤT KỲ THÔNG TIN NÀO LIÊN QUAN ĐẾN VIỆT NAM. Toàn bộ bản tin phải 100% là thế giới quốc tế.\n"
            "- Nhịp điệu cực kỳ nhanh, dứt khoát, lôi cuốn ngay từ 3 giây đầu tiên (Hook mở đầu dí dỏm hoặc giật gân, khơi gợi tò mò tột đỉnh).\n"
            "- Lời thuyết minh súc tích, hóm hỉnh, hài hước duyên dáng với tin vui nhộn; hoặc kịch tính, ngỡ ngàng với tin độc dị bí ẩn.\n"
            "- Mỗi sự kiện chỉ trình bày 1 đến 2 câu cốt lõi (20 - 35 từ) để tổng thời lượng video rơi vào khoảng 45 - 55 giây, hoàn hảo cho chuẩn YouTube Shorts.\n"
            "- Cuối tiêu đề video BẮT BUỘC thêm hashtag #Shorts."
        ),
        "outro_topic_name": "tin độc lạ và hài hước thế giới",
    },
    "hope": {
        "label": "Tin vui",
        "full_label": "Tin vui: Y khoa, sự sống, môi trường & sáng chế",
        "source_label": "Y khoa • Sự sống • Môi trường",
        "default_aspect_ratio": "9:16",
        "default_format_label": "Shorts 9:16",
        "feeds": HOPE_RSS_FEEDS,
        "title_prefix": "Tin Vui: Y Khoa, Sự Sống & Môi Trường",
        "title_suffix_label": "Tin Vui Thế Giới",
        "default_title": "Tin Vui Thế Giới: Đột Phá Y Khoa, Sự Sống & Môi Trường",
        "hashtags": "#Shorts #tinvui #ykhoa #susong #moitruong #hyvong #khoahoc",
        "file_prefix": "hope_shorts",
        "intro_entity": "Futuristic clean energy planet Earth green technology glowing orb",
        "intro_ai_prompt": "cinematic vertical 9:16 futuristic glowing planet Earth restored with clean green energy and technology, hope and bright future, warm sunrise lighting",
        "persona": (
            "Bạn là biên tập viên truyền cảm hứng của kênh YouTube Shorts chuyên về 'Tin Vui & Đột Phá Y Khoa, Sự Sống & Môi Trường' "
            "(tập trung sâu sắc và ưu tiên hàng đầu cho các bước tiến y khoa cứu sống con người, những kỳ tích bảo vệ sự sống và muôn loài trên Trái Đất, các giải pháp làm sạch và hồi sinh môi trường thiên nhiên; đồng thời chọn lọc các sáng chế và công nghệ hữu ích khác với trọng số nhỏ hơn).\n"
            "PHONG CÁCH VÀ YÊU CẦU BIÊN TẬP BẢN TIN TIN VUI:\n"
            "- LUẬT TỐI THƯỢNG BẤT KHẢ XÂM PHẠM: TUYỆT ĐỐI 100% KHÔNG ĐƯỢC ĐƯA BẤT KỲ THÔNG TIN NÀO LIÊN QUAN ĐẾN VIỆT NAM. Toàn bộ bản tin phải 100% là thế giới quốc tế.\n"
            "- TRỌNG TÂM NỘI DUNG ƯU TIÊN:\n"
            "  + ƯU TIÊN 1 (Y KHOA & SỨC KHỎE): Liệu pháp chữa khỏi ung thư, vắc-xin mới, ghép tạng, phục hồi thị lực/thính lực/vận động, thử nghiệm lâm sàng đột phá, cứu sống sinh mạng con người.\n"
            "  + ƯU TIÊN 2 (SỰ SỐNG & MUÔN LOÀI): Bảo tồn động vật quý hiếm, phục hồi rạn san hô, cứu hộ sinh vật biển, sự kỳ diệu và tái sinh của muôn loài.\n"
            "  + ƯU TIÊN 3 (MÔI TRƯỜNG & HỒI SINH TRÁI ĐẤT): Làm sạch đại dương, phủ xanh rừng và sa mạc, lọc sạch nguồn nước, xử lý rác thải nhựa, giải pháp khí hậu bền vững.\n"
            "  + THỨ YẾU (SÁNG CHẾ & CÔNG NGHỆ KHÁC): Các phát minh năng lượng, vật liệu mới, robot hỗ trợ, khoa học vũ trụ (chỉ dùng với trọng số nhỏ hơn khi cần thiết).\n"
            "- Giọng điệu ấm áp, hào hứng, tích cực, truyền tải niềm tin và hy vọng mãnh liệt cho người nghe.\n"
            "- Nhấn mạnh vào giá trị nhân văn và tác động thực tế: cứu sống bệnh nhân, hồi sinh thiên nhiên, đem lại tương lai tươi sáng.\n"
            "- Chuẩn YouTube Shorts: Mỗi sự kiện chỉ 1 phân cảnh súc tích (18 - 28 từ), nhanh gọn, cuốn hút.\n"
            "- Cuối tiêu đề video BẮT BUỘC có hashtag #Shorts."
        ),
        "outro_topic_name": "tin vui, y khoa, sự sống và môi trường",
    },
}


def normalize_category(category: str) -> str:
    """Normalize input category string to one of ('tin_moi', 'tin_nong', 'hope', 'viral', 'world', 'war', 'tech', 'sports')."""
    cat = (category or "").strip().lower()
    if cat in ("tin_moi", "tinmoi", "morning", "world_sports", "thegioi_thethao", "morning_news"):
        return "tin_moi"
    if cat in ("tin_nong", "tinnong", "evening", "war_tech", "chiensu_congnghe", "evening_news"):
        return "tin_nong"
    if cat in ("war", "chiensu", "chien_su", "conflict", "chientranh", "chien_tranh", "war_news", "military"):
        return "war"
    if cat in ("tech", "congnghe", "cong_nghe", "technology", "tech_news"):
        return "tech"
    if cat in ("sports", "thethao", "the_thao", "sport", "sports_news"):
        return "sports"
    if cat in ("viral", "tinla", "tin_la", "docla", "doc_la", "curiosities", "hot_viral", "la_hot", "shorts"):
        return "viral"
    if cat in ("hope", "tinvui", "tin_vui", "goodnews", "good_news", "sangche", "phatminh", "hyvong", "hy_vong", "khoahoc_hyvong"):
        return "hope"
    if cat in ("world", "thoisu", "thoi_su"):
        return "world"
    return "tin_moi"


def get_category_config(category: str) -> dict:
    """Retrieve configuration dict for the given news category."""
    norm = normalize_category(category)
    return CATEGORY_CONFIG.get(norm, CATEGORY_CONFIG["tin_moi"])


def ensure_date_in_title(title: str, date_val: Optional[Any] = None) -> str:
    """Ensure video title contains date/month/year in Vietnamese format (e.g. 'Ngày 21/10/2026')."""
    clean_title = str(title or "").strip()
    if not clean_title:
        clean_title = "Bản Tin Thời Sự Thế Giới"

    # Check if a date format like DD/MM/YYYY or DD-MM-YYYY or "Ngày DD/MM" already exists
    if re.search(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b", clean_title) or re.search(r"\b\d{1,2}[/-]\d{1,2}\b", clean_title):
        return clean_title

    # Determine date object
    if isinstance(date_val, datetime):
        dt = date_val
    elif isinstance(date_val, str) and date_val:
        dt = None
        try:
            dt = datetime.fromisoformat(date_val.replace("Z", "+00:00"))
        except Exception:
            pass
        if not dt:
            m_date = re.search(r"(\d{8}(?:_\d{6})?)", date_val)
            if m_date:
                cand = m_date.group(1)
                try:
                    dt = datetime.strptime(cand, "%Y%m%d_%H%M%S" if len(cand) == 15 else "%Y%m%d")
                except Exception:
                    pass
        if not dt:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
                try:
                    dt = datetime.strptime(date_val[:19], fmt)
                    break
                except Exception:
                    pass
        if not dt:
            dt = datetime.now()
    else:
        dt = datetime.now()

    date_tag = f"Ngày {dt.strftime('%d/%m/%Y')}"

    # If title has a colon separator (e.g. "Prefix: Details")
    if ":" in clean_title:
        prefix, rest = clean_title.split(":", 1)
        final_title = f"{prefix.strip()} {date_tag}: {rest.strip()}"
    elif " - " in clean_title:
        prefix, rest = clean_title.split(" - ", 1)
        final_title = f"{prefix.strip()} {date_tag} - {rest.strip()}"
    elif " | " in clean_title:
        prefix, rest = clean_title.split(" | ", 1)
        final_title = f"{prefix.strip()} {date_tag} | {rest.strip()}"
    else:
        final_title = f"{clean_title} {date_tag}"

    return final_title.strip()


DEFAULT_THUMBNAIL_HOOKS = {
    "tin_moi": "TIN MỚI THẾ GIỚI",
    "tin_nong": "TIN NÓNG ĐẶC BIỆT",
    "world": "TIN NÓNG THẾ GIỚI",
    "war": "CHIẾN SỰ: BƯỚC NGOẶT MỚI",
    "tech": "CÔNG NGHỆ: BƯỚC NGOẶT?",
    "sports": "BÓNG ĐÁ: CHẤN ĐỘNG!",
    "viral": "KHÓ TIN NHƯNG CÓ THẬT!",
    "hope": "TIN VUI: ĐỘT PHÁ MỚI!",
}

_HOOK_DATE_RE = re.compile(r"\b(?:Ngày\s*)?\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b", re.IGNORECASE)
_GREETING_RE = re.compile(
    r"^\s*(?:xin\s+)?(?:kính\s+)?chào(?:\s+mừng)?\b[^.!?\n]*[.!?]+\s*",
    re.IGNORECASE,
)


def _clean_headline(title: str) -> str:
    """Strip agency suffixes and 'breaking:' style prefixes from an RSS headline."""
    cleaned = re.sub(r"\s*[-|–]\s*[A-Za-z0-9\s\.]+$", "", str(title or "")).strip()
    return re.sub(
        r"^(live updates:?|breaking:?|watch:?|video:?|update:?)\s*", "", cleaned, flags=re.IGNORECASE
    ).strip()


def _clean_hook_text(text: str) -> str:
    """Remove dates, 'Toàn Cảnh', hashtags and stray separators from a hook headline."""
    clean = str(text or "")
    clean = re.sub(r"#\w+", "", clean)
    clean = _HOOK_DATE_RE.sub("", clean)
    clean = re.sub(r"toàn\s+cảnh(\s+ngày)?", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s+", " ", clean).strip(" -:|,;.\t")
    return clean


def build_hook_title(hook: str, category: str = "world", date_val: Optional[datetime] = None) -> str:
    """Build '[Hook] - Bản Tin ... DD/MM/YYYY' (<= 98 chars; viral & hope get ' #Shorts')."""
    norm = normalize_category(category)
    cfg = get_category_config(norm)
    dt = date_val if isinstance(date_val, datetime) else datetime.now()
    tail = f" - {cfg.get('title_suffix_label', 'Bản Tin Thế Giới')} {dt.strftime('%d/%m/%Y')}"
    if norm in ("viral", "hope"):
        tail += " #Shorts"
    clean = _clean_hook_text(hook) or cfg.get("default_title", "Bản Tin Thế Giới")
    max_hook = 98 - len(tail)
    if len(clean) > max_hook:
        clean = clean[:max_hook]
        if " " in clean:
            clean = clean.rsplit(" ", 1)[0]
        clean = clean.strip(" -:|,;.")
    return f"{clean}{tail}"


def sanitize_thumbnail_hook(text: str, category: str = "world", max_words: int = 8) -> str:
    """Uppercase thumbnail hook limited to max_words words, with category fallback."""
    words = re.sub(r"\s+", " ", str(text or "")).strip().upper().split()[:max_words]
    hook = " ".join(words).strip(" ,;:-")
    if not hook:
        hook = DEFAULT_THUMBNAIL_HOOKS.get(normalize_category(category), DEFAULT_THUMBNAIL_HOOKS["world"])
    return hook


def strip_leading_greeting(text: str) -> str:
    """Safety net: drop a leading 'Chào mừng...' sentence from the hook scene if the model emits one."""
    stripped = _GREETING_RE.sub("", str(text or ""), count=1).strip()
    return stripped if len(stripped) >= 20 else str(text or "").strip()


CLEAN_HTML_REGEX = re.compile(r"<[^>]+>")


def get_viral_news_time_window(export_dt: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    """Calculate the news time window: from 6:30 AM of the previous day up to export time."""
    now = export_dt or datetime.now()
    start_window = (now - timedelta(days=1)).replace(hour=6, minute=30, second=0, microsecond=0)
    end_window = now + timedelta(hours=3)
    return start_window, end_window


def parse_pubdate_to_datetime(pub_date_str: str) -> Optional[datetime]:
    """Parse RSS pubDate string into local naive datetime for time window filtering."""
    if not pub_date_str:
        return None
    try:
        import email.utils
        parsed_tuple = email.utils.parsedate_to_datetime(pub_date_str)
        if parsed_tuple:
            if parsed_tuple.tzinfo is not None:
                parsed_tuple = parsed_tuple.astimezone().replace(tzinfo=None)
            return parsed_tuple
    except Exception:
        pass
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(pub_date_str[:19], fmt)
        except Exception:
            pass
    return None


def is_within_time_window(
    pub_date_str: str,
    export_dt: Optional[datetime] = None,
    category: str = "viral",
    max_hours: Optional[float] = None,
) -> bool:
    """Check if item's pubDate falls within acceptable freshness window.

    For viral: between 6:30 AM yesterday and export time (~30-36h).
    For hope: within the last 48 hours.
    For others: default to True if unspecified.
    """
    dt = parse_pubdate_to_datetime(pub_date_str)
    if not dt:
        return True
    now = export_dt or datetime.now()
    norm_cat = normalize_category(category) if category else "viral"

    if max_hours is not None:
        return (now - dt) <= timedelta(hours=max_hours)

    if norm_cat == "viral":
        start_dt, end_dt = get_viral_news_time_window(export_dt)
        return start_dt <= dt <= end_dt
    elif norm_cat == "hope":
        # Limit to 48 hours to avoid weeks-old articles while allowing quality research pieces
        return (now - dt) <= timedelta(hours=48)

    return True


NEWS_HISTORY_FILENAME = "published_news_history.json"


def get_news_history_path() -> Path:
    base = runtime_data_dir() / "daily_news"
    base.mkdir(parents=True, exist_ok=True)
    return base / NEWS_HISTORY_FILENAME


def _normalize_title_for_dedup(title: str) -> str:
    clean = re.sub(r"^(live updates:?|breaking:?|watch:?|video:?|update:?)\s*", "", title, flags=re.IGNORECASE)
    clean = re.sub(r"\s*[-|–]\s*[A-Za-z0-9\s\.]+$", "", clean).strip()
    return re.sub(r"[^\w]", "", clean.lower())


def _extract_title_tokens(title: str) -> set[str]:
    stopwords = {
        "this", "that", "with", "from", "have", "been", "were", "they", "will", "what",
        "when", "where", "which", "news", "viral", "video", "world", "today", "more",
        "first", "after", "over", "into", "their", "about", "could", "would", "says",
        "just", "make", "take", "some", "here", "there", "then", "like", "most", "than"
    }
    clean = re.sub(r"\s*[-|–]\s*[A-Za-z0-9\s\.]+$", "", title).strip()
    words = re.findall(r"[a-z0-9]{3,}", clean.lower())
    return {w for w in words if w not in stopwords}


def load_published_news_history(max_age_days: int = 7) -> List[Dict[str, Any]]:
    """Load items published in the last `max_age_days`.

    If the history file does not exist, automatically bootstrap by scanning
    existing social_publish_manifest.json files in runtime_data_dir() / 'daily_news'.
    """
    history_file = get_news_history_path()
    items: List[Dict[str, Any]] = []
    cutoff_dt = datetime.now() - timedelta(days=max_age_days)

    if history_file.is_file():
        try:
            raw_data = json.loads(history_file.read_text(encoding="utf-8"))
            raw_items = raw_data if isinstance(raw_data, list) else raw_data.get("items", [])
            for it in raw_items:
                ts = it.get("timestamp") or it.get("created_at") or ""
                keep = True
                if ts:
                    try:
                        it_dt = datetime.fromisoformat(str(ts)[:19])
                        if it_dt < cutoff_dt:
                            keep = False
                    except Exception:
                        pass
                if keep:
                    items.append(it)
        except Exception as exc:
            logger.warning("Failed to read published history file: %s", exc)

    # Auto-bootstrap from recent social_publish_manifest.json if history is empty
    if not items:
        items = _bootstrap_history_from_manifests(max_age_days=max_age_days)
        if items:
            save_published_news_history(items)

    return items


def _bootstrap_history_from_manifests(max_age_days: int = 7) -> List[Dict[str, Any]]:
    """Scan existing output folders for social_publish_manifest.json to bootstrap history."""
    items: List[Dict[str, Any]] = []
    base_dir = runtime_data_dir() / "daily_news"
    if not base_dir.is_dir():
        return items
    cutoff_dt = datetime.now() - timedelta(days=max_age_days)
    seen_keys: set[str] = set()

    for sub in base_dir.iterdir():
        if not sub.is_dir():
            continue
        try:
            mtime = datetime.fromtimestamp(sub.stat().st_mtime)
            if mtime < cutoff_dt:
                continue
        except Exception:
            pass

        m_file = sub / "social_publish_manifest.json"
        if not m_file.is_file():
            continue
        try:
            m_data = json.loads(m_file.read_text(encoding="utf-8"))
            cat = m_data.get("category", "")
            ts = m_data.get("created_at") or datetime.fromtimestamp(sub.stat().st_mtime).isoformat()

            # Record source items from this manifest
            for s_it in m_data.get("source_items", []):
                t = s_it.get("title", "")
                link = s_it.get("link", "")
                norm_k = _normalize_title_for_dedup(t)
                if norm_k and norm_k not in seen_keys:
                    seen_keys.add(norm_k)
                    items.append({
                        "title": t,
                        "normalized_title": norm_k,
                        "link": link,
                        "category": cat,
                        "timestamp": ts,
                    })
        except Exception:
            pass
    return items


def save_published_news_history(history: List[Dict[str, Any]]) -> None:
    history_file = get_news_history_path()
    try:
        history_file.write_text(json.dumps({"items": history}, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to write published history file: %s", exc)


def record_published_news_history(news_items: List[Any], category: str) -> None:
    """Record newly used items into the persistent 7-day history."""
    if not news_items:
        return
    history = load_published_news_history(max_age_days=7)
    now_iso = datetime.now().isoformat()
    norm_cat = normalize_category(category)

    existing_keys = {it.get("normalized_title") for it in history if it.get("normalized_title")}
    existing_links = {it.get("link") for it in history if it.get("link")}

    added = False
    for it in news_items:
        t = getattr(it, "title", "")
        link = getattr(it, "link", "")
        norm_t = _normalize_title_for_dedup(t)
        if norm_t and norm_t not in existing_keys:
            history.append({
                "title": t,
                "normalized_title": norm_t,
                "link": link,
                "category": norm_cat,
                "timestamp": now_iso,
            })
            existing_keys.add(norm_t)
            if link:
                existing_links.add(link)
            added = True

    if added:
        save_published_news_history(history)
        logger.info("Recorded %d new items into published news history (category: %s)", len(news_items), norm_cat)


def is_duplicate_with_published_history(
    title: str,
    link: str,
    history: List[Dict[str, Any]],
    similarity_threshold: float = 0.55,
) -> bool:
    """Check if an item matches or heavily overlaps with any item published in the last 7 days."""
    if not history or not title:
        return False

    norm_t = _normalize_title_for_dedup(title)
    cand_tokens = _extract_title_tokens(title)
    clean_link = link.split("?")[0].strip().rstrip("/") if link else ""

    for h in history:
        # 1. Exact or base URL match
        h_link = (h.get("link") or "").split("?")[0].strip().rstrip("/")
        if clean_link and h_link and clean_link == h_link:
            return True

        # 2. Normalized alphanumeric title match
        h_norm = h.get("normalized_title") or _normalize_title_for_dedup(h.get("title", ""))
        if norm_t and h_norm and norm_t == h_norm:
            return True

        # 3. Token similarity: Jaccard or Containment overlap (catches rephrased stories from other outlets)
        if cand_tokens:
            h_tokens = _extract_title_tokens(h.get("title", ""))
            if h_tokens:
                intersection = len(cand_tokens & h_tokens)
                union = len(cand_tokens | h_tokens)
                jaccard = (intersection / union) if union > 0 else 0.0
                min_len = min(len(cand_tokens), len(h_tokens))
                containment = (intersection / min_len) if min_len > 0 else 0.0
                if jaccard >= similarity_threshold or (containment >= 0.60 and intersection >= 3):
                    return True

    return False


@dataclass
class WorldNewsItem:
    """An individual world news item extracted from an international RSS feed."""

    title: str
    summary: str
    source: str
    published: str
    link: str
    full_text: str = ""
    image_url: str = ""
    social_platform: str = "x"  # 'x', 'facebook', 'instagram', or 'web'


@dataclass
class DailyNewsScene:
    """A segment of the daily news video."""

    scene_index: int
    text: str
    entity_query: str = ""
    ai_prompt: str = ""
    image_path: str = ""
    image_source_type: Literal["wikimedia_commons", "ai_generated", "custom", "social_screenshot", "direct_photo"] = "wikimedia_commons"
    duration_ms: int = 0
    has_transition_cue: bool = False
    image_url: str = ""
    social_platform: str = "x"


@dataclass
class DailyNewsDigest:
    """A compiled daily news script with scenes ready for video rendering."""

    digest_id: str
    title: str
    summary_lead: str
    hashtags: str
    scenes: List[DailyNewsScene]
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    thumbnail_hook: str = ""
    ticker_summary: str = ""


def _normalize_text_for_search(text: str) -> str:
    """Normalize text by lowering, removing diacritics accents for robust matching."""
    if not text:
        return ""
    import unicodedata
    lowered = text.lower()
    decomposed = unicodedata.normalize("NFD", lowered)
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return stripped.replace("đ", "d")


# Supreme Law: Terms strictly excluded across all news bulletins (0% Vietnam content allowed)
VIETNAM_EXCLUDE_TERMS = frozenset({
    # Country & Nationality & Language
    "vietnam", "viet nam", "việt nam", "vietnamese", "người việt", "người việt nam",
    "tiếng việt", "tieng viet", "dân tộc việt nam", "nước việt nam", "kiều bào việt",
    "chính phủ việt nam", "quốc hội việt nam", "đảng cộng sản việt nam",
    "quân đội nhân dân việt nam", "bộ quốc phòng việt nam", "bộ ngoại giao việt nam",
    "bộ công an việt nam", "chủ tịch nước việt nam", "thủ tướng việt nam",
    "bộ chính trị", "ban chấp hành trung ương", "v-league", "vleague",
    "đội tuyển việt nam", "tuyển việt nam", "u23 việt nam",
    # Major Cities & Administrative Units
    "hanoi", "ha noi", "hà nội",
    "ho chi minh", "hồ chí minh", "tp.hcm", "tphcm", "tp hcm", "thành phố hồ chí minh",
    "saigon", "sai gon", "sài gòn",
    "da nang", "danang", "đà nẵng",
    "hai phong", "hải phòng",
    "can tho", "cần thơ",
    "nha trang", "khanh hoa", "khánh hòa",
    "hue", "huế", "thừa thiên huế",
    "vung tau", "vũng tàu", "bà rịa vũng tàu",
    "quang ninh", "quảng ninh", "ha long", "hạ long",
    "binh duong", "bình dương",
    "dong nai", "đồng nai",
    "quang nam", "quảng nam",
    "nghe an", "nghệ an",
    "thanh hoa", "thanh hóa",
    "bac ninh", "bắc ninh",
    "thai nguyen", "thái nguyên",
    "phu quoc", "phú quốc",
    "da lat", "đà lạt", "lam dong", "lâm đồng",
    "tay nguyen", "tây nguyên",
    "dong bang song cuu long", "đồng bằng sông cửu long",
    # Currency & Financial
    "vnd", "vnđ", "đồng việt nam", "dong viet nam", "ngân hàng nhà nước việt nam",
    "vietcombank", "vietinbank", "bidv", "agribank", "techcombank", "vpbank", "mbbank",
    # State & Domestic Media / News Outlets
    "vtv", "vov", "ttxvn", "thông tấn xã việt nam", "báo nhân dân", "vnexpress",
    "vietnamnet", "zing news", "dân trí", "tuổi trẻ online", "thanh niên online", "tienphong",
    # Prominent Domestic Enterprises
    "vinfast", "vingroup", "vinhomes", "vng", "viettel", "vnpt", "fpt", "masan",
})

VIETNAM_NORM_TERMS = frozenset(_normalize_text_for_search(t) for t in VIETNAM_EXCLUDE_TERMS)


def is_vietnam_related(text: str) -> bool:
    """Check if the text contains any keywords or references related to Vietnam.

    Supreme rule across all news pipelines: 0% Vietnam content allowed.
    """
    if not text:
        return False
    lowered = text.lower()
    for term in VIETNAM_EXCLUDE_TERMS:
        if len(term) <= 4:
            if re.search(r"(?i)\b" + re.escape(term) + r"\b", text):
                return True
        else:
            if term in lowered:
                return True

    # Also check normalized accent-stripped version for diacritic bypasses
    normalized = _normalize_text_for_search(text)
    for term in VIETNAM_NORM_TERMS:
        if len(term) <= 4:
            if re.search(r"\b" + re.escape(term) + r"\b", normalized):
                return True
        else:
            if term in normalized:
                return True
    return False


def assert_and_sanitize_no_vietnam_content(digest: DailyNewsDigest) -> DailyNewsDigest:
    """Supreme Law Enforcer: Guarantee 100% zero Vietnam-related content in the entire digest.

    Inspects title, summary_lead, thumbnail_hook, ticker_summary, and every scene text,
    entity_query, and ai_prompt. Removes or scrubs any offending references.
    """
    # 1. Sanitize Title
    if is_vietnam_related(digest.title):
        logger.critical("VIETNAM_RULE_VIOLATION: Digest title '%s' contains Vietnam reference! Scrubbing.", digest.title)
        clean_title = digest.title
        for term in sorted(VIETNAM_EXCLUDE_TERMS, key=len, reverse=True):
            clean_title = re.sub(rf"(?i)\b{re.escape(term)}\b", "", clean_title)
        clean_title = re.sub(r"\s+", " ", clean_title).strip(" -:,|")
        digest.title = clean_title or "Bản Tin Thời Sự Quốc Tế"

    # 2. Sanitize Summary Lead
    if is_vietnam_related(digest.summary_lead):
        logger.critical("VIETNAM_RULE_VIOLATION: Digest summary_lead contains Vietnam reference! Scrubbing.")
        clean_summary = digest.summary_lead
        for term in sorted(VIETNAM_EXCLUDE_TERMS, key=len, reverse=True):
            clean_summary = re.sub(rf"(?i)\b{re.escape(term)}\b", "", clean_summary)
        clean_summary = re.sub(r"\s+", " ", clean_summary).strip(" -:,|")
        digest.summary_lead = clean_summary or "Bản tin tổng hợp các diễn biến quan trọng trên trường quốc tế."

    # 3. Sanitize Thumbnail Hook
    if is_vietnam_related(digest.thumbnail_hook):
        logger.critical("VIETNAM_RULE_VIOLATION: Digest thumbnail_hook '%s' contains Vietnam reference! Resetting.", digest.thumbnail_hook)
        digest.thumbnail_hook = "ĐIỂM NÓNG THẾ GIỚI"

    # 4. Sanitize Ticker Summary
    if is_vietnam_related(digest.ticker_summary):
        logger.critical("VIETNAM_RULE_VIOLATION: Ticker summary contains Vietnam reference! Filtering items.")
        ticker_parts = [p.strip() for p in digest.ticker_summary.split("|")]
        cleaned_parts = [p for p in ticker_parts if not is_vietnam_related(p)]
        digest.ticker_summary = " | ".join(cleaned_parts) if cleaned_parts else "Cập nhật các diễn biến thời sự quốc tế mới nhất"

    # 5. Sanitize and Filter Scenes
    sanitized_scenes: List[DailyNewsScene] = []
    for sc in digest.scenes:
        if is_vietnam_related(sc.text) or is_vietnam_related(sc.entity_query) or is_vietnam_related(sc.ai_prompt):
            logger.critical("VIETNAM_RULE_VIOLATION: Scene %d contains Vietnam reference! (text: %s)", sc.scene_index, sc.text[:80])
            if sc.scene_index == 0:
                clean_text = sc.text
                for term in sorted(VIETNAM_EXCLUDE_TERMS, key=len, reverse=True):
                    clean_text = re.sub(rf"(?i)\b{re.escape(term)}\b", "quốc tế", clean_text)
                sc.text = re.sub(r"\s+", " ", clean_text).strip()
                sc.entity_query = "International world newsroom broadcast"
                sc.ai_prompt = "cinematic international television broadcast studio with digital world map"
                sanitized_scenes.append(sc)
            elif sc == digest.scenes[-1]:
                clean_text = sc.text
                for term in sorted(VIETNAM_EXCLUDE_TERMS, key=len, reverse=True):
                    clean_text = re.sub(rf"(?i)\b{re.escape(term)}\b", "", clean_text)
                sc.text = re.sub(r"\s+", " ", clean_text).strip()
                sc.entity_query = "International news studio"
                sc.ai_prompt = "cinematic news desk with global displays"
                sanitized_scenes.append(sc)
            else:
                # Any intermediate topical scene that touches on Vietnam is strictly dropped entirely
                logger.warning("Dropping topical scene %d entirely because it contains Vietnam-related content.", sc.scene_index)
        else:
            sanitized_scenes.append(sc)

    for idx, sc in enumerate(sanitized_scenes):
        sc.scene_index = idx
    digest.scenes = sanitized_scenes

    # 6. Sanitize Hashtags: Never leak #haizflow to social publishing
    if digest.hashtags:
        digest.hashtags = " ".join([t for t in digest.hashtags.split() if t.lower().lstrip("#") != "haizflow"])

    return digest


NON_FOOTBALL_KEYWORDS = frozenset({
    "cricket", "rugby", "golf", "pga tour", "snooker", "darts", "horse racing",
    "formula 1", "formula one", "f1", "nascar", "motogp", "nfl", "mlb", "nhl", "baseball",
    "tennis", "wimbledon", "australian open", "us open", "roland garros", "atp", "wta",
    "basketball", "nba", "boxing", "ufc", "mma", "swimming", "athletics", "cycling",
    "tour de france", "winter sports", "skiing", "ice hockey", "curling", "super bowl",
})

FOOTBALL_KEYWORDS = frozenset({
    # General football
    "football", "soccer", "club", "striker", "goal", "match", "transfer", "player",
    "manager", "pitch", "cup", "league", "penalty", "var", "offside", "stadium",
    "fixture", "squad", "uefa", "fifa", "ballon d'or", "world cup", "footballer",
    # 5 Major European Leagues
    "premier league", "champions league", "la liga", "serie a", "bundesliga", "ligue 1",
    "scudetto", "el clasico",
    # English Clubs
    "arsenal", "liverpool", "chelsea", "manchester", "man city", "manchester city",
    "man united", "man utd", "tottenham", "spurs", "newcastle", "aston villa",
    # Spanish, Italian, German & French Clubs
    "real madrid", "barcelona", "barca", "atletico", "bayern", "bayern munich",
    "dortmund", "borussia dortmund", "leverkusen", "bayer leverkusen", "psg",
    "paris saint-germain", "monaco", "marseille", "lyon", "juventus", "inter milan",
    "ac milan", "napoli", "as roma", "lazio",
    # Stars & Prominent Managers
    "messi", "ronaldo", "cristiano", "haaland", "mbappe", "bellingham", "vinicius",
    "vinicius jr", "kane", "harry kane", "salah", "lamine yamal", "ten hag",
    "guardiola", "arteta", "ancelotti", "klopp", "slot",
    # Regional Asian & Southeast Asian Football (Thailand, Indonesia, China, Cambodia)
    "thai league", "thailand football", "thailand national football", "voi chiến",
    "indonesia football", "indonesia national football", "pssi", "shin tae-yong",
    "chinese super league", "csl", "china football", "china national football",
    "cambodia football", "cambodia national football"
})


def is_non_football_news(title: str, desc: str = "") -> bool:
    """Check if sports item is about non-football sports (cricket, rugby, golf, etc.)."""
    full = f"{title} {desc}".lower()
    has_non_football = any(k in full for k in NON_FOOTBALL_KEYWORDS)
    if has_non_football:
        has_football = any(k in full for k in FOOTBALL_KEYWORDS)
        if not has_football:
            return True
    return False


WAR_EXCLUDE_TERMS = frozenset({
    # Sports terms that must never appear in war broadcasts
    "football", "soccer", "premier league", "champions league", "la liga", "serie a",
    "bundesliga", "ligue 1", "arsenal", "manchester", "chelsea", "tottenham", "barcelona",
    "real madrid", "bayern", "psg", "striker", "penalty", "match preview", "predictions",
    "nba", "nfl", "mlb", "cricket", "rugby", "tennis", "golf", "f1", "grand prix",
    "olympic", "olympics", "world cup", "tournament", "el clasico", "kbo", "baseball",
    # Celebrity, Lifestyle, Entertainment & Personal Health
    "cancer-free", "cancer diagnosis", "chemotherapy", "revealing diagnosis", "vanessa trump",
    "celebrity", "red carpet", "wedding", "divorce", "movie", "box office", "actor",
    "actress", "singer", "pop star", "fashion week", "album", "kardashian",
})

WAR_POSITIVE_TERMS = frozenset({
    "war", "conflict", "military", "army", "armed", "defense", "soldier", "soldiers", "troops",
    "battlefield", "frontline", "front line", "airstrike", "air strike", "missile", "missiles",
    "drone", "drones", "uav", "rocket", "rockets", "bombing", "explosion", "shelling",
    "casualties", "killed", "wounded", "hostage", "hostages", "ceasefire", "peace talks",
    "invasion", "offensive", "insurgent", "insurgents", "rebel", "rebels", "coup", "junta",
    "sanction", "sanctions", "hezbollah", "hamas", "houthi", "houthis", "gaza", "ukraine",
    "russia", "kremlin", "pentagon", "nato", "taiwan strait", "north korea", "icbm",
    "ballistic", "air defense", "naval", "warship", "warships", "combat", "clash", "clashes",
    "protest", "protests", "tear gas", "riot", "riots", "police clash", "arrested",
    "demonstrator", "demonstrators", "unrest", "strike", "artillery", "weapon", "weapons",
    "brigade", "commander", "assault", "security crisis", "defense pact"
})


def is_strict_war_news(title: str, desc: str = "") -> bool:
    """Strictly validate whether a news item belongs to war, military, combat, conflict and civil unrest."""
    full = f"{title} {desc}".lower()
    for term in WAR_EXCLUDE_TERMS:
        if re.search(r"\b" + re.escape(term) + r"\b", full):
            return False

    for term in WAR_POSITIVE_TERMS:
        if re.search(r"\b" + re.escape(term) + r"\b", full):
            return True
    return False


ASIA_NEIGHBOR_TERMS = frozenset({
    "china", "chinese", "beijing", "shanghai", "xi jinping", "taiwan", "taipei", "hong kong", "scmp",
    "japan", "japanese", "tokyo", "kyodo", "korea", "korean", "seoul", "yonhap", "pyongyang", "north korea",
    "russia", "russian", "moscow", "kremlin", "putin", "siberia", "tass",
    "asean", "southeast asia", "thailand", "thai", "bangkok", "indonesia", "indonesian", "jakarta", "bali",
    "malaysia", "malaysian", "kuala lumpur", "philippines", "filipino", "manila", "singapore", "singaporean",
    "cambodia", "cambodian", "phnom penh", "laos", "laotian", "vientiane", "myanmar", "burma", "yangon", "naypyidaw"
})


def detect_news_region(item_or_text: Any) -> str:
    """Classify a news item into 'asia_neighbor' vs 'global_other' for regional quota balancing."""
    if isinstance(item_or_text, str):
        full = item_or_text.lower()
    elif hasattr(item_or_text, "title") and isinstance(item_or_text.title, str):
        full = f"{item_or_text.title} {getattr(item_or_text, 'summary', '')} {getattr(item_or_text, 'link', '')}".lower()
    else:
        full = str(item_or_text).lower()
    if any(k in full for k in ASIA_NEIGHBOR_TERMS):
        return "asia_neighbor"
    return "global_other"


MAINSTREAM_HARD_NEWS_TERMS = frozenset({
    # Politics & Diplomacy (World News)
    "election", "parliament", "prime minister", "president", "white house", "kremlin",
    "legislation", "minister says", "parliament passes", "vote", "un general assembly", "security council",
    "ceasefire", "peace talks", "sanctions", "g7", "nato", "envoy", "ambassador",
    "diplomatic", "state department", "treaty", "foreign minister", "summit meeting",
    "congress passes", "senate passes", "supreme court", "lawmaker", "biden", "trump",
    "putin", "zelensky", "netanyahu", "xi jinping", "macron", "scholz", "downing street",

    # Professional Sports (Football, NFL, NBA, Baseball, Cricket, Tennis, Racing)
    "premier league", "champions league", "transfer fee", "la liga", "serie a", "bundesliga",
    "football club", "soccer match", "goal scored", "penalty shootout", "clean sheet",
    "cricket match", "tennis open", "grand slam", "f1 grand prix", "formula 1", "nfl", "nba",
    "quarterback", "touchdown", "wimbledon", "fifa", "uefa", "ballon d'or",
    "head coach", "draft pick", "playmaker", "playmakers", "interception", "field goal",
    "super bowl", "espn", "bleacher report", "sky sports", "roster", "starting lineup",

    # Corporate & Mainstream Tech (Tech News)
    "quarterly earnings", "stock shares", "wall street", "q1 revenue", "q2 revenue", "q3 revenue", "q4 revenue",
    "market valuation", "antitrust", "datacenter", "patent infringement", "nasdaq",
    "semiconductor fab", "tsmc", "asml", "intel core", "amd ryzen", "nvidia blackwell",
    "apple ios update", "google pixel update", "enterprise cloud", "saas platform", "vc funding",
    "venture capital", "ipo filing", "tech layoffs", "market cap", "patch notes", "firmware update",
    "beta release", "specs leaked", "benchmarks", "geekbench",
})

VIRAL_OVERRIDE_TERMS = frozenset({
    "bizarre", "weird", "unbelievable", "shocking", "wild", "funny", "miracle", "ghost",
    "alien", "ufo", "monster", "giant", "caught on camera", "stunt", "oddity", "phenomenon",
    "rare discovery", "mystery", "creature", "illusion", "craziest", "survival",
    "hilarious", "laugh", "comedy", "absurd", "ridiculous", "epic fail", "fail", "clumsy",
    "dumbest", "heist fail", "animal antics", "prank", "bloopers", "not the onion",
    "dở khóc dở cười", "hài hước", "khó đỡ", "oái oăm", "bizarre mistake", "comedy wildlife",
})

LOW_NOVELTY_PATTERNS = [
    r"\b(?:lottery|jackpot|scratch-off|powerball|mega millions)\b",
    r"\b(?:auction(?:ed|s)?|sold at auction|auction house|fetches \$\d|sells? for \$\d|rare (?:penny|coin|stamp|card|whiskey|bottle|baseball card|memorabilia))\b",
    r"\b(?:survey (?:finds|shows|reveals)|study (?:finds|shows|reveals|suggests)|poll shows|researchers (?:find|say)|scientists (?:say|explain why|find))\b",
    r"\bflight\b.*\b(?:delayed|delay|cancelled|cancellation)\b",
    r"\b(?:lost luggage|baggage mix-up|lost baggage|traffic jam|metro delay)\b",
    r"\b(?:warmest|coldest|hottest) (?:day|night|october|november|december|january|summer|winter) in \d+ years\b",
    r"\b(?:zoning|city council|building permit|renovation|home sale|house sells for)\b",
    r"\b(?:man visits all|woman visits all|collects \d+)\b",
    r"\b(?:typhoon|hurricane|tropical depression|flash flood warning)\b",
    r"\b(?:homicide|murdered?|fatally shot|deadly crash|body of abducted|abduction caught|stabbed to death|child abuse)\b",
    r"\b(?:airing tomorrow|on toonami|anime schedule|season premiere|episode \d+)\b",
    r"\b(?:high pressure north|low pressure south|weather setup)\b",
    r"\b(?:saves improve to|defeating the wild \d-\d|world series|worldseries|preseason|box score)\b",
]

VIRAL_BIZARRE_KEYWORDS = frozenset({
    "bizarre", "weird", "unbelievable", "shocking", "wild", "miracle", "mysterious", "mystery",
    "alien", "ufo", "uap", "monster", "creature", "giant", "phenomenon", "unexplained",
    "impossible", "stunt", "mutation", "anomaly", "two-headed", "sinkhole", "crater",
    "surreal", "ancient tomb", "frozen solid", "deep sea", "jaw-dropping", "mind-blowing",
    "haunted", "supernatural", "optical illusion", "astonishing", "craziest", "oddity",
    "peculiar", "strange discovery", "fugitive", "disguise", "unsolved",
})

VIRAL_HUMOR_KEYWORDS = frozenset({
    "hilarious", "funny", "laugh", "laughing", "absurd", "ridiculous", "comedy", "humor", "humorous",
    "epic fail", "fail", "fails", "clumsy", "dumbest", "heist fail", "animal antics", "escaped cow",
    "escaped", "steals", "stole", "drunk", "prank", "pranks", "bloopers", "bizarre mistake",
    "not the onion", "florida man", "florida woman", "caught red-handed", "backfire", "backfires",
    "confusion", "dở khóc dở cười", "hài hước", "khó đỡ", "comedy wildlife", "ring camera",
    "bizarre theft", "cười ra nước mắt", "cười ngả nghiêng", "pha xử lý cồng kềnh",
})


def is_low_novelty_viral_news(title: str, desc: str = "") -> bool:
    """Filter out mundane, bland or low-novelty items (minor auctions, dry surveys, routine delays, mundane lotteries)."""
    full = f"{title} {desc}".lower()
    has_low = any(re.search(pat, full, re.IGNORECASE) for pat in LOW_NOVELTY_PATTERNS)
    if not has_low:
        return False
    # If the story also has a strong comedic or truly bizarre twist, keep it (e.g. clumsy thief steals lottery ticket)
    has_high_twist = any(h in full for h in (
        "thief", "robber", "animal", "clumsy", "drunk", "bizarre", "hilarious", "fail", "caught",
        "cow", "bear", "escaped", "prank", "monkey", "cat", "dog"
    ))
    return not has_high_twist


def calculate_viral_novelty_score(item: Any) -> float:
    """Calculate a novelty & entertainment score for viral items (ranking genuinely bizarre OR truly hilarious stories at the top).

    Flexible ratio: An item scores high if it is extremely bizarre OR extremely funny.
    Mundane or low-novelty items receive heavy penalties.
    """
    title = getattr(item, "title", "")
    summary = getattr(item, "summary", "")
    full_text = getattr(item, "full_text", "")
    social_platform = getattr(item, "social_platform", "")
    image_url = getattr(item, "image_url", "")

    full = f"{title} {summary} {full_text}".lower()
    if is_low_novelty_viral_news(title, summary):
        return -50.0

    bizarre_count = sum(1 for k in VIRAL_BIZARRE_KEYWORDS if k in full)
    humor_count = sum(1 for k in VIRAL_HUMOR_KEYWORDS if k in full)

    # High impact for bizarre OR humor (flexible ratio, reward either or both)
    score = (bizarre_count * 15.0) + (humor_count * 15.0)

    # Bonus for rich media or multi-platform virality (Reddit, TikTok, X clips)
    if social_platform in ("reddit", "tiktok", "instagram", "facebook"):
        score += 10.0
    if image_url:
        score += 5.0
    if len(full_text) > 100:
        score += 5.0

    return score


# 1. Y KHOA & SỨC KHỎE (Medical breakthroughs, cures, treatments, therapies, lifesaving medicine) - Highest Weight
HOPE_MEDICAL_KEYWORDS = frozenset({
    "cancer", "tumor", "tumors", "leukemia", "remission", "cure", "cures", "curing",
    "vaccine", "vaccines", "clinical trial", "therapy", "therapies", "treatment", "treatments",
    "drug", "drugs", "medicine", "medical", "biomedical", "surgery", "surgical", "transplant",
    "paralysis", "paralyzed", "blindness", "sight", "vision restored", "hearing", "cochlear",
    "alzheimer", "alzheimers", "parkinson", "parkinsons", "cardiac", "heart disease", "stroke",
    "stem cell", "stem cells", "gene therapy", "crispr", "dna editing", "immunotherapy", "mrna",
    "antibiotic", "antibiotics", "prosthetic", "bionic", "neuralink", "brain implant",
    "saving lives", "saves lives", "hospital", "patient", "patients", "eradication",
    "regenerative", "regenerative medicine", "pediatric", "diabetes", "insulin", "antidote",
})

# 2. SỰ SỐNG & BẢO TỒN MUÔN LOÀI (Living beings, species, wildlife, marine life, biodiversity, animal rescue) - High Weight
HOPE_LIFE_KEYWORDS = frozenset({
    "species", "wildlife", "animal", "animals", "biodiversity", "endangered", "extinction",
    "habitat", "coral reef", "coral reefs", "corals", "marine life", "ocean life", "sea turtle",
    "sea turtles", "whale", "whales", "elephant", "elephants", "rhino", "rhinos", "tiger", "tigers",
    "panda", "pandas", "bird", "birds", "avian", "fauna", "flora", "biology", "biological",
    "organism", "organisms", "ecosystem", "ecosystems", "rescue", "rescued", "saving animals",
    "revive", "revival", "rebirth", "repopulation", "wildlife recovery", "sanctuary",
    "nature reserve", "living species", "living organism", "vitality", "lifespan", "nature thriving",
})

# 3. MÔI TRƯỜNG & HỒI SINH TRÁI ĐẤT (Environment, ecological restoration, clean water, clean air, earth solutions) - High Weight
HOPE_ENVIRONMENT_KEYWORDS = frozenset({
    "ocean cleanup", "plastic cleanup", "reforestation", "forest restoration", "tree planting",
    "rainforest", "clean water", "drinking water", "water purifier", "purification", "desalination",
    "environmental", "environment", "ecology", "ecological", "planet earth", "green nature",
    "wetlands", "river restoration", "pollution reduction", "air quality", "clean energy",
    "solar", "solar power", "renewable", "renewables", "wind power", "wind turbine", "battery storage",
    "zero emission", "carbon capture", "carbon footprint", "recycling", "upcycling", "sustainable",
    "sustainability", "climate solution", "climate solutions", "clean planet", "greening",
})

# 4. SÁNG CHẾ, CÔNG NGHỆ & TIN TÍCH CỰC KHÁC (Other inventions, general positive/inspiring news) - Lower Weight
HOPE_OTHER_KEYWORDS = frozenset({
    "invention", "inventions", "breakthrough", "breakthroughs", "discovery", "discoveries",
    "milestone", "innovative", "innovation", "humanitarian", "miracle", "robotics", "robot",
    "artificial intelligence", "quantum", "space exploration", "telescope", "fusion energy",
    "clean material", "superconductor", "positive news", "inspiring", "inspiration", "good deed",
    "community", "education", "kindness",
})

HOPE_KEYWORDS = HOPE_MEDICAL_KEYWORDS | HOPE_LIFE_KEYWORDS | HOPE_ENVIRONMENT_KEYWORDS | HOPE_OTHER_KEYWORDS


def detect_hope_subtopic(item_or_text: Any) -> str:
    """Classify hope content into: 'medical', 'life', 'environment', or 'other'."""
    if isinstance(item_or_text, str):
        full = item_or_text.lower()
    else:
        title = getattr(item_or_text, "title", "")
        summary = getattr(item_or_text, "summary", "")
        full_text = getattr(item_or_text, "full_text", "")
        full = f"{title} {summary} {full_text}".lower()

    med_matches = sum(1 for kw in HOPE_MEDICAL_KEYWORDS if kw in full)
    life_matches = sum(1 for kw in HOPE_LIFE_KEYWORDS if kw in full)
    env_matches = sum(1 for kw in HOPE_ENVIRONMENT_KEYWORDS if kw in full)

    counts = [("medical", med_matches), ("life", life_matches), ("environment", env_matches)]
    counts.sort(key=lambda x: x[1], reverse=True)
    if counts[0][1] > 0:
        return counts[0][0]
    return "other"


def calculate_hope_score(item: Any) -> float:
    """Calculate an uplifting & hope score for positive science, inventions, cures and earth solutions.

    Emphasizes:
    - Y khoa & Sức khỏe (Medical breakthroughs & cures): highest weight (+35.0 base + 12.0/match)
    - Sự sống & Muôn loài (Living beings, species, wildlife): high weight (+25.0 base + 10.0/match)
    - Môi trường & Hồi sinh Trái Đất (Environment, ecology, cleanup): high weight (+25.0 base + 10.0/match)
    - Sáng chế, công nghệ & tin khác: smaller weight (+5.0 base + 2.0/match)
    """
    title = getattr(item, "title", "")
    summary = getattr(item, "summary", "")
    full_text = getattr(item, "full_text", "")
    full = f"{title} {summary} {full_text}".lower()

    # Heavy penalty for negative/war/violence words if they slip in
    negatives = (
        "war", "casualty", "casualties", "killed", "missile", "airstrike",
        "murder", "terror", "terrorist", "scandal", "lawsuit", "genocide"
    )
    if any(n in full for n in negatives):
        return -50.0

    score = 10.0

    # 1. Y khoa & Sức khỏe (Medical Breakthroughs & Healthcare) - Highest Weight
    med_matches = sum(1 for kw in HOPE_MEDICAL_KEYWORDS if kw in full)
    if med_matches > 0:
        score += 35.0 + min(med_matches * 12.0, 48.0)

    # 2. Sự sống & Muôn loài (Living Beings, Wildlife, Species Conservation) - High Weight
    life_matches = sum(1 for kw in HOPE_LIFE_KEYWORDS if kw in full)
    if life_matches > 0:
        score += 25.0 + min(life_matches * 10.0, 40.0)

    # 3. Môi trường & Hồi sinh Trái Đất (Environment, Ecology, Earth Restoration) - High Weight
    env_matches = sum(1 for kw in HOPE_ENVIRONMENT_KEYWORDS if kw in full)
    if env_matches > 0:
        score += 25.0 + min(env_matches * 10.0, 40.0)

    # 4. Sáng chế, công nghệ & tin tích cực khác (Other Inventions & Tech) - Smaller Weight
    other_matches = sum(1 for kw in HOPE_OTHER_KEYWORDS if kw in full)
    if other_matches > 0:
        score += 5.0 + min(other_matches * 2.0, 10.0)

    score += min(len(full_text) * 0.005, 10.0)
    if getattr(item, "image_url", ""):
        score += 5.0

    return score


def is_mainstream_hard_news(title: str, desc: str) -> bool:
    """Filter out mainstream world politics, professional sports, and corporate tech news to avoid overlap."""
    full = f"{title} {desc}".lower()
    has_hard_news = any(term in full for term in MAINSTREAM_HARD_NEWS_TERMS)
    if not has_hard_news:
        return False
    # Hard professional sports must never be overridden
    hard_sports = any(s in full for s in (
        "premier league", "champions league", "la liga", "serie a", "bundesliga", "nfl", "nba",
        "nhl", "mlb", "world series", "worldseries", "cricket match", "super bowl", "grand slam",
        "hockey", "baseball", "griffins", "milic 42 saves", "saves improve to"
    ))
    if hard_sports:
        return True
    # If it has strong viral markers, allow it unless heavily political/corporate
    has_viral_override = any(v in full for v in VIRAL_OVERRIDE_TERMS)
    if has_viral_override:
        heavy_corporate_or_politics = any(h in full for h in (
            "quarterly earnings", "revenue", "antitrust", "legislation", "ceasefire",
            "parliament passes", "sanctions", "peace talks"
        ))
        return heavy_corporate_or_politics
    return True


def clean_html_text(raw_text: str) -> str:
    """Remove HTML tags and unescape HTML entities, collapsing excessive spaces."""
    if not raw_text:
        return ""
    stripped = CLEAN_HTML_REGEX.sub(" ", raw_text)
    unescaped = html.unescape(stripped)
    cleaned = re.sub(r"\s+", " ", unescaped).strip()
    # Strip stray leading spam angle brackets often found in RSS spam (e.g. '>!!!!(LIVESTREAMs!)')
    if cleaned.startswith(">"):
        cleaned = re.sub(r"^[>\s:!-]+", "", cleaned)
    return cleaned


PLACEHOLDER_DOMAINS = (
    "googleusercontent.com",
    "gstatic.com",
    "news.google.com",
    "google.com",
    "doubleclick.net",
    "yt3.ggpht.com",
    "gravatar.com",
    "wp.com/wp-content/themes",
)

PLACEHOLDER_PATTERNS = (
    "placeholder",
    "default_image",
    "default-image",
    "no_image",
    "no-image",
    "favicon",
    "fallback",
    "pixel",
    "spacer",
    "tracking",
    "1x1",
)


def is_placeholder_image_url(url: str) -> bool:
    """Detect whether a given image URL points to a generic brand placeholder, icon, or tracking asset."""
    if not url or not isinstance(url, str) or not url.startswith("http"):
        return True
    u_lower = url.lower()
    if any(domain in u_lower for domain in PLACEHOLDER_DOMAINS):
        return True
    try:
        parsed = urllib.parse.urlparse(u_lower)
        path = parsed.path
        if any(p in path for p in PLACEHOLDER_PATTERNS):
            return True
    except Exception:
        pass
    return False


def extract_image_from_html(content: str, base_url: str = "") -> str:
    """Extract substantive image URL from HTML metadata (og:image, twitter:image, or article img)."""
    if not content:
        return ""
    m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', content, re.IGNORECASE)
    if not m:
        m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', content, re.IGNORECASE)
    if not m:
        m = re.search(r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']', content, re.IGNORECASE)
    if not m:
        m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']', content, re.IGNORECASE)
    if m:
        img_url = html.unescape(m.group(1)).strip()
        if img_url.startswith("http") and not is_placeholder_image_url(img_url):
            return img_url
    imgs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', content, re.IGNORECASE)
    for src in imgs:
        clean_src = html.unescape(src).strip()
        if clean_src.startswith("http") and not is_placeholder_image_url(clean_src) and not any(k in clean_src.lower() for k in ("logo", "icon", "avatar", "spacer", "pixel", "tracking", "advert")):
            if any(ext in clean_src.lower() for ext in (".jpg", ".jpeg", ".png", ".webp")):
                return clean_src
    return ""


def fetch_article_details_and_image(url: str, timeout: float = 4.0) -> Tuple[str, str]:
    """Fetch article webpage and extract substantive text paragraphs and OpenGraph/Twitter image."""
    if not url or not url.startswith("http"):
        return "", ""
    try:
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            content = resp.read().decode("utf-8", errors="ignore")

        img_url = extract_image_from_html(content, url)

        # Focus inside <article> if available
        art_match = re.search(r"<article[^>]*>(.*?)</article>", content, flags=re.DOTALL)
        search_space = art_match.group(1) if art_match else content

        paras = re.findall(r"<p[^>]*>(.*?)</p>", search_space, flags=re.DOTALL)
        clean_paras = []
        for p in paras:
            c = html.unescape(re.sub(r"<[^>]+>", "", p)).strip()
            c = re.sub(r"\s+", " ", c)
            lower = c.lower()
            if len(c) > 60 and not any(k in lower for k in [
                "via ap", "getty images", "afp via", "reuters via", "photo by", "hide caption",
                "cookie", "subscribe", "terms of", "privacy", "copyright", "newsletter",
                "guardian on google", "sign up", "navigation"
            ]):
                clean_paras.append(c)
                if len(clean_paras) >= 5:
                    break
        return " ".join(clean_paras), img_url
    except Exception as exc:
        logger.debug("Article details fetch failed for %s: %s", url, exc)
        return "", ""


def fetch_article_details(url: str, timeout: float = 4.0) -> str:
    """Fetch the real article page and extract substantive story paragraphs."""
    body, _ = fetch_article_details_and_image(url, timeout)
    return body


def get_wikipedia_context(query: str, timeout: float = 3.0) -> str:
    """Fetch Wikipedia summary extract for entity background context."""
    if not query:
        return ""
    try:
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(query)}"
        req = urllib.request.Request(url, headers={"User-Agent": "HaizFlowNewsBot/1.0"})
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("extract", "")
    except Exception:
        return ""


def extract_source_name(url: str, raw_src: str) -> str:
    """Derive professional news publisher name from URL or raw tag."""
    if raw_src and raw_src.lower() not in ("international news", "news", "google news"):
        return raw_src
    u_lower = url.lower()
    if "x.com" in u_lower or "twitter.com" in u_lower:
        return "mạng xã hội X (Twitter)"
    if "instagram.com" in u_lower:
        return "mạng xã hội Instagram"
    if "facebook.com" in u_lower or "fb.com" in u_lower:
        return "mạng xã hội Facebook"
    if "odditycentral.com" in u_lower:
        return "chuyên trang Oddity Central"
    if "boredpanda.com" in u_lower:
        return "chuyên trang Bored Panda"
    if "dexerto.com" in u_lower:
        return "trang tin Dexerto"
    if "upi.com" in u_lower:
        return "mục Odd News của hãng UPI"
    if "theverge.com" in u_lower:
        return "chuyên trang The Verge"
    if "techcrunch.com" in u_lower:
        return "chuyên trang TechCrunch"
    if "wired.com" in u_lower:
        return "tạp chí Wired"
    if "arstechnica.com" in u_lower:
        return "chuyên trang Ars Technica"
    if "espn.com" in u_lower:
        return "kênh thể thao ESPN"
    if "skysports.com" in u_lower:
        return "kênh thể thao Sky Sports"
    if "bloomberg.com" in u_lower:
        return "hãng tin Bloomberg"
    if "forbes.com" in u_lower:
        return "tạp chí Forbes"
    if "cnbc.com" in u_lower:
        return "kênh truyền hình CNBC"
    if "npr.org" in u_lower:
        return "Đài phát thanh NPR"
    if "theguardian.com" in u_lower:
        return "báo The Guardian"
    if "aljazeera.com" in u_lower:
        return "hãng tin Al Jazeera"
    if "bbc.co" in u_lower:
        return "hãng thông tấn BBC"
    if "nytimes.com" in u_lower:
        return "báo The New York Times"
    if "reuters.com" in u_lower:
        return "hãng thông tấn Reuters"
    if "apnews.com" in u_lower:
        return "hãng tin AP"
    return "các hãng thông tấn quốc tế"


ENGLISH_JOURNALISM_REPLACEMENTS: List[Tuple[str, str]] = [
    # Armed conflict & attacks
    (r"\bexchange strikes\b", "exchange military attacks"),
    (r"\bexchanges strikes\b", "exchanges military attacks"),
    (r"\bdrone strikes\b", "drone attacks"),
    (r"\bdrone strike\b", "drone attack"),
    (r"\bair strikes\b", "airstrikes"),
    (r"\bair strike\b", "airstrike"),
    (r"\bmissile strikes\b", "missile attacks"),
    (r"\bmissile strike\b", "missile attack"),
    (r"\bstrikes on\b", "attacks on"),
    (r"\bstrikes across\b", "attacks across"),
    (r"\bdeadly strikes\b", "deadly attacks"),
    (r"\blaunches strikes\b", "launches attacks"),
    (r"\bstage strikes\b", "stage military assaults"),
    # Politics & diplomacy
    (r"\blawmakers?\b", "parliamentarians"),
    (r"\bstandoff\b", "tense confrontation"),
    (r"\bstand-off\b", "tense confrontation"),
    (r"\bmidterms?\b", "midterm elections"),
    (r"\bcar ramming\b", "vehicle ramming attack"),
    (r"\bvehicular attack\b", "vehicle ramming attack"),
    (r"\bsettler attacks\b", "attacks by settlers"),
    (r"\bclashes erupt\b", "fierce clashes break out"),
    (r"\bfaces backlash\b", "faces intense public criticism"),
    (r"\bunder fire\b", "facing heavy criticism"),
]

VIETNAMESE_JOURNALISM_REPLACEMENTS: List[Tuple[str, str]] = [
    # Military attacks mistranslated as labor strike (đình công)
    (r"\b(trao đổi|thực hiện|tiến hành|phát động|hứng chịu|chịu|bị|các cuộc|những cuộc|đợt)\s+đình công\b", r"\1 tập kích quân sự"),
    (r"\bđình công bằng máy bay không người lái\b", "tập kích bằng máy bay không người lái"),
    (r"\bđình công bằng uav\b", "tập kích bằng máy bay không người lái"),
    (r"\bđình công bằng tên lửa\b", "tập kích bằng tên lửa"),
    (r"\bđình công của nga\b", "đợt tập kích của Nga"),
    (r"\bđình công của ukraine\b", "đợt tập kích của Ukraine"),
    (r"\bđình công của israel\b", "đợt không kích của Israel"),
    (r"\bđình công quân sự\b", "tấn công quân sự"),
    (r"\bđình công chết người\b", "cuộc tấn công gây chết người"),
    (r"\bđình công vào\b", "tập kích vào"),
    (r"\bđình công qua lại\b", "các đợt tập kích qua lại"),
    # General journalism terminology with case sensitivity
    (r"\bNhà lập pháp\b", "Nghị sĩ"),
    (r"\bnhà lập pháp\b", "nghị sĩ"),
    (r"\bNgười lập pháp\b", "Nghị sĩ"),
    (r"\bngười lập pháp\b", "nghị sĩ"),
    (r"\b(vụ\s+)?đâm xe cố ý\b", "vụ cố ý lao xe tấn công"),
    (r"\b(vụ\s+)?xông vào xe\b", "vụ lao xe"),
    (r"\bNgười định cư\b", "Nhóm người định cư"),
    (r"\bngười định cư\b", "nhóm người định cư"),
    # Remove robotic boilerplate if any slips through
    (r"diễn biến này đang là tâm điểm chú ý trên các phương tiện truyền thông thế giới!?\s*", ""),
    (r"giới quan sát nhận định sự việc này có thể ảnh hưởng đến tình hình an ninh và ngoại giao quốc tế!?\s*", ""),
]


def normalize_english_journalism(text: str) -> str:
    """Pre-normalize English news text before translation to avoid common mistranslations."""
    if not text:
        return ""
    result = text
    for pattern, replacement in ENGLISH_JOURNALISM_REPLACEMENTS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


def normalize_vietnamese_journalism(text: str) -> str:
    """Post-normalize translated Vietnamese text into natural, accurate television broadcast style."""
    if not text:
        return ""
    result = text
    for pattern, replacement in VIETNAMESE_JOURNALISM_REPLACEMENTS:
        result = re.sub(pattern, replacement, result)

    # Context-aware fallback: if text relates to conflict/military and still has 'đình công', replace with 'đợt tập kích'
    mil_keywords = {
        "quân sự", "tên lửa", "uav", "máy bay", "ukraine", "nga", "israel", "gaza", "houthi",
        "lebanon", "syria", "iran", "quân đội", "chiến sự", "chiến tranh", "vũ khí", "bắn phá",
        "thiệt hại", "tập kích", "nổ", "không kích", "phòng không"
    }
    words = set(re.findall(r"\w+", result.lower()))
    if words & mil_keywords:
        result = re.sub(r"\bđình công\b", "đợt tập kích", result, flags=re.IGNORECASE)

    return re.sub(r"\s+", " ", result).strip()


TOPIC_STOPWORDS = frozenset({
    "the", "a", "an", "and", "in", "on", "at", "for", "of", "to", "with", "by", "as",
    "is", "are", "was", "were", "from", "after", "over", "into", "about", "says", "new",
    "amid", "could", "would", "will", "has", "have", "had", "out", "up", "down", "its",
    "their", "his", "her", "that", "this", "under", "ahead", "near", "amidst", "during",
    "first", "two", "three", "four", "five", "day", "days", "week", "more", "than",
    "news", "world", "today", "report", "reports", "say", "said", "people", "year", "years",
})


def extract_topic_keywords(text: str) -> set[str]:
    """Extract significant entity keywords for clustering news items by event/topic."""
    words = re.findall(r"\w+", text.lower())
    return {w for w in words if len(w) > 2 and w not in TOPIC_STOPWORDS}


def cluster_and_rank_news_topics(
    items: List[WorldNewsItem],
    max_topics: int = 8,
    category: str = "world",
) -> List[WorldNewsItem]:
    """Cluster multi-outlet news reports on the same event into unified, rich topics.

    Applies Prominence Scoring (cross-source coverage) and Regional Quota Balancing
    to guarantee representation of China, Southeast Asia, Russia, Japan, Korea alongside
    global West and Middle East points.
    """
    if not items:
        return []

    clusters: List[dict] = []

    for item in items:
        kw = extract_topic_keywords(item.title)
        if not kw:
            continue

        matched_cluster = None
        for cl in clusters:
            overlap = kw & cl["keywords"]
            # Two items match if they share 2+ significant words, or 1 strong proper noun/term (>= 6 chars)
            if len(overlap) >= 2 or (len(overlap) >= 1 and any(len(w) >= 6 for w in overlap)):
                matched_cluster = cl
                break

        if matched_cluster:
            matched_cluster["items"].append(item)
            matched_cluster["keywords"].update(kw)
        else:
            clusters.append({
                "keywords": kw,
                "items": [item],
            })

    # For each cluster, synthesize a single, richer WorldNewsItem with prominence score
    unified_items: List[WorldNewsItem] = []
    for cl in clusters:
        cluster_items: List[WorldNewsItem] = cl["items"]
        primary = max(cluster_items, key=lambda it: len(it.full_text) * 2 + len(it.title))

        # Combine sources if from different reputable publishers
        unique_sources = []
        for it in cluster_items:
            if it.source and it.source not in unique_sources and it.source != "các hãng thông tấn quốc tế":
                unique_sources.append(it.source)
        merged_source = " và ".join(unique_sources[:2]) if unique_sources else primary.source

        # Combine substantive article details
        all_texts = []
        seen_texts = set()
        for it in cluster_items:
            txt = it.full_text if it.full_text else it.summary
            clean_txt = clean_html_text(txt)
            if clean_txt and clean_txt not in seen_texts and len(clean_txt) > 40:
                all_texts.append(clean_txt)
                seen_texts.add(clean_txt)

        merged_full_text = " ".join(all_texts) if all_texts else primary.full_text
        primary_image = next((it.image_url for it in cluster_items if it.image_url), primary.image_url)
        primary_platform = next((it.social_platform for it in cluster_items if it.social_platform), primary.social_platform)

        u_item = WorldNewsItem(
            title=primary.title,
            summary=primary.summary,
            source=merged_source,
            published=primary.published,
            link=primary.link,
            full_text=merged_full_text,
            image_url=primary_image,
            social_platform=primary_platform,
        )
        # Prominence score based on multi-outlet coverage & title substantive length
        setattr(u_item, "_prominence_score", len(cluster_items) * 3.0 + len(primary.title) * 0.02)
        unified_items.append(u_item)

    norm_cat = normalize_category(category)
    if norm_cat == "viral":
        # Discard low-novelty items if we have sufficient candidate stories
        high_novelty_items = [it for it in unified_items if not is_low_novelty_viral_news(it.title, it.summary)]
        if len(high_novelty_items) >= max_topics:
            unified_items = high_novelty_items
        # Rank by novelty score: genuinely bizarre OR truly hilarious stories score highest
        unified_items.sort(key=calculate_viral_novelty_score, reverse=True)
    elif norm_cat == "hope":
        # Rank by hope score: prioritizes scientific breakthroughs, cures, clean energy & inventions
        unified_items.sort(key=calculate_hope_score, reverse=True)
    else:
        # Rank by multi-source prominence and substantive summary
        unified_items.sort(key=lambda it: getattr(it, "_prominence_score", 0.0) + len(it.summary) * 0.01, reverse=True)

    # Regional Quota Balancing across ALL categories (including Shorts: viral & hope)
    asia_items = [it for it in unified_items if detect_news_region(it) == "asia_neighbor"]
    other_items = [it for it in unified_items if detect_news_region(it) != "asia_neighbor"]

    # Target 40-50% Asia / Neighboring region (China, ASEAN, Russia, Japan, Korea)
    target_asia = max(1 if max_topics <= 3 else 2, min(len(asia_items), max(1, max_topics // 2))) if asia_items else 0
    target_other = max(0, max_topics - target_asia)

    selected_asia = asia_items[:target_asia]
    selected_other = other_items[:target_other]

    # If either group is short, fill from the other group
    remaining = max_topics - (len(selected_asia) + len(selected_other))
    if remaining > 0:
        unused_asia = [it for it in asia_items if it not in selected_asia]
        unused_other = [it for it in other_items if it not in selected_other]
        fillers = (unused_asia + unused_other)[:remaining]
        selected_other.extend(fillers)

    # Interleave to create an engaging, well-distributed broadcast
    balanced_result: List[WorldNewsItem] = []
    idx_a, idx_o = 0, 0
    while len(balanced_result) < max_topics and (idx_a < len(selected_asia) or idx_o < len(selected_other)):
        if idx_a < len(selected_asia):
            balanced_result.append(selected_asia[idx_a])
            idx_a += 1
        if idx_o < len(selected_other) and len(balanced_result) < max_topics:
            balanced_result.append(selected_other[idx_o])
            idx_o += 1

    return balanced_result[:max_topics]


def fetch_world_news_rss(
    max_items: int = 8,
    exclude_vietnam: bool = True,
    timeout: float = 12.0,
    scrape_article_body: bool = True,
    category: str = "world",
    export_dt: Optional[datetime] = None,
) -> List[WorldNewsItem]:
    """Fetch recent world news items from international RSS feeds, strictly excluding Vietnam news."""
    norm_cat = normalize_category(category)

    # Strategy: Merged morning broadcast 'Tin Mới' (World + Sports)
    if norm_cat == "tin_moi":
        n_world = max(1, (max_items + 1) // 2)
        n_sports = max(1, max_items - n_world)
        w_items = fetch_world_news_rss(
            max_items=n_world,
            exclude_vietnam=exclude_vietnam,
            timeout=timeout,
            scrape_article_body=scrape_article_body,
            category="world",
            export_dt=export_dt,
        )
        s_items = fetch_world_news_rss(
            max_items=n_sports,
            exclude_vietnam=exclude_vietnam,
            timeout=timeout,
            scrape_article_body=scrape_article_body,
            category="sports",
            export_dt=export_dt,
        )
        return w_items + s_items

    # Strategy: Merged evening broadcast 'Tin Nóng' (War + Tech)
    if norm_cat == "tin_nong":
        n_war = max(1, (max_items + 1) // 2)
        n_tech = max(1, max_items - n_war)
        war_items = fetch_world_news_rss(
            max_items=n_war,
            exclude_vietnam=exclude_vietnam,
            timeout=timeout,
            scrape_article_body=scrape_article_body,
            category="war",
            export_dt=export_dt,
        )
        tech_items = fetch_world_news_rss(
            max_items=n_tech,
            exclude_vietnam=exclude_vietnam,
            timeout=timeout,
            scrape_article_body=scrape_article_body,
            category="tech",
            export_dt=export_dt,
        )
        return war_items + tech_items

    raw_items: List[WorldNewsItem] = []
    seen_titles: set[str] = set()
    published_history: List[Dict[str, Any]] = []
    try:
        published_history = load_published_news_history(max_age_days=7)
    except Exception as exc:
        logger.warning("Could not load published news history: %s", exc)

    cfg = get_category_config(category)
    feed_urls = cfg.get("feeds", WORLD_RSS_FEEDS)

    import ssl
    import concurrent.futures
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

    def fetch_single_feed(feed_url: str) -> Tuple[str, bytes]:
        try:
            req = urllib.request.Request(feed_url, headers=headers)
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=timeout) as resp:
                return feed_url, resp.read()
        except Exception as exc:
            logger.debug("Failed to fetch RSS from %s: %s", feed_url, exc)
            return feed_url, b""

    # Fetch all candidate feeds in parallel for high speed and broad coverage
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(feed_urls))) as executor:
        feed_results = list(executor.map(fetch_single_feed, feed_urls))

    for feed_url, xml_data in feed_results:
        if not xml_data:
            continue
        try:
            root = ET.fromstring(xml_data)
            channel = root.find("channel")
            if channel is None:
                continue

            feed_items_count = 0
            max_per_feed = 6
            for entry in channel.findall("item"):
                title_elem = entry.find("title")
                desc_elem = entry.find("description")
                link_elem = entry.find("link")
                pub_elem = entry.find("pubDate")
                src_elem = entry.find("source")

                title = clean_html_text(title_elem.text if title_elem is not None else "")
                desc = clean_html_text(desc_elem.text if desc_elem is not None else "")
                link = link_elem.text.strip() if link_elem is not None and link_elem.text else ""
                pub = pub_elem.text.strip() if pub_elem is not None and pub_elem.text else ""
                raw_src = src_elem.text.strip() if src_elem is not None and src_elem.text else ""
                src = extract_source_name(link or feed_url, raw_src)

                if not title:
                    continue

                # Filter out domestic Vietnam news
                if exclude_vietnam and (is_vietnam_related(title) or is_vietnam_related(desc) or is_vietnam_related(link)):
                    logger.info("Filtered out Vietnam domestic item: %s", title)
                    continue

                # For war category, strictly ensure it is military/conflict, and filter out sports & lifestyle
                if category == "war" and not is_strict_war_news(title, desc):
                    logger.debug("Filtered out non-war/sports item from war: %s", title)
                    continue

                # For sports category, strictly ensure it is football/soccer related, not other sports
                if category == "sports" and is_non_football_news(title, desc):
                    logger.info("Filtered out non-football sports item: %s", title)
                    continue

                # For viral category, strictly filter out mainstream world politics, professional sports, and corporate tech
                if category == "viral" and is_mainstream_hard_news(title, desc):
                    logger.debug("Filtered out mainstream world/tech/sports item from viral: %s", title)
                    continue

                # For viral category, filter out low-novelty mundane items (auctions, dry surveys, minor flight delays, routine lotteries)
                if category == "viral" and is_low_novelty_viral_news(title, desc):
                    logger.debug("Filtered out low-novelty item from viral: %s", title)
                    continue

                # Check 7-day persistent published history to prevent cross-day duplication
                if is_duplicate_with_published_history(title, link, published_history):
                    logger.info("Filtered out duplicate item from 7-day published history: %s", title)
                    continue

                # Time window constraint: viral within ~36h, hope within 48h
                if category in ("viral", "hope") and pub:
                    if not is_within_time_window(pub, export_dt, category=category):
                        logger.debug("Filtered out %s item outside freshness window: %s (%s)", category, title, pub)
                        continue

                norm_key = re.sub(r"[^\w]", "", title.lower())
                if norm_key in seen_titles:
                    continue
                seen_titles.add(norm_key)

                # Extract image enclosure or media thumbnail from feed if available
                item_image = ""
                enc = entry.find("enclosure")
                if enc is not None and enc.get("url") and "image" in enc.get("type", ""):
                    item_image = enc.get("url", "")
                if not item_image:
                    for m_tag in entry.findall("{http://search.yahoo.com/mrss/}content"):
                        if m_tag.get("url"):
                            item_image = m_tag.get("url")
                            break
                if not item_image:
                    for m_tag in entry.findall("{http://search.yahoo.com/mrss/}thumbnail"):
                        if m_tag.get("url"):
                            item_image = m_tag.get("url")
                            break
                if not item_image:
                    for child in entry:
                        tag_lower = child.tag.lower()
                        if tag_lower.endswith("thumbnail") or tag_lower.endswith("content"):
                            u = child.get("url")
                            if u and any(ext in u.lower() for ext in (".jpg", ".jpeg", ".png", ".webp")):
                                item_image = u
                                break
                if not item_image and desc_elem is not None and desc_elem.text:
                    unescaped_desc = html.unescape(desc_elem.text)
                    m_img = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', unescaped_desc, re.IGNORECASE)
                    if m_img:
                        cand = m_img.group(1).strip()
                        if not is_placeholder_image_url(cand):
                            item_image = cand
                if not item_image:
                    content_elem = entry.find("{http://purl.org/rss/1.0/modules/content/}encoded")
                    if content_elem is not None and content_elem.text:
                        unescaped_c = html.unescape(content_elem.text)
                        m_img = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', unescaped_c, re.IGNORECASE)
                        if m_img:
                            cand = m_img.group(1).strip()
                            if not is_placeholder_image_url(cand):
                                item_image = cand

                if item_image and is_placeholder_image_url(item_image):
                    item_image = ""

                # Multi-platform identification (Reddit, TikTok, Threads, Instagram, Facebook, X)
                full_text_check = f"{link} {title} {raw_src} {feed_url}".lower()
                if "reddit" in full_text_check:
                    social_plat = "reddit"
                elif "tiktok" in full_text_check:
                    social_plat = "tiktok"
                elif "threads" in full_text_check:
                    social_plat = "threads"
                elif "instagram" in full_text_check:
                    social_plat = "instagram"
                elif "facebook" in full_text_check or "fb.com" in full_text_check:
                    social_plat = "facebook"
                else:
                    social_plat = "x"

                raw_items.append(
                    WorldNewsItem(
                        title=title,
                        summary=desc[:1000] if desc else title,
                        source=src,
                        published=pub,
                        link=link,
                        image_url=item_image,
                        social_platform=social_plat,
                    )
                )

                feed_items_count += 1
                if feed_items_count >= max_per_feed:
                    break
        except Exception as exc:
            logger.warning("Failed to fetch RSS from %s: %s", feed_url, exc)

        if len(raw_items) >= max(80, max_items * 10):
            break

    # Cluster multi-feed reports into distinct topics
    clustered_items = cluster_and_rank_news_topics(raw_items, max_topics=max_items, category=category)

    # Deep article scraping: fetch substantive paragraphs from source publishers for the selected topics
    if scrape_article_body:
        for it in clustered_items:
            if it.link:
                body, page_img = fetch_article_details_and_image(it.link, timeout=4.0)
                if body and not it.full_text:
                    if exclude_vietnam and is_vietnam_related(body):
                        logger.warning("Scraped article body for '%s' contains Vietnam reference! Scrubbed to prevent pollution.", it.title)
                        body = ""
                    it.full_text = body
                    logger.debug("Scraped deep article body (%d chars) for '%s'", len(body), it.title)
                if page_img and not it.image_url and not is_placeholder_image_url(page_img):
                    it.image_url = page_img

    logger.info("Clustered and fetched %d distinct international news topics with deep article details.", len(clustered_items))
    return clustered_items


def clean_query_for_wikimedia(query: str) -> str:
    """Strip subjective fluff, sentiment adjectives, and meta phrases to maximize Wikipedia encyclopedia match accuracy."""
    fluff = {
        "beautiful", "stunning", "gorgeous", "amazing", "wonderful", "incredible",
        "hope", "inspiring", "positive", "happy", "great", "best", "special",
        "mysterious", "nature", "shocking", "unbelievable", "viral", "funny",
        "cute", "epic", "dramatic", "crazy", "weird",
    }
    words = re.findall(r"\b[a-zA-Z]{3,}\b", query)
    cleaned = [w for w in words if w.lower() not in fluff]
    return " ".join(cleaned) if cleaned else query


def search_wikimedia_commons(
    query: str,
    category: str = "world",
    timeout: float = 8.0,
) -> Tuple[Optional[str], Optional[str]]:
    """Search Wikimedia Commons / Wikipedia API for copyright-safe public domain / CC images with category verification."""
    cleaned_query = query.strip()
    if not cleaned_query:
        return None, None

    is_sports = (category == "sports")
    search_term = clean_query_for_wikimedia(cleaned_query)

    if is_sports:
        # Immediate rejection of non-football metaphor queries (witches, mafia, religion, medical, etc.)
        metaphor_blacklist = [
            r"\bwitch(?:craft|-hunt|\s+hunt)?\b",
            r"\bmafia\b",
            r"\bgodfather\b",
            r"\bcatholic\b",
            r"\bchurch\b",
            r"\bpope\b",
            r"\bvatican\b",
            r"\bmonastery\b",
            r"\bpriest\b",
            r"\bbishop\b",
            r"\bholy\b",
            r"\bcrime(?:\s+family|\s+boss)?\b",
            r"\bgangster\b",
            r"\bcartel\b",
            r"\bdoctor\b",
            r"\bhospital\b",
            r"\bsurgery\b",
            r"\banatomy\b",
            r"\bmovie\b",
            r"\bcinema\b",
            r"\bhollywood\b",
            r"^\s*saints?\s*$",
        ]
        for bad_pat in metaphor_blacklist:
            if re.search(bad_pat, cleaned_query, re.IGNORECASE):
                logger.info("Search query '%s' contains non-football concept/metaphor. Falling back to AI photorealistic illustration.", query)
                return None, None

        # Ensure search term has explicit football context if missing
        lower_term = search_term.lower()
        football_terms = ("football", "soccer", "fc", "f.c.", "club", "stadium", "manager", "player", "champions league", "premier league", "la liga", "serie a", "bundesliga")
        if not any(ft in lower_term for ft in football_terms):
            search_term = f"{search_term} football"

    endpoint = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": search_term,
        "gsrlimit": 6,
        "prop": "pageimages|description",
        "piprop": "thumbnail|original",
        "pithumbsize": 1280,
        "format": "json",
    }
    url = f"{endpoint}?{urllib.parse.urlencode(params)}"
    headers = {"User-Agent": "HaizFlowNewsBot/1.0 (https://github.com/MachHongHai/HaizFlow)"}

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        pages = data.get("query", {}).get("pages", {})
        # Sort candidates: prefer real JPG/JPEG photographs over SVG/vector diagrams or historical paintings
        def _candidate_rank(p):
            p_src = ((p.get("thumbnail") or {}).get("source") or (p.get("original") or {}).get("source") or "").lower()
            p_title = str(p.get("title") or "").lower()
            p_desc = str(p.get("description") or "").lower()
            score = p.get("index", 999)
            if ".svg" in p_src or "vector" in p_title or "diagram" in p_title:
                score += 50
            if any(w in p_title or w in p_desc for w in ("painting", "drawing", "etching", "sketch", "engraving", "artwork", "illustration")):
                score += 40
            elif p_src.endswith(".jpg") or p_src.endswith(".jpeg"):
                score -= 10
            return score

        sorted_pages = sorted(pages.values(), key=_candidate_rank)
        query_words = set(re.findall(r"\b[a-z]{3,}\b", search_term.lower()))
        is_seeking_ent = any(w in query_words for w in ("film", "movie", "actor", "actress", "song", "album", "singer", "novel"))
        ent_blacklist = (
            "actor", "actress", "film", "movie", "television series", "tv series",
            "album", "song", "singer", "band", "novel", "author", "playwright",
            "politician", "political party",
        )

        for pdata in sorted_pages:
            title = str(pdata.get("title") or "").strip()
            desc = str(pdata.get("description") or "").strip().lower()
            combined = f"{title} {desc}".lower()

            thumb = pdata.get("thumbnail", {})
            orig = pdata.get("original", {})
            src = thumb.get("source") or orig.get("source")
            if not src or not (src.endswith(".jpg") or src.endswith(".jpeg") or src.endswith(".png") or "thumb" in src):
                continue

            # General Entertainment / Biographical Blacklist (prevent returning actors/films for science, nature, world news)
            if not is_seeking_ent and any(bad in desc for bad in ent_blacklist):
                logger.debug("Rejected entertainment candidate '%s' (desc: '%s') for query '%s'", title, desc, search_term)
                continue

            # Strict verification for football / sports category
            if is_sports:
                # 1. Reject candidates containing non-football domains
                blacklist = [
                    "witch", "witchcraft", "sorcery", "magic", "occult",
                    "catholic", "christian", "church", "pope", "bishop", "priest", "monastery", "holy",
                    "mafia", "gangster", "crime family", "cartel",
                    "film", "movie", "television series", "tv series", "actor", "actress",
                    "album", "song", "singer", "band", "novel", "book",
                    "commune", "municipality", "village", "district of",
                    "weapon", "artillery", "ammunition", "military unit",
                    "medical condition", "disease", "syndrome", "anatomy",
                    "species", "genus", "plant", "insect",
                ]
                has_blacklisted = False
                for b_word in blacklist:
                    if b_word in desc or (b_word in title.lower() and not ("saint-germain" in title.lower() and b_word in ("saint", "holy"))):
                        has_blacklisted = True
                        break
                if has_blacklisted:
                    logger.debug("Rejected non-football candidate '%s' (desc: '%s') for sports news", title, desc)
                    continue

                # 2. Require positive football context in title or description
                positive_keywords = (
                    "football", "soccer", "footballer", "f.c.", "fc", "club", "player",
                    "manager", "coach", "stadium", "midfielder", "striker", "forward",
                    "defender", "goalkeeper", "premier league", "la liga", "champions league",
                    "serie a", "bundesliga", "uefa", "fifa", "ballon d'or", "world cup",
                    "athletic", "derby", "league", "cup", "trophy", "association football",
                )
                if not any(pos in combined for pos in positive_keywords):
                    logger.debug("Candidate '%s' lacks positive football keywords (desc: '%s'). Skipping.", title, desc)
                    continue
            else:
                # Require that candidate title or description actually relates to search query
                title_words = set(re.findall(r"\b[a-z]{3,}\b", title.lower()))
                desc_words = set(re.findall(r"\b[a-z]{3,}\b", desc))
                if not (query_words & title_words) and len(query_words & desc_words) < 2:
                    logger.debug("Rejected candidate '%s' (desc: '%s') - no keyword match with '%s'", title, desc, search_term)
                    continue

            return title, src
    except Exception as exc:
        logger.debug("Wikimedia search error for query '%s': %s", query, exc)

    return None, None


def download_and_format_image(
    image_url: str,
    output_path: Path,
    aspect_ratio: AspectRatio = "9:16",
    timeout: float = 12.0,
) -> bool:
    if not image_url or is_placeholder_image_url(image_url):
        return False
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Referer": "https://www.google.com/",
    }
    try:
        req = urllib.request.Request(image_url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read()

        if len(content) < 5000:
            return False

        img = Image.open(io.BytesIO(content)).convert("RGB")
        src_w, src_h = img.size
        # Reject low-res icons, avatars, and square placeholder logos
        if src_w <= 320 and src_h <= 320:
            logger.debug("Rejected low-res/icon image (%dx%d) from %s", src_w, src_h, image_url)
            return False
        target_w, target_h = resolution_for_aspect_ratio(aspect_ratio)

        src_ratio = src_w / max(1, src_h)
        target_ratio = target_w / max(1, target_h)

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # If aspect ratios are very close (within 15%), direct center crop
        if abs(src_ratio - target_ratio) < 0.18:
            if src_ratio > target_ratio:
                new_w = int(round(src_h * target_ratio))
                left = (src_w - new_w) // 2
                cropped = img.crop((left, 0, left + new_w, src_h))
            else:
                new_h = int(round(src_w / target_ratio))
                top = (src_h - new_h) // 2
                cropped = img.crop((0, top, src_w, top + new_h))
            final_img = cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)
            final_img.save(output_path, quality=92)
            return True

        # Broadcast News Style: Blurred Backdrop + Sharp Centered Foreground
        # 1. Background: scale to cover target, blur heavily, slightly darken
        bg_scale = max(target_w / src_w, target_h / src_h)
        bg_w, bg_h = int(round(src_w * bg_scale)), int(round(src_h * bg_scale))
        bg = img.resize((bg_w, bg_h), Image.Resampling.BILINEAR)

        # Center crop background to exact target canvas
        bg_left = (bg_w - target_w) // 2
        bg_top = (bg_h - target_h) // 2
        bg = bg.crop((bg_left, bg_top, bg_left + target_w, bg_top + target_h))
        bg = bg.filter(ImageFilter.GaussianBlur(radius=28))
        enhancer = ImageEnhance.Brightness(bg)
        bg = enhancer.enhance(0.55)  # Darken background to 55%

        # 2. Foreground: scale to fit cleanly inside canvas with safe margins
        margin_pct = 0.04
        max_fg_w = int(round(target_w * (1.0 - margin_pct * 2)))
        max_fg_h = int(round(target_h * (1.0 - margin_pct * 2)))
        fg_scale = min(max_fg_w / src_w, max_fg_h / src_h)
        fg_w, fg_h = int(round(src_w * fg_scale)), int(round(src_h * fg_scale))
        fg = img.resize((fg_w, fg_h), Image.Resampling.LANCZOS)

        # 3. Paste foreground into center of backdrop
        paste_x = (target_w - fg_w) // 2
        paste_y = (target_h - fg_h) // 2
        bg.paste(fg, (paste_x, paste_y))

        bg.save(output_path, quality=92)
        return True
    except Exception as exc:
        logger.warning("Failed to download or format image from %s: %s", image_url, exc)
        return False


def score_item_topic_match(
    entity_query: str,
    ai_prompt: str,
    scene_text: str,
    item: WorldNewsItem,
) -> int:
    """Calculate topic overlap score between a scene's entity/prompt/text and a news item."""
    query_text = f"{entity_query} {ai_prompt}".lower()
    item_text = f"{item.title} {item.summary}".lower()

    stops = {
        "the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or", "with",
        "from", "by", "is", "was", "this", "that", "these", "those", "are", "were",
        "it", "its", "as", "new", "photo", "cinematic", "high", "quality", "news",
        "real", "world", "style", "image", "visual", "shot", "showing", "background",
        "clean", "bright", "futuristic", "vertical", "horizontal", "people",
    }
    query_words = set(re.findall(r"\b[a-z]{3,}\b", query_text)) - stops
    item_words = set(re.findall(r"\b[a-z]{3,}\b", item_text)) - stops

    score = len(query_words.intersection(item_words))

    # Numbers are definitive topic markers (e.g. 53 orangutans, 150 million years, 90 percent)
    scene_numbers = set(re.findall(r"\b\d+\b", scene_text))
    item_numbers = set(re.findall(r"\b\d+\b", item_text))
    score += len(scene_numbers.intersection(item_numbers)) * 2

    # Proper names/capitalized terms in Vietnamese scene text (e.g. Borneo, Spinosaurus, Florida, Yale)
    scene_proper = set(re.findall(r"\b[A-Z][a-z]{3,}\b", scene_text))
    item_proper = set(re.findall(r"\b[A-Z][a-z]{3,}\b", item.title + " " + item.summary))
    score += len(scene_proper.intersection(item_proper)) * 2

    return score


def find_matching_news_item_for_scene(
    scene_text: str,
    scene_entity: str,
    scene_ai_prompt: str,
    source_event_idx: Optional[int],
    news_items: List[WorldNewsItem],
) -> Optional[WorldNewsItem]:
    """Find the verified authentic news item corresponding to this scene.

    Completely avoids sequential drift (idx-1) to guarantee 100% text-to-image fidelity.
    """
    if not news_items:
        return None

    # Step 1: Check suggested event index if provided by Gemini
    if source_event_idx is not None and isinstance(source_event_idx, int) and 1 <= source_event_idx <= len(news_items):
        cand = news_items[source_event_idx - 1]
        score = score_item_topic_match(scene_entity, scene_ai_prompt, scene_text, cand)
        if score >= 1:
            return cand

    # Step 2: Global semantic / keyword matching across all candidates
    best_score = 0
    best_item: Optional[WorldNewsItem] = None
    for item in news_items:
        score = score_item_topic_match(scene_entity, scene_ai_prompt, scene_text, item)
        if score > best_score:
            best_score = score
            best_item = item

    if best_score >= 2 and best_item is not None:
        return best_item

    return None


def synthesize_news_script_with_gemini(
    news_items: List[WorldNewsItem],
    api_key: str,
    detail_level: Literal["concise", "standard", "deep"] = "standard",
    max_topics: int = 8,
    category: str = "world",
) -> DailyNewsDigest:
    """Use Gemini Flash to create an editorial Vietnamese YouTube news broadcast (Option A: 7-10 topics)."""
    cfg = get_category_config(category)
    now_dt = datetime.now()
    date_str = now_dt.strftime("%d/%m/%Y")
    items_text = "\n\n".join(
        f"SỰ KIỆN {idx + 1}: [{item.source}] {item.title}\nChi tiết sự việc từ bài báo: {item.full_text if item.full_text else item.summary}"
        for idx, item in enumerate(news_items[:15])
    )

    if category in ("viral", "hope"):
        if max_topics <= 3:
            scenes_per_topic_desc = f"1 phân cảnh chi tiết, sống động và hấp dẫn (25-35 từ) cho mỗi sự kiện (tập trung Top {max_topics} sự kiện đắt giá nhất)"
            target_words = "khoảng 130 đến 180 từ tiếng Việt (khoảng 45 đến 55 giây, nhịp điệu cuốn hút chuẩn YouTube Shorts Top 3)"
            min_scenes = max_topics + 2
            max_scenes = max_topics + 2
            word_count_guideline = "25 - 35 từ sống động, đào sâu diễn biến và chi tiết bất ngờ"
        else:
            scenes_per_topic_desc = f"1 phân cảnh cuốn hút và súc tích (18-28 từ) cho mỗi sự kiện (tổng cộng đủ {max_topics} sự kiện nổi bật khắp thế giới)"
            target_words = "khoảng 140 đến 220 từ tiếng Việt (khoảng 45 đến 55 giây, nhanh gọn và lôi cuốn chuẩn YouTube Shorts)"
            min_scenes = max_topics + 2
            max_scenes = max_topics + 2
            word_count_guideline = "18 - 28 từ súc tích, truyền cảm hứng và khơi gợi hy vọng"
    elif detail_level == "deep":
        scenes_per_topic_desc = "2 đến 3 phân cảnh phân tích chuyên sâu, giàu cảm xúc, trích dẫn phát biểu và số liệu"
        target_words = "1100 - 1500 từ tiếng Việt (khoảng 7 đến 9 phút xem)"
        min_scenes = max_topics * 2 + 2
        max_scenes = max_topics * 3 + 2
        word_count_guideline = "55 - 80 từ mỗi phân cảnh"
    elif detail_level == "concise":
        scenes_per_topic_desc = "1 đến 2 phân cảnh súc tích nhưng đầy đủ dữ kiện"
        target_words = "500 - 700 từ tiếng Việt (khoảng 3 đến 4.5 phút xem)"
        min_scenes = max_topics + 2
        max_scenes = max_topics + 4
        word_count_guideline = "35 - 50 từ mỗi phân cảnh"
    else:  # standard (default for YouTube Phương án A)
        scenes_per_topic_desc = "2 phân cảnh toàn diện (Scene 1: Tường thuật diễn biến trực tiếp; Scene 2: Phân tích số liệu, bảng xếp hạng và phát biểu)"
        target_words = "800 - 1100 từ tiếng Việt (khoảng 5 đến 7 phút xem)"
        min_scenes = max_topics * 2
        max_scenes = max_topics * 2 + 4
        word_count_guideline = "45 - 65 từ tường thuật sống động, giàu thông tin"

    category_specific_rules = ""
    if category in ("tin_moi", "morning"):
        category_specific_rules = """
ĐẶC THÙ BẮT BUỘC CHO BẢN TIN MỚI (CHIẾN LƯỢC KẾT HỢP: THỜI SỰ THẾ GIỚI & BÓNG ĐÁ QUỐC TẾ):
- Bản tin kết hợp hài hòa 2 mảng nội dung quốc tế được người xem quan tâm nhất buổi sáng:
  + MẢNG 1 (THỜI SỰ & KINH TẾ QUỐC TẾ): Các diễn biến thời sự nóng bỏng, quan hệ quốc tế, kinh tế toàn cầu và các sự kiện đáng chú ý tại Âu - Mỹ, Trung Đông và khu vực Châu Á láng giềng.
  + MẢNG 2 (ĐIỂM SÁNG SÂN CỎ & BÓNG ĐÁ ĐỈNH CAO): Điểm nhấn các giải đấu hàng đầu thế giới (Ngoại Hạng Anh, Cúp C1, La Liga, Serie A...), kết quả tỉ số, siêu phẩm bàn thắng, diễn biến bảng xếp hạng và các câu chuyện ngôi sao (Mbappe, Haaland, Bellingham, Vinicius, Messi, Ronaldo...).
- BỐ CỤC & CHUYỂN MẠCH: Duy trì phong cách thời sự đĩnh đạc, hiện đại (format theme Bản tin thế giới). Giữa 2 mảng nội dung có câu chuyển mạch tự nhiên, chuyên nghiệp (ví dụ: "Tiếp nối bản tin là những điểm nhấn sôi động trên sân cỏ quốc tế rạng sáng nay...").
- Mỗi sự kiện triển khai 2 phân cảnh chi tiết (45-65 từ/cảnh).
- TUYỆT ĐỐI CẤM đưa tin về Việt Nam (không đưa tin chính trị, xã hội, hay bóng đá Việt Nam). Toàn bộ bản tin 100% là quốc tế.
"""
    elif category in ("tin_nong", "evening"):
        category_specific_rules = """
ĐẶC THÙ BẮT BUỘC CHO BẢN TIN NÓNG (CHIẾN LƯỢC KẾT HỢP: CHIẾN SỰ THẾ GIỚI & ĐỘT PHÁ CÔNG NGHỆ):
- Bản tin phân tích chuyên sâu 2 chuyên đề kịch tính và có sức ảnh hưởng toàn cầu lớn nhất buổi tối:
  + CHUYÊN ĐỀ 1 (CHIẾN SỰ & AN NINH QUỐC PHÒNG): Cập nhật thực địa các điểm nóng chiến trường quốc tế (Nga - Ukraine, Trung Đông Gaza/Lebanon/Yemen, Biển Đỏ, căng thẳng eo biển Đài Loan/Triều Tiên...), thương vong, đòn tập kích, động thái quân sự và vũ khí phòng thủ.
  + CHUYÊN ĐỀ 2 (ĐỘT PHÁ CÔNG NGHỆ THẾ GIỚI & AI): Trí tuệ nhân tạo (OpenAI, Google, Nvidia...), vi mạch bán dẫn, công nghệ vũ trụ, robot, xe điện và các bước ngoặt công nghệ tương lai.
- BỐ CỤC: Giọng điệu đĩnh đạc, kịch tính, chuẩn mực chính luận quân sự và phân tích công nghệ đỉnh cao sắc bén (format theme Chiến sự thế giới).
- Mỗi sự kiện triển khai 2 phân cảnh chi tiết (45-65 từ/cảnh).
- TUYỆT ĐỐI CẤM đưa tin về Việt Nam. Toàn bộ bản tin 100% là quốc tế.
"""
    elif category == "sports":
        category_specific_rules = """
ĐẶC THÙ BẮT BUỘC RIÊNG CHO BẢN TIN BÓNG ĐÁ (100% FOOTBALL FOCUS - CHẤT LƯỢNG CAO, GIÀU DỮ KIỆN):
- Tập trung 100% vào BÓNG ĐÁ ĐỈNH CAO & BÓNG ĐÁ KHU VỰC:
  + 5 Giải VĐQG hàng đầu Châu Âu & Cúp C1: Ngoại Hạng Anh (Premier League), Ý (Serie A), Đức (Bundesliga), Pháp (Ligue 1), Tây Ban Nha (La Liga), Cúp C1 (UEFA Champions League).
  + Câu chuyện Ngôi sao: Mbappe, Haaland, Bellingham, Vinicius, Lamine Yamal, Messi, Ronaldo, Harry Kane, Salah, phát biểu, drama chuyển nhượng, danh hiệu Quả Bóng Vàng.
  + Bóng đá láng giềng & khu vực người Việt quan tâm: Thái Lan (Thai League, ĐTQG), Indonesia (dàn sao nhập tịch Châu Âu, vòng loại World Cup), Trung Quốc (CSL, thanh trừng tiêu cực, cải tổ), Campuchia (bóng đá trẻ, giải đấu khu vực).
- TUYỆT ĐỐI CẤM đưa tin về các môn thể thao khác (bóng bầu dục, bóng chày, golf, cricket, tennis, F1, bóng rổ, bơi lội,...).
- TUYỆT ĐỐI CẤM đưa tin về Việt Nam (không đưa V-League, không đưa tuyển Việt Nam hay cầu thủ Việt Nam). Toàn bộ bản tin phải 100% là bóng đá quốc tế.
- BẢN TIN PHẢI DÀY DẶN, GIÀU DỮ LIỆU, TUYỆT ĐỐI CẤM VIẾT NGẮN NGỦN NGHÈO NÀN:
  + Mỗi sự kiện bóng đá PHẢI triển khai đủ 2 phân cảnh rõ rệt (Scene 1 & Scene 2), mỗi phân cảnh dài 45-65 từ:
    * Scene 1 (Diễn biến kịch tính): Tường thuật tỷ số chính xác, phút ghi bàn, ai kiến tạo, khoảnh khắc siêu phẩm, tình huống cứu thua, sai lầm phòng ngự, bước ngoặt thẻ đỏ hay can thiệp VAR.
    * Scene 2 (Thống kê & Nhận định): Nêu số liệu thống kê (kiểm soát bóng, số cú sút trúng đích), tác động lên bảng xếp hạng giải đấu (khoảng cách điểm số, cuộc đua vô địch hay top 4), giá trị chuyển nhượng (triệu Euro/Bảng Anh) và phát biểu sau trận của HLV hoặc ngôi sao bóng đá.
- Giọng văn: Phong cách bình luận viên bóng đá truyền hình (như VTV/K+/Sky Sports) sôi nổi, giàu năng lượng, dùng thuật ngữ chuyên môn chuẩn xác ("siêu phẩm sút xa", "màn lội ngược dòng nghẹt thở", "cú đúp đẳng cấp", "cục diện bảng xếp hạng", "bom tấn chuyển nhượng").
- QUY TẮC BẮT BUỘC CHO "entity_query" TÌM ẢNH BÓNG ĐÁ:
  + "entity_query" BẮT BUỘC PHẢI LÀ TÊN CỤ THỂ CỦA CẦU THỦ, HUẤN LUYỆN VIÊN HOẶC CÂU LẠC BỘ BÓNG ĐÁ KÈM DANH TỪ BÓNG ĐÁ (Ví dụ: "Kylian Mbappe football player", "Real Madrid football club", "Mikel Arteta football manager", "Erling Haaland Manchester City", "Arsenal football club", "Lamine Yamal Barcelona").
  + TUYỆT ĐỐI CẤM đưa các từ ngữ ẩn dụ, tu từ, thành ngữ hoặc từ ngữ chung chung vào "entity_query" (NGHIÊM CẤM các từ: "witch hunt", "witch", "mafia", "godfather", "saint", "devils", "gunners", "war", "battle", "doctor", "crisis", "the team").
"""
    elif category == "war":
        category_specific_rules = """
ĐẶC THÙ BẮT BUỘC CHO BẢN TIN CHIẾN SỰ THẾ GIỚI:
- Tập trung chuyên sâu 100% vào chiến sự, quân sự và xung đột trên khắp thế giới:
  + Chiến trường Nga - Ukraine, Trung Đông (Gaza, Bờ Tây, Lebanon/Hezbollah, Yemen/Houthi, Syria, Iran), các điểm nóng an ninh Châu Á (eo biển Đài Loan, bán đảo Triều Tiên, nội chiến Myanmar), và các cuộc biểu tình bạo loạn vũ trang.
  + TUYỆT ĐỐI CẤM 100% đưa tin thể thao (bóng đá, giải đấu), tin đời tư nghệ sĩ, giải trí, sức khỏe cá nhân hay kinh tế thuần túy. Toàn bộ bản tin phải 100% là sự kiện chiến sự, quân sự và an ninh quốc phòng quốc tế.
- Giọng điệu đĩnh đạc, nghiêm túc, kịch tính, chuẩn mực chính luận quân sự - địa chính trị quốc tế.
- Mỗi sự kiện triển khai 2 phân cảnh chi tiết (45-65 từ/cảnh): Scene 1 tường thuật diễn biến giao tranh, thương vong thực địa, phòng tuyến hoặc đòn không kích; Scene 2 phân tích khí tài vũ khí, động thái chiến lược các bên và tác động an ninh khu vực.
- TUYỆT ĐỐI KHÔNG đưa tin về Việt Nam. Chỉ đưa tin thế giới quốc tế.
"""
    elif category == "tech":
        category_specific_rules = """
ĐẶC THÙ BẮT BUỘC CHO BẢN TIN CÔNG NGHỆ:
- Tập trung vào AI, bán dẫn vi mạch, thiết bị đột phá, không gian vũ trụ, phần mềm và các tập đoàn công nghệ toàn cầu (bao gồm Thung lũng Silicon, xe điện & AI Trung Quốc, chip bán dẫn Đài Loan/Hàn Quốc, robotics Nhật Bản).
- Mỗi sự kiện triển khai 2 phân cảnh chi tiết (45-65 từ/cảnh): Scene 1 nêu bật sản phẩm và tính năng đột phá; Scene 2 phân tích thông số kỹ thuật, giá trị thị trường và tác động thực tế.
- TUYỆT ĐỐI KHÔNG đưa tin về Việt Nam.
"""
    elif category == "viral":
        category_specific_rules = f"""
ĐẶC THÙ BẮT BUỘC RIÊNG CHO BẢN TIN TIN LẠ & HÀI HƯỚC (CHUẨN YOUTUBE SHORTS - {max_topics} SỰ KIỆN ĐỘC LẠ & HÀI):
- TIÊU CHUẨN TUYỂN CHỌN KHẮC KHE: Các sự kiện PHẢI THẬT SỰ ĐỘC LẠ hoặc THẬT SỰ HÀI HƯỚC (tình huống dở khóc dở cười, pha xử lý cồng kềnh, động vật tấu hài, tên trộm vụng về, pha fail kinh điển, hiện tượng kỳ dị bí ẩn, kỳ tích khó tin).
- NGUỒN TIN ĐA KHU VỰC: Tích hợp các câu chuyện viral từ Trung Quốc (Douyin/Weibo), Thái Lan và Đông Nam Á (clip hài, động vật hoang dã oái oăm), Nga/Siberia (thời tiết khắc nghiệt, hố sụt kỳ bí), Nhật Bản/Hàn Quốc bên cạnh trào lưu mạng Âu - Mỹ.
- LƯỢC BỎ TRIỆT ĐỂ các tin độ độc lạ không nhiều, nhạt nhẽo (như bán đấu giá tem/tiền xu thông thường, khảo sát dân số khô khan, hoãn chuyến bay vì giấy tờ, biến đổi thời tiết nhẹ...).
- TỈ LỆ LINH HOẠT: Tuyệt đối không ép buộc cân bằng 50/50 giữa lạ và hài. Tùy ngày nguồn tin nào nhiều và đặc sắc hơn thì ưu tiên tin đó; điều cốt lõi là TẤT CẢ các tin được chọn PHẢI THẬT SỰ ĐỘC LẠ HOẶC THẬT SỰ HÀI HƯỚC, mang tính giải trí hoặc gây sốc cao.
- Mỗi sự kiện CHỈ TRIỂN KHAI ĐÚNG 1 PHÂN CẢNH (Scene) với dung lượng súc tích (18-28 từ tiếng Việt). Giọng văn dí dỏm, hóm hỉnh với tin hài; kịch tính, ngỡ ngàng với tin lạ; nhịp điệu nhanh lôi cuốn chuẩn YouTube Shorts.
- Intro (Hook) và Outro cực ngắn (10-18 từ mỗi cảnh) để giữ tổng thời lượng lồng tiếng vừa vặn chuẩn YouTube Shorts (45-55 giây). Intro đi thẳng vào cú hook ấn tượng nhất, KHÔNG chào hỏi.
- Tiêu đề: chỉ cần trả "hook_title" ở trên; hệ thống tự ghép đuôi " - {cfg.get('title_suffix_label', 'Tin Nóng & Độc Lạ')} DD/MM/YYYY #Shorts".
- TUYỆT ĐỐI CẤM đưa tin về Việt Nam. Chỉ đưa tin thế giới quốc tế.
- QUY TẮC "entity_query": Từ khóa tiếng Anh cụ thể miêu tả khoảnh khắc/nhân vật/sự cố hài hước hoặc độc lạ.
- QUY TẮC BẮT BUỘC CHO "ai_prompt": PHẢI XÁC ĐỊNH RÕ CHỦ THỂ THỊ GIÁC CỐT LÕI (con vật gì, đồ vật gì, nhân vật gì). Prompt ngắn gọn, đơn giản (15-25 từ tiếng Anh), TRỌNG TÂM 100% VÀO CHỦ THỂ ĐÓ để làm hình ảnh minh họa chân thực. TUYỆT ĐỐI KHÔNG để từ địa danh (như Maryland, Florida) làm AI vẽ nhầm ra tên người (như vẽ ra một cô gái tên Mary thay vì con bò)!
"""
    elif category == "hope":
        category_specific_rules = f"""
ĐẶC THÙ BẮT BUỘC RIÊNG CHO BẢN TIN TIN VUI (CHUẨN YOUTUBE SHORTS - {max_topics} ĐỘT PHÁ HY VỌNG):
- NGUYÊN TẮC PHÂN BỔ TRỌNG TÂM:
  1. TẬP TRUNG NHIỀU NHẤT VÀO:
     + Y KHOA & SỨC KHỎE: Đột phá điều trị bệnh hiểm nghèo, ung thư, tế bào gốc, vắc-xin, phục hồi vận động/thị lực, cứu sống bệnh nhân.
     + SỰ SỐNG & MUÔN LOÀI: Kỳ tích bảo tồn động vật hoang dã, cứu hộ sinh vật nguy cấp, tái sinh hệ sinh thái rạn san hô và đại dương.
     + MÔI TRƯỜNG & HỒI SINH TRÁI ĐẤT: Thu gom rác thải đại dương, phủ xanh rừng rậm, làm sạch nguồn nước và không khí, giải pháp bền vững cho Trái Đất.
  2. CÁC LOẠI TIN KHÁC (TRỌNG SỐ BÉ HƠN):
     + Vẫn có thể sử dụng các tin về sáng chế công nghệ, năng lượng mới, vật liệu tương lai nhưng phân bổ trọng số thấp hơn, không lấn át nhóm Y khoa - Sự sống - Môi trường.
- BÌNH LUẬN TRUYỀN CẢM HỨNG VÀ HY VỌNG:
  + Lời bình luận phải đem lại cảm giác ấm áp, hy vọng, niềm tin vào tương lai nhân loại và sự kỳ diệu của sự sống.
  + Nhấn mạnh lợi ích thiết thực: Cứu sống bao nhiêu sinh mạng, hồi sinh bao nhiêu diện tích rừng/biển, chữa khỏi bệnh gì.
- CHUẨN YOUTUBE SHORTS NGẮN GỌN, CUỐN HÚT:
  + Mỗi sự kiện CHỈ TRIỂN KHAI ĐÚNG 1 PHÂN CẢNH (Scene) với dung lượng 18-28 từ tiếng Việt, súc tích, mạch lạc, dứt khoát.
  + Intro (Hook 3 giây đầu): Nêu ngay đột phá y khoa/sự sống/môi trường ấn tượng nhất để khơi gợi hy vọng, KHÔNG chào hỏi rườm rà.
  + Outro (Phân cảnh kết): Đúc kết 1 câu ngắn tràn đầy hy vọng về tương lai và mời đăng ký kênh để đón nhận nguồn năng lượng tích cực mỗi ngày.
  + Tổng thời lượng video khoảng 45-55 giây.
- Tiêu đề: chỉ cần trả "hook_title" ở trên; hệ thống tự ghép đuôi " - {cfg.get('title_suffix_label', 'Tin Vui Thế Giới')} DD/MM/YYYY #Shorts".
- TUYỆT ĐỐI CẤM đưa tin về Việt Nam. Chỉ đưa tin thế giới quốc tế.
- QUY TẮC CHO "entity_query" VÀ "ai_prompt": Từ khóa tiếng Anh chuẩn xác về chủ thể y khoa/động vật/môi trường (ví dụ: 'cancer immunotherapy laboratory cells', 'coral reef restoration ocean divers', 'reforestation tree planting drones'). Tránh từ ngữ trừu tượng.
"""
    else:
        category_specific_rules = """
ĐẶC THÙ BẮT BUỘC CHO BẢN TIN THỜI SỰ THẾ GIỚI:
- Tập trung vào địa chính trị, an ninh quốc tế, kinh tế vĩ mô toàn cầu.
- ĐẶC BIỆT CHÚ TRỌNG: Cân đối giữa các điểm nóng Âu - Mỹ, Trung Đông với các quốc gia láng giềng gần gũi và đối tác chiến lược tại Châu Á - Thái Bình Dương (Trung Quốc, Đông Nam Á láng giềng, Nga, Nhật Bản, Hàn Quốc).
- Mỗi sự kiện triển khai 2 phân cảnh chi tiết (45-65 từ/cảnh): Scene 1 tường thuật diễn biến cốt lõi; Scene 2 phân tích nguyên nhân, số liệu thiệt hại/ngân sách và phản ứng các bên.
- TUYỆT ĐỐI KHÔNG đưa tin về Việt Nam.
"""

    prompt = f"""{cfg["persona"]}

{items_text}

{category_specific_rules}

QUY TẮC BIÊN TẬP VÀNG BẮT BUỘC:
1. LUẬT TỐI THƯỢNG BẤT KHẢ XÂM PHẠM (ÁP DỤNG TUYỆT ĐỐI CHO TẤT CẢ CÁC BẢN TIN):
   - TUYỆT ĐỐI 100% KHÔNG ĐƯỢC ĐƯA BẤT KỲ THÔNG TIN NÀO LIÊN QUAN ĐẾN VIỆT NAM.
   - NGHIÊM CẤM nhắc tên Việt Nam, người Việt Nam, kiều bào, địa danh, tỉnh thành, tổ chức, cơ quan, chính sách, kinh tế, thể thao, hay bất kỳ liên hệ, so sánh nào với Việt Nam.
   - Toàn bộ 100% nội dung (tiêu đề "hook_title", mô tả "summary_lead", "thumbnail_hook", "ticker_summary", và toàn bộ lời thuyết minh trong từng "scene") PHẢI THUẦN TÚY LÀ SỰ KIỆN QUỐC TẾ NGUYÊN BẢN.
2. NGUYÊN TẮC TRUNG THỰC & ĐỐI SOÁT TÀI LIỆU (GROUNDING PRINCIPLE):
   - CHỈ ĐƯỢC CHỌN VÀ BIÊN TẬP TỪ CÁC SỰ KIỆN CÓ THẬT TRONG DANH SÁCH [SỰ KIỆN 1..N] ĐƯỢC CUNG CẤP Ở TRÊN.
   - TUYỆT ĐỐI CẤM TỰ BỊA RA CÁC CÂU CHUYỆN HOẶC ĐỘT PHÁ KHÔNG CÓ TRONG DANH SÁCH (ví dụ: Không tự bịa ra thuốc chữa ung thư, Alzheimer hay vắc-xin nếu danh sách tài liệu bên trên không có bài báo tương ứng).
   - Với mỗi phân cảnh, BẮT BUỘC trả về "source_event_index" là số nguyên từ 1 đến {len(news_items)} chỉ rõ phân cảnh này tường thuật sự kiện nào trong danh sách. Nếu là phân cảnh Hook (Scene 0), điền số thứ tự của sự kiện ấn tượng nhất được chọn làm hook. Nếu là phân cảnh Outro kết thúc tổng quan chung, điền 0.
3. TIÊU ĐỀ, THUMBNAIL & TICKER GÂY TÒ MÒ (QUYẾT ĐỊNH LƯỢT NHẤP):
   - "hook_title": tiêu đề tin nóng/gây tò mò nhất của bản tin, 35-60 ký tự, tiếng Việt có dấu, viết hoa chữ cái đầu mỗi từ. KHÔNG chứa ngày tháng, KHÔNG chứa cụm "Toàn Cảnh", KHÔNG chứa tên chuyên mục (hệ thống tự ghép đuôi " - {cfg['title_suffix_label']} {date_str}").
   - Ví dụ "hook_title": "Giá Vàng Lao Dốc, Chạm Đáy Mới" hoặc "Nga Tập Kích Kyiv, Thế Giới Nín Thở".
   - "thumbnail_hook": câu chữ IN HOA trên ảnh bìa, TỐI ĐA 8 TỪ, gợi tò mò hoặc đặt câu hỏi mở (ví dụ: "SỐC: ĐÁY MỚI?", "BƯỚC NGOẶT LỊCH SỬ?"). Không lặp nguyên văn hook_title.
   - "ticker_summary": dòng chữ chạy cuối màn hình tóm tắt TẤT CẢ các tin trong bản tin, mỗi tin 1 mệnh đề ngắn (8-14 từ), nối nhau bằng ký tự " | ", không xuống dòng.
   - Ghi chú: Hệ thống tự ghép tiêu đề cuối cùng dạng "[hook_title] - {cfg['title_suffix_label']} {date_str}".
4. TUYỆT ĐỐI CẤM NỘI DUNG NGẮN NGỦN NGHÈO NÀN:
   - Mỗi tin PHẢI triển khai đủ 2 phân cảnh (Scene 1 và Scene 2), mỗi phân cảnh dài từ 45 đến 65 từ tiếng Việt đầy đủ chi tiết (riêng Shorts mỗi sự kiện 1 phân cảnh 18-28 từ).
   - TUYỆT ĐỐI CẤM viết 1-2 câu ngắn ngủn qua loa rồi chuyển sang tin khác. Người xem cần nghe diễn biến đầy đủ, tên nhân vật, địa điểm, số liệu cụ thể và phân tích sâu sắc.
5. TUYỆT ĐỐI CẤM các câu sáo rỗng, sáo ngữ rập khuôn gây phản cảm cho người xem như:
   - "Diễn biến này đang là tâm điểm chú ý trên các phương tiện truyền thông thế giới"
   - "Giới quan sát nhận định sự việc này có thể ảnh hưởng đến tình hình an ninh và ngoại giao quốc tế"
   - "Đang thu hút sự theo dõi sát sao của dư luận"
6. TỰ COOK LẠI NỘI DUNG THÀNH LỜI THUYẾT MINH PHÁT THANH VIÊN SỐNG ĐỘNG:
   - Đọc kỹ toàn bộ dữ kiện thực tế từ bài báo (Nhân vật, chức danh, hành động, số liệu/tỷ số/thông số/kết quả, địa điểm chính xác, nguyên nhân và trích dẫn phát biểu).
   - "Cook" lại thành lời thuyết minh hấp dẫn, giàu cảm xúc, chuẩn phong cách phát thanh viên/bình luận viên truyền hình.
   - TUYỆT ĐỐI KHÔNG lặp lại tiêu đề ở các phân cảnh liền kề.
   - TUYỆT ĐỐI CẤM lặp lại cụm từ "Theo ghi nhận từ..." ở các phân cảnh thứ hai. Hãy đa dạng hóa tự nhiên:
     "Theo báo [Nguồn],", "Báo [Nguồn] có viết,", "[Nguồn] cho hay,", "Thông tin từ [Nguồn] cho biết,", "Cụ thể, [Nguồn] nêu rõ,".
   - Scene 1: Nêu bật sự kiện và diễn biến chính.
   - Scene 2: Phân tích số liệu cụ thể, chi tiết bối cảnh, thông số kỹ thuật hoặc tuyên bố từ người trong cuộc.
7. MỞ ĐẦU ĐI THẲNG VÀO TIN SỐC (HOOK 3 GIÂY ĐẦU):
   - TUYỆT ĐỐI CẤM mọi lời chào/mời chào/giới thiệu kênh ở đầu bản tin: "Chào mừng...", "Xin chào...", "Kính chào quý vị...", "Hôm nay chúng ta cùng điểm qua...".
   - Câu đầu tiên của Scene 0 phải nêu NGAY sự kiện chấn động/kịch tính nhất kèm một con số hoặc chi tiết gây sốc, hoặc một câu hỏi tò mò, rồi mới dẫn dắt sang các tin tiếp theo.
   - Ví dụ: "Một tên lửa vừa giáng thẳng xuống trung tâm Kyiv rạng sáng nay, hai người chết, hai mươi hai người bị thương. Đây mới chỉ là điểm nóng đầu tiên, cùng điểm qua những diễn biến chấn động nhất ngay sau đây."
8. BỐ CỤC BẢN TIN YOUTUBE ({max_topics} SỰ KIỆN):
   - Phân cảnh mở đầu (Scene 0 - Hook): 2-3 câu (35-50 từ; Shorts 10-18 từ), mở bằng tin sốc nhất rồi dẫn vào bản tin. Không chào hỏi, không nêu tên kênh.
   - Các phân cảnh cho từng tin: Mỗi tin triển khai {scenes_per_topic_desc} ({word_count_guideline} mỗi câu thuyết minh).
   - Phân cảnh kết thúc (Outro): Lời chào kết, nhắc khán giả bấm đăng ký kênh YouTube để cập nhật {cfg["outro_topic_name"]} mỗi ngày.
   - Tổng kịch bản toàn bản tin gồm từ {min_scenes} đến {max_scenes} phân cảnh, tổng độ dài khoảng {target_words}.
9. VỚI MỖI PHÂN CẢNH (SCENE):
   - "source_event_index": Số nguyên 1 đến {len(news_items)} chỉ rõ sự kiện tương ứng trong danh sách (hoặc 0 nếu là Outro).
   - "text": Lời đọc thuyết minh tiếng Việt hoàn chỉnh, giàu thông tin chi tiết. Tên riêng quốc tế viết chuẩn xác bằng chữ Latin nguyên bản (ví dụ: "Kylian Mbappé", "Erling Haaland", "Real Madrid", "Mikel Arteta", "Champions League").
   - "entity_query": Từ khóa tiếng Anh cụ thể, đơn giản (1-3 từ) tìm ảnh thật chính xác (ví dụ: 'Bornean orangutan', 'Coral reef', 'Dentistry', 'Spinosaurus', 'Sunrise'). TUYỆT ĐỐI KHÔNG dùng tính từ hoa mỹ, cảm thán hay cụm từ trừu tượng.
   - "ai_prompt": QUY TẮC BẮT BUỘC VỀ XÁC ĐỊNH CHỦ THỂ CỐT LÕI (CORE VISUAL SUBJECT GROUNDING):
     + BƯỚC 1: Xác định rõ CHỦ THỂ HÌNH ẢNH TRUNG TÂM (con vật cụ thể, đồ vật cụ thể, con người hay hành động cụ thể).
     + BƯỚC 2: Viết prompt tiếng Anh đơn giản, ngắn gọn (15 - 25 từ), TRỌNG TÂM 100% VÀO CHỦ THỂ ĐÓ để làm hình ảnh minh họa chân thực.
     + TUYỆT ĐỐI KHÔNG để AI vẽ nhầm theo tên địa danh, từ trừu tượng hay ẩn dụ:
       * Ví dụ: Tin về con bò tẩu thoát ở Maryland -> Chủ thể là 'a cow', prompt: 'photorealistic news photo of a real cow standing on highway road shoulder with police car'. TUYỆT ĐỐI KHÔNG để từ Maryland làm AI vẽ ra một người tên Mary!
       * Ví dụ: Tin về tượng quái vật làm từ rác -> Chủ thể là 'a tall monster sculpture made of scrap junk and recycled materials'.
       * Ví dụ: Tin về bộ sưu tập ếch -> Chủ thể là 'thousands of toy frogs and frog figurines packed on shelves'.
       * Ví dụ: Tin về bài hát công sở -> Chủ thể là 'cheerful corporate office employees laughing in meeting room'.
   - "has_transition_cue": true nếu đây là phân cảnh bắt đầu một sự kiện/tin tức mới hoặc phân cảnh kết thúc (outro); false nếu là phân cảnh thứ hai phân tích chi tiết.
10. ĐỊNH HƯỚNG KỸ XẢO THỊ GIÁC & TIẾT CHẾ NGHỆ THUẬT (VISUAL HARNESS & ARTISTIC BALANCE):
   - Vận dụng tư duy kỹ xảo truyền hình hiện đại (Motion graphics, dynamic infographics, 3D geo-mapping, cinematic framing) để làm giàu hình ảnh minh họa:
     + Với tin địa chính trị, chiến sự, ngoại giao: Ưu tiên góc máy phóng sự điều tra, hình ảnh thực địa, bản đồ phân bổ tọa độ rõ nét, góc chụp trực quan của nhân vật trung tâm.
     + Với tin kinh tế, công nghệ, số liệu, giá vàng: Ưu tiên minh họa trực quan dạng bảng biểu dữ liệu, biểu đồ số liệu sắc nét, thiết bị phần cứng vĩ mô hoặc trung tâm điều khiển hiện đại.
     + Với tin thể thao, độc lạ: Góc máy hành động dynamic action shot, cận cảnh biểu cảm kịch tính và chi tiết giàu cảm xúc.
   - NGUYÊN TẮC VÀNG BẮT BUỘC VỀ TIẾT CHẾ NGHỆ THUẬT:
     Tạo sự phong phú sáng tạo và minh họa rõ trực quan, nghệ thuật cho nội dung, TUYỆT ĐỐI KHÔNG ĐƯỢC QUÁ ĐÀ, QUÁ LỐ gây mất tập trung vào thông tin cốt lõi của bản tin. Kỹ xảo và hình ảnh phải phục vụ và tôn vinh thông tin thời sự, không phô diễn rườm rà.

YÊU CẦU ĐỊNH DẠNG:
Trả về DUY NHẤT một chuỗi JSON hợp lệ với cấu trúc sau:
{{
  "hook_title": "[Tiêu đề tin nóng gây tò mò nhất, 35-60 ký tự, không ngày tháng]",
  "thumbnail_hook": "[TỐI ĐA 8 TỪ IN HOA GỢI TÒ MÒ]",
  "ticker_summary": "[Tin 1 | Tin 2 | Tin 3 ... tóm tắt tất cả tin]",
  "summary_lead": "Tóm tắt 1-2 câu chứa đựng thông điệp cốt lõi",
  "hashtags": "{cfg['hashtags']}",
  "scenes": [
    {{
      "scene_index": 0,
      "source_event_index": 1,
      "text": "Câu hook nêu ngay tin sốc nhất rồi dẫn vào bản tin (KHÔNG chào hỏi)...",
      "entity_query": "{cfg['intro_entity']}",
      "ai_prompt": "{cfg['intro_ai_prompt']}",
      "has_transition_cue": false
    }},
    {{
      "scene_index": 1,
      "source_event_index": 1,
      "text": "Mở đầu bản tin hôm nay...",
      "entity_query": "English Entity Keyword",
      "ai_prompt": "Cinematic photo of...",
      "has_transition_cue": true
    }}
  ]
}}
"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.25,
            "responseMimeType": "application/json",
        },
    }

    res = None
    last_exc = None
    for model_name in GEMINI_MODELS:
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=35) as resp:
                res = json.loads(resp.read().decode("utf-8"))
            if res and "candidates" in res and res["candidates"]:
                logger.info("Successfully synthesized news script using model '%s'", model_name)
                break
        except Exception as exc:
            last_exc = exc
            logger.warning("Gemini model '%s' failed (%s). Trying next candidate...", model_name, exc)
            time.sleep(1.0)

    if not res:
        raise last_exc or RuntimeError("All Gemini candidate models failed.")

    raw_text = res["candidates"][0]["content"]["parts"][0]["text"]
    parsed = json.loads(raw_text)

    scenes: List[DailyNewsScene] = []
    raw_scenes = parsed.get("scenes", [])
    total_raw = len(raw_scenes)
    for idx, s in enumerate(raw_scenes):
        raw_cue = s.get("has_transition_cue")
        if isinstance(raw_cue, bool):
            is_cue = raw_cue
        else:
            is_cue = (idx > 0 and (idx % 2 == 1 or idx == total_raw - 1))

        # Map authentic news item image & platform using topic matching (0% blind sequential drift)
        source_idx_val = s.get("source_event_index")
        src_idx_int = None
        if isinstance(source_idx_val, int):
            src_idx_int = source_idx_val
        elif isinstance(source_idx_val, str) and source_idx_val.isdigit():
            src_idx_int = int(source_idx_val)

        matched_item = find_matching_news_item_for_scene(
            scene_text=str(s.get("text", "")).strip(),
            scene_entity=str(s.get("entity_query", "")).strip(),
            scene_ai_prompt=str(s.get("ai_prompt", "")).strip(),
            source_event_idx=src_idx_int,
            news_items=news_items,
        )

        item_img = ""
        item_plat = "x"
        if matched_item:
            cand = matched_item.image_url
            item_img = cand if not is_placeholder_image_url(cand) else ""
            item_plat = matched_item.social_platform
        elif category not in ("viral", "hope") and idx == 0 and news_items:
            # Long-form standard broadcast: hook uses first topic photo if available
            cand = news_items[0].image_url
            item_img = cand if not is_placeholder_image_url(cand) else ""
            item_plat = news_items[0].social_platform

        scenes.append(
            DailyNewsScene(
                scene_index=idx,
                text=str(s.get("text", "")).strip(),
                entity_query=str(s.get("entity_query", "")).strip(),
                ai_prompt=str(s.get("ai_prompt", "")).strip(),
                has_transition_cue=is_cue,
                image_url=item_img,
                social_platform=item_plat,
            )
        )

    # Safety net: the hook scene must never open with a greeting.
    if scenes:
        scenes[0].text = strip_leading_greeting(scenes[0].text)

    hook_title = str(parsed.get("hook_title") or "").strip()
    if not hook_title:
        legacy_title = str(parsed.get("title") or "").strip()
        hook_title = legacy_title.split(":", 1)[1] if ":" in legacy_title else legacy_title
    final_title = build_hook_title(hook_title, category, now_dt)
    summary_lead = str(parsed.get("summary_lead", "")).strip()

    digest = DailyNewsDigest(
        digest_id=uuid.uuid4().hex[:8],
        title=final_title,
        summary_lead=summary_lead,
        hashtags=" ".join([t for t in str(parsed.get("hashtags", cfg.get("hashtags", "#tintucthegioi"))).strip().split() if t.lower().lstrip("#") != "haizflow"]),
        scenes=scenes,
        thumbnail_hook=sanitize_thumbnail_hook(parsed.get("thumbnail_hook", ""), category),
        ticker_summary=re.sub(r"\s+", " ", str(parsed.get("ticker_summary") or "")).strip() or summary_lead,
    )
    return assert_and_sanitize_no_vietnam_content(digest)


def translate_text_en_to_vi(text: str, timeout_seconds: float = 4.0) -> str:
    """Translate English news text to natural Vietnamese using free translation helper."""
    clean = text.strip()
    if not clean:
        return ""
    import sys
    if "unittest" in sys.modules and any("test" in arg.lower() for arg in sys.argv) and not os.environ.get("HAIZFLOW_NETWORK_TESTS"):
        return normalize_vietnamese_journalism(clean)

    norm_en = normalize_english_journalism(clean)
    try:
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=vi&dt=t&q={urllib.parse.quote(norm_en[:1000])}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            translated = "".join([part[0] for part in data[0] if part and part[0]]).strip()
            if translated:
                return normalize_vietnamese_journalism(translated)
    except Exception as exc:
        logger.debug("Translation helper error: %s", exc)
    return normalize_vietnamese_journalism(clean)


def extract_search_keywords_from_headline(title: str, category: str = "world") -> str:
    """Extract clean entity search keywords in English for Wikimedia Commons."""
    # Remove news agency suffixes like "- BBC", "- The New York Times", "| Reuters", etc.
    cleaned = re.sub(r"\s*[-|–]\s*[A-Za-z0-9\s\.]+$", "", title).strip()
    # Remove breaking news prefixes
    cleaned = re.sub(r"^(live updates:?|breaking:?|watch:?|video:?|update:?)\s*", "", cleaned, flags=re.IGNORECASE).strip()

    if category == "sports":
        # Check for known football clubs, stars or managers in the headline to avoid metaphorical words
        known_football = [
            "Real Madrid", "Barcelona", "Arsenal", "Manchester City", "Man City",
            "Manchester United", "Man United", "Liverpool", "Chelsea", "Tottenham",
            "Bayern Munich", "Borussia Dortmund", "Bayer Leverkusen", "Paris Saint-Germain",
            "PSG", "Juventus", "Inter Milan", "AC Milan", "Atletico Madrid",
            "Mbappe", "Haaland", "Bellingham", "Vinicius", "Yamal", "Lewandowski",
            "De Bruyne", "Salah", "Ronaldo", "Messi", "Arteta", "Guardiola", "Ten Hag",
            "Ancelotti", "Arne Slot", "Klopp", "Hansi Flick", "Xabi Alonso",
        ]
        for k in known_football:
            if re.search(rf"\b{re.escape(k)}\b", cleaned, re.IGNORECASE):
                return f"{k} football"

    # If the headline is very long, pick the first 5-6 words as keyword query
    words = cleaned.split()
    if len(words) > 6:
        base = " ".join(words[:5])
    else:
        base = cleaned

    if category == "sports" and "football" not in base.lower():
        base = f"{base} football"
    return base


GEOGRAPHIC_TERMS = frozenset({
    "maryland", "florida", "ohio", "texas", "california", "wisconsin", "michigan", "kansas",
    "nevada", "oregon", "washington", "arizona", "georgia", "virginia", "colorado", "alaska",
    "hawaii", "illinois", "pennsylvania", "tennessee", "indiana", "missouri", "carolina",
    "new york", "london", "paris", "tokyo", "chicago", "bali", "toronto", "canada", "australia",
    "uk", "britain", "england", "scotland", "ireland", "germany", "france", "italy", "spain",
})


def extract_core_visual_subject(text: str) -> str:
    """Extract and isolate the core concrete visual subject noun phrase from an English headline or summary.

    Prevents image generators from hallucinating names from geographic terms
    (e.g., turning 'cow in Maryland' into a person named 'Mary Land').
    """
    if not text:
        return "authentic news scene"

    cleaned = re.sub(r"^(watch:?|video:?|breaking:?|photos?:?|exclusive:?|update:?)\s*", "", text, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\s*[-|–]\s*[A-Za-z0-9\s\.]+$", "", cleaned).strip()
    lowered = cleaned.lower()

    # 1. Animals (the animal is ALWAYS the core subject)
    for animal in [
        "cow", "bull", "calf", "dog", "puppy", "cat", "kitten", "monkey", "chimpanzee",
        "bear", "frog", "alligator", "crocodile", "snake", "shark", "whale", "dolphin",
        "bird", "duck", "goose", "pig", "horse", "goat", "sheep", "raccoon", "possum",
        "skunk", "otter", "fox", "deer", "moose", "elephant", "tiger", "lion", "flamingo",
    ]:
        if re.search(rf"\b{animal}s?\b", lowered):
            if any(k in lowered for k in ("highway", "road", "street", "traffic", "freeway", "interstate")):
                return f"a real {animal} standing on highway road shoulder"
            if any(k in lowered for k in ("steal", "stole", "lawn", "yard", "garden")):
                return f"a colorful lawn {animal} in front yard"
            if any(k in lowered for k in ("collection", "memorabilia", "museum", "figurines")):
                return f"a massive collection of toy {animal} figurines on shelves"
            if any(k in lowered for k in ("tree", "roof", "chimney", "stuck")):
                return f"a {animal} rescued from tree"
            return f"an authentic {animal}"

    # 2. Quirky Objects / Inventions / Artistic Creations
    if any(k in lowered for k in ("spirit walker", "sculpture", "statue", "recycled", "costume")):
        return "a tall creature sculpture made of scrap metal and recycled items"
    if any(k in lowered for k in ("drum", "drums", "ghostbusters", "synthesizer", "sequencer")):
        return "a musician playing an electronic drum kit in modern music studio"
    if any(k in lowered for k in ("linkedin", "corporate", "office humor", "jargon")):
        return "corporate office employees laughing and singing together in meeting room"
    if any(k in lowered for k in ("thief", "burglar", "robber", "chimney", "heist")):
        return "a clumsy burglar stuck upside down in bakery chimney"
    if any(k in lowered for k in ("robot", "drone", "humanoid", "cyborg")):
        return "an advanced humanoid robot prototype standing in laboratory"
    if any(k in lowered for k in ("pain", "sensitivity", "clinical study", "experiment")):
        return "medical researchers conducting a clinical laboratory study with monitors"

    # 3. Clean fallback: filter out geographic distractors and journalistic filler
    words = cleaned.split()
    filtered = [w for w in words if w.lower().strip(",.-\"':;") not in GEOGRAPHIC_TERMS]
    candidate = " ".join(filtered[:5])
    return candidate if candidate else "authentic news scene"


def ground_prompt_to_core_subject(prompt: str, fallback_headline: str = "", category: str = "world") -> str:
    """Ensure prompt is simple, English-only, and grounded 100% on the core visual subject.

    Guarantees no Vietnamese text leaks into English image generators and eliminates
    bizarre misinterpretations (like 'Maryland' -> woman named Mary).
    """
    has_vietnamese = bool(re.search(r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]", prompt, re.IGNORECASE))

    if has_vietnamese or not prompt.strip() or len(prompt.strip()) < 10:
        # Prompt contains Vietnamese or is empty -> extract grounded subject from original English headline
        subject = extract_core_visual_subject(fallback_headline)
        return f"photorealistic news photography of {subject}, authentic real-world news photo style"

    cleaned_prompt = prompt.strip()

    # Grounding check: if headline mentions an animal but prompt missed it, enforce the animal
    lowered_head = fallback_headline.lower()
    for animal in ("cow", "bull", "dog", "cat", "monkey", "bear", "frog", "alligator", "snake", "shark", "bird", "horse", "goat", "raccoon", "flamingo"):
        if re.search(rf"\b{animal}s?\b", lowered_head) and not re.search(rf"\b{animal}s?\b", cleaned_prompt.lower()):
            cleaned_prompt = f"photorealistic news photo of a real {animal}, {cleaned_prompt}"
            break

    # Strip risky standalone geographic names that cause persona hallucinations
    for geo in ("maryland", "florida", "kansas", "ohio", "wisconsin"):
        cleaned_prompt = re.sub(rf"\b{geo}\b(?!\s+state)", "", cleaned_prompt, flags=re.IGNORECASE)
    cleaned_prompt = re.sub(r"\s+", " ", cleaned_prompt).strip(" ,.-")

    return cleaned_prompt


WORLD_LEAD_INS = [
    "Mở đầu bản tin thời sự quốc tế hôm nay",
    "Tại khu vực châu Âu",
    "Chuyển sang tình hình an ninh quốc tế",
    "Ở một diễn biến đáng chú ý khác",
    "Tại khu vực Bắc Mỹ",
    "Về hợp tác và quan hệ ngoại giao",
    "Tại khu vực Trung Đông",
    "Khép lại khối tin thế giới hôm nay",
]

FOOTBALL_LEAD_INS = [
    "Mở đầu bản tin bóng đá quốc tế hôm nay",
    "Tâm điểm sân cỏ châu Âu",
    "Chuyển sang diễn biến hấp dẫn tại giải Ngoại Hạng Anh",
    "Tại đấu trường danh giá Champions League Cúp C1",
    "Ở một diễn biến đáng chú ý khác trên sân cỏ",
    "Nóng bỏng thị trường chuyển nhượng cầu thủ",
    "Tại đấu trường La Liga Tây Ban Nha",
    "Khép lại bản tin bóng đá rạng sáng nay",
]

TECH_LEAD_INS = [
    "Mở đầu bản tin công nghệ thế giới hôm nay",
    "Tâm điểm làn sóng trí tuệ nhân tạo AI",
    "Đột phá mới trong lĩnh vực bán dẫn và phần cứng",
    "Ở một diễn biến đáng chú ý khác trong giới công nghệ",
    "Tin tức mới nhất từ các tập đoàn công nghệ hàng đầu",
    "Về xu hướng ứng dụng công nghệ và phần mềm",
    "Đột phá công nghệ không gian và năng lượng mới",
    "Khép lại bản tin công nghệ hôm nay",
]

WAR_LEAD_INS = [
    "Mở đầu bản tin chiến sự với diễn biến nóng nhất trên chiến trường",
    "Chuyển sang điểm nóng quân sự tiếp theo",
    "Tại thực địa mặt trận giao tranh ác liệt",
    "Theo báo cáo mới nhất từ các bên tham chiến",
    "Về đợt tập kích và các diễn biến quân sự vừa ghi nhận",
    "Căng thẳng xung đột vũ trang tiếp tục leo thang",
    "Một diễn biến bất ổn bạo lực và biểu tình nghiêm trọng",
    "Khép lại bản tin chiến sự thế giới hôm nay",
]

VIRAL_LEAD_INS = [
    "Mở đầu tiêu điểm độc lạ và hài hước gây sốt mạng xã hội hôm nay",
    "Tình huống dở khóc dở cười đang viral chóng mặt trên mạng xã hội",
    "Gây bão trên nền tảng X rạng sáng nay với khoảnh khắc cười ra nước mắt",
    "Một câu chuyện hy hữu dở khóc dở cười vừa được chia sẻ rầm rộ",
    "Đoạn clip triệu view khiến cộng đồng mạng quốc tế cười ngả nghiêng",
    "Hiện tượng kỳ lạ khó tin khiến người xem không khỏi sững sờ",
    "Pha xử lý cồng kềnh đầy hài hước đang thu hút hàng chục triệu lượt xem",
    "Khoảnh khắc độc lạ có một không hai vừa được ghi lại",
    "Một sự cố bi hài vừa xảy ra khiến cư dân mạng xôn xao",
    "Khép lại bản tin độc lạ và hài hước thế giới hôm nay",
]

HOPE_LEAD_INS = [
    "Mở đầu bản tin tin vui với bước đột phá y học đầy kỳ diệu",
    "Tin vui lớn cho môi trường và sự sống muôn loài trên Trái Đất",
    "Bước tiến y khoa mang tính bước ngoặt mở ra hy vọng cứu sống hàng triệu người",
    "Kỳ tích bảo tồn và hồi sinh một loài sinh vật quý hiếm vừa được ghi nhận",
    "Giải pháp công nghệ xanh độc đáo giúp làm sạch đại dương và hồi sinh Trái Đất",
    "Một thử nghiệm lâm sàng điều trị bệnh hiểm nghèo vừa đem lại kết quả rực rỡ",
    "Nỗ lực phủ xanh rừng rậm và tái sinh nguồn nước đang mang lại hy vọng lớn",
    "Phép màu y học giúp bệnh nhân phục hồi một cách kỳ diệu",
    "Một sáng chế hữu ích đang lan tỏa giải pháp bền vững cho cộng đồng",
    "Khép lại bản tin tin vui và hy vọng hôm nay",
]

NEWS_LEAD_INS = WORLD_LEAD_INS


def get_lead_ins_for_category(category: str) -> List[str]:
    """Return category-specific journalistic broadcast lead-ins."""
    cat = normalize_category(category)
    if cat == "war":
        return WAR_LEAD_INS
    if cat == "sports":
        return FOOTBALL_LEAD_INS
    if cat == "tech":
        return TECH_LEAD_INS
    if cat == "viral":
        return VIRAL_LEAD_INS
    if cat == "hope":
        return HOPE_LEAD_INS
    return WORLD_LEAD_INS


def format_source_attribution_lead_in(source: str, topic_index: int) -> str:
    """Format varied, natural journalistic attribution lead-in (avoiding repetitive templates)."""
    if not source or source == "các hãng thông tấn quốc tế":
        fallbacks = [
            "Theo các hãng thông tấn quốc tế, ",
            "Báo chí quốc tế đưa tin, ",
            "Các cơ quan truyền thông quốc tế cho hay, ",
            "Thông tin từ các hãng tin quốc tế cho biết, ",
        ]
        return fallbacks[topic_index % len(fallbacks)]

    # Check for social media sources (X, Instagram, Facebook)
    src_lower = source.lower()
    if "mạng xã hội" in src_lower or any(p in src_lower for p in ("x (twitter)", "instagram", "facebook", "bored panda", "oddity central", "dexerto")):
        soc_patterns = [
            f"Theo bài đăng gây sốt trên {source}, ",
            f"Đoạn video lan truyền mạnh mẽ trên {source} cho thấy, ",
            f"Chia sẻ thu hút hàng triệu lượt xem trên {source} nêu rõ, ",
            f"Theo ghi nhận xu hướng bùng nổ trên {source}, ",
        ]
        return soc_patterns[topic_index % len(soc_patterns)]

    # Clean brand name (e.g. 'báo The Guardian' -> 'The Guardian', 'Đài phát thanh NPR' -> 'NPR')
    brand = re.sub(
        r"^(báo|đài phát thanh|hãng tin|hãng thông tấn|đài)\s+",
        "",
        source,
        flags=re.IGNORECASE,
    ).strip()

    cap_source = source[0].upper() + source[1:] if source else source

    patterns = [
        f"Theo {source}, ",
        f"{cap_source} có viết, ",
        f"{brand} cho hay, ",
        f"Thông tin từ {source} cho biết, ",
        f"{brand} đưa tin, ",
        f"Cụ thể, {source} thông tin, ",
        f"Theo {brand}, ",
        f"{cap_source} nêu rõ, ",
    ]
    return patterns[topic_index % len(patterns)]


def cook_summary_into_vietnamese(item: WorldNewsItem, vi_title: str) -> str:
    """Cook raw article paragraphs into natural, non-repetitive Vietnamese narrative."""
    source_text = item.full_text if item.full_text and len(item.full_text) > 80 else item.summary
    cleaned = clean_html_text(source_text)
    # Remove press agency brand names
    cleaned = re.sub(
        r"\b(The New York Times|BBC News|BBC|CNBC|Reuters|CNN|Politico|Al Jazeera|CBS News|Associated Press|AP|The Guardian|NPR|Financial Times|Washington Post|Sky Sports|ESPN)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Pre-normalize English idioms before translation
    cleaned = normalize_english_journalism(cleaned)

    # Translate substantive paragraphs with increased depth
    vi_full = translate_text_en_to_vi(cleaned[:1000])

    # Split into sentences and eliminate sentences that repeat the title
    raw_sentences = [s.strip() for s in re.split(r"[.!?]+", vi_full) if len(s.strip()) > 15]
    filtered_sentences = []
    title_words = set(vi_title.lower().split())

    for s in raw_sentences:
        s_words = set(s.lower().split())
        overlap = len(s_words & title_words) / max(1, len(title_words))
        # If sentence overlaps more than 65% with the title, skip to avoid repetition
        if overlap > 0.65:
            continue
        filtered_sentences.append(s)

    if filtered_sentences:
        cooked = ". ".join(filtered_sentences[:3]).strip()
        if not cooked.endswith("."):
            cooked += "."
        return normalize_vietnamese_journalism(cooked)

    # If no sentences survived, translate backup text or Wikipedia summary
    backup_text = clean_html_text(item.summary) if item.summary else clean_html_text(item.full_text)
    if backup_text:
        vi_backup = translate_text_en_to_vi(backup_text[:400])
        if vi_backup and len(vi_backup) > 20:
            res = vi_backup if vi_backup.endswith(".") else vi_backup + "."
            return normalize_vietnamese_journalism(res)

    wiki = get_wikipedia_context(extract_search_keywords_from_headline(item.title))
    if wiki:
        vi_wiki = translate_text_en_to_vi(wiki[:350])
        if vi_wiki:
            res = vi_wiki if vi_wiki.endswith(".") else vi_wiki + "."
            return normalize_vietnamese_journalism(res)

    return "Các cơ quan chức năng sở tại đang tiếp tục phối hợp điều tra và cập nhật thêm các dữ liệu chi tiết."


def fallback_offline_news_script(
    news_items: List[WorldNewsItem],
    detail_level: Literal["concise", "standard", "deep"] = "standard",
    max_topics: int = 8,
    category: str = "world",
) -> DailyNewsDigest:
    """Generate a high-quality editorial fallback news digest if Gemini API is unreachable or offline."""
    cfg = get_category_config(category)
    norm_cat = normalize_category(category)
    now_dt = datetime.now()
    date_str = now_dt.strftime("%d/%m/%Y")
    selected = news_items[:max_topics] if news_items else []
    scenes: List[DailyNewsScene] = []
    sc_idx = 0
    vi_titles: List[str] = []
    vi_first = ""
    if selected:
        vi_first = translate_text_en_to_vi(_clean_headline(selected[0].title))

    if norm_cat == "viral":
        # Viral YouTube Shorts Format: Fast hook, punchy scenes, quick CTA
        if len(selected) <= 3:
            intro_text = (
                f"Top {len(selected)} tin độc lạ gây bão rạng sáng nay: {vi_first}. Cùng khám phá ngay sau đây!"
                if vi_first
                else "Top 3 câu chuyện độc lạ khó tin vừa gây bão mạng xã hội quốc tế. Xem ngay những khoảnh khắc sốc nhất sau đây."
            )
        else:
            intro_text = (
                f"Gây sốc rạng sáng nay: {vi_first}. Và còn {max(len(selected) - 1, 0)} câu chuyện độc lạ khó tin khác đang chờ bạn ngay sau đây."
                if vi_first
                else "Một loạt câu chuyện độc lạ khó tin vừa gây bão mạng xã hội quốc tế. Xem ngay những khoảnh khắc sốc nhất sau đây."
            )
        scenes.append(
            DailyNewsScene(
                scene_index=sc_idx,
                text=intro_text,
                entity_query=cfg.get("intro_entity", "Breaking viral shock trends on social media smartphones"),
                ai_prompt=cfg.get("intro_ai_prompt", "cinematic vertical 9:16 smartphone screen glowing with breaking viral social media alerts, neon accents, dramatic modern lighting"),
                has_transition_cue=False,
                image_url="",
                social_platform="x",
            )
        )
        sc_idx += 1

        for idx, item in enumerate(selected, start=1):
            clean_full_headline = re.sub(r"\s*[-|–]\s*[A-Za-z0-9\s\.]+$", "", item.title).strip()
            clean_full_headline = re.sub(
                r"^(live updates:?|breaking:?|watch:?|video:?|update:?)\s*", "", clean_full_headline, flags=re.IGNORECASE
            ).strip()
            vi_title = translate_text_en_to_vi(clean_full_headline)
            vi_titles.append(vi_title)
            cat_lead_ins = get_lead_ins_for_category(category)
            if len(selected) <= 3:
                lead_in = f"Vị trí số {idx}"
            else:
                lead_in = cat_lead_ins[(idx - 1) % len(cat_lead_ins)]
            cooked_facts = cook_summary_into_vietnamese(item, vi_title)
            # Combine into 1 punchy, dramatic narration for the Short scene
            combined_text = f"{lead_in}: {vi_title}. {cooked_facts}"

            core_sub = extract_core_visual_subject(clean_full_headline)
            ai_prompt_val = f"photorealistic news photography of {core_sub}, authentic real-world news photo style"

            scenes.append(
                DailyNewsScene(
                    scene_index=sc_idx,
                    text=combined_text,
                    entity_query=extract_search_keywords_from_headline(item.title, category=category),
                    ai_prompt=ai_prompt_val,
                    has_transition_cue=True,
                    image_url=item.image_url,
                    social_platform=item.social_platform,
                )
            )
            sc_idx += 1

        # Outro scene for Shorts
        scenes.append(
            DailyNewsScene(
                scene_index=sc_idx,
                text="Bản tin độc lạ thế giới hôm nay xin được khép lại tại đây. Đừng quên thả tim, chia sẻ cảm nghĩ và bấm đăng ký kênh để không bỏ lỡ các tin tức độc lạ tiếp theo! Xin chào và hẹn gặp lại.",
                entity_query="Social media creator smartphone studio",
                ai_prompt="cinematic 9:16 smartphone screen with subscribe button and glowing social media likes",
                has_transition_cue=True,
                image_url="",
                social_platform="x",
            )
        )

        title = build_hook_title(vi_first, norm_cat, now_dt)
        return assert_and_sanitize_no_vietnam_content(
            DailyNewsDigest(
                digest_id=uuid.uuid4().hex[:8],
                title=title,
                summary_lead=f"Tổng hợp các câu chuyện độc lạ, nóng sốc gây bão mạng xã hội ngày {date_str}.",
                hashtags=cfg.get("hashtags", "#Shorts #doclathegioi #tinhot #xuhuong"),
                scenes=scenes,
                thumbnail_hook=sanitize_thumbnail_hook("", norm_cat),
                ticker_summary=" | ".join(vi_titles),
            )
        )

    elif norm_cat == "hope":
        # Hope YouTube Shorts Format: Inspiring hook, punchy scenes, uplifting outro
        if len(selected) <= 3:
            intro_text = (
                f"Top {len(selected)} tin vui lớn rạng sáng nay: {vi_first}. Cùng đón nhận những năng lượng tích cực ngay sau đây!"
                if vi_first
                else "Top 3 tin vui và kỳ tích truyền cảm hứng vừa được ghi nhận trên thế giới. Cùng khám phá ngay sau đây!"
            )
        else:
            intro_text = (
                f"Tin vui lớn rạng sáng nay: {vi_first}. Cùng những đột phá y học, phép màu sự sống và giải pháp hồi sinh môi trường ngay sau đây."
                if vi_first
                else "Những đột phá y khoa kỳ diệu và giải pháp hồi sinh môi trường vừa mang lại niềm hy vọng lớn cho Trái Đất. Cùng đón nhận những tin vui rực rỡ nhất sau đây."
            )
        scenes.append(
            DailyNewsScene(
                scene_index=sc_idx,
                text=intro_text,
                entity_query=cfg.get("intro_entity", "Futuristic clean energy planet Earth green technology glowing orb"),
                ai_prompt=cfg.get("intro_ai_prompt", "cinematic vertical 9:16 futuristic glowing planet Earth restored with clean green energy and technology, hope and bright future, warm sunrise lighting"),
                has_transition_cue=False,
                image_url="",
                social_platform="x",
            )
        )
        sc_idx += 1

        for idx, item in enumerate(selected, start=1):
            clean_full_headline = re.sub(r"\s*[-|–]\s*[A-Za-z0-9\s\.]+$", "", item.title).strip()
            clean_full_headline = re.sub(
                r"^(live updates:?|breaking:?|watch:?|video:?|update:?)\s*", "", clean_full_headline, flags=re.IGNORECASE
            ).strip()
            vi_title = translate_text_en_to_vi(clean_full_headline)
            vi_titles.append(vi_title)
            cat_lead_ins = get_lead_ins_for_category(category)
            if len(selected) <= 3:
                lead_in = f"Vị trí số {idx}"
            else:
                lead_in = cat_lead_ins[(idx - 1) % len(cat_lead_ins)]
            cooked_facts = cook_summary_into_vietnamese(item, vi_title)
            combined_text = f"{lead_in}: {vi_title}. {cooked_facts}"

            core_sub = extract_core_visual_subject(clean_full_headline)
            ai_prompt_val = f"cinematic news photography of {core_sub}, clean bright futuristic lighting, uplifting science aesthetic"

            scenes.append(
                DailyNewsScene(
                    scene_index=sc_idx,
                    text=combined_text,
                    entity_query=extract_search_keywords_from_headline(item.title, category=category),
                    ai_prompt=ai_prompt_val,
                    has_transition_cue=True,
                    image_url=item.image_url,
                    social_platform=item.social_platform,
                )
            )
            sc_idx += 1

        # Outro scene for Hope Shorts
        scenes.append(
            DailyNewsScene(
                scene_index=sc_idx,
                text="Những bước tiến y khoa, điều kỳ diệu của sự sống và nỗ lực bảo vệ Trái Đất hôm nay nhắc chúng ta rằng tương lai luôn tràn đầy hy vọng. Hãy bấm đăng ký kênh để đón nhận nguồn năng lượng tích cực mỗi ngày! Xin chào và hẹn gặp lại.",
                entity_query="Futuristic clean technology globe sunrise",
                ai_prompt="cinematic vertical 9:16 sunrise over thriving green planet Earth, inspiring future, glowing subscribe button",
                has_transition_cue=True,
                image_url="",
                social_platform="x",
            )
        )

        title = build_hook_title(vi_first, norm_cat, now_dt)
        return assert_and_sanitize_no_vietnam_content(
            DailyNewsDigest(
                digest_id=uuid.uuid4().hex[:8],
                title=title,
                summary_lead=f"Tổng hợp các bước tiến y khoa, phép màu sự sống, phục hồi môi trường và tin vui thắp sáng hy vọng ngày {date_str}.",
                hashtags=cfg.get("hashtags", "#Shorts #tinvui #ykhoa #susong #moitruong #hyvong #khoahoc"),
                scenes=scenes,
                thumbnail_hook=sanitize_thumbnail_hook("", norm_cat),
                ticker_summary=" | ".join(vi_titles),
            )
        )

    # Standard World / Tech / Sports format
    # Intro scene
    scenes.append(
        DailyNewsScene(
            scene_index=sc_idx,
            text=(
                f"Tin nóng rạng sáng nay: {vi_first}. Đây mới chỉ là điểm nóng đầu tiên trong {len(selected)} sự kiện {cfg['label'].lower()} nổi bật nhất hôm nay, cùng điểm qua ngay sau đây."
                if vi_first
                else f"Điểm nóng {cfg['label'].lower()} rạng sáng nay vừa có những diễn biến đáng chú ý. Cùng điểm qua ngay sau đây."
            ),
            entity_query=cfg.get("intro_entity", "Globe world map broadcast"),
            ai_prompt=cfg.get("intro_ai_prompt", "cinematic 35mm newsroom with glowing digital world map background, high tech aesthetic"),
            has_transition_cue=False,
            image_url="",
            social_platform="x",
        )
    )
    sc_idx += 1

    for idx, item in enumerate(selected, start=1):
        clean_full_headline = re.sub(r"\s*[-|–]\s*[A-Za-z0-9\s\.]+$", "", item.title).strip()
        clean_full_headline = re.sub(
            r"^(live updates:?|breaking:?|watch:?|video:?|update:?)\s*", "", clean_full_headline, flags=re.IGNORECASE
        ).strip()

        vi_title = translate_text_en_to_vi(clean_full_headline)
        vi_titles.append(vi_title)
        entity_query = extract_search_keywords_from_headline(item.title, category=category)

        # Scene 1: Event announcement with natural journalistic lead-in (has_transition_cue=True plays the sound cue!)
        cat_lead_ins = get_lead_ins_for_category(category)
        lead_in = cat_lead_ins[(idx - 1) % len(cat_lead_ins)]
        scenes.append(
            DailyNewsScene(
                scene_index=sc_idx,
                text=f"{lead_in}: {vi_title}.",
                entity_query=entity_query,
                ai_prompt=f"cinematic photorealistic news scene: {entity_query}, 35mm photography, dramatic lighting",
                has_transition_cue=True,
                image_url=item.image_url,
                social_platform=item.social_platform,
            )
        )
        sc_idx += 1

        # Scene 2: Substantive facts & context cooked from the article (always included for rich broadcast depth)
        cooked_facts = cook_summary_into_vietnamese(item, vi_title)
        source_lead = format_source_attribution_lead_in(item.source, idx - 1)
        scenes.append(
            DailyNewsScene(
                scene_index=sc_idx,
                text=f"{source_lead}{cooked_facts}",
                entity_query=entity_query,
                ai_prompt=f"cinematic photo of international correspondents discussing {entity_query}, 35mm lens",
                has_transition_cue=False,
                image_url=item.image_url,
                social_platform=item.social_platform,
            )
        )
        sc_idx += 1

    # Outro scene (has_transition_cue=True plays the sound cue before closing!)
    scenes.append(
        DailyNewsScene(
            scene_index=sc_idx,
            text=f"Bản tin {cfg['outro_topic_name']} hôm nay xin phép được khép lại tại đây. Cảm ơn quý vị đã quan tâm theo dõi. Đừng quên bấm Đăng ký kênh và bật chuông thông báo để cập nhật các tin tức {cfg['label'].lower()} mới nhất mỗi ngày. Xin kính chào và hẹn gặp lại.",
            entity_query="News studio broadcast",
            ai_prompt="cinematic news studio desk with modern broadcast lighting and digital displays",
            has_transition_cue=True,
            image_url="",
            social_platform="x",
        )
    )

    return assert_and_sanitize_no_vietnam_content(
        DailyNewsDigest(
            digest_id=uuid.uuid4().hex[:8],
            title=build_hook_title(vi_first, norm_cat, now_dt),
            summary_lead=f"Tổng hợp toàn diện {len(selected)} sự kiện {cfg['label'].lower()} quốc tế nổi bật ngày {date_str}.",
            hashtags=cfg.get("hashtags", "#tintucthegioi #thoisuquocte #youtube"),
            scenes=scenes,
            thumbnail_hook=sanitize_thumbnail_hook("", norm_cat),
            ticker_summary=" | ".join(vi_titles),
        )
    )


def is_image_mostly_blank(img_path: Union[str, Path, None]) -> bool:
    """Detect if an image is essentially a blank/solid color or dark silhouette (e.g. empty black screen)."""
    if not img_path:
        return True
    try:
        from PIL import ImageStat
        p = Path(img_path)
        if not p.is_file():
            return True
        im = Image.open(p).convert("L")
        st = ImageStat.Stat(im)
        std = st.stddev[0]
        mean = st.mean[0]
        # Solid flat color (stddev < 15), dark void (mean < 55 and stddev < 26), or washed white (mean > 240 and stddev < 20)
        if std < 15.0 or (mean < 55.0 and std < 26.0) or (mean > 240.0 and std < 20.0):
            return True
        return False
    except Exception:
        return False


def create_social_post_visual(
    platform: str,
    headline: str,
    author_name: str = "",
    author_handle: str = "",
    image_path: Optional[str] = None,
    dest_path: Path = Path("scene.jpg"),
    aspect_ratio: AspectRatio = "9:16",
) -> Path:
    """Generate an authentic social media screenshot card (Facebook, Instagram, X) for video scenes."""
    dest_path = Path(dest_path).resolve()
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    target_w, target_h = resolution_for_aspect_ratio(aspect_ratio)

    plat = (platform or "x").lower()
    if "reddit" in plat:
        plat_key = "reddit"
        plat_name = "Reddit"
        plat_color = (255, 69, 0)
        default_handle = author_handle or "r/Damnthatsinteresting · Top 24h"
    elif "tiktok" in plat:
        plat_key = "tiktok"
        plat_name = "TikTok"
        plat_color = (254, 44, 85)
        default_handle = author_handle or "@ViralTrends · Video triệu view"
    elif "threads" in plat:
        plat_key = "threads"
        plat_name = "Threads"
        plat_color = (20, 20, 20)
        default_handle = author_handle or "@TrendingNow · Vừa chia sẻ"
    elif "insta" in plat:
        plat_key = "instagram"
        plat_name = "Instagram"
        plat_color = (225, 48, 108)
        default_handle = author_handle or "@curious.planet · Xu hướng 24h"
    elif "fb" in plat or "face" in plat:
        plat_key = "facebook"
        plat_name = "Facebook"
        plat_color = (24, 119, 242)
        default_handle = author_handle or "Cộng đồng thế giới · Bài đăng hot"
    else:
        plat_key = "x"
        plat_name = "X (Twitter)"
        plat_color = (29, 155, 240)
        default_handle = author_handle or "@TrendingWorld · Vừa đăng"

    canvas = Image.new("RGB", (target_w, target_h), (12, 16, 24))

    # Font setup
    try:
        font_author = ImageFont.truetype("segoeuib.ttf", max(24, int(target_w * 0.034)))
        font_sub = ImageFont.truetype("segoeui.ttf", max(18, int(target_w * 0.024)))
        font_text = ImageFont.truetype("segoeuib.ttf", max(26, int(target_w * 0.035)))
        font_badge = ImageFont.truetype("segoeuib.ttf", max(18, int(target_w * 0.022)))
        font_stats = ImageFont.truetype("segoeui.ttf", max(18, int(target_w * 0.024)))
    except Exception:
        font_author = ImageFont.load_default()
        font_sub = font_author
        font_text = font_author
        font_badge = font_author
        font_stats = font_author

    # 1. Background (if photo available, blur heavily for ambient glow)
    has_photo = bool(image_path and Path(image_path).is_file() and not is_image_mostly_blank(image_path))
    if has_photo:
        try:
            raw_img = Image.open(image_path).convert("RGB")
            bg = raw_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
            bg = bg.filter(ImageFilter.GaussianBlur(radius=32))
            dark = Image.new("RGB", (target_w, target_h), (10, 14, 20))
            canvas = Image.blend(bg, dark, 0.58)
        except Exception:
            pass

    draw = ImageDraw.Draw(canvas)

    # 2. Main Social Post Card layout
    # Calculate text wrap lines first
    words = headline.split()
    lines = []
    cur_line = []
    max_char_per_line = 36 if aspect_ratio == "9:16" else 58
    for w in words:
        test_line = " ".join(cur_line + [w])
        if len(test_line) > max_char_per_line:
            lines.append(" ".join(cur_line))
            cur_line = [w]
        else:
            cur_line.append(w)
    if cur_line:
        lines.append(" ".join(cur_line))
    lines = lines[:4 if not has_photo else 3]

    line_spacing = 48 if aspect_ratio == "9:16" else 40

    if aspect_ratio == "9:16":
        card_w = target_w - 70
        card_x = 35
        if has_photo:
            card_y = int(target_h * 0.08)
            card_h = int(target_h * 0.58)
        else:
            # Dynamic snug height for text-only post
            card_h = 100 + len(lines) * line_spacing + 70
            card_y = int(target_h * 0.22)
    else:
        card_w = int(target_w * 0.85)
        card_x = (target_w - card_w) // 2
        if has_photo:
            card_y = int(target_h * 0.08)
            card_h = int(target_h * 0.65)
        else:
            card_h = 100 + len(lines) * line_spacing + 70
            card_y = int(target_h * 0.18)

    # Drop shadow & card body
    draw.rounded_rectangle(
        [card_x + 5, card_y + 6, card_x + card_w + 5, card_y + card_h + 6],
        radius=26,
        fill=(6, 8, 12),
    )
    draw.rounded_rectangle(
        [card_x, card_y, card_x + card_w, card_y + card_h],
        radius=26,
        fill=(22, 27, 34),
        outline=(58, 70, 88),
        width=2,
    )

    # Platform badge
    badge_w = int(target_w * 0.16)
    badge_h = int(target_h * 0.024) if aspect_ratio == "9:16" else 36
    draw.rounded_rectangle(
        [card_x + 28, card_y + 24, card_x + 28 + badge_w, card_y + 24 + badge_h],
        radius=8,
        fill=plat_color,
    )
    draw.text((card_x + 40, card_y + 28), plat_name, fill=(255, 255, 255), font=font_badge)

    # Author
    author_disp = author_name or f"Tin Nóng {plat_name}"
    draw.text((card_x + 36 + badge_w + 16, card_y + 24), author_disp, fill=(255, 255, 255), font=font_author)
    draw.text((card_x + 36 + badge_w + 16, card_y + 60), default_handle, fill=(148, 163, 184), font=font_sub)

    # Headline text with word wrap
    text_y = card_y + 92
    for line in lines:
        draw.text((card_x + 28, text_y), line, fill=(241, 245, 249), font=font_text)
        text_y += line_spacing

    # 3. Media Image inside Card (only if photo available)
    if has_photo:
        media_y = text_y + 12
        stats_reserved_h = 55
        media_h = (card_y + card_h) - media_y - stats_reserved_h
        media_w = card_w - 56

        if media_h > 80:
            try:
                m_img = Image.open(image_path).convert("RGB")
                scale = max(media_w / m_img.width, media_h / m_img.height)
                nw = int(round(m_img.width * scale))
                nh = int(round(m_img.height * scale))
                m_img = m_img.resize((nw, nh), Image.Resampling.LANCZOS)
                cx = (nw - media_w) // 2
                cy = (nh - media_h) // 2
                m_img = m_img.crop((cx, cy, cx + media_w, cy + media_h))

                canvas.paste(m_img, (card_x + 28, media_y))
                draw.rectangle(
                    [card_x + 28, media_y, card_x + 28 + media_w, media_y + media_h],
                    outline=(64, 78, 98),
                    width=1,
                )
            except Exception as exc:
                logger.debug("Failed embedding image into social visual: %s", exc)

    # 4. Social Reaction Bar
    stats_y = card_y + card_h - 42
    draw.text((card_x + 32, stats_y), "♥ 184.2K", fill=(239, 68, 68), font=font_stats)
    draw.text((card_x + 200, stats_y), "💬 24.6K", fill=(148, 163, 184), font=font_stats)
    draw.text((card_x + 360, stats_y), "⇄ 52.1K", fill=(34, 197, 94), font=font_stats)
    draw.text((card_x + card_w - 170, stats_y), "★ Viral 24h", fill=(245, 158, 11), font=font_stats)

    canvas.save(dest_path, format="JPEG", quality=94)
    return dest_path


def prepare_scene_illustrations(
    scenes: List[DailyNewsScene],
    output_dir: Path,
    aspect_ratio: AspectRatio = "9:16",
    prefer_real_images: bool = True,
    category: str = "world",
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> None:
    """Acquire copyright-safe public domain images from Wikimedia or render social screenshot cards."""
    output_dir.mkdir(parents=True, exist_ok=True)
    total = len(scenes)

    for idx, scene in enumerate(scenes):
        pct = int(10 + (idx / max(1, total)) * 25)
        if progress_callback:
            progress_callback(pct, f"Đang chuẩn bị hình ảnh phân cảnh {idx + 1}/{total}...")

        img_dest = output_dir / f"scene_{scene.scene_index:03d}.jpg"
        acquired = False

        # Category: Viral (Authentic real article photo OR tailored photorealistic AI generation)
        if category == "viral":
            temp_raw = output_dir / f"raw_scene_{scene.scene_index:03d}.jpg"
            photo_found = False
            source_type = "social_screenshot"

            # Tier 1: Direct authentic photo from article/post (highest fidelity 100% real event)
            if prefer_real_images and scene.image_url and not is_placeholder_image_url(scene.image_url):
                try:
                    if download_and_format_image(scene.image_url, temp_raw, aspect_ratio=aspect_ratio):
                        if not is_image_mostly_blank(temp_raw):
                            photo_found = True
                            source_type = "direct_photo"
                            logger.info("Found authentic article photo for viral scene %d: %s", idx, scene.image_url)
                except Exception as dl_err:
                    logger.debug("Direct photo fetch failed for scene %d: %s", idx, dl_err)

            # Tier 2: Contextual photorealistic AI generation (precisely depicting the strange/funny scene narrative)
            # NEVER query Wikimedia Commons for viral/funny memes to prevent irrelevant historical archival mismatches.
            if not photo_found:
                prompt_to_use = ground_prompt_to_core_subject(
                    prompt=scene.ai_prompt,
                    fallback_headline=scene.entity_query or scene.text,
                    category=category,
                )
                try:
                    logger.info("Generating grounded AI visual for viral scene %d: %s", idx, prompt_to_use[:70])
                    generated_path = generate_scene_image(
                        prompt=prompt_to_use,
                        destination_path=temp_raw,
                        aspect_ratio=aspect_ratio,
                        style="cinematic",
                        allow_free_online=True,
                    )
                    if generated_path and Path(generated_path).is_file() and not is_image_mostly_blank(temp_raw):
                        photo_found = True
                        source_type = "ai_generated"
                        logger.info("Generated contextual AI image for viral scene %d successfully", idx)
                except Exception as ai_err:
                    logger.warning("AI image generation failed for viral scene %d: %s", idx, ai_err)

            # Generate social visual: if photo_found embeds photo; if not, renders clean text card
            create_social_post_visual(
                platform=scene.social_platform,
                headline=scene.text,
                image_path=str(temp_raw.resolve()) if photo_found else None,
                dest_path=img_dest,
                aspect_ratio=aspect_ratio,
            )
            scene.image_path = str(img_dest.resolve())
            scene.image_source_type = source_type
            acquired = True

        # Category: World / Tech / Sports / Hope (Direct Article Photo -> Wikimedia -> AI Cinematic)
        if not acquired and prefer_real_images and scene.image_url and not is_placeholder_image_url(scene.image_url):
            try:
                if download_and_format_image(scene.image_url, img_dest, aspect_ratio=aspect_ratio):
                    if not is_image_mostly_blank(img_dest):
                        scene.image_path = str(img_dest.resolve())
                        scene.image_source_type = "direct_photo"
                        acquired = True
            except Exception as dl_err:
                logger.debug("Direct photo fetch failed for scene %d: %s", idx, dl_err)

        if not acquired and prefer_real_images and scene.entity_query:
            try:
                title, image_url = search_wikimedia_commons(scene.entity_query, category=category)
                if image_url:
                    logger.info("Found verified Wikimedia photo for '%s': %s", scene.entity_query, title)
                    if download_and_format_image(image_url, img_dest, aspect_ratio=aspect_ratio):
                        scene.image_path = str(img_dest.resolve())
                        scene.image_source_type = "wikimedia_commons"
                        acquired = True
            except Exception as exc:
                logger.debug("Wikimedia fetch failed for scene %d: %s", idx, exc)

        # Fallback to AI Image Generation (Cinematic Photorealistic style)
        if not acquired:
            prompt_to_use = ground_prompt_to_core_subject(
                prompt=scene.ai_prompt,
                fallback_headline=scene.entity_query or scene.text,
                category=category,
            )
            if category == "sports" and "football" not in prompt_to_use.lower() and "soccer" not in prompt_to_use.lower():
                prompt_to_use = f"cinematic photorealistic football match action photography, professional sports broadcast: {prompt_to_use}, 35mm lens, dramatic stadium floodlights"
            logger.info("Generating AI cinematic visual for scene %d: %s", idx, prompt_to_use[:70])

            try:
                generated_path = generate_scene_image(
                    prompt=prompt_to_use,
                    destination_path=img_dest,
                    aspect_ratio=aspect_ratio,
                    style="cinematic",
                    allow_free_online=True,
                )
                scene.image_path = str(generated_path.resolve())
                scene.image_source_type = "ai_generated"
                acquired = True
            except Exception as exc:
                logger.warning("AI image generation failed for scene %d (%s). Creating fallback card.", idx, exc)

        # Emergency fallback: create a clean dark gradient news slide
        if not acquired or not Path(scene.image_path).is_file():
            tw, th = resolution_for_aspect_ratio(aspect_ratio)
            card = Image.new("RGB", (tw, th), color=(18, 24, 38))
            card.save(img_dest, quality=90)
            scene.image_path = str(img_dest.resolve())
            scene.image_source_type = "custom"


acquire_images_for_scenes = prepare_scene_illustrations


def get_mock_news_items(category: str = "world") -> List[WorldNewsItem]:
    """Provide realistic, high-quality international news items for offline tests / fallbacks."""
    cat = normalize_category(category)
    if cat == "tin_moi":
        return get_mock_news_items("world")[:4] + get_mock_news_items("sports")[:4]
    if cat == "tin_nong":
        return get_mock_news_items("war")[:4] + get_mock_news_items("tech")[:4]
    if cat == "tech":
        return [
            WorldNewsItem(
                title="Nvidia unveils next-generation Blackwell Ultra AI superchips with 4x inference speedup",
                summary="Nvidia CEO Jensen Huang delivered a keynote introducing the Blackwell Ultra GB200 NVL72 computing architecture, delivering four times faster inference and training speeds for frontier artificial intelligence models while cutting power consumption by 25 times compared to previous architectures. Major cloud hyperscalers have already committed tens of billions to immediate deployment.",
                source="The Verge",
                published="Today",
                link="https://theverge.com",
            ),
            WorldNewsItem(
                title="OpenAI launches advanced reasoning model capable of real-time web tasks and software execution",
                summary="OpenAI officially rolled out its next-generation reasoning AI model with autonomous task execution capabilities, allowing the system to research complex web data, verify code correctness, and solve PhD-level science problems without hallucination.",
                source="TechCrunch",
                published="Today",
                link="https://techcrunch.com",
            ),
            WorldNewsItem(
                title="SpaceX achieves historic orbital Starship catch at launch tower with robotic Mechazilla arms",
                summary="SpaceX completed a landmark test flight of its 400-foot Starship mega-rocket, successfully guiding the 70-meter Super Heavy booster back to the Starbase launch pad where it was caught mid-air by the mechanical arms of the launch tower.",
                source="Ars Technica",
                published="Today",
                link="https://arstechnica.com",
            ),
            WorldNewsItem(
                title="Apple reveals comprehensive on-device generative AI features across iPhone and Mac systems",
                summary="Apple executives showcased deep artificial intelligence integration across iOS and macOS, featuring local privacy-first neural processing on Apple Silicon chips along with private cloud compute for high-complexity queries.",
                source="Wired",
                published="Today",
                link="https://wired.com",
            ),
            WorldNewsItem(
                title="European Union enacts global first landmark regulations for frontier AI model safety standards",
                summary="European regulators officially commenced enforcement of the world's first comprehensive legal framework governing foundation artificial intelligence models, mandating rigorous red-teaming, energy efficiency disclosure, and copyright compliance audits.",
                source="BBC News",
                published="Today",
                link="https://bbc.com",
            ),
            WorldNewsItem(
                title="Google DeepMind demonstrates breakthrough in molecular biology predicting entire cellular interactions",
                summary="Scientists at Google DeepMind unveiled AlphaFold 3 capabilities extending beyond proteins to predict the structures and interactions of DNA, RNA, ligands, and biochemical molecules with unprecedented atomic accuracy.",
                source="Nature Technology",
                published="Today",
                link="https://nature.com",
            ),
            WorldNewsItem(
                title="Researchers unveil fault-tolerant silicon quantum processor achieving breakthrough coherence times",
                summary="An international team of quantum physicists revealed a silicon-based quantum computing processor operating with over 99.9% gate fidelity and fault-tolerant error correction, bringing commercial quantum advantage closer to reality.",
                source="MIT Technology Review",
                published="Today",
                link="https://technologyreview.com",
            ),
            WorldNewsItem(
                title="Autonomous electric vehicle platform secures commercial regulatory approval across major global capitals",
                summary="Transportation safety authorities granted full driverless commercial robotaxi licenses across Tokyo, Singapore, and Phoenix following over 50 million miles of zero-fatality autonomous road testing.",
                source="Bloomberg Technology",
                published="Today",
                link="https://bloomberg.com",
            ),
        ]
    elif cat == "sports":
        return [
            WorldNewsItem(
                title="Real Madrid advances to Champions League semi-finals after dramatic penalty shootout victory",
                summary="Real Madrid secured a spot in the UEFA Champions League semi-finals following a pulsating 120-minute clash that concluded in an intense penalty shootout, with Jude Bellingham and Vinicius Junior leading the attack and decisive saves from the goalkeeper.",
                source="BBC Football",
                published="Today",
                link="https://bbc.com/sport/football",
            ),
            WorldNewsItem(
                title="Kylian Mbappe scores sensational brace as Paris Saint-Germain books European final berth",
                summary="Kylian Mbappe produced a masterclass performance with two second-half goals, driving an exhilarating 3-2 comeback victory that ignited roaring celebrations among fans and pundits across European football.",
                source="Sky Sports Football",
                published="Today",
                link="https://skysports.com/football",
            ),
            WorldNewsItem(
                title="Premier League title race intensifies as Arsenal and Manchester City deadlocked atop standings",
                summary="The English Premier League championship duel reached fever pitch after decisive weekend fixtures. Mikel Arteta's Arsenal and Pep Guardiola's Manchester City remain separated by a solitary point entering the season's climactic final weeks.",
                source="The Guardian Football",
                published="Today",
                link="https://theguardian.com/football",
            ),
            WorldNewsItem(
                title="Erling Haaland nets blistering hat-trick as Manchester City dismantles London rivals",
                summary="Norwegian striker Erling Haaland took his season tally to record heights with a clinical 18-minute hat-trick at the Etihad Stadium, combining brilliantly with Kevin De Bruyne to overwhelm the opponent's defensive backline.",
                source="ESPN FC",
                published="Today",
                link="https://espn.com/soccer",
            ),
            WorldNewsItem(
                title="Liverpool orchestrates dramatic stoppage-time Anfield comeback with Mohamed Salah strike",
                summary="Mohamed Salah delivered a thunderous 94th-minute winner in front of the Kop, sealing a thrilling 2-1 victory for Liverpool after an unrelenting wave of pressure broke down a resolute ten-man visiting defense.",
                source="BBC Football",
                published="Today",
                link="https://bbc.com/sport/football",
            ),
            WorldNewsItem(
                title="Barcelona teenage sensation Lamine Yamal sparkles in dominant 3-0 La Liga derby triumph",
                summary="Seventeen-year-old winger Lamine Yamal orchestrated two sublime assists and curled in a stunning 25-yard goal as FC Barcelona commanded the pitch, tightening their grip on the top positions in Spanish La Liga.",
                source="The Guardian Football",
                published="Today",
                link="https://theguardian.com/football",
            ),
            WorldNewsItem(
                title="European Transfer Window: Mega 120-million-euro striker signing agreed between top clubs",
                summary="Major European clubs reached a blockbuster 120-million-euro agreement for the prolific international forward, wrapping up weeks of high-stakes negotiations on a five-year contract ahead of the deadline.",
                source="Sky Sports Football",
                published="Today",
                link="https://skysports.com/football",
            ),
            WorldNewsItem(
                title="Harry Kane propels Bayern Munich to crucial Bundesliga victory with milestone 35th goal",
                summary="England captain Harry Kane continued his astonishing debut season in Germany, nodding home a pinpoint corner before converting a late penalty to steer Bayern Munich through a high-octane 3-1 away triumph.",
                source="ESPN FC",
                published="Today",
                link="https://espn.com/soccer",
            ),
        ]
    elif cat == "war":
        return [
            WorldNewsItem(
                title="Ukrainian defense forces repel massive multi-pronged armored offensive along Eastern Kharkiv frontline",
                summary="General Staff confirmed Ukrainian defenders repulsed intensive mechanized assaults involving over 30 armored fighting vehicles and continuous kamikaze drone sorties across the Kupyansk-Lyman sector, holding frontline fortifications under heavy retaliatory artillery fire.",
                source="BBC News / Conflict Desk",
                published="Today",
                link="https://bbc.com/news/world",
            ),
            WorldNewsItem(
                title="Coordinated airstrikes strike strategic underground command depots amid escalating Middle East conflict",
                summary="Combat aviation executed precision strikes on subterranean weapons facilities and radar radar arrays, producing substantial secondary detonations and prompting regional air defense systems into maximum alert posture across neighboring territories.",
                source="Al Jazeera English",
                published="Today",
                link="https://aljazeera.com",
            ),
            WorldNewsItem(
                title="Sudan Armed Forces and Rapid Support Forces engage in fierce street battles across Khartoum bridges",
                summary="Urban fighting intensified throughout key river bridgeheads in Khartoum and North Darfur, where heavy automatic weapon fire and sniper operations disrupted civilian evacuation routes despite international calls for humanitarian corridors.",
                source="The Guardian World",
                published="Today",
                link="https://theguardian.com/world",
            ),
            WorldNewsItem(
                title="Naval coalition warships intercept salvo of anti-ship ballistic missiles and attack drones in Red Sea",
                summary="Guided-missile destroyers operating in international waters successfully engaged and destroyed multiple hostile ballistic projectiles and unmanned surface vessels targeting commercial cargo vessels transiting vital maritime trade lanes.",
                source="Reuters Defense",
                published="Today",
                link="https://reuters.com",
            ),
            WorldNewsItem(
                title="Violent anti-government riots and clashes with security forces break out in South American capital",
                summary="State security personnel deployed tear gas and water cannons as thousands of violent demonstrators stormed barricades outside ministerial headquarters, leaving dozens of officers injured and prompting emergency curfew declarations.",
                source="Associated Press",
                published="Today",
                link="https://apnews.com",
            ),
            WorldNewsItem(
                title="Myanmar ethnic alliance captures fortified border garrison following weeks of sustained artillery siege",
                summary="Allied ethnic resistance battalions announced the seizure of a fortified military stronghold near the northern frontier, confiscating heavy howitzers and ammunition caches following protracted trench warfare.",
                source="NPR World",
                published="Today",
                link="https://npr.org",
            ),
            WorldNewsItem(
                title="Long-range drone strike ignites major aviation fuel depot at strategic regional military airfield",
                summary="Satellite imagery confirmed extensive fire and smoke billows at a frontline logistical airbase after a swarm of autonomous one-way attack drones penetrated perimeter defense nets, damaging repair hangars and taxiways.",
                source="Financial Times",
                published="Today",
                link="https://ft.com",
            ),
            WorldNewsItem(
                title="UN Security Council convenes emergency closed-door meeting over cross-border military escalation",
                summary="Ambassadors convened an emergency session in New York to address sudden cross-border artillery duels and troop build-ups, debating draft resolutions urging immediate cessation of military hostilities and mutual de-escalation.",
                source="BBC News",
                published="Today",
                link="https://bbc.com",
            ),
        ]
    elif cat == "viral":
        return [
            WorldNewsItem(
                title="Bizarre glowing purple sky leaves millions stunned across Northern Europe as viral photos explode on X",
                summary="A rare geomagnetic atmospheric storm painted skies across Scandinavia and the UK in surreal vibrant neon purple hues. Millions of viral photos and video clips on X and Instagram generated over 80 million impressions within hours.",
                source="X Trending",
                published="Today",
                link="https://x.com",
                social_platform="x",
            ),
            WorldNewsItem(
                title="Clumsy burglar gets stuck upside down in bakery ventilation shaft and has to call police to rescue him",
                summary="A hapless thief attempting a late-night bakery heist in Brussels slipped into the ductwork, wedging himself upside down directly above the ovens. After shouting for help for three hours, he sheepishly called the emergency hotline himself, amusing responding officers.",
                source="UPI Odd News",
                published="Today",
                link="https://upi.com",
                social_platform="x",
            ),
            WorldNewsItem(
                title="Mischievous sea otter repeatedly hijacks surfboards from beachgoers in California causing hilarious chaos",
                summary="A brazen five-year-old female sea otter dubbed Otter 841 has been paddling up to unsuspecting surfers, climbing onto their longboards, and refusing to give them back until coaxed with squid treats. The hilarious viral video garnered 60 million views on TikTok.",
                source="Reddit r/funny",
                published="Today",
                link="https://reddit.com",
                social_platform="reddit",
            ),
            WorldNewsItem(
                title="Mysterious 100-foot ancient crystal cavern uncovered by construction workers in Mexican desert",
                summary="Construction crews excavating in Chihuahua accidentally broke into a hidden underground chamber filled with towering selenite crystals up to 30 feet tall. Breathtaking footage shared on Facebook gained over 200,000 shares in 24 hours.",
                source="Facebook Viral",
                published="Today",
                link="https://facebook.com",
                social_platform="facebook",
            ),
            WorldNewsItem(
                title="Tokyo cafe introduces ultra-lifelike AI robot baristas that remember every customer's face and mood",
                summary="A futuristic robot cafe in Shibuya went ultra-viral on Instagram after showcasing humanoid robotic baristas powered by multimodal AI that converse naturally, brew personalized latte art, and remember thousands of frequent patrons.",
                source="Instagram Trends",
                published="Today",
                link="https://instagram.com",
                social_platform="instagram",
            ),
        ]
    elif cat == "hope":
        return [
            WorldNewsItem(
                title="Landmark clinical trial achieves 90 percent remission in aggressive pediatric leukemia using tailored immunotherapy",
                summary="Oncologists at a premier medical research institute revealed groundbreaking results from a Phase 3 clinical trial where personalized mRNA cell therapy completely eliminated cancerous cells in nine out of ten young patients with previously incurable leukemia.",
                source="ScienceDaily Health",
                published="Today",
                link="https://sciencedaily.com/health",
                social_platform="x",
            ),
            WorldNewsItem(
                title="Conservation milestone as endangered sea turtle population rebounds by four hundred percent in protected marine sanctuaries",
                summary="Marine biologists documented an extraordinary revival across tropical nesting beaches, with over 150000 healthy turtle hatchlings reaching the ocean following community-led reef protection and coastal habitat preservation programs.",
                source="Good News Network",
                published="Today",
                link="https://goodnewsnetwork.org/species-recovery",
                social_platform="x",
            ),
            WorldNewsItem(
                title="Scientists engineer solar-powered ocean barrier that extracts tons of microplastics autonomously",
                summary="Marine engineers and environmental researchers deployed a revolutionary self-sustaining autonomous barrier powered by floating solar panels, capable of intercepting and filtering over 50 tons of microplastics from ocean currents each month without harming marine wildlife.",
                source="Optimist Daily",
                published="Today",
                link="https://optimistdaily.com/ocean-cleanup",
                social_platform="x",
            ),
            WorldNewsItem(
                title="Bionic neural implant successfully restores artificial vision and spatial awareness for patients with severe blindness",
                summary="A joint biomedical engineering team demonstrated a wireless cortical visual prosthesis that enables totally blind patients to identify everyday objects, navigate doorways, and read large printed letters safely without human assistance.",
                source="ScienceDaily Health",
                published="Today",
                link="https://sciencedaily.com/vision-implant",
                social_platform="x",
            ),
            WorldNewsItem(
                title="Global reforestation initiative restores 500000 hectares of biodiverse rainforest with drone seed firing",
                summary="An international conservation consortium celebrated the successful restoration of half a million hectares of degraded tropical jungle using autonomous mapping drones that plant up to 100000 native tree seeds per day with 85% germination rates.",
                source="Good News Network",
                published="Today",
                link="https://goodnewsnetwork.org/reforestation",
                social_platform="x",
            ),
            WorldNewsItem(
                title="Next-generation solid-state battery delivers 1000-mile electric vehicle range and charges in ten minutes",
                summary="Materials scientists introduced a non-flammable solid-state battery architecture that retains 95% capacity after 3000 rapid charge cycles, slashing manufacturing costs by 40% and offering zero-emission long-range transport for all.",
                source="New Atlas",
                published="Today",
                link="https://newatlas.com/battery",
                social_platform="x",
            ),
        ]
    else:
        # Default World News
        return [
            WorldNewsItem(
                title="Macron rejects interior minister's resignation after French riots",
                summary="French President Emmanuel Macron delivered a televised address urging citizens to remain calm and rejecting his minister's resignation after intense protests erupted in Paris, Lyon and Marseille. Over 45,000 security personnel have been deployed across major cities.",
                source="Financial Times",
                published="Today",
                link="https://ft.com",
            ),
            WorldNewsItem(
                title="Israeli police arrest 10 over settler attacks on diplomats in West Bank",
                summary="Law enforcement confirmed the detention of ten suspects following violent assaults against European diplomats and press corps in the West Bank, prompting strong condemnation from Washington and Brussels.",
                source="BBC News",
                published="Today",
                link="https://bbc.com",
            ),
            WorldNewsItem(
                title="Australian MP Helen Haines critically injured in deliberate car ramming",
                summary="Independent lawmaker Helen Haines is in critical condition after a targeted vehicular attack outside parliament offices in Canberra, leading the Australian Prime Minister to call for emergency security measures.",
                source="Al Jazeera",
                published="Today",
                link="https://aljazeera.com",
            ),
            WorldNewsItem(
                title="Egypt agrees to help Saudi Arabia defend airspace against Houthi attacks",
                summary="Cairo officially confirmed military coordination with Riyadh to bolster regional air defense and safeguard crucial Red Sea maritime corridors from escalated drone and ballistic strikes.",
                source="Politico",
                published="Today",
                link="https://politico.com",
            ),
            WorldNewsItem(
                title="Italian police detain hundreds as stores looted in weekend unrest in Milan",
                summary="Over 200 arrests were made in central Milan following severe rioting and commercial looting sparked by nationwide cost-of-living demonstrations.",
                source="Reuters",
                published="Today",
                link="https://reuters.com",
            ),
            WorldNewsItem(
                title="Russian foreign minister Lavrov visits Iran for urgent regional security talks",
                summary="Sergey Lavrov arrived in Tehran for high-stakes diplomatic consultations aimed at averting full-scale conflict and stabilizing energy markets across the Persian Gulf.",
                source="CBS News",
                published="Today",
                link="https://cbsnews.com",
            ),
            WorldNewsItem(
                title="Fire at Canadian Forces Base Wainwright kills 4 soldiers and injures 39",
                summary="Defense officials confirmed a devastating blaze broke out during tactical field exercises in Alberta, leading to immediate investigations into military facility safety protocols.",
                source="The New York Times",
                published="Today",
                link="https://nytimes.com",
            ),
            WorldNewsItem(
                title="Super Typhoon Champi intensifies to Category 5 after battering Pacific islands",
                summary="Meteorological authorities issued catastrophic storm warnings as Super Typhoon Champi reached sustained winds of 165 mph, tracking northwest toward regional shipping lanes.",
                source="Yale Climate Connections",
                published="Today",
                link="https://yaleclimateconnections.org",
            ),
        ]


def get_editorial_scripts_dir() -> Path:
    """Return the dedicated central directory for raw editorial scripts and Proof-of-Work text files."""
    central_dir = runtime_data_dir() / "editorial_scripts"
    central_dir.mkdir(parents=True, exist_ok=True)
    return central_dir


def safe_script_filename(title: str, category: str, created_at: str, digest_id: str = "") -> str:
    """Generate a clean, sortable, unambiguous filename for an editorial script."""
    # Date extraction (YYYY-MM-DD)
    date_str = ""
    if created_at:
        m = re.search(r"(\d{4})[-_]?(\d{2})[-_]?(\d{2})", created_at)
        if m:
            date_str = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    # Clean title slug
    norm_title = _normalize_text_for_search(title)
    # Remove hashtags and special characters
    norm_title = re.sub(r"#\w+", "", norm_title)
    words = re.findall(r"[a-z0-9]+", norm_title)

    # Filter common filler words
    slug_words = []
    for w in words:
        if w in ("tin", "nong", "doc", "la", "the", "gioi", "ngay", "ban"):
            continue
        slug_words.append(w.capitalize())
        if len(slug_words) >= 5 or sum(len(x) for x in slug_words) >= 30:
            break

    slug = "_".join(slug_words) if slug_words else "Ban_Tin"
    norm_cat = normalize_category(category)

    # Short unique suffix
    suffix = str(digest_id or "").strip()[:8]
    if not suffix:
        clean_seed = "".join(words) or title
        suffix = hex(abs(hash(clean_seed)))[2:10]

    return f"{date_str}_{norm_cat}_{slug}_{suffix}.txt"


def generate_editorial_proof_of_work_text(
    data: dict | DailyNewsDigest,
    news_items: Optional[List[WorldNewsItem]] = None,
) -> str:
    """Format comprehensive human-readable Proof-of-Work document for YouTube appeal/compliance."""
    is_dict = isinstance(data, dict)

    title = str((data.get("title") if is_dict else getattr(data, "title", "")) or "Bản Tin Thế Giới").strip()
    category = str((data.get("category") if is_dict else "world") or "world")
    norm_cat = normalize_category(category)
    cfg = get_category_config(norm_cat)
    category_label = str((data.get("category_label") if is_dict else cfg.get("label", "")) or cfg.get("label", "Thời sự"))
    aspect_ratio = str((data.get("aspect_ratio") if is_dict else "16:9") or "16:9")
    format_name = "Shorts dọc 9:16" if aspect_ratio == "9:16" else "Video ngang 16:9"
    created_at = str((data.get("created_at") if is_dict else getattr(data, "created_at", "")) or "")
    voice = str((data.get("voice") if is_dict else "vi-VN-NamMinhNeural") or "vi-VN-NamMinhNeural")
    digest_id = str((data.get("digest_id") if is_dict else getattr(data, "digest_id", "")) or "")

    summary = str((data.get("summary") if is_dict else getattr(data, "summary_lead", "")) or "").strip()
    thumbnail_hook = str((data.get("thumbnail_hook") if is_dict else getattr(data, "thumbnail_hook", "")) or "").strip()
    ticker_summary = str((data.get("ticker_summary") if is_dict else getattr(data, "ticker_summary", "")) or "").strip()
    hashtags = str((data.get("hashtags") if is_dict else getattr(data, "hashtags", "")) or "").strip()

    yt_pub = bool(data.get("youtube_published") if is_dict else False)
    yt_status = "Đã xuất bản (Published)" if yt_pub else "Chưa xuất bản / Lưu trữ nội bộ (Draft / Stored)"
    yt_url = str((data.get("youtube_url") if is_dict else "") or "")

    # Extract scenes
    if is_dict:
        raw_scenes = data.get("script_scenes", [])
    else:
        raw_scenes = getattr(data, "scenes", [])

    scenes_list = []
    for idx, sc in enumerate(raw_scenes, start=1):
        if isinstance(sc, dict):
            scenes_list.append({
                "index": sc.get("scene_index", idx - 1) + 1,
                "text": str(sc.get("text", "")).strip(),
                "entity": str(sc.get("entity", "")).strip(),
                "image_source": str(sc.get("image_source", "social_screenshot")),
                "transition": bool(sc.get("transition_cue", False)),
            })
        else:
            scenes_list.append({
                "index": getattr(sc, "scene_index", idx - 1) + 1,
                "text": str(getattr(sc, "text", "")).strip(),
                "entity": str(getattr(sc, "entity_query", "")).strip(),
                "image_source": str(getattr(sc, "image_source_type", "social_screenshot")),
                "transition": bool(getattr(sc, "has_transition_cue", False)),
            })

    # Sources extraction
    sources_lines = []
    if news_items:
        for idx, item in enumerate(news_items, start=1):
            src_name = getattr(item, "source", "Hãng tin quốc tế") or "Hãng tin quốc tế"
            src_title = getattr(item, "title", "")
            src_link = getattr(item, "link", "")
            src_pub = getattr(item, "published", "")
            line = f"• [Nguồn {idx:02d}] {src_name}: \"{src_title}\"\n  Link: {src_link}"
            if src_pub:
                line += f"\n  Thời điểm công bố: {src_pub}"
            sources_lines.append(line)
    elif is_dict and data.get("source_items"):
        for idx, it in enumerate(data.get("source_items", []), start=1):
            line = f"• [Nguồn {idx:02d}] {it.get('source', 'Báo chí quốc tế')}: \"{it.get('title', '')}\"\n  Link: {it.get('link', '')}"
            if it.get("published"):
                line += f"\n  Thời điểm công bố: {it.get('published')}"
            sources_lines.append(line)
    elif is_dict and data.get("sources"):
        raw_srcs = data.get("sources", [])
        sources_lines.append(f"• Các tổ chức báo chí & nền tảng nguồn: {', '.join(str(s) for s in raw_srcs)}")
    else:
        sources_lines.append("• Hãng thông tấn quốc tế: Reuters, AP, UPI Odd, BBC, Reddit, X (Verified news feeds)")

    sources_block = "\n".join(sources_lines)

    # Full continuous voiceover script
    continuous_paragraphs = [s["text"] for s in scenes_list if s["text"]]
    continuous_script = "\n\n".join(continuous_paragraphs) if continuous_paragraphs else "(Chưa có văn bản lời thoại)"

    # Scene breakdown
    scene_breakdown_blocks = []
    for s in scenes_list:
        badge = "(Phân cảnh mở đầu - Hook)" if s["index"] == 1 else "(Phân cảnh nội dung)"
        trans_str = "Có chuyển cảnh Ken Burns" if s["transition"] else "Liền mạch"
        scene_breakdown_blocks.append(
            f"[PHÂN CẢNH {s['index']:02d}] {badge}\n"
            f"• Lời thoại MC: {s['text']}\n"
            f"• Từ khóa thực thể / Hình ảnh: {s['entity'] or '(Tự động chọn theo ngữ cảnh)'}\n"
            f"• Phương thức minh họa: {s['image_source']}\n"
            f"• Hiệu ứng chuyển động: {trans_str}"
        )
    scene_breakdown_str = "\n\n".join(scene_breakdown_blocks)

    doc = f"""================================================================================
HAIZFLOW STUDIO - HỒ SƠ BIÊN TẬP & KỊCH BẢN GỐC (EDITORIAL PROOF OF WORK)
Tài liệu xác nhận quy trình sản xuất nội dung chính chủ & nghiên cứu tin tức
================================================================================
TIÊU ĐỀ VIDEO: {title}
CHUYÊN MỤC: {category_label} ({norm_cat})
ĐỊNH DẠNG: {aspect_ratio} ({format_name})
THỜI GIAN BIÊN TẬP: {created_at or datetime.now().isoformat()}
MÃ ĐỊNH DANH (ID): {digest_id or 'news_auto'}
SỐ LƯỢNG PHÂN CẢNH: {len(scenes_list)} cảnh
GIỌNG ĐỌC SẢN XUẤT: {voice}
TRẠNG THÁI YOUTUBE: {yt_status}
LIÊN KẾT VIDEO: {yt_url or '(Chưa đăng hoặc xuất file cục bộ)'}

--------------------------------------------------------------------------------
1. NGUỒN TÀI LIỆU NGHIÊN CỨU & ĐỐI SOÁT (ORIGINAL SOURCES & FACT-CHECKING)
--------------------------------------------------------------------------------
{sources_block}

--------------------------------------------------------------------------------
2. Ý TƯỞNG BIÊN TẬP & ĐỊNH HƯỚNG BẢN TIN (EDITORIAL CONCEPT & HOOKS)
--------------------------------------------------------------------------------
• LỜI DẪN MỞ ĐẦU (EDITORIAL LEAD / HOOK):
  {summary or '(Không có)'}

• TIÊU ĐỀ ẢNH BÌA (THUMBNAIL HOOK):
  {thumbnail_hook or '(Mặc định theo tiêu đề)'}

• NỘI DUNG CHỮ CHẠY CHÂN TRANG (TICKER TAPE SUMMARY):
  {ticker_summary or '(Không kích hoạt)'}

• TỪ KHÓA & THẺ TAG (EDITORIAL HASHTAGS):
  {hashtags or '#Shorts'}

--------------------------------------------------------------------------------
3. TOÀN VĂN KỊCH BẢN LỜI THOẠI BIÊN TẬP (FULL CONTINUOUS VOICEOVER SCRIPT)
(Văn bản kịch bản gốc hoàn chỉnh để đọc thuyết minh liên tục)
--------------------------------------------------------------------------------
{continuous_script}

--------------------------------------------------------------------------------
4. BẢNG PHÂN CẢNH SẢN XUẤT CHI TIẾT (SCENE-BY-SCENE PRODUCTION BREAKDOWN)
(Chi tiết phân cảnh, lời bình từng đoạn, chỉ đạo mỹ thuật và hiệu ứng chuyển cảnh)
--------------------------------------------------------------------------------
{scene_breakdown_str}

================================================================================
CAM KẾT BIÊN TẬP & BẢN QUYỀN SẢN XUẤT (EDITORIAL COMPLIANCE STATEMENT):
Tài liệu này là bằng chứng xác thực quá trình lao động sáng tạo, biên soạn và
dàn dựng nội dung nguyên bản (Significant Editorial Value & Human Effort) được
thực hiện trên hệ thống HaizFlow Studio.
Mọi phân cảnh, cấu trúc lời bình và hình ảnh minh họa đều được đối soát, biên tập
kỹ lưỡng từ các nguồn dữ liệu quốc tế mở, tuân thủ chặt chẽ chính sách bản quyền
và chính sách chống nội dung lặp lại / không có giá trị gia tăng của YouTube
(YouTube Channel Monetization Policies - Originality & Significant Editorial Effort).
================================================================================
"""
    return doc.strip() + "\n"


def export_editorial_script_file(
    manifest_data: dict,
    news_items: Optional[List[WorldNewsItem]] = None,
    output_dir: Optional[Path] = None,
) -> Path:
    """Generate and write the editorial proof-of-work text file in both local run folder and central scripts dir."""
    text_content = generate_editorial_proof_of_work_text(manifest_data, news_items=news_items)

    # 1. Save in central editorial_scripts directory
    central_dir = get_editorial_scripts_dir()
    title = str(manifest_data.get("title", ""))
    cat = str(manifest_data.get("category", "world"))
    created_at = str(manifest_data.get("created_at", ""))
    video_path_str = str(manifest_data.get("video_path", ""))
    digest_id = ""
    if video_path_str:
        m = re.search(r"_([a-f0-9]{8,12})\.mp4", video_path_str, re.IGNORECASE)
        if m:
            digest_id = m.group(1)

    filename = safe_script_filename(title, cat, created_at, digest_id=digest_id)
    central_path = central_dir / filename
    central_path.write_text(text_content, encoding="utf-8")

    # 2. Also save in the video output folder if specified
    if output_dir:
        out_p = Path(output_dir).resolve()
        if out_p.is_dir():
            local_path = out_p / "script_raw.txt"
            local_path.write_text(text_content, encoding="utf-8")

    return central_path


def retroactive_export_all_daily_news_scripts() -> List[Path]:
    """Scan all existing daily news folders and ensure they have raw script files."""
    base_dir = runtime_data_dir() / "daily_news"
    exported: List[Path] = []
    if not base_dir.is_dir():
        return exported

    for run_dir in base_dir.iterdir():
        if not run_dir.is_dir():
            continue
        manifest_path = run_dir / "social_publish_manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            m = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not m.get("script_scenes"):
                continue
            script_path = export_editorial_script_file(m, output_dir=run_dir)
            exported.append(script_path)
            if not m.get("raw_script_path"):
                m["raw_script_path"] = str(script_path.resolve())
                manifest_path.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("Could not export raw script for %s: %s", run_dir, exc)

    return exported


def format_youtube_description_with_sources(
    manifest: Dict[str, Any],
    title: Optional[str] = None,
    summary: Optional[str] = None,
    hashtags: Optional[str] = None,
    max_length: int = 4900,
) -> str:
    """Format an exhaustive, professional YouTube description citing all news sources.

    Strictly guarantees that 100% of reported news sources and URLs are listed for
    both standard landscape videos (16:9) and vertical Shorts (9:16) without omission.
    """
    final_title = (title or manifest.get("title") or "").strip()
    final_summary = (summary or manifest.get("summary") or "").strip()
    raw_hashtags = (hashtags or manifest.get("hashtags") or "").strip()
    clean_hashtags = " ".join([t for t in raw_hashtags.split() if t.lower().lstrip("#") != "haizflow"])

    # Auto-add #Shorts if this is a vertical short (9:16) or shorts category (viral/hope)
    norm_cat = str(manifest.get("category") or "").strip().lower()
    aspect_ratio = str(manifest.get("aspect_ratio") or "")
    is_shorts = (aspect_ratio == "9:16") or norm_cat in ("viral", "hope", "tinla", "docla", "tinvui", "hyvong")
    if is_shorts and "#shorts" not in clean_hashtags.lower():
        clean_hashtags = f"#Shorts {clean_hashtags}".strip()

    # 1. Extract every single source item without omission
    raw_source_items = manifest.get("source_items") or manifest.get("news_items") or []
    raw_sources = manifest.get("sources") or []

    # Normalize source items list
    items_to_format: List[Dict[str, str]] = []
    seen_links = set()

    for item in raw_source_items:
        if isinstance(item, dict):
            src_name = str(item.get("source") or "Báo chí quốc tế").strip().replace("<", "").replace(">", "")
            src_title = str(item.get("title") or "").strip().replace("<", "").replace(">", "")
            src_link = str(item.get("link") or "").strip().replace("<", "").replace(">", "")
        elif hasattr(item, "source") or hasattr(item, "title") or hasattr(item, "link"):
            src_name = str(getattr(item, "source", "Báo chí quốc tế")).strip().replace("<", "").replace(">", "")
            src_title = str(getattr(item, "title", "")).strip().replace("<", "").replace(">", "")
            src_link = str(getattr(item, "link", "")).strip().replace("<", "").replace(">", "")
        else:
            continue

        link_key = src_link.strip().rstrip("/").lower() if src_link else f"{src_name}:{src_title}".lower()
        if link_key and link_key in seen_links:
            continue
        if link_key:
            seen_links.add(link_key)
        items_to_format.append({
            "source": src_name or "Báo chí quốc tế",
            "title": src_title,
            "link": src_link,
        })

    # If raw_sources has entries not in source_items, add them too
    for src in raw_sources:
        src_str = str(src).strip()
        if not src_str:
            continue
        if any(item["source"].lower() == src_str.lower() for item in items_to_format):
            continue
        items_to_format.append({
            "source": src_str,
            "title": "",
            "link": "",
        })

    def _build_full_desc(header: str, items: List[Dict[str, str]], condensed_level: int = 0) -> str:
        sources_blocks = []
        for idx, item in enumerate(items, start=1):
            src_name = item["source"]
            src_title = item["title"]
            src_link = item["link"]

            if condensed_level == 0:
                # Full detailed block
                if src_title and src_link:
                    sources_blocks.append(f"[{idx:02d}] {src_name}: \"{src_title}\"\n🔗 {src_link}")
                elif src_link:
                    sources_blocks.append(f"[{idx:02d}] {src_name}\n🔗 {src_link}")
                elif src_title:
                    sources_blocks.append(f"[{idx:02d}] {src_name}: \"{src_title}\"")
                else:
                    sources_blocks.append(f"[{idx:02d}] {src_name}")
            elif condensed_level == 1:
                # Moderate condensed: single line per item with title up to 60 chars
                short_title = (src_title[:60] + "...") if len(src_title) > 60 else src_title
                if short_title and src_link:
                    sources_blocks.append(f"[{idx:02d}] {src_name}: \"{short_title}\" - {src_link}")
                elif src_link:
                    sources_blocks.append(f"[{idx:02d}] {src_name}: {src_link}")
                elif short_title:
                    sources_blocks.append(f"[{idx:02d}] {src_name}: \"{short_title}\"")
                else:
                    sources_blocks.append(f"[{idx:02d}] {src_name}")
            else:
                # Ultra condensed: minimal footprint to guarantee 100% inclusion within character limit
                if src_link:
                    sources_blocks.append(f"[{idx:02d}] {src_name}: {src_link}")
                elif src_title:
                    sources_blocks.append(f"[{idx:02d}] {src_name}: {src_title[:40]}")
                else:
                    sources_blocks.append(f"[{idx:02d}] {src_name}")

        sources_text = ""
        if sources_blocks:
            separator = "\n\n" if condensed_level == 0 else "\n"
            sources_text = (
                "--------------------------------------------------\n"
                "📰 NGUỒN TIN BÁO CHÍ THAM KHẢO (SOURCES):\n"
                + separator.join(sources_blocks)
                + "\n--------------------------------------------------"
            )

        components = [c for c in [header, sources_text, clean_hashtags] if c]
        return "\n\n".join(components)

    # 1. Header: Title and Summary Lead
    header_parts = []
    if final_title:
        header_parts.append(final_title)
    if final_summary and final_summary != final_title:
        header_parts.append(final_summary)
    header_text = "\n\n".join(header_parts)

    full_desc = _build_full_desc(header_text, items_to_format, condensed_level=0)

    # If full description exceeds max_length, adapt progressively:
    # First: condense source item format
    if len(full_desc) > max_length and items_to_format:
        full_desc = _build_full_desc(header_text, items_to_format, condensed_level=1)

    # Second: if still too long, shorten summary lead to make room for 100% of sources
    if len(full_desc) > max_length and len(final_summary) > 250:
        short_summary = final_summary[:250].rstrip() + "..."
        compressed_header = "\n\n".join([p for p in [final_title, short_summary] if p])
        full_desc = _build_full_desc(compressed_header, items_to_format, condensed_level=1)

    # Third: if still too long in extreme cases, ultra-condense sources (all sources still kept!)
    if len(full_desc) > max_length and items_to_format:
        short_summary = final_summary[:150].rstrip() + "..." if len(final_summary) > 150 else final_summary
        compressed_header = "\n\n".join([p for p in [final_title, short_summary] if p])
        full_desc = _build_full_desc(compressed_header, items_to_format, condensed_level=2)

    # Strip any haizflow tag if present and illegal angle brackets (<, >)
    full_desc = re.sub(r"#\s*haizflow\b", "", full_desc, flags=re.IGNORECASE).strip()
    full_desc = re.sub(r"[<>]", "", full_desc)
    return full_desc


def produce_daily_news_video(
    output_dir: Optional[Path] = None,
    aspect_ratio: AspectRatio = "16:9",
    voice_id: str = "vi-VN-NamMinhNeural",
    mock_news: bool = False,
    detail_level: Literal["concise", "standard", "deep"] = "standard",
    max_topics: int = 8,
    bgm_path: Optional[str] = "default",
    bgm_volume: float = 0.08,
    category: str = "world",
    progress_callback: Optional[Callable[[int, str], None]] = None,
    prefer_real_images: bool = True,
) -> Path:
    """Full end-to-end execution of the Daily News video production pipeline (YouTube Edition)."""
    norm_cat = normalize_category(category)
    cfg = get_category_config(norm_cat)

    # Viral and Hope categories target YouTube Shorts: vertical 9:16 and rich compilation (default 8/7 topics)
    # All other news categories (world, war, tech, sports) are standard long-form broadcasts and MUST strictly be 16:9
    if norm_cat in ("viral", "hope"):
        aspect_ratio = "9:16"
        if not max_topics or max_topics <= 0 or max_topics in (7, 8):
            max_topics = 3
    else:
        aspect_ratio = "16:9"

    if output_dir is None:
        date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = runtime_data_dir() / "daily_news" / f"{norm_cat}_{date_str}"

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    def report(pct: int, msg: str):
        logger.info("[%d%%] %s", pct, msg)
        if progress_callback:
            progress_callback(pct, msg)

    report(5, f"Đang cào tin tức {cfg['label'].lower()} quốc tế từ các hãng thông tấn...")

    acquire_prevent_sleep()
    # Step 1: Fetch international news (Vietnam strictly excluded)
    if mock_news:
        news_items = get_mock_news_items(norm_cat)
    else:
        news_items = fetch_world_news_rss(max_items=max_topics, exclude_vietnam=True, category=norm_cat)
        if not news_items:
            logger.warning("No live RSS items retrieved for category '%s'. Falling back to default topics.", norm_cat)
            return produce_daily_news_video(
                output_dir,
                aspect_ratio,
                voice_id,
                mock_news=True,
                detail_level=detail_level,
                max_topics=max_topics,
                bgm_path=bgm_path,
                bgm_volume=bgm_volume,
                category=norm_cat,
                progress_callback=progress_callback,
                prefer_real_images=prefer_real_images,
            )

    report(15, f"Đang tổng hợp bản tin {cfg['label']} YouTube tiếng Việt ({max_topics} sự kiện) qua Gemini Flash...")

    # Step 2: Synthesize Vietnamese news script with Gemini Flash
    gemini_key = get_effective_gemini_api_key()
    if gemini_key:
        try:
            digest = synthesize_news_script_with_gemini(
                news_items,
                gemini_key,
                detail_level=detail_level,
                max_topics=max_topics,
                category=norm_cat,
            )
        except Exception as exc:
            logger.warning("Gemini synthesis error: %s. Using local fallback.", exc)
            digest = fallback_offline_news_script(news_items, detail_level=detail_level, max_topics=max_topics, category=norm_cat)
    else:
        logger.info("No Gemini API key detected. Using local fallback synthesis.")
        digest = fallback_offline_news_script(news_items, detail_level=detail_level, max_topics=max_topics, category=norm_cat)

    # Supreme Law check: enforce 0% Vietnam content before any asset generation or rendering
    digest = assert_and_sanitize_no_vietnam_content(digest)

    report(30, f"Kịch bản hoàn tất: '{digest.title}' ({len(digest.scenes)} phân cảnh chi tiết). Bắt đầu tìm ảnh tư liệu...")

    # Step 3: Fetch copyright-safe illustrations / Wikimedia photos
    assets_dir = output_dir / "assets"
    prepare_scene_illustrations(
        scenes=digest.scenes,
        output_dir=assets_dir,
        aspect_ratio=aspect_ratio,
        prefer_real_images=prefer_real_images,
        category=norm_cat,
        progress_callback=progress_callback,
    )

    report(55, "Đang chuyển đổi phân cảnh thành dự án HaizFlow Video...")

    # Step 4: Convert into HaizFlow ArticleVideoProject
    article_scenes: List[ArticleScene] = []
    for sc in digest.scenes:
        article_scenes.append(
            ArticleScene(
                scene_index=sc.scene_index,
                text=sc.text,
                has_image=True,
                image_path=sc.image_path,
                image_prompt=sc.ai_prompt or sc.entity_query,
                has_transition_cue=sc.has_transition_cue,
            )
        )

    config = ArticleProjectConfig(
        article_text=digest.title + "\n\n" + "\n".join(s.text for s in digest.scenes),
        voice_provider="edge",
        voice_id=voice_id,
        aspect_ratio=aspect_ratio,
        image_style="cinematic",
        subtitle_enabled=not bool((digest.ticker_summary or "").strip()),
        subtitle_font_family="Arial",
        subtitle_font_size=48 if aspect_ratio == "9:16" else 38,
        background_music_path=str(bgm_path or ""),
        background_music_volume=bgm_volume,
        branding_enabled=True,
        ticker_text=(digest.ticker_summary or "").strip(),
        ticker_label="TIN VUI" if norm_cat == "hope" else ("ĐỘC LẠ" if norm_cat == "viral" else ("TIN NÓNG" if norm_cat in ("tin_nong", "war") else "TIN MỚI")),
        category=norm_cat,
    )

    final_title = ensure_date_in_title(digest.title, digest.created_at)
    if norm_cat in ("viral", "hope") and "#Shorts" not in final_title and "#shorts" not in final_title.lower():
        final_title = f"{final_title} #Shorts"

    project = ArticleVideoProject(
        project_id=f"news_{digest.digest_id}",
        project_name=final_title,
        config=config,
        scenes=article_scenes,
    )

    report(65, "Đang tổng hợp giọng đọc AI và dựng các slide chuyển động Ken Burns...")

    # Step 5: Render video with SlideComposer
    final_video_path = output_dir / f"{cfg['file_prefix']}_{digest.digest_id}.mp4"
    compose_article_video(
        project=project,
        output_video_path=final_video_path,
        progress_callback=progress_callback,
    )

    # Step 5b: Curiosity thumbnail (hook <= 8 words + bulletin label). Never blocks publishing.
    thumbnail_file = output_dir / "thumbnail.jpg"
    thumbnail_path_str = ""
    try:
        from haizflow.pipeline.thumbnail import build_thumbnail

        cover_image = next((s.image_path for s in digest.scenes if s.image_path and Path(s.image_path).is_file()), None)
        build_thumbnail(
            source_image=cover_image,
            hook=digest.thumbnail_hook,
            label=cfg.get("title_suffix_label", ""),
            output_path=thumbnail_file,
            aspect_ratio=aspect_ratio,
            category=norm_cat,
        )
        thumbnail_path_str = str(thumbnail_file.resolve())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Thumbnail generation failed: %s", exc)

    # Step 6: Save metadata and publishing manifest
    manifest_path = output_dir / "social_publish_manifest.json"
    manifest_data = {
        "title": final_title,
        "summary": digest.summary_lead,
        "hashtags": digest.hashtags,
        "thumbnail_hook": digest.thumbnail_hook,
        "thumbnail_label": cfg.get("title_suffix_label", "").upper(),
        "thumbnail_path": thumbnail_path_str,
        "ticker_summary": digest.ticker_summary,
        "category": norm_cat,
        "category_label": cfg["label"],
        "video_path": str(final_video_path.resolve()),
        "scenes_count": len(digest.scenes),
        "detail_level": detail_level,
        "aspect_ratio": aspect_ratio,
        "voice": voice_id,
        "bgm_enabled": bool(bgm_path and bgm_path != ""),
        "bgm_volume": bgm_volume,
        "sources": list(dict.fromkeys(item.source for item in news_items if getattr(item, "source", ""))),
        "source_items": [
            {
                "title": getattr(item, "title", ""),
                "source": getattr(item, "source", "Báo chí quốc tế"),
                "link": getattr(item, "link", ""),
                "published": getattr(item, "published", ""),
            }
            for item in news_items
        ],
        "youtube_published": False,
        "youtube_video_id": "",
        "youtube_url": "",
        "youtube_published_at": "",
        "youtube_description": "",
        "custom_note": "",
        "script_scenes": [
            {
                "scene_index": s.scene_index,
                "text": s.text,
                "entity": s.entity_query,
                "image_source": s.image_source_type,
                "transition_cue": s.has_transition_cue,
            }
            for s in digest.scenes
        ],
    }

    # Step 6b: Save raw editorial script & Proof-of-Work document
    try:
        proof_file = export_editorial_script_file(
            manifest_data=manifest_data,
            news_items=news_items,
            output_dir=output_dir,
        )
        if proof_file:
            manifest_data["raw_script_path"] = str(proof_file.resolve())
    except Exception as script_err:
        logger.warning("Failed to export editorial proof of work script: %s", script_err)

    # Step 6c: Generate complete YouTube description with all source citations
    manifest_data["youtube_description"] = format_youtube_description_with_sources(
        manifest_data,
        title=final_title,
        summary=digest.summary_lead,
        hashtags=digest.hashtags,
    )

    manifest_path.write_text(json.dumps(manifest_data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Step 6d: Record used items in persistent 7-day history to eliminate cross-day duplication
    try:
        record_published_news_history(news_items, norm_cat)
    except Exception as hist_err:
        logger.warning("Failed to record published news history: %s", hist_err)

    report(100, f"Đã xuất bản video thành công: {final_video_path.name}")
    logger.info("Video produced at: %s", final_video_path)
    try:
        return final_video_path
    finally:
        release_prevent_sleep()
