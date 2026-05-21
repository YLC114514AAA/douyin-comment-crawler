"""
抖音评论区爬虫 — 数据处理与输出
提供评论筛选、统计计算、JSON/TXT文件生成功能
"""

import json
import os
from datetime import datetime, timezone, timedelta

import config


# 北京时间时区
TZ_BEIJING = timezone(timedelta(hours=8))


def _format_time(timestamp: int) -> str:
    """将 Unix 时间戳转换为北京时间字符串"""
    if not timestamp:
        return "未知"
    dt = datetime.fromtimestamp(timestamp, tz=TZ_BEIJING)
    return dt.strftime("%Y-%m-%d %H:%M")


def filter_by_douyin_id(comments: list[dict], targets: list[str]) -> list[dict]:
    """
    按抖音号/UID/昵称筛选评论。按以下优先级匹配：
      1. unique_id（抖音号，如 @zhangsan）
      2. uid（数字ID）
      3. short_id（短ID）
      4. nickname（昵称）
    大小写不敏感。
    """
    if not targets:
        return comments

    target_set = {t.strip().lower() for t in targets if t.strip()}
    results = []
    for c in comments:
        searchable = {
            (c.get("unique_id") or "").lower(),
            (c.get("uid") or "").lower(),
            (c.get("short_id") or "").lower(),
            (c.get("nickname") or "").lower(),
        }
        if searchable & target_set:
            results.append(c)
    return results


def _user_display_name(c: dict) -> str:
    """获取用户的主要显示标识"""
    unique_id = c.get("unique_id", "")
    if unique_id:
        return f"{c.get('nickname', '未知')} (抖音号: {unique_id})"
    return f"{c.get('nickname', '未知')} (UID: {c.get('uid', '')})"


def group_by_user(comments: list[dict]) -> dict[str, list[dict]]:
    """按用户分组评论（优先用抖音号，其次用昵称+UID）"""
    groups = {}
    for c in comments:
        unique_id = c.get("unique_id", "")
        if unique_id:
            key = f"{c.get('nickname', '未知')} | 抖音号: {unique_id}"
        else:
            key = f"{c.get('nickname', '未知')} | UID: {c.get('uid', '')}"
        if key not in groups:
            groups[key] = []
        groups[key].append(c)
    return groups


def compute_stats(comments: list[dict]) -> dict:
    """计算统计汇总"""
    if not comments:
        return {"total_comments": 0, "total_likes": 0, "avg_likes": 0, "max_comment": None}

    total_likes = sum(c.get("digg_count", 0) for c in comments)
    max_comment = max(comments, key=lambda c: c.get("digg_count", 0))

    return {
        "total_comments": len(comments),
        "total_likes": total_likes,
        "avg_likes": round(total_likes / len(comments), 1),
        "max_comment": max_comment,
    }


def save_json(data: dict, filepath: str):
    """保存 JSON 格式结果"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[输出] JSON 已保存: {filepath}")


def save_text_report(
    comments: list[dict],
    target_ids: list[str],
    video_url: str,
    total_scraped: int,
    filepath: str,
):
    """生成并保存中文可读的文本报告"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    now = datetime.now(TZ_BEIJING).strftime("%Y-%m-%d %H:%M:%S")
    groups = group_by_user(comments)
    stats = compute_stats(comments)

    lines = []
    lines.append("=" * 55)
    lines.append("  抖音评论区 — 指定用户发言抓取报告")
    lines.append("=" * 55)
    lines.append("")
    lines.append(f"视频链接: {video_url}")
    lines.append(f"抓取时间: {now}")
    lines.append(f"查询目标: {', '.join(target_ids) if target_ids else '(全部)'}")
    lines.append(f"视频总评论数(已抓取): {total_scraped} 条")
    lines.append(f"匹配到评论数: {len(comments)} 条")
    lines.append("")

    for group_name, user_comments in groups.items():
        c0 = user_comments[0]
        uid = c0.get("uid", "")
        unique_id = c0.get("unique_id", "")
        short_id = c0.get("short_id", "")
        user_stats = compute_stats(user_comments)

        lines.append("=" * 55)
        lines.append(f"用户: {c0.get('nickname', '未知')}")
        lines.append(f"  抖音号: {unique_id if unique_id else '(未设置)'}")
        lines.append(f"  UID: {uid}")
        if short_id and short_id != "0":
            lines.append(f"  Short ID: {short_id}")
        lines.append("=" * 55)

        for idx, c in enumerate(user_comments, 1):
            likes = c["digg_count"]
            t = _format_time(c["create_time"])
            ip = c.get("ip_label", "-")
            lines.append(f"  评论 #{idx} | 点赞: {likes} | 时间: {t} | IP: {ip}")
            lines.append(f"  内容: {c['text']}")

            images = c.get("images", [])
            if images:
                lines.append(f"  图片: [{len(images)}张]")
                for img_url in images:
                    lines.append(f"    - {img_url}")
            else:
                lines.append(f"  图片: 无")

            stickers = c.get("stickers", [])
            if stickers:
                lines.append(f"  贴纸: [{len(stickers)}个]")
                for s_url in stickers:
                    lines.append(f"    - {s_url}")
            else:
                lines.append(f"  贴纸: 无")

            if c.get("reply_comment_total", 0) > 0:
                lines.append(f"  二级回复数: {c['reply_comment_total']}")

            lines.append("")

        lines.append("-" * 55)
        lines.append(f"小计: {user_stats['total_comments']}条评论 | "
                     f"总点赞: {user_stats['total_likes']} | "
                     f"平均点赞: {user_stats['avg_likes']}")
        lines.append("")

    lines.append("=" * 55)
    lines.append("  汇总")
    lines.append("=" * 55)
    lines.append(f"匹配用户数: {len(groups)}")
    lines.append(f"总评论数: {stats['total_comments']}")
    lines.append(f"总点赞数: {stats['total_likes']}")
    lines.append(f"平均点赞数: {stats['avg_likes']}")

    if stats["max_comment"]:
        mc = stats["max_comment"]
        text_preview = mc["text"][:30] + ("..." if len(mc["text"]) > 30 else "")
        lines.append(f"最高点赞评论: [{mc['digg_count']}] \"{text_preview}\" ({mc['nickname']})")

    lines.append("=" * 55)

    report = "\n".join(lines)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"[输出] 文本报告已保存: {filepath}")

    # 也在控制台打印
    print("\n" + report)
