from playwright.sync_api import sync_playwright
from datetime import datetime

def baidu_search():
    with sync_playwright() as p:
        # 启动浏览器（不设置宽高）
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        try:
            # Step 1: 访问百度
            page.goto("https://www.baidu.com")
            page.wait_for_timeout(3000)
            
            # Step 2: 输入搜索内容
            # 使用组合属性的XPath确保唯一性
            search_box = page.locator('xpath=//input[@id="kw" and @name="wd" and @class="s_ipt"]')
            search_box.fill("人工智能")
            page.wait_for_timeout(3000)
            
            # 点击搜索按钮
            # 使用组合属性的XPath确保唯一性
            search_btn = page.locator('xpath=//input[@id="su" and @type="submit" and @class="bg s_btn"]')
            search_btn.click()
            page.wait_for_timeout(3000)
            
            # 生成带时间戳的截图文件名
            timestamp = datetime.now().isoformat(timespec='seconds')
            screenshot_name = f'screenshot{timestamp}.png'
            
            # 截图并保存
            page.screenshot(path=screenshot_name)
            
        finally:
            # 关闭浏览器
            browser.close()

if __name__ == '__main__':
    baidu_search()