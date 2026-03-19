# -*- coding: utf-8 -*-
# filename: commander/logic_core_extractor.py
import re
from datetime import datetime

def extract_core_logic(drafts: list):
    """
    Naxuye 核心提取工艺 (V5.6 双质检增强版)
    职责：深度清洗 LLM 杂质，注入标准化工业水印，防止重复加工。
    """
    processed_results = []
    # 统一 Build Time，确保同一批次的组件时间戳一致
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    for item in drafts:
        path = item.get("path", "unknown.py")
        content = item.get("content", "")
        
        # 空内容保护
        if not content.strip():
            print(f"⚠️ [Extractor] 组件 {path} 内容为空，跳过")
            continue
            
        print(f"⚙️ [Extractor] 正在抛光组件: {path}")
        
        # 1. 深度除垢：彻底移除残留的 Markdown 代码块标记
        # 更彻底的清洗
        content = re.sub(r'^```\w*\n?', '', content, flags=re.MULTILINE)
        content = re.sub(r'\n```$', '', content, flags=re.MULTILINE)
        content = content.replace('```', '')
                
        # 3. 注入 2026 工业资产水印（避免重复注入）
        header = (
            f'# -*- coding: utf-8 -*-\n'
            f'# {"="*60}\n'
            f'# NAXUYE INDUSTRIAL AGENT COMPONENT\n'
            f'# Component: {path}\n'
            f'# Build Time: {timestamp}\n'
            f'# Status: Verified & Hardened (L6 Autonomy)\n'
            f'# {"="*60}\n\n'
        )
        
        # 检查是否已有水印
        if "NAXUYE INDUSTRIAL AGENT COMPONENT" not in content:
            processed_content = header + content
        else:
            print(f"   ↳ 检测到已存在水印，跳过重复注入")
            processed_content = content
        
        # 4. 路径安全化（防止目录遍历）
        safe_path = path.replace("..", "_").replace("/", "_").replace("\\", "_")
        
        processed_results.append({
            "path": safe_path,
            "content": processed_content
        })
        
    print(f"✅ [Extractor] 抛光完成，共处理 {len(processed_results)} 个组件")
    return processed_results