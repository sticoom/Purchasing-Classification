

# 📦 Cross-border E-commerce Pick-up Plan Processor
### 跨境电商提货计划自动化分发系统

本项目是一款专为跨境电商（Cross-border E-commerce）场景设计的物流数据处理工具。它能够自动解析提货计划与采购订单，实现供应商维度的自动拆表、物流时效计算及异常数据预警。

---

## 🚀 核心功能 (Features)

* **智能日期推算**：自动解析版本单号（如 `THJH260302/A`），提取年份及月日，并自动倒推 5 天作为计划发货时间。
* **高精度供应商匹配**：基于 SKU 进行精确匹配，支持单 SKU 对应多行采购记录的去重识别。
* **数据预清洗**：前置过滤“提货未入库数量”为 0 的无效行，确保下发给供应商的指令 100% 有效。
* **全局时序排列**：所有输出文件均按照“计划发货时间”进行升序排列，方便仓库排程。
* **严格字段重组**：输出结果强行适配 A-Q 列标准字段顺序，剔除冗余信息。

---

## 🛠 逻辑架构 (Logic Architecture)

系统采用典型的 **ETL（提取-转换-加载）** 架构：

1.  **数据输入 (Input)**
    * **提货计划表**：作为主数据基准，保留所有原始行信息。
    * **采购订单追踪表**：作为匹配库，提供 SKU 与供应商的对应关系。

2.  **核心处理层 (Processing)**
    * **日期引擎**：提取版本号第 5-6 位（年）、7-10 位（月日），执行 `Date - 5 days` 计算。
    * **分流器 (The Funnel)**：
        * **0 值流**：提货未入库数量 = 0 → 转移至异常表 Sheet3。
        * **多匹配流**：1 个 SKU 对应多个厂家 → 转移至异常表 Sheet1。
        * **无匹配流**：SKU 在采购表中缺失 → 转移至异常表 Sheet2。
        * **主流程**：1 对 1 匹配成功 → 记录进入供应商独立文件。

3.  **排序引擎 (Sort Engine)**
    * 根据计算出的 `datetime` 对象执行全局升序排列。

4.  **数据输出 (Output)**
    * 生成按供应商命名的 `.xlsx` 压缩包。

---

## 📊 数据规范 (Data Specifications)

### 1. 输入要求
* **支持格式**：`.xlsx`, `.xls`, `.csv`。
* **读取逻辑**：程序默认读取文件的第一个工作表（First Sheet）。

### 2. 输出字段顺序 (Strict A-Q Order)
输出文件将严格按照以下顺序排列：
1. 单据编号 | 2. 版本单号 | 3. 国家 | 4. SKU | 5. SKU 名称 | 6. FNSKU | 7. 供应商 | 8. 装箱数 | 9. 订单状态 | 10. 提货数量 | 11. 已关联送货数量 | 12. 提货未入库数量 | 13. 已入库数量 | 14. 关联送货单 | 15. 提货状态 | 16. 计划备注 | 17. 计划发货时间。

---

## 💻 技术实现 (Tech Stack)

* **Language**: Python 3.9+
* **Framework**: [Streamlit](https://streamlit.io/) (Web UI)
* **Data Processing**: Pandas (High Performance)
* **Excel Engine**: Openpyxl
* **Packaging**: Zipfile (In-memory buffer)

---

## 📖 快速开始 (Quick Start)

1.  **安装依赖**：
    ```bash
    pip install streamlit pandas openpyxl
    ```
2.  **本地运行**：
    ```bash
    streamlit run app.py
    ```
3.  **部署**：
    支持一键部署至 Streamlit Cloud 或通过 Docker 部署至私有云。

---

