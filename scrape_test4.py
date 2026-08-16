import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        async def handle_response(response):
            if "studentProfilePESUAdmin" in response.url and response.request.method == "POST":
                try:
                    text = await response.text()
                    print(f"--- RESPONSE from {response.url} ---")
                    print(text[:2000])
                except Exception as e:
                    pass
                    
        page.on("response", handle_response)
        
        await page.goto('https://www.pesuacademy.com/Academy/')
        await page.fill('input[name="j_username"]', 'PES2202300447')
        await page.fill('input[name="j_password"]', 'haseeb1234')
        await page.click('button[id^="postloginform"]')
        await page.wait_for_load_state('networkidle')
        await page.goto('https://www.pesuacademy.com/Academy/s/studentProfilePESU')
        await page.wait_for_selector('.announcements-inner li', timeout=10000)
        
        print("Clicking announcement...")
        await page.evaluate('document.querySelector(".announcements-inner li a").click()')
        await asyncio.sleep(5)
        
        await browser.close()

asyncio.run(main())
