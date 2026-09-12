import argparse
import base64
import email.mime.text
import json
import os
import shutil
import subprocess
import sys
import tempfile

_AUTH_KEYWORDS = (
    "Access denied",
    "No credentials",
    "auth login",
    "GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE",
    "invalid_grant",
    "Token has been expired or revoked",
    "insufficient authentication scopes",
)


def _find_gws() -> str:
    command = os.environ.get("GWS_COMMAND", "gws")
    found = shutil.which(command)
    if found:
        return found
    candidate = os.path.expandvars(
        r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\OpenJS.NodeJS.LTS_Microsoft.Winget.Source_8wekyb3d8bbwe\node-v24.19.0-win-x64\gws.cmd"
    )
    if os.path.exists(candidate):
        return candidate
    raise FileNotFoundError(
        "gws コマンドが見つかりません。settings.json の gws_command を設定するか、PATH に追加してください。"
    )


def _run_gws(args: list[str]) -> str:
    exe = _find_gws()
    result = subprocess.run(
        [exe, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "gws がエラーを返しました").strip())
    return (result.stdout or "").strip()


def _is_auth_error(message: str) -> bool:
    return any(k in message for k in _AUTH_KEYWORDS)


def _ok(**kwargs) -> None:
    print(json.dumps({"ok": True, **kwargs}, ensure_ascii=True))


def _err(message: str, auth_required: bool = False) -> None:
    print(json.dumps({"ok": False, "error": message, "auth_required": auth_required}, ensure_ascii=True))


def cmd_list(args) -> None:
    try:
        params: dict = {
            "userId": "me",
            "maxResults": min(max(args.limit, 1), 50),
        }
        if args.unread:
            params["labelIds"] = ["UNREAD"]
        if args.query:
            params["q"] = args.query
        raw = _run_gws(["gmail", "messages", "list", "--params", json.dumps(params)])
        payload = json.loads(raw) if raw else {}
        messages = payload.get("messages", [])
        result_items = []
        for msg in messages[:20]:
            mid = msg.get("id", "")
            try:
                detail_raw = _run_gws([
                    "gmail", "messages", "get", "--params",
                    json.dumps({
                        "userId": "me",
                        "id": mid,
                        "format": "metadata",
                        "metadataHeaders": ["Subject", "From", "Date"],
                    }),
                ])
                detail = json.loads(detail_raw) if detail_raw else {}
                headers = {
                    h["name"]: h["value"]
                    for h in detail.get("payload", {}).get("headers", [])
                }
                result_items.append({
                    "id": mid,
                    "subject": headers.get("Subject", "（件名なし）"),
                    "from": headers.get("From", ""),
                    "date": headers.get("Date", ""),
                })
            except Exception:
                result_items.append({"id": mid, "subject": "（取得失敗）", "from": "", "date": ""})
        _ok(messages=result_items, count=len(result_items))
    except RuntimeError as exc:
        msg = str(exc)
        _err(msg, auth_required=_is_auth_error(msg))
    except Exception as exc:
        _err(str(exc))


def cmd_draft_create(args) -> None:
    try:
        mime_msg = email.mime.text.MIMEText(args.body or "", "plain", "utf-8")
        mime_msg["To"] = args.to or ""
        mime_msg["Subject"] = args.subject or ""
        raw_bytes = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode()
        draft_body = {"message": {"raw": raw_bytes}}
        _run_gws([
            "gmail", "drafts", "create",
            "--params", json.dumps({"userId": "me"}),
            "--json", json.dumps(draft_body, ensure_ascii=False),
        ])
        _ok(message=f"下書きを作成しました: {args.subject}")
    except RuntimeError as exc:
        msg = str(exc)
        _err(msg, auth_required=_is_auth_error(msg))
    except Exception as exc:
        _err(str(exc))


def cmd_auth(_args) -> None:
    try:
        exe = _find_gws()
        gcloud_bin = os.path.expandvars(r"%LOCALAPPDATA%\Google\Cloud SDK\google-cloud-sdk\bin")
        bat = tempfile.NamedTemporaryFile(suffix=".bat", delete=False, mode="w", encoding="utf-8")
        bat.write(
            f"@echo off\n"
            f"set PATH={gcloud_bin};%PATH%\n"
            f'"{exe}" auth setup --login\n'
            f"pause\n"
        )
        bat.close()
        os.startfile(bat.name)
        _ok()
    except Exception as exc:
        _err(str(exc))


def main() -> None:
    parser = argparse.ArgumentParser(prog="GMailCtrlCli", description="Gmail CLI for assist-chat plugin")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="メール一覧")
    p_list.add_argument("--unread", action="store_true", default=True, help="未読のみ（既定）")
    p_list.add_argument("--query", help="Gmail検索クエリ")
    p_list.add_argument("--limit", type=int, default=20, help="最大件数（1〜50）")
    p_list.set_defaults(func=cmd_list)

    p_draft = sub.add_parser("draft-create", help="下書き作成")
    p_draft.add_argument("--to", required=True, help="宛先メールアドレス")
    p_draft.add_argument("--subject", required=True, help="件名")
    p_draft.add_argument("--body", default="", help="本文")
    p_draft.set_defaults(func=cmd_draft_create)

    p_auth = sub.add_parser("auth", help="Google認証")
    p_auth.set_defaults(func=cmd_auth)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
