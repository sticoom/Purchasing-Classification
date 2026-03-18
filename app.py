import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import io
import zipfile

# 设置页面配置
st.set_page_config(page_title="跨境电商提货计划处理系统", layout="wide")

# --- 核心逻辑函数 ---

def get_date_details(version_code):
    """提取日期并计算倒推5天后的结果"""
    if pd.isna(version_code) or len(str(version_code)) < 10:
        return "❌", datetime(2099, 12, 31)
    try:
        code_str = str(version_code)
        year = int("20" + code_str[4:6])
        month = int(code_str[6:8])
        day = int(code_str[8:10])
        target_date = datetime(year, month, day)
        result_date = target_date - timedelta(days=5)
        return f"{result_date.month}月{result_date.day}日", result_date
    except:
        return "❌", datetime(2099, 12, 31)

def read_file(uploaded_file):
    """读取第一个 Sheet，支持 xlsx, xls, csv"""
    file_name = uploaded_file.name
    if file_name.endswith('.csv'):
        return pd.read_csv(uploaded_file)
    else:
        return pd.read_excel(uploaded_file, sheet_name=0)

# --- 页面 UI ---

st.title("📦 提货计划 - 自动分发系统 (全功能增强版)")
st.info("当前逻辑：1. 过滤掉未入库数量为0的行 | 2. 按发货时间升序 | 3. 严格字段排序 A-Q")

col1, col2 = st.columns(2)
with col1:
    plan_file = st.file_uploader("1. 上传：提货计划表", type=['xlsx', 'xls', 'csv'])
with col2:
    order_file = st.file_uploader("2. 上传：采购订单追踪表", type=['xlsx', 'xls', 'csv'])

# 定义目标字段顺序（严格按照截图 A-Q）
TARGET_HEADERS = [
    "单据编号", "版本单号", "国家", "SKU", "SKU名称", 
    "FNSKU", "供应商", "装箱数", "订单状态", "提货数量", 
    "已关联送货数量", "提货未入库数量", "已入库数量", 
    "关联送货单", "提货状态", "计划备注", "计划发货时间"
]

if st.button("开始执行处理", disabled=not (plan_file and order_file)):
    try:
        with st.spinner("正在执行前置筛选、日期计算与全局排序..."):
            # 1. 加载数据
            plan_df = read_file(plan_file)
            order_df = read_file(order_file)

            # 2. 预处理供应商库
            sku_supplier_map = order_df.groupby('SKU')['供应商'].apply(
                lambda x: set(x.dropna().unique())
            ).to_dict()

            # 3. 日期与排序处理
            date_results = plan_df['版本单号'].apply(get_date_details)
            plan_df['计划发货时间'] = date_results.apply(lambda x: x[0])
            plan_df['_sort_key'] = date_results.apply(lambda x: x[1])
            plan_df = plan_df.sort_values(by='_sort_key', ascending=True)

            # 4. 初始化存储桶
            supplier_files_content = {}
            multi_suppliers_list = []
            no_match_list = []
            zero_stock_list = [] # 新增：Sheet3 桶

            # 5. 核心循环：前置筛选 + 匹配逻辑
            for _, row in plan_df.iterrows():
                current_row = row.copy()
                sku = str(current_row.get('SKU', '')).strip()
                
                # --- [新增前置筛选] 检查提货未入库数量 ---
                # 兼容处理：确保转换为数字，失败则默认为0
                unstocked_qty = pd.to_numeric(current_row.get('提货未入库数量', 0), errors='coerce')
                
                if unstocked_qty == 0:
                    current_row['供应商'] = "无需提货（数量为0）"
                    zero_stock_list.append(current_row.reindex(TARGET_HEADERS).fillna(""))
                    continue # 跳过后续供应商匹配逻辑，直接处理下一行

                # --- 正常匹配逻辑 ---
                suppliers = sku_supplier_map.get(sku, set())
                
                if not suppliers:
                    current_row['供应商'] = "该SKU已无在途订单"
                    no_match_list.append(current_row.reindex(TARGET_HEADERS).fillna(""))
                elif len(suppliers) > 1:
                    current_row['供应商'] = "、".join(list(suppliers))
                    multi_suppliers_list.append(current_row.reindex(TARGET_HEADERS).fillna(""))
                else:
                    supplier_name = list(suppliers)[0]
                    current_row['供应商'] = supplier_name
                    if supplier_name not in supplier_files_content:
                        supplier_files_content[supplier_name] = []
                    supplier_files_content[supplier_name].append(current_row.reindex(TARGET_HEADERS).fillna(""))

            # 6. 生成压缩包
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zf:
                
                # 写入供应商文件
                for sup_name, rows in supplier_files_content.items():
                    temp_df = pd.DataFrame(rows)
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        temp_df.to_excel(writer, index=False, columns=TARGET_HEADERS)
                    zf.writestr(f"{sup_name}.xlsx", output.getvalue())
                
                # 写入异常汇总文件 (含 Sheet1, Sheet2, Sheet3)
                err_output = io.BytesIO()
                with pd.ExcelWriter(err_output, engine='openpyxl') as writer:
                    if multi_suppliers_list:
                        pd.DataFrame(multi_suppliers_list).to_excel(writer, index=False, sheet_name="注意⚠️存在多个供应商")
                    if no_match_list:
                        pd.DataFrame(no_match_list).to_excel(writer, index=False, sheet_name="该SKU已无在途订单")
                    # [新增 Sheet3]
                    if zero_stock_list:
                        pd.DataFrame(zero_stock_list).to_excel(writer, index=False, sheet_name="提货未入库数量为0的数据")
                
                zf.writestr("异常情况汇总.xlsx", err_output.getvalue())

            st.success("✅ 处理完成！已自动按时间排序并剔除了 0 值数据。")
            st.download_button(
                label="📥 点击下载处理结果 (.zip)",
                data=zip_buffer.getvalue(),
                file_name=f"提货计划_{datetime.now().strftime('%m%d_%H%M')}.zip",
                mime="application/zip"
            )

    except Exception as e:
        st.error(f"❌ 运行失败：{str(e)}")
