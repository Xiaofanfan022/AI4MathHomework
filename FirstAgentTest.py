"""
第一个智能体：ReAct（Thought → Action → Observation）最小闭环。

这是课程作业的起点版本，用于理解 agent 的工作方式：
  1. 把「用户请求 + 历史 Thought/Action/Observation」拼成一个 prompt
  2. 让 LLM 输出下一步的 Thought 和 Action
  3. 解析 Action，真的去执行对应工具
  4. 把工具返回值作为 Observation 追加回历史，回到第 1 步

配置全部从 .env 读取，代码里不再出现任何密钥。
"""

import os
import re

import requests
from dotenv import load_dotenv
from openai import OpenAI
from tavily import TavilyClient

# 读取同目录下的 .env（不存在也不会报错，此时依赖系统环境变量）
load_dotenv()


# ============================================================
# 0. 配置
# ============================================================

def _require(name: str) -> str:
    """取一个必需的环境变量，缺失时给出可操作的报错，而不是让程序在深处崩掉。"""
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"缺少环境变量 {name}。请在项目根目录的 .env 中填写它"
            f"（可参考 .env.example），然后重新运行。"
        )
    return value


API_KEY = _require("OPENAI_API_KEY")
BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://aihubmix.com/v1").strip()
MODEL_ID = os.environ.get("MODEL_NAME", "").strip() or "coding-glm-5.1-free"
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "").strip()


# ============================================================
# 1. 工具层
# ============================================================

def get_weather(city: str) -> str:
    """通过 wttr.in 查询指定城市的实时天气。"""
    url = f"https://wttr.in/{city}?format=j1"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        current = data["current_condition"][0]
        desc = current["weatherDesc"][0]["value"]
        temp_c = current["temp_C"]
        return f"{city}当前天气：{desc}，气温{temp_c}摄氏度"
    except requests.exceptions.RequestException as e:
        return f"错误：查询天气时遇到网络问题 - {e}"
    except (KeyError, IndexError) as e:
        return f"错误：解析天气数据失败，可能是城市名称无效 - {e}"


def get_attraction(city: str, weather: str) -> str:
    """根据城市和天气，用 Tavily 搜索并返回景点推荐。"""
    if not TAVILY_API_KEY:
        return "错误：未配置 TAVILY_API_KEY。"

    tavily = TavilyClient(api_key=TAVILY_API_KEY)
    query = f"'{city}' 在'{weather}'天气下最值得去的旅游景点推荐及理由"

    try:
        response = tavily.search(query=query, search_depth="basic", include_answer=True)
        if response.get("answer"):
            return response["answer"]

        formatted = [
            f"- {r['title']}: {r['content']}" for r in response.get("results", [])
        ]
        if not formatted:
            return "抱歉，没有找到相关的旅游景点推荐。"
        return "根据搜索，为您找到以下信息：\n" + "\n".join(formatted)
    except Exception as e:
        return f"错误：执行Tavily搜索时出现问题 - {e}"


AVAILABLE_TOOLS = {
    "get_weather": get_weather,
    "get_attraction": get_attraction,
}


# ============================================================
# 2. LLM 客户端
# ============================================================

class OpenAICompatibleClient:
    """调用任何兼容 OpenAI 接口的 LLM 服务。"""

    def __init__(self, model: str, api_key: str, base_url: str):
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def generate(self, prompt: str, system_prompt: str) -> str:
        print("正在调用大语言模型...")
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                stream=False,
            )
            print("大语言模型响应成功。")
            return response.choices[0].message.content or ""
        except Exception as e:
            print(f"调用LLM API时发生错误: {e}")
            return "错误：调用语言模型服务时出错。"


# ============================================================
# 3. ReAct 提示词
# ============================================================

AGENT_SYSTEM_PROMPT = """
你是一个智能旅行助手。你的任务是分析用户的请求，并使用可用工具一步步地解决问题。

# 可用工具:
- `get_weather(city: str)`: 查询指定城市的实时天气。
- `get_attraction(city: str, weather: str)`: 根据城市和天气搜索推荐的旅游景点。

# 输出格式要求:
你的每次回复必须严格遵循以下格式，包含一对Thought和Action：

Thought: [你的思考过程和下一步计划]
Action: [你要执行的具体行动]

Action的格式必须是以下之一：
1. 调用工具：function_name(arg_name="arg_value")
2. 结束任务：Finish[最终答案]

# 重要提示:
- 每次只输出一对Thought-Action
- Action必须在同一行，不要换行
- 当收集到足够信息可以回答用户问题时，必须使用 Action: Finish[最终答案] 格式结束

请开始吧！
"""


# ============================================================
# 4. 主循环
# ============================================================

def run(user_prompt: str, max_steps: int = 5) -> str:
    llm = OpenAICompatibleClient(model=MODEL_ID, api_key=API_KEY, base_url=BASE_URL)
    history = [f"用户请求: {user_prompt}"]

    print(f"用户输入: {user_prompt}\n" + "=" * 40)

    for step in range(max_steps):
        print(f"--- 循环 {step + 1} ---\n")

        llm_output = llm.generate("\n".join(history), system_prompt=AGENT_SYSTEM_PROMPT)

        # 模型有时会一口气输出多对 Thought-Action，只保留第一对
        match = re.search(
            r"(Thought:.*?Action:.*?)(?=\n\s*(?:Thought:|Action:|Observation:)|\Z)",
            llm_output,
            re.DOTALL,
        )
        if match:
            truncated = match.group(1).strip()
            if truncated != llm_output.strip():
                llm_output = truncated
                print("已截断多余的 Thought-Action 对")
        print(f"模型输出:\n{llm_output}\n")
        history.append(llm_output)

        action_match = re.search(r"Action:\s*(.+)", llm_output, re.DOTALL)
        if not action_match:
            observation = (
                "错误: 未能解析到 Action 字段。"
                "请确保你的回复严格遵循 'Thought: ... Action: ...' 的格式。"
            )
            print(f"Observation: {observation}\n" + "=" * 40)
            history.append(f"Observation: {observation}")
            continue

        action_str = action_match.group(1).strip()

        if action_str.startswith("Finish"):
            finish_match = re.search(r"Finish\[(.*)\]", action_str, re.DOTALL)
            final_answer = finish_match.group(1).strip() if finish_match else action_str
            print(f"任务完成，最终答案: {final_answer}")
            return final_answer

        # 解析 function_name(arg="value")
        name_match = re.search(r"(\w+)\s*\(", action_str)
        args_match = re.search(r"\((.*)\)", action_str, re.DOTALL)
        if not name_match or not args_match:
            observation = f"错误：无法解析 Action 中的工具调用格式 -> {action_str}"
        else:
            tool_name = name_match.group(1)
            kwargs = dict(re.findall(r'(\w+)\s*=\s*"([^"]*)"', args_match.group(1)))
            if tool_name in AVAILABLE_TOOLS:
                observation = AVAILABLE_TOOLS[tool_name](**kwargs)
            else:
                observation = f"错误：未定义的工具 '{tool_name}'"

        print(f"Observation: {observation}\n" + "=" * 40)
        history.append(f"Observation: {observation}")

    print("已达到最大循环次数，未能得出结论。")
    return ""


if __name__ == "__main__":
    run("你好，请帮我查询一下今天上海的天气，然后根据天气推荐一个合适的旅游景点。")
