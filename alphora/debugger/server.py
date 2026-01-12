"""
Alphora Debugger - Web 服务器
"""

import asyncio
import threading
import time
from typing import Optional

HAS_FASTAPI = False

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException
    from fastapi.responses import HTMLResponse
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn
    HAS_FASTAPI = True
except ImportError:
    pass

import logging
logger = logging.getLogger(__name__)

_server_thread: Optional[threading.Thread] = None


def start_server_background(port: int = 9527):
    """在后台启动服务器"""
    global _server_thread

    if not HAS_FASTAPI:
        raise ImportError("需要安装: pip install fastapi uvicorn")

    if _server_thread and _server_thread.is_alive():
        return

    def run():
        from .tracer import tracer

        app = FastAPI(title="Alphora Debugger")
        app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

        @app.get("/", response_class=HTMLResponse)
        async def dashboard():
            return DASHBOARD_HTML

        @app.get("/api/status")
        async def get_status():
            return {"enabled": tracer.enabled, "stats": tracer.get_stats()}

        @app.post("/api/clear")
        async def api_clear():
            tracer.clear()
            return {"success": True}

        @app.get("/api/events")
        async def get_events(event_type: Optional[str] = None, agent_id: Optional[str] = None,
                             since_seq: int = 0, limit: int = Query(100, ge=1, le=1000)):
            return tracer.get_events(event_type=event_type, agent_id=agent_id, since_seq=since_seq, limit=limit)

        @app.get("/api/agents")
        async def get_agents():
            return tracer.get_agents()

        @app.get("/api/llm-calls")
        async def get_llm_calls(agent_id: Optional[str] = None, limit: int = Query(100, ge=1, le=1000)):
            return tracer.get_llm_calls(agent_id=agent_id, limit=limit)

        @app.get("/api/stats")
        async def get_stats():
            return tracer.get_stats()

        @app.websocket("/ws")
        async def websocket_endpoint(ws: WebSocket):
            await ws.accept()
            await ws.send_json({
                "type": "init",
                "stats": tracer.get_stats(),
                "agents": tracer.get_agents(),
                "events": tracer.get_events(limit=500)
            })

            last_seq = tracer.event_seq

            try:
                while True:
                    await asyncio.sleep(0.2)
                    current_seq = tracer.event_seq
                    if current_seq > last_seq:
                        events = tracer.get_events(since_seq=last_seq, limit=100)
                        if events:
                            await ws.send_json({
                                "type": "events",
                                "events": events,
                                "stats": tracer.get_stats(),
                                "agents": tracer.get_agents()
                            })
                        last_seq = current_seq

                    try:
                        data = await asyncio.wait_for(ws.receive_json(), timeout=0.05)
                        if data.get("type") == "ping":
                            await ws.send_json({"type": "pong"})
                    except asyncio.TimeoutError:
                        pass
            except WebSocketDisconnect:
                pass
            except Exception:
                pass

        config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning")
        server = uvicorn.Server(config)

        logger.info(f"[Debugger] 调试面板: http://localhost:{port}/")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(server.serve())

    _server_thread = threading.Thread(target=run, daemon=False, name="DebugServer")
    _server_thread.start()
    time.sleep(0.5)


DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Alphora Debugger</title>
    <style>
        :root {
            --bg-0: #0a0a0f; --bg-1: #12121a; --bg-2: #1a1a24; --bg-3: #252532;
            --border: #2a2a3a; --text-1: #f0f0f5; --text-2: #9090a0; --text-3: #606070;
            --blue: #4a9eff; --green: #4ade80; --yellow: #facc15; --red: #f87171; 
            --purple: #a78bfa; --cyan: #22d3ee; --orange: #fb923c; --pink: #f472b6;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg-0); color: var(--text-1); overflow: hidden; }
        
        header {
            display: flex; justify-content: space-between; align-items: center;
            padding: 10px 20px; background: var(--bg-1); border-bottom: 1px solid var(--border);
            position: fixed; top: 0; left: 0; right: 0; z-index: 100; height: 50px;
        }
        .logo { display: flex; align-items: center; gap: 10px; }
        .logo-icon { width: 28px; height: 28px; background: linear-gradient(135deg, var(--blue), var(--purple)); 
                     border-radius: 6px; display: flex; align-items: center; justify-content: center; font-size: 14px; }
        .logo h1 { font-size: 15px; font-weight: 600; }
        
        .stats-bar { display: flex; gap: 20px; }
        .stat-item { font-size: 12px; color: var(--text-2); }
        .stat-item .value { font-weight: 600; margin-left: 4px; }
        .stat-item.blue .value { color: var(--blue); }
        .stat-item.green .value { color: var(--green); }
        .stat-item.yellow .value { color: var(--yellow); }
        
        .header-right { display: flex; align-items: center; gap: 12px; }
        .status { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-2); }
        .status-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--green); }
        .status-dot.off { background: var(--red); }
        .btn { padding: 6px 12px; border-radius: 6px; border: none; font-size: 12px; cursor: pointer; background: var(--bg-2); color: var(--text-2); }
        .btn:hover { background: var(--bg-3); color: var(--text-1); }
        
        main { margin-top: 50px; height: calc(100vh - 50px); display: flex; }
        
        /* 左侧：拓扑图 */
        .graph-panel { flex: 1; position: relative; background: var(--bg-0); overflow: hidden; }
        
        #graphSvg { width: 100%; height: 100%; }
        
        /* 节点样式 */
        .node-group { cursor: pointer; }
        .node-box { fill: var(--bg-1); stroke: var(--border); stroke-width: 2; rx: 12; }
        .node-box.selected { stroke: var(--blue); stroke-width: 2; }
        .node-header { fill: var(--bg-2); }
        .node-icon { font-size: 16px; }
        .node-title { fill: var(--text-1); font-size: 13px; font-weight: 500; }
        .node-sub { fill: var(--text-3); font-size: 10px; font-family: monospace; }
        .node-badge { font-size: 10px; font-weight: 500; }
        
        /* 连线 */
        .edge-line { stroke: var(--border); stroke-width: 2; fill: none; }
        .edge-arrow { fill: var(--border); }
        .edge-line.active { stroke: var(--blue); stroke-width: 2; }
        .edge-arrow.active { fill: var(--blue); }
        
        /* 消息气泡 */
        .message-bubble { 
            position: absolute; background: var(--bg-2); border: 1px solid var(--border);
            border-radius: 8px; padding: 8px 12px; font-size: 11px; max-width: 200px;
            pointer-events: none; opacity: 0; transition: opacity 0.2s;
        }
        .message-bubble.show { opacity: 1; }
        
        /* 图例 */
        .graph-legend {
            position: absolute; bottom: 16px; left: 16px; background: var(--bg-1);
            border: 1px solid var(--border); border-radius: 8px; padding: 12px 16px;
            font-size: 11px;
        }
        .legend-item { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; color: var(--text-2); }
        .legend-item:last-child { margin-bottom: 0; }
        .legend-dot { width: 10px; height: 10px; border-radius: 3px; }
        
        /* 右侧：流程面板 */
        .flow-panel {
            width: 400px; background: var(--bg-1); border-left: 1px solid var(--border);
            display: flex; flex-direction: column;
        }
        .flow-header {
            padding: 14px 16px; border-bottom: 1px solid var(--border);
            display: flex; justify-content: space-between; align-items: center;
        }
        .flow-title { font-size: 13px; font-weight: 500; }
        .flow-filter { display: flex; gap: 4px; }
        .filter-btn { padding: 4px 10px; border-radius: 4px; font-size: 11px; background: transparent; 
                     border: none; color: var(--text-3); cursor: pointer; }
        .filter-btn:hover { color: var(--text-2); }
        .filter-btn.active { background: var(--bg-2); color: var(--text-1); }
        
        .flow-content { flex: 1; overflow-y: auto; padding: 12px; }
        
        /* 流程卡片 */
        .flow-card {
            background: var(--bg-2); border-radius: 10px; margin-bottom: 10px;
            border: 1px solid var(--border); overflow: hidden; transition: all 0.2s;
        }
        .flow-card:hover { border-color: #3a3a4a; }
        .flow-card.selected { border-color: var(--blue); }
        
        .flow-card-header {
            padding: 12px 14px; display: flex; align-items: center; gap: 10px; cursor: pointer;
        }
        .flow-card-icon {
            width: 32px; height: 32px; border-radius: 8px; display: flex; align-items: center; justify-content: center;
            font-size: 15px; flex-shrink: 0;
        }
        .flow-card.agent .flow-card-icon { background: rgba(74, 158, 255, 0.15); }
        .flow-card.llm .flow-card-icon { background: rgba(74, 222, 128, 0.15); }
        .flow-card.memory .flow-card-icon { background: rgba(167, 139, 250, 0.15); }
        .flow-card.derive .flow-card-icon { background: rgba(251, 146, 60, 0.15); }
        .flow-card.error .flow-card-icon { background: rgba(248, 113, 113, 0.15); }
        
        .flow-card-info { flex: 1; min-width: 0; }
        .flow-card-title { font-size: 12px; font-weight: 500; margin-bottom: 3px; display: flex; align-items: center; gap: 6px; }
        .flow-card-agent { font-size: 10px; padding: 1px 5px; background: var(--bg-0); border-radius: 3px; color: var(--text-3); }
        .flow-card-preview { font-size: 11px; color: var(--text-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        
        .flow-card-meta { text-align: right; flex-shrink: 0; }
        .flow-card-time { font-size: 10px; color: var(--text-3); font-family: monospace; }
        .flow-card-duration { font-size: 10px; color: var(--green); font-family: monospace; }
        
        .flow-card-body { padding: 0 14px 14px; display: none; }
        .flow-card.expanded .flow-card-body { display: block; }
        
        .flow-card-section { margin-bottom: 10px; }
        .flow-card-section:last-child { margin-bottom: 0; }
        .flow-card-label { font-size: 10px; color: var(--text-3); margin-bottom: 6px; text-transform: uppercase; }
        .flow-card-content {
            background: var(--bg-0); border-radius: 6px; padding: 10px 12px;
            font-family: monospace; font-size: 11px; line-height: 1.5;
            color: var(--text-2); max-height: 150px; overflow-y: auto; white-space: pre-wrap; word-break: break-all;
        }
        
        /* 连接指示器 */
        .flow-connector {
            display: flex; align-items: center; justify-content: center; padding: 2px 0;
        }
        .flow-connector-line {
            width: 2px; height: 16px; background: linear-gradient(to bottom, var(--border), var(--bg-3));
        }
        .flow-connector-arrow { color: var(--text-3); font-size: 10px; }
        
        /* 空状态 */
        .empty-state {
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            height: 100%; color: var(--text-3); gap: 8px;
        }
        .empty-state-icon { font-size: 40px; opacity: 0.5; }
        
        ::-webkit-scrollbar { width: 5px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--bg-3); border-radius: 3px; }
    </style>
</head>
<body>
    <header>
        <div class="logo">
            <div class="logo-icon">🔍</div>
            <h1>Alphora Debugger</h1>
        </div>
        <div class="stats-bar">
            <div class="stat-item blue">Agents<span class="value" id="statAgents">0</span></div>
            <div class="stat-item green">LLM Calls<span class="value" id="statCalls">0</span></div>
            <div class="stat-item yellow">Tokens<span class="value" id="statTokens">0</span></div>
        </div>
        <div class="header-right">
            <div class="status"><div class="status-dot" id="statusDot"></div><span id="statusText">连接中</span></div>
            <button class="btn" onclick="clearData()">清空</button>
        </div>
    </header>
    
    <main>
        <div class="graph-panel">
            <svg id="graphSvg">
                <defs>
                    <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
                        <polygon points="0 0, 10 3.5, 0 7" fill="#2a2a3a"/>
                    </marker>
                    <marker id="arrowhead-active" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
                        <polygon points="0 0, 10 3.5, 0 7" fill="#4a9eff"/>
                    </marker>
                </defs>
                <g id="graphEdges"></g>
                <g id="graphNodes"></g>
            </svg>
            
            <div class="graph-legend">
                <div class="legend-item"><div class="legend-dot" style="background: var(--blue)"></div>智能体节点</div>
                <div class="legend-item"><div class="legend-dot" style="background: var(--green)"></div>LLM 调用</div>
                <div class="legend-item"><div class="legend-dot" style="background: var(--orange)"></div>派生关系</div>
            </div>
        </div>
        
        <div class="flow-panel">
            <div class="flow-header">
                <div class="flow-title">执行流程</div>
                <div class="flow-filter">
                    <button class="filter-btn active" data-filter="all">全部</button>
                    <button class="filter-btn" data-filter="llm">LLM</button>
                    <button class="filter-btn" data-filter="agent">Agent</button>
                </div>
            </div>
            <div class="flow-content" id="flowContent">
                <div class="empty-state">
                    <div class="empty-state-icon">📭</div>
                    <div>等待事件...</div>
                </div>
            </div>
        </div>
    </main>
    
    <script>
        // 状态
        let ws = null;
        let events = [];
        let agents = {};
        let selectedAgent = null;
        let currentFilter = 'all';
        
        // 颜色映射
        const agentColors = ['#4a9eff', '#4ade80', '#facc15', '#f87171', '#a78bfa', '#22d3ee', '#fb923c', '#f472b6'];
        
        // 初始化
        function init() {
            connectWS();
            setupFilters();
            window.addEventListener('resize', renderGraph);
        }
        
        function connectWS() {
            ws = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`);
            
            ws.onopen = () => {
                document.getElementById('statusDot').classList.remove('off');
                document.getElementById('statusText').textContent = '已连接';
            };
            
            ws.onclose = () => {
                document.getElementById('statusDot').classList.add('off');
                document.getElementById('statusText').textContent = '断开';
                setTimeout(connectWS, 2000);
            };
            
            ws.onmessage = (e) => {
                const msg = JSON.parse(e.data);
                
                if (msg.type === 'init' || msg.type === 'events') {
                    if (msg.stats) updateStats(msg.stats);
                    if (msg.agents) msg.agents.forEach(a => agents[a.agent_id] = a);
                    if (msg.events) {
                        if (msg.type === 'init') events = msg.events;
                        else msg.events.forEach(ev => events.push(ev));
                    }
                    renderGraph();
                    renderFlow();
                }
            };
        }
        
        function updateStats(s) {
            document.getElementById('statAgents').textContent = s.active_agents || 0;
            document.getElementById('statCalls').textContent = s.total_llm_calls || 0;
            document.getElementById('statTokens').textContent = s.total_tokens >= 1000 ? 
                (s.total_tokens/1000).toFixed(1) + 'K' : (s.total_tokens || 0);
        }
        
        // ==================== 拓扑图渲染 ====================
        
        function renderGraph() {
            const svg = document.getElementById('graphSvg');
            const nodesG = document.getElementById('graphNodes');
            const edgesG = document.getElementById('graphEdges');
            
            nodesG.innerHTML = '';
            edgesG.innerHTML = '';
            
            const agentList = Object.values(agents);
            if (agentList.length === 0) return;
            
            const width = svg.clientWidth;
            const height = svg.clientHeight;
            
            const nodeWidth = 200;
            const nodeHeight = 80;
            const padding = 60;
            
            // 构建层级
            const levels = {};
            const processed = new Set();
            
            // 找根节点
            const childIds = new Set(agentList.filter(a => a.parent_id).map(a => a.agent_id));
            const roots = agentList.filter(a => !a.parent_id);
            
            function assignLevel(agent, level) {
                if (processed.has(agent.agent_id)) return;
                processed.add(agent.agent_id);
                
                if (!levels[level]) levels[level] = [];
                levels[level].push(agent);
                
                // 找子节点
                agentList.filter(a => a.parent_id === agent.agent_id)
                    .forEach(child => assignLevel(child, level + 1));
            }
            
            roots.forEach(r => assignLevel(r, 0));
            // 处理孤立节点
            agentList.filter(a => !processed.has(a.agent_id))
                .forEach(a => assignLevel(a, 0));
            
            const levelCount = Object.keys(levels).length;
            const positions = {};
            
            // 计算位置
            Object.entries(levels).forEach(([level, nodesInLevel]) => {
                const l = parseInt(level);
                const y = padding + (height - 2 * padding) / (levelCount || 1) * l + nodeHeight / 2;
                
                nodesInLevel.forEach((agent, i) => {
                    const x = padding + (width - 2 * padding) / (nodesInLevel.length + 1) * (i + 1);
                    positions[agent.agent_id] = { x, y, agent };
                });
            });
            
            // 绘制连线
            agentList.filter(a => a.parent_id && positions[a.parent_id]).forEach(agent => {
                const from = positions[agent.parent_id];
                const to = positions[agent.agent_id];
                
                if (from && to) {
                    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                    
                    const startY = from.y + nodeHeight / 2;
                    const endY = to.y - nodeHeight / 2;
                    const midY = (startY + endY) / 2;
                    
                    path.setAttribute('d', `M ${from.x} ${startY} C ${from.x} ${midY}, ${to.x} ${midY}, ${to.x} ${endY}`);
                    path.setAttribute('class', 'edge-line');
                    path.setAttribute('marker-end', 'url(#arrowhead)');
                    path.dataset.from = agent.parent_id;
                    path.dataset.to = agent.agent_id;
                    
                    edgesG.appendChild(path);
                }
            });
            
            // 绘制节点
            Object.values(positions).forEach((pos, idx) => {
                const { x, y, agent } = pos;
                const color = agentColors[idx % agentColors.length];
                
                // 获取该 Agent 的 LLM 调用数
                const agentEvents = events.filter(e => e.agent_id === agent.agent_id);
                const llmCalls = agentEvents.filter(e => e.event_type === 'llm_call_end').length;
                
                const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
                g.setAttribute('class', 'node-group');
                g.setAttribute('transform', `translate(${x - nodeWidth/2}, ${y - nodeHeight/2})`);
                g.dataset.agentId = agent.agent_id;
                
                g.innerHTML = `
                    <rect class="node-box ${selectedAgent === agent.agent_id ? 'selected' : ''}" 
                          width="${nodeWidth}" height="${nodeHeight}" style="stroke: ${color}"/>
                    <rect class="node-header" x="0" y="0" width="${nodeWidth}" height="30" rx="12" 
                          style="clip-path: inset(0 0 6px 0 round 12px 12px 0 0)"/>
                    <text class="node-icon" x="14" y="22">${getAgentIcon(agent.agent_type)}</text>
                    <text class="node-title" x="36" y="21">${agent.agent_type || 'Agent'}</text>
                    <text class="node-sub" x="14" y="52">${agent.agent_id.slice(0, 12)}</text>
                    ${llmCalls > 0 ? `
                        <rect x="${nodeWidth - 36}" y="44" width="26" height="18" rx="4" fill="${color}" opacity="0.2"/>
                        <text class="node-badge" x="${nodeWidth - 23}" y="56" text-anchor="middle" fill="${color}">${llmCalls}</text>
                    ` : ''}
                `;
                
                g.onclick = () => selectAgent(agent.agent_id);
                nodesG.appendChild(g);
            });
        }
        
        function getAgentIcon(type) {
            if (!type) return '🤖';
            const lower = type.toLowerCase();
            if (lower.includes('trans')) return '🌐';
            if (lower.includes('chat')) return '💬';
            if (lower.includes('search')) return '🔍';
            if (lower.includes('code')) return '💻';
            return '🤖';
        }
        
        function selectAgent(agentId) {
            selectedAgent = selectedAgent === agentId ? null : agentId;
            renderGraph();
            renderFlow();
        }
        
        // ==================== 流程渲染 ====================
        
        function renderFlow() {
            const container = document.getElementById('flowContent');
            
            let filtered = [...events];
            
            // 按 Agent 过滤
            if (selectedAgent) {
                filtered = filtered.filter(e => e.agent_id === selectedAgent);
            }
            
            // 按类型过滤
            if (currentFilter === 'llm') {
                filtered = filtered.filter(e => e.event_type.includes('llm'));
            } else if (currentFilter === 'agent') {
                filtered = filtered.filter(e => e.event_type.includes('agent') || e.event_type === 'prompt_created');
            }
            
            if (filtered.length === 0) {
                container.innerHTML = `<div class="empty-state"><div class="empty-state-icon">📭</div><div>暂无事件</div></div>`;
                return;
            }
            
            let html = '';
            filtered.forEach((ev, idx) => {
                const info = getEventInfo(ev);
                const agentName = agents[ev.agent_id]?.agent_type || 'Unknown';
                
                if (idx > 0) {
                    html += `<div class="flow-connector"><div class="flow-connector-line"></div></div>`;
                }
                
                html += `
                    <div class="flow-card ${info.type}" data-idx="${idx}" onclick="toggleCard(this)">
                        <div class="flow-card-header">
                            <div class="flow-card-icon">${info.icon}</div>
                            <div class="flow-card-info">
                                <div class="flow-card-title">
                                    ${info.title}
                                    <span class="flow-card-agent">${agentName}</span>
                                </div>
                                <div class="flow-card-preview">${info.preview}</div>
                            </div>
                            <div class="flow-card-meta">
                                <div class="flow-card-time">${formatTime(ev.timestamp)}</div>
                                ${info.duration ? `<div class="flow-card-duration">${info.duration}</div>` : ''}
                            </div>
                        </div>
                        <div class="flow-card-body">
                            ${info.sections.map(s => `
                                <div class="flow-card-section">
                                    <div class="flow-card-label">${s.label}</div>
                                    <div class="flow-card-content">${escapeHtml(s.content)}</div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `;
            });
            
            container.innerHTML = html;
        }
        
        function getEventInfo(ev) {
            const d = ev.data;
            
            switch (ev.event_type) {
                case 'agent_created':
                    return {
                        type: 'agent', icon: '🤖', title: '创建智能体',
                        preview: d.agent_type,
                        sections: [
                            { label: 'Agent Type', content: d.agent_type },
                            { label: 'LLM', content: d.llm_info?.model_name || '-' }
                        ]
                    };
                case 'agent_derived':
                    return {
                        type: 'derive', icon: '🔀', title: '派生智能体',
                        preview: `→ ${d.child_type}`,
                        sections: [
                            { label: '子智能体', content: `${d.child_type}\\n${d.child_id}` }
                        ]
                    };
                case 'prompt_created':
                    return {
                        type: 'agent', icon: '📝', title: '创建 Prompt',
                        preview: d.system_prompt_preview?.slice(0, 50) || '-',
                        sections: [
                            { label: 'System Prompt', content: d.system_prompt_preview || '-' },
                            { label: 'Memory', content: d.enable_memory ? `启用 (${d.memory_id})` : '禁用' }
                        ]
                    };
                case 'llm_call_start':
                    return {
                        type: 'llm', icon: '▶️', title: 'LLM 调用开始',
                        preview: d.input_preview?.slice(0, 50) || d.model_name,
                        sections: [
                            { label: '模型', content: d.model_name },
                            { label: '输入', content: d.input_preview || '-' }
                        ]
                    };
                case 'llm_call_end':
                    return {
                        type: 'llm', icon: '✅', title: 'LLM 调用完成',
                        preview: d.output_preview?.slice(0, 50) || '-',
                        duration: d.duration_ms ? `${d.duration_ms.toFixed(0)}ms` : null,
                        sections: [
                            { label: '输出', content: d.output_preview || '-' },
                            { label: '耗时', content: d.duration_ms ? `${d.duration_ms.toFixed(0)} ms` : '-' },
                            { label: 'Tokens', content: d.token_usage?.total_tokens || '-' }
                        ]
                    };
                case 'llm_call_error':
                    return {
                        type: 'error', icon: '❌', title: 'LLM 调用失败',
                        preview: d.error?.slice(0, 50) || '-',
                        sections: [{ label: '错误', content: d.error || '-' }]
                    };
                case 'memory_add':
                    return {
                        type: 'memory', icon: '💾', title: '添加记忆',
                        preview: `[${d.role}] ${d.content_preview?.slice(0, 40)}`,
                        sections: [
                            { label: '角色', content: d.role },
                            { label: '内容', content: d.content_preview || '-' }
                        ]
                    };
                case 'memory_retrieve':
                    return {
                        type: 'memory', icon: '📖', title: '检索记忆',
                        preview: `${d.message_count} 条消息`,
                        sections: [
                            { label: '轮数', content: d.rounds },
                            { label: '消息数', content: d.message_count }
                        ]
                    };
                default:
                    return {
                        type: 'agent', icon: '📌', title: ev.event_type,
                        preview: JSON.stringify(d).slice(0, 50),
                        sections: [{ label: '数据', content: JSON.stringify(d, null, 2) }]
                    };
            }
        }
        
        function toggleCard(card) {
            card.classList.toggle('expanded');
        }
        
        function formatTime(ts) {
            return new Date(ts * 1000).toLocaleTimeString('zh-CN', { hour12: false });
        }
        
        function escapeHtml(t) {
            const d = document.createElement('div');
            d.textContent = t;
            return d.innerHTML;
        }
        
        function setupFilters() {
            document.querySelectorAll('.filter-btn').forEach(btn => {
                btn.onclick = () => {
                    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    currentFilter = btn.dataset.filter;
                    renderFlow();
                };
            });
        }
        
        async function clearData() {
            if (!confirm('确定清空所有调试数据？')) return;
            await fetch('/api/clear', { method: 'POST' });
            events = [];
            agents = {};
            selectedAgent = null;
            renderGraph();
            renderFlow();
        }
        
        init();
    </script>
</body>
</html>
'''