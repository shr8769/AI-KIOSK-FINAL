import asyncio
import json
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        c = await b.new_context()
        page = await c.new_page()
        
        # Intercept network requests to find the API endpoint
        api_responses = []
        page.on("response", lambda response: api_responses.append(response))
        
        await page.goto('https://www.pesuacademy.com/Academy/')
        await page.fill('input[name="j_username"]', 'PES2202300447')
        await page.fill('input[name="j_password"]', 'haseeb1234')
        await page.click('button[id^="postloginform"]', force=True)
        await page.wait_for_load_state('networkidle')
        await page.goto('https://www.pesuacademy.com/Academy/s/studentProfilePESU', wait_until='networkidle')
        
        # Click the first announcement
        await page.click('.announcements-inner li a', force=True)
        await asyncio.sleep(2)  # Wait for modal/request
        
        # Print responses after click
        print("Network Responses:")
        for r in api_responses:
            if "pesuacademy.com/Academy/" in r.url and "get" in r.url.lower() or "announcement" in r.url.lower() or "show" in r.url.lower() or "detail" in r.url.lower():
                print(f"URL: {r.url}")
                try:
                    text = await r.text()
                    print(f"Body: {text[:200]}")
                except:
                    pass
        print('Done')

asyncio.run(run())
