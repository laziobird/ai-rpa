from langchain_openai import ChatOpenAI
from browser_use import Agent, Browser, BrowserConfig
from dotenv import load_dotenv
load_dotenv()

import asyncio

task="""
### Step 1 访问 www.amazon.com， 获取 iphone16,6.1 英寸显示屏的最低价
### Step 3 访问 www.apple.com.cn，获取 iphone16,6.1 英寸显示屏的价格
### Step 4 把www.amazon.com的最低价网址和价格，apple.com.cn的的价格和网址整理成一个简单表格，发到指定mail.163.com邮箱，邮箱用户名 XXXX@163.com，密码 XXX,标题: iphone16 最低价
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