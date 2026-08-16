import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto('https://www.pesuacademy.com/Academy/')
        await page.fill('input[name="j_username"]', 'PES2202300447')
        await page.fill('input[name="j_password"]', 'haseeb1234')
        await page.click('button[id^="postloginform"]')
        await page.wait_for_load_state('networkidle')
        await page.goto('https://www.pesuacademy.com/Academy/s/studentProfilePESU')
        await page.wait_for_selector('.announcements-inner li', timeout=10000)
        
        # Click the first announcement to open the modal
        await page.click('.announcements-inner li a')
        await page.wait_for_selector('#pesuModal', timeout=5000)
        await asyncio.sleep(2)
        
        modal_html = await page.evaluate('document.querySelector("#pesuModal").innerHTML')
        print("======== MODAL ========\\n", modal_html)
        await browser.close()

asyncio.run(main())
