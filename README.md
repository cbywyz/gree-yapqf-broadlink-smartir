# 格力空调 + 博联 RM Mini 3 + Home Assistant SmartIR 完整部署教程

**Gree AC (Junyue 俊越 / YAPQF remote) + Broadlink RM Mini 3 + Home Assistant SmartIR — Full Working Guide**

> 2026-09-25 实测打通：HA 面板直接控格力空调（开关 / 5 种模式 / 4 档风速 / 温度调节），温湿度自动联动第三方传感器。

## 相关仓库（同一系列教程）

- [cbywyz/ha-hualing-fan-broadlink](https://github.com/cbywyz/ha-hualing-fan-broadlink) —— 华凌风扇（WH-FGA2401）红外接入教程：RM3 学码 + **全套 8 键遥控器编码库**，思路与本仓库同源（Broadlink 红外），风扇没有现成码库、纯靠学习
- [cbywyz/ha-midea-hualing-ac](https://github.com/cbywyz/ha-midea-hualing-ac) —— 美的/华凌**空调**接入教程：华凌本地 token 拿不到，走 `midea_auto_cloud` 云端方案（美居账号一次登录）
- [cbywyz/phicomm-aircat-m1](https://github.com/cbywyz/phicomm-aircat-m1) —— 斐讯悟空 M1 空气检测仪本地复活（本仓库温湿度数据源的完整教程）
- [cbywyz/ha-tv-kids-lock](https://github.com/cbywyz/ha-tv-kids-lock) —— 电视**家长管控**教程（HA 自动化，任意智能电视通用，以小米电视为例）：音量上限锁 + 信号源锁定 + 儿童观看定时锁，管控放在电视外面，没有密码可破。
- [cbywyz/istoreos-caddy-lucky](https://github.com/cbywyz/istoreos-caddy-lucky) —— iStoreOS **公网入口**教程：Caddy 终结 TLS（Let's Encrypt 自动签发/续期）+ LUCKY 反代，标准 443 **免端口**访问家里的服务。上面这些 HA 想在出门在外也能打开，靠的就是这套（含防火墙放行、DDNS、两套域名互备的踩坑实录）。

## 适用范围

| 你的情况 | 是否适用 |
|---|---|
| 格力空调，遥控器型号 **YAP 系列**（YAP0F / YAP1F2 / YAPQF 等，机身背面或电池仓有标注） | ✅ 直接用本文方案（码表 1185） |
| 格力空调，其他型号遥控器 | ⚠️ 流程一样，码表要按 §5 换着试 |
| Broadlink RM Mini 3 / RM4 系列红外遥控器（已接入 HA broadlink 集成） | ✅ |
| Home Assistant 容器版（Python 3.13 / 3.14） | ✅ |

## 为什么你的 SmartIR 发码没反应？（核心结论，先看这个）

如果你按官方文档装了 `smartHomeHub/SmartIR`，配置看起来全对、`climate` 实体也生成了，但空调毫无反应——**九成不是码表问题，是发送根本没成功**。

**根因**：SmartIR 官方版 1.18.1（2022 年后停更）调用 `remote.send_command` 时发送的是**裸 Base64 码**，而新版 Home Assistant 的 broadlink 集成要求原始码必须带 **`b64:` 前缀**。不带前缀的码会被当成「存储的学习命令」解析，直接报错：

```
ValueError: You need to specify a device
Failed to call remote.send_command: You need to specify a device
```

这个错误出现在 HA 日志里，但 SmartIR 实体状态层面看起来一切正常——所以非常隐蔽。

**解法**：换社区维护的 fork —— **[litinoveweedle/SmartIR](https://github.com/litinoveweedle/SmartIR)**（1.19.x），它的 `controller.py` 已加上 `b64:` 前缀，并修复了 Python 3.12+ 移除 `distutils` 的问题（官方版在新 HA 上连加载都过不了）。

## 三大坑速查

| # | 坑 | 症状 | 解法 |
|---|---|---|---|
| 1 | 官方 SmartIR 1.18.1 发码无 `b64:` 前缀 | 实体正常、空调没反应；HA 日志有 `ValueError: You need to specify a device` | 换 litinoveweedle fork 1.19.x |
| 2 | fork 1.19.x **不支持** configuration.yaml 里的集成级 `smartir:` 行 | 启动报 `The 'smartir' integration does not support YAML setup` | **删掉** `smartir:` 那一行；`climate: - platform: smartir` 的 YAML 写法仍然支持 |
| 3 | fork 的 `controller_data` 改为结构化格式 | 沿用旧字符串写法不生效或报错 | 用 YAML 映射（见下方配置示例） |
| 4 | 官方版在 Python 3.12+ 上 `from distutils.version import StrictVersion` 直接崩 | 集成加载即失败 | 同坑 1，换 fork；或自行替换 StrictVersion 实现 |

## 部署步骤

### 1. 安装 fork 版 SmartIR

从 [litinoveweedle/SmartIR releases](https://github.com/litinoveweedle/SmartIR/releases) 下载最新 `smartir.zip`，解压到 HA 配置目录：

```
/config/custom_components/smartir/
├── __init__.py
├── climate.py
├── controller.py
├── controller_const.py
├── fan.py / light.py / media_player.py
├── manifest.json
├── codes/            # 官方码表
│   └── climate/
│       ├── 1185.json ← 格力 YAP 遥控器协议（本方案用这个）
│       └── ...
└── custom_codes/     # 自己的码表放这里，HACS 更新不丢
```

HACS 用户：添加自定义仓库 `https://github.com/litinoveweedle/SmartIR` 后安装即可。

### 2. configuration.yaml 配置

⚠️ **不要再写 `smartir:` 集成级行**（坑 2），直接写 climate 平台：

```yaml
climate:
  - platform: smartir
    name: 工厂格力
    unique_id: gong_chang_ge_li
    device_code: 1185              # 格力 YAP 遥控器系列协议
    controller_data:
      controller_type: Broadlink
      remote_entity: remote.zhi_neng_yao_kong   # 换成你的 broadlink remote 实体
      delay_secs: 0.5
      num_repeats: 1
    temperature_sensor: sensor.xxx_temperature   # 可选：室温传感器
    humidity_sensor: sensor.xxx_humidity         # 可选：湿度传感器
```

### 3. 重启并验证

重启 HA，`climate` 实体应出现且 `hvac_modes` 包含 5 种模式：

```
['heat_cool', 'cool', 'dry', 'fan_only', 'heat', 'off']
fan_modes: ['low', 'mid', 'high', 'auto']
```

调用 `climate.set_temperature`（制冷 26°C）测试。**同时盯着 HA 日志**——如果出现 `ValueError: You need to specify a device`，说明你还在用官方版，回到坑 1。

### 4. 如何确认码表是否兼容你的空调

码发出去了（日志无报错）但空调不响应 = **码表协议不对**（这是另一类问题，与坑 1 无关）。格力红外协议有多个代际变体，码表按遥控器型号选：

| 遥控器系列 | 建议码表 | 实测 |
|---|---|---|
| **YAP0F / YAP1F2 / YAPQF** | **1185** | ✅ 俊越挂机开机/制冷/温度全有效 |
| GWH09KF / GC-EAF09HR | 1184 | 未测 |
| GWH12-KF-K3DNA5G-I | 1180 | ❌ 本机不兼容（发码成功但无响应） |
| GMV-R45G/NaB-K | 1182 | 未测 |

验证方法：从码表 JSON 里取一条原始码，直接在开发者工具里发（不经 SmartIR）：

```yaml
action: remote.send_command
target:
  entity_id: remote.zhi_neng_yao_kong
data:
  command: "b64:JgCSAAABKJ..."   # ← 注意必须有 b64: 前缀
```

## 进阶：学码补齐附加按键（上下扫风 / 灯光 / 睡眠等）

SmartIR 码表只含温控主功能（开关/模式/风速/温度）。遥控器上的**扫风、灯光、睡眠**等键码表里没有，需要用 `remote.learn_command` 学原遥控器的码。

> 本仓库 [codes/gree_yap_extra_codes.json](codes/gree_yap_extra_codes.json) 已附 YAPQF 实测的**上下扫风完整码**（748 字节三段式），可直接 b64 直发，不用学。其余键照下面流程自己学。

### 5.1 learn_command 用法（新版 HA）

⚠️ **新版 HA（2024+）已移除 `storage_path` 参数**，网上旧文档传了会直接 400。现在学到的码自动存进 `.storage/broadlink_remote_<mac>_codes`：

```yaml
action: remote.learn_command
target:
  entity_id: remote.xxx          # 你的 broadlink remote 实体
data:
  device: gree_extra             # 自定义组名
  command: ["swing_vertical"]    # 自定义命令名；传列表可串行学多键
  command_type: ir
  timeout: 60                    # 等按键的最长秒数（0-60）
```

调用后黑豆进入学习状态，把原遥控器对准黑豆正面接收窗（**5~10 厘米**，太近红外过载反而截断），按下按键即可。回放时**不带 `b64:` 前缀**就表示查学习库：

```yaml
action: remote.send_command
target:
  entity_id: remote.xxx
data:
  device: gree_extra
  command: ["swing_vertical"]
```

### 5.2 学码实战坑（全部踩过）

| # | 坑 | 现象 / 解法 |
|---|---|---|
| 1 | 传旧参数 `storage_path` | HTTP 400 Bad Request —— 删掉，新版码自动入库 |
| 2 | 残留学习窗口截胡第一个码 | 试探参数时触发的学习还在等码，正式学习第一键被它收走 → 全部错位。开学前确保没有未超时的学习任务（等 60s 或重启） |
| 3 | **码长截断诊断法** | 某键反复学到**恒定长度**的短码（如恒 400）且回放无效 = 三段式长码（含长间隔）被学习模式提前截断（RM 系列短板，完整码 748）。先试 `alternative: true` 换采样模式；仍不行就直接回放历史好码或从博联 App 抓 |
| 4 | `alternative: true` 不是万能 | 我们实测它学出 2 字节的废码，比不传还差——穷举一下两种模式都试试 |
| 5 | **先确认硬件有该功能再学码** | 血泪教训：我们三轮学码后才发现空调的左右导风条是**固定死、无电机**的——遥控器上「左右扫风」键发的码完全正确，但设备根本不执行。学码前先上手摸摸导风条动不动！ |

### 5.3 面板加按钮（Lovelace button 卡片）

学好的码做成按钮，`tap_action` 直接 b64 发码（不依赖学习库，重装也不丢）：

```yaml
type: button
name: 上下扫风
icon: mdi:arrow-up-down
icon_height: 36px
tap_action:
  action: perform-action
  perform_action: remote.send_command
  target:
    entity_id: remote.xxx
  data:
    command:
      - "b64:JgAoAQABKZIXNRcRFxAXNRc1FzUXNRcRFjUX..."   # 完整码见 codes/gree_yap_extra_codes.json
```

批量学码可用 [scripts/learn_extra_keys.py](scripts/learn_extra_keys.py)（串行学习 + 码长截断检测 + 学成自动回放验证）：

```bash
export HASS_URL="http://homeassistant.local:8123"
export HASS_TOKEN="<长期访问令牌>"
python scripts/learn_extra_keys.py swing_vertical swing_horizontal \
    --entity remote.xxx \
    --codes-file /config/.storage/broadlink_remote_<mac>_codes
```

## 排错表

| 现象 | 原因 | 处理 |
|---|---|---|
| `remote.send_command` HTTP 500 | 码无 `b64:` 前缀（官方版 SmartIR 的锅） | 换 fork 1.19.x |
| 启动报 `does not support YAML setup` | configuration.yaml 里残留 `smartir:` 行 | 删掉该行 |
| 启动报 `No module named 'distutils'` | 官方 1.18.1 + Python 3.12+ | 换 fork 1.19.x |
| 实体正常、日志无报错、空调没反应 | 码表协议与你的空调不匹配 | 按 §4 换码表；都不行就用 `remote.learn_command` 学原遥控器的码 |
| 实体只有 off/cool/heat 两三种模式 | 用了 1183 等简化码表 | 换 1185（5 模式 + 4 风速） |
| 博联官方 App 能控制、HA 不能 | 大概率坑 1；确认 HA 日志无发送错误后再怀疑码表 | 见上 |
| 学码反复得到恒定短码且回放无效 | 三段式长码被截断，或硬件根本没这功能 | 见 §5.2 坑 3 / 坑 5 |

## 实测环境

- Home Assistant 容器版（2026.x，Python 3.14），broadlink 集成（本地模式）
- Broadlink RM Mini 3（黑豆），遥控器与空调同房间直射
- SmartIR fork 1.19.1 + 码表 1185
- 温湿度来源：斐讯悟空 M1（本地复活版，另见 [phicomm-aircat-m1](https://github.com/cbywyz/phicomm-aircat-m1)）

## 致谢

- [litinoveweedle/SmartIR](https://github.com/litinoveweedle/SmartIR) —— fork 版修复，本方案核心
- [smartHomeHub/SmartIR](https://github.com/smartHomeHub/SmartIR) —— 原项目与码表库
- 社区所有贡献 Gree 码表的作者

救活了点个 ⭐
