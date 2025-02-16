import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import json
import os
import re
import boto3
from auth import init_auth, login_required
import io

# 设置页面配置
st.set_page_config(
    page_title="Bella x Nemo's Financial",
    layout="wide"
)

# S3 配置
S3_BUCKET = st.secrets["aws"]["bucket_name"]
s3_client = boto3.client('s3',
    region_name=st.secrets["aws"]["region"],
    aws_access_key_id=st.secrets["aws"]["access_key_id"],
    aws_secret_access_key=st.secrets["aws"]["secret_access_key"]
)

# 使用 Streamlit 的会话状态来存储数据
if 'transactions_df' not in st.session_state:
    st.session_state.transactions_df = None
if 'categories' not in st.session_state:
    st.session_state.categories = [
        "Bills & Utilities",
        "Food & Drink",
        "Shopping",
        "Travel",
        "Groceries",
        "Home",
        "Professional Services",
        "Health & Wellness",
        "Gas",
        "Automotive",
        "Entertainment",
        "Fees & Adjustments",
        "Education",
        "Miscellaneous"
    ]
if 'category_rules' not in st.session_state:
    st.session_state.category_rules = {}

def download_from_s3():
    """从 S3 下载数据到内存"""
    try:
        # 下载交易数据
        response = s3_client.get_object(Bucket=S3_BUCKET, Key="all_transactions.csv")
        st.session_state.transactions_df = pd.read_csv(io.StringIO(response['Body'].read().decode('utf-8')))
        st.session_state.transactions_df['Date'] = pd.to_datetime(st.session_state.transactions_df['Date'])
        if 'Memo' not in st.session_state.transactions_df.columns:
            st.session_state.transactions_df['Memo'] = ''
        st.session_state.transactions_df['Memo'] = st.session_state.transactions_df['Memo'].fillna('').astype(str)

        # 下载分类数据
        response = s3_client.get_object(Bucket=S3_BUCKET, Key="categories.json")
        st.session_state.categories = json.loads(response['Body'].read().decode('utf-8'))

        # 下载规则数据
        response = s3_client.get_object(Bucket=S3_BUCKET, Key="category_rules.json")
        st.session_state.category_rules = json.loads(response['Body'].read().decode('utf-8'))

        st.success("成功从云端同步数据！")
        return True
    except Exception as e:
        st.error(f"从云端同步数据失败: {str(e)}")
        return False

def upload_to_s3():
    """将内存中的数据上传到 S3"""
    try:
        # 上传交易数据
        csv_buffer = io.StringIO()
        st.session_state.transactions_df.to_csv(csv_buffer, index=False)
        s3_client.put_object(Bucket=S3_BUCKET, Key="all_transactions.csv", Body=csv_buffer.getvalue())

        # 上传分类数据
        categories_json = json.dumps(st.session_state.categories, indent=4)
        s3_client.put_object(Bucket=S3_BUCKET, Key="categories.json", Body=categories_json)

        # 上传规则数据
        rules_json = json.dumps(st.session_state.category_rules, indent=4)
        s3_client.put_object(Bucket=S3_BUCKET, Key="category_rules.json", Body=rules_json)

        st.success("成功将更改同步到云端！")
        return True
    except Exception as e:
        st.error(f"同步到云端失败: {str(e)}")
        return False

def apply_category_rules(df, rules):
    """应用分类规则到数据框"""
    for description, rule_info in rules.items():
        category = rule_info['category'] if isinstance(rule_info, dict) else rule_info
        escaped_description = re.escape(description)
        mask = df['Description'].str.contains(escaped_description, case=False, na=False, regex=True)
        df.loc[mask, 'Category'] = category
    return df

def check_missing_rules(df, rules):
    """检查缺失规则的交易"""
    unique_descriptions = df['Description'].unique()
    missing_rules = []
    for desc in unique_descriptions:
        rule_found = False
        for rule_desc in rules.keys():
            if rule_desc in desc or desc in rule_desc:
                rule_found = True
                break
        if not rule_found:
            missing_rules.append({
                'Description': desc,
                'Category': df[df['Description'] == desc]['Category'].iloc[0],
                'Count': len(df[df['Description'] == desc])
            })
    return missing_rules

def show_rules_management(rules, on_rule_update, df=None):
    """显示规则管理界面"""
    st.subheader("分类规则管理")
    
    # 添加分类管理部分
    with st.expander("分类管理"):
        # 显示当前所有分类
        st.write("当前分类列表：")
        categories_df = pd.DataFrame({
            "Category": st.session_state.categories,
            "Delete": [False] * len(st.session_state.categories)
        })
        
        edited_categories = st.data_editor(
            categories_df,
            column_config={
                "Category": st.column_config.TextColumn(
                    "分类名称",
                    help="点击编辑以修改分类名称"
                ),
                "Delete": st.column_config.CheckboxColumn(
                    "删除",
                    help="选中要删除的分类"
                )
            },
            hide_index=True,
            use_container_width=True,
            num_rows="dynamic"  # 允许添加新行
        )
        
        if st.button("保存分类更改"):
            # 获取未标记删除的分类，处理 None 值
            edited_categories['Delete'] = edited_categories['Delete'].fillna(False)
            
            # 找出被删除的分类
            deleted_categories = edited_categories[edited_categories['Delete']]['Category'].tolist()
            
            # 获取保留的分类
            new_categories = edited_categories[~edited_categories['Delete']]['Category'].tolist()
            # 过滤掉空值
            new_categories = [cat for cat in new_categories if pd.notna(cat) and cat.strip() != '']
            
            # 如果有分类被删除，更新交易数据
            if deleted_categories and df is not None:
                # 将使用被删除分类的交易的分类设置为空
                for category in deleted_categories:
                    df.loc[df['Category'] == category, 'Category'] = ''
                st.session_state.transactions_df = df
                
                # 同时更新规则中的分类
                rules_updated = False
                for desc, rule_info in rules.items():
                    category = rule_info['category'] if isinstance(rule_info, dict) else rule_info
                    if category in deleted_categories:
                        if isinstance(rule_info, dict):
                            rules[desc]['category'] = ''
                        else:
                            rules[desc] = ''
                        rules_updated = True
                
                if rules_updated:
                    on_rule_update(rules)
            
            # 更新分类
            st.session_state.categories = new_categories
            st.success("分类更改已保存！所有使用已删除分类的交易已被清空。")
            st.rerun()
    
    st.divider()  # 添加分隔线
    
    # 如果提供了交易数据，检查缺失的规则
    if df is not None:
        missing_rules = check_missing_rules(df, rules)
        if missing_rules:
            st.warning(f"发现 {len(missing_rules)} 个没有对应规则的交易描述")
            missing_df = pd.DataFrame(missing_rules)
            st.write("缺失规则的交易：")
            edited_missing_df = st.data_editor(
                missing_df,
                column_config={
                    "Description": st.column_config.TextColumn(
                        "描述",
                        disabled=True,
                    ),
                    "Category": st.column_config.SelectboxColumn(
                        "当前分类",
                        options=st.session_state.categories,
                        required=True
                    ),
                    "Count": st.column_config.NumberColumn(
                        "出现次数",
                        disabled=True
                    )
                },
                hide_index=True,
                use_container_width=True,
                key="missing_rules_editor"
            )
            
            # 显示选中要添加规则的按钮
            if st.button("为这些交易添加规则"):
                # 首先更新交易分类
                changes_made = False
                for _, row in edited_missing_df.iterrows():
                    original_category = df[df['Description'] == row['Description']]['Category'].iloc[0]
                    if original_category != row['Category']:
                        # 更新数据框中的分类
                        df.loc[df['Description'] == row['Description'], 'Category'] = row['Category']
                        changes_made = True
                
                if changes_made:
                    st.session_state.transactions_df = df
                
                # 然后添加规则
                new_rules = rules.copy()  # 创建规则的副本
                for _, row in edited_missing_df.iterrows():
                    new_rules[row['Description']] = {
                        'category': row['Category'],
                        'last_modified': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                on_rule_update(new_rules)  # 使用on_rule_update而不是直接保存
                st.success("已更新交易分类并添加规则！")
                st.rerun()
    
    # 转换规则为DataFrame，包含修改时间，并过滤掉无效规则
    rules_data = []
    for desc, rule_info in rules.items():
        if isinstance(rule_info, dict):
            rules_data.append({
                'Description': desc,
                'Category': rule_info['category'],
                'Last Modified': rule_info['last_modified'],
                'Delete': False  # 添加删除列
            })
        else:
            # 处理旧格式的规则
            rules_data.append({
                'Description': desc,
                'Category': rule_info,
                'Last Modified': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'Delete': False  # 添加删除列
            })
    
    rules_df = pd.DataFrame(rules_data).sort_values('Last Modified', ascending=False).reset_index(drop=True)

    # 添加搜索框
    search_term = st.text_input("搜索描述", key="rules_search")
    
    # 保存完整的规则DataFrame的副本
    full_rules_df = rules_df.copy()
    
    # 应用搜索过滤
    if search_term:
        rules_df = rules_df[rules_df['Description'].str.contains(search_term, case=False, na=False)].reset_index(drop=True)

    # 添加分类过滤
    selected_categories = st.multiselect(
        "按分类筛选",
        options=['全部'] + st.session_state.categories,
        default=['全部'],
        key="rules_category_filter"
    )
    if '全部' not in selected_categories:
        rules_df = rules_df[rules_df['Category'].isin(selected_categories)].reset_index(drop=True)
    
    # 在规则表格前显示行数
    if '全部' in selected_categories:
        empty_rules = len(rules_df[rules_df['Category'] == ''])
        misc_rules = len(rules_df[rules_df['Category'] == 'Miscellaneous'])
        st.write(f"总共 {len(rules_df)} 条规则，其中 {misc_rules} 条是 Miscellaneous，{empty_rules} 条没有分类")
    else:
        st.write(f"总共 {len(rules_df)} 条规则")
    
    edited_rules = st.data_editor(
        rules_df,
        column_config={
            "Description": st.column_config.TextColumn(
                "Description",
                disabled=True,
            ),
            "Category": st.column_config.SelectboxColumn(
                "Category",
                options=st.session_state.categories,
                required=True
            ),
            "Last Modified": st.column_config.TextColumn(
                "Last Modified",
                disabled=True
            ),
            "Delete": st.column_config.CheckboxColumn(
                "删除",
                help="选中要删除的规则"
            )
        },
        hide_index=True,
        use_container_width=True,
        disabled=["Description", "Last Modified"],
        key="rules_editor",
        num_rows="fixed"
    )
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("更新规则"):
            # 创建一个新的规则字典，基于原始规则
            new_rules = rules.copy()
            
            # 处理编辑器中的规则
            for _, row in edited_rules.iterrows():
                description = row['Description']
                if row['Delete']:  # 如果规则被标记为删除
                    if description in new_rules:
                        del new_rules[description]
                else:
                    new_category = row['Category']
                    # 检查规则是否存在且category是否改变
                    if description in new_rules:
                        old_category = new_rules[description]['category'] if isinstance(new_rules[description], dict) else new_rules[description]
                        if new_category != old_category:
                            # 只在category改变时更新last_modified
                            new_rules[description] = {
                                'category': new_category,
                                'last_modified': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            }
                        # 如果category没有改变，保持原样
                    else:
                        # 如果是新规则
                        new_rules[description] = {
                            'category': new_category,
                            'last_modified': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }
            
            # 更新规则
            on_rule_update(new_rules)
            
            # 如果提供了数据框，立即应用规则
            if df is not None:
                df = apply_category_rules(df, new_rules)
                st.session_state.transactions_df = df
                st.success("规则已更新并应用到所有交易！")
                st.rerun()
            else:
                st.success("规则已更新！")
    
    with col2:
        # 显示选中要删除的规则数量
        to_delete = edited_rules['Delete'].sum()
        if to_delete > 0:
            st.info(f"已选中 {to_delete} 条规则待删除")

@login_required
def main():
    st.title("Bella x Nemo's Financial")
    
    # 如果没有数据，从云端加载
    if st.session_state.transactions_df is None:
        st.info("正在从云端同步数据...")
        if not download_from_s3():
            st.error("无法从云端获取数据，请检查网络连接或联系管理员。")
            return
    
    # 添加同步按钮
    col1, col2 = st.columns(2)
    with col1:
        if st.button("从云端同步数据 (覆盖本地更改)"):
            if download_from_s3():
                st.rerun()
    
    with col2:
        if st.button("将本地更改同步到云端"):
            upload_to_s3()
    
    # 使用会话状态中的数据
    df = st.session_state.transactions_df
    if df is None:
        return
    
    # 创建标签页
    tab1, tab2 = st.tabs(["交易管理", "规则管理"])
    
    with tab1:
        # 交易列表部分
        st.subheader("交易列表")
        
        # 筛选选项
        filter_container = st.container()
        with filter_container:
            # 第一行筛选器
            col_search, col_date, col_month = st.columns(3)
            
            with col_search:
                search_term = st.text_input("搜索描述", "")
            
            with col_date:
                date_range = st.date_input(
                    "日期范围",
                    value=(df['Date'].min(), df['Date'].max()),
                    min_value=df['Date'].min().date(),
                    max_value=df['Date'].max().date()
                )

            with col_month:
                all_months = sorted(df['Month'].unique())
                selected_months = st.multiselect(
                    "月份",
                    options=['全部'] + list(all_months),
                    default=['全部']
                )                

            # 第二行筛选器
            col_card, col_category, col_amount = st.columns(3)

            with col_card:
                selected_card = st.multiselect(
                    "Card",
                    options=['全部'] + list(df['Card'].unique()),
                    default=['全部']
                )

            with col_category:
                selected_categories = st.multiselect(
                    "分类",
                    options=['全部'] + st.session_state.categories,
                    default=['全部']
                )
            
            with col_amount:
                amount_range = st.slider(
                    "金额范围 ($)",
                    min_value=float(df['Amount'].min()),
                    max_value=float(df['Amount'].max()),
                    value=(float(df['Amount'].min()), float(df['Amount'].max())),
                    format="$%.2f"
                )
            
            # 第三行筛选器 - 交易类型
            col_type = st.columns(3)[0]  # 只使用第一列
            with col_type:
                transaction_type = st.radio(
                    "交易类型",
                    options=['全部', '支出 (正数)', '收入 (负数)'],
                    horizontal=True
                )
            
            # 第四行筛选器 - 货币类型
            col_currency = st.columns(3)[0]  # 只使用第一列
            with col_currency:
                selected_currency = st.radio(
                    "货币类型",
                    options=['全部'] + list(df['Currency'].unique()),
                    horizontal=True
                )
        
        # 应用筛选
        filtered_df = df.copy()
        
        # 描述搜索筛选
        if search_term:
            filtered_df = filtered_df[filtered_df['Description'].str.contains(search_term, case=False, na=False)]
        
        # 日期范围筛选
        if len(date_range) == 2:
            filtered_df = filtered_df[
                (filtered_df['Date'].dt.date >= date_range[0]) &
                (filtered_df['Date'].dt.date <= date_range[1])
            ]
        
        # 信用卡筛选
        if '全部' not in selected_card:
            filtered_df = filtered_df[filtered_df['Card'].isin(selected_card)]
        
        # 分类筛选
        if '全部' not in selected_categories:
            filtered_df = filtered_df[filtered_df['Category'].isin(selected_categories)]
        
        # 金额范围筛选
        filtered_df = filtered_df[
            (filtered_df['Amount'] >= amount_range[0]) &
            (filtered_df['Amount'] <= amount_range[1])
        ]

        # 货币筛选
        if selected_currency != '全部':
            filtered_df = filtered_df[filtered_df['Currency'] == selected_currency]
        
        # 月份筛选
        if '全部' not in selected_months:
            filtered_df = filtered_df[filtered_df['Month'].isin(selected_months)]
        
        # 交易类型筛选
        if transaction_type == '支出 (正数)':
            filtered_df = filtered_df[filtered_df['Amount'] > 0]
        elif transaction_type == '收入 (负数)':
            filtered_df = filtered_df[filtered_df['Amount'] < 0]
        
        # 显示交易列表
        filtered_df = filtered_df.reset_index(drop=True)
        # 确保 Memo 列是字符串类型
        filtered_df['Memo'] = filtered_df['Memo'].fillna('').astype(str)
        st.write(f"显示 {len(filtered_df)} 条交易")
        edited_df = st.data_editor(
            filtered_df,
            column_config={
                "Date": st.column_config.DateColumn("Date", disabled=True),
                "Description": st.column_config.TextColumn("Description", disabled=True),
                "Amount": st.column_config.NumberColumn("Amount", format="$%.2f", disabled=True),
                "Currency": st.column_config.TextColumn(
                    "Currency",
                    disabled=True,
                    help="交易货币"
                ),                
                "Category": st.column_config.TextColumn(
                    "Category",
                    disabled=True,
                    help="要修改分类请到规则管理页面"
                ),
                "Card": st.column_config.TextColumn("Card", disabled=True),
                "Month": st.column_config.TextColumn("Month", disabled=True),
                "Type": st.column_config.TextColumn("Type", disabled=True),
                "Memo": st.column_config.TextColumn(
                    "Memo",
                    help="可以在这里添加备注信息",
                    default=""
                )
            },
            hide_index=True,
            use_container_width=True,
            num_rows="fixed",
            disabled=["Date", "Description", "Amount", "Currency", "Amount_USD", "Card", "Month", "Type", "Category"]
        )
        
        col_save = st.columns(2)[0]
        with col_save:
            if st.button("保存更改"):
                # 获取编辑后的数据框中已更改的行
                changed_rows = edited_df[edited_df['Memo'] != df.loc[edited_df.index, 'Memo']]
                
                if not changed_rows.empty:
                    # 更新原始数据框中对应的行
                    for idx in changed_rows.index:
                        df.loc[idx, 'Memo'] = changed_rows.loc[idx, 'Memo']
                    
                    # 保存更改到会话状态
                    st.session_state.transactions_df = df
                    st.success(f"成功更新了 {len(changed_rows)} 条交易的备注！")
                    st.rerun()
                else:
                    st.info("没有检测到任何更改。")

        # 分类统计部分
        st.divider()  # 添加分隔线
        st.subheader("分类统计")
        
        # 创建两列布局用于统计展示
        stat_col1, stat_col2 = st.columns([1, 1])
        
        with stat_col1:
            # 显示饼图 - 按分类的支出分布
            category_spending = edited_df.groupby('Category')['Amount'].sum().reset_index()
            fig_category = px.pie(
                category_spending,
                values='Amount',
                names='Category',
                title='支出分类分布'
            )
            st.plotly_chart(fig_category, use_container_width=True)
        
        with stat_col2:
            # 合并金额和交易次数统计
            amount_stats = edited_df.groupby('Category')['Amount'].agg(['sum', 'count']).reset_index()
            amount_stats.columns = ['Category', 'Total Amount', 'Transaction Count']
            amount_stats = amount_stats.sort_values('Total Amount', ascending=False)
            
            st.write("分类统计详情")
            st.dataframe(
                amount_stats,
                column_config={
                    "Total Amount": st.column_config.NumberColumn("Total Amount", format="$%.2f"),
                    "Transaction Count": st.column_config.NumberColumn("Count", format="%d")
                },
                hide_index=True,
                use_container_width=True
            )

        # 添加每月各类别支出的堆叠柱状图
        st.divider()
        st.subheader("月度分类支出分析")
        
        # 计算每月每个类别的支出
        monthly_category_spending = edited_df.pivot_table(
            index='Month',
            columns='Category',
            values='Amount',
            aggfunc='sum'
        ).fillna(0).reset_index()
        
        # 创建堆叠柱状图
        fig_monthly_category = px.bar(
            monthly_category_spending,
            x='Month',
            y=monthly_category_spending.columns[1:],  # 除了Month的所有列
            title='月度分类支出趋势',
            labels={'value': '支出金额 ($)', 'Month': '月份', 'variable': '分类'},
            barmode='stack'
        )
        fig_monthly_category.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig_monthly_category, use_container_width=True)

        # 添加按信用卡的支出分布
        st.divider()
        st.subheader("信用卡使用分析")
        
        card_col1, card_col2 = st.columns([1, 1])
        
        with card_col1:
            # 按信用卡的支出饼图
            card_spending = edited_df.groupby('Card')['Amount'].sum().reset_index()
            fig_card = px.pie(
                card_spending,
                values='Amount',
                names='Card',
                title='各信用卡支出占比'
            )
            st.plotly_chart(fig_card, use_container_width=True)
        
        with card_col2:
            # 信用卡使用统计
            card_stats = edited_df.groupby('Card').agg({
                'Amount': ['sum', 'count', 'mean']
            }).reset_index()
            card_stats.columns = ['Card', 'Total Amount', 'Transaction Count', 'Average Amount']
            card_stats = card_stats.sort_values('Total Amount', ascending=False)
            
            st.write("信用卡使用详情")
            st.dataframe(
                card_stats,
                column_config={
                    "Total Amount": st.column_config.NumberColumn("Total Amount", format="$%.2f"),
                    "Transaction Count": st.column_config.NumberColumn("Count", format="%d"),
                    "Average Amount": st.column_config.NumberColumn("Avg Amount", format="$%.2f")
                },
                hide_index=True,
                use_container_width=True
            )

    with tab2:
        show_rules_management(st.session_state.category_rules, lambda new_rules: st.session_state.category_rules.update(new_rules), df)

if __name__ == "__main__":
    # 初始化认证系统
    if init_auth():
        main() 