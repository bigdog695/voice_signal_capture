#!/usr/bin/env python3
"""
12345 市民热线工单总结服务

该服务接收通话记录，使用 DeepSeek 14B 模型生成标准化的工单内容。
"""

import json
import logging
import time
import re
import itertools
import random
import os
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
import uvicorn


# 配置日志
from logging.handlers import TimedRotatingFileHandler

# 创建日志目录
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 配置日志格式
log_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# 文件处理器 - 按天轮转
file_handler = TimedRotatingFileHandler(
    filename=LOG_DIR / 'ticket_service.log',
    when='midnight',  # 每天午夜轮转
    interval=1,  # 间隔1天
    backupCount=30,  # 保留30天
    encoding='utf-8'
)
file_handler.setFormatter(log_formatter)
file_handler.setLevel(logging.INFO)

# 控制台处理器
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
console_handler.setLevel(logging.INFO)

# 配置根日志记录器
logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, console_handler]
)
logger = logging.getLogger(__name__)

# 常量配置
MAX_RETRIES = 2
REQUEST_TIMEOUT = 60

# Ollama 模型配置
OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'deepseek-r1:14b')

# DeepSeek节点配置（从环境变量读取，支持逗号分隔的多个端点）
DEEPSEEK_ENDPOINTS_ENV = os.environ.get(
    'DEEPSEEK_ENDPOINTS',
    'http://127.0.0.1:11434/api/generate'
)
DEEPSEEK_ENDPOINTS = [ep.strip() for ep in DEEPSEEK_ENDPOINTS_ENV.split(',')]


class DeepSeekLoadBalancer:
    """DeepSeek API负载均衡器 - 使用轮询策略"""

    def __init__(self, endpoints: List[str]):
        """
        初始化负载均衡器

        Args:
            endpoints: DeepSeek API端点列表
        """
        self.endpoints = endpoints
        self.round_robin = itertools.cycle(endpoints)
        self.health_status = {ep: True for ep in endpoints}
        self.request_count = {ep: 0 for ep in endpoints}
        self.error_count = {ep: 0 for ep in endpoints}

        logger.info(f"初始化DeepSeek负载均衡器，节点数: {len(endpoints)}")
        for ep in endpoints:
            logger.info(f"  - {ep}")

    def get_next_endpoint(self) -> str:
        """
        获取下一个可用节点（轮询策略 + 健康检查）

        Returns:
            可用的端点URL
        """
        # 尝试找到健康的节点
        for _ in range(len(self.endpoints)):
            endpoint = next(self.round_robin)
            if self.health_status.get(endpoint, True):
                self.request_count[endpoint] += 1
                logger.debug(f"选择节点: {endpoint} (请求数: {self.request_count[endpoint]})")
                return endpoint

        # 所有节点都不健康，随机选择一个重试
        logger.warning("所有DeepSeek节点都不健康，随机选择节点重试")
        endpoint = random.choice(self.endpoints)
        self.request_count[endpoint] += 1
        return endpoint

    def mark_unhealthy(self, endpoint: str):
        """
        标记节点为不健康

        Args:
            endpoint: 节点URL
        """
        self.health_status[endpoint] = False
        self.error_count[endpoint] += 1
        logger.warning(
            f"节点标记为不健康: {endpoint} "
            f"(累计错误: {self.error_count[endpoint]})"
        )

    def mark_healthy(self, endpoint: str):
        """
        标记节点为健康

        Args:
            endpoint: 节点URL
        """
        was_unhealthy = not self.health_status.get(endpoint, True)
        self.health_status[endpoint] = True
        if was_unhealthy:
            logger.info(f"节点恢复健康: {endpoint}")

    def get_stats(self) -> Dict[str, Any]:
        """
        获取负载均衡器统计信息

        Returns:
            统计信息字典
        """
        return {
            "total_endpoints": len(self.endpoints),
            "healthy_endpoints": sum(1 for h in self.health_status.values() if h),
            "endpoints": [
                {
                    "url": ep,
                    "healthy": self.health_status[ep],
                    "request_count": self.request_count[ep],
                    "error_count": self.error_count[ep]
                }
                for ep in self.endpoints
            ]
        }


# 创建全局负载均衡器实例
load_balancer = DeepSeekLoadBalancer(DEEPSEEK_ENDPOINTS)

# 加载六安市地区数据
def load_location_data() -> str:
    """加载六安市地区从属关系数据，格式化为提示文本"""
    try:
        location_file = Path(__file__).parent / "location.json"
        with open(location_file, 'r', encoding='utf-8') as f:
            location_data = json.load(f)

        # 格式化为易读的提示文本
        location_info = "六安市行政区划包括：\n"
        for districts in location_data.values():
            for district, towns in districts.items():
                location_info += f"- {district}：{', '.join(towns[:10])}"
                if len(towns) > 10:
                    location_info += f"等{len(towns)}个乡镇街道"
                location_info += "\n"

        return location_info.strip()
    except Exception as e:
        logger.warning(f"加载地区数据失败: {e}，将使用默认配置")
        return "六安市包含：金安区、裕安区、霍邱县、金寨县、舒城县、霍山县、叶集区等行政区划"

LOCATION_CONTEXT = load_location_data()


class LocationCorrector:
    """地名矫正器：使用LLM进行地名矫正"""

    def __init__(self, location_file: Path):
        """初始化地名数据库"""
        self.location_data = self._load_location_data(location_file)
        logger.info(f"地名数据库加载完成")

    def _load_location_data(self, location_file: Path) -> Dict:
        """加载location.json数据"""
        try:
            with open(location_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载地名数据失败: {e}")
            return {}

    def correct_zone(self, raw_zone: str) -> Dict[str, Any]:
        """
        使用LLM矫正地名（使用负载均衡）

        返回: {
            "corrected": 矫正后的地名,
            "original": 原始地名,
            "method": "llm_correction",
            "success": True/False
        }
        """
        if not raw_zone:
            return {
                "corrected": raw_zone,
                "original": raw_zone,
                "method": "no_input",
                "success": False
            }

        prompt = f"""你是地名校对专家。请根据六安市标准地名库矫正用户输入的地名。

标准地名库：
{json.dumps(self.location_data, ensure_ascii=False, indent=2)}

用户输入的地名："{raw_zone}"

任务要求：
1. 【重要】仅矫正地名库中存在的标准地名，不要编造或猜测不存在的地名
2. 识别可能的错别字（同音字、形近字、方言读音等）
3. 返回最匹配的标准地名
4. 格式要求：
   - 保持原有格式（如果输入是"六安市霍邱县冯岭镇拱岗村"，输出也应该是完整地址格式）
   - 只矫正地名中的错别字，不要改变地址结构
   - 村名、小区名等如果不在地名库中，必须保留原文不变
   - 如果无法确定匹配，直接返回原文

示例：
输入："六安市霍邱县冯岭镇拱岗村"
输出："六安市霍邱县冯瓴镇拱岗村"

输入："刘安市金安区三十铺镇"
输出："六安市金安区三十铺镇"

输入："六安市舒城县山西镇"
输出："六安市舒城县山七镇"

只返回矫正后的完整地名，不要任何解释或额外文字。"""

        # 使用负载均衡器选择节点
        endpoint = load_balancer.get_next_endpoint()

        try:
            payload = {
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "top_p": 0.9
                }
            }

            response = requests.post(
                endpoint,
                json=payload,
                timeout=30,
                headers={'Content-Type': 'application/json'}
            )
            response.raise_for_status()

            # 标记节点为健康
            load_balancer.mark_healthy(endpoint)

            result = response.json()
            corrected = result.get('response', '').strip()

            # 移除可能的<think>标签和多余内容
            corrected = re.sub(r'<think>.*?</think>', '', corrected, flags=re.DOTALL)
            corrected = re.sub(r'<[^>]+>', '', corrected)
            corrected = corrected.strip()

            logger.info(f"LLM地名矫正 (节点: {endpoint}): '{raw_zone}' -> '{corrected}'")

            return {
                "corrected": corrected,
                "original": raw_zone,
                "method": "llm_correction",
                "success": True,
                "changed": raw_zone != corrected
            }

        except Exception as e:
            logger.error(f"LLM地名矫正失败 (节点: {endpoint}): {e}，返回原文")
            # 标记节点为不健康
            load_balancer.mark_unhealthy(endpoint)
            return {
                "corrected": raw_zone,
                "original": raw_zone,
                "method": "llm_failed",
                "success": False,
                "error": str(e)
            }


# Pydantic 模型定义
class ConversationEntry(BaseModel):
    citizen: Optional[str] = None
    hot_line: Optional[str] = None

class TicketSummaryRequest(BaseModel):
    pass  # 动态验证 JSON 内容

class TicketSummaryResponse(BaseModel):
    ticket_type: str
    ticket_zone: str
    ticket_title: str
    ticket_content: str
    zone_correction: Optional[Dict[str, Any]] = None  # 地名矫正元数据


# FastAPI 应用实例
app = FastAPI(
    title="12345 市民热线工单总结服务",
    description="将通话记录转换为标准化工单内容",
    version="1.0.0"
)


class TicketSummarizer:
    """工单总结器"""

    def __init__(self, location_corrector: LocationCorrector):
        self.location_corrector = location_corrector
        self.system_prompt = (
            "你是12345市民热线工单总结员，负责将通话内容转化为规范的工单记录。\n\n"
            "【核心原则】\n"
            "1. 【禁止编造】严格基于通话记录提取信息，不得添加、推测或编造任何未提及的内容\n"
            "2. 【忠实原文】如实记录对话中的表述，保留关键原话\n"
            "3. 【信息完整】对话中提到的所有关键信息（姓名、电话、地址、金额、时间等）必须全部记录\n\n"
            f"【地区背景知识】\n{LOCATION_CONTEXT}\n\n"
            "【重要】你必须严格按照以下JSON格式输出，字段名称不能改变：\n"
            "```json\n"
            "{\n"
            '  "ticket_type": "工单类型",\n'
            '  "ticket_zone": "所属区域",\n'
            '  "ticket_title": "工单标题",\n'
            '  "ticket_content": "工单内容"\n'
            "}\n"
            "```\n\n"
            "【字段说明】\n"
            "1. ticket_type：必须是以下之一：咨询、求助、举报、投诉\n"
            "   - 咨询：咨询办事流程、办事进度、政策文件、公开电话等\n"
            "   - 求助：涉及个人事项，因主观或客观原因个人无能为力解决，需要政府帮助才能解决\n"
            "   - 举报：举报他人违法违规行为，需要执法部门依法查处\n"
            "   - 投诉：除上述三类之外的其他诉求\n"
            "2. ticket_zone：【仅根据对话内容填写】尽可能详细的地址（格式：市-区/县-乡镇/街道-村/社区-小区名）\n"
            '   例如："六安市霍邱县三流乡三桥村" 或 "六安市金安区三十铺镇阳光花园小区"\n'
            '   【重要】如果对话中未明确提及地址，填写"未提及"\n'
            "3. ticket_title：一句话概括主要诉求（15字以内）\n"
            '4. ticket_content：分为两部分，格式为"来电人咨询：[市民反映内容] 话务员解答内容：[话务员回复]"\n'
            '   【重要】必须使用第三人称客观叙述，不要使用"我"、"您"等第一、第二人称\n'
            "   - 来电人咨询：详细记录市民反映的具体情况，必须包含：\n"
            "     * 具体门牌号、楼栋单元（如有）\n"
            "     * 手机号码（如有）\n"
            "     * 涉及的金钱数目（如有）\n"
            "     * 具体时间要素（如有）\n"
            "     * 数字信息尽量使用阿拉伯数字表示\n"
            "     * 不要重复ticket_zone中的地区信息\n"
            '     * 使用"来电人"、"市民"、"当事人"等第三人称\n'
            '     * 【禁止编造】如果对话中未提及某项信息，不要编造\n'
            "   - 话务员解答内容：【重要】必须详细记录话务员的所有解答信息，必须包含：\n"
            "     * 话务员提供的所有解决方案或办理流程（多个方案需逐一列出）\n"
            "     * 涉及的重要个人信息：姓名、身份证号码、联系方式等（如有）\n"
            "     * 涉及的部门名称、联系电话、办公地址、办公时间（如有）\n"
            "     * 涉及的办事材料、证件要求（如有）\n"
            "     * 涉及的时间节点、办理期限（如有）\n"
            "     * 涉及的费用、金额信息（如有）\n"
            "     * 话务员承诺的后续跟进措施（如转办、回访等）\n"
            '     * 使用"话务员"、"工作人员"等第三人称\n'
            '     * 使用数字序号(1. 2. 3.)组织多个要点，确保信息完整清晰\n'
            '     * 【禁止编造】如果话务员未解答或未提供信息，如实记录"话务员表示将进一步核实"等\n'
            '   示例1："来电人咨询：市民询问居民医保如何暂停参保。话务员解答内容：话务员已告知市民有3种办理方式：1. 携带相关证件前往政务中心办理停保；2. 线上添加办公QQ号123456789，上传身份证正反面照片办理；3. 本人通过手机微信小程序\'安徽医保公共服务\'线上办理。"\n'
            '   示例2："来电人咨询：市民张某（身份证号：342522********1234）反映其2024年1月缴纳的医保费用5000元未到账。话务员解答内容：话务员已记录市民姓名张某、身份证号342522********1234、联系电话138****5678，承诺将工单转交市医保局核实，预计3个工作日内电话回复处理结果。如需加急可拨打医保局咨询电话0564-1234567（工作日9:00-17:00）。"\n\n'
            "【输出规则】\n"
            "- 只输出JSON，不要任何额外解释\n"
            "- 字段名称必须完全一致，不能使用其他名称\n"
            "- 所有字段都是必填项\n"
            "- 【再次强调】严禁编造对话中未提及的信息"
        )

    def format_conversation(self, conversation_data: Dict[str, List[Dict]]) -> str:
        """格式化对话内容为可读文本"""
        formatted_text = "通话记录：\n"

        for session_id, messages in conversation_data.items():
            formatted_text += f"\n会话ID: {session_id}\n"
            for i, message in enumerate(messages):
                if "citizen" in message and message["citizen"]:
                    formatted_text += f"市民: {message['citizen']}\n"
                elif "hot-line" in message and message["hot-line"]:
                    formatted_text += f"接线员: {message['hot-line']}\n"

        return formatted_text

    def call_deepseek_model(self, prompt: str) -> str:
        """调用 Ollama 模型（使用负载均衡）"""
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "system": self.system_prompt,
            "stream": False,
            "format": "json",  # 强制JSON格式输出
            "options": {
                "temperature": 0.1,  # 降低随机性，提高格式遵循度
                "top_p": 0.9,
                "repeat_penalty": 1.1
            }
        }

        # 使用负载均衡器选择节点
        endpoint = load_balancer.get_next_endpoint()

        try:
            response = requests.post(
                endpoint,
                json=payload,
                timeout=REQUEST_TIMEOUT,
                headers={'Content-Type': 'application/json'}
            )
            response.raise_for_status()

            # 标记节点为健康
            load_balancer.mark_healthy(endpoint)

            result = response.json()
            return result.get('response', '').strip()

        except requests.exceptions.RequestException as e:
            logger.error(f"调用 Ollama 模型失败 (节点: {endpoint}): {e}")
            # 标记节点为不健康
            load_balancer.mark_unhealthy(endpoint)
            raise HTTPException(status_code=500, detail=f"模型调用失败: {str(e)}")

    def extract_json_from_response(self, response_text: str) -> str:
        """从模型响应中提取JSON内容"""
        import re

        # 移除前后空白
        text = response_text.strip()

        # 移除 <think>...</think> 标签及其内容
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)

        # 移除其他可能的XML/HTML标签
        text = re.sub(r'<[^>]+>', '', text)

        # 处理markdown代码块
        if '```json' in text:
            # 提取 ```json ... ``` 中的内容
            json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
            if json_match:
                text = json_match.group(1)
        elif '```' in text:
            # 提取 ``` ... ``` 中的内容
            code_match = re.search(r'```\s*(.*?)\s*```', text, re.DOTALL)
            if code_match:
                text = code_match.group(1)

        # 移除剩余的反引号
        text = text.replace('```', '').strip()

        # 寻找JSON对象（从第一个 { 到最后一个 }）
        start_idx = text.find('{')
        if start_idx == -1:
            # 如果没有找到 {，可能是数组格式
            start_idx = text.find('[')
            if start_idx == -1:
                logger.warning(f"未找到JSON起始标记，原文: {text[:200]}...")
                return text

        # 寻找匹配的结束括号
        bracket_count = 0
        end_idx = -1
        start_char = text[start_idx]
        end_char = '}' if start_char == '{' else ']'

        for i in range(start_idx, len(text)):
            if text[i] == start_char:
                bracket_count += 1
            elif text[i] == end_char:
                bracket_count -= 1
                if bracket_count == 0:
                    end_idx = i
                    break

        if end_idx != -1:
            extracted_json = text[start_idx:end_idx + 1]
            logger.debug(f"提取的JSON: {extracted_json}")
            return extracted_json
        else:
            logger.warning(f"未找到JSON结束标记，返回处理后的文本: {text[:200]}...")
            return text.strip()

    def validate_and_parse_json(self, json_text: str) -> Dict[str, str]:
        """验证并解析 JSON 响应"""
        try:
            # 尝试解析 JSON
            data = json.loads(json_text)

            # 验证必要字段
            required_fields = ['ticket_type', 'ticket_zone', 'ticket_title', 'ticket_content']
            for field in required_fields:
                if field not in data:
                    raise ValueError(f"缺少必要字段: {field}")

            # 验证 ticket_type 的有效值
            valid_types = ['咨询', '求助', '举报', '投诉']
            if data['ticket_type'] not in valid_types:
                logger.warning(f"工单类型 '{data['ticket_type']}' 不在标准列表中，但继续处理")

            return data

        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}, 原文: {json_text}")
            raise ValueError(f"JSON 格式错误: {str(e)}")
        except Exception as e:
            logger.error(f"JSON 验证失败: {e}")
            raise ValueError(f"数据验证失败: {str(e)}")

    def summarize(self, conversation_data: Dict[str, List[Dict]]) -> Dict[str, Any]:
        """执行工单总结（包含地名矫正）"""
        formatted_conversation = self.format_conversation(conversation_data)

        prompt = f"""请根据以下通话记录生成工单总结。

通话记录：
{formatted_conversation}

【重要提醒】
1. 严格基于上述通话记录，不要添加任何未提及的信息
2. 如果对话中没有明确提到地址，ticket_zone 必须填写"未提及"
3. 如果话务员未提供解答，如实记录实际情况

请严格按照以下格式输出JSON（字段名称不能改变）：
{{
  "ticket_type": "咨询|求助|举报|投诉 之一",
  "ticket_zone": "详细地址（例如：六安市金安区三十铺镇水韵东方小区）或"未提及"",
  "ticket_title": "一句话概括",
  "ticket_content": "来电人咨询：[使用第三人称客观描述市民反映的内容，不要用"我"、"您"，要用"市民"、"来电人"等称呼，包括门牌号、手机号、金额、时间等具体信息，数字使用阿拉伯数字，禁止编造未提及的信息] 话务员解答内容：[【重要】必须详细完整记录话务员的所有解答信息，包括：姓名、身份证号码、联系方式、部门电话、办理流程、时间节点、费用信息、后续跟进措施等（如有），使用第三人称，用数字序号组织多个要点，禁止编造]"
}}

重要提示：
1. ticket_content必须使用第三人称客观叙述，避免第一、第二人称
2. 话务员解答部分必须详细完整，特别要记录姓名、身份证号码等关键个人信息，确保所有解答信息完整记录
3. 【禁止编造】严格忠实于通话记录原文"""

        last_error = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                logger.info(f"第 {attempt + 1} 次尝试调用模型")

                # 调用模型
                model_response = self.call_deepseek_model(prompt)
                logger.info(f"模型原始响应: {model_response[:500]}...")  # 记录前500字符

                # 清理响应（移除各种非JSON内容）
                cleaned_response = self.extract_json_from_response(model_response)
                logger.info(f"提取的JSON: {cleaned_response}")

                # 验证和解析 JSON
                result = self.validate_and_parse_json(cleaned_response)
                logger.info("工单总结生成成功")

                # 地名矫正（固定二次调用LLM）
                raw_zone = result.get('ticket_zone', '')
                logger.info(f"开始地名矫正，原始地名: '{raw_zone}'")

                correction_result = self.location_corrector.correct_zone(raw_zone)

                # 更新结果
                result['ticket_zone'] = correction_result['corrected']
                result['zone_correction'] = correction_result

                if correction_result.get('changed', False):
                    logger.info(
                        f"地名已矫正: '{correction_result['original']}' -> '{correction_result['corrected']}'"
                    )
                else:
                    logger.info("地名无需矫正")

                return result

            except Exception as e:
                last_error = e
                logger.error(f"第 {attempt + 1} 次尝试失败: {e}")
                if attempt < MAX_RETRIES:
                    time.sleep(1)  # 短暂延迟后重试

        # 所有重试都失败
        raise HTTPException(
            status_code=500,
            detail=f"工单总结生成失败，已重试 {MAX_RETRIES + 1} 次: {str(last_error)}"
        )


# 创建地名矫正器和工单总结器实例
location_file = Path(__file__).parent / "location.json"
location_corrector = LocationCorrector(location_file)
summarizer = TicketSummarizer(location_corrector)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """记录所有请求"""
    start_time = time.time()

    # 记录请求
    logger.info(f"收到请求: {request.method} {request.url}")

    response = await call_next(request)

    # 记录响应时间
    process_time = time.time() - start_time
    logger.info(f"请求处理完成，耗时: {process_time:.2f}秒")

    return response


@app.get("/")
async def root():
    """健康检查端点"""
    return {
        "service": "12345 市民热线工单总结服务",
        "status": "running",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/health")
async def health_check():
    """详细的健康检查（包含负载均衡器状态）"""
    try:
        # 测试 DeepSeek 服务连接（测试第一个节点）
        test_endpoint = DEEPSEEK_ENDPOINTS[0].replace('/api/generate', '')
        test_response = requests.get(test_endpoint, timeout=5)
        deepseek_status = "healthy" if test_response.status_code == 200 else "unhealthy"
    except:
        deepseek_status = "unreachable"

    # 获取负载均衡器统计
    lb_stats = load_balancer.get_stats()

    return {
        "service": "healthy",
        "deepseek_service": deepseek_status,
        "load_balancer": lb_stats,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/lb-stats")
async def get_load_balancer_stats():
    """
    获取负载均衡器详细统计信息
    """
    return load_balancer.get_stats()


@app.post("/summarize", response_model=TicketSummaryResponse)
async def summarize_ticket(request: Request):
    """
    工单总结接口

    接收通话记录 JSON，返回标准化的工单内容
    """
    try:
        # 获取原始请求体
        body = await request.body()
        logger.info(f"接收到请求，数据大小: {len(body)} 字节")

        # 解析 JSON
        try:
            conversation_data = json.loads(body)
        except json.JSONDecodeError as e:
            logger.error(f"请求 JSON 解析失败: {e}")
            raise HTTPException(status_code=400, detail=f"无效的 JSON 格式: {str(e)}")

        # 验证数据结构
        if not isinstance(conversation_data, dict):
            raise HTTPException(status_code=400, detail="请求数据必须是 JSON 对象")

        if not conversation_data:
            raise HTTPException(status_code=400, detail="请求数据不能为空")

        # 验证数据格式
        for session_id, messages in conversation_data.items():
            if not isinstance(messages, list):
                raise HTTPException(
                    status_code=400,
                    detail=f"会话 {session_id} 的消息必须是数组格式"
                )

            for i, message in enumerate(messages):
                if not isinstance(message, dict):
                    raise HTTPException(
                        status_code=400,
                        detail=f"会话 {session_id} 的第 {i+1} 条消息必须是对象格式"
                    )

                if not any(key in message for key in ['citizen', 'hot-line']):
                    logger.warning(f"消息 {i+1} 既不包含 'citizen' 也不包含 'hot-line' 字段")

        logger.debug(f"解析的对话数据: {conversation_data}")

        # 执行工单总结
        result = summarizer.summarize(conversation_data)

        # 记录结果
        logger.info(f"生成工单: {result['ticket_title']}")
        logger.debug(f"完整工单内容: {result}")

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"服务内部错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"服务内部错误: {str(e)}")


if __name__ == "__main__":
    logger.info("启动 12345 市民热线工单总结服务")
    logger.info(f"Ollama 模型配置: {OLLAMA_MODEL}")
    logger.info(f"负载均衡配置:")
    logger.info(f"  - 节点数量: {len(DEEPSEEK_ENDPOINTS)}")
    for i, ep in enumerate(DEEPSEEK_ENDPOINTS, 1):
        logger.info(f"  - 节点{i}: {ep}")

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8001,
        reload=False,
        log_level="info"
    )