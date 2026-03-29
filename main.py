# -*- coding: utf-8 -*-
# filename: main.py
import asyncio
import os
import sys
from dotenv import load_dotenv

# 🚨 暴力锁定：直接指定 E 盘根目录下的 .env，彻底解决“环境漂移”
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
if os.path.exists(env_path):
    load_dotenv(dotenv_path=env_path, override=True)  # 强制覆盖所有环境变量
    
    # 🚨 【核心桥接逻辑】
    base_key = os.getenv("DEEPSEEK_API_KEY")
    if base_key:
        if not os.getenv("DEEPSEEK_REASONER_API_KEY"):
            os.environ["DEEPSEEK_REASONER_API_KEY"] = base_key
        if not os.getenv("DEEPSEEK_CHAT_API_KEY"):
            os.environ["DEEPSEEK_CHAT_API_KEY"] = base_key
        print("🩸 [System] 算力通道已全量桥接至通用 DeepSeek 接口")
    
    # 🧪 实时物理自检
    test_key = os.getenv("DEEPSEEK_REASONER_API_KEY")
    if not test_key:
        print("⚠️ [System] 警告：DeepSeek 算力未就绪")
else:
    print(f"❌ [Fatal] 物理链路中断：未在 {env_path} 发现配置文件！")

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# 初始化血色终端
console = Console()

def print_ignition_info(target_dir):
    """【资产固化】打印血色风格的交付面板"""
    main_py_path = os.path.join(target_dir, "main.py")
    
    matrix_text = Text()
    matrix_text.append(f"🩸 资产已强行固化至物理层 (集装箱规格)\n", style="bold red")
    matrix_text.append(f"📍 坐标: {target_dir}\n", style="white")
    matrix_text.append(f"🔥 唤醒指令: ", style="bold white")
    
    if os.path.exists(main_py_path):
        display_cmd = f"python \"{main_py_path}\""
    else:
        display_cmd = f"cd /d \"{target_dir}\""
        
    matrix_text.append(display_cmd, style="bold red underline blink")
    
    console.print(Panel(
        matrix_text, 
        title="[bold red]PROJECT HARVESTED[/bold red]", 
        border_style="red", 
        expand=False
    ))

async def main():
    # 延迟加载，防止启动阶段的循环引用
    try:
        from langgraph_workflow import naxuye_app
    except ImportError as e:
        console.print(f"[bold white on red] 🚨 核心逻辑加载失败: {e} [/bold white on red]")
        return

    # 初始血色界面
    console.print(Panel.fit(
        "[bold red]NAXUYE-STRATEGIC T V5.5 [BLOOD EDITION][/bold red]\n"
        "[dim white]Matrix Neural Link: [/dim white][bold red]CRITICAL ACTIVE[/bold red]\n"
        "[dim white]Power Grid: ALIYUN | ZHIPU | DEEPSEEK[/dim white]",
        border_style="red",
        subtitle="[red]人机融合·工业意志[/red]"
    ))
    
    while True:
        target = console.input("\n[bold red]🩸 注入建设目标 (输入 'quit' 脱离矩阵): [/bold red]")
        if target.lower() == 'quit': 
            break

        # 🚨 每一轮显式清空内存状态，适配集装箱逻辑
        initial_state = {
            "input": target,
            "chat_history": [],
            "plan": {},
            "intelligence": "",
            "active_node": {},
            "draft": [],
            "passed_slots": [],
            "audit_report": {"score": 0, "advice": "", "error_type": "NONE"},
            "retry_count": 0,
            "error_log": [],
            "final_path": "",
            "final_decision": "",
            "target_components": [],
            "batch_retry_count": 0,
            "agent_name": "",
            "input_schema": {},
            "trigger_keywords": [],
            "test_cases": []
        }

        console.print("\n[bold red]👁️  正在剥离现实，算力矩阵正在重构逻辑...[/bold red]")
        
        final_save_path = None
        
        try:
            async for output in naxuye_app.astream(initial_state):
                for node_name, state_update in output.items():
                    console.print(f"[bold red]>>>[/bold red] 维度 [on red]{node_name}[/on red] 处理完成")
                    
                    # 🚨 Planner 错误显示
                    if node_name == "planner":
                        plan = state_update.get("plan", {})
                        if plan.get("error"):
                            console.print(f"    ┗ [bold red]PLANNER 错误: {plan['error']}[/bold red]")
                    
                    # 🚨 实时审计结果反馈
                    if node_name == "reviewer":
                        report = state_update.get("audit_report", {})
                        score = report.get("score", 0)
                        retry_count = state_update.get("retry_count", 0)
                        error_type = report.get("error_type", "")
                        
                        if error_type in ["SAFETY_INTERCEPT", "PLANNER_FAILURE", "CRITICAL_FAILURE"]:
                            status = f"[bold white on red] {error_type} [/bold white on red]"
                        else:
                            status = "[bold white on green] PERFECT [/bold white on green]" if score >= 80 else "[bold white on red] REJECTED [/bold white on red]"
                        
                        console.print(f"    ┗ {status} 逻辑纯度: {score} | 重试次数: {retry_count}")
                    
                    # 冒烟测试结果反馈
                    if node_name == "smoke_test":
                        report = state_update.get("audit_report", {})
                        if report.get("error_type") == "SMOKE_TEST_FAILURE":
                            console.print(f"    ┗ [bold white on red] SMOKE TEST FAILED [/bold white on red] {report.get('summary', '')}")
                        else:
                            console.print(f"    ┗ [bold white on green] SMOKE TEST PASSED [/bold white on green]")

                    # 实时捕捉 Logistic 传递的路径简报
                    if node_name == "logistic":
                        report_text = state_update.get("final_decision", "")
                        console.print(Panel(f"[bold red]{report_text}[/bold red]", border_style="red"))
                        # ✅ 关键修复：更新 final_save_path
                        final_save_path = state_update.get("final_path")
        
        except Exception as e:
            console.print(f"[bold red]❌ 矩阵流转异常: {e}[/bold red]")

        # 🚨 物理层路径兜底：如果 logistic 没返回路径，手动查找
        if not final_save_path:
            try:
                factory_root = os.getenv("NAXUYE_WORKSPACE", os.path.join(os.path.expanduser("~"), "naxuye-workspace", "agent_factory"))
                if os.path.exists(factory_root):
                    # 过滤出所有带 _SAFE 的文件夹并按修改时间排序
                    dirs = [os.path.join(factory_root, d) for d in os.listdir(factory_root) 
                            if os.path.isdir(os.path.join(factory_root, d)) and "_SAFE" in d]
                    if dirs:
                        final_save_path = max(dirs, key=os.path.getmtime)
                        console.print(f"[dim white]📁 兜底路径: {final_save_path}[/dim white]")
            except Exception as path_err:
                console.print(f"[dim red]路径溯源失败: {path_err}[/dim red]")

        # 交付面板展示
        if final_save_path:
            print_ignition_info(final_save_path)
        else:
            console.print("[bold white on red]⚠️  警告：资产未能成功固化，物理链路中断。[/bold white on red]")

    console.print("[bold red]🔌 意识脱离，矩阵归于沉寂。[/bold red]")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[bold red]强制断开神经链接...[/bold red]")
    except Exception as e:
        console.print(f"\n[bold white on red] 系统核爆级错误: {e} [/bold white on red]")
        import traceback
        traceback.print_exc()
        input("\n[dim]按任意键退出矩阵...[/dim]")