"""
抖音评论区爬虫 — 核心模块
基于 Playwright 浏览器自动化，双重提取策略：
  1. 拦截评论 API 响应（优先，可获取完整数据含抖音号）
  2. 直接从页面 DOM 提取（兜底，只含昵称和可见内容）
"""

import re
import time
from playwright.sync_api import sync_playwright

import config


class DouyinCommentCrawler:
    """抖音视频评论区爬虫"""

    def __init__(self, headless=False):
        self.headless = headless
        self.playwright = None
        self.context = None

    def parse_share_text(self, user_input: str) -> str:
        """解析用户输入：分享文案/短链接/标准URL -> 可导航URL"""
        short_link = re.search(r"https?://v\.douyin\.com/\S+", user_input)
        if short_link:
            return short_link.group(0).rstrip("/")

        if "douyin.com/video/" in user_input or "iesdouyin.com/share/video/" in user_input:
            return user_input.strip()

        url_match = re.search(r"https?://\S+", user_input)
        if url_match:
            return url_match.group(0).rstrip("/")

        if re.match(r"^\d{15,20}$", user_input.strip()):
            return f"https://www.douyin.com/video/{user_input.strip()}"

        raise ValueError(f"无法识别输入格式: {user_input[:100]}...")

    def crawl(self, user_input: str) -> tuple:
        """
        返回 (video_url, api_comments, dom_comments)
        api_comments: 从API拦截到的（含抖音号/UID）
        dom_comments: 从DOM读取的（兜底数据）
        """
        url = self.parse_share_text(user_input)
        print(f"[信息] 解析输入 -> {url[:80]}...")

        self.playwright = sync_playwright().start()

        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=config.BROWSER_DATA_DIR,
            headless=self.headless,
            viewport={"width": config.VIEWPORT_WIDTH, "height": config.VIEWPORT_HEIGHT},
            user_agent=config.USER_AGENT,
            locale="zh-CN",
        )
        page = self.context.new_page()

        # ---- 在导航之前就注册拦截器 ----
        api_collected = {}

        def on_response(response):
            url_lower = response.url.lower()
            # 匹配多种可能的评论 API 路径
            if not any(kw in url_lower for kw in ["comment/list", "comment_list"]):
                return
            if "/reply" in url_lower:  # 跳过二级回复接口
                return
            try:
                data = response.json()
            except Exception:
                return

            comments_list = data.get("comments")
            if not comments_list:
                return

            for c in comments_list:
                cid = c.get("cid")
                if not cid or cid in api_collected:
                    continue
                api_collected[cid] = self._extract_comment_data(c)

        page.on("response", on_response)
        # ---------------------------------

        try:
            # 导航到视频页
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            final_url = page.url
            aweme_id = self._extract_aweme_id(final_url)
            video_url = f"https://www.douyin.com/video/{aweme_id}"
            print(f"[信息] 视频ID: {aweme_id}")

            # 如果重定向到了 share 页，跳到标准页
            if "/share/video/" in final_url or "iesdouyin.com" in final_url:
                print(f"[信息] 跳转到标准视频页...")
                page.goto(video_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000)

            # 处理登录
            self._handle_login(page)

            # 尝试打开评论区
            self._open_comment_panel(page)

            # 滚动加载（API拦截 + DOM兜底）
            self._scroll_to_load_comments(page, api_collected)

            # 从 DOM 读取作为兜底
            dom_comments = self._extract_from_dom(page)

            print(f"[信息] API拦截: {len(api_collected)} 条, DOM读取: {len(dom_comments)} 条")
            return video_url, list(api_collected.values()), dom_comments

        finally:
            page.remove_listener("response", on_response)
            page.close()

    def _extract_aweme_id(self, url: str) -> str:
        for pattern in [r"/video/(\d+)", r"/share/video/(\d+)"]:
            m = re.search(pattern, url)
            if m:
                return m.group(1)
        m = re.search(r"(\d{15,20})", url)
        if m:
            return m.group(1)
        raise ValueError(f"无法提取视频ID: {url}")

    def _handle_login(self, page):
        """检测并等待用户登录"""
        for _ in range(3):  # 最多尝试 3 次检测
            current_url = page.url
            if "login" in current_url.lower() or "passport" in current_url.lower():
                print("=" * 50)
                print("[登录] 请在浏览器窗口中扫码登录")
                print(f"[登录] 等待 {config.LOGIN_TIMEOUT} 秒...")
                print("=" * 50)
                start = time.time()
                while time.time() - start < config.LOGIN_TIMEOUT:
                    try:
                        if "/video/" in page.url:
                            print("[登录] 登录成功！")
                            page.wait_for_timeout(2000)
                            return
                    except Exception:
                        pass
                    time.sleep(1)
                print("[警告] 登录超时，尝试继续...")
                return
            time.sleep(2)

    def _open_comment_panel(self, page):
        """确保评论区是打开状态"""
        print("[信息] 检查评论区状态...")

        # 多种方式尝试打开评论区
        attempts = [
            # 方法1: data-e2e 属性
            ('[data-e2e="feed-comment-icon"]', "评论图标(data-e2e)"),
            ('[data-e2e="comment-icon"]', "评论图标(comment-icon)"),
            # 方法2: 点击评论数区域
            ('[class*="comment" i]', "评论区元素"),
            # 方法3: XPath 文本匹配
            ('//*[contains(text(), "评论")]', "评论文字"),
        ]

        for selector, desc in attempts:
            try:
                el = page.locator(selector).first
                if el.is_visible(timeout=2000):
                    el.click()
                    print(f"[信息] 点击了 {desc}")
                    page.wait_for_timeout(2000)
                    break
            except Exception:
                continue

    def _scroll_to_load_comments(self, page, api_collected: dict):
        """滚动评论区触发加载，同时拦截API"""
        print("[信息] 开始滚动加载评论区...")
        no_new = 0
        last_total = 0

        for i in range(config.MAX_SCROLL_ATTEMPTS):
            # 多种滚动策略
            # 1. 查找评论区容器并滚动
            try:
                page.evaluate("""
                    const container = document.querySelector(
                        '[class*="comment-list" i], [class*="CommentList" i], ' +
                        '[data-e2e="comment-list"], [class*="comment-container" i]'
                    );
                    if (container) {
                        container.scrollTop += 800;
                    } else {
                        window.scrollBy(0, 600);
                    }
                """)
            except Exception:
                page.evaluate("window.scrollBy(0, 600)")

            # 2. 滚轮事件
            try:
                page.mouse.wheel(0, 400)
            except Exception:
                pass

            page.wait_for_timeout(config.SCROLL_PAUSE_MS)

            total = len(api_collected)
            if total > last_total:
                print(f"[进度] API拦截: {total} 条评论...")
                last_total = total
                no_new = 0
            else:
                no_new += 1
                if no_new >= config.NO_NEW_COMMENTS_THRESHOLD:
                    print(f"[信息] 连续{config.NO_NEW_COMMENTS_THRESHOLD}次无新评论, 停止滚动")
                    break

        print(f"[信息] 滚动完成, API共拦截 {len(api_collected)} 条评论")

    def _extract_comment_data(self, c: dict) -> dict:
        """从API响应提取单条评论"""
        images = []
        for img in (c.get("image_list") or []):
            origin = img.get("origin_url") or {}
            urls = origin.get("url_list") or []
            if urls:
                images.append(urls[0])

        stickers = []
        sticker = c.get("sticker") or {}
        static = sticker.get("static_url") or {}
        sticker_urls = static.get("url_list") or []
        if sticker_urls:
            stickers.append(sticker_urls[0])

        user = c.get("user") or {}
        avatar_list = (user.get("avatar_thumb") or {}).get("url_list") or []

        return {
            "cid": c.get("cid", ""),
            "text": c.get("text", ""),
            "images": images,
            "stickers": stickers,
            "digg_count": c.get("digg_count", 0),
            "create_time": c.get("create_time", 0),
            "ip_label": c.get("ip_label", ""),
            "reply_comment_total": c.get("reply_comment_total", 0),
            "nickname": user.get("nickname", ""),
            "uid": user.get("uid", ""),
            "unique_id": user.get("unique_id", ""),
            "short_id": user.get("short_id", ""),
            "avatar": avatar_list[0] if avatar_list else "",
            "source": "api",
        }

    def _extract_from_dom(self, page) -> list[dict]:
        """
        从页面DOM直接提取评论（兜底方案）
        只能获取到页面上渲染出来的内容，没有 unique_id/uid
        """
        try:
            results = page.evaluate("""
                () => {
                    const comments = [];
                    // 使用 data-e2e 属性查找评论项
                    const items = document.querySelectorAll('[data-e2e="comment-item"]');
                    const seen = new Set();

                    items.forEach(item => {
                        // 跳过嵌套的二级评论
                        if (item.parentElement && item.parentElement.closest('[data-e2e="comment-item"]')) {
                            return;
                        }

                        const nameEl = item.querySelector('[data-e2e="feed-author-name"], [class*="author" i], [class*="nickname" i]');
                        const contentEl = item.querySelector('[data-e2e="comment-content"], [class*="comment-content" i], [class*="commentText" i]');
                        const likeEl = item.querySelector('[data-e2e="like-count"], [class*="like" i], [class*="digg" i]');
                        const timeEl = item.querySelector('[data-e2e="comment-time"], [class*="time" i], [class*="date" i]');

                        const nickname = nameEl ? nameEl.innerText.trim() : '';
                        const text = contentEl ? contentEl.innerText.trim() : item.innerText.trim();
                        const likeText = likeEl ? likeEl.innerText.trim() : '0';
                        const timeText = timeEl ? timeEl.innerText.trim() : '';

                        // 去重
                        const key = nickname + '|' + text.substring(0, 50);
                        if (seen.has(key)) return;
                        seen.add(key);

                        const digg_count = parseInt(likeText.replace(/[^0-9]/g, '')) || 0;

                        comments.push({
                            cid: '',
                            text: text,
                            images: [],
                            stickers: [],
                            digg_count: digg_count,
                            create_time: 0,
                            ip_label: '',
                            reply_comment_total: 0,
                            nickname: nickname,
                            uid: '',
                            unique_id: '',
                            short_id: '',
                            avatar: '',
                            source: 'dom',
                        });
                    });

                    return comments;
                }
            """)
            return results
        except Exception as e:
            print(f"[警告] DOM提取失败: {e}")
            return []

    def close(self):
        """关闭浏览器资源"""
        if self.context:
            self.context.close()
        if self.playwright:
            self.playwright.stop()
