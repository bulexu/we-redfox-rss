# we-mp-rss · v0.2.0 发布说明

> 本项目基于 [rachelos/we-mp-rss](https://github.com/rachelos/we-mp-rss) 二次开发，专注于**更稳定的数据源接入 + 更丰富的内容归档**，适合需要长期运行 RSS 服务的团队。

---

## 📖 项目简介

`we-mp-rss` 是一个 **微信公众号 → RSS 订阅源** 服务：将关注的公众号自动转化为标准 RSS 2.0 源，可被 RSS 阅读器 / 自建信息流聚合 / 自动化流水线订阅，无需登录公众号、无须手动抓取。

本分支在保留上游全部能力的基础上，重点增强了**数据源稳定性**与**多端归档能力**：

- 用无状态 REST API（redfox）替代易过期的微信扫码会话
- 抓取链路内置自动降级 + 外挂兜底双层防护
- 新增飞书多维表（Bitable）自动归档，把采集到的文章直接落到团队的数据表

---

## 🎯 本分支核心能力

### 1️⃣ 数据源升级

- 通过 [redfox.hk](https://redfox.hk) 无状态 REST API 拉取公众号文章列表与作品
- 摆脱微信扫码会话的 cookie 失效焦虑，长期运行不掉线

### 2️⃣ 文章正文三级抓取

正文获取采用 **系统内降级 + 外挂兜底** 的双层方案：

- **系统内自动降级**（无需人工介入）：
  - Tier 1：Playwright 渲染（默认）
  - Tier 2：redfox API 兜底（由 `GATHER.CONTENT_REDFOX_FALLBACK` 控制开关，默认开启）
- **外挂人工兜底**（独立于系统降级）：
  - Tier 3：[八爪鱼 RPA](https://rpa.bazhuayu.com/shareableLink/6aa1062894a41f8dcd647ff3) 客户端，需在八爪鱼单独配置
  - 系统会暴露两个 AK 端点供 RPA 回写正文：
    - `GET /api/v1/wx/articles/pending-content`
    - `POST /api/v1/wx/articles/{article_id}/content`

### 3️⃣ 飞书多维表自动归档

- `/lark/bitables` 后台页面可视化配置推送目标
- 每条 Bitable 可关联多个公众号（`mp_ids` 白名单）
- 字段映射白名单（`title` / `url` / `content` / `publish_time` / `mp_name` 等）
- 幂等去重：复合主键，二次推送自动跳过
- 全异步执行，不拖慢抓取主流程
- 失败可重试：每行记录 `last_error` / `last_error_at`

### 4️⃣ Redfox 调用观测

- 调用日志：每次 redfox 请求的 endpoint、code、耗时、HTTP 状态、错误信息
- 每日调用柱状图：近 7 / 30 / 180 天切换，颜色按当日失败率分桶（绿/蓝/橙/红/灰）
- Redis 存储，30 天滚动保留

### 5️⃣ 全部能力一览

**内容生产与分发**

- 文章列表（redfox REST 拉取）
- RSS 订阅源生成（RSS 2.0，支持 CDATA / 全文 / 封面 / 自定义分页大小）
- 定时自动更新（默认 10s，可配）
- 自定义 RSS 标题、描述、封面、分页大小
- 多通道通知（钉钉 / 微信群机器人 / 飞书 / 自定义 Webhook）
- HTML 内容过滤规则（全局 + 公众号专属，优先级 0-100）
- 多种导出格式：**Markdown / DOCX / PDF / JSON**

**Web 管理后台**

- 13 套主题（深色 / 护眼 / 紫 / 蓝 / 绿 / 橙 / 玫瑰 / 青 / 粉 / 靛 / 紫罗兰 / 咖啡 / 海军蓝）
- 响应式分页（PC 翻页、移动端加载更多）
- 系统信息页（redfox 调用日志、状态、数据库信息、缓存状态）
- 内容过滤规则可视化编辑
- 多维表配置界面
- 错误捕获与降级提示

**安全与认证**

- JWT 登录会话（默认 4320 分钟可配）
- `SAFE_HIDE_CONFIG` 自动遮蔽敏感配置展示

**扩展与运维**

- 环境异常统计：自动追踪各订阅的抓取失败（限流、风控、超时）
- Webhook Headers / Cookies 认证
- 配置缓存：Redis / Memcached / 内存三级，降重复读开销
- 数据库：SQLite（默认）/ MySQL / PostgreSQL

---

## 🚀 快速开始

```bash
docker run -d \
  --name we-mp-rss \
  -p 8001:8001 \
  -v $(pwd)/data:/app/data \
  -e REDIS_URL=redis://your-redis:6379/0 \
  -e WX_REDFOX_KEY=your-redfox-key \
  ghcr.io/bulexu/we-mp-rss:latest
```

完整文档（含 `.env` 配置项、AK 管理、RPA 接入、字段映射）请参考 [README.zh-CN.md](./README.zh-CN.md) / [README.md](./README.md)。

---

## ⚙️ 环境要求

| 组件 | 必需 | 说明 |
| --- | :---: | --- |
| Docker | ✅ | 推荐部署方式 |
| Redis | ✅ | Redfox 日志统计、多 worker 会话需要 |
| redfox API Key | ✅ | 数据源，无状态 REST |
| Lark App ID / Secret | 可选 | 启用飞书多维表归档时需要 |

---

## 🙏 致谢

本项目基于 [rachelos/we-mp-rss](https://github.com/rachelos/we-mp-rss) 开发，感谢原作者及社区贡献者：

cyChaos、子健MeLift、晨阳、童总、胜宇、军亮、余光、一路向北、水煮土豆丝、人可、须臾、澄明、五梭、Jarvis、三三、哈基米、苹果

---

## 📌 版本

- 当前版本：`v0.2.0`
- 上游基线：rachelos/we-mp-rss（初始 fork 快照 `c1dac93c`）
- 下一版本计划：更多归档通道（Notion / Airtable）、redfox 调用成本统计