prompt_template = '''参考python程序 
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
    page.wait_for_timeout(2000)  # 短暂等待
    # 定位搜索按钮并点击
    page.locator("#search-button").click()
    page.wait_for_timeout(500)  # 短暂等待
    # 定位搜索框并输入web自动化
    page.locator("#search-term").fill("web自动化")
    page.wait_for_timeout(500)  # 短暂等待
    # 使用keyboard.down模拟键盘的enter事件
    page.keyboard.down("Enter")
    page.wait_for_timeout(500)  # 短暂等待
    # 断言搜索结果
    result = page.locator(".list>li:nth-child(1) .topic-title>span")
    # 截图
    page.wait_for_timeout(3000)  # 短暂等待
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
{task}
"
2、记录了是用 playwright 完成任务的日志，根据下面日志内容和“1、任务描述”生成完整的 playwright 代码
"
{a}
"
特别注意：
   2.1 : 通过 xpath 找到元素时，为了保证唯一性，加上 element 除了href属性以外，所有的 attributes 进行辨识
   2.2 : 不要初始化浏览器的宽高
   2.3 : 每次跳转或者打开页面， 先调用 page.wait_for_timeout(3000)  再进行操作
3、最后结果要用 page.screenshot 方法截图，截图名称规则 'screenshot'+当前时间(格式 YYYY-MM-DDTHH:MM:SS)+'.png'
''' 