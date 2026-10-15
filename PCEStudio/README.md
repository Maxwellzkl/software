# PCE Studio

面向 Keysight/Agilent B2902B 的 Windows 双通道光伏 I-V 测量软件。使用 `import pyvisa as visa` 通过 USB VISA 控制源表。

项目地址：<https://github.com/Maxwellzkl/software/tree/main/PCEStudio>

## 已实现功能

- 自动枚举 USB VISA 资源并用 `*IDN?` 验证 B2902B。
- 单通道模式可选择 CH1 或 CH2；双通道模式同步测量两个独立器件/像素。
- 双通道共享扫描参数，各通道单独保存器件编号、Point、面积和 Light/Dark 状态。
- 正扫、反扫、正反扫；B2902B 内部 LIST 扫描完成一个扫向后立即更新曲线。
- 长时间 LIST 扫描通过 VISA 状态字节轮询等待完成，避免 Normal/Long 档在点数较多时被固定通信超时误判为失败。
- 可调参数包括 Source Function、V/I 模式、DC、Source Delay、Start、Stop、VAR1 Count、Compliance、源量程、两种测量量程、Measure Delay 和 Measure Speed；所有数值参数在界面显示对应单位。
- 所有下拉框和数值输入框均禁止用鼠标滚轮改值；鼠标滚轮只滚动参数页面，避免悬停误操作。
- Measure Speed 提供 Auto、Short、Medium、Normal、Long、Manual 六档，默认 Normal；Manual 可自定义 NPLC。
- Source Range 提供 B2902B 对应固定量程；Voltage/Current Measure Range 提供 Auto、Fixed、Limited 三种模式。由于软件只使用 DC，未列入仅脉冲模式可用的 10 A 档。
- 根据 Start、Stop 和 VAR1 Count 实时显示正扫/反扫步长。
- Light 数据分别计算正扫和反扫的 PCE、Voc、Jsc、FF、Pmax；双扫按平均 Voc/Jsc/FF 重新计算平均 PCE。
- Dark 数据只保存和绘图，不计算光伏性能。
- 器件编号和面积保存至本机数据库；历史测试曲线可勾选叠加比较。
- IV 图为右侧主工作区；器件配置采用紧凑卡片，结果与历史曲线使用底部标签页切换。
- 窗口初始尺寸会按屏幕可用区域自动适配，参数栏宽度保持在紧凑范围；小屏幕可通过左侧滚动条查看全部参数。
- 原始文件名为 `器件编号_light或dark_Point.csv`，重名时自动添加 `_002` 等序号。
- 数据输出目录可直接输入，也可点击“选择…”打开 Windows 目录选择窗口。
- “结束并导出统计”生成 `output_file_年月日_时分秒.xlsx`。
- “i 参数说明”可查看扫描、量程、速度和单位解释；右下角显示 `created by ZKL` 及可点击的 GitHub 链接。
- 内置明确标注的 B2902B 模拟器，用于无源表时验证界面、计算、保存和导出流程。

## 计算口径

- `J = I × 1000 / Area`，单位为 mA/cm²。
- Jsc 使用 V=0 两侧数据线性插值，并按光伏性能惯例报告绝对值。
- Voc 使用 J=0 两侧数据线性插值，并报告绝对值。
- 在 0 到 Voc 的功率区间内计算 `Pmax = max(|V × J|)`。
- `FF = Pmax / |Voc × Jsc| × 100%`。
- `PCE = Pmax / Pin × 100%`，Pin 默认 100 mW/cm²且可调。
- 正反扫平均结果先分别平均 Voc、Jsc、FF，再据此重新计算 Pmax 和 PCE。

扫描范围没有覆盖 V=0 或电流零交点时，软件仍保存原始数据，但对应性能参数显示为空，并给出提示。

## 源码运行

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pce_app
```

## 构建可移植 EXE

在项目目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

输出为 `dist\PCEStudio_portable\PCEStudio.exe`。复制到其他电脑时必须保留整个 `PCEStudio_portable` 文件夹，不能只复制其中的 EXE。目标测量电脑仍需安装 Keysight IO Libraries Suite，以提供 USB VISA 驱动和 VISA backend；Python 和项目源码不需要另行安装。

## 使用流程

1. 安装 Keysight IO Libraries Suite，并用 USB 连接 B2902B。
2. 点击“自动枚举”，选择源表，然后点击“连接并识别”。
3. 选择单/双通道并填写各通道器件编号、Point、面积、Light/Dark。
4. 设置扫描参数。开始前务必检查 Compliance、源量程和接线。
5. 点击“开始测量”。“停止测量”会请求中止扫描并关闭输出。
6. 测试完成后，可勾选历史记录比较曲线。
7. 点击“结束并导出统计”生成 Excel 汇总。

软件每次测量结束、异常、用户停止或正常退出时都会尝试执行 `ABOR` 并关闭 CH1/CH2 输出。首次接入真实器件前，建议先用限流电阻和保守 Compliance 验证接线、极性及量程。
