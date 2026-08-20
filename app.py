"""
MyReadingManga Cloud Proxy Downloader - Streamlit Web App
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

def fetch_html_via_proxy(target_url: str) -> tuple[str, str]:
    """Cơ chế xoay vòng proxy công khai để bypass chặn IP máy chủ."""
    proxies = [
        # Jina AI Reader
        f"https://r.jina.ai/{target_url}",
        # AllOrigins Proxy
        f"https://api.allorigins.win/raw?url={urllib.parse.quote(target_url)}",
        # Codetabs Proxy
        f"https://api.codetabs.com/v1/proxy?quest={urllib.parse.quote(target_url)}"
    ]

    for p_url in proxies:
        try:
            r = requests.get(p_url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200 and len(r.text) > 500:
                return r.text, p_url
        except Exception:
            continue

    # Fallback gửi request trực tiếp
    try:
        r = requests.get(target_url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://myreadingmanga.info/"
        })
        if r.status_code == 200:
            return r.text, "Direct Request"
    except Exception:
        pass

    return "", "Failed"

def fetch_mrm_images(first_page_url: str) -> tuple[list[str], str, list[str]]:
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
        html, source = fetch_html_via_proxy(page_url)

        if not html:
            logs.append(f"Trang {current_page} [{page_url}] -> Không thể tải qua Proxy lẫn Direct.")
            break

        logs.append(f"Trang {current_page} -> Tải thành công qua [{source}]")
        soup = BeautifulSoup(html, "html.parser")

        if current_page == 1:
            title_tag = soup.select_one("h1.entry-title, h1")
            if title_tag:
                comic_title = sanitize_filename(title_tag.get_text(strip=True))
            else:
                path = urllib.parse.urlparse(base_url).path.strip("/").split("/")
                comic_title = sanitize_filename(path[0] if path else "MRM_Chapter")

        entry_content = soup.select_one("div.entry-content, div.post-content, article, body")
        if not entry_content:
            break

        found_in_page = 0
        img_tags = entry_content.select("img")

        for img in img_tags:
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
                    if not any(bad in src.lower() for bad in ["banner", "ads", "icon", "placeholder", "svg"]):
                        seen.add(src)
                        all_images.append(src)
                        found_in_page += 1

        # Fallback quét bằng Regex nếu DOM bị proxy format lại dạng Markdown
        if found_in_page == 0:
            raw_matches = re.findall(r'https?://[^\s"\'<>)]+?\.(?:jpg|jpeg|png|webp)', html, re.IGNORECASE)
            for m in raw_matches:
                clean_m = m.split("?")[0]
                if clean_m not in seen and not any(bad in clean_m.lower() for bad in ["avatar", "logo", "icon", "theme"]):
                    seen.add(clean_m)
                    all_images.append(clean_m)
                    found_in_page += 1

        logs.append(f"-> Quét được {found_in_page} ảnh tại trang {current_page}")

        if found_in_page == 0:
            break

        if not soup.select(".entry-pagination, .post-page-numbers, .pagination, a[href*='/" + str(current_page + 1) + "/']"):
            break

        current_page += 1

    return all_images, comic_title, logs

def download_image(img_url: str, ref_url: str) -> bytes | None:
    """Tải trực tiếp ảnh từ CDN lưu trữ (hầu hết CDN ảnh không chặn IP datacenter)."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": ref_url
    }
    try:
        r = requests.get(img_url, headers=headers, timeout=25)
        if r.status_code == 200:
            return r.content
    except Exception:
        pass

    # Fallback qua image proxy nếu CDN ảnh cũng chặn
    try:
        p_img = f"https://api.allorigins.win/raw?url={urllib.parse.quote(img_url)}"
        r = requests.get(p_img, timeout=25)
        if r.status_code == 200:
            return r.content
    except Exception:
        pass

    return None

# --- GIAO DIỆN STREAMLIT ---
st.set_page_config(page_title="MyReadingManga Downloader", page_icon="📖", layout="centered")
st.title("📖 MyReadingManga Cloud Downloader")

url_input = st.text_input(
    "👉 Nhập link bài viết (URL):", 
    placeholder="https://myreadingmanga.info/sakumoto-ayu-big-cat-love-eng/"
)

if st.button("🚀 Bắt đầu Quét & Tải", type="primary"):
    if not url_input or "http" not in url_input:
        st.warning("Vui lòng nhập đường link bài viết hợp lệ!")
    else:
        st.info("Đang bypass IP và bóc tách danh sách ảnh...")

        images, comic_title, logs = fetch_mrm_images(url_input)

        with st.expander("🔍 Xem chi tiết Log kết nối", expanded=False):
            for l in logs:
                st.write(l)

        if not images:
            st.error("Không tìm thấy ảnh hoặc trang web đích đang chặn hoàn toàn kết nối. Vui lòng thử lại sau giây lát.")
        else:
            st.success(f"Tìm thấy {len(images)} ảnh! Đang tải và đóng gói ZIP...")

            zip_buffer = io.BytesIO()
            progress_bar = st.progress(0)
            status_text = st.empty()

            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for idx, img_url in enumerate(images, 1):
                    ext = img_url.split(".")[-1].lower()
                    if ext not in ["jpg", "jpeg", "png", "webp"]:
                        ext = "jpg"
                    fname = f"{str(idx).zfill(4)}.{ext}"

                    content = download_image(img_url, url_input)
                    if content:
                        zip_file.writestr(fname, content)

                    progress = idx / len(images)
                    progress_bar.progress(progress)
                    status_text.text(f"Đang xử lý: {idx}/{len(images)} ảnh")

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
