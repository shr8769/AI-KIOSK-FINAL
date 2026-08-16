import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        # Intercept network requests to see what handleShowMoreAnnouncement does
        page.on("request", lambda request: print(">>", request.method, request.url))
        
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
