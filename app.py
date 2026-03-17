import json
import os
import re
import threading
import tkinter as tk
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, ttk
from urllib import error, parse, request


API_BASE = "https://api.github.com"
PER_PAGE = 100
CACHE_DIR = Path(".cache")


@dataclass
class Follower:
    login: str
    name: str
    html_url: str

    @property
    def display_name(self) -> str:
        return self.name or self.login


def normalize_text(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())


def extract_username(value: str) -> str:
    cleaned = value.strip()
    if "github.com/" not in cleaned:
        return cleaned.strip("/")

    parsed = parse.urlparse(cleaned)
    parts = [part for part in parsed.path.split("/") if part]
    return parts[0] if parts else ""


def is_subsequence(needle: str, haystack: str) -> bool:
    if not needle:
        return True

    index = 0
    for ch in haystack:
        if ch == needle[index]:
            index += 1
            if index == len(needle):
                return True
    return False


def build_search_keys(follower: Follower) -> list[str]:
    login = normalize_text(follower.login)
    name = normalize_text(follower.name)
    raw_parts = re.split(r"[^A-Za-z0-9]+", follower.name or "")
    parts = [normalize_text(part) for part in raw_parts if normalize_text(part)]
    initials = "".join(part[0] for part in parts if part)

    keys = [login, name, initials]
    return [key for key in keys if key]


def match_score(keyword: str, follower: Follower) -> int | None:
    if not keyword:
        return 0

    normalized_keyword = normalize_text(keyword)
    if not normalized_keyword:
        return 0

    keys = build_search_keys(follower)
    best_score = None

    for key in keys:
        if key == normalized_keyword:
            score = 100
        elif key.startswith(normalized_keyword):
            score = 85
        elif normalized_keyword in key:
            score = 70
        elif is_subsequence(normalized_keyword, key):
            score = 55
        else:
            continue

        if best_score is None or score > best_score:
            best_score = score

    return best_score


class GitHubAPI:
    def __init__(self) -> None:
        self.token = os.getenv("GITHUB_TOKEN", "").strip()

    def _request_json(self, path: str, query: dict[str, str | int] | None = None) -> tuple[object, dict[str, str]]:
        url = f"{API_BASE}{path}"
        if query:
            url += "?" + parse.urlencode(query)

        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "github-followers-search-app",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        req = request.Request(url, headers=headers)
        with request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body), dict(resp.headers.items())

    def _read_pages(self, username: str) -> list[dict]:
        followers: list[dict] = []
        page = 1

        while True:
            data, _ = self._request_json(
                f"/users/{username}/followers",
                {"per_page": PER_PAGE, "page": page},
            )
            page_items = data if isinstance(data, list) else []
            if not page_items:
                break

            followers.extend(page_items)
            if len(page_items) < PER_PAGE:
                break
            page += 1

        return followers

    def _fetch_user_name(self, login: str) -> str:
        try:
            data, _ = self._request_json(f"/users/{login}")
        except error.HTTPError:
            return ""
        except error.URLError:
            return ""

        if isinstance(data, dict):
            return (data.get("name") or "").strip()
        return ""

    def _cache_path(self, username: str) -> Path:
        CACHE_DIR.mkdir(exist_ok=True)
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", username)
        return CACHE_DIR / f"{safe_name}_followers.json"

    def load_cached_followers(self, username: str) -> list[Follower]:
        cache_path = self._cache_path(username)
        if not cache_path.exists():
            return []

        with cache_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)

        followers = []
        for item in data:
            followers.append(
                Follower(
                    login=item.get("login", ""),
                    name=item.get("name", ""),
                    html_url=item.get("html_url", ""),
                )
            )
        return followers

    def save_cached_followers(self, username: str, followers: list[Follower]) -> None:
        cache_path = self._cache_path(username)
        payload = [
            {"login": follower.login, "name": follower.name, "html_url": follower.html_url}
            for follower in followers
        ]
        with cache_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)

    def load_followers(self, username: str, progress_callback) -> list[Follower]:
        raw_followers = self._read_pages(username)
        followers: list[Follower] = []
        total = len(raw_followers)

        for index, item in enumerate(raw_followers, start=1):
            login = item.get("login", "").strip()
            html_url = item.get("html_url", "").strip()
            if not login:
                continue

            progress_callback(f"正在获取姓名 {index}/{total}: {login}")
            name = self._fetch_user_name(login)
            followers.append(Follower(login=login, name=name, html_url=html_url))

        self.save_cached_followers(username, followers)
        return followers


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("GitHub Followers Search")
        self.root.geometry("940x620")

        self.api = GitHubAPI()
        self.followers: list[Follower] = []
        self.filtered: list[Follower] = []

        self.username_var = tk.StringVar(value="dufe-fintech")
        self.keyword_var = tk.StringVar()
        self.status_var = tk.StringVar(value="输入 GitHub 用户名或组织名后，点击“加载 Followers”。")

        self._build_ui()
        self.keyword_var.trace_add("write", self._on_keyword_change)

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=16)
        container.pack(fill=tk.BOTH, expand=True)

        top = ttk.Frame(container)
        top.pack(fill=tk.X)

        ttk.Label(top, text="GitHub 用户/组织").pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self.username_var, width=28).pack(side=tk.LEFT, padx=(8, 12))
        ttk.Button(top, text="加载 Followers", command=self.load_followers).pack(side=tk.LEFT)

        search_bar = ttk.Frame(container, padding=(0, 14, 0, 10))
        search_bar.pack(fill=tk.X)

        ttk.Label(search_bar, text="关键词").pack(side=tk.LEFT)
        ttk.Entry(search_bar, textvariable=self.keyword_var, width=32).pack(side=tk.LEFT, padx=(8, 12))
        ttk.Label(search_bar, text="支持子串和缩写式模糊匹配，例如: wfs").pack(side=tk.LEFT)

        columns = ("login", "name", "url")
        self.tree = ttk.Treeview(container, columns=columns, show="headings", height=22)
        self.tree.heading("login", text="Login")
        self.tree.heading("name", text="Name")
        self.tree.heading("url", text="Profile URL")
        self.tree.column("login", width=180, anchor=tk.W)
        self.tree.column("name", width=220, anchor=tk.W)
        self.tree.column("url", width=470, anchor=tk.W)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<Double-1>", self.open_selected_profile)

        bottom = ttk.Frame(container, padding=(0, 10, 0, 0))
        bottom.pack(fill=tk.X)
        ttk.Label(bottom, textvariable=self.status_var).pack(side=tk.LEFT)

    def load_followers(self) -> None:
        username = extract_username(self.username_var.get())
        if not username:
            messagebox.showwarning("缺少用户名", "请输入 GitHub 用户名或组织名。")
            return

        self.username_var.set(username)
        cached = self.api.load_cached_followers(username)
        if cached:
            self.followers = cached
            self.apply_filter()
            self.status_var.set(f"已从本地缓存加载 {len(cached)} 个 followers，后台继续刷新...")
        else:
            self.status_var.set("正在加载 followers，请稍候...")

        worker = threading.Thread(target=self._load_followers_worker, args=(username,), daemon=True)
        worker.start()

    def _load_followers_worker(self, username: str) -> None:
        try:
            self._set_status(f"正在拉取 {username} 的 followers 列表...")
            followers = self.api.load_followers(username, self._set_status)
        except error.HTTPError as exc:
            if exc.code == 404:
                self._show_error("未找到该用户/组织，请检查名字是否正确。")
            elif exc.code == 403:
                self._show_error("GitHub API 限流了。可以设置环境变量 GITHUB_TOKEN 后重试。")
            else:
                self._show_error(f"GitHub API 请求失败，状态码: {exc.code}")
            return
        except error.URLError:
            self._show_error("网络请求失败，请检查网络后重试。")
            return
        except Exception as exc:
            self._show_error(f"程序出错: {exc}")
            return

        self.root.after(0, self._set_followers, followers)

    def _set_followers(self, followers: list[Follower]) -> None:
        self.followers = followers
        self.apply_filter()
        self.status_var.set(f"已加载 {len(self.followers)} 个 followers。")

    def _show_error(self, message: str) -> None:
        self.root.after(0, lambda: messagebox.showerror("加载失败", message))
        self._set_status(message)

    def _set_status(self, message: str) -> None:
        self.root.after(0, lambda: self.status_var.set(message))

    def _on_keyword_change(self, *_args) -> None:
        self.apply_filter()

    def apply_filter(self) -> None:
        keyword = self.keyword_var.get().strip()
        matches: list[tuple[int, Follower]] = []

        for follower in self.followers:
            score = match_score(keyword, follower)
            if score is None:
                continue
            matches.append((score, follower))

        matches.sort(key=lambda item: (-item[0], item[1].display_name.lower(), item[1].login.lower()))
        self.filtered = [follower for _, follower in matches]
        self._render_rows()

        if keyword:
            self.status_var.set(f"共找到 {len(self.filtered)} 个匹配结果。")
        elif self.followers:
            self.status_var.set(f"已显示全部 {len(self.followers)} 个 followers。")

    def _render_rows(self) -> None:
        for item_id in self.tree.get_children():
            self.tree.delete(item_id)

        for follower in self.filtered:
            self.tree.insert("", tk.END, values=(follower.login, follower.name, follower.html_url))

    def open_selected_profile(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return

        values = self.tree.item(selection[0], "values")
        if values and len(values) >= 3:
            webbrowser.open(values[2])


def main() -> None:
    root = tk.Tk()
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
