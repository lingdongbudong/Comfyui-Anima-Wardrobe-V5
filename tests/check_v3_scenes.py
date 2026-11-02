# -*- coding: utf-8 -*-
"""场景搭配预设库基线（v3.9.0）。

「一键设置场景搭配」= 把 姿势/场景/表情/动作 的固定组合一次套用，套用到的
字段不参与随机。它复用**法典场景那一套机制**（`canon()` 合并 → `apply_preset`
填充 → 档位/权重/锁定三闸门），所以这组基线要钉住的不只是"数据文件合法"，
而是**这条复用链路真的按预期工作**：

  ① 数据层   —— build_scenes --check 通过（派生档位与磁盘一致）、字段/选项真实存在、
                不得写 count/role、id 不与法典撞名。
  ② 合并层   —— canon() = 法典 14 组 + 场景 N 条；法典条目逐字节不变。
  ③ 闸门层   —— 按档位可用性正确（L0 抽不到 L2+ 的场景）；
                强制指定超档场景时 F15 必须报出来。
  ④ 应用层   —— 预设字段真的被写进 state；**被 trim 裁不掉**（"真固定"）。
  ⑤ 输出层   —— 预设 id **不出现在正文里**；同 seed 逐字节可复现。
  ⑥ 载荷层   —— /pools 的 n_canon 候选数与引擎一致；/scenes 的字段名有中文标签。

跑法：python tests/check_v3_scenes.py
"""
import os
import subprocess
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import _boot  # noqa: E402

R = _boot.load("anima_v4_rules")
BUILD = os.path.join(PLUGIN, "tools", "build_scenes.py")

FAILS = []


def ck(name, cond, note=""):
    if cond:
        print(f"  [OK] {name}")
    else:
        print(f"  [!!] {name}  {note}")
        FAILS.append(name)


def main():
    print("── ① 数据层：构建脚本校验 + 结构 ──")
    r = subprocess.run([sys.executable, BUILD, "--check"],
                       capture_output=True, text=True, cwd=PLUGIN)
    ck("build_scenes --check 通过（派生档位与磁盘一致）", r.returncode == 0,
       (r.stdout + r.stderr).strip().replace("\n", " | ")[:200])

    scenes = R.scene_list()
    ck("场景库非空", len(scenes) > 0, str(len(scenes)))
    ids = [s["id"] for s in scenes]
    ck("id 唯一", len(set(ids)) == len(ids))
    ck("id 一律以 sc_ 开头（与法典 c1..c14 区分）",
       all(i.startswith("sc_") for i in ids))
    canon_ids = set(R.pools().get("canon", {}).keys())
    ck("id 不与法典预设撞名", not (set(ids) & canon_ids),
       str(sorted(set(ids) & canon_ids)))

    forbidden = [(s["id"], k) for s in scenes for k in ("count", "role")
                 if k in (s.get("tags") or {})]
    ck("没有预设去写 count / role（人数与角色是地基）", not forbidden,
       str(forbidden[:3]))

    bad = []
    for s in scenes:
        for k, v in (s.get("tags") or {}).items():
            _sec, fld = R.field_by_key(k)
            if not fld or v not in [en for _zh, en in fld.get("opts", [])]:
                bad.append((s["id"], k, v))
    ck("每条预设的字段与取值都真实存在（写错=静默失效）", not bad, str(bad[:3]))

    by_group = {}
    for s in scenes:
        by_group[s["group"]] = by_group.get(s["group"], 0) + 1
    ck("分组齐全（sfw / nsfw 都有）",
       {"sfw", "nsfw"} <= set(by_group), str(by_group))

    # ── v3.21.0：姿势场景分组 ──────────────────────────────────
    pose = [s for s in scenes if s.get("group") == "pose"]
    ck("存在「姿势场景」分组（group=pose）", len(pose) >= 24, f"{len(pose)} 条")
    ck("姿势场景每条都写了 pose_base",
       all("pose_base" in (s.get("tags") or {}) for s in pose),
       str([s["id"] for s in pose if "pose_base" not in (s.get("tags") or {})][:3]))
    ck("姿势场景的 theme 以「姿势·」开头（面板角标可辨）",
       all(str(s.get("theme") or "").startswith("姿势·") for s in pose),
       str([s["id"] for s in pose if not str(s.get("theme") or "").startswith("姿势·")][:3]))
    pure = [s for s in pose if "place" not in (s.get("tags") or {})]
    ck("纯姿势型不锁地点（可套用在任何环境）", len(pure) >= 14, f"{len(pure)} 条")
    ck("完整造型型锁了地点", len(pose) - len(pure) >= 10, f"{len(pose) - len(pure)} 条")
    ck("姿势场景覆盖跪坐/正座类",
       any("seiza" in (s.get("tags") or {}).values() for s in pose))
    ck("姿势场景全部落在 SFW 档（L0/L1）",
       all(int(s["level"]) <= 1 for s in pose),
       str(sorted({int(s["level"]) for s in pose})))

    lv0 = [s["id"] for s in scenes if int(s["level"]) == 0]
    ck("存在全年龄档（L0）场景 —— SFW 一键搭配可用", len(lv0) >= 5,
       f"{len(lv0)} 条")

    # ── ①之二 人数钉死（v3.22.1）────────────────────────────────
    # 报障：场景写的 `n_act` 整段消失，肛交变群交、单人自慰变双人。
    # 根因是人数随机抽到多人 → 引擎清空单人向字段，而场景库没声明人数。
    # 这一组断言就是那次修复的护栏。
    locked = [s for s in scenes if s.get("count_lock")]
    ck("有 count_lock 的场景 ≥ 40 条（双人正戏 / 自慰 / 双女 / 群体）",
       len(locked) >= 40, str(len(locked)))
    # v4.5.0：中性的双女写法（`2girls, multiple girls`）不进随机池，只给场景钉人数 ——
    # 往 count 字段加第 7 个选项会重排所有未锁人数的抽取（零漂移对拍会全红）。
    _COUNT_OK = set([en for _z, en in R.field_by_key("count")[1]["opts"]]) \
        | set(R.COUNT_LOCK_EXTRA)
    ck("count 取值合法（不写空串、必须是 count 选项或中性双女写法）",
       all(s["count_lock"] in _COUNT_OK for s in locked),
       str([s["id"] for s in locked if s["count_lock"] not in _COUNT_OK][:3]))
    ck("count_lock 档位不高于条目档位（否则闸门会静默跳过）",
       all(R.count_lock_level(s["count_lock"]) <= int(s["level"]) for s in locked),
       str([s["id"] for s in locked
            if R.count_lock_level(s["count_lock"]) > int(s["level"])][:3]))
    # 引擎级：套用后人数必须变成声明值，且场景的 n_act / n_pos 不再被多人分支清空
    allids = [en for _z, en in R.field_by_key("n_canon")[1]["opts"]] + \
             [sid for _z, sid, _n in R.scene_options(99, include_manual=True)]
    bad_count, lost_act = [], []
    for s in locked:
        w = R.empty_weights()
        w["fields"]["n_canon"] = 3.0
        bag = {k: 0.0 for k in allids}; bag[s["id"]] = 3.0
        w["options"]["n_canon"] = bag
        lvk = {0: "sfw", 1: "suggestive", 2: "explicit",
               3: "hardcore", 4: "extreme"}[int(s["level"])]
        st = R.draw(level=lvk, seed=7, weights=w, base_prob=0.9)["state"]
        if st.get("count") != s["count_lock"]:
            bad_count.append((s["id"], st.get("count"), s["count_lock"]))
        for k in ("n_act", "n_pos", "n_theme"):
            if s["tags"].get(k) and not st.get(k):
                lost_act.append((s["id"], k, s["tags"][k]))
    # v3.22.3（用户口径）：非必要多人的场景一律一名女性
    nolock = [s["id"] for s in scenes
              if s.get("group") != "near" and not s.get("manual_only") and not s.get("count_lock")]
    ck("每条非特写场景都声明了人数（count_lock）", not nolock, str(nolock[:3]))
    MULTI_F = ("2girls, yuri", "multiple girls, orgy")
    # 必要多人白名单：双女互慰（2 女）+ RBQ 壁尻共用（群交，用户 2026-10-23 明确要求）
    # + v3.42.2 那批 L4 SM 场景（v3.42.7 起 9 条已改单人，只剩「双女对悬」一条 2girls，
    #   其余 id 保留登记：万一将来又被改成双女，不用再跑一次白名单）
    # v4.5.0：新增的 6 条「双女日常互动」（用户 2026-10-30 拍板，补 L0/L1 零覆盖）。
    #   3 条 L0 走中性的 `2girls, multiple girls`（不写 yuri），
    #   3 条 L1 写 `2girls, yuri`（关系标签自 v4.5.0 起降到擦边档）。
    #   它们本来就是"必要多人"，所以登记进白名单而不是放宽规则。
    DUO_DAILY = {
        "sc_duo_hand_in_hand", "sc_duo_back_hug", "sc_duo_selfie",
        "sc_duo_lap_pillow", "sc_duo_feeding", "sc_duo_hair_braid",
    }
    WHITE_MULTI = {"sc_msb_mutual", "sc_ccc_rbq_wall"} | DUO_DAILY | {
        "sc_les_sm_suspension_pair", "sc_les_sm_suspension_twine",
        "sc_les_sm_pillory_duo", "sc_les_sm_wax_bound",
        "sc_les_sm_mutual_rope", "sc_les_sm_backtoback",
        "sc_les_sm_pet_leash", "sc_les_sm_collar_hold",
        "sc_les_sm_enema_bound", "sc_les_sm_clamp_pull"}
    # 特写里的「双女」组（舔阴 / 双女胸部 6 条）是必要多人，单独算，不参与这条
    bad_multi = [s["id"] for s in scenes
                 if s.get("count_lock") in MULTI_F and s["id"] not in WHITE_MULTI
                 and not s.get("manual_only")]
    ck("非特写场景里多女只在白名单（其余都是一名女性）", not bad_multi, str(bad_multi[:3]))
    ck("默认（sfw/pose）都是 1girl, solo（双女日常互动除外）",
       all(s["count_lock"] == "1girl, solo" for s in scenes
           if s.get("group") in ("sfw", "pose")
           and s["id"] not in DUO_DAILY),
       str([s["id"] for s in scenes if s.get("group") in ("sfw", "pose")
            and s["id"] not in DUO_DAILY
            and s["count_lock"] != "1girl, solo"][:3]))
    ck("双女日常互动覆盖 L0 与 L1（各 ≥ 3 条）",
       sum(1 for s in scenes if s["id"] in DUO_DAILY and s["level"] == 0) >= 3
       and sum(1 for s in scenes if s["id"] in DUO_DAILY and s["level"] == 1) >= 3,
       str([(s["id"], s["level"]) for s in scenes if s["id"] in DUO_DAILY]))
    # ── v3.24.0：候选构图变体 / 贴地场景的相机禁令 ───────────────────
    pz = next((x for x in scenes if x["id"] == "sc_ccc_paizuri"), {})
    rv = pz.get("random_variants") or []
    ck("乳交有 2 个构图变体（我躺着 / 我坐着）",
       [v.get("zh") for v in rv] == ["我躺着", "我坐着"], str([v.get("zh") for v in rv]))
    wm = next((x for x in scenes if x["id"] == "sc_cam_worm_sit"), {})
    props = (wm.get("random_fields") or {}).get("prop") or []
    ck("贴地场景坐处候选 = 台阶 / 椅子 / 沙发",
       props == ["stairs", "chair", "couch"], str(props))
    # 相机禁令：device 闭麦 + 正文 20 抽不出现相机类词
    ck("贴地场景闭麦 device（selfie / 监控 这类会带出相机）",
       "device" in (wm.get("drop_fields") or []), str(wm.get("drop_fields")))
    # ⚠️ v4.4.3：`lens` 必须也在名单里 —— 曾把 "the camera looks up" 换成
    #    "the lens looks up"，机器照画不误（模型把 lens 当成一台躺在地上的镜头），
    #    「贴地超广角·坐姿长腿」就是这么画出一台相机的。
    BADW = ("camera", "lens", "selfie", "webcam", "photo", "phone", "dslr",
            "tripod", "shutter")
    hit = []
    for sd in range(20):
        w20 = R.empty_weights()
        w20["fields"]["n_canon"] = 3.0
        ids20 = [en for _z, en in R.field_by_key("n_canon")[1]["opts"]] + \
                [x for _z, x, _n in R.scene_options(99, True)]
        bag20 = {k: 0.0 for k in ids20}; bag20["sc_cam_worm_sit"] = 3.0
        w20["options"]["n_canon"] = bag20
        txt = R.draw(level="suggestive", seed=7000 + sd, weights=w20, base_prob=0.9)["text"].lower()
        got = [b for b in BADW if b in txt]
        if got:
            hit.append((sd, got))
    # ── v3.26.0：雨中透衫回眸 —— 只剩一把伞的反面：一把都不要 ────────
    rw = next((x for x in scenes if x["id"] == "sc_rain_wetshirt"), {})
    ck("雨中透衫：不再有裸 umbrella 标签",
       "umbrella" not in str(rw.get("extra", "")).lower(), str(rw.get("extra"))[:80])
    ck("雨中透衫：闭麦 prop（prop 池里有 umbrella / parasol）",
       "prop" in (rw.get("drop_fields") or []), str(rw.get("drop_fields")))
    ck("雨中透衫：仍是擦边 L1（未被 wet clothes 之类抬档）",
       int(rw.get("level", -1)) == 1, str(rw.get("level")))
    UMB = ("umbrella", "parasol", "canopy")
    ubad, hand_bad = [], []
    for sd in range(20):
        w20 = R.empty_weights()
        w20["fields"]["n_canon"] = 3.0
        ids20 = [en for _z, en in R.field_by_key("n_canon")[1]["opts"]] + \
                [x for _z, x, _n in R.scene_options(99, True)]
        bag20 = {k: 0.0 for k in ids20}; bag20["sc_rain_wetshirt"] = 3.0
        w20["options"]["n_canon"] = bag20
        rr = R.draw(level="suggestive", seed=6500 + sd, weights=w20, base_prob=0.9)
        txt = rr["text"].lower()
        if any(b in txt for b in UMB):
            ubad.append(sd)
        if rr["state"].get("pose_risque") != "hair flip":
            hand_bad.append((sd, rr["state"].get("pose_risque"),
                             rr["state"].get("arms_hands")))
    ck("雨中透衫：20 抽正文零伞类词（不再出现凭空第二把）", not ubad, str(ubad[:3]))
    # ── v3.27.0：护士查房（多池变体：姿势 × 道具）──────────────────
    nu = next((x for x in scenes if x["id"] == "sc_nurse_rounds"), {})
    pools = R.scene_random_variants("sc_nurse_rounds")
    ck("护士查房：变体是多池（姿势 + 道具两个池）",
       [p["key"] for p in pools] == ["pose", "tool"], str([p["key"] for p in pools]))
    ck("护士查房：姿势池 5 个、道具池 4 个（含空手）",
       [len(p["items"]) for p in pools] == [5, 4], str([len(p["items"]) for p in pools]))
    ck("护士查房：道具池里有「空手」（用户口径：可以不拿东西）",
       any(it["zh"] == "空手" for it in pools[1]["items"]),
       str([it["zh"] for it in pools[1]["items"]]))
    ck("护士查房：闭麦 prop / pose_base / arms_hands（会与姿势和持物打架）",
       all(k in (nu.get("drop_fields") or []) for k in ("prop", "pose_base", "arms_hands")),
       str(nu.get("drop_fields")))
    # 乳交是单池写法，扩成多池后必须仍然只返回 1 个池
    pz_pools = R.scene_random_variants("sc_ccc_paizuri")
    ck("单池写法（数组）仍解析为 1 个池",
       len(pz_pools) == 1 and len(pz_pools[0]["items"]) == 2, str(len(pz_pools)))
    TOOLS = ("clipboard", "stethoscope", "medical tray")
    JUNK = ("ice cream", "wine glass", "cake", "balloon", "parasol", "umbrella")
    multi, junk, empty_cnt = [], [], 0
    for sd in range(20):
        w20 = R.empty_weights()
        w20["fields"]["n_canon"] = 3.0
        ids20 = [en for _z, en in R.field_by_key("n_canon")[1]["opts"]] + \
                [x for _z, x, _n in R.scene_options(99, True)]
        bag20 = {k: 0.0 for k in ids20}; bag20["sc_nurse_rounds"] = 3.0
        w20["options"]["n_canon"] = bag20
        txt = R.draw(level="suggestive", seed=7400 + sd, weights=w20, base_prob=0.9)["text"].lower()
        n_tool = sum(1 for t in TOOLS if t in txt)
        if n_tool > 1:
            multi.append((sd, n_tool))
        if n_tool == 0:
            empty_cnt += 1
        if any(b in txt for b in JUNK):
            junk.append(sd)
    ck("护士查房：20 抽手里至多一件道具（含空手，不会两件以上）", not multi, str(multi[:3]))
    # 空手是 1/4 概率；20 抽里既不能一次不出（说明池没接上），也不该占多数
    ck("护士查房：空手能抽到、但不是多数（1–12 / 20）", 1 <= empty_cnt <= 12,
       f"{empty_cnt}/20")
    # ── v3.27.2：偷窥场景 —— 画面内不出现相机与监控 UI ──────────────
    vo = next((x for x in scenes if x["id"] == "sc_ccc_voyeur_cam"), {})
    ck("偷窥场景：extra 不再含 camera（裸名词会要求把机器画进来）",
       "camera" not in str(vo.get("extra", "")).lower(), str(vo.get("extra"))[:80])
    ck("偷窥场景：tags 不再有 device（security camera footage 会带监控 UI）",
       "device" not in (vo.get("tags") or {}), str((vo.get("tags") or {}).get("device")))
    ck("偷窥场景：闭麦 device / prop / n_cum",
       all(k in (vo.get("drop_fields") or []) for k in ("device", "prop", "n_cum")),
       str(vo.get("drop_fields")))
    VPS = ["from above", "from side", "from behind", "dutch angle", "framed by foreground"]
    ck("偷窥场景：机位 5 选 1（俯视 / 平视 / 背后 / 斜角 / 前景框住）",
       (vo.get("random_fields") or {}).get("viewpoint") == VPS,
       str((vo.get("random_fields") or {}).get("viewpoint")))
    CAM = ("camera", "lens", "footage", "cctv", "webcam", "tripod", "shutter")
    cam_hit, vp_seen = [], set()
    for sd in range(40):
        w20 = R.empty_weights()
        w20["fields"]["n_canon"] = 3.0
        ids20 = [en for _z, en in R.field_by_key("n_canon")[1]["opts"]] + \
                [x for _z, x, _n in R.scene_options(99, True)]
        bag20 = {k: 0.0 for k in ids20}; bag20["sc_ccc_voyeur_cam"] = 3.0
        w20["options"]["n_canon"] = bag20
        rr = R.draw(level="explicit", seed=6600 + sd, weights=w20, base_prob=0.9)
        txt = rr["text"].lower()
        vp_seen.add(rr["state"].get("viewpoint") or "")
        cam_hit += [(sd, b) for b in CAM if b in txt]
    ck("偷窥场景：40 抽正文零相机类词", not cam_hit, str(cam_hit[:3]))
    # ── v3.29.0：第三人称·俯视（原「第一人称·俯视自身」改名）/ 新「第一人称·俯视自身」──
    t3 = next((x for x in scenes if x["id"] == "sc_ccc_pov_crotch_self"), {})
    ck("改名：sc_ccc_pov_crotch_self 现在叫「第三人称 · 俯视」",
       t3.get("zh") == "第三人称 · 俯视", str(t3.get("zh")))
    ck("改名：内容同步成第三人称（viewpoint=from above，不含 pov）",
       (t3.get("tags") or {}).get("viewpoint") == "from above"
       and "pov" not in str(t3.get("tags")).lower(),
       str((t3.get("tags") or {}).get("viewpoint")))
    ck("改名：extra 不再有 first-person / own body",
       "first-person" not in str(t3.get("extra", "")).lower()
       and "own body" not in str(t3.get("extra", "")).lower(), str(t3.get("extra"))[:80])
    ck("改名：闭麦 n_act / n_pos / prop（避免 handjob、bent over、卧室杂货）",
       all(k in (t3.get("drop_fields") or []) for k in ("n_act", "n_pos", "prop")),
       str(t3.get("drop_fields")))

    t1 = next((x for x in scenes if x["id"] == "sc_ccc_pov_self_body"), {})
    # v4.5.37（用户：场景改为第三人称摄影）→ 改名「第三人称 · 坐床沿俯视」，id 不变
    ck("存在「第三人称 · 坐床沿俯视」", t1.get("zh") == "第三人称 · 坐床沿俯视", str(t1.get("zh")))
    # ── v4.5.30：真机出现「第三人称俯拍 + 完整人脸」后修正 ──────────────
    # 根因两条：① `pov crotch` 在 Danbooru 里更偏「镜头贴近胯部」，不是
    #   「自己低头看自己」；② `extreme close-up` 会让模型直接给一张**脸部大特写**。
    # 现改为 `first-person view, pov` + `cowboy shot`，并把「脸/下巴不入画」写进画框。
    ck("坐床沿俯视：第三人称斜上方俯拍（from above）+ 情色 L2",
       (t1.get("tags") or {}).get("viewpoint") == "from above"
       and int(t1.get("level", -1)) == 2,
       f"{t1.get('level')} / {(t1.get('tags') or {}).get('viewpoint')}")
    # ── v4.5.33（用户 2026-10-30）：坐姿低头看穿丝袜的大腿 ──────────
    # 构图三层：前景自己的胸 / 中景穿丝袜的大腿 / 远景地板。
    # v4.5.35（真机崩坏后修正）：`cowboy shot` 定义是「膝上含头」，与
    # `head out of frame` 自相矛盾 → 闭麦 shot_size；`faceless female` 会让
    # 模型画成「无头躯干」（颈肩失去锚点、躯干塌）→ 去掉，只留 head out of frame。
    ck("坐床沿俯视：坐姿 + cowboy shot（第三人称要含头，不再需要「头出画」）",
       (t1.get("tags") or {}).get("pose_base") == "sitting"
       and (t1.get("tags") or {}).get("shot_size") == "cowboy shot",
       str({k: (t1.get("tags") or {}).get(k) for k in ("pose_base", "shot_size")}))
    ck("坐床沿俯视：画框写明「床沿 + 低头看腿 + 胸 / 大腿 / 地板」",
       all(k in str(t1.get("extra", "")).lower()
           for k in ("sitting on the edge of a bed", "looking down at her own lap",
                     "breasts", "thighs", "floor below")),
       str(t1.get("extra"))[:140])
    ck("俯视自身：不用 faceless female（会画成无头躯干、躯干塌）",
       "faceless female" not in str(t1.get("extra", "")).lower(),
       str(t1.get("extra"))[:100])
    # v4.5.36（用户：不想用椅子）→ 改坐床沿
    ck("俯视自身：坐床沿（不再出现椅子）",
       "sitting on the edge of a bed" in str(t1.get("extra", "")).lower()
       and "chair" not in str(t1.get("extra", "")).lower()
       and "chair" not in str(t1.get("scene_nl", "")).lower(),
       str(t1.get("extra"))[:120])
    ck("坐床沿俯视：正文写「斜上方看 + 床沿 + 大腿丝袜 + 地板」",
       all(k in str(t1.get("scene_nl", "")).lower()
           for k in ("seen from above", "sits on the edge of a bed",
                     "thighs in stockings", "floor shows below")),
       str(t1.get("scene_nl"))[:140])
    ck("俯视自身：闭麦 n_body / bottom / n_shoes_keep（否则会混入肛门 / 纱笼 / 大腿靴）",
       all(k in (t1.get("drop_fields") or [])
           for k in ("n_body", "bottom", "n_shoes_keep")),
       str(t1.get("drop_fields"))[-120:])
    ck("俯视自身：丝袜走候选池（穿丝袜的大腿）",
       len(((t1.get("random_fields") or {}).get("socks")) or []) >= 5,
       str((t1.get("random_fields") or {}).get("socks")))

    # ── v3.38.9（用户 2026-10-24）：「第一人称 · 口交」→「第三人称 · 口交」──
    # 报障：场景库里的口交条目是第一人称（pov, fellatio），且姿势完全没写，
    # 出图时会看到"自己视角 + 自己的身体"，与场景搭配（第三人称）语义不符。
    t2 = next((x for x in scenes if x["id"] == "sc_ccc_pov_oral"), {})
    ck("改名：sc_ccc_pov_oral 现在叫「第三人称 · 口交」",
       t2.get("zh") == "第三人称 · 口交", str(t2.get("zh")))
    ck("改名：viewpoint 从 pov, fellatio 改成 from side（不含 pov）",
       (t2.get("tags") or {}).get("viewpoint") == "from side"
       and "pov" not in str(t2.get("tags")).lower(),
       str((t2.get("tags") or {}).get("viewpoint")))
    ck("改名：主题从「第一人称」并入「双人正戏」",
       t2.get("theme") == "双人正戏", str(t2.get("theme")))
    ck("姿势合理：她跪、身体前倾、双腿之间、手扶腿",
       (t2.get("tags") or {}).get("pose_base") == "kneeling"
       and (t2.get("tags") or {}).get("pose_risque") == "leaning forward"
       and all(k in str(t2.get("extra")) for k in ("fellatio", "between legs", "hands on thighs")),
       str((t2.get("tags") or {}).get("pose_base")) + " / " + str(t2.get("extra")))
    ck("姿势合理：extra 不再有 first-person view",
       "first-person" not in str(t2.get("extra")).lower(), str(t2.get("extra"))[:80])
    ck("闭麦会破坏第三人称/姿势的字段（device/n_act/n_pos/n_exposure/arms_hands/n_cum）",
       all(k in (t2.get("drop_fields") or [])
           for k in ("device", "n_act", "n_pos", "n_exposure", "arms_hands", "n_cum")),
       str(t2.get("drop_fields")))
    # 引擎级：30 抽 —— 机位恒定、零 pov、零 presenting、人数恒 1girl,1boy,hetero
    _vp, _bad, _cnt = Counter(), [], Counter()
    for _sd in range(30):
        _res = R.draw(level=int(t2.get("level", 3)), seed=_sd, forced={"n_canon": t2["id"]})
        _toks = {x.strip() for x in _res["text"].split(",")}
        _vp[_res["state"].get("viewpoint") or ""] += 1
        _cnt[_res["state"].get("count") or ""] += 1
        if {"pov", "presenting", "first-person view"} & _toks:
            _bad.append(_sd)
    ck("第三人称口交：30 抽机位恒 from side、零 pov / presenting",
       set(_vp) == {"from side"} and not _bad, f"{dict(_vp)} / bad={_bad[:3]}")
    ck("第三人称口交：30 抽人数恒 1girl, 1boy, hetero",
       set(_cnt) == {"1girl, 1boy, hetero"}, str(dict(_cnt)))

    # ── v3.39.0（用户 2026-10-24）：新增「远景」主题 12 条 ──
    # 报障：全库 218 条里只有 1 条 wide shot（占 0.5%），近景/特写合计 50%，
    # 远景是完全空白的一档。12 条全 SFW / L0，写法 = wide shot + scenery +
    # landscape/negative space + 大场景 place + distant figure（竖屏下能压到最小）。
    wide = [x for x in scenes if x["id"].startswith("sc_wide_")]
    # v3.39.1：再补 4 条「回眸」→ 12 + 4 = 16
    ck("新增远景 16 条（12 常规 + 4 回眸）", len(wide) == 16, str(len(wide)))
    ck("远景全部在 sfw 组 + 主题为「远景」",
       all(x["group"] == "sfw" and x.get("theme") == "远景" for x in wide),
       str([(x["id"], x["group"], x.get("theme")) for x in wide]))
    ck("远景全部 L0（只做安全内容）", all(int(x["level"]) == 0 for x in wide),
       str([(x["id"], x["level"]) for x in wide]))
    ck("远景全部写死 wide shot",
       all((x.get("tags") or {}).get("shot_size") == "wide shot" for x in wide),
       str([(x["id"], (x.get("tags") or {}).get("shot_size")) for x in wide]))
    ck("远景全部钉 1girl, solo（多人会稀释'人在远处'的效果）",
       all(x.get("count_lock") == "1girl, solo" for x in wide),
       str([(x["id"], x.get("count_lock")) for x in wide]))
    # dof 一律闭麦（`focus on face` 与远景互斥）；action 只对非回眸条目闭麦 ——
    # 回眸那 4 条把 `action=looking back` 写死在 tags 里，再闭麦就自相矛盾了
    ck("远景全部闭麦 dof（focus on face 与远景互斥）",
       all("dof" in (x.get("drop_fields") or []) for x in wide),
       str([(x["id"], x.get("drop_fields")) for x in wide]))
    ck("非回眸条目闭麦 action（否则会抽到喝水/吃东西）",
       all("action" in (x.get("drop_fields") or [])
           for x in wide if not x["id"].endswith("_lookback")),
       str([(x["id"], x.get("drop_fields")) for x in wide if "action" not in (x.get("drop_fields") or [])]))
    # ⚠️ v4.4.4：`distant figure` 删除，改留 `small figure`。
    #    "distant figure" 字面就是**另一个远处的人**，与 `reflection` 一起
    #    会让画面多画一个人（实测「湖畔晨雾」左边水面上站了个陌生人影，
    #    见 10-30 的 nl_fix_b/c/d 三次同 seed 对照）。
    #    `small figure` 只描述"她在画面里很小"，不引入第二个主体。
    ck("远景 extra 都带 scenery + small figure",
       all("scenery" in str(x.get("extra")) and "small figure" in str(x.get("extra"))
           for x in wide),
       str([x["id"] for x in wide if "small figure" not in str(x.get("extra"))]))
    ck("远景 extra 不再有 distant figure / reflection（会画出第二个人）",
       not any("distant figure" in str(x.get("extra"))
               or "reflection" in str(x.get("extra")).lower() for x in wide),
       str([x["id"] for x in wide
            if "distant figure" in str(x.get("extra"))
            or "reflection" in str(x.get("extra")).lower()]))
    ck("远景覆盖 16 个不同 place（不重复取景地）",
       len({(x.get("tags") or {}).get("place") for x in wide}) == 16,
       str(sorted({(x.get("tags") or {}).get("place") for x in wide})))
    # 回眸 4 条：走 action=looking back + eye_gaze=looking back + from behind，
    # 三个字段一起写才稳定（只写 action 时模型经常只转肩不回头）
    _lb = [x for x in wide if x["id"].endswith("_lookback")]
    ck("远景里有 4 条回眸", len(_lb) == 4, str(len(_lb)))
    ck("回眸条目三个字段齐全（from behind / looking back / looking back）",
       all((x.get("tags") or {}).get("viewpoint") == "from behind"
           and (x.get("tags") or {}).get("action") == "looking back"
           and (x.get("tags") or {}).get("eye_gaze") == "looking back" for x in _lb),
       str([(x["id"], (x.get("tags") or {}).get("action")) for x in _lb]))
    ck("回眸条目 extra 写 looking back over shoulder（动作落点）",
       all("looking back over shoulder" in str(x.get("extra")) for x in _lb),
       str([x["id"] for x in _lb]))
    # 引擎级：每条各抽 1 次，景别必须真是 wide shot
    _wrong = []
    for x in wide:
        _st = R.draw(level=0, seed=7, forced={"n_canon": x["id"]})["state"]
        if _st.get("shot_size") != "wide shot":
            _wrong.append((x["id"], _st.get("shot_size")))
    ck("远景 16 条实抽景别恒 wide shot", not _wrong, str(_wrong))

    # ── v3.39.2（用户 2026-10-24）：雪原条目改成"冬季叠穿" ──
    # 报障：雪原里人物穿短裤/薄袜/凉鞋，与季节完全不符（outfit 随机抽到泳装也不奇怪）。
    _snow = next((x for x in wide if x["id"] == "sc_wide_snow_field"), {})
    _st = _snow.get("tags") or {}
    ck("雪原写死长裙 + 连裤袜 + 长靴 + 围巾 + 针织",
       _st.get("bottom") == "long skirt" and _st.get("socks") == "pantyhose"
       and _st.get("shoes") == "knee boots" and _st.get("accessory") == "scarf"
       and _st.get("cloth_mat") == "knitwear", str(_st))
    _WINTER_TOPS = {"coat", "down jacket", "fur-trimmed coat", "fur coat", "fur collar"}
    ck("雪原外套只在冬装池里抽（5 种：大衣/羽绒/毛边/毛皮/毛领）",
       set((_snow.get("random_fields") or {}).get("top") or []) == _WINTER_TOPS,
       str((_snow.get("random_fields") or {}).get("top")))
    ck("雪原闭麦 outfit（整身套装会和上面的冬装打架）",
       "outfit" in (_snow.get("drop_fields") or []), str(_snow.get("drop_fields")))
    ck("雪原 extra 写明 winter clothes / layered / long coat / maxi skirt",
       all(k in str(_snow.get("extra")) for k in ("winter clothes", "layered clothes",
                                                  "long coat", "maxi skirt")),
       str(_snow.get("extra"))[:110])
    # 引擎级：20 抽 —— 外套必须在冬装池内、下装恒长裙、且不出现夏装/泳装
    _SUMMER = {"bikini", "one-piece swimsuit", "shorts", "short shorts", "denim shorts",
               "sandals", "bare feet", "miniskirt", "tank top", "sleeveless shirt",
               "tube top", "camisole", "sundress", "high heels"}
    _bad_top, _bad_bot, _bad_summer = [], [], []
    for _sd in range(20):
        _r = R.draw(level=0, seed=_sd, forced={"n_canon": "sc_wide_snow_field"})
        if _r["state"].get("top") not in _WINTER_TOPS:
            _bad_top.append((_sd, _r["state"].get("top")))
        if _r["state"].get("bottom") != "long skirt":
            _bad_bot.append((_sd, _r["state"].get("bottom")))
        _toks = {x.strip() for x in _r["text"].split(",")}
        if _SUMMER & _toks:
            _bad_summer.append((_sd, sorted(_SUMMER & _toks)))
    ck("雪原 20 抽外套恒在冬装池", not _bad_top, str(_bad_top[:3]))
    ck("雪原 20 抽下装恒 long skirt", not _bad_bot, str(_bad_bot[:3]))
    ck("雪原 20 抽不出现夏装/泳装/光腿类标签", not _bad_summer, str(_bad_summer[:3]))
    # v3.33.0（用户口径：「增加更多姿势，不再固定为躺姿」）：
    # 姿势从"锁死 on back"放开成 5 选 1 —— 但**只放实测能出第一人称的那几种**。
    # 站 / 坐直 / 跪 三种实测都会变成「从上方俯拍她」（站着那张还会把整张脸带进来），
    # 所以池子里只有仰躺 / 侧躺 / 坐起 / 屈膝 / 盘腿。
    # v4.5.33：用户改成「坐姿低头看大腿」→ 姿势从随机池收回、写死 sitting。
    ck("俯视自身：姿势写死坐姿（sitting），不再随机",
       (t1.get("tags") or {}).get("pose_base") == "sitting"
       and "pose_base" not in (t1.get("random_fields") or {}),
       str({k: (t1.get("tags") or {}).get(k) for k in ("pose_base",)}))
    ck("新增：闭麦 n_cum / n_act（单人无第二人，且与明确自慰分层）",
       all(k in (t1.get("drop_fields") or []) for k in ("n_cum", "n_act")),
       str(t1.get("drop_fields")))
    # ⚠️ v3.32.1：`first-person view` 会把画面变成「手机第一人称拍摄」——
    #    实测这个模型必然补上 HDR / 对焦框 / 录像按钮 / 日文菜单，
    #    正向换 8 种措辞（pov / from above / close-up / 双手空着 / 插画风 /
    #    提高 cfg / 加 UI 负词）全部无效。第一人称语义交给 `pov crotch`
    #    + `looking down along own body` + `foreshortening` 就够。
    ck("俯视自身：正文不写 first-person view（它会带出相机 UI）",
       "first-person view" not in str(t1.get("extra", "")).lower(),
       str(t1.get("extra"))[:100])
    # ⚠️ `traditional media` 是实测唯一能压住相机 UI 的词：它把画面拉回"画出来的"
    #    而不是"拍出来的"。但**光有它还不够** —— 手部动作进来之后 UI 又回到约 1/4，
    #    要再加 `painted style`（不是 `painting`：那个会把"墙上的画"真的画出来，
    #    而且画里常是裸女像；`painted texture` 会变厚涂、`canvas texture` 无效、
    #    `comic, manga panel` 会直接出三格分镜）。
    ck("俯视自身：带 traditional media + painted style（压掉相机 UI 的有效组合）",
       "traditional media" in str(t1.get("extra", "")).lower()
       and "painted style" in str(t1.get("extra", "")).lower(),
       str(t1.get("extra"))[-60:])
    ck("俯视自身：不用 painting（它会把墙上的画真的画出来）",
       "painting" not in str(t1.get("extra", "")).lower(),
       str(t1.get("extra"))[-60:])

    # v3.33.0（用户口径：「手部增加更多动作例如按摩胸部、抚摸生殖器等」）：
    # `arms_hands` 字段的 20 个选项里根本没有这类动作（全是叉腰 / 比耶 / 敬礼），
    # 所以走 `random_variants` 的自由短语池 —— 与姿势字段正交，各自独立抽。
    _rv = t1.get("random_variants") or {}
    _hand = (_rv.get("hand") or {}).get("items") or []
    _hand_ex = [str(x.get("extra", "")).lower() for x in _hand]
    # v4.5.33：用户口径「改为手搭在大腿上」——自抚类全部撤掉。
    ck("俯视自身：手部动作池 2 条（双手 / 单手搭在大腿上）",
       len(_hand) == 2, str(len(_hand)))
    ck("俯视自身：手部动作是「搭在大腿上」，不含自抚",
       all("resting on her thigh" in x for x in _hand_ex)
       and not any(w in " ".join(_hand_ex)
                   for w in ("pussy", "breast", "nipple")),
       str(_hand_ex))
    # v3.33.0（用户追加口径「优先保证是人物自身视角」）：
    # **双手同时在胸上**会被画成「对面有个人在揉她」（实测 f_8 / g1 / h4 全部跑成第三人称正面），
    # 所以手部池一律单手或手指动作。
    ck("俯视自身：手部动作不含「碰胸/碰下身」（会变成对面视角或自抚）",
       not any(w in " ".join(_hand_ex) for w in ("breast", "pussy", "nipple")),
       str(_hand_ex))
    ck("俯视自身：`arms_hands` 仍然闭麦（两套手部指令会打架）",
       "arms_hands" in (t1.get("drop_fields") or []), str(t1.get("drop_fields")))

    # ── v3.32.0：第一人称 · 俯视自身 = **代入本体视角**，正文不得有面部特征 ──
    # 用户口径（2026-10-23）：「视角是代入人物视角，提示词内应该没有人物面部特征，
    # 然后以自己视角看自己身体才对。」所以这条要钉的不是"字段长什么样"，而是
    # **抽 40 次正文里一个面部/头发标签都不许出现**，且不许冒出角色名
    # （角色 tag 会把镜头从"自己的身体"拉回一张脸）。
    FACE_FIELDS = ["eyes_color", "emotion", "eye_gaze", "mouth", "makeup",
                   "hair_len", "hair_color", "hair_curl", "hair_tie",
                   "hair_bangs", "hair_fx", "hair_acc"]
    ck("俯视自身：闭麦全部面部 / 头发字段",
       all(k in (t1.get("drop_fields") or []) for k in FACE_FIELDS),
       str([k for k in FACE_FIELDS if k not in (t1.get("drop_fields") or [])]))
    ck("俯视自身：tags 里不再写眼神（eye_gaze=looking down 本身就是面部）",
       "eye_gaze" not in (t1.get("tags") or {}),
       str((t1.get("tags") or {}).get("eye_gaze")))
    # v4.5.37：改成第三人称后，画框里本来就该有人 —— 撤掉 no_role
    ck("坐床沿俯视：不再声明 no_role（第三人称需要角色）",
       t1.get("no_role") is not True, str(t1.get("no_role")))
    _bad = set()
    for _k in FACE_FIELDS:
        for _zh, _en in (R.field_by_key(_k)[1].get("opts") or []):
            _bad.add(_en.lower())
    _leak, _roles = [], []
    for sd in range(40):
        rr = R.draw(level="explicit", seed=6800 + sd, weights=R.empty_weights(),
                    base_prob=0.9, forced={"n_canon": "sc_ccc_pov_self_body"})
        _toks = [x.strip().lower() for x in rr["text"].split(",")]
        _hit = [x for x in _toks if x in _bad]
        if _hit:
            _leak.append((sd, _hit))
        if rr["state"].get("role"):
            _roles.append((sd, rr["state"]["role"]))
    # v4.5.37：第三人称 —— 面部/头发标签与角色名**应当**正常出现（不再屏蔽）
    ck("坐床沿俯视：40 抽里角色名正常出现（第三人称有角色）",
       len(_roles) >= 32, f"role={len(_roles)}/40")
    ck("坐床沿俯视：40 抽里头发/面部标签正常出现（不再屏蔽）",
       len(_leak) >= 32, f"face={len(_leak)}/40")
    # ── v3.30.0：镜前检视 —— 手部固定为「双手掰开展示」─────────────
    mc = next((x for x in scenes if x["id"] == "sc_msb_mirror_check"), {})
    mct = mc.get("tags") or {}
    ck("镜前检视：不再把 arms_hands 钉在「手在头发里」",
       "arms_hands" not in mct, str(mct.get("arms_hands")))
    ck("镜前检视：闭麦 arms_hands / n_act / n_cum（手部与单人向）",
       all(k in (mc.get("drop_fields") or []) for k in ("arms_hands", "n_act", "n_cum")),
       str(mc.get("drop_fields")))
    ck("镜前检视：extra 写死双手掰开",
       all(k in str(mc.get("extra", "")).lower()
           for k in ("spread pussy", "two hands spreading", "both hands between her legs")),
       str(mc.get("extra"))[:90])
    ck("镜前检视：`legs apart` 换成 n_pos 的 `spread legs`（原来那个属 pose_base，会打架）",
       mct.get("n_pos") == "spread legs" and "legs apart" not in str(mc.get("extra", "")),
       f"{mct.get('n_pos')} / {str(mc.get('extra'))[:60]}")
    ck("镜前检视：姿势只剩坐 / 跪 / 正座",
       (mc.get("random_fields") or {}).get("pose_base") == ["sitting", "kneeling", "seiza"],
       str((mc.get("random_fields") or {}).get("pose_base")))
    mc_ok, mc_bad, mc_pose = 0, [], set()
    for sd in range(20):
        w20 = R.empty_weights()
        w20["fields"]["n_canon"] = 3.0
        ids20 = [en for _z, en in R.field_by_key("n_canon")[1]["opts"]] + \
                [x for _z, x, _n in R.scene_options(99, True)]
        bag20 = {k: 0.0 for k in ids20}; bag20["sc_msb_mirror_check"] = 3.0
        w20["options"]["n_canon"] = bag20
        rr = R.draw(level="explicit", seed=6700 + sd, weights=w20, base_prob=0.9)
        t = rr["text"].lower()
        mc_pose.add(rr["state"].get("pose_base") or "")
        if "spread pussy" in t and "two hands spreading" in t:
            mc_ok += 1
        mc_bad += [(sd, b) for b in ("anilingus", "cum string", "creampie", "handjob")
                   if b in t]
    ck("镜前检视：20 抽全部带「双手掰开」", mc_ok == 20, f"{mc_ok}/20")
    ck("镜前检视：20 抽零双人向词（单人场景）", not mc_bad, str(mc_bad[:3]))
    ck("镜前检视：姿态只在坐 / 跪 / 正座之内",
       mc_pose <= {"sitting", "kneeling", "seiza"}, str(sorted(mc_pose)))

    # ── v3.33.0：束缚 · 口球垂涎 —— 画面里只能有她一个人 ────────────────
    # 用户口径（2026-10-23）：「继续更新束缚 · 口球垂涎场景保证画面只有一人。」
    # 原来这条挂的是 `1girl, 1boy, hetero`，且 `n_act` / `n_pos` / `n_orgasm` 照抽 ——
    # 实测正文里会出现 `cum on breasts` / `mating press` / `against wall, sex` / `after sex`，
    # 模型一定画第二个人。改成单人自缚后要钉住四件事：
    # ① 人数钉死 `1girl, solo`；② 双人向字段全部闭麦；
    # ③ 机位不许走 `pov` 系（`pov, cowgirl position` 这类会直接带出第二个人）；
    # ④ 眼神不许 `looking at another`。
    g = next((x for x in scenes if x["id"] == "sc_ccc_bdsm_gag"), {})
    ck("口球：人数钉死 1girl, solo（原来是 1girl, 1boy, hetero）",
       g.get("count_lock") == "1girl, solo", str(g.get("count_lock")))
    ck("口球：闭麦双人向字段 n_act / n_cum / n_pos / n_orgasm",
       all(k in (g.get("drop_fields") or []) for k in ("n_act", "n_cum", "n_pos", "n_orgasm")),
       str([k for k in ("n_act", "n_cum", "n_pos", "n_orgasm")
            if k not in (g.get("drop_fields") or [])]))
    ck("口球：机位只在单人机位里选（不含 pov 系）",
       all("pov" not in v for v in ((g.get("random_fields") or {}).get("viewpoint") or ["x"])),
       str((g.get("random_fields") or {}).get("viewpoint")))
    ck("口球：眼神不含 looking at another",
       "looking at another" not in ((g.get("random_fields") or {}).get("eye_gaze") or []),
       str((g.get("random_fields") or {}).get("eye_gaze")))
    _gbad = []
    for sd in range(40):
        rr = R.draw(level="hardcore", seed=6900 + sd, weights=R.empty_weights(),
                    base_prob=0.9, forced={"n_canon": "sc_ccc_bdsm_gag"})
        _t = rr["text"].lower()
        _h = [w for w in ("1boy", "hetero", "penis", "cum", "fellatio", "handjob",
                          "mating", "boy", "another", "pov") if w in _t]
        if _h:
            _gbad.append((sd, _h))
    ck("口球：40 抽零双人词 / 零 pov 机位", not _gbad, str(_gbad[:3]))

    # ── v3.34.0：异种 · 触手 —— 束缚感 + 高潮表情 + 触手入口（概率）──────
    # 用户口径（2026-10-23）：「使人物状态更有被束缚感等符合场景的表情与状态，
    # 并且有概率使触手插入口部。」随后追加：「口球不要加入到提示词内了。」
    # ⚠️ 最后这条是关键教训：`tentacle gag` 会被画成一根触手**横穿嘴巴**（就是口球的样子），
    #    要"伸进嘴里"反而得用 `tentacle in her mouth, oral, deepthroat`（实测才会含着）。
    tt = next((x for x in scenes if x["id"] == "sc_ccc_tentacle"), {})
    _trv = tt.get("random_variants") or {}
    _bind = (_trv.get("bind") or {}).get("items") or []
    _mouth = (_trv.get("mouth") or {}).get("items") or []
    ck("触手：束缚方式 3 选 1（双手吊起 / 手臂反绑 / 缠满全身）",
       len(_bind) == 3, str([i.get("zh") for i in _bind]))
    ck("触手：口部 3 选 1（贴脸 / 绕颈 / 入口，约 1/3 概率）",
       len(_mouth) == 3, str([i.get("zh") for i in _mouth]))
    ck("触手：口部池里一定有一条「触手入口」",
       any("in her mouth" in str(i.get("extra", "")).lower() for i in _mouth),
       str([i.get("extra") for i in _mouth]))
    # ⚠️ 用户明确「口球不要加入到提示词内」—— 正文与变体里都不许出现 gag 类词。
    ck("触手：全程不出现 gag 类词（会被画成口球）",
       "gag" not in str(tt.get("extra", "")).lower()
       and not any("gag" in str(i.get("extra", "")).lower() for i in _mouth),
       str([i.get("extra") for i in _mouth]))
    ck("触手：高潮状态改成随机（不再写死 body writhe）",
       set(((tt.get("random_fields") or {}).get("n_orgasm") or []))
       == {"body writhe", "orgasm, trembling", "ahegao, rolled back eyes",
           "mind break", "moaning", "aroused"},
       str((tt.get("random_fields") or {}).get("n_orgasm")))
    ck("触手：表情限定在失控 / 受惊一侧（不含 embarrassed 那种从容）",
       set(((tt.get("random_fields") or {}).get("emotion") or []))
       == {"tears", "crying", "scared", "surprised"},
       str((tt.get("random_fields") or {}).get("emotion")))
    _tbad = []
    for sd in range(30):
        rr = R.draw(level="hardcore", seed=6950 + sd, weights=R.empty_weights(),
                    base_prob=0.9, forced={"n_canon": "sc_ccc_tentacle"})
        _t = rr["text"].lower()
        _h = [w for w in ("1boy", "hetero", "gag", "fellatio", "handjob") if w in _t]
        if _h:
            _tbad.append((sd, _h))
    ck("触手：30 抽零双人词 / 零 gag 词", not _tbad, str(_tbad[:3]))

    # ── v3.34.0：事后 · 余韵 —— 画面里只有她一个人 ────────────────────
    # 用户口径（2026-10-23）：「顺便更新事后 · 余韵场景，保证只有一人出现在画面中。」
    # 原来挂的是 `1girl, 1boy, hetero`；另外两个隐藏入口：`viewpoint` 的
    # `pov, cowgirl position` 与 `eye_gaze` 的 `looking at another`。
    ag = next((x for x in scenes if x["id"] == "sc_ccc_afterglow"), {})
    _agrf = ag.get("random_fields") or {}
    ck("余韵：人数钉死 1girl, solo（原来是 1girl, 1boy, hetero）",
       ag.get("count_lock") == "1girl, solo", str(ag.get("count_lock")))
    ck("余韵：闭麦双人向字段 n_act / n_pos / pose_risque",
       all(k in (ag.get("drop_fields") or []) for k in ("n_act", "n_pos", "pose_risque")),
       str(ag.get("drop_fields")))
    ck("余韵：机位限定单人机位（不含 pov 系）",
       all("pov" not in v for v in (_agrf.get("viewpoint") or ["x"])),
       str(_agrf.get("viewpoint")))
    ck("余韵：眼神不含 looking at another",
       "looking at another" not in (_agrf.get("eye_gaze") or []),
       str(_agrf.get("eye_gaze")))
    # v3.34.1（用户口径：「保证能够出现中景画面的各种姿势全身照」）：
    # 景别从"只拍脸"放开到 **cowboy shot / full body**，姿势 6 选 1；
    # 同时 `dof` 必须离开 `focus on face` —— 焦点钉在脸上会把镜头一路拉回特写，
    # 全身照根本不成立（实测就是这么失败的）。
    ck("余韵：景别只在中景/全身里选（cowboy shot / full body）",
       set(_agrf.get("shot_size") or []) == {"cowboy shot", "full body"},
       str(_agrf.get("shot_size")))
    ck("余韵：姿势 6 选 1（侧躺/仰躺/俯卧/坐起/蜷缩/屈膝）",
       set(_agrf.get("pose_base") or [])
       == {"on side", "on back", "on stomach", "sitting", "fetal position", "knees up"},
       str(_agrf.get("pose_base")))
    ck("余韵：dof 不再钉 focus on face（它会把镜头拉回脸）",
       "focus on face" not in (_agrf.get("dof") or [])
       and "dof" not in (ag.get("tags") or {}),
       f"{_agrf.get('dof')} / {(ag.get('tags') or {}).get('dof')}")
    ck("余韵：机位去掉 from behind（事后余韵要看得见表情）",
       "from behind" not in (_agrf.get("viewpoint") or []),
       str(_agrf.get("viewpoint")))
    _abad, _empty_shot, _poses = [], 0, set()
    for sd in range(60):
        rr = R.draw(level="hardcore", seed=6980 + sd, weights=R.empty_weights(),
                    base_prob=0.9, forced={"n_canon": "sc_ccc_afterglow"})
        _t = rr["text"].lower()
        _toks = {x.strip().lower() for x in _t.split(",")}
        _h = [w for w in ("1boy", "hetero", "penis", "cum in", "another", "pov") if w in _t]
        if _h:
            _abad.append((sd, _h))
        if not rr["state"].get("shot_size"):
            _empty_shot += 1
        _poses.add(rr["state"].get("pose_base"))
    ck("余韵：60 抽零双人词 / 零 pov", not _abad, str(_abad[:3]))
    # ⚠️ v3.34.1 引擎修复的回归断言：`trim_to_cap` 以前只保护 `canon()` 里的
    #    tags 字段，**不含 random_fields** —— 密度超限时「景别·全身」会被当软字段削掉，
    #    正文里只剩 `depth of field` 没有 `full body`，用户看到的是"选了全身照却出特写"。
    #    现在 `_preset_fields` 也进了 protected，60 抽必须一个空景别都没有。
    ck("余韵：60 抽景别一次都没被密度裁剪削掉", _empty_shot == 0, f"{_empty_shot}/60")
    ck("余韵：60 抽覆盖到全部 6 种姿势",
       _poses == {"on side", "on back", "on stomach", "sitting", "fetal position", "knees up"},
       str(sorted(x for x in _poses if x)))

    # ── v3.35.0：隐奸 · 被子下 —— 改成第一人称「她顶着被子坐在我身上」──
    # 用户口径（2026-10-23）：「改为第一人称她顶着被子坐我身上。」
    # 原来的组合是第三人称侧面（`from side` + `on side` + `sex from behind`），
    # 画面里根本不像"我在下面"。改成 POV 骑乘后要钉住四件事：
    # ① 机位与体位都是 `cowgirl position`，且视角是 `pov`（镜头=躺着的男方）；
    # ② 被子必须是**罩在她头上、撑成帐篷**（`blanket draped over her head` +
    #    `tented blanket`），不是"盖住全身"（盖住就什么都看不见了）；
    # ③ 男方只露身体不露脸（`faceless male`），否则会变成双人对话构图；
    # ④ 闭麦 `device` —— POV 场景抽到 `webcam footage` / `polaroid frame` 会带出手机 UI 和画框。
    hs = next((x for x in scenes if x["id"] == "sc_ccc_hidden_sex"), {})
    _hst = hs.get("tags") or {}
    ck("隐奸：机位改成第一人称骑乘（pov, cowgirl position）",
       _hst.get("viewpoint") == "pov, cowgirl position", str(_hst.get("viewpoint")))
    ck("隐奸：体位是 cowgirl position + 跪跨",
       _hst.get("n_act") == "cowgirl position" and _hst.get("pose_base") == "kneeling",
       f"{_hst.get('n_act')} / {_hst.get('pose_base')}")
    # v3.35.1（用户口径：「被子不要遮挡胸部，并且生殖器清晰可见」）：
    # 被子从"罩头 + 帐篷盖身"收成**只当兜帽**（挂在肩后），胸与私处都留在外面。
    # 光写 `blanket draped over her head` 不够 —— 模型会把被子顺手画成披肩盖住胸，
    # 必须再补一句 `blanket hanging behind her shoulders` 把被子"推"到背后。
    # 私处同理：骑乘位天然被身体挡住，要 `leaning back`（后仰把胯推到镜头前）
    # + `pussy visible` + `clitoris` + `spread pussy lips` 才真的看得清，
    # 只写 `pussy visible` 时实测还只是"隐约可见"。
    ck("隐奸：被子只当兜帽（罩头 + 挂在肩后，不挡胸）",
       all(k in str(hs.get("extra", "")).lower()
           for k in ("blanket draped over her head like a hood",
                     "blanket hanging behind her shoulders")),
       str(hs.get("extra"))[:140])
    # v3.36.0（用户口径：「增加乳夹，生殖器插入」）：
    # 乳夹走 `n_theme = nipple clamps`（词库里唯一带"夹"的主题），
    # 链条细节写进 extra 的两句（`nipple clamps with chain` + `chain between nipple clamps`），
    # 只写 `nipple clamps` 时模型会把夹子画成"贴纸"、没有链子连接。
    # 插入则要把上一版"外阴展示"那组词换掉 —— `spread pussy lips` / `clitoris` / `implied sex`
    # 都是"未插入 + 只做暗示"的语义，与"正在插入"直接打架，留着会让模型二选一。
    ck("隐奸：乳夹（n_theme = nipple clamps + 链子描述）",
       (hs.get("tags") or {}).get("n_theme") == "nipple clamps"
       and "nipple clamps with chain" in str(hs.get("extra", "")).lower()
       and "chain between nipple clamps" in str(hs.get("extra", "")).lower(),
       f"{(hs.get('tags') or {}).get('n_theme')} / {str(hs.get('extra'))[-100:]}")
    ck("隐奸：胸点名可见（bare breasts + nipples）",
       all(k in str(hs.get("extra", "")).lower() for k in ("bare breasts", "nipples")),
       str(hs.get("extra"))[:120])
    ck("隐奸：结合处写成插入状态（penetration / deep penetration / stretched）",
       all(k in str(hs.get("extra", "")).lower()
           for k in ("penetration", "deep penetration", "pussy stretched around him")),
       str(hs.get("extra"))[-140:])
    ck("隐奸：去掉与明确插入矛盾的暗示词（implied sex / spread pussy lips）",
       "implied sex" not in str(hs.get("extra", "")).lower()
       and "spread pussy lips" not in str(hs.get("extra", "")).lower(),
       str(hs.get("extra"))[-140:])
    ck("隐奸：后仰把胯推到镜头前（leaning back）",
       "leaning back" in str(hs.get("extra", "")).lower(), str(hs.get("extra"))[:80])
    ck("隐奸：被子不再整块盖住身体（去掉 tented blanket / covering her body）",
       "tented blanket" not in str(hs.get("extra", "")).lower()
       and "covering her body" not in str(hs.get("extra", "")).lower(),
       str(hs.get("extra"))[:140])
    ck("隐奸：男方不露脸（faceless male）",
       "faceless male" in str(hs.get("extra", "")).lower(), str(hs.get("extra"))[-60:])
    ck("隐奸：闭麦 device（POV 抽到 webcam / polaroid 会带相机 UI 与画框）",
       "device" in (hs.get("drop_fields") or []), str(hs.get("drop_fields")))
    _hbad = []
    for sd in range(20):
        rr = R.draw(level="hardcore", seed=6990 + sd, weights=R.empty_weights(),
                    base_prob=0.9, forced={"n_canon": "sc_ccc_hidden_sex"})
        _t = rr["text"].lower()
        _h = [w for w in ("boots", "polaroid", "webcam", "thighhigh", "hakama",
                          "coat", "hands up", "on one knee") if w in _t]
        if _h:
            _hbad.append((sd, _h))
    ck("隐奸：20 抽零杂物（靴子 / 拍立得 / 监控 / 外套 / 单膝跪）",
       not _hbad, str(_hbad[:3]))

    # ── v3.37.0：骑乘位 · 女方在上 —— 赤足 + 结合处插入 ────────────────
    # 用户口径（2026-10-23）：「保证人物不穿鞋，生殖器插入。」
    # ① 不穿鞋：`shoes` 写死 `bare feet`（词库里它就是"赤足"选项），
    #    并把 `socks` 也钉成 `barefoot` —— 否则会抽 `thighhighs`，光脚穿长袜一样矛盾；
    #    闭麦 `n_shoes_keep`（`thigh boots` 是从那里漏进来的，不在 `shoes` 里）。
    # ② 插入：`cowgirl position` 本身只是"骑乘"，不写 `penetration` 时结合处经常被身体挡住，
    #    要 `penetration` + `deep penetration` + `pussy stretched around him` 三句才清楚。
    cw = next((x for x in scenes if x["id"] == "sc_ccc_cowgirl"), {})
    _cwt = cw.get("tags") or {}
    ck("骑乘：鞋子写死赤足（bare feet）+ 袜子 barefoot",
       _cwt.get("shoes") == "bare feet" and _cwt.get("socks") == "barefoot",
       f"{_cwt.get('shoes')} / {_cwt.get('socks')}")
    ck("骑乘：闭麦 n_shoes_keep（thigh boots 从这里漏）",
       "n_shoes_keep" in (cw.get("drop_fields") or []), str(cw.get("drop_fields")))
    ck("骑乘：结合处写成插入状态",
       all(k in str(cw.get("extra", "")).lower()
           for k in ("penetration", "deep penetration", "pussy stretched around him")),
       str(cw.get("extra"))[-110:])
    _cwbad = []
    for sd in range(40):
        rr = R.draw(level="hardcore", seed=6960 + sd, weights=R.empty_weights(),
                    base_prob=0.9, forced={"n_canon": "sc_ccc_cowgirl"})
        # ⚠️ v3.41.2：必须按**标签**逐条比对，并排掉角色/作品名 ——
        #    有角色叫 `stocking`（《Panty & Stocking》），子串匹配会把她当袜子。
        _role = {x.strip().lower() for x in str(rr["state"].get("role") or "").split(",")}
        _t = [x.strip().lower() for x in rr["text"].split(",")
              if x.strip() and x.strip().lower() not in _role]
        _h = [w for w in ("high heels", "boots", "sneakers", "slippers", "loafers",
                          "sandals", "geta", "uwabaki", "mary janes",
                          "thighhigh", "stocking", "pantyhose", "latex", "poncho")
              if any(w in x for x in _t)]
        if _h:
            _cwbad.append((sd, _h))
    ck("骑乘：40 抽零鞋类 / 零袜类 / 零服装残留", not _cwbad, str(_cwbad[:3]))

    # ── v3.31.0：去掉镜子（改名 + 换机位 + 闭麦 prop）─────────────────
    ck("去镜：改名为「自慰 · 侧面检视」", mc.get("zh") == "自慰 · 侧面检视", str(mc.get("zh")))
    ck("去镜：机位不再是镜中倒影（from side）",
       mct.get("viewpoint") == "from side" and "mirror" not in str(mct), str(mct.get("viewpoint")))
    ck("去镜：tags 里没有 prop（mirror 已移除）", "prop" not in mct, str(mct.get("prop")))
    ck("去镜：闭麦 prop（否则随机又把镜子抽回来）", "prop" in (mc.get("drop_fields") or []),
       str(mc.get("drop_fields")))
    ck("去镜：extra 不再含 mirror / reflection",
       not any(k in str(mc.get("extra", "")).lower() for k in ("mirror", "reflection")),
       str(mc.get("extra"))[:80])
    mir = []
    for sd in range(20):
        w20 = R.empty_weights()
        w20["fields"]["n_canon"] = 3.0
        ids20 = [en for _z, en in R.field_by_key("n_canon")[1]["opts"]] + \
                [x for _z, x, _n in R.scene_options(99, True)]
        bag20 = {k: 0.0 for k in ids20}; bag20["sc_msb_mirror_check"] = 3.0
        w20["options"]["n_canon"] = bag20
        t = R.draw(level="explicit", seed=6750 + sd, weights=w20, base_prob=0.9)["text"].lower()
        mir += [(sd, b) for b in ("mirror", "reflection") if b in t]
    ck("去镜：20 抽正文零镜面词", not mir, str(mir[:3]))

    names = [x.get("zh") for x in scenes]
    ck("场景中文名没有重复（改名不会撞名）", len(names) == len(set(names)),
       str([n for n in set(names) if names.count(n) > 1][:3]))
    ck("偷窥场景：5 种机位都能抽到", set(VPS) <= vp_seen, str(sorted(vp_seen)))
    ck("护士查房：20 抽零杂道具（冰淇淋 / 高脚杯 / 蛋糕 / 气球）", not junk, str(junk[:3]))
    # ⚠️ v3.39.0：手部入口从 `arms_hands` 改成 `pose_risque = hair flip`（甩发）。
    #    原来两个都写 = 同一条预设自带两个手部动作（上肢单槽冲突），
    #    而擦边档位是由 `hair flip` 判 L1 撑起来的，所以留它。
    ck("雨中透衫：手部锁在「甩发」（v3.39.0 起只留 pose_risque 一侧）",
       not hand_bad, str(hand_bad[:3]))
    ck("贴地场景 20 抽正文零相机类词", not hit, str(hit[:3]))
    # ⚠️ v4.4.3：`scene_nl` 里一律不许出现「摄影器材」名词。
    #    句子的主语写成 the camera / the lens 时，模型会把机器**画进画面**——
    #    实测「贴地超广角·坐姿长腿」画出一台躺在地上的相机（用户现场发现）。
    #    视角一律改用 "seen from above / below / behind" 这类无人称短语。
    #    （selfie / phone 不在此列：那是场景本体，不是机位描述。）
    GEAR = ("camera", "lens", "dslr", "tripod", "webcam", "photo",
            "footage", "shutter", "viewfinder")
    nl_gear = [(s["id"], g) for s in scenes
               for g in GEAR if g in str(s.get("scene_nl") or "").lower()]
    ck("scene_nl 一律不含摄影器材名词（camera / lens 会被画成实物）",
       not nl_gear, str(nl_gear[:3]))
    # ⚠️ v4.4.4：`scene_nl` 里也不许写「镜中倒影」——
    #    "her reflection faces her from the glass" 会要求画出**第二个人影**，
    #    与 `viewpoint="mirror, reflection"` 同源（两个身子、姿势对不上）。
    #    镜子交给 tags 的 prop=mirror / extra 的 "mirror as backdrop" 就够了。
    nl_mir = [s["id"] for s in scenes
              if any(w in str(s.get("scene_nl") or "").lower()
                     for w in ("reflection", "mirror image", "in the glass"))]
    ck("scene_nl 不写镜中倒影（reflection 会画出第二个身子）",
       not nl_mir, str(nl_mir[:3]))
    ck("套用后 count 等于 count_lock（引擎侧真的钉住了）", not bad_count, str(bad_count[:3]))
    ck("钉人数后 n_act / n_pos / n_theme 不再被多人分支清空",
       not lost_act, str(lost_act[:3]))

    print("── ② 合并层：canon = 法典 + 场景 ──")
    merged = R.canon()
    ck("合并后条数 = 法典 14 + 场景 N",
       len(merged) == 14 + len(scenes), f"{len(merged)} vs {14 + len(scenes)}")
    ck("法典条目原样保留（c8 内容不变）",
       merged.get("c8", {}).get("n_act") == "deepthroat",
       str(merged.get("c8")))
    ck("场景 id 能取到 `{字段: 值}` 形状的预设",
       isinstance(merged.get(lv0[0]), dict) and bool(merged.get(lv0[0])),
       str(merged.get(lv0[0]))[:80])
    ck("场景预设的 n_extra 挂在同一键上（与法典同形状）",
       "n_extra" in (merged.get(lv0[0]) or {}))

    print("── ③ 闸门层：按档位可用性 ──")
    for lv in (0, 2, 3, 4):
        got = {R.canon_level(en) for _zh, en, _n in
               R.eligible_options("n_canon", lv) if en.startswith("sc_")}
        ck(f"L{lv} 的场景候选档位全部 ≤ {lv}", all(g <= lv for g in got),
           str(sorted(got)))
    ck("L0 候选中不含 L2+ 场景",
       not [en for _z, en, _n in R.eligible_options("n_canon", 0)
            if en.startswith("sc_") and R.canon_level(en) > 0])
    # ⚠️ v3.18.0：随机候选池故意排除特写搭配（manual_only），
    #    所以 L4 能拿到的 = 全部场景 − 特写条数；特写要单独断言"一条都不在池子里"。
    manual_n = len([s for s in scenes if s.get("manual_only")])
    ck("高档（L4）能拿到全部**非特写**场景",
       len([en for _z, en, _n in R.eligible_options("n_canon", 4)
            if en.startswith("sc_")]) == len(scenes) - manual_n,
       f"{len(scenes) - manual_n} vs {len(scenes)}-{manual_n}")
    ck("特写搭配一条都不在随机候选池里",
       not [en for _z, en, _n in R.eligible_options("n_canon", 4)
            if R.scene_index().get(en, {}).get("manual_only")])

    # 文本框（n_extra）必须**按标签**判档，不能套 canon 段的段下限（=2）——
    # 否则 SFW 场景自带的附加标签串（`afternoon light, quiet`）会被判成 2 档，
    # 在闸门测试与自检里假报"越档"。
    ck("n_extra 按标签判档（不套段下限）",
       R.field_value_num("n_extra", "afternoon light, quiet") == 0,
       str(R.field_value_num("n_extra", "afternoon light, quiet")))

    # 强制指定超档场景 → F15（档位准入）必须报出来
    hi = [s["id"] for s in scenes if int(s["level"]) >= 4]
    if hi:
        rr = R.draw(level=0, seed=5, forced={"n_canon": hi[0]}, base_prob=0.0)
        ck("强制超档场景 → F15 报越档", "n_canon" in rr["report"]["over_fields"],
           str(rr["report"]["over_fields"]))
    else:
        ck("强制超档场景 → F15 报越档", False, "库里没有 L4 场景，无法验证")

    print("── ④ 应用层：预设真被写进去，且裁不掉（真固定）──")
    sid = "sc_rain_street_lookback" if "sc_rain_street_lookback" in merged \
        else lv0[0]
    # ⚠️ v4.4.4：`scene_nl` 是**元数据键**，不进 state 的普通字段（走 `_scene_nl`），
    #    所以不参与"字段是否写进 state"的比对 —— 它有自己的一条断言。
    want = {k: v for k, v in merged[sid].items()
            if k not in ("n_extra", "scene_nl")}
    res = R.draw(level=0, seed=9, forced={"n_canon": sid}, base_prob=0.0)
    st = res["state"]
    missing = {k: v for k, v in want.items() if st.get(k) != v}
    ck(f"场景「{sid}」的字段全部写入 state", not missing, str(missing))
    ck("n_extra 也写进去了", bool(st.get("n_extra")))
    ck("scene_nl 进 _scene_nl（不当普通字段写 state）",
       st.get("_scene_nl") == merged[sid].get("scene_nl")
       and "scene_nl" not in st,
       str(st.get("_scene_nl"))[:60])

    # trim：把上限压到 16，场景字段必须活下来（这正是"真固定"的判据）
    res2 = R.draw(level=0, seed=9, forced={"n_canon": sid},
                  base_prob=1.0, tag_cap="16")
    st2 = res2["state"]
    lost = [k for k in want if not st2.get(k)]
    ck("标签上限压到 16 后，场景字段一个都没被裁掉", not lost,
       f"被裁：{lost}；dropped={res2['dropped']}")
    ck("被裁的只可能是非预设字段", not (set(res2["dropped"] or []) & set(want)),
       str(res2["dropped"]))

    print("── ⑤ 输出层：id 不进正文 + 可复现 ──")
    ck("预设 id 不出现在正文里",
       sid not in res["text"] and not any(
           t.startswith("sc_") for t in res["tags"]), res["text"][:80])
    ck("法典 id（c8）也不出现在正文里",
       not any((t.startswith("c") and t[1:].isdigit()) for t in res["tags"]))
    a = R.draw(level=0, seed=42, forced={"n_canon": sid})["text"]
    b = R.draw(level=0, seed=42, forced={"n_canon": sid})["text"]
    ck("同 seed 逐字节可复现", a == b)
    ck("L0 场景输出的自检全绿",
       res["report"]["ok_f"] == res["report"]["total_f"],
       str([c["id"] for c in res["report"]["F"] if not c["ok"]]))

    print("── ⑥ 载荷层：面板与引擎同口径 ──")
    nodes = _boot.load("nodes")
    pools = nodes.pools_payload()
    ncanon = None
    for s in pools["sections"]:
        for f in s["fields"]:
            if f["key"] == "n_canon":
                ncanon = f
    ck("/pools 里有 n_canon 字段", ncanon is not None)
    # ⚠️ 面板列出的候选数必须与引擎实际能抽到的同源候选**完全一致**
    #    （历史教训：预演 A、实跑 B）
    panel_ids = [o["en"] for o in (ncanon or {}).get("opts", [])]
    engine_ids = [en for _zh, en, _n in R.eligible_options("n_canon", 4)]
    # ⚠️ v3.18.0 起口径变了：面板要能列出**特写搭配**（manual_only），
    #    而引擎的随机候选池**故意不含**它们（否则随机分布会变）。
    #    所以这里断言的是「面板 = 随机候选 + 特写搭配」，而不是两边全等。
    manual_ids = [sid for _zh, sid, _n in R.manual_scene_options(4)]
    # ⚠️ v3.21.0：改成比较**集合**而不是列表 —— 面板按词库书写顺序列，
    #    引擎按档位/权重排序，两边数量与内容一致就够了，顺序本来就不承诺相同。
    ck("/pools 的 n_canon 候选 == 引擎随机候选 + 特写搭配（L4）",
       len(panel_ids) == len(engine_ids) + len(manual_ids)
       and set(panel_ids) == set(engine_ids + manual_ids),
       f"{len(panel_ids)} vs {len(engine_ids)}+{len(manual_ids)}")
    ck("面板候选带上了场景条目",
       sum(1 for i in panel_ids if i.startswith("sc_")) == len(scenes))

    sc_payload = nodes.scenes_payload()
    ck("/scenes 载荷含全部分组与场景",
       sc_payload["counters"]["scenes"] == len(scenes)
       and bool(sc_payload["groups"]), str(sc_payload["counters"]))
    # v3.10.0：一级分组是 **NSFW 档位**（L0–L4），不是 sfw/nsfw
    ck("载荷带五个档位分组", len(sc_payload["level_groups"]) == 5,
       str([g["title"] for g in sc_payload["level_groups"]]))
    ck("五个档位分组的条数之和 == 场景总数",
       sum(g["count"] for g in sc_payload["level_groups"]) == len(scenes),
       str([(g["title"], g["count"]) for g in sc_payload["level_groups"]]))
    ck("每一档都有场景（分类展示不留空组）",
       all(g["count"] > 0 for g in sc_payload["level_groups"]),
       str([(g["title"], g["count"]) for g in sc_payload["level_groups"]]))
    ck("每条场景都带题材标签（面板卡片要显示）",
       all(s.get("theme") for s in sc_payload["scenes"]),
       str([s["id"] for s in sc_payload["scenes"] if not s.get("theme")][:3]))
    ck("库规模已扩到 60 条以上", len(scenes) >= 60, str(len(scenes)))
    no_lab = [f for sc in sc_payload["scenes"] for f in sc["fields"]
              if not f.get("lab") or f.get("lab") == f.get("field")]
    ck("每个字段都带中文标签（面板直接渲染）", not no_lab, str(no_lab[:3]))

    print("── ⑦ 挖矿类主题（原「自慰」，v3.11.0；v4.0.0 题材改名）──")
    msb = [s for s in scenes if s.get("theme") == "挖矿"]
    ck("存在「挖矿」题材预设", len(msb) >= 20, f"{len(msb)} 条")
    lvset = {int(s["level"]) for s in msb}
    ck("挖矿类覆盖 L2 / L3 / L4 三档（按 NSFW 等级分类）",
       {2, 3, 4} <= lvset, str(sorted(lvset)))
    ck("挖矿类全部 ≥ L2（L1 擦边档拿得到是漏洞）",
       all(int(s["level"]) >= 2 for s in msb))
    ck("用户示例①「拉开内裤展示」在库里",
       any(s["id"] == "sc_msb_panties_aside" for s in msb))
    ck("用户示例②「假阳具」在库里",
       any("dildo" in str(s.get("tags", {}).get("n_theme", ""))
           or s.get("tags", {}).get("n_act") == "dildo riding" for s in msb))
    # ⚠️ 自慰是单人行为，但预设**不能写 count/role** —— 所以"单人"靠 extra 里的
    #    `solo` 标签表达：人数抽到单人时与 count 的 solo 去重，抽到多人时
    #    repair 的"数量互斥"会把它去掉（优雅降级，不崩不越档）。
    solo_ok = [s for s in msb if "solo" in (s.get("extra") or "")]
    ck("挖矿类预设用 extra 里的 solo 表达单人", len(solo_ok) >= len(msb) - 1,
       f"{len(solo_ok)}/{len(msb)} 含 solo")
    ck("双人互慰**不**写 solo（它本来就是两个人）",
       "solo" not in (next(s for s in msb
                          if s["id"] == "sc_msb_mutual")["extra"]))
    # 闸门：自慰类在 L2 档只放 L2 的、L3 档不放 L4 的
    ids_l2 = {en for _z, en, _n in R.eligible_options("n_canon", 2)
              if en.startswith("sc_msb_")}
    ck("L2 档只拿到 L2 的挖矿场景",
       ids_l2 == {s["id"] for s in msb if int(s["level"]) == 2},
       f"{len(ids_l2)} 条")
    ids_l3 = {en for _z, en, _n in R.eligible_options("n_canon", 3)
              if en.startswith("sc_msb_")}
    ck("L3 档拿不到 L4 的挖矿场景（潮吹）",
       not (ids_l3 & {s["id"] for s in msb if int(s["level"]) == 4}),
       str(sorted(ids_l3 & {s["id"] for s in msb if int(s["level"]) == 4})))

    print("── ⑧ 擦边组扩充（v3.17.1：3 → 28；v3.17.2 镜头模板：→ 38）──")
    # 只统计**场景搭配**的擦边组：特写搭配里也有 1 条 L1（泪光），
    # 它不属于这一组，混进来会让"全部落在 sfw 组"的断言失真。
    l1 = [s for s in scenes if int(s.get("level", -1)) == 1 and not s.get("manual_only")]
    ck("擦边组 ≥ 38 条", len(l1) >= 38, f"{len(l1)} 条")
    # v3.21.0：姿势场景（group=pose）也是 SFW 内容，L1 的「四肢着地」就在这里，
    # 不放行它会让这条断言把"新分组"当成"分组错误"。
    ck("擦边条目全部落在 sfw / pose 组（面板分组正确）",
       all(s["group"] in ("sfw", "pose") for s in l1),
       str(sorted({s["group"] for s in l1})))
    # 派生档位复算（与 build_scenes 同口径）：有标签的档位 ≤1 且至少一条 =1
    # ⚠️ v4.5.0：必须把 `count_lock` 一起传进去 —— 人数锁自 v4.5.0 起参与档位派生，
    #    少传一个参数会让"双女日常互动"（内容全 L0 + 双女锁）复算成 0。
    sys.path.insert(0, os.path.join(PLUGIN, "tools"))
    from build_scenes import scene_level
    bad_lv = [(s["id"], scene_level(s["tags"], s.get("extra", ""),
                                    s.get("random_fields"),
                                    s.get("random_variants"),
                                    s.get("count_lock", "")))
              for s in l1
              if scene_level(s["tags"], s.get("extra", ""),
                             s.get("random_fields"),
                             s.get("random_variants"),
                             s.get("count_lock", "")) != 1]
    ck("擦边条目派生档位全部 = 1（不沉到全年龄、不浮到成人）",
       not bad_lv, str(bad_lv[:4]))
    # 暗示姿势的使用率（v3.14.0 pose_risque 字段进场景配方）
    n_risque = sum(1 for s in l1 if "pose_risque" in s["tags"])
    ck("擦边条目大量使用暗示姿势（pose_risque）", n_risque >= 20,
       f"{n_risque}/{len(l1)} 条")
    # 四大题材方向都有覆盖（新增 25 条的 theme 分布）
    new_ids = {"sc_changing_room_peek", "sc_bedroom_sleepshirt", "sc_bath_towel",
               "sc_balcony_laundry", "sc_rain_wetshirt", "sc_sofa_catnap",
               "sc_konbini_midnight", "sc_kitchen_apron", "sc_skirt_wind",
               "sc_hotel_mirror", "sc_beach_volley", "sc_pool_ladder",
               "sc_surf_board", "sc_float_ring", "sc_shower_peek",
               "sc_watergun_fight", "sc_ol_overtime", "sc_maid_serving",
               "sc_nurse_rounds", "sc_classroom_openwin", "sc_jk_bike_ride",
               "sc_yoga_mat", "sc_gym_mirror", "sc_gymnastics_split",
               "sc_jog_rest"}
    got = {s["id"] for s in scenes} & new_ids
    ck("v3.17.1 新增 25 条全部在库", len(got) == 25,
       f"缺 {sorted(new_ids - got)}")
    # v3.17.2 镜头×姿势模板（10 条，纯镜头不带 place，地点交给随机）
    cam_ids = {"sc_cam_wide_low_side", "sc_cam_med_high_kneel",
               "sc_cam_fisheye_squat", "sc_cam_bird_lying", "sc_cam_pov_stand",
               "sc_cam_low_stretch", "sc_cam_side_hairflip", "sc_cam_dutch_wall",
               "sc_cam_ots_lookback", "sc_cam_worm_sit"}
    got_cam = {s["id"] for s in scenes} & cam_ids
    ck("v3.17.2 镜头模板 10 条全部在库", len(got_cam) == 10,
       f"缺 {sorted(cam_ids - got_cam)}")
    ck("镜头模板一律不带 place（纯镜头模板，地点随机）",
       all("place" not in s["tags"] for s in scenes if s["id"] in cam_ids),
       str([s["id"] for s in scenes if s["id"] in cam_ids and "place" in s["tags"]]))
    ck("镜头模板 theme=「镜头实验」",
       all(s.get("theme") == "镜头实验" for s in scenes if s["id"] in cam_ids))
    # 抽一条真套用：擦边预设写进 state 后 F15 档位准入不红。
    # ⚠️ 必须走 **state**（apply_preset 的真实路径）—— 用 check_text 纯文本反推
    #    会把 `bent over` 误归到 n_pos 槽位（成品层反推歧义），假越档。
    _sample = next(s for s in scenes if s["id"] == "sc_yoga_mat")
    _tags = list(dict.fromkeys(
        t.strip() for f in _sample["tags"].values() for t in str(f).split(",")))
    _rep = R.check(_tags, dict(_sample["tags"]), 1)
    ck("擦边预设成品在 L1 检查无致命越档",
       all(c["ok"] for c in _rep["F"] if c["id"] == "F15"),
       str([c["note"] for c in _rep["F"] if c["id"] == "F15" and not c["ok"]]))

    # ── v3.44.1：丝袜专项 10 条（服装一定出现丝袜 + 腿环概率）──────
    # 这组不是"内容好看不好看"，而是**契约**：
    #   · 每条必须锁 socks（否则"一定出现"是假的）；
    #   · 候选必须是**丝袜类**，混进 `barefoot` / `ankle socks` 就等于没锁；
    #   · 候选最高档位不能超过条目档位（否则 build_scenes 会把 level 顶上去）；
    #   · 腿环走 `accessory` 候选，出现率按候选数算，写死成 100% 就不是"概率"了；
    #   · 最硬的一条：真套用一次，正文里必须真的有丝袜标签。
    print("\n── 丝袜专项（v3.44.1：10 条 + 腿环候选）──")
    sock_ids = sorted(s["id"] for s in scenes if s["id"].startswith("sc_sock_"))
    ck("丝袜专项 10 条全部在库", len(sock_ids) == 10,
       f"{len(sock_ids)}：{sock_ids}")
    ck("10 条 theme 一律「丝袜」（面板题材条能一键筛出）",
       all(next(s for s in scenes if s["id"] == i).get("theme") == "丝袜"
           for i in sock_ids),
       str([(i, next(s for s in scenes if s["id"] == i).get("theme"))
            for i in sock_ids]))
    ck("10 条都钉了人数（非特写场景的硬要求）",
       all(next(s for s in scenes if s["id"] == i).get("count_lock")
           for i in sock_ids))
    # 丝袜类判定：socks 字段里"赤足 / 短袜 / 袜套 / 足袋"这类**不是丝袜**，
    # 候选里出现它们就说明写错了键（把鞋袜当丝袜）。
    NOT_STOCKING = {"barefoot", "ankle socks", "no-show socks", "tabi",
                    "leg warmers", "slippers", "loose socks", "ribbed socks",
                    "fishnet socks", "frilled socks", "lace-trimmed socks"}
    bad_cand = []
    for i in sock_ids:
        sc = next(s for s in scenes if s["id"] == i)
        for c in (sc.get("random_fields") or {}).get("socks", []):
            if c in NOT_STOCKING or R.option_level("socks", c) is None:
                bad_cand.append((i, c))
    ck("每条都锁了 socks，且候选里没有「赤足 / 短袜」这类非丝袜",
       not bad_cand, str(bad_cand))
    ck("socks 候选一律 ≤ 条目自身档位（不会把档位顶上去）",
       all(R.option_level("socks", c) <= next(
               s for s in scenes if s["id"] == i).get("level", 0)
           for i in sock_ids
           for c in (next(s for s in scenes if s["id"] == i)
                     .get("random_fields") or {}).get("socks", [])),
       str([(i, c) for i in sock_ids
            for c in (next(s for s in scenes if s["id"] == i)
                      .get("random_fields") or {}).get("socks", [])
            if R.option_level("socks", c) > next(
                s for s in scenes if s["id"] == i).get("level", 0)]))
    ck("腿环（thigh strap）只在 accessory 候选里、不在 tags 里写死",
       all("thigh strap" in (next(s for s in scenes if s["id"] == i)
                             .get("random_fields") or {}).get("accessory", [])
           and "accessory" not in next(s for s in scenes if s["id"] == i)["tags"]
           for i in sock_ids),
       str([i for i in sock_ids
            if "thigh strap" not in (next(s for s in scenes if s["id"] == i)
                                     .get("random_fields") or {}).get("accessory", [])]))
    ck("sock_color 被闭麦（候选已带颜色，再抽一次颜色会自相矛盾）",
       all("sock_color" in (next(s for s in scenes if s["id"] == i)
                            .get("drop_fields") or [])
           for i in sock_ids),
       str([i for i in sock_ids
            if "sock_color" not in (next(s for s in scenes if s["id"] == i)
                                    .get("drop_fields") or [])]))
    _lv = Counter(next(s for s in scenes if s["id"] == i).get("level")
                  for i in sock_ids)
    ck("档位铺开 L0:4 / L1:3 / L2:2 / L3:1",
       (_lv.get(0), _lv.get(1), _lv.get(2), _lv.get(3)) == (4, 3, 2, 1),
       str(sorted(_lv.items())))
    # 真套用：n_canon 顶到 3.0 → apply_preset 写 state → 正文必须含候选之一
    _canon = R.canon()
    _miss = []
    _strap = 0
    _runs = 0
    for i in sock_ids:
        sc = next(s for s in scenes if s["id"] == i)
        lv_i = int(sc.get("level", 0))
        cands = sc["random_fields"]["socks"]
        w = R.empty_weights()
        w["fields"]["n_canon"] = 3.0
        w["options"]["n_canon"] = {k: (3.0 if k == i else 0.0) for k in _canon}
        for seed in (7, 77, 777):
            r = R.draw(level=lv_i, seed=seed, weights=w, tag_cap="自动")
            _runs += 1
            if (r["state"].get("socks") or "").strip() not in cands:
                _miss.append((i, seed, r["state"].get("socks")))
            if (r["state"].get("accessory") or "") == "thigh strap":
                _strap += 1
    ck("真套用 3 个 seed × 10 条：socks 全部命中候选（丝袜必现）",
       not _miss, str(_miss[:5]))
    ck("腿环出现率落在 10%–70%（是「概率」而不是恒有/恒无）",
       0.10 <= _strap / max(1, _runs) <= 0.70,
       f"{_strap}/{_runs}")

    # ── v3.44.2：候选池扩到**全集** + 亮丝星点加权 ─────────────────
    # 用户口径：「丝袜要能随机抽到各种款式」（点名白色亮丝星点过膝袜 / 白色亮丝星点袜 /
    # 淡粉亮丝星点吊带袜）。所以候选不再是每场景 3–4 款，而是**该档可用全集**：
    #   L0 54 款 · L1 58 款 · L2/L3 65 款（丝袜款里剔掉赤足/短袜/袜套等棉袜）。
    # ⚠️ 亮丝星点只有 15 款，全集里占 28%；要 ~1/3 只能**重复占位**
    #    （抽取是等概率取列表元素）—— 重复项是刻意加权，测试要允许并守住比例。
    _LEVEL_MIN = {0: 54, 1: 58, 2: 65, 3: 65}
    _size = {}
    _glit = {}
    _bad_share = []
    for i in sock_ids:
        sc = next(s for s in scenes if s["id"] == i)
        c = sc["random_fields"]["socks"]
        lv_i = int(sc.get("level", 0))
        _size[i] = (len(set(c)), len(c))
        share = sum(1 for x in c if "glittery" in x) / len(c)
        _glit[i] = round(share, 3)
        if len(set(c)) < _LEVEL_MIN[lv_i] or not (0.25 <= share <= 0.40):
            _bad_share.append((i, len(set(c)), round(share, 3)))
    ck("候选池覆盖该档全集（L0≥54 / L1≥58 / L2·L3≥65 款）",
       all(v[0] >= _LEVEL_MIN[next(s for s in scenes if s["id"] == i)["level"]]
           for i, v in _size.items()), str(_size))
    ck("亮丝星点系占候选 25%–40%（缺了就没覆盖到点名的那几款）",
       not _bad_share, str(_bad_share))
    ck("三族齐全：连裤 / 过膝 / 吊带过膝（点名款都在候选里）",
       all(any("glittery pantyhose" in x for x in
               next(s for s in scenes if s["id"] == i)["random_fields"]["socks"])
           and any("glittery thighhighs" in x and "garter" not in x for x in
                   next(s for s in scenes if s["id"] == i)["random_fields"]["socks"])
           and any("glittery thighhighs, garter straps" in x for x in
                   next(s for s in scenes if s["id"] == i)["random_fields"]["socks"])
           for i in sock_ids),
       "有点名款缺失")
    _named = ["white glittery thighhighs", "white glittery pantyhose",
              "pale pink glittery thighhighs, garter straps"]
    ck("用户点名的三款（白亮丝过膝 / 白亮丝连裤 / 淡粉亮丝吊带）都在候选里",
       all(n in next(s for s in scenes if s["id"] == i)["random_fields"]["socks"]
           for i in sock_ids for n in _named))
    # 真抽一轮看**款式多样性**：每场景 60 抽，统计出现过多少种不同款式
    _canon2 = R.canon()
    _variety = {}
    _glit_hit = 0
    _glit_n = 0
    for i in sock_ids:
        sc = next(s for s in scenes if s["id"] == i)
        lv_i = int(sc.get("level", 0))
        w = R.empty_weights()
        w["fields"]["n_canon"] = 3.0
        w["options"]["n_canon"] = {k: (3.0 if k == i else 0.0) for k in _canon2}
        seen = set()
        for seed in range(20000, 20060):
            r = R.draw(level=lv_i, seed=seed, weights=w, tag_cap="自动")
            got = (r["state"].get("socks") or "").strip()
            if got:
                seen.add(got)
                _glit_n += 1
                if "glittery" in got:
                    _glit_hit += 1
        _variety[i] = len(seen)
    ck("60 抽里每场景至少出现 15 种不同丝袜款（真的抽得开）",
       all(v >= 15 for v in _variety.values()), str(_variety))
    ck("实测亮丝星点出现率 15%–50%（加权生效，但没到主导）",
       0.15 <= _glit_hit / max(1, _glit_n) <= 0.50,
       f"{_glit_hit}/{_glit_n} = {_glit_hit / max(1, _glit_n):.1%}")

    # ── v4.4.5：变体级自然语言（`nl` 替换 / `nl_extra` 追加）──────────
    _vn, _vadd, _bad, _vtexts = [], [], [], []
    for s in scenes:
        rv = s.get("random_variants")
        if not rv:
            continue
        _pools = ([rv] if isinstance(rv, list)
                  else [((v.get("items") if isinstance(v, dict)
                         and isinstance(v.get("items"), list) else v) or [])
                        for v in rv.values()])
        for _body in _pools:
            for it in (_body or []):
                if not isinstance(it, dict):
                    continue
                if it.get("nl"):
                    _vn.append((s["id"], it.get("zh")))
                if it.get("nl_extra"):
                    _vadd.append((s["id"], it.get("zh")))
                for k in ("nl", "nl_extra"):
                    t = str(it.get(k) or "").strip()
                    if not t:
                        continue
                    _vtexts.append((s["id"], it.get("zh"), t))
                    if "," in t or any(g in t.lower() for g in
                                       ("camera", "lens", "dslr", "tripod",
                                        "reflection")):
                        _bad.append((s["id"], it.get("zh"), k))
    # v4.5.13：「丝袜里的跳蛋开关」的 6 个「姿势 × 地点」变体也是替换型 nl
    # （服装池只给 extra，不写 nl，不计入）
    # v4.5.33：「俯视自身」手部池 8 → 2 条 → 49-6=43 / 34 / 15-6=9
    # v4.5.38：「种付位·压制」压制动作池 5 条（追加型）→ 43+5=48 / 34 / 9+5=14
    # v4.5.43：「双女·穿戴式后入」胸部道具池 4 条（追加型）→ 48+4=52 / 34 / 14+4=18
    # v4.5.45：「悬吊·大字形插入」胸部道具池 4 条（追加型）→ 52+4=56 / 34 / 18+4=22
    # v5.0.3：「樱花道·回眸微笑」「白色婚纱·捧花等待」各 3 条变体，全部是追加型
    #         （手部/捧花交给变体池，场景主句不变）→ 56+6=62 / 34 / 22+6=28
    ck("动作型变体 62 个都写了变体 nl（替换 34 / 追加 28）",
       len(_vn) == 34 and len(_vadd) == 28, f"nl={len(_vn)} nl_extra={len(_vadd)}")
    ck("变体 nl 不含逗号 / 器材词 / reflection", not _bad, str(_bad[:3]))
    _nlset = R.nl_sentences()
    _missset = [(sid, zh) for sid, zh, t in _vtexts if t.lower() not in _nlset]
    ck("变体 nl 全部进了 nl_sentences()（repair / F17 会放行）",
       not _missset, str(_missset[:3]))
    _s0 = {"count": "1girl, solo"}
    R.apply_preset(_s0, "sc_near_nsfw_tongue", 3, R.empty_weights(),
                   variant_pick=0.0, variant_seed=None)
    _s1 = {"count": "1girl, solo"}
    R.apply_preset(_s1, "sc_near_nsfw_tongue", 3, R.empty_weights(),
                   variant_pick=0.99, variant_seed=None)
    ck("替换型：不同变体得到不同 body（不再共用一句）",
       _s0.get("_scene_nl") != _s1.get("_scene_nl"),
       (_s0.get("_scene_nl") or "")[:40])
    _s2 = {"count": "1girl, solo"}
    R.apply_preset(_s2, "sc_ccc_pov_self_body", 2, R.empty_weights(),
                   variant_pick=0.0, variant_seed=None)
    ck("追加型：场景句保留 + 变体句追加",
       "seen from above she sits on the edge of a bed" in str(_s2.get("_scene_nl"))
       and "rest flat on her thighs" in str(_s2.get("_scene_nl")),
       str(_s2.get("_scene_nl"))[-60:])
    _s3, _s4 = {"count": "1girl, solo"}, {"count": "1girl, solo"}
    R.apply_preset(_s3, "sc_pose_skirt_lift_disdain", 1, R.empty_weights(),
                   variant_pick=0.0, variant_seed=None)
    R.apply_preset(_s4, "sc_pose_skirt_lift_disdain", 1, R.empty_weights(),
                   variant_pick=0.99, variant_seed=None)
    ck("零漂移：没写 nl 的变体（内裤款式池）不改变正文",
       _s3.get("_scene_nl") == _s4.get("_scene_nl"), "两端不一致")

    # ⚠️ v4.5.1：`scene_nl` 句内**不许有逗号**。
    #    `collect()` 会按逗号把整句拆成 tag 堆，碎片又不在 `nl_sentences()` 的
    #    精确集合里 → F11 报"超长且不在词库内"（实测改「手持自拍」时踩到，
    #    sfw 200 抽里红 2 次）。分句一律用句号。
    nl_comma = [s["id"] for s in scenes if "," in str(s.get("scene_nl") or "")]
    ck("scene_nl 句内不含逗号（会被 collect 拆成 tag 碎片，F11 报超长）",
       not nl_comma, str(nl_comma[:3]))

    # ── v4.5.1：POV 手部视角 + 角色自己的手 = 画面里多出第三只手 ─────
    # 实测（`蝴蝶忍-001_L0_第一人称-手持自拍_00001`，用户现场发现）：一条场景
    # 同时写了 `viewpoint=pov hands`（观众的两只手入镜）、`arms_hands=v`（她自己
    # 比耶）、extra 的 `arm extended towards viewer` / `v sign`，再加 scene_nl 里的
    # "the hand makes a small v sign" —— 等于把"比耶"说了三遍、把手说了两套。
    # 模型照单全收：左下伸向镜头的手 + 右侧比耶的手 + 正下方多出来的一只手。
    # 判据：**POV 手部**视角（观众自己出手）不许再叠加角色自己的手部动作；
    # `pov, cowgirl position` 这类纯机位不在此列（它们的手部是场景道具）。
    POV_HAND_VP = ("pov hands",)
    dup_hands = []
    for s in scenes:
        _t = s.get("tags") or {}
        _vp = str(_t.get("viewpoint") or "").lower()
        if any(p in _vp for p in POV_HAND_VP) and (_t.get("arms_hands")
                                                   or _t.get("pose_risque")):
            dup_hands.append((s["id"], _vp, _t.get("arms_hands"),
                              _t.get("pose_risque")))
    ck("没有场景同时开「POV 手部视角」与角色自己的手部动作（会画出第三只手）",
       not dup_hands, str(dup_hands[:3]))
    sf = next((x for x in scenes if x["id"] == "sc_pov_hands_selfie"), {})
    ck("手持自拍：不再开 pov hands（第三只手的直接来源）",
       "pov" not in str((sf.get("tags") or {}).get("viewpoint") or "").lower(),
       str((sf.get("tags") or {}).get("viewpoint")))
    ck("手持自拍：闭麦 viewpoint（关掉随机视角，否则机位会跑到背后/侧面）",
       "viewpoint" in (sf.get("drop_fields") or []), str(sf.get("drop_fields")))
    ck("手持自拍：extra 不再重复 v sign（比耶只留 arms_hands=v 一个出口）",
       "v sign" not in str(sf.get("extra") or "").lower(),
       str(sf.get("extra"))[:80])
    ck("手持自拍：仍是 L0（去掉 pov hands 不该抬档）",
       int(sf.get("level", -1)) == 0, str(sf.get("level")))
    pov_bad, vdup = [], []
    for sd in range(20):
        rr = R.draw(level=0, seed=8100 + sd,
                    forced={"n_canon": "sc_pov_hands_selfie"}, base_prob=0.9)
        txt = rr["text"].lower()
        if "pov hands" in txt:
            pov_bad.append(sd)
        # "比耶"只能有一个出口：tags 里的 `v` 恰好一次（NL 那句不算标签堆）
        if [t for t in rr["tags"] if t.startswith("v")].count("v") != 1:
            vdup.append((sd, [t for t in rr["tags"] if t.startswith("v")]))
    ck("手持自拍：20 抽正文零 pov hands", not pov_bad, str(pov_bad[:3]))
    ck("手持自拍：20 抽正文里 `v` 恰好一次（不再三重叠加）", not vdup,
       str(vdup[:3]))

    # ── v4.5.2：双腿分开站 —— 句子写「手垂在身侧」，手部动作却在随机 ──
    # 原来 `tags` 不锁 `arms_hands` / `emotion`，而 `desc` 与 `scene_nl` 写死
    # "hands loose at her sides"。实测 seed1 抽到 `hand on own hip`（叉腰）、
    # seed2 抽到 `covering own mouth`（捂嘴）—— 标签和句子各说一套，
    # 用户看到的就是"这姿势哪里不对"。改成锁「叉腰 + 微笑」，句子同步改写。
    # ⚠️ 顺带锁了 `mouth` / `eye_gaze`：本库的联动表**没有** smile × mouth 的
    #    互斥规则（`L.bans_for({'emotion':'smile'}, 'mouth')` 返回空集），
    #    不锁的话 10 抽里有 2 抽是 `smile` + `frown`（抿嘴皱眉还在笑）。
    la = next((x for x in scenes if x["id"] == "sc_pose_legs_apart"), {})
    _lt = la.get("tags") or {}
    ck("双腿分开：锁了「叉腰」与「微笑」（原来手部在随机，与句子打架）",
       _lt.get("arms_hands") == "hand on own hip"
       and _lt.get("emotion") == "smile",
       str({k: _lt.get(k) for k in ("arms_hands", "emotion")}))
    ck("双腿分开：scene_nl 不再写「手垂在身侧」",
       "loose at her sides" not in str(la.get("scene_nl") or ""),
       str(la.get("scene_nl"))[:60])
    la_bad = []
    for sd in range(20):
        _rr = R.draw(level=0, seed=8200 + sd,
                     forced={"n_canon": "sc_pose_legs_apart"}, base_prob=0.9)
        _s = _rr["state"]
        if (_s.get("arms_hands") != "hand on own hip"
                or _s.get("emotion") != "smile"
                or _s.get("mouth") == "frown"):
            la_bad.append((sd, _s.get("arms_hands"), _s.get("emotion"),
                           _s.get("mouth")))
    ck("双腿分开：20 抽手部恒为叉腰、情绪恒为微笑、口部不出 frown",
       not la_bad, str(la_bad[:3]))

    # ── v4.5.3：「手放膝上」改成第三人称摄影 ────────────────────────
    # 原来这条特写**没锁视角也没锁人数**：40 抽里机位乱跳（from behind / 空），
    # 人数抽到 `1girl, 1boy, hetero`（一个只有手和大腿的画框里凭空多出个男的）。
    # 用户口径（2026-10-30）：第三人称、脸入画、斜上方俯拍、锁单人。
    # `action` 一并闭麦 —— 它会给坐姿塞 `dancing` / `spinning` / `swimming`。
    hl = next((x for x in scenes if x["id"] == "sc_near_hand_lap"), {})
    _ht = hl.get("tags") or {}
    ck("手放膝上：第三人称机位（from above，不再靠随机视角）",
       _ht.get("viewpoint") == "from above", str(_ht.get("viewpoint")))
    ck("手放膝上：七分身 cowboy shot（脸入画，不再是 extreme close-up）",
       _ht.get("shot_size") == "cowboy shot", str(_ht.get("shot_size")))
    ck("手放膝上：锁 1girl, solo（原来会抽到 1girl, 1boy, hetero）",
       str(hl.get("count_lock") or "") == "1girl, solo",
       str(hl.get("count_lock")))
    ck("手放膝上：闭麦 action（dancing / swimming 会和坐姿打架）",
       "action" in (hl.get("drop_fields") or []), str(hl.get("drop_fields")))
    hl_bad = []
    for sd in range(20):
        _rr = R.draw(level=0, seed=8300 + sd,
                     forced={"n_canon": "sc_near_hand_lap"}, base_prob=0.9)
        _s = _rr["state"]
        if (_s.get("count") != "1girl, solo"
                or _s.get("viewpoint") != "from above"
                or _s.get("shot_size") != "cowboy shot"):
            hl_bad.append((sd, _s.get("count"), _s.get("viewpoint"),
                           _s.get("shot_size")))
    ck("手放膝上：20 抽人数 / 机位 / 景别恒定", not hl_bad, str(hl_bad[:3]))

    # ── v4.5.4：城市桥夜景 —— 「车流灯轨」被写成了 traffic lights ────
    # `traffic lights` 在 danbooru 是**红绿灯本体**，不是车灯光轨。
    # 实测（`蝴蝶忍-092_L0_城市桥-夜景`）：画面上方左右各浮着一盏红灯。
    # 车灯光轨的正确写法是 `light trails` + `long exposure`。
    # 全库扫一遍：城市场景还会再加，这条红线靠测试守住。
    tl_hit = []
    for s in scenes:
        blob = (str(s.get("extra") or "") + " "
                + str(s.get("scene_nl") or "")).lower()
        for w in ("traffic light", "traffic signal", "signal light"):
            if w in blob:
                tl_hit.append((s["id"], w))
    ck("场景库没有把「车流灯轨」写成 traffic lights（会画出红绿灯本体）",
       not tl_hit, str(tl_hit[:3]))
    bn = next((x for x in scenes if x["id"] == "sc_wide_bridge_night"), {})
    ck("城市桥夜景：extra 改用 light trails（车灯光轨）",
       "light trails" in str(bn.get("extra") or "").lower(),
       str(bn.get("extra"))[:90])

    # ── v4.5.5：鞋跟特写 —— 只拍高跟鞋，画面里不出现人像 ────────────
    # 实测（`蝴蝶忍-118_L0_鞋跟特写_00001`）：画框里塞进一个弯腰的整人 + 脸。
    # 三个来源：① 没锁人数（会抽到 `1girl, 1boy, hetero`）；
    #           ② 没设 `no_role` → 写了角色名 + 发色/瞳色，模型就去画脸；
    #           ③ `arms_hands` 随机（抽到叉腰），脚部特写里多一只手。
    # 口径与特写页前端 `NEAR_VISIBLE["脚部"]` 对齐：只留皮肤 / 袜 / 鞋 / 姿势 /
    # 景别 / 机位 / 场景 / 光效，头发五官妆容身材全部闭麦。
    fh = next((x for x in scenes if x["id"] == "sc_near_foot_heel"), {})
    _ff = set(fh.get("drop_fields") or [])
    ck("鞋跟特写：no_role（画框无脸，不再写角色名与外貌）",
       fh.get("no_role") is True, str(fh.get("no_role")))
    ck("鞋跟特写：锁 1girl, solo", str(fh.get("count_lock") or "") == "1girl, solo",
       str(fh.get("count_lock")))
    ck("鞋跟特写：闭麦手部 / 头发 / 五官 / 妆容 / 身材 / 取景杂项",
       {"arms_hands", "hair_len", "hair_color", "eyes_color", "emotion",
        "eye_gaze", "mouth", "makeup", "figure", "dof", "device"} <= _ff,
       str(sorted(_ff)))
    ck("鞋跟特写：shoes 锁 high heels（确保是高跟鞋）",
       (fh.get("tags") or {}).get("shoes") == "high heels",
       str((fh.get("tags") or {}).get("shoes")))
    fh_v = R.scene_random_variants("sc_near_foot_heel")
    ck("鞋跟特写：10 款高跟随机变体",
       len(fh_v) == 1 and len(fh_v[0]["items"]) == 10,
       str([len(p["items"]) for p in fh_v]))
    fh_bad = []
    for sd in range(20):
        _s = R.draw(level=0, seed=8400 + sd,
                    forced={"n_canon": "sc_near_foot_heel"}, base_prob=0.9)["state"]
        _leak = {k: _s.get(k) for k in
                 ("role", "hair_len", "eyes_color", "emotion", "eye_gaze",
                  "mouth", "arms_hands", "figure", "leg") if _s.get(k)}
        if _leak or _s.get("count") != "1girl, solo":
            fh_bad.append((sd, _leak, _s.get("count")))
    ck("鞋跟特写：20 抽零角色 / 零头发五官 / 零手部，人数恒定",
       not fh_bad, str(fh_bad[:2]))

    # ── v4.5.6：泳装场景不许把「上装 / 下装 / 叠穿」抽进来 ────────────
    # 实测（`蝴蝶忍-127_L1_泳池阶梯-出水瞬间`）：画的是连体泳衣 + **牛仔裤**
    # + 运动鞋。根因：这些场景只锁 `outfit`（泳衣本身），`top / bottom /
    # cloth_state_sfw / cloth_mat` 全随机 —— 泳池里能抽出牛仔裤、飞行夹克、
    # 「外套搭肩」。鞋子按用户口径锁 `bare feet`。
    # ⚠️ `socks` 不闭麦：用户 2026-10-30 明确「丝袜可以出现」。
    SWIM = ["sc_beach_midsummer", "sc_poolside_summer", "sc_poolside_microbikini",
            "sc_beach_volley", "sc_pool_ladder", "sc_surf_board", "sc_float_ring",
            "sc_pose_poolside_kneel"]
    SC = {s["id"]: s for s in scenes}
    miss_drop, bad_shoe, kept_socks = [], [], []
    for _sid in SWIM:
        _s = SC.get(_sid) or {}
        _tags = _s.get("tags") or {}
        _dp = set(_s.get("drop_fields") or [])
        for _k in ("top", "bottom", "cloth_mat", "cloth_state_sfw"):
            if _k in _tags:
                continue
            if _k not in _dp:
                miss_drop.append((_sid, _k))
        if _tags.get("shoes") != "bare feet":
            bad_shoe.append((_sid, _tags.get("shoes")))
        if "socks" in _dp:
            kept_socks.append(_sid)
    ck("泳装场景：闭麦 top / bottom / cloth_mat / cloth_state_sfw",
       not miss_drop, str(miss_drop[:3]))
    ck("泳装场景：鞋子锁赤足（不会穿运动鞋下水）", not bad_shoe, str(bad_shoe[:3]))
    ck("泳装场景：socks 不闭麦（丝袜可以出现）", not kept_socks, str(kept_socks[:3]))
    swim_bad = []
    for _sid in SWIM:
        # ⚠️ 场景自己在 tags 里写了的字段不算泄漏（`sc_surf_board` 的
        #    `cloth_state_sfw = off shoulder` 是配方的一部分，不是随机抽进来的）
        _tg = (SC.get(_sid) or {}).get("tags") or {}
        for sd in range(6):
            _s = R.draw(level=1, seed=8500 + sd,
                        forced={"n_canon": _sid}, base_prob=0.9)["state"]
            _leak = [(k, _s.get(k)) for k in
                     ("top", "bottom", "cloth_state_sfw", "cloth_mat")
                     if _s.get(k) and k not in _tg]
            if _leak or _s.get("shoes") != "bare feet":
                swim_bad.append((_sid, sd, _leak, _s.get("shoes")))
    ck("泳装场景：8 条 × 6 抽零上装 / 零下装 / 零叠穿，鞋子恒赤足",
       not swim_bad, str(swim_bad[:2]))

    # ── v4.5.7：泳装「款式」随机（用户问「其他泳装款式能抽到吗」）────────
    # 原来 8 条都把 `outfit` 写死成一款 —— 实测 20 抽 20 次同一款。
    # 改成 `random_fields.outfit` 抽一个（**不是** `random_variants`：
    # 那个是往 extra 追加标签，两条 outfit 会同时出现 = 两层泳装）。
    # ⚠️ 候选计入档位派生，所以 L0 场景里不能放 `micro bikini`（L1）。
    no_pool, over_lv, few_faces = [], [], []
    for _sid in SWIM:
        _s = SC.get(_sid) or {}
        _lv = int(_s.get("level") or 0)
        _pool = ((_s.get("random_fields") or {}).get("outfit") or [])
        if "outfit" in (_s.get("tags") or {}):
            no_pool.append((_sid, "tags 里还写死着 outfit"))
        if len(set(_pool)) < 4:
            no_pool.append((_sid, len(set(_pool))))
        for _v in _pool:
            if R.option_level("outfit", _v) > _lv:
                over_lv.append((_sid, _v, R.option_level("outfit", _v), _lv))
    ck("泳装场景：8 条都不再写死 outfit，款式候选 ≥4 种",
       not no_pool, str(no_pool[:3]))
    ck("泳装场景：款式候选不超本场景档位（L0 里不放 micro bikini）",
       not over_lv, str(over_lv[:3]))
    for _sid in SWIM:
        _lv = int((SC.get(_sid) or {}).get("level") or 0)
        _seen = set()
        for sd in range(12):
            _st = R.draw(level=_lv, seed=8700 + sd,
                         forced={"n_canon": _sid}, base_prob=0.9)["state"]
            _seen.add(_st.get("outfit") or "")
        if len(_seen - {""}) < 3:
            few_faces.append((_sid, sorted(_seen)))
    ck("泳装场景：12 抽里每条至少出 3 种不同款式",
       not few_faces, str(few_faces[:2]))

    # ── v4.5.8：泳装场景的「披肩」是概率，不是必有 / 必无 ─────────────
    # v4.5.6 把 `top` / `cloth_state_sfw` 全闭麦后，用户附件里那种
    # 「敞开的和风羽织披在外面」就再也出不来了（用户 2026-10-30 反馈）。
    # 但直接把 `top` 放回随机又会抽到牛仔外套 / 羽绒服 —— 所以走变体池：
    # 每轮抽一条，4 条披 + 3 条不披（≈57%）。"不披"必须给中性 L0 标签
    # （`shoulders` / `collarbone`），因为 `_items()` 会丢掉 extra 为空的条目。
    # ⚠️ 披肩款式只能用 L0：`open kimono` / `sheer shawl` / `sheer sleeves`
    #    都是 L2，写进来会把整条场景抬到 L2（档位由内容派生）。
    no_var, bad_var_lv = [], []
    for _sid in SWIM:
        _s = SC.get(_sid) or {}
        _lv = int(_s.get("level") or 0)
        _pools = R.scene_random_variants(_sid)
        _items = [it for p in _pools for it in p["items"]]
        if len(_items) != 7:
            no_var.append((_sid, len(_items)))
            continue
        for it in _items:
            for t in str(it.get("extra") or "").split(","):
                t = t.strip().lower()
                if t and R.tag_level(t) > _lv:
                    bad_var_lv.append((_sid, t, R.tag_level(t), _lv))
    ck("泳装场景：8 条都有 7 条披肩变体（4 披 / 3 不披）",
       not no_var, str(no_var[:3]))
    ck("泳装场景：披肩变体只用本档标签（L2 的 open kimono 不能进）",
       not bad_var_lv, str(bad_var_lv[:3]))
    shawl_rate = []
    for _sid in SWIM:
        _lv = int((SC.get(_sid) or {}).get("level") or 0)
        _hit = 0
        for sd in range(30):
            _v = R.draw(level=_lv, seed=8800 + sd,
                        forced={"n_canon": _sid},
                        base_prob=0.9)["state"].get("_scene_variant") or ""
            if _v and not _v.startswith("无披肩"):
                _hit += 1
        shawl_rate.append((_sid, _hit))
    bad_rate = [(s, h) for s, h in shawl_rate if not (9 <= h <= 24)]
    ck("泳装场景：披肩出现率落在 30%–80%（是概率，不是恒有 / 恒无）",
       not bad_rate, str(bad_rate[:3]))

    # ── v4.5.9：沙滩排球「跃起扣杀」的姿势 ──────────────────────────
    # 实测（`蝴蝶忍-141_L1_沙滩排球-跃起扣杀`）：`pose_risque = leg up` +
    # `action = jumping` 被模型读成**正面一字马**，腿竖到头顶，左脚还多画了一只；
    # 两只手臂交叉抱在胸前，球飘在旁边没人碰。
    # ⚠️ `leg up` 同时是这条场景**唯一撑 L1 的标签**（bikini / jumping / sweat
    #    都判 0 档），不能直接删 —— 换成同样判 L1、且正是扣杀姿态的 `arched back`。
    bv = SC.get("sc_beach_volley") or {}
    _bt = bv.get("tags") or {}
    ck("沙滩排球：姿势换成 arched back（不再是正面一字马 leg up）",
       _bt.get("pose_risque") == "arched back", str(_bt.get("pose_risque")))
    ck("沙滩排球：手部锁 hand up（引拍那只手，不让它们随机交叉）",
       _bt.get("arms_hands") == "hand up", str(_bt.get("arms_hands")))
    ck("沙滩排球：闭麦 pose_base / prop / device"
       "（站立多余、书架窗帘、拍立得框都不能上沙滩）",
       {"pose_base", "prop", "device"} <= set(bv.get("drop_fields") or []),
       str(bv.get("drop_fields")))
    ck("沙滩排球：仍是擦边 L1（换标签不改变档位）",
       int(bv.get("level", -1)) == 1, str(bv.get("level")))
    ck("沙滩排球：scene_nl 不再写「one leg is lifted high behind」",
       "lifted high behind" not in str(bv.get("scene_nl") or ""),
       str(bv.get("scene_nl"))[:70])
    bv_bad = []
    for sd in range(20):
        _s = R.draw(level=1, seed=8900 + sd,
                    forced={"n_canon": "sc_beach_volley"}, base_prob=0.9)["state"]
        if (_s.get("pose_risque") != "arched back"
                or _s.get("arms_hands") != "hand up"
                or _s.get("pose_base")
                or _s.get("prop")):
            bv_bad.append((sd, _s.get("pose_risque"), _s.get("arms_hands"),
                           _s.get("pose_base"), _s.get("prop")))
    ck("沙滩排球：20 抽姿势 / 手部恒定，无 pose_base、无场景道具",
       not bv_bad, str(bv_bad[:2]))
    # ⚠️ 用户 2026-10-30 追加：画面里不要出现包包。
    #    实测 4 张里有 2 张拎着 `handbag`（accessory 字段抽到的）。
    #    这里只 ban 这一个值，耳环 / 项链 / 草帽 这些照常随机。
    ck("沙滩排球：ban 掉 handbag（扣杀时不能拎包）",
       "handbag" in (bv.get("ban_tags") or []), str(bv.get("ban_tags")))
    bag_hit = []
    for sd in range(20):
        _t = R.draw(level=1, seed=8950 + sd,
                    forced={"n_canon": "sc_beach_volley"},
                    base_prob=0.9)["text"].lower()
        if "handbag" in _t:
            bag_hit.append(sd)
    ck("沙滩排球：20 抽正文零 handbag", not bag_hit, str(bag_hit[:3]))

    # ── v4.5.10：第一人称·仰望站立 —— 画面里不许出现相机本体 / 取景 UI ──
    # 实测（`蝴蝶忍-178_L1_第一人称-仰望站立`）：画框底部出现一台单反，
    # 左上角还叠着 REC 红点 + 电量，人物被挤成背景。
    # 根因不是 `scene_nl`（里面没有器材词），而是 `device` 字段随机抽到了
    # `security camera footage` / `webcam footage` / `polaroid frame` ——
    # 40 抽里 9 次带相机类词（占 22%）。闭麦 device 后 20 抽零命中。
    ps = SC.get("sc_cam_pov_stand") or {}
    ck("仰望站立：闭麦 device（监控 / 摄像头 / 拍立得框都会画出器材）",
       "device" in (ps.get("drop_fields") or []), str(ps.get("drop_fields")))
    cam_hit = []
    for sd in range(20):
        _t = R.draw(level=1, seed=5100 + sd,
                    forced={"n_canon": "sc_cam_pov_stand"},
                    base_prob=0.9)["text"].lower()
        _g = [w for w in ("camera", "footage", "webcam", "polaroid",
                          "dslr", "lens") if w in _t]
        if _g:
            cam_hit.append((sd, _g))
    ck("仰望站立：20 抽正文零相机类词", not cam_hit, str(cam_hit[:2]))
    # ── v4.5.11：仰望站立的姿势 / 神态按用户参考图定死 ─────────────
    # 用户口径（2026-10-30）：「正面摄影，人物身体略微前倾，双手放大腿上支撑，
    # 表情害羞，低头看向镜头」。`hands on own thighs` 已在 `pose_risque` 里，
    # 这里补 `emotion = embarrassed, blush` 与 extra 的 `leaning forward`。
    # ⚠️ `comp` 里的 `profile`（侧脸）与 `landscape`（横构图）和「正面竖幅」
    #    直接冲突 —— 实测 20 抽里 `profile` 出 1 次、`landscape` 出 2 次，
    #    用 ban_tags 点掉（其余 symmetry / bokeh / vignetting 保留）。
    ck("仰望站立：emotion = embarrassed, blush（害羞脸红）",
       (ps.get("tags") or {}).get("emotion") == "embarrassed, blush",
       str((ps.get("tags") or {}).get("emotion")))
    ck("仰望站立：extra 带 leaning forward（上身前倾）",
       "leaning forward" in str(ps.get("extra") or "").lower(),
       str(ps.get("extra")))
    ck("仰望站立：ban 掉 profile / landscape（正面竖幅）",
       {"profile", "landscape"} <= set(ps.get("ban_tags") or []),
       str(ps.get("ban_tags")))
    ps_bad = []
    for sd in range(20):
        _s = R.draw(level=1, seed=5250 + sd,
                    forced={"n_canon": "sc_cam_pov_stand"},
                    base_prob=0.9)["state"]
        if (_s.get("emotion") != "embarrassed, blush"
                or _s.get("pose_risque") != "hands on own thighs"
                or _s.get("comp") in ("profile", "landscape")):
            ps_bad.append((sd, _s.get("emotion"), _s.get("pose_risque"),
                           _s.get("comp")))
    ck("仰望站立：20 抽神态 / 撑腿姿势恒定，无侧脸无横构图",
       not ps_bad, str(ps_bad[:2]))
    # ⚠️ 用户 2026-10-30「画面不要出现包包」—— 实测这条 4 张里 1 张挂着
    #    金链黑色手提包（accessory 抽到 handbag），与沙滩排球同一个来源。
    ck("仰望站立：ban 掉 handbag（不拎包）",
       "handbag" in (ps.get("ban_tags") or []), str(ps.get("ban_tags")))
    ps_bag = []
    for sd in range(20):
        if "handbag" in R.draw(level=1, seed=5270 + sd,
                               forced={"n_canon": "sc_cam_pov_stand"},
                               base_prob=0.9)["text"].lower():
            ps_bag.append(sd)
    ck("仰望站立：20 抽正文零 handbag", not ps_bag, str(ps_bag[:3]))

    # ── v4.5.12：「裙下真空」改成第三人称 · 隐晦 · 裙子+丝袜+袜口开关 ────
    # 用户口径（2026-10-30）：第三人称摄影 / 裙子款式服装 + 丝袜 /
    # 大腿丝袜内固定跳蛋开关 / 表达隐晦自慰 / 场景名称更新。
    # 「隐晦」的落地关键：**不写 `n_theme = vibrator`**（那是 L3，会把
    # 跳蛋本体画出来），只在 `extra` 写 `remote control in thighhighs`。
    # 同时闭麦所有会"露"的 NSFW 字段 —— 实测不闭麦时抽到过
    # `n_body = clitoris`、`n_fabric = wet cotton`、`n_shoes_keep = otherwise nude`
    # （"只穿这四件、其余全裸"），隐晦直接破功。
    sv = SC.get("sc_msb_skirt_vacuum") or {}
    _st = sv.get("tags") or {}
    ck("丝袜开关：场景名已更新（不再叫「裙下真空」）",
       "裙下真空" not in str(sv.get("zh") or ""), str(sv.get("zh")))
    ck("丝袜开关：第三人称侧面机位",
       _st.get("viewpoint") == "from side", str(_st.get("viewpoint")))
    # v4.5.13（用户追加）：丝袜与服装款式多变 / 户外要有「被看到」的刺激感。
    # 结构改成：服装由 `random_variants.outfit` 池给（上装+下装成对），
    # 丝袜由 `random_fields.socks` 抽（9 款都带袜口，粉色开关才卡得住），
    # 姿势与地点仍由 `random_variants.scene` 池给。
    ck("丝袜开关：服装与丝袜不再写死（top/bottom 撤出 tags，socks 走候选池）",
       "top" not in _st and "bottom" not in _st and "socks" not in _st,
       str(sorted(_st)))
    _svsocks = ((sv.get("random_fields") or {}).get("socks") or [])
    ck("丝袜开关：丝袜候选 ≥8 款且都带袜口（thighhighs / 及膝以上）",
       len(_svsocks) >= 8
       and all("thighhighs" in v for v in _svsocks),
       str(_svsocks))
    _svp = R.scene_random_variants("sc_msb_skirt_vacuum")
    _pool = {p["key"]: p["items"] for p in _svp}
    # v4.5.25：加第三池 `mood`（表情二选一：隐忍 / 快要高潮）
    ck("丝袜开关：变体是「姿势地点 + 服装 + 表情」三池（6 / 6 / 2）",
       set(_pool) == {"scene", "outfit", "mood"}
       and len(_pool["scene"]) == 6 and len(_pool["outfit"]) == 6
       and len(_pool["mood"]) == 2,
       str({k: len(v) for k, v in _pool.items()}))
    ck("丝袜开关：姿势池每条都带 nl，服装池只给 extra",
       all(it.get("nl") for it in _pool["scene"])
       and all(not it.get("nl") for it in _pool["outfit"]),
       str([(it["zh"], bool(it.get("nl"))) for it in _pool["scene"]]))
    ck("丝袜开关：表情池两条（隐忍 / 快要高潮）且都带 extra + nl_extra",
       [it["zh"] for it in _pool["mood"]] == ["隐忍", "快要高潮"]
       and all(it.get("extra") and it.get("nl_extra") for it in _pool["mood"]),
       str([(it["zh"], it.get("extra"), bool(it.get("nl_extra")))
            for it in _pool["mood"]]))
    _svout = [it for it in _pool["scene"] if "outdoors" in str(it.get("extra"))]
    # v4.5.17（用户 2026-10-30 第四轮）：**取消「风吹起裙子」** —— 风把裙摆掀起来
    # 就等于给了模型一个「裙下走光」的入口，与「不露生殖器」直接冲突。
    # 户外三条改为「一手把裙角按在大腿上」（hand holds the hem down），
    # 裙摆靠自重垂落，刺激感交给「忍不出声」而不是靠风。
    ck("丝袜开关：户外变体仍是 3 条",
       len(_svout) == 3, str([it["zh"] for it in _svout]))
    _svwind = [(it["zh"], str(it.get("nl")).lower()[:40]) for it in _pool["scene"]
               if any(w in str(it.get("nl")).lower()
                      for w in ("the wind", "gust", "breeze", "blown"))]
    ck("丝袜开关：任何变体都不再写风（v4.5.17 取消风吹裙摆）",
       not _svwind
       and not any(w in str(sv.get("scene_nl") or "").lower()
                   for w in ("the wind", "gust", "breeze", "blown")),
       str(_svwind))
    # ── v4.5.14：户外三条改夜里 + 线只画「两端都被挡住」的一段 ──────
    # 线的几何位置**无法真正控制**（tag 表达不了连接关系），能做的是把它写成
    # 「从袜口遥控器往上、没入裙摆下缘」—— 两端都有物体遮挡，模型即使只画一小截，
    # 读起来也是连着的。原来写 "runs up from it beneath the skirt"，模型常画成
    # 往下垂到椅子上，落单成一截。
    ck("丝袜开关：户外三条都是夜里（extra 带 night）",
       all("night" in str(it.get("extra")).lower() for it in _svout),
       str([(it["zh"], it.get("extra")) for it in _svout]))
    ck("丝袜开关：weather 已闭麦（否则随机 clear sky 会和夜里打架）",
       "weather" in (sv.get("drop_fields") or []), str(sv.get("drop_fields")))
    # ── v4.5.15：开关改「腿环绑在大腿上」+ 线只露一小截、其余被裙摆遮 ──
    # 用户口径（2026-10-30）：线围绕大腿、剩余部分被服装遮挡；开关被腿环绑在大腿上；
    # 不显著露出开关与线；面部与耳朵赤红。
    # ⚠️ 线的写法是决定性变量：旧版 "the rest slips under the hem of her skirt"
    #    （先说「剩余部分」）会让模型画出一根很长的线往下垂/在长椅上打圈，真机 0/6 对；
    #    改成 "only a tiny loop of pink cable shows above the strap and her skirt
    #    hides the rest"（**先说只露一小截**）后，真机 5.5/6 对。
    #    顺序不能反 —— 先提"剩余"就等于先给了"线很长"的暗示。
    # ── v4.5.24：**彻底不写连接线**（用户 2026-10-30 第八轮拍板）───────
    # 真机七轮（v4.5.17→v4.5.23，共 150+ 张）的结论：**细线的长度无法用正向
    # 提示词约束**。试过「没入裙摆 / 止于袜口 / 往上走 / 从顶部出线 / 上端被裙摆
    # 压住 / 创可贴压线」六种写法，最好的也只有约 2/3 合格，其余必然画飞
    # （垂到地面绕圈、甩出大弧、或直接连到手里）。
    # 用户决定：**去掉线**，只留「腿环 + 粉色开关 + 粉色创可贴压住开关」。
    # 这样画面 100% 不会出现飞线，也不会出现「手握线/跳蛋」。
    # v4.5.26（用户：要能认出是「无线遥控器开关」+ 裙摆遮一半 + 不小心露出来）
    # v4.5.27（用户：只出现一个遥控器 / 遥控器改到丝袜下面 / 腿环固定丝袜+开关）
    _bad_line = [(it["zh"]) for it in _pool["scene"]
                 if "rectangular pink wireless remote" not in str(it.get("nl")).lower()
                 or "tucked inside the top of her thighhighs"
                 not in str(it.get("nl")).lower()
                 or "the stocking covers its upper half"
                 not in str(it.get("nl")).lower()
                 or "buckled over the stocking" not in str(it.get("nl")).lower()
                 or "only the lower half of the remote shows below the band"
                 not in str(it.get("nl")).lower()]
    ck("丝袜开关：每条 nl 都写「遥控器塞在袜口内侧 + 腿环压住丝袜与遥控器 + 下半露出」",
       not _bad_line
       and all(k in str(sv.get("scene_nl") or "").lower() for k in (
           "rectangular pink wireless remote",
           "tucked inside the top of her thighhighs",
           "the stocking covers its upper half",
           "buckled over the stocking",
           "only the lower half of the remote shows below the band")),
       str(_bad_line))
    # ⚠️ 双遥控器的根因：`pink switch` 标签 + 自然语言各描述一次 → 模型画两个。
    # 现在只留自然语言一个描述源，extra 里不许再出现 switch / remote。
    ck("丝袜开关：extra 不写任何开关/遥控器标签（只留自然语言一个描述源，防双遥控器）",
       not any(w in str(sv.get("extra") or "").lower()
               for w in ("switch", "remote", "device")),
       str(sv.get("extra")))
    # 线必须**彻底退场**：nl 与 extra 里都不许出现 cable / cord / wire / remote。
    # ⚠️ `wire` 要用词边界 —— v4.5.26 起正文里有 `wireless remote`，
    #    直接查子串会把「无线」误判成「电线」（这次就踩了）。
    import re as _re
    def _has_cord(t):
        t = str(t).lower()
        return ("cable" in t or "cord" in t or "remote control" in t
                or _re.search(r"\bwire\b", t) is not None)
    _cordy = [(it["zh"]) for it in _pool["scene"] if _has_cord(it.get("nl"))]
    ck("丝袜开关：nl 与 extra 完全不写连接线（cable / cord / wire）",
       not _cordy
       and not _has_cord(str(sv.get("scene_nl") or "") + str(sv.get("extra") or "")),
       str(_cordy))
    # v4.5.25：用户明确「创可贴也不要」—— extra 与 nl 里都不许再出现 bandaid。
    ck("丝袜开关：彻底不用创可贴（extra / nl 零 bandaid）",
       "bandaid" not in (str(sv.get("extra") or "") + str(sv.get("scene_nl") or "")).lower()
       and not any("bandaid" in str(it.get("nl")).lower()
                   for it in _pool["scene"]),
       str(sv.get("extra")))

    ck("丝袜开关：arms_hands 已撤出 tags 并闭麦（防随机抽叉腰/举手打架）",
       "arms_hands" not in (sv.get("tags") or {})
       and "arms_hands" in (sv.get("drop_fields") or []),
       str({"tags_arms": (sv.get("tags") or {}).get("arms_hands"),
            "drop": "arms_hands" in (sv.get("drop_fields") or [])}))
    # v4.5.25：用户「取消脸和耳朵发红」—— nl 不许写红，emotion 也不许带 blush。
    _bad_ear = [(it["zh"]) for it in _pool["scene"]
                if any(w in str(it.get("nl")).lower()
                       for w in ("burn deep red", "cheeks", "blush", "flushed"))]
    ck("丝袜开关：nl 不再写脸/耳朵发红（burn deep red / cheeks / blush）",
       not _bad_ear
       and not any(w in str(sv.get("scene_nl") or "").lower()
                   for w in ("burn deep red", "cheeks", "blush", "flushed")),
       str(_bad_ear))
    ck("丝袜开关：emotion / mouth 已闭麦（表情改由 mood 池给）",
       {"emotion", "mouth"} <= set(sv.get("drop_fields") or [])
       and "emotion" not in (sv.get("tags") or {})
       and "mouth" not in (sv.get("tags") or {}),
       str({"drop": sorted(set(sv.get("drop_fields") or []) & {"emotion", "mouth"}),
            "tags": sorted(set(sv.get("tags") or {}) & {"emotion", "mouth"})}))
    _svextra = str(sv.get("extra") or "").lower()
    # ⚠️ 丝袜池里不能有 `garter straps`（吊袜带）：它会在袜口往上画出两条竖带，
    #    和粉色线在画面上混成一起，用户实测「有几张变成了吊带线」。
    _svsocks = list(((sv.get("random_fields") or {}).get("socks")) or [])
    # v4.5.28：用户允许「长筒袜 / 吊带袜等」，且要求袜口在裙摆下方。
    # 之前排除吊带袜是因为它的竖带会和粉色线混淆 —— 线取消后这条限制解除。
    ck("丝袜开关：丝袜池 ≥10 款、全部带袜口，且包含吊带袜",
       len(_svsocks) >= 10
       and all("thighhighs" in v.lower() for v in _svsocks)
       and any("garter" in v.lower() for v in _svsocks),
       str(_svsocks))
    ck("丝袜开关：每条 nl 都写「袜口在裙摆下方」",
       all("the top of her thighhighs sits below the hem of her skirt"
           in str(it.get("nl")).lower() for it in _pool["scene"])
       and "the top of her thighhighs sits below the hem of her skirt"
       in str(sv.get("scene_nl") or "").lower(),
       str([it["zh"] for it in _pool["scene"]]))
    # v4.5.28：`blush` 还会从 `makeup` 字段漏进来（makeup = "blush, half-closed eyes,
    # eyeliner"）—— 只闭麦 emotion/mouth 不够，makeup 也必须闭。
    ck("丝袜开关：makeup 已闭麦（否则 blush 会从 makeup 漏回来）",
       "makeup" in (sv.get("drop_fields") or []), str(sv.get("drop_fields")))
    ck("丝袜开关：extra 用腿环 thigh strap（耳赤红由 nl 表达）",
       "thigh strap" in _svextra and "ear blush" not in _svextra,
       str(sv.get("extra")))
    ck("丝袜开关：extra 不再单独要 pink cord / under skirt"
       "（线已彻底退场；under skirt 会诱导裙下走光视角）",
       "pink cord" not in _svextra and "under skirt" not in _svextra,
       str(sv.get("extra")))
    ck("丝袜开关：extra 带 legs together（防三条腿）",
       "legs together" in _svextra, str(sv.get("extra")))
    ck("丝袜开关：姿势 / 地点已从 tags 撤出并闭麦",
       {"pose_base", "place", "prop"} <= set(sv.get("drop_fields") or [])
       and "pose_base" not in _st and "place" not in _st,
       str(sv.get("drop_fields")))
    _pz, _sz, _oz = set(), set(), set()
    for sd in range(30):
        _o = R.draw(level=2, seed=8900 + sd,
                    forced={"n_canon": "sc_msb_skirt_vacuum"},
                    base_prob=0.9)
        _pz.add(_o["state"].get("_scene_variant") or "")
        _sz.add(_o["state"].get("socks") or "")
        _oz.add(tuple(sorted(t.strip() for t in
                             str(_o["state"].get("n_extra") or "").split(","))))
    ck("丝袜开关：30 抽里姿势地点变体 ≥4 种", len(_pz - {""}) >= 4,
       str(sorted(_pz)))
    ck("丝袜开关：30 抽里丝袜款 ≥4 种、服装组合 ≥4 种",
       len(_sz - {""}) >= 4 and len(_oz) >= 4,
       f"socks={len(_sz - {''})} outfit={len(_oz)}")
    ck("丝袜开关：不写 vibrator（L3，会把跳蛋本体画出来）",
       _st.get("n_theme") != "vibrator", str(_st.get("n_theme")))
    # ── v4.5.17：撤掉 `n_act = masturbation` ─────────────────────────
    # `masturbation` 是 Danbooru 语义里「手在自慰」的标签，写进正文就等于给模型
    # 下了一条「把手放到下身」的指令。撤掉后档位仍稳在 L2：
    # `no panties under skirt`(L2) + `aroused`(L2) 两个锚点都在。
    ck("丝袜开关：n_act 已闭麦、不再锁 masturbation（手不参与自慰）",
       "n_act" not in (sv.get("tags") or {})
       and "n_act" in (sv.get("drop_fields") or []),
       str({"tags": (sv.get("tags") or {}).get("n_act"),
            "drop": "n_act" in (sv.get("drop_fields") or [])}))
    ck("丝袜开关：闭麦会「露」的 NSFW 字段"
       "（n_body / n_fabric / n_exposure / n_shoes_keep）",
       {"n_body", "n_fabric", "n_exposure", "n_shoes_keep"}
       <= set(sv.get("drop_fields") or []), str(sv.get("drop_fields")))
    ck("丝袜开关：仍是 L2（由 no panties under skirt 撑住）",
       int(sv.get("level", -1)) == 2, str(sv.get("level")))
    # ── v4.5.16 / v4.5.18：手部只留一个动作 tag，另一手按胸口 ─────────
    # 引擎限制（F18）：同一双手只能有**一个**手部动作 tag。`holding own skirt`
    # 已撤（Danbooru 常见画法是「撩裙」，会把裙子撩到胯部），改成三个
    # 「手不碰布料」的动作：坐/蹲 `hand on own knee`、站立 `hand on own hip`、
    # 靠墙 `hand on wall`。
    _hand_items = [str(it.get("extra") or "") for it in _pool["scene"]]
    _HANDS = ("hand on own knee", "hand on own hip", "hand on wall")
    ck("丝袜开关：每条变体恰好一个手部 tag（膝盖 / 腰侧 / 扶墙）",
       all(any(h in e.lower() for h in _HANDS) for e in _hand_items)
       and not any(("holding own skirt" in e.lower()
                    or "covering own mouth" in e.lower()) for e in _hand_items),
       str(_hand_items))
    _bad_endure = [(it["zh"]) for it in _pool["scene"]
                   if "pressed flat against her chest" not in str(it.get("nl")).lower()
                   or "must not make a sound" not in str(it.get("nl")).lower()]
    ck("丝袜开关：每条 nl 都写「另一手按在胸口 + 公共场所忍不出声」",
       not _bad_endure
       and "pressed flat against her chest" in str(sv.get("scene_nl") or "").lower()
       and "must not make a sound" in str(sv.get("scene_nl") or "").lower(),
       str(_bad_endure))
    _bad_mouth = [(it["zh"]) for it in _pool["scene"]
                  if "over her mouth" in str(it.get("nl")).lower()]
    ck("丝袜开关：nl 里不再出现捂嘴（over her mouth）",
       not _bad_mouth
       and "over her mouth" not in str(sv.get("scene_nl") or "").lower(),
       str(_bad_mouth))
    sv_bad = []
    for sd in range(20):
        _o = R.draw(level=2, seed=8600 + sd,
                    forced={"n_canon": "sc_msb_skirt_vacuum"}, base_prob=0.9)
        _t = _o["text"].lower()
        _g = [w for w in ("otherwise nude", "clitoris", "pussy", "anus",
                          "squirting", "ahegao", "camera", "polaroid",
                          "masturbation", "vibrator", "the wind", "gust",
                          "over her mouth", "cable", "cord", "blush",
                          "bandaid", "burn deep red")
              if w in _t]
        if _g or (_o["state"].get("viewpoint") != "from side"):
            sv_bad.append((sd, _g, _o["state"].get("viewpoint")))
    ck("丝袜开关：20 抽零露骨词、零 masturbation/风/捂嘴/线/红脸/创可贴，机位恒定",
       not sv_bad, str(sv_bad[:2]))

    # ── v4.5.38：种付位 · 压制 —— 改成真第一人称 ────────────────────────
    # 用户口径（2026-10-31，附 蝴蝶忍-212 那张图）：要第一人称压制视角。
    # 那张画面里男方**整条上身连同脸**都在画框上方、她的脸反倒倒扣在最下方 ——
    # 这是「从她头顶往后 180 度看过去」的机位，不是 POV。三个根因：
    #   ① extra 写了 `boy on top` + 人数锁 `1boy`：模型必须把男方画成**主体**，
    #      而第一人称根本拍不到自己的脸 → 它只能把机位挪到远处，退成第三人称；
    #   ② 景别 `close-up` 装不下「脸 + 折叠腿 + 按压的手」，模型再次选择后退；
    #   ③ 句子主语是 `he presses her shoulders` —— 全篇没有一处告诉模型镜头在哪。
    mp = next((x for x in scenes if x["id"] == "sc_ccc_mating_press"), {})
    _mpt = mp.get("tags") or {}
    _mpe = str(mp.get("extra") or "").lower()
    _mpn = str(mp.get("scene_nl") or "").lower()
    ck("种付位：机位是第一人称性交（pov, sexual intercourse）",
       _mpt.get("viewpoint") == "pov, sexual intercourse", str(_mpt.get("viewpoint")))
    ck("种付位：景别从 close-up 放宽到 cowboy shot（装得下脸 + 折叠腿 + 手）",
       _mpt.get("shot_size") == "cowboy shot", str(_mpt.get("shot_size")))
    ck("种付位：extra 不再写死「他的手按哪里」（落点交给变体池）",
       "his hands pressing" not in _mpe and "boy on top" not in _mpe,
       _mpe[:160])
    # ⚠️ 用户 2026-10-31 追加：「几种压制动作可以随机抽取，保证多样性」。
    #    press 池每条必须**同时**给 extra 与 nl_extra —— 只给 extra 会让句子
    #    还停在上一条落点（按膝的句子配按踝的 tag，画面自相矛盾）。
    _mpv = ((mp.get("random_variants") or {}).get("press") or {})
    _mpitems = _mpv.get("items") if isinstance(_mpv, dict) else _mpv
    ck("种付位：压制落点是变体池（5 选 1），每条都带 extra + nl_extra",
       isinstance(_mpitems, list) and len(_mpitems) == 5
       and all(str(it.get("extra") or "").strip()
               and str(it.get("nl_extra") or "").strip() for it in _mpitems),
       str(len(_mpitems or [])))
    ck("种付位：extra 写明「他的脸出画」（POV 里男方不能露脸）",
       "his face out of frame" in _mpe, _mpe[:160])
    ck("种付位：句子把镜头锚在他的眼睛上，并写死「只有手与前臂入画」",
       "seen from his eyes" in _mpn and "only his hands and forearms" in _mpn,
       _mpn[:160])
    ck("种付位：赤足写死 + 闭麦 n_shoes_keep（thigh boots 从这里漏）",
       _mpt.get("shoes") == "bare feet"
       and "n_shoes_keep" in (mp.get("drop_fields") or []), str(_mpt.get("shoes")))
    ck("种付位：闭麦会破坏机位的字段（action / device / dof / comp / texture_fx / arms_hands）",
       {"action", "device", "dof", "comp", "texture_fx", "arms_hands"}
       <= set(mp.get("drop_fields") or []), str(mp.get("drop_fields")))
    # ⚠️ 丝袜必须走 random_fields：本节目标签数已顶到密度上限，光靠随机抽的
    #    `socks` 会被 trim_to_cap 当低权重削掉（实测 20 抽 0 次）；
    #    而池里**不能有 pantyhose** —— sanitize 有一条「连裤袜 + 赤足 → 鞋改高跟」。
    ck("种付位：丝袜走 random_fields 且池里不含 pantyhose（连裤袜 + 赤足会被改成高跟）",
       "socks" in (mp.get("random_fields") or {})
       and not any("pantyhose" in v for v in mp["random_fields"]["socks"]),
       str((mp.get("random_fields") or {}).get("socks")))
    _mpbad = []
    _mppress = set()
    for sd in range(30):
        _o = R.draw(level=3, seed=9100 + sd, base_prob=0.9,
                    forced={"n_canon": "sc_ccc_mating_press"})
        _t = _o["text"].lower()
        _g = [w for w in ("boy on top", "walking", "selfie", "webcam",
                          "pixel art", "silhouette", "looking at another",
                          "high heel", "boots", "umbrella", "my hands",
                          "hands on her body", "pantyhose")
              if w in _t]
        for _it in _mpitems or []:
            if str(_it.get("extra") or "").lower() in _t:
                _mppress.add(str(_it.get("zh")))
        if (_g or "pov" not in _t or "cowboy shot" not in _t
                or _o["state"].get("shoes") != "bare feet"):
            _mpbad.append((sd, _g))
    ck("种付位：30 抽零第三人称词零杂物，pov + cowboy shot + 赤足恒定",
       not _mpbad, str(_mpbad[:2]))
    ck("种付位：30 抽里 5 种压制动作全部被抽到（多样性）",
       len(_mppress) == 5, str(sorted(_mppress)))

    print()
    if FAILS:
        print(f"[check_v3_scenes] 失败 {len(FAILS)} 项：{FAILS}")
        return 1
    print(f"[check_v3_scenes] 通过：{len(scenes)} 个场景（"
          + " / ".join(f"{k}={v}" for k, v in sorted(by_group.items()))
          + "）· 合并 / 闸门 / 固定 / 输出 / 载荷 全部符合预期")
    return 0


if __name__ == "__main__":
    sys.exit(main())
