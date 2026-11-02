# 维护者指南 · Comfyui-Anima-Wardrobe-V5

> 改代码**之前**先读完这一页。这里写的是「不照做就会踩」的契约，
> 不是风格建议。下面接的是原 README 的「七、目录与数据流」与「八、测试基线」。

## 一、六条硬契约

| # | 契约 | 违反会怎样 |
|---|---|---|
| 1 | **节点控件只能追加到末尾** | `widgets_values` 是**按位置**存的数组。中间插一个控件，300+ 张旧工作流全部错位（模型名落到 seed 上这种事） |
| 2 | **旧类名不得从 `NODE_CLASS_MAPPINGS` 删除** | 工作流 JSON 存的是节点类型名，删别名 = 旧工作流全部「节点缺失」 |
| 3 | **词库/档位表是零漂移导出物，不手改** | `presets/anima_v4_pools.json` 由 `tools/export_v3_pools.mjs` 从源 HTML 生成。手改下次导出被冲回去，且 `check_v3_pools` 会红 |
| 4 | **NSFW 判定表与造型台逐字对齐** | `anima_v4_nsfw.py` 是**自动生成**的，`tests/check_nsfw_parity.py` 用 33 项常量 + 27 组行为对拍钉住。手改一处就漂移 |
| 5 | **数据文件进进程级缓存** | 改完 JSON 必须**重启 ComfyUI 后端**，否则你以为改错了 |
| 6 | **新增 `socks` 等服装选项必须登记 `STYLE_OF`** | `anima_v4_outfit_style.py` 的 `STYLE_OF["socks"]` 漏登记 → `check_v3_color` 红，`run_all` 从 20 绿掉到 1 红（v3.42.23 踩过） |

## 二、改东西的验证三件套

任何改动，**跑完这三步才算改完**（顺序不能省）：

```bash
# ① 基线：先确认改动前是绿的（或确认红的是既有的那 3 项）
python tests/run_all.py

# ② 改完再跑同一条命令，失败项**不得多于**改动前
python tests/run_all.py

# ③ 前端面板（如果碰了 js/）
node tests/av3_ui_smoke.mjs
```

⚠️ 已知的**历史红灯基线**（不是新引入的 bug，别去追）：
`check_v3_pools` 的词库零漂移、场景「触手·余韵」抽到 hetero、`check_v3_charhair` 的
11 个幽灵角色。这三项在 v5.0.8 时仍是红 —— 判断"我有没有搞坏东西"的标准是
**失败项不多于三项且不是新面孔**。

真机验证另有一套（出图看结果），见 README 各版本的「真机」段落 —— 那部分没法自动化。

---

## 七、目录与数据流

```
Comfyui-Anima-Wardrobe-V5/
├── __init__.py              节点注册 + HTTP 路由 /anima-wardrobe-v5/*（另挂 v4 / v3）
├── nodes.py                 3 个节点 + 面板接口的 payload 构造
├── anima_v4_rules.py        随机引擎 / 档位闸门 / 三层权重 / 角色选中 / 自检 / 槽位序
├── anima_v4_nsfw.py         NSFW 判定层（**自动生成，勿手改**）
├── anima_v4_overrides.py    人工校准层（段下限 + 逐选项上抬 LEVEL_RAISE + 降级 LEVEL_DEMOTE）
├── anima_v4_link.py         字段联动层（v3.15.0：体位配对 / 表情配套 / 场景倾向三张表）
├── anima_v4_pngmeta.py      把正文注入 PNG 元数据（v3.6.0 起，**不改用户工作流**）
├── presets/
│   ├── anima_v4_pools.json        词库（零漂移导出物）
│   ├── anima_v4_levels.json       每条选项的档位（派生数据）
│   ├── anima_v4_characters.json   角色库 2390 位（联网构建，**只读**）
│   ├── thumbs/                    内置角色缩略图（约 2390 张 webp）
│   ├── anima_v4_scenes.json       场景搭配 200 条 + 特写搭配 60 条（v3.9.0 起，独立于零漂移词库）
│   ├── user_characters.json       用户角色覆盖层（编辑 + 自定义，v3.4.0）
│   ├── user_thumbs/               用户上传的角色预览图（v3.4.0）
│   ├── user_presets.json          命名预设（用户数据）
│   └── user_favorites.json        角色收藏（用户数据）
├── locales/zh|en/nodeDefs.json    界面中文（显示名 / 控件名 / 下拉值）
├── js/anima_wardrobe_v4_studio.js 可视化面板（词库权重 + 角色库两页）
├── tools/                   导出 / 分类 / 同步 / 建角色库 / 抓图 / 迁移 / 建工作流
└── tests/                   13 项基线 + run_all.py
```

### 对外 HTTP 路由

| 路由 | 用途 |
|---|---|
| `GET /anima-wardrobe-v5/health` | 自检：段数 / 字段数 / 选项数 / 档位列表 |
| `GET /anima-wardrobe-v5/pools` | 完整词库（含中文名与逐项档位） |
| `GET /anima-wardrobe-v5/contract` | 段落 / 字段 / 槽位 / 档位契约 |
| `GET /anima-wardrobe-v5/scenes` | 场景搭配 + 特写搭配（v3.18.0 起每条带 `manual` / `part`，`near_parts` 给出部位顺序） |
| `GET /anima-wardrobe-v5/characters` | 角色库（作品 + 角色，约 928 KB；含 `trigger` 与 `user` 标记，`tags` 只带前 8 条） |
| `GET /anima-wardrobe-v5/characters/detail?tag=` | 单个角色**完整**记录 + 内置原始标签（编辑弹窗用） |
| `GET /anima-wardrobe-v5/thumb/<slug>` | 角色缩略图（**先查 `user_thumbs/` 再查 `thumbs/`**，自动试 webp/jpg/png） |
| `GET /anima-wardrobe-v5/roll-options` | 随机面板的初值 |
| `POST /anima-wardrobe-v5/roll` | 跑一次抽取（与节点共用同一套引擎） |
| `POST /anima-wardrobe-v5/characters/save` | 新增 / 编辑角色（`mode` = `create` / `edit`） |
| `POST /anima-wardrobe-v5/characters/delete` | 删除自定义角色 |
| `POST /anima-wardrobe-v5/characters/reset` | 内置角色恢复默认 |
| `POST /anima-wardrobe-v5/characters/delete` | 删除角色（v3.18.6：**内置也能删**；传 `tags:[...]` 即批量；内置记录先写 tombstone） |
| `POST /anima-wardrobe-v5/characters/thumb` | 上传预览图（base64 data URL） |
| `POST /anima-wardrobe-v5/characters/thumb-clear` | 清除自定义预览图 |

### 改东西的正确姿势

| 想改什么 | 改哪里 | 改完必须跑 |
|---|---|---|
| **词条** | `ANIMA提示词生成器.html`（**唯一真源**，作者飞蓬，不随本仓库分发） | `node tools/export_v3_pools.mjs` → `python tools/classify_v3_levels.py` |
| **判定表** | 造型台 `wardrobe_rules.py`（**唯一真源**） | `python tools/sync_nsfw_tables.py` |
| **段下限 / 上抬·降级白名单** | `anima_v4_overrides.py` | `python tools/classify_v3_levels.py` |
| **角色库** | `tools/build_characters.py` 里的排除表 / 目标作品 / 阈值 | `python tools/build_characters.py` → `python tests/check_v3_chars.py` |
| **角色编辑 / 自定义角色** | 面板里点 ✎ / ＋ 添加角色（存 `presets/user_characters.json`） | `python tests/check_v3_userdata.py` |
| **场景搭配预设** | `presets/anima_v4_scenes.json`（**人写内容**） | `python tools/build_scenes.py`（校验 + 派生档位）→ `python tests/check_v3_scenes.py` |
| **特写搭配（v3.18.0）** | 同上文件，`group=near` + `manual_only=true` | `python tools/build_scenes.py` → `python tests/check_v3_near.py`（**随机隔离 + 零影响对拍**） |
| 随机逻辑 / 权重 / 角色选中 | `anima_v4_rules.py` | `python tests/run_all.py` |
| **出图元数据（提示词写没写进 PNG）** | `anima_v4_pngmeta.py` | `python tests/check_v3_pngmeta.py`（真机：提交一张最小图，解剖产物） |
| 面板 | `js/anima_wardrobe_v4_studio.js` | `node tests/av3_ui_smoke.mjs` |
| **节点控件个数** | `nodes.py`（**只能追加到末尾**） | 对应版本的迁移脚本：v3.1.0 → `fix_workflows_v301.py`、v3.2.0 → `fix_workflows_v302.py`、**v3.10.0 → `fix_workflows_v303.py`**（都先 `--dry`） |

⚠️ **只改 JSON 不改 HTML，下次导出会被原样冲回去。**

---

## 八、测试基线（只增不减 · 全部 0 失败）

```bash
python tests/run_all.py          # 一键全跑，默认每档 200 次抽样
python tests/run_all.py 500      # 更狠
```

| 测试 | 钉住什么 |
|---|---|
| `check_v3_pools.py` | 词库零漂移（与源 HTML 对拍）+ 档位表一致 + 段下限生效 |
| `check_nsfw_parity.py` | 33 项常量/函数与造型台**逐字一致** + 27 组标签判档行为对拍 |
| `check_v3_gate.py` | 五档 × N 次：准入越界 0 · NSFW 段泄漏 0 · 未登记超档标签 0 · 自检全绿 |
| `check_v3_link.py` | **字段联动（v3.15.0）**：三张表 ↔ 词库一致性 · place 主题覆盖完整 · **运行时零矛盾**（体位配对 / 表情配套）· 场景预抽可用（含 lock/forced）· **场景加权与硬剔除实测生效**（泳池边泳装占比 vs 教室对照）· **sanitize 兜底路径**（全场景随机 80 轮无违和）· **场景搭配库字段引用完整性** |
| `check_v3_pose.py` | **姿势段 + 暗示姿势档位（v3.14.0）**：字段与档位分布 · **段级闸门按"段内最低档"判**（按最高档判会让 SFW 档姿势整段消失）· 逐选项闸门 · **实抽 SFW 零泄漏 / L1·L2 能抽到** · 姿势 tag 无废弃写法 · 场景库引用全合法 |
| `check_v3_weights.py` | 9 组权重语义（0 必无 / 3.0 必现 / 非法输入不炸 / 权重 0 让路…）+ **锁定字段不被法典预设写回**（v3.8.0） |
| `check_v3_near.py` | **特写搭配（v3.18.0）**：32 条结构与部位校验 · **随机隔离（5 档 × N seed 零命中）** · 显式套用才生效 · **摘掉特写后输出 SHA256 全等** · 载荷 manual/part/near_parts · 合法 `sc_*` 不再被误报 · 关 ③ 段后 F10 仍通过 |
| `check_v3_scenes.py` | 场景搭配库（v3.9.0 起）：结构与取值校验 · 派生档位一致 · canon 合并 · 按档可用性 · **预设字段裁不掉（真固定）** · id 不进正文 · 面板载荷与引擎同口径 · **挖矿主题（原「自慰」，v3.11.0）：覆盖 L2/L3/L4 · solo 约定 · 档位闸门** |
| `check_v3_repair.py` | 成品检查与自动修复（v3.8.0）：超档剔除 · 校准项保住 · 判定表盲区折算 · 六组互斥 · 格式归一 · **幂等** · **正常生成零改动** · 校准表不变量（两表不相交 + 选项原文真实存在 + 落盘档位==运行时） |
| `check_v3_roles.py` | 12 组角色语义（含 v3.10.0 的**随机池**：作品名解析 / 只含该作品 / 每次换人 / 可复现 / 优先级 / 无效回退）（分隔符 / 100% 抽取 / 按人数组合抽 N 位 / 群像 / 透传 / 巨乳开关） |
| `check_v3_chars.py` | 角色库结构 + 合规（无宝可梦/无男性）+ 覆盖 + `/characters` 的 work_id 映射 + `--net` 抽查标签真实存在 |
| `check_v3_charhair.py` | **角色官方发型对齐（v3.45.0）**：发型表 key 是真角色 · 值是真词库选项 · 开启后写入官方值 · 关闭一字不写 · 权重 0 让路 · **表里没有的角色开/关逐字段相同（零漂移）** |
| `check_v3_store.py` | 预设/收藏存储：原子写 · 幂等 · 参数校验 · 坏文件容错 · 上限保护 |
| `check_v3_userdata.py` | 用户角色覆盖层：原子写 · 参数校验 · 合并正确性（edits/custom/works.count/**tags 整条替换**）· **缓存纪律** · 删除与恢复默认 · 图片落盘与安全 · **特征标签（列表语义 + 校验 + 引擎采用）** · **内置库逐字节零改动** |
| `check_v3_pngmeta.py` | PNG 元数据注入：**先钉死"病"**（承载位全是空串）· 注入后承载位/终点位/兜底位都写对 · **不越界**（质量词/分隔符/负向/插件自身控件零改动、除文本控件外整份工作流逐字节一致）· 幂等 · **API 只加惰性键且已声明输入零改动** · 异常安全 · 节点接线 |
| `av3_ui_smoke.mjs` | jsdom 真跑面板：**252 条**断言（权重树 / 角色浏览器 / **🎲 按 IP 随机抽角色** / **🔁 随机池** / **🎬 场景搭配页（档位分组 + **默认折叠** + **全部展开** + **👁 非破坏性预览**）** / 收藏 / 预设 / 免责声明 / 巨乳开关 / **角色编辑与自定义角色** / **特征标签增删改** / **段「本档不参与」判据** / **预演请求带 selected_roles+lock_fields**） |

> `av3_ui_smoke.mjs` 的 fetch 桩喂的是 `tools/dump_ui_fixtures.py` 从**真后端**
> 导出的夹具 —— 接口改了字段名，冒烟立刻红。它抓到过 4 个真 bug：
> 面板把 `/contract` 的 `option_count` 用在 `/pools` 的字段上（权重细则按钮全灰）、
> 改了权重没点「采用」就不生效、**点档位按钮直接抛异常导致档位切不动**（v3.0.0 就存在）、
> 缩略图加载失败没退化处理。

---

---

## 附、仓库边界与发版

> 编号避开正文章节 —— 「九」在本文档之外是「已知限制」，别混。

### `.gitignore` 里为什么排除了这些

| 排除项 | 体积 | 理由 | 缺席后果 |
|---|---|---|---|
| `presets/thumbs/` | 16 MB / ~2400 张 | 取自公开图库的他人作品，公开仓库转存有版权风险 | 角色浏览器退化为首字母色块，功能不受影响 |
| `tools/.cache_chars` `tools/.cache_roles` | 12 MB / 3600 文件 | 建库断点续跑缓存，可重建 | 重跑 `build_characters.py` 会重新联网拉数据 |
| `*.bak-*` | 单文件最大 1.9 MB | 引擎改写前落的本地回滚快照，属单机历史 | 无法回滚到改动前，但数据文件本身仍完整 |
| `presets/user_thumbs/` | 20 KB | 用户上传的角色预览图，属个人数据 | 自定义角色的预览图丢失 |
| `__pycache__` | 624 KB | 构建产物，跨 Python 版本不通用 | 无 |
| `_roll_error.log` | — | 含本机绝对路径的 traceback | 出错时重新生成 |

`presets/user_*.json` 五份**在仓库里是空模板**（保留 schema、清空内容）：
别人的收藏与自建角色不该出现在公开仓库里。首次启动时引擎会重建结构。

### 发版检查清单

1. `__init__.py` 的 `__version__` 改掉，`README.md` 版本徽章同步改
2. `docs/CHANGELOG.md` 顶部加一条（格式照抄现有行：`| **vX.Y.Z** | 改了什么 / 为什么 / 怎么验证 |`）
3. `python tests/run_all.py` —— 失败项不多于三项历史基线
4. `node tests/av3_ui_smoke.mjs` —— 全绿（v5.0.8 基线 481 条断言）
   ⚠️ 这条需要 `jsdom`：先 `npm i jsdom`（仓库不锁 `node_modules`），
   并先跑 `python tools/dump_ui_fixtures.py` 生成喂给桩的接口夹具
5. `git status --short` —— 没有意料外的文件（尤其 `presets/user_*.json` 不要带上本地改动）
6. 打 tag 并推送：`git tag vX.Y.Z && git push origin vX.Y.Z`

### 数据文件的"真源"关系（别搞反）

```
ANIMA提示词生成器.html（飞蓬，不随仓库分发）
        │  tools/export_v3_pools.mjs
        ▼
presets/anima_v4_pools.json  ──► tools/classify_v3_levels.py ──► presets/anima_v4_levels.json
        │  （零漂移导出物，禁手改）                                    （派生数据）
        ▼
tests/fixtures/pools.json（对拍基线，tools/dump_ui_fixtures.py 生成）
```

⚠️ **只改 JSON 不改上游，下次导出会被原样冲回去。**

`presets/anima_v4_scenes.json` 是例外 —— 它是**人写内容**（不是导出物），
改完跑 `tools/build_scenes.py --check` 校验并派生档位。

`presets/anima_v4_characters.json` 是**联网构建**的只读产物：
改法在 `tools/build_characters.py` 的排除表 / 目标作品 / 阈值，
手工补录写 `tools/manual_characters.json`（重跑不会丢）。
