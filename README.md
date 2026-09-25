# 格力空调 + 博联 RM Mini 3 + Home Assistant SmartIR 完整部署教程

**Gree AC (Junyue 俊越 / YAPQF remote) + Broadlink RM Mini 3 + Home Assistant SmartIR — Full Working Guide**

> 2026-09-25 实测打通：HA 面板直接控格力空调（开关 / 5 种模式 / 4 档风速 / 温度调节），温湿度自动联动第三方传感器。

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

## 排错表

| 现象 | 原因 | 处理 |
|---|---|---|
| `remote.send_command` HTTP 500 | 码无 `b64:` 前缀（官方版 SmartIR 的锅） | 换 fork 1.19.x |
| 启动报 `does not support YAML setup` | configuration.yaml 里残留 `smartir:` 行 | 删掉该行 |
| 启动报 `No module named 'distutils'` | 官方 1.18.1 + Python 3.12+ | 换 fork 1.19.x |
| 实体正常、日志无报错、空调没反应 | 码表协议与你的空调不匹配 | 按 §4 换码表；都不行就用 `remote.learn_command` 学原遥控器的码 |
| 实体只有 off/cool/heat 两三种模式 | 用了 1183 等简化码表 | 换 1185（5 模式 + 4 风速） |
| 博联官方 App 能控制、HA 不能 | 大概率坑 1；确认 HA 日志无发送错误后再怀疑码表 | 见上 |

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
