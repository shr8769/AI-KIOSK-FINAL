import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        c = await b.new_context()
        page = await c.new_page()
        await page.goto('https://www.pesuacademy.com/Academy/')
        await page.fill('input[name="j_username"]', 'PES2202300447')
        await page.fill('input[name="j_password"]', 'haseeb1234')
        await page.click('button[id^="postloginform"]', force=True)
        await page.wait_for_load_state('networkidle')
        await page.goto('https://www.pesuacademy.com/Academy/s/studentProfilePESU', wait_until='networkidle')
        html = await page.content()
        with open('pesu_dump.html', 'w', encoding='utf-8') as f:
            f.write(html)
        print('Done')

asyncio.run(run())
