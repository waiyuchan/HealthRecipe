# 饭搭子、热量与记忆

## 一次沟通会做什么

1. 用 request_id 检查重试，避免一次发送重复记忆／保存消息；相同标识配不同内容返回冲突。
2. 读取有效记忆、最近 14 天饮食记录与历史评分，不把旧的做菜记录当个人实际摄入。
3. 用已确认城市查询 Open-Meteo；缓存 30 分钟。断线可展示六小时内旧数据，但明确标为 stale，不用旧气温参与推荐；失败结果缓存 60 秒，避免每次刷新重复等待。
4. 先在服务端应用忌口、用时、最近 N 天去重；当前消息里明确的过敏／不吃声明立即参与排除。支持常见别名和食材组，但不保证识别所有复合配料或交叉接触。
5. 把合格菜谱及逐项计算的参考热量、有效记忆和近期饮食摘要交给配置模型；未配置或失败则本地模式。只有当前消息、工具结果和上次菜谱 ID，不重放聊天原文。
6. 校验模型 JSON，丢弃不在合格候选中的菜谱 ID、无效餐别及无来源的记忆。记忆证据须逐字出现在当前消息中，保存原话，不改写为诊断。身体感受 14 天，明确过敏不自动过期。
7. 保存对话与可见结果。餐单只是草稿，用户点击后才整批加入；去重和事务处理防止重复或半次写入。单道菜不等同完整营养配餐。

当前不配置模型即可使用本地数据工具与保守记忆；它不是同等自由对话能力的替代。界面始终显示模式，服务断线有明确提示。

## 通用模型接入

默认 `HEALTHRECIPE_LLM_PROVIDER=custom`。必须同时配置：

- `HEALTHRECIPE_LLM_BASE_URL`：兼容接口的基础地址，以 `/v1` 等供应商要求的路径结束。
- `HEALTHRECIPE_LLM_MODEL`：供应商允许访问的模型名。
- `HEALTHRECIPE_LLM_API_KEY`：仅在服务端环境中保存。

请求使用标准 `POST /chat/completions`，JSON messages 与 JSON object 响应，超时连接 5 秒、读取 40 秒。无需引入 SDK；[OpenAI 官方参考](https://platform.openai.com/docs/api-reference/chat/create)定义基础协议，[通义兼容接口参考](https://help.aliyun.com/en/model-studio/qwen-api-via-openai-chat-completions)用于兼容联调。不是所有标称兼容的模型都支持 JSON object 格式，应以供应商文档为准。

显式适配快捷方式：

```dotenv
HEALTHRECIPE_LLM_PROVIDER=qwen
DASHSCOPE_API_KEY=在本机配置
HEALTHRECIPE_LLM_MODEL=按供应商填写
# 可选 DASHSCOPE_BASE_URL，按区域与工作空间调整
```

`deepseek` 使用 `DEEPSEEK_API_KEY`；`openai` 使用 `OPENAI_API_KEY` 且需明确 `HEALTHRECIPE_LLM_MODEL`；`local` 强制本地模式。`auto` 仅在管理员显式设置时才探测已有凭据；默认不会因为机器上其他项目有密钥就开始调用。

只有配置模型才会发送当前消息、有效记忆、近期饮食摘要、候选菜谱和城市天气。密钥不出现在状态 API、界面、日志或备份。请求失败只记录错误类型，不转储供应商响应或 Authorization。

## 记忆与隐私

- 类别：身体感受、饮食偏好、饮食目标、生活习惯。保留内容、来源原文、创建日期和有效期限。
- 可以在发送时取消记忆，也可全局关闭；关闭后既不读取既有记忆，也不添加新记忆。
- 本地模式只识别保守的第一人称陈述；提问、假设与他人状况不做健康事实记忆。不宣称拥有完整自然语言理解。
- 删除／修改记忆会清空聊天和 request_id 缓存，避免旧上下文继续引用原事实；食谱与摄入记录保留。
- 到期记忆不再用于筛选或模型上下文；旧聊天原文从来不重放，所以不会从过期记录里“复活”身体状态。
- 聊天与记忆默认都存入同一个家庭 SQLite。当前未做个人账户隔离，界面明确显示家庭共用提示；未来上线多用户前应按用户／家庭权限隔离。
- 导出的 v2 JSON 包含聊天和记忆，需要当作私人资料保存。服务端数据库备份也含这些信息。

饮食助手不能用体感或不完整日记证明食物导致疾病，不能生成疾病诊断、治疗饮食处方或极端热量限制。急重症提示直接优先就医；持续或加重的不适建议专业评估。设计参考 [NHS 均衡饮食建议](https://www.nhs.uk/live-well/eat-well/how-to-eat-a-balanced-diet/eight-tips-for-healthy-eating/)与 [BDA 饮食／症状记录说明](https://www.bda.uk.com/food-health/your-health/nutrition-and-covid-19-recovery-hub/patients/resources/keeping-a-diary.html)。

## 数据升级

SQLite `user_version=2`：新增 `memories`、`messages`、`chat_runs`，history 新增 `servings_eaten`、`meal`、`nutrition_snapshot`。旧表列通过检查后增量添加；不删除原菜谱、历史或偏好。遇到未来数据库版本拒绝运行。

JSON v2 在 v1 基础上新增记忆、消息和摄入快照。v1 导入时缺省为空，旧做菜记录没有个人份量，因此不自动计入个人摄入。导出在同一 SQLite 读事务中取得所有表；恢复在单个写事务中替换，任何校验／引用冲突均回滚。

## 关键文件

- `src/assistant.py`：工具编排、模型协议、结构校验、本地回退。
- `src/memory.py`：保守原话提取、明确食材限制。
- `src/weather.py`：城市消歧、真实天气、缓存与失效状态。
- `src/nutrition.py`、`data/nutrition.json`：可追溯食材数据和份量核算。
- `src/storage/sqlite.py`：迁移、事务、营养快照、遗忘与消息重试。
- `web/companion.js`：聊天、记忆管理、城市确认与热量页面。
