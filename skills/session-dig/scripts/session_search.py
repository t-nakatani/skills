#!/usr/bin/env python3
"""Search and explore Claude Code session history.

Sessions are stored as append-only JSONL files in ~/.claude/projects/<project-key>/.
Even after context compaction, all original messages remain in the JSONL.
"""

import json
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime


def get_project_sessions_dir(working_dir: str | None = None) -> Path:
    """Resolve the sessions directory for the current project.

    Claude Code maps /Users/foo/my_project to ~/.claude/projects/-Users-foo-my-project/
    Both / and _ are replaced with -.
    """
    if working_dir is None:
        working_dir = os.getcwd()
    import re

    project_key = re.sub(r"[/_]", "-", working_dir)
    projects_dir = Path.home() / ".claude" / "projects"
    candidate = projects_dir / project_key
    if candidate.exists():
        return candidate
    # Fallback: fuzzy match against existing directories
    if projects_dir.exists():
        normalized = project_key.lower()
        for d in projects_dir.iterdir():
            if d.is_dir() and d.name.lower() == normalized:
                return d
    return candidate


def parse_message_content(msg: dict) -> str:
    """Extract text content from a message object."""
    content = msg.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict):
                parts.append(c.get("text", ""))
            else:
                parts.append(str(c))
        return " ".join(parts)
    return str(content)


def classify_message(text: str) -> tuple[str, str]:
    """Classify a user message and return (type, display_text)."""
    if text.startswith("<task-notification>"):
        return "task-notification", "[task notification]"
    if text.startswith("<command-message>"):
        if "<command-name>" in text:
            cmd = text.split("<command-name>")[-1].split("</command-name>")[0]
            return "command", f"[command: {cmd}]"
        return "command", "[command]"
    if "This session is being continued from a previous conversation" in text:
        return "summary", "[compaction summary]"
    if text.startswith("[Request interrupted"):
        return "interrupted", text.strip()
    return "user", text


def search_sessions(
    sessions_dir: Path, keywords: list[str], max_results: int = 10
) -> list[dict]:
    """Search sessions for keyword matches in user messages (AND logic)."""
    results = []
    keywords_lower = [kw.lower() for kw in keywords]

    for f in sessions_dir.glob("*.jsonl"):
        try:
            size = f.stat().st_size
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            session_id = f.stem

            matched_messages = []
            first_user_msg = ""
            user_msg_count = 0

            with open(f) as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    if obj.get("type") != "user":
                        continue
                    msg = obj.get("message", {})
                    if not isinstance(msg, dict) or msg.get("role") != "user":
                        continue

                    text = parse_message_content(msg)
                    if not text.strip():
                        continue

                    msg_type, _ = classify_message(text)
                    if msg_type in ("task-notification", "command", "summary"):
                        continue

                    user_msg_count += 1
                    if not first_user_msg:
                        first_user_msg = text[:200]

                    text_lower = text.lower()
                    if all(kw in text_lower for kw in keywords_lower):
                        matched_messages.append(text[:300])

            if matched_messages:
                results.append(
                    {
                        "session_id": session_id,
                        "size_kb": round(size / 1024, 1),
                        "modified": mtime.strftime("%Y-%m-%d %H:%M"),
                        "user_msg_count": user_msg_count,
                        "match_count": len(matched_messages),
                        "first_user_msg": first_user_msg,
                        "first_match": matched_messages[0],
                    }
                )
        except Exception:
            continue

    results.sort(key=lambda x: x["modified"], reverse=True)
    return results[:max_results]


def list_sessions(sessions_dir: Path, recent: int = 15) -> list[dict]:
    """List recent sessions with first user message as preview."""
    sessions = []
    for f in sessions_dir.glob("*.jsonl"):
        try:
            size = f.stat().st_size
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            session_id = f.stem

            first_msg = ""
            user_msg_count = 0
            has_compaction = False

            with open(f) as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    if obj.get("type") != "user":
                        continue
                    msg = obj.get("message", {})
                    if not isinstance(msg, dict) or msg.get("role") != "user":
                        continue
                    text = parse_message_content(msg)
                    if not text.strip():
                        continue

                    msg_type, _ = classify_message(text)
                    if msg_type == "summary":
                        has_compaction = True
                        continue
                    if msg_type in ("task-notification", "command"):
                        continue

                    user_msg_count += 1
                    if not first_msg:
                        first_msg = text[:200]

            sessions.append(
                {
                    "session_id": session_id,
                    "size_kb": round(size / 1024, 1),
                    "modified": mtime.strftime("%Y-%m-%d %H:%M"),
                    "user_msg_count": user_msg_count,
                    "has_compaction": has_compaction,
                    "preview": first_msg,
                }
            )
        except Exception:
            continue

    sessions.sort(key=lambda x: x["modified"], reverse=True)
    return sessions[:recent]


def show_session(sessions_dir: Path, session_id: str) -> dict:
    """Show user messages from a specific session."""
    fpath = sessions_dir / f"{session_id}.jsonl"
    if not fpath.exists():
        return {"error": f"Session {session_id} not found"}

    messages = []
    has_compaction = False

    with open(fpath) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("type") != "user":
                continue
            msg = obj.get("message", {})
            if not isinstance(msg, dict) or msg.get("role") != "user":
                continue
            text = parse_message_content(msg)
            if not text.strip():
                continue

            msg_type, display_text = classify_message(text)
            if msg_type == "summary":
                has_compaction = True

            messages.append(
                {
                    "index": len(messages),
                    "type": msg_type,
                    "text": display_text[:500],
                }
            )

    size = fpath.stat().st_size
    mtime = datetime.fromtimestamp(fpath.stat().st_mtime)

    return {
        "session_id": session_id,
        "size_kb": round(size / 1024, 1),
        "modified": mtime.strftime("%Y-%m-%d %H:%M"),
        "has_compaction": has_compaction,
        "total_messages": len(messages),
        "messages": messages,
    }


def main():
    parser = argparse.ArgumentParser(description="Search Claude Code session history")
    parser.add_argument(
        "--dir", help="Project sessions directory (auto-detected from cwd if omitted)"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    sp_search = subparsers.add_parser("search", help="Search sessions by keyword")
    sp_search.add_argument(
        "keywords", nargs="+", help="Keywords to search for (AND logic)"
    )
    sp_search.add_argument("--max", type=int, default=10, help="Max results")

    sp_list = subparsers.add_parser("list", help="List recent sessions")
    sp_list.add_argument(
        "--recent", type=int, default=15, help="Number of recent sessions"
    )

    sp_show = subparsers.add_parser("show", help="Show user messages from a session")
    sp_show.add_argument("session_id", help="Session ID (UUID)")

    args = parser.parse_args()

    if args.dir:
        sessions_dir = Path(args.dir)
    else:
        sessions_dir = get_project_sessions_dir()

    if not sessions_dir.exists():
        print(
            json.dumps({"error": f"Sessions directory not found: {sessions_dir}"}),
        )
        sys.exit(1)

    if args.command == "search":
        results = search_sessions(sessions_dir, args.keywords, args.max)
        print(json.dumps(results, indent=2, ensure_ascii=False))
    elif args.command == "list":
        results = list_sessions(sessions_dir, args.recent)
        print(json.dumps(results, indent=2, ensure_ascii=False))
    elif args.command == "show":
        result = show_session(sessions_dir, args.session_id)
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
