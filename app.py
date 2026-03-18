import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import io
import zipfile

# 设置页面配置
st.set_page_config(page_title="跨境电商提货计划处理系统", layout="wide")

# --- 核心逻辑函数 ---

def get_date_details(version_code):
    """
    核心计算逻辑：
    1. 返回用于显示的“X月X日”
    2. 返回用于排序的 datetime 对象（若失败则返回一个遥远的未来日期，排在最后）
    """
    if pd.isna(version_code) or len(str(version_code)) < 10:
        return "❌", datetime(2099, 12, 31)
    try:
        code_str = str(version_code)
        # 根据需求：5-6位是年份，7-10位是MMDD
        year = int("20" + code_str[4:6])
        month = int(code_str[6:8])
        day = int(code_str[8:10])
        
        target_date = datetime(year, month, day)
        # 往前倒推5天
        result_date = target_date - timedelta(days=5)
        
        display_str = f"{result_date.month}月{result_date.day}日"
        return display_str, result_date
    except:
        return "❌", datetime(2099, 12, 31)

def read_file(uploaded_file):
    """自动识别格式并读取第一个 Sheet"""
    file_name = uploaded_file.name
    if file_name.endswith('.csv'):
        return pd.read_csv(uploaded_file)
    else:
        return pd.read_excel(uploaded_file, sheet_name=0)

# --- 页面 UI ---

st.title("📦 提货计划 - 自动分发系统 (时间升序优化版)")
st.markdown(f"**当前操作员**：{st.session_state.get('user_name', '曾倩文')} | **逻辑**：保留原始行 + 字段A-Q排序 + 发货时间升序")

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

if st.button("开始处理并排序", disabled=not (plan_file and order_file)):
    try:
        with st.spinner("正在计算日期并进行全局升序排列..."):
            # 1. 加载原始数据
            plan_df = read_file(plan_file)
            order_df = read_file(order_file)

            # 2. 预处理供应商匹配库 (处理多行但供应商一致的情况)
            sku_supplier_map = order_df.groupby('SKU')['供应商'].apply(
                lambda x: set(x.dropna().unique())
            ).to_dict()

            # 3. 处理日期计算与排序辅助列
            # 我们先在内存中计算出所有行的日期，方便后面排序
            date_results = plan_df['版本单号'].apply(get_date_details)
            plan_df['计划发货时间'] = date_results.apply(lambda x: x[0])
            plan_df['_sort_key'] = date_results.apply(lambda x: x[1])

            # --- 关键步骤：根据发货时间进行升序排列 ---
            plan_df = plan_df.sort_values(by='_sort_key', ascending=True)

            # 4. 数据分发逻辑
            supplier_files_content = {}
            multi_suppliers_list = []
            no_match_list = []

            for _, row in plan_df.iterrows():
                current_row = row.copy()
                sku = str(current_row.get('SKU', '')).strip()
                
                # 匹配供应商
                suppliers = sku_supplier_map.get(sku, set())
                
                if not suppliers:
                    current_row['供应商'] = "该SKU已无在途订单"
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

            # 5. 生成 ZIP
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zf:
                
                # 写入供应商文件 (由于 plan_df 已排序，这里 push 进去的顺序也是有序的)
                for sup_name, rows in supplier_files_content.items():
                    temp_df = pd.DataFrame(rows)
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        temp_df.to_excel(writer, index=False, columns=TARGET_HEADERS)
                    zf.writestr(f"{sup_name}.xlsx", output.getvalue())
                
                # 写入异常汇总文件
                err_output = io.BytesIO()
                with pd.ExcelWriter(err_output, engine='openpyxl') as writer:
                    if multi_suppliers_list:
                        pd.DataFrame(multi_suppliers_list).to_excel(writer, index=False, sheet_name="注意⚠️存在多个供应商")
                    if no_match_list:
                        pd.DataFrame(no_match_list).to_excel(writer, index=False, sheet_name="该SKU已无在途订单")
                zf.writestr("异常情况汇总.xlsx", err_output.getvalue())

            st.success("✅ 排序并分发成功！")
            st.download_button(
                label="📥 下载已按时间排序的结果 (.zip)",
                data=zip_buffer.getvalue(),
                file_name=f"提货计划_升序版_{datetime.now().strftime('%m%d')}.zip",
                mime="application/zip"
            )

    except Exception as e:
        st.error(f"❌ 运行出错：{str(e)}")
