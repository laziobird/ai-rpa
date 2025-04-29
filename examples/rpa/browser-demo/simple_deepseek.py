import asyncio
import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from browser_use import Agent

# dotenv
load_dotenv()

api_key = os.getenv('DEEPSEEK_API_KEY', '')
if not api_key:
	raise ValueError('DEEPSEEK_API_KEY is not set')


async def run_search():
	agent = Agent(
		#task=('go to amazon.com, search for laptop, sort by best rating, and give me the price of the first result'),
		task="""
	   ### 
		### Step 1: Navigate to the Website
		- Open [ceshiren](https://ceshiren.com/).
		- 输入"web自动化"查询 
		### Step 2: 打开搜索结果的第一个链接A
		### Step 3: 获取链接A页面的标题和内容
		- 任务完成
		**重要:** 保证准确性和效率 
		""",
		llm=ChatOpenAI(
			base_url='https://api.deepseek.com/v1',
			model='deepseek-reasoner',
			api_key=SecretStr(api_key),
		),
		use_vision=False,
		max_failures=2,
		max_actions_per_step=1,
	)

	await agent.run()


if __name__ == '__main__':
	asyncio.run(run_search())
