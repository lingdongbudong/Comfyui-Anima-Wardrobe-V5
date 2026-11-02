# Comfyui-Anima-Wardrobe-V5

> **ANIMA3 提示词随机生成 · ComfyUI 自定义节点**
> 按五级 NSFW 档位随机组合一段**完整英文正文**，直接喂给 `Anima_工作流V3` 的「全局正文」节点。
> 纯本地、零第三方依赖、运行时零联网 —— 只生成提示词，不生成图片。

<!-- 徽章用静态端点，不依赖仓库是否已发布 -->
![version](https://img.shields.io/badge/version-v5.0.8-blue)
![license](https://img.shields.io/badge/license-GPL--3.0-green)
![python](https://img.shields.io/badge/python-3.10%2B-yellow)
![deps](https://img.shields.io/badge/dependencies-zero-success)
![nodes](https://img.shields.io/badge/nodes-4-orange)
![offline](https://img.shields.io/badge/runtime-offline-lightgrey)

> [!WARNING]
> **内含成人向内容（NSFW）。**
> 词库包含 `explicit` / `hardcore` / `extreme` 三级真实露骨词条 —— 默认档位是 `sfw`，
> 但任何人都可以主动调高。**仅限 18 岁以上使用。**
> 所有角色一律视为 18 岁以上的**虚构**人物；**禁止**用于真实人物、未成年人、
> 非自愿及暴力伤害相关内容。若你所在地区或所用平台不允许此类内容，请勿安装。

> 章节编号沿用自早期版本（「一、」「三、」），所以有跳号 —— 其余章节已迁到 `docs/`。
> 保留原编号是为了不打断文中大量「见四之七」这类交叉引用。对照表见 [文档索引](#文档索引)。

---

## 这是什么

一个把浏览器单文件工具 `ANIMA提示词生成器.html`（作者：飞蓬）的资产搬进 ComfyUI 的插件：
**按档位收窄候选池 → 随机组合 → 自检回滚 → STRING 直出**，结果可复现、可批量、可审计。

四个节点、零依赖、零联网。与 `Comfyui-Anima-Wardrobe`（造型台 v2.x）**可以同时安装**：
类名、分类、HTTP 路由、前端脚本全部独立命名。

```text
┌──────────────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│ Anima 提示词随机生成(V5)  │ text │  CR Text 1004    │      │  六条底模流       │
│ 档位 / 权重 / 角色 / 场景 │─────▶│ （全局正文端口）  │─────▶│  自动全部吃到     │
└──────────────────────────┘      └──────────────────┘      └──────────────────┘
        │ report / level / cn_summary                        接上后工作流零改动
        ▼                                                    拔掉线回手写文本框
  接「分级审查」做自检；接「拼接台」并入自己的手写正文
```

## 核心特性

| 特性 | 说明 |
|---|---|
| **五级档位闸门** | `sfw` / `L1`~`L4` / `不限`。低档**先从候选池排除**，不是抽完再筛 —— 这才是 SFW 档真正干净的原因 |
| **三层权重** | 段 / 字段 / 选项，`0` = 关闭，`1` = 常态，`3.0` = 必现。越档选项点到 3.0 也进不来（闸门优先） |
| **角色库 2390 位** | 联网构建的只读数据，覆盖 284 个作品 IP；可收藏、可编辑、可自建、可锁官方服装 |
| **场景搭配 271 条** | 场景 / 特写 / 姿势三类，每条锁字段 + 派生档位 + 可选变体池 |
| **可复现** | 同 `seed` 同设置正文**逐字相同**；`-1` 才每次重抽 |
| **出图元数据** | 把完整正向写进 PNG（`anima_v4_prompt` 块），**不改你的工作流** |
| **零依赖零联网** | 纯 Python 标准库 + 原生 JS。不联网、不上传、不调大模型 |
| **可自检** | 每次抽取自带 `report`（越界 / 回滚 / 让路原因逐条写明），另有独立审查节点 |

## 一、它解决什么

源脚本 `ANIMA提示词生成器.html` 是个浏览器单文件工具，靠「复制 → 粘贴进 ComfyUI
节点 1004」或「存成 prompts.txt」进入流程。它有 90% 的资产可以直接搬，但有四个硬缺口：

| 缺口 | 源脚本现状 | 本插件 |
|---|---|---|
| 没有分级 | 只有 `SFW` / `NSFW` 两个按钮，一刀切 | **五级闸门**，逐级放开段落；低档绝不越界 |
| 盲抽后补锅 | `Math.random()<0.65` 先抽，抽完才打补丁，高档内容会漏进低档 | 候选池**先按档位收敛**，抽完再体检、超档回滚 |
| 权重不可调 | 一个写死的概率 | **三层权重**：段 / 字段 / 选项，0 = 关闭，3.0 = 必现 |
| 结果出不去 | 只留在浏览器 | STRING 直出，可复现、可批量、可审计 |

## 三、节点

| 节点 | 分类 | 主要输入 | 输出 |
|---|---|---|---|
| `AnimaV5RandomPrompt`<br>**Anima 提示词随机生成（V5）** | AnimaWardrobeV5 | `nsfw_level` 档位 · `seed` · `tag_cap` · `base_prob` · `selected_roles` 已选角色 · `scene_pick` 场景开关 · 共 23 个控件，全表见[附录 A](docs/USAGE.md#附录-a节点参数全表) | `text` 英文标签串<br>`report` 自检报告<br>`level` 实际档位<br>`cn_summary` 中文摘要 |
| `AnimaV5PromptGrader`<br>**Anima 提示词分级审查（V5）** | 同上 | `text`（可接线上游） · `detailed` | `text` 透传 · `num` 档位数字<br>`level` 档位 key · `report` 明细 |
| `AnimaV5PromptAssemble`<br>**Anima 提示词拼接台（V5）** | 同上 | `main` 随机结果 · `supplement` 手写补充 · `mode` · `max_level` | `text` |
| `AnimaV5PromptCheck`<br>**Anima 提示词检查与修复（V5）** | 同上 | `text` 任意提示词 · `level` 目标档位 · `auto_fix` | `text` · `report` · `level` · `num` |

节点上另有四个按钮：`⚙ 打开随机面板` · `🔁 换种子` · `🎲 每次重抽` · `🧹 清空权重`。
界面**全中文**（`locales/zh` 与 `locales/en` 都放中文，所以浏览器语言是英文也显示中文）。

> **界面口径**：能在面板里配的项，节点上不重复外露（档位 / 段开关 / 权重都只在面板里）；
> 动作类按钮保留在节点上。与 Krea2 系列插件是同一套规矩。

## 安装

### 方式一：git clone（推荐，便于升级）

```bash
cd <ComfyUI>/custom_nodes
git clone https://github.com/lingdongbudong/Comfyui-Anima-Wardrobe-V5.git
# 重启 ComfyUI
```

### 方式二：ZIP

下载仓库 ZIP → 解压到 `<ComfyUI>/custom_nodes/` →
**确认层级是 `custom_nodes/Comfyui-Anima-Wardrobe-V5/__init__.py`**
（ZIP 常多套一层，这是最常见的一种装不上）。

### 没有依赖要装

运行时纯标准库。只有两个**可选**的构建脚本需要额外东西：

| 脚本 | 额外依赖 | 用途 |
|---|---|---|
| `tools/fetch_character_thumbs.py` | Pillow（用 ComfyUI 的 `python_embeded` 跑） | 抓角色缩略图（不随仓库分发） |
| `tools/build_characters.py` | 联网 | 重建角色库（约 30 分钟，有缓存可续跑） |

## 快速上手

1. **验证装没装成功**：打开 `workflows/Anima-V5_独立提示词输出.json` 点运行 ——
   不出图、不需要任何模型或 LoRA。看到一段英文标签串就是通了。
   （这份工作流用到 Comfyroll 的 `CR Save Text To File`；没装可以删掉那两个保存节点，
   直接看 STRING 输出。）
2. **接进出图工作流**：拖入「Anima 提示词随机生成（V5）」，把 `text` 输出连到
   **CR Text 节点 1004 那个空着的 text 输入端口**。接上后六条底模流自动全部吃到，
   工作流一根线都不用改；拔掉线就回到手写文本框。
3. **调档位和权重**：点节点上的 `⚙ 打开随机面板`。档位、段开关、逐选项权重都在面板里。

## 参数速查

只列最常改的几个，全表见 [附录 A：节点参数全表](docs/USAGE.md#附录-a节点参数全表)。

| 参数 | 默认 | 什么时候改它 |
|---|---|---|
| `nsfw_level` | `sfw` | 想要更露骨：`L1` → `L2` → `L3` → `L4`。低档不会越界 |
| `seed` | `-1` | 想复现某张图：把当时的 seed 填进来（`>=0` 即钉死） |
| `base_prob` | `0.65` | 觉得字段出现得太频繁 / 太稀疏。受它控制的字段本来就不是每张都有 |
| `tag_cap` | `自动` | 标签太多把别的词挤掉了，或想强制精简 |
| `role_pick` | `True` | 勾掉 = 这一抽**完全不抽角色**，人物特征全交给词库权重 |
| `scene_pick` | `False` | 勾上 = **必出**一条场景搭配（按当前档位锁档抽） |
| `selected_roles` | 空 | 在面板「角色库」里点选，会自动写进这里 |
| `weights_json` | 空 | 一般不用手写 —— 面板点出来的就是这个 |

## 示例文件

| 文件 | 用途 | 额外依赖 |
|---|---|---|
| `workflows/Anima-V5_独立提示词输出.json` | 6 个节点、不出图，**验证插件装好没** | Comfyroll（`CR Save Text To File`，可删） |
| `presets/anima_v4_pools.json` | 词库真源导出物：15 段 / 57 字段 / 1134 选项 | 无（**禁手改**，见 MAINTAINERS） |
| `presets/anima_v4_characters.json` | 角色库 2390 位 / 284 作品 IP（只读） | 无 |
| `presets/anima_v4_scenes.json` | 场景 271 条（人写内容，不是导出物） | 无 |
| `presets/character_outfits.json` | 2316 位角色的官方服装预设 | 无 |
| `presets/user_*.json` | 收藏 / 预设 / 自建角色 —— **仓库里是空模板** | 运行时自动生成 |
| `docs/特写场景搭配_可行性评估.md` | 特写搭配为什么这么做（设计取舍记录） | 无 |
| `docs/特写场景搭配_设计稿-v1.md` | 特写搭配的一稿设计（保留作为决策记录） | 无 |

## 文档索引

| 文档 | 内容 |
|---|---|
| [README](README.md) | 门面：它是什么 / 节点 / 安装 / 快速上手（就是本页） |
| [docs/USAGE.md](docs/USAGE.md) | **完整使用手册**：五级档位 / 角色库 / 收藏预设 / 场景搭配 / 三层权重 / 参数全表 / 31 条 FAQ |
| [docs/MAINTAINERS.md](docs/MAINTAINERS.md) | 维护者指南：六条硬契约 / 验证三件套 / 目录与数据流 / 测试基线 / 仓库边界与发版 |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | 版本历史（每条写清「改了什么 / 为什么 / 怎么验的」） |

**章节编号对照**（为什么有跳号）：

| 原编号 | 现在的位置 |
|---|---|
| 一、它解决什么 · 三、节点 | 本页 |
| 二、四、四之二~四之十、五、六、九、十 | [docs/USAGE.md](docs/USAGE.md) |
| 七、八 | [docs/MAINTAINERS.md](docs/MAINTAINERS.md) |
| 十一、版本历史 | [docs/CHANGELOG.md](docs/CHANGELOG.md) |

## 兼容性与已知限制

- **ComfyUI**：需要支持 `WEB_DIRECTORY` 的版本（2024 年后的正式版均可）。
- **Python**：3.10+（与 ComfyUI 一致）。
- **并存**：可与造型台 v2.x 同时安装；节点菜单里会出现 V5 / V4 / V3 三套同名节点，
  那是**别名兼容**（旧工作流存的是类名，删别名会全部报「节点缺失」）。新工作流用 V5。
- **角色缩略图不随仓库分发**（约 2400 张取自公开图库）—— 缺席时面板退化为首字母色块，
  不阻塞任何功能。想补：`python tools/fetch_character_thumbs.py`。
- **词库的唯一真源是 `ANIMA提示词生成器.html`（作者飞蓬），不随本仓库分发。**
  所以「从 HTML 重新导出词库」这条流水线在拿到那个文件之前跑不了；
  但**读词库、改场景、改角色、调权重、跑节点全都不需要它**。
- **数据文件进进程级缓存**：改了 `presets/*.json` 必须重启 ComfyUI 后端才生效。
- 完整限制清单见 [docs/USAGE.md · 九、已知限制与待办](docs/USAGE.md#九已知限制与待办)。

## 署名与来源

| 角色 | 谁 |
|---|---|
| 插件作者 | **灵冻不冻**（[@lingdongbudong](https://github.com/lingdongbudong)） |
| 上游词库与框架 | `ANIMA提示词生成器.html`，作者 **飞蓬**（作者声明已授权开源，未指明具体许可证） |
| NSFW 判定口径 | 与 `Comfyui-Anima-Wardrobe`（造型台 v2.x）的 `AnimaNSFWGrader` 逐字对齐，有 33 项常量对拍 |
| 角色库数据 | 取自公开的 Danbooru 标签统计；角色名与作品名归各自权利人所有 |
| 运行平台 | [ComfyUI](https://github.com/comfyanonymous/ComfyUI)（GPL-3.0，与本项目无隶属关系） |

本插件**不附带任何图像**。角色名仅用于提示词检索与描述。

## 许可证

[GPL-3.0](LICENSE)。`LICENSE` 末尾附有**来源与第三方声明**（不属于许可条款）：
上游授权状态、判定口径归属、角色名权属、运行环境关系。
