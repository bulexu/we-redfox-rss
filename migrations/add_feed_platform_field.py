#!/usr/bin/env python3
"""数据库迁移脚本：为 feeds 表添加 platform 字段。

背景：
  * 之前 Feed.platform 是从 id 前缀推断的隐式信息, 没单独持久化。
  * 公众号订阅列表 (apis/mps.py get_mps) 只过滤 FEATURED_MP_ID,
    没按平台过滤, 导致小红书订阅也出现在公众号列表里。
  * 现在加 platform 列, 列表查询按 platform 过滤, 索引更高效。

回填策略 (兼容旧数据 + 当前 uuid 化后的 id):
  * ``MP_WXS_*``        → ``"mp"``
  * ``XHS_KW_*``        → ``"xhs"``
  * ``XHS_U_*``         → ``"xhs"``
  * 其它                → ``"unknown"``

执行方式：python migrations/add_feed_platform_field.py
"""
from core.db import DB
from sqlalchemy import inspect, text
from core.print import print_info, print_error, print_success


def migrate():
    print_info("开始迁移：为 feeds 表添加 platform 字段")

    engine = DB.get_engine()
    inspector = inspect(engine)

    try:
        if 'feeds' not in inspector.get_table_names():
            print_error("feeds 表不存在，跳过迁移")
            return

        columns = [col['name'] for col in inspector.get_columns('feeds')]

        # 1) 加 platform 列 (默认 unknown, 让 NULL 历史行也能写入)
        if 'platform' not in columns:
            print_info("添加 platform 字段...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE feeds ADD COLUMN platform VARCHAR(16) DEFAULT 'unknown'"))
                conn.commit()
            print_success("platform 字段添加成功")
        else:
            print_info("platform 字段已存在，跳过 ADD COLUMN")

        # 2) 按 id 前缀回填 platform。  老数据 NULL 会被更新, 已有值不动 (幂等)。
        print_info("回填历史 feeds.platform ...")
        with engine.connect() as conn:
            r_mp = conn.execute(text(
                "UPDATE feeds SET platform = 'mp' WHERE id LIKE 'MP_WXS_%' AND (platform IS NULL OR platform = '' OR platform = 'unknown')"
            ))
            r_xhs_kw = conn.execute(text(
                "UPDATE feeds SET platform = 'xhs' WHERE id LIKE 'XHS_KW_%' AND (platform IS NULL OR platform = '' OR platform = 'unknown')"
            ))
            r_xhs_u = conn.execute(text(
                "UPDATE feeds SET platform = 'xhs' WHERE id LIKE 'XHS_U_%' AND (platform IS NULL OR platform = '' OR platform = 'unknown')"
            ))
            conn.commit()
        print_success(
            f"回填完成（MP_WXS_={r_mp.rowcount} 行, "
            f"XHS_KW_={r_xhs_kw.rowcount} 行, XHS_U_={r_xhs_u.rowcount} 行）"
        )

        # 3) 加索引 (如果还没建)。  SQLite ALTER TABLE ADD INDEX 语法见下方。
        indexes = {ix['name'] for ix in inspector.get_indexes('feeds')}
        if 'ix_feeds_platform' not in indexes:
            print_info("为 platform 列添加索引...")
            with engine.connect() as conn:
                conn.execute(text("CREATE INDEX ix_feeds_platform ON feeds (platform)"))
                conn.commit()
            print_success("platform 索引已创建")
        else:
            print_info("platform 索引已存在，跳过")

        print_success("数据库迁移完成！")

    except Exception as e:
        print_error(f"数据库迁移失败：{e}")
        raise


if __name__ == "__main__":
    migrate()