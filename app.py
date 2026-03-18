import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import io
import zipfile

# 设置页面配置
st.set_page_config(page_title="跨境电商提货计划处理系统", layout="wide")

# --- 核心逻辑函数 ---

def calculate_delivery_date(version_code):
    """
    计算计划发货时间：从第5-6位取年份，7-10位取月日，倒推5天
    """
    if pd.isna(version_code) or len(str(version_code)) < 10:
        return "❌"
    try:
        code_str = str(version_code)
        year = int("20" + code_str[4:6])
        month = int(code_str[6:8])
        day = int(code_str[8:10])
        
        target_date = datetime(year, month, day)
        result_date = target_date - timedelta(days=5)
        return f"{result_date.month}月{result_date.day}日"
    except:
        return "❌"

def read_file(uploaded_file):
    """
    自动识别格式并读取第一个 Sheet
    """
    file_name = uploaded_file.name
    if file_name.endswith('.csv'):
        return pd.read_csv(uploaded_file)
    else:
        # 默认读取第一个 sheet
        return pd.read_excel(uploaded_file, sheet_name=0)

# --- 页面 UI ---

st.title("📦 提货计划 - 供应商自动分发系统 (Streamlit版)")
st.info("逻辑确认：保留提货计划表所有行；按供应商拆分文件；字段顺序严格按 A-Q 排列。")

col1, col2 = st.columns(2)
with col1:
    plan_file = st.file_uploader("1. 上传：提货计划表 (必填)", type=['xlsx', 'xls', 'csv'])
with col2:
    order_file = st.file_uploader("2. 上传：采购订单追踪表 (必填)", type=['xlsx', 'xls', 'csv'])

# 定义目标字段顺序（严格按照截图 A-Q）
TARGET_HEADERS = [
    "单据编号", "版本单号", "国家", "SKU", "SKU名称", 
    "FNSKU", "供应商", "装箱数", "订单状态", "提货数量", 
    "已关联送货数量", "提货未入库数量", "已入库数量", 
    "关联送货单", "提货状态", "计划备注", "计划发货时间"
]

if st.button("开始处理数据", disabled=not (plan_file and order_file)):
    try:
        with st.spinner("正在处理逻辑并生成文件..."):
            # 1. 加载数据
            plan_df = read_file(plan_file)
            order_df = read_file(order_file)

            # 2. 预处理供应商匹配库 (处理多行但供应商一致的情况)
            # 按 SKU 分组，获取每个 SKU 对应的唯一供应商集合
            sku_supplier_map = order_df.groupby('SKU')['供应商'].apply(
                lambda x: set(x.dropna().unique())
            ).to_dict()

            # 3. 处理主逻辑
            results_all = []
            
            # 记录异常数据
            multi_suppliers_list = []
            no_match_list = []
            
            # 供应商分类存储
            supplier_files_content = {}

            for index, row in plan_df.iterrows():
                # 复制原始行数据，防止污染原 df
                current_row = row.copy()
                
                sku = str(current_row.get('SKU', '')).strip()
                version = current_row.get('版本单号', '')
                
                # 计算新字段
                current_row['计划发货时间'] = calculate_delivery_date(version)
                
                # 获取匹配的供应商集合
                suppliers = sku_supplier_map.get(sku, set())
                
                if not suppliers:
                    current_row['供应商'] = "该SKU已无在途订单"
                    # 只提取目标字段并按顺序排列
                    ordered_row = current_row.reindex(TARGET_HEADERS).fillna("")
                    no_match_list.append(ordered_row)
                elif len(suppliers) > 1:
                    current_row['供应商'] = "、".join(list(suppliers))
                    ordered_row = current_row.reindex(TARGET_HEADERS).fillna("")
                    multi_suppliers_list.append(ordered_row)
                else:
                    supplier_name = list(suppliers)[0]
                    current_row['供应商'] = supplier_name
                    ordered_row = current_row.reindex(TARGET_HEADERS).fillna("")
                    
                    if supplier_name not in supplier_files_content:
                        supplier_files_content[supplier_name] = []
                    supplier_files_content[supplier_name].append(ordered_row)

            # 4. 生成 ZIP
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zf:
                
                # A. 写入正常供应商文件
                for sup_name, rows in supplier_files_content.items():
                    temp_df = pd.DataFrame(rows)
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        temp_df.to_excel(writer, index=False, columns=TARGET_HEADERS)
                    zf.writestr(f"{sup_name}.xlsx", output.getvalue())
                
                # B. 写入异常汇总文件
                err_output = io.BytesIO()
                with pd.ExcelWriter(err_output, engine='openpyxl') as writer:
                    if multi_suppliers_list:
                        pd.DataFrame(multi_suppliers_list).to_excel(writer, index=False, sheet_name="注意⚠️存在多个供应商", columns=TARGET_HEADERS)
                    if no_match_list:
                        pd.DataFrame(no_match_list).to_excel(writer, index=False, sheet_name="该SKU已无在途订单", columns=TARGET_HEADERS)
                zf.writestr("异常情况汇总.xlsx", err_output.getvalue())

            # 5. 提供下载
            st.success("✅ 数据处理成功！")
            st.download_button(
                label="📥 点击下载结果压缩包 (ZIP)",
                data=zip_buffer.getvalue(),
                file_name=f"处理结果_{datetime.now().strftime('%m%d_%H%M')}.zip",
                mime="application/zip"
            )

    except Exception as e:
        st.error(f"❌ 程序运行出错：{str(e)}")
        st.write("请检查 Excel 字段名是否与需求严格一致。")
