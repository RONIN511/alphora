"""
ChatExcel API 服务器

提供 HTTP API 接口，支持文件上传和对话交互。

启动方式:
    uvicorn server:app --host 0.0.0.0 --port 8000

API 端点:
    POST /chat - 发送消息
    POST /upload - 上传文件
    GET /files - 列出文件
    DELETE /session - 清空会话
"""

import os
import uuid
import asyncio
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from alphora.sandbox import Sandbox, SandboxManager

from .main import ChatExcel


# ==================== 配置 ====================

class Config:
    """服务器配置"""
    SANDBOX_BASE_PATH = os.getenv("SANDBOX_BASE_PATH", "/tmp/chatexcel_sandboxes")
    SANDBOX_TIMEOUT = int(os.getenv("SANDBOX_TIMEOUT", "300"))
    SANDBOX_MEMORY_MB = int(os.getenv("SANDBOX_MEMORY_MB", "512"))
    BOCHA_API_KEY = os.getenv("BOCHA_API_KEY", "")
    MAX_SESSIONS = int(os.getenv("MAX_SESSIONS", "100"))
    SESSION_IDLE_TIMEOUT = int(os.getenv("SESSION_IDLE_TIMEOUT", "3600"))


# ==================== 会话管理 ====================

class SessionManager:
    """管理用户会话和沙箱"""
    
    def __init__(self):
        self.sandbox_manager: Optional[SandboxManager] = None
        self.sessions: Dict[str, ChatExcel] = {}
    
    async def initialize(self):
        """初始化沙箱管理器"""
        self.sandbox_manager = SandboxManager(
            base_path=Config.SANDBOX_BASE_PATH,
            max_sandboxes=Config.MAX_SESSIONS,
            auto_cleanup=True,
        )
        await self.sandbox_manager.start()
    
    async def shutdown(self):
        """关闭所有会话"""
        self.sessions.clear()
        if self.sandbox_manager:
            await self.sandbox_manager.shutdown()
    
    async def get_or_create_session(self, session_id: str) -> ChatExcel:
        """获取或创建会话"""
        if session_id in self.sessions:
            return self.sessions[session_id]
        
        # 创建新沙箱
        sandbox = await self.sandbox_manager.get_or_create(session_id)
        
        # 创建 ChatExcel 实例
        agent = ChatExcel(
            sandbox=sandbox,
            bocha_api_key=Config.BOCHA_API_KEY,
        )
        
        self.sessions[session_id] = agent
        return agent
    
    async def delete_session(self, session_id: str):
        """删除会话"""
        if session_id in self.sessions:
            del self.sessions[session_id]
        
        if self.sandbox_manager:
            await self.sandbox_manager.destroy_sandbox(session_id)
    
    def generate_session_id(self) -> str:
        """生成新的会话 ID"""
        return str(uuid.uuid4())


# 全局会话管理器
session_manager = SessionManager()


# ==================== FastAPI 应用 ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    await session_manager.initialize()
    yield
    await session_manager.shutdown()


app = FastAPI(
    title="ChatExcel API",
    description="Excel 数据分析智能体 API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== 请求/响应模型 ====================

class ChatRequest(BaseModel):
    """聊天请求"""
    message: str
    session_id: Optional[str] = None
    stream: bool = False


class ChatResponse(BaseModel):
    """聊天响应"""
    session_id: str
    response: str
    files: list = []


class UploadResponse(BaseModel):
    """上传响应"""
    session_id: str
    filename: str
    size: int
    message: str


# ==================== API 端点 ====================

@app.get("/")
async def root():
    """健康检查"""
    return {"status": "ok", "service": "ChatExcel API"}


@app.post("/session")
async def create_session():
    """创建新会话"""
    session_id = session_manager.generate_session_id()
    agent = await session_manager.get_or_create_session(session_id)
    
    return {
        "session_id": session_id,
        "welcome": agent.get_welcome_message()
    }


@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """删除会话"""
    await session_manager.delete_session(session_id)
    return {"status": "deleted", "session_id": session_id}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    发送聊天消息
    
    - **message**: 用户消息
    - **session_id**: 会话 ID（不传则创建新会话）
    - **stream**: 是否使用流式响应
    """
    # 获取或创建会话
    session_id = request.session_id or session_manager.generate_session_id()
    agent = await session_manager.get_or_create_session(session_id)
    
    # 流式响应
    if request.stream:
        async def generate():
            # TODO: 实现流式输出
            response = await agent.chat(request.message)
            yield f"data: {response}\n\n"
            yield "data: [DONE]\n\n"
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream"
        )
    
    # 普通响应
    response = await agent.chat(request.message)
    
    # 获取生成的文件列表
    files = []
    try:
        file_list = await agent.sandbox.list_files()
        files = [{"name": f.name, "size": f.size} for f in file_list]
    except Exception:
        pass
    
    return ChatResponse(
        session_id=session_id,
        response=response,
        files=files,
    )


@app.post("/upload", response_model=UploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    session_id: Optional[str] = None,
):
    """
    上传文件到会话沙箱
    
    - **file**: 要上传的文件
    - **session_id**: 会话 ID（不传则创建新会话）
    """
    # 获取或创建会话
    session_id = session_id or session_manager.generate_session_id()
    agent = await session_manager.get_or_create_session(session_id)
    
    # 读取文件内容
    content = await file.read()
    
    # 写入沙箱
    await agent.sandbox.write_file_bytes(file.filename, content)
    
    return UploadResponse(
        session_id=session_id,
        filename=file.filename,
        size=len(content),
        message=f"文件 '{file.filename}' 上传成功",
    )


@app.get("/files/{session_id}")
async def list_files(session_id: str):
    """列出会话中的文件"""
    if session_id not in session_manager.sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    agent = session_manager.sessions[session_id]
    
    try:
        files = await agent.sandbox.list_files()
        return {
            "session_id": session_id,
            "files": [
                {
                    "name": f.name,
                    "size": f.size,
                    "size_human": f.size_human,
                }
                for f in files
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/download/{session_id}/{filename}")
async def download_file(session_id: str, filename: str):
    """下载会话中的文件"""
    if session_id not in session_manager.sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    agent = session_manager.sessions[session_id]
    
    try:
        content = await agent.sandbox.download_file(filename)
        
        # 确定 MIME 类型
        ext = os.path.splitext(filename)[1].lower()
        mime_types = {
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.xls': 'application/vnd.ms-excel',
            '.csv': 'text/csv',
            '.pdf': 'application/pdf',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
        }
        media_type = mime_types.get(ext, 'application/octet-stream')
        
        return StreamingResponse(
            iter([content]),
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"File not found: {str(e)}")


# ==================== 运行入口 ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
