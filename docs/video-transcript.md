# 视频文案补抓

在环境变量中设置 `REDFOX_CONVERT_VIDEO=True`（默认 False），或设置
`config.yaml` 中的 `redfox.convert_video: true`。重启服务后，新抓取并成功入库的作品会投递到内容补抓队列。
启动时及每个内容补抓周期还会运行“扫描待提取视频文案”，每批最多投递 10 条已有作品，
不受公众号 `gather.content_auto_check` 开关限制。已完成作品跳过，失败作品一小时后可再次扫描入队。

小红书仅处理 `work_type=video`；YouTube 不投递异步提取任务。
其他 Redfox 平台作品投递任务。
抖音、小红书、B 站使用提交任务和轮询结果接口。
YouTube 在采集流程中直接调用字幕接口，仍受 `REDFOX_CONVERT_VIDEO` 开关控制；
已保存字幕的作品跳过重复调用，字幕为空或获取失败时保留原介绍，不转入异步提取队列。
历史补抓扫描也排除 YouTube。
当前 SDK 未提供 X、TikTok、Instagram 视频文案接口，这些任务会显示失败原因，不影响作品采集。

原介绍保留在 description，提取结果追加到 content，并保存在 extinfo.video_transcript。
远端 taskId 保存在 extinfo.transcript_task_id，失败重试时复用，避免重复提交。
每次最多查询 60 次，间隔 5 秒；支持的平台失败后由队列最多重试两次。
内容补抓队列为串行队列，等待视频结果时后续补抓任务需要排队。
已完成的作品跳过接口调用，后续列表刷新保留文案和任务 ID。
进程内避免同一作品重复排队；没有跨进程锁。
