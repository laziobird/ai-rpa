from langchain_openai import ChatOpenAI
from browser_use import Agent, Browser, BrowserConfig
from dotenv import load_dotenv
import datetime
load_dotenv()

import asyncio

task="""
   ### 
### Step 1: Navigate to the Website
- Open [ceshiren](https://ceshiren.com/).
- 输入"web自动化"查询 
### Step 2: 打开搜索结果的第一个链接
- 任务完成
**重要:** 保证准确性和效率 
"""

browser = Browser()

agent = Agent(
   task=task,
    llm=ChatOpenAI(model="gpt-4o"),
    browser=browser,
    )

async def main():
    await agent.run()
    input("Press Enter to close the browser...")
    await browser.close()

if __name__ == '__main__':
    asyncio.run(main())