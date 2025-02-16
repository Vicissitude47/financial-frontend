# Personal Financial Management System

一个基于 Streamlit 的个人财务管理系统，用于追踪和分析信用卡消费。

## 功能特点

### 1. 交易管理
- 导入并显示信用卡交易记录
- 支持多种筛选方式：
  - 日期范围
  - 信用卡类型
  - 交易分类
  - 金额范围
  - 月份
  - 交易类型（支出/收入）
- 实时更新交易分类
- 自动保存修改

### 2. 规则管理
- 智能分类规则系统
- 规则搜索和筛选
- 批量规则更新
- 自动检测缺失规则
- 一键添加缺失规则

### 3. 数据分析
- 分类支出统计
- 可视化支出分布（饼图）
- 实时更新统计数据

## 安装说明

1. 克隆仓库：
```bash
git clone [repository-url]
```

2. 安装依赖：
```bash
pip install -r requirements.txt
```

## 目录结构
```
Financial/
├── transaction_manager.py   # 主程序
├── requirements.txt         # 依赖文件
├── Tests/                   # 测试目录
│   └── test_transaction_manager.py
├── Output/                  # 输出目录
│   ├── all_transactions.csv
│   └── category_rules.json
└── Source/                  # 源数据目录
    └── [信用卡交易数据文件]
```

## 使用说明

1. 启动应用：
```bash
cd financial-frontend
.\venv\Scripts\activate
streamlit run transaction_manager.py
```

2. 数据导入：
   - 将信用卡交易数据文件放入 `Source` 目录
   - 支持的信用卡：
     - Chase Sapphire
     - Chase Prime
     - Capital One
     - Amex Platinum
     - Amex Marriott

3. 交易管理：
   - 使用各种筛选器查找特定交易
   - 点击交易记录修改分类
   - 点击"保存更改"保存修改
   - 点击"应用现有规则"应用分类规则

4. 规则管理：
   - 在规则管理标签页查看和编辑规则
   - 使用搜索框查找特定规则
   - 使用分类筛选器筛选规则
   - 检查并添加缺失的规则

## 默认分类
- Bills & Utilities
- Food & Drink
- Shopping
- Travel
- Groceries
- Home
- Professional Services
- Health & Wellness
- Gas
- Automotive
- Entertainment
- Fees & Adjustments
- Education
- Miscellaneous

## 开发说明

### 运行测试
```bash
cd Tests
python test_transaction_manager.py -v
```

测试覆盖以下场景：
- 基本规则应用
- 大小写不敏感匹配
- 部分文本匹配
- 特殊字符处理
- 默认分类验证

## 贡献指南
1. Fork 项目
2. 创建功能分支
3. 提交更改
4. 推送到分支
5. 创建 Pull Request

## 许可证
[许可证类型] 