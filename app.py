"""
MyReadingManga Auto-Bypass Downloader - Streamlit Web App
"""

import io
import re
import zipfile
from urllib.parse import urlparse
import cloudscraper
import requests
import streamlit as st
from bs4 import BeautifulSoup

def sanitize_filename(name: str) -> str:
    clean = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    return clean[:80] if clean else "MRM_Comic"

def create_scraper_session():
    """Khởi tạo scraper tự động vượt Cloudflare JS Challenge."""
    return cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'darwin',
            'desktop': True
        },
        delay=10
    )

def fetch_mrm_images(first_page_url: str) -> tuple[list[str], str, list[str]]:
    scraper = create_scraper_session()

    # Chuẩn hoá URL bài viết
    base_url = re.sub(r'/\d+/?$', '/', first_page_url.strip())
    if not base_url.endswith("/"):
        base_url += "/"

    all_images = []
    seen = set()
    logs = []
    comic_title = "MRM_Comic"
    current_page = 1

    while True:
        page_url = base_url if current_page == 1 else f"{base_url}{current_page}/"
        try:
            r = scraper.get(page_url, timeout=30)
            logs.append(f"Trang {current_page} [{page_url}] -> HTTP {r.status_code}")

            if r.status_code in (403, 404):
                if r.status_code == 403:
                    logs.append("⚠️ Cloudflare chặn cứng IP máy chủ.")
                break

            html = r.text
        except Exception as e:
            logs.append(f"Lỗi kết nối trang {current_page}: {str(e)}")
            break

        soup = BeautifulSoup(html, "html.parser")

        if current_page == 1:
            title_tag = soup.select_one("h1.entry-title")
            if title_tag:
                comic_title = sanitize_filename(title_tag.get_text(strip=True))
            else:
                path = urlparse(base_url).path.strip("/").split("/")
                comic_title = sanitize_filename(path[0] if path else "MRM_Chapter")

        entry_content = soup.select_one("div.entry-content, div.post-content, article")
        if not entry_content:
            logs.append(f"Không tìm thấy khối nội dung bài viết ở trang {current_page}.")
            break

        found_in_page = 0
        for img in entry_content.select("img"):
            candidates = [
                img.get("data-src"),
                img.get("data-lazy-src"),
                img.get("data-full-url"),
                img.get("data-original"),
                img.get("src")
            ]

            srcset = img.get("srcset") or img.get("data-srcset")
            if srcset:
                parts = [p.strip().split(" ")[0] for p in srcset.split(",") if p.strip()]
                if parts:
                    candidates.insert(0, parts[-1])

            src = None
            for c in candidates:
                if c and not c.startswith("data:image") and "avatar" not in c and "logo" not in c:
                    src = c.split("?")[0]
                    break

            if src:
                if src.startswith("//"):
                    src = "https:" + src
                if src.startswith("http") and src not in seen:
                    if not any(bad in src.lower() for bad in ["banner", "ads", "icon", "placeholder"]):
                        seen.add(src)
                        all_images.append(src)
                        found_in_page += 1

        logs.append(f"-> Tìm được {found_in_page} ảnh tại trang {current_page}")

        if found_in_page == 0:
            break

        has_next = soup.select(".entry-pagination, .post-page-numbers, .pagination, a[href*='/" + str(current_page + 1) + "/']")
        if not has_next:
            break

        current_page += 1

    return all_images, comic_title, logs

# --- GIAO DIỆN STREAMLIT ---
st.set_page_config(page_title="MyReadingManga Downloader", page_icon="📖", layout="centered")
st.title("📖 MyReadingManga Downloader (Auto Bypass)")

url_input = st.text_input(
    "👉 Nhập link bài viết (URL):", 
    placeholder="https://myreadingmanga.info/sakumoto-ayu-big-cat-love-eng/"
)

if st.button("🚀 Bắt đầu Quét & Tải", type="primary"):
    if not url_input or "http" not in url_input:
        st.warning("Vui lòng nhập đường link bài viết hợp lệ!")
    else:
        st.info("Đang tự động vượt Cloudflare và quét toàn bộ danh sách ảnh...")

        images, comic_title, logs = fetch_mrm_images(url_input)

        with st.expander("🔍 Chi tiết Log kết nối", expanded=False):
            for l in logs:
                st.write(l)

        if not images:
            st.error("Không lấy được dữ liệu! Vui lòng kiểm tra Log kết nối.")
        else:
            st.success(f"Tìm thấy {len(images)} ảnh! Đang gom và nén ZIP...")

            zip_buffer = io.BytesIO()
            progress_bar = st.progress(0)
            status_text = st.empty()

            down_scraper = create_scraper_session()

            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for idx, img_url in enumerate(images, 1):
                    ext = img_url.split(".")[-1].lower()
                    if ext not in ["jpg", "jpeg", "png", "webp"]:
                        ext = "jpg"
                    fname = f"{str(idx).zfill(4)}.{ext}"

                    try:
                        r = down_scraper.get(img_url, headers={"Referer": url_input}, timeout=30)
                        if r.status_code == 200:
                            zip_file.writestr(fname, r.content)
                    except Exception:
                        pass

                    progress = idx / len(images)
                    progress_bar.progress(progress)
                    status_text.text(f"Đang nén: {idx}/{len(images)} ảnh")

            zip_buffer.seek(0)
            zip_filename = f"{comic_title}.zip"

            st.balloons()
            st.download_button(
                label="📥 TẢI FILE ZIP VỀ MÁY",
                data=zip_buffer,
                file_name=zip_filename,
                mime="application/zip",
                type="primary"
            )
