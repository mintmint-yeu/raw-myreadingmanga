"""
MyReadingManga Raw Downloader - Optimized Engine
"""

import io
import re
import zipfile
from urllib.parse import urlparse
import streamlit as st
from bs4 import BeautifulSoup
from curl_cffi import requests as cureq

def sanitize_filename(name: str) -> str:
    clean = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    return clean[:80] if clean else "MRM_Comic"

def fetch_mrm_images(first_page_url: str, cookie_str: str, custom_ua: str) -> tuple[list[str], str, list[str]]:
    ua = custom_ua.strip() if custom_ua.strip() else "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
        "Referer": "https://myreadingmanga.info/",
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
    }
    if cookie_str.strip():
        headers["Cookie"] = cookie_str.strip()

    # Chuẩn hoá URL gốc (xóa pagination thừa)
    base_url = re.sub(r'/\d+/?$', '/', first_page_url.strip())
    if not base_url.endswith("/"):
        base_url += "/"

    all_images = []
    seen = set()
    logs = []
    comic_title = "MRM_Comic"
    current_page = 1

    session = cureq.Session(impersonate="chrome124")

    while True:
        page_url = base_url if current_page == 1 else f"{base_url}{current_page}/"
        try:
            r = session.get(page_url, headers=headers, timeout=25)
            logs.append(f"Trang {current_page} [{page_url}] -> HTTP {r.status_code}")
            
            if r.status_code in (403, 404):
                if r.status_code == 403:
                    logs.append("⚠️ Cloudflare chặn (403). Hãy cập nhật Cookie và User-Agent mới nhất.")
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
        img_tags = entry_content.select("img")

        for img in img_tags:
            # Quét tất cả các thuộc tính chứa link ảnh có thể có
            candidates = [
                img.get("data-src"),
                img.get("data-lazy-src"),
                img.get("data-full-url"),
                img.get("data-original"),
                img.get("src")
            ]
            
            # Quét thêm từ srcset nếu có
            srcset = img.get("srcset") or img.get("data-srcset")
            if srcset:
                parts = [p.strip().split(" ")[0] for p in srcset.split(",") if p.strip()]
                if parts:
                    candidates.insert(0, parts[-1]) # Lấy ảnh có độ phân giải cao nhất

            src = None
            for c in candidates:
                if c and not c.startswith("data:image") and "avatar" not in c and "logo" not in c:
                    src = c.split("?")[0]
                    break

            if src:
                if src.startswith("//"):
                    src = "https:" + src
                if src.startswith("http") and src not in seen:
                    # Bỏ các ảnh icon/quảng cáo nhỏ
                    if not any(bad in src.lower() for bad in ["banner", "ads", "icon", "placeholder"]):
                        seen.add(src)
                        all_images.append(src)
                        found_in_page += 1

        logs.append(f"-> Tìm được {found_in_page} ảnh tại trang {current_page}")

        if found_in_page == 0:
            break

        # Kiểm tra xem có trang tiếp theo không
        has_next = soup.select(".entry-pagination, .post-page-numbers, .pagination, a[href*='/" + str(current_page + 1) + "/']")
        if not has_next:
            break

        current_page += 1

    return all_images, comic_title, logs

# --- GIAO DIỆN STREAMLIT ---
st.set_page_config(page_title="MyReadingManga Downloader", page_icon="📖", layout="centered")
st.title("📖 MyReadingManga Raw Downloader")

url_input = st.text_input(
    "👉 Nhập link bài viết (URL):", 
    placeholder="https://myreadingmanga.info/slug-truyen/..."
)

with st.expander("⚙️ Cấu hình Vượt Cloudflare (Bắt buộc nếu bị chặn)"):
    ua_input = st.text_input(
        "👉 Nhập User-Agent trình duyệt của bạn:",
        placeholder="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)... (Lấy từ DevTools)",
        help="Phải là User-Agent của đúng trình duyệt bạn đã dùng để lấy Cookie."
    )
    cookie_input = st.text_area(
        "👉 Nhập Header Cookie đầy đủ:", 
        placeholder="cf_clearance=...; các giá trị cookie khác...",
        help="F12 -> Thẻ Network -> F5 lại web -> Bấm vào request đầu tiên -> Copy toàn bộ chuỗi ở mục Cookie."
    )

if st.button("🚀 Bắt đầu Quét & Tải", type="primary"):
    if not url_input or "http" not in url_input:
        st.warning("Vui lòng nhập đường link bài viết hợp lệ!")
    else:
        st.info("Đang bóc tách dữ liệu...")
        
        images, comic_title, logs = fetch_mrm_images(url_input, cookie_input, ua_input)

        with st.expander("🔍 Xem Log tiến trình", expanded=False):
            for l in logs:
                st.write(l)

        if not images:
            st.error("Không lấy được ảnh! Hãy kiểm tra tab 'Log tiến trình' ở trên để xem website trả về lỗi gì.")
        else:
            st.success(f"Tìm thấy {len(images)} ảnh! Đang tải về và nén...")

            zip_buffer = io.BytesIO()
            progress_bar = st.progress(0)
            status_text = st.empty()

            session_down = cureq.Session(impersonate="chrome124")
            down_headers = {
                "Referer": url_input,
                "User-Agent": ua_input.strip() if ua_input.strip() else "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }
            if cookie_input.strip():
                down_headers["Cookie"] = cookie_input.strip()

            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for idx, img_url in enumerate(images, 1):
                    ext = img_url.split(".")[-1].lower()
                    if ext not in ["jpg", "jpeg", "png", "webp"]:
                        ext = "jpg"
                    fname = f"{str(idx).zfill(4)}.{ext}"

                    try:
                        r = session_down.get(img_url, headers=down_headers, timeout=30)
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