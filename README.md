# semg-intent-recognition

基于表面肌电信号（sEMG）的手势意图识别。数据来自 MYO 臂环的 8 通道电极，共 7 类手势。

## 数据集

本项目使用 **EMG data for gestures** 数据集（压缩包内名为 `EMG_data_for_gestures`）。

原始数据**没有纳入本仓库的版本管理**（约 251 MB 文本），`data/` 已写入 `.gitignore`。
如需复现下方目录结构，请从 UCI 下载该数据集，并把 `EMG_data_for_gestures-master/`
中的内容直接解压到 `data/` 下。

- 来源：<https://archive.ics.uci.edu/dataset/481/emg+data+for+gestures>
- DOI：10.24432/C5GH2K
- 许可证：CC BY 4.0

### 引用

> Lobov, S., Krilova, N., Kastalskiy, I., Kazantsev, V., & Makarov, V. A. (2018).
> Latent Factors Limiting the Performance of sEMG-Interfaces. *Sensors*, 18(4), 1122.
> <https://doi.org/10.3390/s18041122>

### 采集方式

共 36 名受试者（`01`–`36`），每人完成两轮动作，每轮包含 6–7 个静态手势。
采集设备为 MYO Thalmic 臂环，8 个电极等距分布于前臂一周，信号经蓝牙传输至 PC。
每个手势保持 3 秒，手势之间停顿 3 秒。

## 目录结构

```
data/
├── 01/
│   ├── 1_raw_data_13-12_22.03.16.txt
│   └── 2_raw_data_13-13_22.03.16.txt
├── 02/
├── ...
└── 36/
```

每个 `*_raw_data_*.txt` 为 **Tab 分隔**，**含一行表头**，共 10 列：

```
time	channel1	channel2	channel3	channel4	channel5	channel6	channel7	channel8	class
1	1e-05	-2e-05	-1e-05	-3e-05	0	-1e-05	0	-1e-05	0
```

| 列号 | 列名 | 含义 |
|------|------|------|
| 1 | `time` | 时间，单位毫秒 |
| 2–9 | `channel1`–`channel8` | MYO 的 8 个肌电通道 |
| 10 | `class` | 手势标签，见下表 |

类别标签：

| 标签 | 手势 |
|------|------|
| 0 | 未标注数据 |
| 1 | 手放松 |
| 2 | 握拳 |
| 3 | 腕屈 |
| 4 | 腕伸 |
| 5 | 桡侧偏 |
| 6 | 尺侧偏 |
| 7 | 伸掌（并非所有受试者都做了该手势） |

**关于类别分布的两点实测结论**（非数据集文档原文，系对本副本统计所得）：

- 类别 7（伸掌）仅出现在**受试者 11 和 30**，其余 34 人只有类别 0–6。
- 全数据集中类别 0 占比约 **65%**（约 270 万 / 420 万条），这部分对应手势之间的停顿段。
  直接用于训练会严重不平衡，通常需要降采样或类别加权。

**关于采样率**：数据集自带说明未标注采样频率。对本副本实测，`time` 列步长以 1 ms
为主（约 6.3 万行跨 6.57 万 ms，平均 1.04 ms/样本，含少量缺口），据此推算约 1 kHz；
而部分文献按 200 Hz 处理该数据集。窗口长度按样本数设置时，请留意此处歧义。

## 出处声明

上文数据集描述改编自数据集自带的 `data/README.txt`（该文件已保留）。
原始文件未做任何修改，此处按 CC BY 4.0 转载。

## 许可证

本仓库的代码适用根目录下的 [LICENSE](LICENSE)。
`data/` 中的数据集为另一独立作品，适用 CC BY 4.0，详见上文。
