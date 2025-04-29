from langchain_openai import ChatOpenAI
from browser_use import Agent, Browser, BrowserConfig
from dotenv import load_dotenv
load_dotenv()

import asyncio

task="""
   ### 
### Step 1
- Open [infoq](https://www.infoq.com/).
- 输入"opentelemetry",点击搜索 
---

### Step 2
- 点击搜索结果网页第一个链接
- 获取页面标题和发布时间，保持在Memory中
- 任务完成

**重要:** 保证准确性和效率 .
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
    ##await browser.close()

if __name__ == '__main__':
    asyncio.run(main())