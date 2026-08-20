"""
MyReadingManga Jina/Markdown Parser Downloader - Streamlit Web App
"""

import io
import re
import zipfile
import urllib.parse
import requests
import streamlit as st
from bs4 import BeautifulSoup

def sanitize_filename(name: str) -> str:
    clean = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    return clean[:80] if clean else "MRM_Comic"

def fetch_content_via_jina(target_url: str) -> tuple[str, int]:
    """Sử dụng Jina AI Reader làm proxy đọc nội dung chống Cloudflare 403."""
    jina_url = f"https://r.jina.ai/{target_url}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "X-No-Cache": "true"
    }
    try:
        r = requests.get(jina_url, headers=headers, timeout=25)
        return r.text, r.status_code
    except Exception:
        return "", 500

def extract_images_from_markdown_or_html(content: str) -> list[str]:
    """Quét triệt để link ảnh từ cả cú pháp Markdown và HTML raw."""
    urls = []
    seen = set()

    # 1. Cú pháp Markdown: ![alt](url) hoặc [alt](url)
    md_matches = re.findall(r'!\[.*?\]\((https?://[^\s\)]+)\)', content)
    for u in md_matches:
        u_clean = u.split("?")[0]
        if u_clean not in seen:
            seen.add(u_clean)
            urls.append(u_clean)

    # 2. Cú pháp HTML <img> trong text
    soup = BeautifulSoup(content, "html.parser")
    for img in soup.select("img"):
        src = img.get("data-src") or img.get("src") or img.get("data-lazy-src") or ""
        if src.startswith("http"):
            src_clean = src.split("?")[0]
            if src_clean not in seen:
                seen.add(src_clean)
                urls.append(src_clean)

    # 3. Regex quét vét mọi URL có đuôi ảnh thông dụng
    raw_images = re.findall(r'https?://[^\s"\'<>\)\(\]\[]+\.(?:jpg|jpeg|png|webp)', content, re.IGNORECASE)
    for u in raw_images:
        u_clean = u.split("?")[0]
        if u_clean not in seen:
            seen.add(u_clean)
            urls.append(u_clean)

    # Lọc bỏ avatar, banner quảng cáo, icon hệ thống
    valid_images = []
    for u in urls:
        low = u.lower()
        if not any(bad in low for bad in ["avatar", "gravatar", "logo", "banner", "ads", "icon", "theme", "emoji", "pixel"]):
            valid_images.append(u)

    return valid_images

def parse_title_from_text(content: str, fallback_url: str) -> str:
    # Lấy tiêu đề từ cú pháp H1 Markdown (# Title) hoặc Title: Title
    title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    if title_match:
        return sanitize_filename(title_match.group(1))
    
    title_match_2 = re.search(r'Title:\s*(.+)', content, re.IGNORECASE)
    if title_match_2:
        return sanitize_filename(title_match_2.group(1))

    path = urllib.parse.urlparse(fallback_url).path.strip("/").split("/")
    return sanitize_filename(path[0] if path else "MRM_Comic")

def fetch_mrm_pages(first_page_url: str) -> tuple[list[str], str, list[str]]:
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
        content, status = fetch_content_via_jina(page_url)

        if status != 200 or not content or len(content) < 300:
            logs.append(f"Trang {current_page} [{page_url}] -> Dừng quét (HTTP {status})")
            break

        logs.append(f"Trang {current_page} -> Nhận dữ liệu thành công")

        if current_page == 1:
            comic_title = parse_title_from_text(content, base_url)

        page_images = extract_images_from_markdown_or_html(content)
        found_in_page = 0

        for img_url in page_images:
            if img_url not in seen:
                seen.add(img_url)
                all_images.append(img_url)
                found_in_page += 1

        logs.append(f"-> Bóc tách được {found_in_page} ảnh tại trang {current_page}")

        if found_in_page == 0:
            break

        # Kiểm tra xem văn bản có chứa phân trang trang tiếp theo không
        next_page_str = f"/{current_page + 1}/"
        if next_page_str not in content and f"Page {current_page + 1}" not in content:
            break

        current_page += 1

    return all_images, comic_title, logs

def download_image_bytes(img_url: str, referer: str) -> bytes | None:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": referer
    }
    # Tải trực tiếp
    try:
        r = requests.get(img_url, headers=headers, timeout=20)
        if r.status_code == 200 and len(r.content) > 1000:
            return r.content
    except Exception:
        pass

    # Fallback qua AllOrigins Proxy nếu CDN ảnh chặn
    try:
        proxy_url = f"https://api.allorigins.win/raw?url={urllib.parse.quote(img_url)}"
        r = requests.get(proxy_url, timeout=25)
        if r.status_code == 200 and len(r.content) > 1000:
            return r.content
    except Exception:
        pass

    return None

# --- GIAO DIỆN STREAMLIT ---
st.set_page_config(page_title="MyReadingManga Downloader", page_icon="📖", layout="centered")
st.title("📖 MyReadingManga Downloader")

url_input = st.text_input(
    "👉 Nhập link bài viết (URL):", 
    placeholder="https://myreadingmanga.info/sakumoto-ayu-big-cat-love-eng/"
)

if st.button("🚀 Bắt đầu Quét & Tải", type="primary"):
    if not url_input or "http" not in url_input:
        st.warning("Vui lòng nhập đường link bài viết hợp lệ!")
    else:
        st.info("Đang đọc nội dung và lọc ảnh...")

        images, comic_title, logs = fetch_mrm_pages(url_input)

        with st.expander("🔍 Chi tiết Log tiến trình", expanded=False):
            for l in logs:
                st.write(l)

        if not images:
            st.error("Không tìm thấy ảnh hợp lệ! Kiểm tra lại đường dẫn bài viết.")
        else:
            st.success(f"Bóc tách thành công {len(images)} ảnh! Đang nén file ZIP...")

            zip_buffer = io.BytesIO()
            progress_bar = st.progress(0)
            status_text = st.empty()

            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for idx, img_url in enumerate(images, 1):
                    ext = img_url.split(".")[-1].lower()
                    if ext not in ["jpg", "jpeg", "png", "webp"]:
                        ext = "jpg"
                    fname = f"{str(idx).zfill(4)}.{ext}"

                    data = download_image_bytes(img_url, url_input)
                    if data:
                        zip_file.writestr(fname, data)

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
