# ChatExcel

**基于 Alphora 框架的 Excel 数据分析智能体示例**

ChatExcel 是一个完整的 AI 数据分析助手示例，展示了如何使用 Alphora 框架和 alphora_community 社区组件构建功能丰富的智能体应用。

## ✨ 特性

- 📊 **数据查看** - 预览 Excel/CSV 文件内容、结构、统计信息
- 📈 **数据分析** - 使用 Python 进行数据处理、统计分析、可视化
- 🔍 **联网搜索** - 搜索最新信息辅助分析
- 📝 **文件生成** - 生成分析报告、处理后的数据文件
- 💬 **多轮对话** - 支持上下文记忆和历史压缩
- 🔧 **自动修复** - 代码执行失败时自动分析并修复

## 🚀 快速开始

### 安装依赖

```bash
pip install alphora
pip install fastapi uvicorn  # API 服务需要
```

### 方式 1: 编程调用

```python
import asyncio
from chatexcel import ChatExcel
from alphora.sandbox import Sandbox

async def main():
    # 创建沙箱和 Agent
    async with Sandbox.create_local() as sandbox:
        agent = ChatExcel(sandbox=sandbox)
        
        # 上传文件
        with open("sales.xlsx", "rb") as f:
            await sandbox.write_file_bytes("sales.xlsx", f.read())
        
        # 开始对话
        print(agent.get_welcome_message())
        
        # 查看数据结构
        response = await agent.chat("查看 sales.xlsx 的数据结构")
        print(response)
        
        # 分析数据
        response = await agent.chat("按月份统计销售额，并生成柱状图")
        print(response)

asyncio.run(main())
```

### 方式 2: API 服务

```bash
# 启动服务
uvicorn chatexcel.server:app --host 0.0.0.0 --port 8000
```

API 调用示例：

```bash
# 创建会话
curl -X POST http://localhost:8000/session

# 上传文件
curl -X POST http://localhost:8000/upload \
    -F "file=@sales.xlsx" \
    -F "session_id=your-session-id"

# 发送消息
curl -X POST http://localhost:8000/chat \
    -H "Content-Type: application/json" \
    -d '{
        "session_id": "your-session-id",
        "message": "分析这个销售数据"
    }'

# 下载生成的文件
curl http://localhost:8000/download/your-session-id/result.xlsx -o result.xlsx
```

## 📁 项目结构

```
chatexcel/
├── __init__.py      # 包入口
├── main.py          # ChatExcel Agent 主类
├── server.py        # FastAPI 服务器
├── config.yaml      # 配置文件
├── prompts/         # 提示词模块
│   ├── __init__.py
│   └── excel_qa.py  # 业务提示词
└── README.md        # 本文档
```

## 🔧 配置

### 环境变量

```bash
# LLM 配置
export OPENAI_API_KEY="sk-xxx"
# 或
export ANTHROPIC_API_KEY="sk-ant-xxx"

# 联网搜索（可选）
export BOCHA_API_KEY="your-bocha-api-key"

# 沙箱配置
export SANDBOX_BASE_PATH="/tmp/chatexcel"
export SANDBOX_TIMEOUT=300
export SANDBOX_MEMORY_MB=512
```

### 配置文件

编辑 `config.yaml` 自定义配置，包括：
- 沙箱后端（local/docker）
- 资源限制
- LLM 模型选择
- 服务器参数

## 🧩 依赖的社区组件

ChatExcel 使用了以下 alphora_community 组件：

| 组件 | 用途 |
|------|------|
| `python_coder` | 代码生成、执行、自动修复 |
| `file_viewer` | 多格式文件查看 |
| `internet_search` | 博查 API 联网搜索 |
| `memory_manager` | 长对话历史压缩 |

## 📖 使用示例

### 基础数据查看

```
用户: 查看 data.xlsx 的结构
助手: [调用 view_file 工具，显示文件结构信息]
```

### 数据分析

```
用户: 计算每个城市的销售总额，按降序排列
助手: [调用 execute_python_task，生成并执行分析代码]
```

### 生成可视化

```
用户: 把上面的结果做成柱状图
助手: [执行代码生成图表，保存为图片文件]
```

### 联网搜索

```
用户: 搜索一下最新的电商行业趋势报告
助手: [调用 search_internet 工具获取最新信息]
```

## 🔒 安全说明

- 代码在隔离的沙箱环境中执行
- 支持 Docker 容器级别隔离
- 可配置资源限制（CPU、内存、超时）
- 危险操作（如 os.system）被阻止

## 📝 License

MIT License
