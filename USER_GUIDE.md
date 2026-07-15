# BenchArc SEC 用户使用指南

BenchArc SEC 是用于将 SEC（体积排阻色谱）原始数据整理为发表级图形的
macOS 本地应用。数据处理和绘图均在本机完成，应用不会上传实验数据。

## 1. 安装与首次启动

1. 从 [GitHub Releases](https://github.com/yny0420/BenchArc-SEC/releases/latest)
   下载最新的 `BenchArc_SEC_*.dmg`。
2. 打开 DMG，将 **BenchArc SEC** 拖入 **Applications**。
3. 当前版本为 Apple Silicon 构建，用户不需要安装 Python、PySide6、NumPy
   或其他运行环境。
4. 当前安装包尚未经过 Apple 公证。如果首次双击被 macOS 阻止，请按住
   Control 点击应用，选择“打开”，再确认一次。

## 2. 导入 SEC 原始数据

推荐优先使用仪器导出的 TXT、CSV 或 TSV 文件，因为原始数据最适合定量分析。

1. 点击顶部的 **Add data files**。
2. 选择一个或多个文件。应用支持 UTF-16 UNICORN 多通道 TXT，以及普通的
   TXT、CSV 和 TSV 表格。
3. 导入后，在左侧 **Source** 列表中选择需要编辑的样品。
4. 应用会自动寻找体积/时间列和 UV/A280 信号列。请在左上角确认识别出的
   列名和数据点数是否合理。

## 3. 调整坐标轴

在 **Axes** 区域设置：

- **X minimum / maximum**：显示的洗脱体积范围。
- **Y minimum / maximum**：显示的 UV 范围。
- **major tick / minor tick**：主刻度和次刻度间距。
- **X label / Y label**：坐标轴标题。

修改后预览会自动刷新。坐标范围只影响显示，不会删除原始数据。

## 4. 设置发表风格

点击 **Apply bold gray preset** 可恢复默认发表风格：白色背景、灰色曲线、
黑色左/下坐标轴、无网格和无填充。也可以单独修改曲线颜色和线宽、坐标轴
宽度、字体大小以及主峰标注。

## 5. 数据变换与归一化

**Data transformations** 提供以下选项：

- **Smoothing window**：移动平均平滑窗口。默认值 1 表示不平滑。
- **Subtract baseline**：将当前显示范围内的最低点修正为 0。
- **Visible maximum = 1**：将显示范围内的最高点归一化为 1。
- **Selected peak = 1**：在指定洗脱体积附近寻找局部峰，并将该峰归一化为 1。

选择峰归一化时，在 **Reference peak near (ml)** 输入参考峰附近的体积，
并使用 **Peak half-window (ml)** 限制搜索范围。所有变换仅改变显示值，不会
覆盖导入的原始信号；变换信息会记录在 SVG 元数据中。

## 6. 计算峰面积

1. 在 **Peak area** 中填写 **Start (ml)** 和 **End (ml)**。
2. 勾选 **Calculate and shade**。
3. 应用会显示原始积分面积、线性基线校正面积和当前显示尺度下的面积。
4. **Set ±1 ml around main peak** 可快速建立初始积分范围，之后应根据实际
   峰边界手动调整。

进行样品间定量比较时，应统一积分区间、基线方法与归一化方式，并优先报告
线性基线校正面积。图片数字化得到的面积只能视为近似值。

## 7. 批量处理

1. 一次导入多个数据文件。
2. 在 Source 列表中逐个检查样品。
3. 若所有样品需要相同设置，点击 **Apply settings to all**。
4. 点击 **Batch export** 并选择输出目录。

批量导出会为每个可用样品生成 SVG 和 600 dpi PNG。启用峰面积计算时，还会
生成可由 Excel 打开的 `BenchArc_SEC_peak_areas.csv`。

## 8. 导出发表图

- **Export SVG**：推荐用于 Adobe Illustrator、Affinity Designer 或
  Inkscape 中继续编辑。
- **Export 600 dpi PNG**：推荐用于论文草稿、幻灯片和直接提交。

导出前请确认坐标范围、单位、峰位置和积分范围，并保留原始数据文件与分析参数。

## 9. 图片输入说明

PNG、JPEG 和 TIFF 图片可以通过 **Add images** 导入，但该功能依赖坐标校准和
曲线颜色提取。图片得到的数值属于近似数字化结果，不建议用于精确产率或峰面积
比较。只要原始 TXT/CSV/TSV 可用，就应优先使用原始数据。

## 10. 常见问题

### 导入后曲线不正确

确认应用识别的是体积列和 UV/A280 列，而不是电导、缓冲液浓度或分段编号。

### 归一化后 Y 轴变为 0–1

这是预期行为。选择 **Off** 可恢复 mAU 显示。

### 无法计算峰面积

确认起始体积小于终止体积，并且两者都位于实际数据范围内。

### macOS 提示应用无法验证

当前版本未经过 Apple 公证。Control-click 应用并选择“打开”。不要从非官方来源
下载安装包。

### 如何报告问题

请在 [GitHub Issues](https://github.com/yny0420/BenchArc-SEC/issues) 中说明
macOS 版本、BenchArc SEC 版本、输入文件类型和复现步骤。不要上传含有敏感或
未公开实验信息的数据文件。
