from openai import OpenAI
from dotenv import load_dotenv
import os
# dotenv
load_dotenv()

import os
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY', ''))  # 从环境变量读取

def chatgpt_query(prompt, model="gpt-4o"):
    """带基础错误处理的API调用函数"""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是有10年编程经验的软件工程师"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"API调用失败: {str(e)}"

# 示例调用
if __name__ == "__main__":
    user_input = ("""
参考python程序 
"from playwright.sync_api import sync_playwright, expect
import asyncio
import websockets
def test_playwright():
    # 实例化playwright
    playwright = sync_playwright().start()
    # 打开chrome浏览器,headless默认是True,无头模式,这里设置为False方便查看效果
    browser = playwright.chromium.launch(headless=False)
    # 打开一个窗口页面
    page = browser.new_page()
    # 在当前窗口页面打开测试人网站
    page.goto("https://ceshiren.com/")
    # 定位搜索按钮并点击
    page.locator("#search-button").click()
    # 定位搜索框并输入web自动化
    page.locator("#search-term").fill("web自动化")
    # 使用keyboard.down模拟键盘的enter事件
    page.keyboard.down("Enter")
    # 断言搜索结果
    result = page.locator(".list>li:nth-child(1) .topic-title>span")
    expect(result).to_contain_text("自动化测试")

    # 截图
    page.screenshot(path='screenshot.png')
    # 用例完成后先关闭浏览器
    browser.close()
    # 然后关闭playwright服务
    playwright.stop()

if __name__ == '__main__':
    test_playwright()" 
写一个python程序：
1、任务描述
"
### Step 1: Navigate to the Website
• Open [ceshiren](https://ceshiren.com/).
• 输入"web自动化"查询 
### Step 2: 打开搜索结果的第一个链接
• 任务完成
**重要:** 保证准确性和效率
"
2、记录了用 playwright 完成改任务的操作日志，根据操作日志内容和任务描述生成完整的 playwright 代码
"
Navigate action, navigate to URL in the current tab , and url is https://ceshiren.com/
 Click action , this is a click element , and the element xpath : {'html/body/section/div/div/header/div/div/div[2]/ul/li/button'} . And the element attributes : {'aria-expanded': 'false', 'aria-haspopup': 'true', 'href': '/search', 'data-auto-route': 'true', 'title': '搜索', 'aria-label': '搜索', 'id': 'search-button', 'class': 'icon btn-flat'}
 Input text action ,  input {'web自动化'} into a input interactive element , the element xpath: {'html/body/section/div/div/header/div/div/div[2]/div/div/div/div/div/input'} . And the element attributes: {'id': 'search-term', 'type': 'text', 'value': '', 'autocomplete': 'off', 'placeholder': '搜索', 'aria-label': '搜索'}
Send keys Action , first call browser.get_current_page(), then call page.keyboard.press   These keys are {'Enter'}
 Click action , this is a click element , and the element xpath : {'html/body/section/div/div/header/div/div/div[2]/div/div/div/div/div[2]/div/ul/li/a'} . And the element attributes : {'class': 'widget-link search-link', 'href': '/t/topic/31158', 'title': ''}
"
   2.1 : 通过 xpath 找到元素时，为了保证唯一性，加上element的 attributes 进行辨识
3、最后结果一定要用 page.screenshot 方法截图，截图名称规则 'screenshot'+当前时间(格式 YYYY-MM-DDTHH:MM:SS)+'.png'    
    
    
"""
)

    print(chatgpt_query(user_input))