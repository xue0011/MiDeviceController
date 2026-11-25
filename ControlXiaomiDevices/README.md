## AI 控制层（新增）

本目录在原脚本之上增加了三个文件，把「控制设备」变成可被 AI 工作流调用的能力：

| 文件 | 作用 |
| --- | --- |
| `device_driver.py` | 设备注册表（`devices.json`，缺失回退 `devices.example.json`）+ 能力/范围校验 + 真机失败降级模拟 |
| `mcp_server.py` | MCP Server（FastMCP，stdio），暴露 7 个设备控制工具，全部返回 JSON 字符串 |
| `agent/` | LangGraph 设备 Agent（解析 → 安全校验 → 执行 → 回复）+ FastAPI，端口 8020 |

### MCP 方式（推荐，供外部 Agent 调用）

```bash
pip install -r requirements.txt
python mcp_server.py                     # stdio，交给 MCP 客户端启动即可
```

客户端配置示例：

```json
{"mcpServers": {"device-control": {
  "command": "python",
  "args": ["<本目录绝对路径>/mcp_server.py"]
}}}
```

### HTTP 方式（本地调试）

```bash
python -m agent                          # http://127.0.0.1:8020/docs
curl -s http://127.0.0.1:8020/chat -H 'Content-Type: application/json' \
  -d '{"text":"把客厅灯调暗一点"}'
```

### 设备清单

复制 `devices.example.json` 为 `devices.json`，按实际局域网 IP / token 填写。不填 IP 或真机不可达时自动使用模拟模式（返回 `backend: "simulated"`），无硬件也能跑通。

支持能力：`light` → 开关 / 亮度(1–100) / 色温(1700–6500K)；`airpurifier` → 开关 / 模式(auto,silent,favorite,idle) / 档位(1–14) / AQI；`plug` → 开关。

---

## 原有脚本（保留）

# ControlXiaomiDevices
This repository is a set of python scripts to control xiaomi IoT device。  
### 测试环境
Ubuntu 18.04 64bit  
Python 3.6  

### 依赖包
先安装pip3: sudo apt-get install python3-pip  
pip3 install -r requirements.txt  

### 脚本列表
* testbulb.py 控制小米智能台灯脚本 
* testGateway.py 控制网关设备脚本，正在编写中...    
* testAirpurifier.py 控制小米空气净化器脚本  
* UDP_Resend.py UDP重放攻击脚本  

### 数据包列表  
pcap 文件夹中查看  
  


### 参考资料  
https://github.com/Danielhiversen/PyXiaomiGateway  
https://github.com/skorokithakis/python-yeelight  
https://github.com/rytilahti/python-miio  


