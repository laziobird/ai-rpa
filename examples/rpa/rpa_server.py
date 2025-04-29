import asyncio
import datetime
# 使用简单的日志配置来替代
import logging
import os
import pathlib
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.responses import FileResponse
from langchain_openai import ChatOpenAI
from pydantic import SecretStr, BaseModel

from browser_use import Agent
from browser_use.agent.views import AgentOutput

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


# 使用生命周期管理器
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 简单记录启动信息
    print("正在启动服务...")

    yield

    # 简单记录关闭信息
    print("正在关闭服务...")

# dotenv
load_dotenv()
api_key = os.getenv('DEEPSEEK_API_KEY', '')
if not api_key:
    raise ValueError('DEEPSEEK_API_KEY is not set')

async def run_search(task: str, connection_id: str = None):
    logger = logging.getLogger(__name__)
    logger.info(f"开始执行任务: {task[:50]}...")

    try:
        # 创建Agent实例
        agent = Agent(
            task=task,
            llm=ChatOpenAI(
                base_url='https://api.deepseek.com/v1',
                model='deepseek-reasoner',
                api_key=SecretStr(api_key),
            ),
            use_vision=False,
            max_failures=2,
            max_actions_per_step=1,
        )

        # 自定义监控进度回调函数
        async def step_callback(state, output, step_number):
            """每一步Agent执行完成后的回调函数，将执行信息发送到前端"""
            try:
                # 发送当前步骤信息到前端
                await send_log_to_frontend(output, connection_id)
                
                # 同时发送结构化的步骤信息
                step_info = {
                    "step": 1,  # 固定为步骤1，因为这是RPA自动化的主要步骤
                    "status": "in-progress",
                    "message": f"AI步骤 {step_number}: {output.current_state.next_goal}",
                    "details": f"执行操作: {', '.join([a.model_dump_json(exclude_unset=True)[:30] + '...' for a in output.action])}"
                }
                await send_ws_message(step_info, websocket_connections.get(connection_id))
            except Exception as e:
                logger.error(f"发送步骤信息失败: {str(e)}")

        # 注册步骤回调函数
        agent.register_new_step_callback = step_callback

        # 执行任务
        logger.info("开始执行自动化任务")
        result = await agent.run()
        logger.info("自动化任务执行完成")

        # 提取最终结果
        final_result = "操作已完成，但未找到明确的结果内容"

        if hasattr(result, 'history') and result.history:
            # 尝试从最后一个操作提取结果
            for history_item in reversed(result.history):
                if hasattr(history_item, 'result') and history_item.result:
                    for action_result in reversed(history_item.result):
                        if hasattr(action_result, 'extracted_content') and action_result.extracted_content:
                                final_result = action_result.extracted_content
                                break
                    if final_result != "操作已完成，但未找到明确的结果内容":
                        break

        logger.info(f"最终结果: {final_result}")
        return final_result

    except Exception as e:
        logger.error(f"任务执行失败: {str(e)}")
        raise

# 确保静态目录存在
static_dir = pathlib.Path("static")
static_dir.mkdir(exist_ok=True)

# 创建FastAPI应用，使用lifespan替代on_event
app = FastAPI(
    title="DeepSeek Agent API",
    description="API for running agent tasks",
    lifespan=lifespan
)


#启动 gpt-api 的服务
async def start_gpt_api():
    import subprocess
    subprocess.Popen(["python", "examples/models/gpt_api.py"])  # 启动 gpt-api

@app.on_event("startup")
async def startup_event():
    await start_gpt_api()

# 添加首页路由
@app.get("/")
async def root():
    # 使用文件模板替代直接返回HTML
    template_path = os.path.join(os.path.dirname(__file__), 'templates', 'simple_page.html')
    return FileResponse(template_path)

# 修改请求模型以支持连接ID
class TaskRequest(BaseModel):
    task: str
    connection_id: str = None

    class Config:
        arbitrary_types_allowed = True

# 存储活跃的WebSocket连接
active_websockets = set()

# 添加一个全局变量来跟踪WebSocket连接ID
websocket_connections = {}
connection_counter = 0

# 修改WebSocket处理程序以支持连接ID
@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    global connection_counter
    connection_counter += 1
    connection_id = f"{client_id}_{connection_counter}"

    await websocket.accept()
    logging.info(f"📡 新的WebSocket连接已建立，ID: {connection_id}")

    # 将连接添加到活跃集合和映射中
    active_websockets.add(websocket)
    websocket_connections[connection_id] = websocket
    logging.info(f"📡 当前活跃WebSocket连接数: {len(active_websockets)}")

    try:
        # 发送连接成功消息
        await websocket.send_json({
            "status": "connected",
            "message": "WebSocket连接已建立",
            "connection_id": connection_id,
            "timestamp": str(datetime.datetime.now())
        })

        # 等待接收消息
        while True:
            data = await websocket.receive_text()
            logging.info(f"📡 收到WebSocket消息 [ID: {connection_id}]: {data[:100]}")
            # 这里只需要保持连接，实际消息会由API处理程序发送
            await websocket.send_json({
                "status": "received",
                "message": "收到消息",
                "connection_id": connection_id,
                "timestamp": str(datetime.datetime.now())
            })
    except Exception as e:
        logging.error(f"WebSocket错误 [ID: {connection_id}]: {str(e)}")
    finally:
        # 从活跃集合和映射中删除连接
        try:
            active_websockets.remove(websocket)
            if connection_id in websocket_connections:
                del websocket_connections[connection_id]
            logging.info(f"📡 WebSocket连接已关闭 [ID: {connection_id}]，当前活跃连接数: {len(active_websockets)}")
        except:
            pass

        # 确保关闭WebSocket连接
        try:
            if websocket.client_state.CONNECTED:
                await websocket.close()
        except:
            pass

# 添加一个不带客户端ID的WebSocket端点（向后兼容）
@app.websocket("/ws")
async def websocket_endpoint_no_id(websocket: WebSocket):
    # 生成随机客户端ID
    client_id = f"auto_{datetime.datetime.now().timestamp()}"
    # 调用带ID的处理函数
    await websocket_endpoint(websocket, client_id)

# 定义API端点
@app.post("/run-search")
async def api_run_search(request: TaskRequest):
    try:
        # 记录任务开始
        logging.info(f"🚀 开始执行任务: {request.task[:50]}...")

        # 使用连接ID，如果提供了的话
        if request.connection_id:
            logging.info(f"📡 请求中包含WebSocket连接ID: {request.connection_id}")

        # 获取指定的WebSocket连接（如果有）
        target_websocket = None
        if request.connection_id and request.connection_id in websocket_connections:
            target_websocket = websocket_connections[request.connection_id]
            logging.info(f"📡 找到指定的WebSocket连接 ID: {request.connection_id}")

        # 显示活跃连接状态
        logging.info(f"📡 当前活跃WebSocket连接数: {len(active_websockets)}")
        if not active_websockets:
            logging.warning("⚠️ 没有活跃的WebSocket连接，进度更新将无法发送")
            # 等待更长时间，给前端更多机会建立连接
            await asyncio.sleep(2)
            logging.info(f"📡 等待后检查，当前活跃WebSocket连接数: {len(active_websockets)}")

        # 确保WebSocket连接稳定
        await asyncio.sleep(1)  # 增加等待时间

        try:
            # 确保WebSocket连接稳定
            await asyncio.sleep(0.5)  # 给WebSocket连接一些建立的时间

            # 步骤1: 初始化任务
            logging.info("✅ 步骤1: 大模型模拟RPA开始")
            llm_log_path = os.path.join(os.path.dirname(__file__), 'llm_context.log')
            # 创建my.log文件（如果不存在）
            if os.path.exists(llm_log_path):
                with open(llm_log_path, 'w', encoding='utf-8') as log_file:
                    log_file.write("--new-job--\n")
            # # 执行任务
            result = await run_search(request.task, request.connection_id)
            logging.info(f"🔍 大模型模拟RPA结果: {result}")

            # 通过WebSocket发送步骤1完成的消息
            sent_count = await send_ws_message({
                "step": 1,
                "status": "completed",
                "message": "初始化任务完成，大模型执行结果:" + result.__str__(),
                "details": "准备开始读取日志"
            }, target_websocket)

            # 打印日志以确认消息已发送
            logging.info(f"✅ 步骤1完成消息已发送给 {sent_count} 个活跃连接")

            # 步骤2: 读取同目录下的my.log文件指定内容
            logging.info("✅ 步骤2: 读取日志内容")

            # 通过WebSocket发送步骤2开始的消息
            sent_count = await send_ws_message({
                "step": 2,
                "status": "in-progress",
                "message": "正在读取日志内容"
            }, target_websocket)

            # 打印日志以确认消息已发送
            logging.info(f"✅ 步骤2开始消息已发送给 {sent_count} 个活跃连接")

            a = ""
            try:
                with open(llm_log_path, 'r', encoding='utf-8') as log_file:
                    content = log_file.read()
                    sections = content.split('--new-job--')
                    if len(sections) > 1:
                        a = sections[-1].strip()  # 获取最后一个标记后的内容
                    else:
                        a = "未找到有效的日志内容"
                logging.info(f"📝 读取到的日志内容: {a[:100]}...")

                # 通过WebSocket发送步骤2完成的消息
                sent_count = await send_ws_message({
                    "step": 2,
                    "status": "completed",
                    "message": "日志读取完成",
                    "details": f"读取了{len(a)}字节的日志内容"
                }, target_websocket)

                # 打印日志以确认消息已发送
                logging.info(f"✅ 步骤2完成消息已发送给 {sent_count} 个活跃连接")

            except Exception as read_error:
                a = f"读取日志文件失败: {str(read_error)}"
                logging.error(f"❌ 读取日志失败: {str(read_error)}")

                # 通过WebSocket发送步骤2出错的消息
                sent_count = await send_ws_message({
                    "step": 2,
                    "status": "error",
                    "message": "日志读取失败",
                    "details": str(read_error)
                }, target_websocket)

            # 步骤3 生成提示词
            logging.info("✅ 步骤3: 生成提示词")

            # 通过WebSocket发送步骤3开始的消息
            sent_count = await send_ws_message({
                "step": 3,
                "status": "in-progress",
                "message": "正在生成提示词"
            }, target_websocket)

            # 从文件中导入提示词模板
            from examples.rpa.templates.prompt_template import prompt_template

            # 替换变量
            final_prompt = prompt_template.replace('{task}', request.task).replace('{a}', a)
            logging.info("🔤 已生成提示词\n"+final_prompt)

            # 通过WebSocket发送步骤3完成的消息
            sent_count = await send_ws_message({
                "step": 3,
                "status": "completed",
                "message": "提示词生成完成",
                "details": f"生成了{len(final_prompt)}字节的提示词"
            }, target_websocket)

            # 步骤4 获取生成的代码
            logging.info("✅ 步骤4: 生成代码")

            # 通过WebSocket发送步骤4开始的消息
            sent_count = await send_ws_message({
                "step": 4,
                "status": "in-progress",
                "message": "正在调用AI模型生成代码"
            }, target_websocket)

            # 创建DeepSeek LLM实例
            deepseek_llm = ChatOpenAI(
                base_url='https://api.deepseek.com/v1',
                model='deepseek-reasoner',  # 使用适合代码生成的模型
                api_key=SecretStr(api_key),
            )
            logging.info("🤖 正在调用DeepSeek模型生成代码...")
            # 调用模型
            response = await deepseek_llm.ainvoke([
                {"role": "user", "content": final_prompt}
            ])

            #官方标准配置（需替换为你的API密钥）
            #步骤4 获取生成的代码
            generated_code = response.content

            #调用 OpenAI API
            # async with httpx.AsyncClient() as client:
            #     api_response = await client.post("http://localhost:8001/chatgpt_query",
            #                                      json={"prompt": final_prompt, "model": "gpt-4o"})
            #     if api_response.status_code == 200:
            #         generated_code = api_response.json().get("response")
            #         logging.info(f"🎉 代码生成成功\n" + generated_code)
            #     else:
            #         logging.error(f"❌ 代码生成失败: {api_response.text}")
            #         raise HTTPException(status_code=500, detail="代码生成失败")

            logging.info(f"🎉 代码生成成功\n"+generated_code)
            
            # 通过WebSocket发送步骤4完成的消息
            sent_count = await send_ws_message({
                "step": 4,
                "status": "completed",
                "message": "代码生成完成",
                "details": f"生成了{len(generated_code)}字节的代码"
            }, target_websocket)
            # 返回结果
            return {
                "status": "success",
                "result": "大模型自动化RPA程序成功完成！",
                "log_content": a[:500] + ("..." if len(a) > 500 else ""),
                "prompt": final_prompt,
                "generated_code": generated_code,
                "steps": [
                    {"name": "初始化任务", "status": "completed", "result": "任务已初始化"},
                    {"name": "读取日志", "status": "completed", "result": f"读取了{len(a)}字节的日志内容"},
                    {"name": "生成提示词", "status": "completed", "result": f"生成了{len(final_prompt)}字节的提示词"},
                    {"name": "生成代码", "status": "completed", "result": f"生成了{len(generated_code)}字节的代码"}
                ]
            }
        except Exception as e:
            # 记录异常并返回错误
            logging.error(f"❌ 执行失败: {str(e)}")
            
            # 通过WebSocket发送错误消息
            sent_count = await send_ws_message({
                "status": "error",
                "message": f"执行失败: {str(e)}"
            }, target_websocket)
            
            raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        # 记录异常并返回错误
        logging.error(f"❌ 执行失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# 定义保存代码的请求模型
class CodeRequest(BaseModel):
    code: str

# 添加保存和运行代码的API端点
@app.post("/save-and-run")
async def save_and_run_code(request: CodeRequest):
    try:
        if not request.code:
            raise HTTPException(status_code=400, detail="代码不能为空")
        
        # 保存代码到文件
        filepath = "rpa-demo.py"
        try:
            # 保存前清空文件内容
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(request.code)
            logging.info(f"✅ 代码已保存到文件: {filepath}")
        except Exception as e:
            logging.error(f"❌ 保存代码到文件失败: {str(e)}")
            raise HTTPException(status_code=500, detail=f"保存代码失败: {str(e)}")

        # 使用子进程运行代码
        try:
            # 创建一个新的进程来运行Python代码
            import subprocess
            import sys
            
            # 使用当前Python解释器的路径，而不是依赖于系统环境变量
            python_executable = sys.executable
            
            process = subprocess.Popen(
                [python_executable, filepath],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # 限制执行时间，避免脚本无限运行
            try:
                stdout, stderr = process.communicate(timeout=60)  # 60秒超时
                if process.returncode == 0:
                    logging.info(f"✅ RPA代码执行成功")
                    return {
                        "status": "success", 
                        "output": stdout,
                        "message": "RPA代码已成功执行"
                    }
                else:
                    logging.error(f"❌ RPA代码执行失败: {stderr}")
                    return {
                        "status": "error", 
                        "output": stderr,
                        "message": "RPA代码执行时出错"
                    }
            except subprocess.TimeoutExpired:
                process.kill()
                logging.error("❌ RPA代码执行超时")
                return {
                    "status": "error",
                    "message": "RPA代码执行超时，可能存在无限循环"
                }
                
        except Exception as e:
            logging.error(f"❌ 运行RPA代码失败: {str(e)}")
            raise HTTPException(status_code=500, detail=f"运行RPA代码失败: {str(e)}")
            
    except Exception as e:
        logging.error(f"❌ 处理请求失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# 通过WebSocket发送消息的统一函数
async def send_ws_message(message, target_websocket=None):
    try:
        if target_websocket:
            # 如果有指定的连接，只发送给这个连接
            try:
                await target_websocket.send_json(message)
                return 1
            except Exception as ws_error:
                logging.error(f"发送WebSocket消息失败: {str(ws_error)}")
                return 0
        else:
            # 否则发送给所有活跃连接
            sent_count = 0
            for ws in list(active_websockets):
                try:
                    await ws.send_json(message)
                    sent_count += 1
                except Exception as ws_error:
                    logging.error(f"发送WebSocket消息失败: {str(ws_error)}")
                    try:
                        active_websockets.remove(ws)
                    except:
                        pass
            return sent_count
    except Exception as e:
        logging.error(f"发送WebSocket消息异常: {str(e)}")
        return 0

# 新增: 用于发送log_response内容到前端控制台的函数
async def send_log_to_frontend(response: AgentOutput, connection_id=None):
    """将log_response的内容发送到前端控制台"""
    try:
        # 选择适当的emoji
        if 'Success' in response.current_state.evaluation_previous_goal:
            emoji = '👍'
        elif 'Failed' in response.current_state.evaluation_previous_goal:
            emoji = '⚠'
        else:
            emoji = '🤷'
            
        # 构建要发送到前端的日志信息
        log_info = {
            "type": "agent_log",
            "timestamp": str(datetime.datetime.now()),
            "data": {
                "page_summary": response.current_state.page_summary,
                "evaluation": response.current_state.evaluation_previous_goal,
                "memory": response.current_state.memory,
                "next_goal": response.current_state.next_goal,
                "actions": []
            },
            "emoji": emoji
        }
        
        # 添加动作信息
        for i, action in enumerate(response.action):
            log_info["data"]["actions"].append({
                "index": i + 1,
                "total": len(response.action),
                "details": action.model_dump_json(exclude_unset=True)
            })
        
        # 通过WebSocket发送到前端
        target_websocket = None
        if connection_id and connection_id in websocket_connections:
            target_websocket = websocket_connections[connection_id]
            
        await send_ws_message(log_info, target_websocket)
        logging.info(f"⏱️ 已发送Agent日志到前端")
    except Exception as e:
        logging.error(f"发送Agent日志到前端时出错: {str(e)}")

if __name__ == '__main__':
    # 检查是否直接运行脚本
    if os.getenv("RUN_MODE") == "api":
        print("🚀 正在启动API服务...")
        # 启动API服务
        uvicorn.run(app, host="0.0.0.0", port=8000)
    else:
        # 默认示例任务
        default_task = """
		### Step 1: Navigate to the Website
		- Open [华律网](https://www.66law.cn/).
		- 选择'法律商城'，跳转新页面	
		**重要:** 保证准确性
        """
        asyncio.run(run_search(default_task))
