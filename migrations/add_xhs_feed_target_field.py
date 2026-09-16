#!/usr/bin/env python3
"""数据库迁移脚本：为 feeds 表添加 target 字段（小红书关键词/账号的原始检索值）。

背景：
  * 之前关键字订阅的 feed.id = "XHS_KW_<中文 keyword>"，导致 URL 含中文，
    且 keyword 是唯一键，改名困难。
  * 现在关键字订阅的 feed.id = "XHS_KW_<uuid>"，原始 keyword 改存到 feeds.target。
  * 账号订阅的 userId 也存到 feeds.target（之前是从 id 拆出来的，仍兼容老数据）。

执行方式：python migrations/add_xhs_feed_target_field.py
"""
from core.db import DB
from sqlalchemy import inspect, text
from core.print import print_info, print_error, print_success

# 旧 feed.id 前缀长度，用于从历史 id 拆出原始 target
XHS_KW_PREFIX = "XHS_KW_"
XHS_U_PREFIX = "XHS_U_"


def migrate():
    """执行数据库迁移"""
    print_info("开始迁移：为 feeds 表添加 target 字段（小红书订阅关键字/账号原值）")

    engine = DB.get_engine()
    inspector = inspect(engine)

    try:
        if 'feeds' not in inspector.get_table_names():
            print_error("feeds 表不存在，跳过迁移")
            return

        columns = [col['name'] for col in inspector.get_columns('feeds')]

        # 1) 加 target 列
        if 'target' not in columns:
            print_info("添加 target 字段...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE feeds ADD COLUMN target VARCHAR(500)"))
                conn.commit()
            print_success("target 字段添加成功")
        else:
            print_info("target 字段已存在，跳过 ADD COLUMN")

        # 2) 把历史 XHS_KW_*/XHS_U_* 数据的 target 从 id 回填
        #    兼容旧逻辑（_split_feed_id），避免老数据迁移后丢关键字
        print_info("回填历史 XHS 订阅的 target 字段...")
        with engine.connect() as conn:
            updated = conn.execute(text(
                "UPDATE feeds SET target = SUBSTR(id, {}) WHERE id LIKE '{}%' AND (target IS NULL OR target = '')".format(
                    len(XHS_KW_PREFIX) + 1,  # SQLite SUBSTR 从 1 开始；前缀长度 + 1 = target 起点
                    XHS_KW_PREFIX,
                )
            ))
            updated2 = conn.execute(text(
                "UPDATE feeds SET target = SUBSTR(id, {}) WHERE id LIKE '{}%' AND (target IS NULL OR target = '')".format(
                    len(XHS_U_PREFIX) + 1,
                    XHS_U_PREFIX,
                )
            ))
            conn.commit()
        print_success(f"回填完成（XHS_KW_={updated.rowcount} 行，XHS_U_={updated2.rowcount} 行）")

        print_success("数据库迁移完成！")

    except Exception as e:
        print_error(f"数据库迁移失败：{e}")
        raise


if __name__ == "__main__":
    migrate()