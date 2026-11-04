"""Redfox 各平台返回字段一致性测试。

所有平台映射后的 dict 必须满足 ``core.redfox.validation.NORMALIZED_FIELDS``
定义的统一契约;  原始响应必须包含各平台声明依赖的核心字段。

用法 (项目根目录):
    python -m core.redfox.tests_fields          # 只跑本地 fixture
    python -m core.redfox.tests_fields --live   # 额外调用真实接口检查字段
"""
from __future__ import annotations

import copy
import sys
from typing import Any, Dict, List, Tuple

from core.redfox.validation import (
    NORMALIZED_FIELDS,
    extract_items,
    get_reports,
    reset_reports,
    validate_normalized,
    validate_raw,
)


# ---------------------------------------------------------------------------
# 各平台真实响应样例 (取自 2026-11-04 实际接口返回,  仅保留映射依赖字段)
# ---------------------------------------------------------------------------

XHS_ITEM: Dict[str, Any] = {
    "workId": "6ae8dadd000000001b031fc5",
    "workTitle": "露营厨房系统，帮我看看这个炉子和锅怎么样",
    "workDesc": "#户外露营 #露营 #露营装备 #露营厨房系统 #露营套锅",
    "coverUrl": "https://sns-i11-ae.rednotecdn.com/spectrum/1040g34o32732spc26c1049nnaiiv7m5u9ec2lh0",
    "workUrl": "https://www.xiaohongshu.com/explore/6ae8dadd000000001b031fc5",
    "workPublishTime": "2026-11-03 07:00:36",
    "accountNickname": "大荣荣",
    "accountUserid": "598ba5f350c4b450023ed8be",
    "workLikedCount": 8,
    "workCommentsCount": 0,
    "workCollectedCount": 6,
    "workSharedCount": 1,
    "workType": "video",
    "accountType": "旅行度假",
}

BILIBILI_ITEM: Dict[str, Any] = {
    "bvId": "BV1fxJ86vEBL",
    "title": "雨中露营，独自在森林过夜",
    "description": "🌊 充气帐篷 cozy 露营 · 韩式露营料理 · 露营 ASMR 🏕️🍜",
    "picUrl": "https://i0.hdslb.com/bfs/archive/demo.jpg",
    "created": "2026-10-19 22:05:00",
    "author": "一布在户外",
    "authorId": "3569806",
    "likeCount": 12,
    "commentCount": 0,
    "favoriteCount": 4,
    "playCount": 100,
    "shareCount": 2,
    "duration": 1471,
    "tagNames": ["露营", "户外"],
}

DOUYIN_ITEM: Dict[str, Any] = {
    "videoId": "7423358270530551059",
    "content": "#轻便露营灯 #便捷露营灯 #露营必备灯",
    "coverUrl": "https://p26-sign.douyinpic.com/tos-cn-i-demo.webp",
    "opusUrl": "https://www.douyin.com/video/7423358270530551059",
    "publishTime": "2026-10-17 15:22:23",
    "authorName": "胖虎露营",
    "authorUid": "2685487812714169",
    "likeCount": 10,
    "commentCount": 2,
    "collectCount": 1,
    "shareCount": 0,
    "duration": 29600,
    "imageUrlList": [],
    "videoType": "video",
}

TIKTOK_ITEM: Dict[str, Any] = {
    "workId": "7698305558255766817",
    "content": "#camping #survival #wilderness #campinglife",
    "publishTime": 1762000000,
    "shareLink": "https://www.tiktok.com/@george41026/video/7698305558255766817",
    "mediaType": "video",
    "authorData": {
        "userHandle": "george41026",
        "userName": "george",
        "userId": "7501047534392427553",
        "fansCount": 1200,
        "avatarImage": "https://p16-common-sign.tiktokcdn-us.com/demo.webp",
    },
    "statsData": {
        "likeCount": 283696,
        "commentTotal": 2794,
        "favoriteCount": 31660,
        "viewCount": 6516788,
        "shareTotal": 19313,
        "repostTotal": 0,
    },
    "videoData": {
        "coverImage": "https://p19-common-sign.tiktokcdn-us.com/demo.jpeg",
        "playAddress": "https://v16-webapp.tiktok.com/demo.mp4",
        "downloadNoMarkAddress": "https://v16-webapp.tiktok.com/demo-download.mp4",
        "playDuration": 15000,
    },
}

YOUTUBE_ITEM: Dict[str, Any] = {
    "videoId": "9WNPZKg62TE",
    "title": "Hot Tent Camping in the Rain at Night",
    "description": "Where are you watching from? Do you prefer camping in the rain or snow?",
    "thumbnails": [
        {"url": "https://i.ytimg.com/vi/9WNPZKg62TE/hq720.jpg", "width": 720, "height": 404},
    ],
    "author": "Forest camp",
    "channelId": "UCh2ZoEnKTSTIFATtvpxJdCQ",
    "publishedTime": "15 hours ago",
    "duration": "33:34",
    "viewCount": 4294,
}

INSTAGRAM_ITEM: Dict[str, Any] = {
    "mediaId": "380809389031498049014091366509260360",
    "code": "DTZETeTj0yK",
    "captionText": "Nothing beats moments like this",
    "captionHashtags": [],
    "imageUrl": "https://scontent-bos5-1.cdninstagram.com/v/t51.71878-15/demo.jpg",
    "takenAt": "2026-06-24T12:00:00Z",
    "user": {
        "username": "natgeo",
        "fullName": "National Geographic",
        "followerCount": 280000000,
    },
    "likeCount": 124941,
    "commentCount": 580,
    "playCount": 1000000,
    "shareCount": 20,
    "mediaFormat": "video",
    "mediaType": 2,
    "videoUrl": "https://scontent.cdninstagram.com/demo.mp4",
    "videoDuration": 12.5,
}

X_ITEM: Dict[str, Any] = {
    "tweetId": "1937963239129690113",
    "text": "camping under the stars tonight",
    "createdAt": "Wed Jun 25 20:04:37 +0000 2025",
    "username": "natgeo",
    "user": {"displayName": "National Geographic", "username": "natgeo", "followers": 1000000},
    "medias": [
        {"coverUrl": "https://pbs.twimg.com/amplify_video_thumb/demo.jpg", "type": "photo", "variants": []},
    ],
    "likeCount": 101416,
    "replyCount": 100,
    "bookmarkCount": 12872,
    "viewCount": 500000,
    "retweetCount": 2000,
    "quoteCount": 10,
    "language": "en",
}


def _cases() -> List[Tuple[str, Dict[str, Any], Any]]:
    """(platform, fixture, normalizer) 列表。"""
    from core.redfox.bilibili.sync import _normalize_work as bili_norm
    from core.redfox.douyin.sync import _normalize_work as dy_norm
    from core.redfox.instagram.sync import _normalize_post as ins_norm
    from core.redfox.tiktok.sync import _normalize_video as tt_norm
    from core.redfox.x.sync import _normalize_tweet as x_norm
    from core.redfox.xhs.sync import _normalize_note as xhs_norm
    from core.redfox.youtube.sync import _normalize_video as yt_norm

    return [
        ("xhs", XHS_ITEM, xhs_norm),
        ("bilibili", BILIBILI_ITEM, bili_norm),
        ("douyin", DOUYIN_ITEM, dy_norm),
        ("tiktok", TIKTOK_ITEM, tt_norm),
        ("youtube", YOUTUBE_ITEM, yt_norm),
        ("instagram", INSTAGRAM_ITEM, ins_norm),
        ("x", X_ITEM, x_norm),
    ]


# ---------------------------------------------------------------------------
# fixture 测试
# ---------------------------------------------------------------------------

def test_normalized_contract() -> bool:
    """所有平台映射结果都包含统一的规范字段且类型正确。"""
    for platform, raw, normalizer in _cases():
        reset_reports()
        assert validate_raw(platform, raw) == [], (
            f"{platform}: fixture 缺少原始字段: {validate_raw(platform, raw)}"
        )
        item = normalizer(raw)
        assert item, f"{platform}: 映射结果为空"
        missing = [f for f in NORMALIZED_FIELDS if f not in item]
        assert not missing, f"{platform}: 缺少规范字段 {missing}"
        issues = validate_normalized(platform, item)
        assert not issues, f"{platform}: 规范字段校验失败: {issues}"
        assert not get_reports(), f"{platform}: 不应产生字段告警: {get_reports()}"
    print("  ✓ 各平台映射结果符合统一字段契约")
    return True


def test_detect_missing_raw_field() -> bool:
    """原始响应缺字段时能被发现。"""
    raw = copy.deepcopy(XHS_ITEM)
    raw.pop("workDesc")
    issues = validate_raw("xhs", raw)
    assert "缺少原始字段 workDesc" in issues, issues
    print("  ✓ 可检测原始响应缺字段")
    return True


def test_detect_bad_normalized_item() -> bool:
    """规范字段缺失 / 类型错误 / JSON 非法时能被发现。"""
    item = _cases()[0][2](XHS_ITEM)
    broken = dict(item)
    broken.pop("title")
    broken["publish_time"] = "2026-11-03"
    broken["image_urls"] = "not-json"
    issues = validate_normalized("xhs", broken)
    assert any("缺少规范字段 title" in i for i in issues), issues
    assert any("publish_time 类型错误" in i for i in issues), issues
    assert any("image_urls 不是合法 JSON" in i for i in issues), issues
    print("  ✓ 可检测规范字段缺失 / 类型错误 / JSON 非法")
    return True


def test_extract_items() -> bool:
    """统一列表提取: dict / list / 未知结构。"""
    assert extract_items("xhs", {"list": [{"a": 1}]}) == [{"a": 1}]
    assert extract_items("bilibili", {"workList": [{"b": 2}]}) == [{"b": 2}]
    assert extract_items("tiktok", [{"c": 3}]) == [{"c": 3}]

    reset_reports()
    assert extract_items("xhs", {"unexpected": []}) == []
    messages = get_reports().get("xhs", {}).get("messages", [])
    assert any("未找到列表字段" in m for m in messages), messages
    print("  ✓ 统一列表提取可发现接口结构变化")
    return True


# ---------------------------------------------------------------------------
# 真实接口检查 (可选)
# ---------------------------------------------------------------------------

def _live_calls() -> List[Tuple[str, Any, Any]]:
    from core.redfox import bilibili, douyin, instagram, tiktok, x, xhs, youtube

    normalizers = {platform: normalizer for platform, _, normalizer in _cases()}
    return [
        ("xhs", lambda: xhs.search_articles(keyword="露营", page=1, sort="最新"), normalizers["xhs"]),
        ("bilibili", lambda: bilibili.search_works("露营", 1, bilibili.ORDER_LATEST), normalizers["bilibili"]),
        ("douyin", lambda: douyin.search_articles("露营", 1, 20), normalizers["douyin"]),
        ("tiktok", lambda: tiktok.search_videos("camping", 0, 20), normalizers["tiktok"]),
        ("youtube", lambda: youtube.search_videos("camping"), normalizers["youtube"]),
        ("instagram", lambda: instagram.search_posts("camping"), normalizers["instagram"]),
        ("x", lambda: x.search_tweets("camping"), normalizers["x"]),
    ]


def _load_env() -> None:
    """直接跑本模块时加载项目根目录 ``.env`` (与 main.py 行为一致)。"""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    from pathlib import Path
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)


def test_live_fields() -> bool:
    """调用真实接口,  校验原始字段 + 映射结果。"""
    _load_env()
    ok = True
    for platform, call, normalizer in _live_calls():
        reset_reports()
        try:
            data = call()
        except Exception as exc:  # noqa: BLE001
            print(f"  ! {platform}: 调用失败,  跳过 ({type(exc).__name__}: {exc})")
            continue

        items = extract_items(platform, data)
        if not items:
            print(f"  ! {platform}: 未返回作品,  跳过")
            continue

        for raw in items[:3]:
            item = normalizer(raw)
            issues = validate_raw(platform, raw) + validate_normalized(platform, item)
            if issues:
                ok = False
                print(f"  ✗ {platform}: {issues}")
                break
        else:
            print(f"  ✓ {platform}: {len(items[:3])} 条字段正常")
    return ok


def main() -> int:
    print("=== core.redfox.tests_fields ===")
    failures: List[Tuple[str, str]] = []
    tests = [
        ("normalized_contract", test_normalized_contract),
        ("missing_raw_field", test_detect_missing_raw_field),
        ("bad_normalized_item", test_detect_bad_normalized_item),
        ("extract_items", test_extract_items),
    ]
    for name, fn in tests:
        print(f"[{name}]")
        try:
            fn()
        except AssertionError as exc:
            failures.append((name, f"ASSERT: {exc}"))
            print(f"  ✗ {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append((name, f"{type(exc).__name__}: {exc}"))
            print(f"  ✗ {type(exc).__name__}: {exc}")

    if "--live" in sys.argv:
        print("[live_fields]")
        try:
            if not test_live_fields():
                failures.append(("live_fields", "字段校验未通过"))
        except Exception as exc:  # noqa: BLE001
            failures.append(("live_fields", f"{type(exc).__name__}: {exc}"))
            print(f"  ✗ {type(exc).__name__}: {exc}")

    if failures:
        print(f"\n{len(failures)} 个测试失败:")
        for name, message in failures:
            print(f"  - {name}: {message}")
        return 1
    print("\n全部通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
