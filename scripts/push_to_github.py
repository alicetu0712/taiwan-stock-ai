"""
scripts/push_to_github.py — 不需要 git，直接用 GitHub API 上傳程式碼

執行：python3 scripts/push_to_github.py --token 你的PAT --repo taiwan-stock-ai
"""

import sys
import base64
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

SKIP_DIRS  = {".git", "__pycache__", "data", "logs", "reports", ".venv", "venv", "node_modules"}
SKIP_FILES = {".env", ".DS_Store", "*.pyc", "platform.db"}
SKIP_EXTS  = {".pyc", ".pyo", ".db", ".sqlite", ".xlsx", ".log"}

def should_skip(path: Path) -> bool:
    for part in path.parts:
        if part in SKIP_DIRS:
            return True
    if path.name in SKIP_FILES:
        return True
    if path.suffix in SKIP_EXTS:
        return True
    return False


def collect_files(base: Path):
    files = {}
    for p in sorted(base.rglob("*")):
        if p.is_file() and not should_skip(p.relative_to(base)):
            rel = str(p.relative_to(base))
            try:
                content = p.read_bytes()
                files[rel] = content
            except Exception as e:
                print(f"  跳過 {rel}：{e}")
    return files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", required=True, help="GitHub Personal Access Token")
    parser.add_argument("--repo",  default="taiwan-stock-ai", help="Repo 名稱")
    parser.add_argument("--user",  default=None, help="GitHub 帳號（留空自動偵測）")
    parser.add_argument("--private", action="store_true", default=True)
    args = parser.parse_args()

    from github import Github, GithubException

    print("連接 GitHub...")
    g    = Github(args.token)
    user = g.get_user()
    username = args.user or user.login
    print(f"登入成功：{username}")

    # 建立 repo
    try:
        repo = user.create_repo(
            args.repo,
            description="AI Taiwan Equity Research Platform v6.0",
            private=args.private,
            auto_init=False,
        )
        print(f"建立 repo：{repo.html_url}")
    except GithubException as e:
        if "already exists" in str(e):
            repo = g.get_repo(f"{username}/{args.repo}")
            print(f"Repo 已存在，繼續上傳：{repo.html_url}")
        else:
            print(f"建立 repo 失敗：{e}")
            sys.exit(1)

    # 收集檔案
    base = Path(__file__).parent.parent
    files = collect_files(base)
    print(f"共 {len(files)} 個檔案準備上傳")

    # 上傳
    ok = err = 0
    for i, (rel_path, content) in enumerate(files.items(), 1):
        try:
            # 試著取得現有檔案（更新用）
            try:
                existing = repo.get_contents(rel_path)
                repo.update_file(rel_path, f"update {rel_path}", content, existing.sha)
            except GithubException:
                repo.create_file(rel_path, f"add {rel_path}", content)
            ok += 1
            if i % 10 == 0 or i == len(files):
                print(f"  [{i}/{len(files)}] {rel_path}")
        except Exception as e:
            err += 1
            print(f"  ❌ {rel_path}：{e}")

    print(f"\n✅ 上傳完成：{ok} 成功，{err} 失敗")
    print(f"Repo URL：{repo.html_url}")
    print(f"\n下一步：去 https://share.streamlit.io 部署這個 repo")
    print(f"  Main file：dashboard/app.py")


if __name__ == "__main__":
    main()
