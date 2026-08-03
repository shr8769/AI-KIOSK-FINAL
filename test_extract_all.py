import asyncio
import re
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
        
        # Get all onclicks
        onclicks = await page.evaluate('''() => {
            let els = document.querySelectorAll('.announcements-inner li a');
            return Array.from(els).map(el => el.getAttribute('onclick'));
        }''')
        
        print(f"Found {len(onclicks)} announcements")
        
        for idx, onclick in enumerate(onclicks[:5]): # just test first 5
            if onclick:
                match = re.search(r'handleShowMoreAnnouncement\((.*?),(.*?),(.*?)\)', onclick.replace(' ', ''))
                if match:
                    c_mode, a_type, ann_id = match.groups()
                    html = await page.evaluate(f'''() => {{
                        return new Promise((resolve, reject) => {{
                            $.ajax({{
                                url: '/Academy/s/studentProfilePESUAdmin',
                                type: 'POST',
                                data: {{ controllerMode: {c_mode}, actionType: {a_type}, AnnouncementId: {ann_id} }},
                                success: function(data) {{ resolve(data); }},
                                error: function(err) {{ reject(err); }}
                            }});
                        }});
                    }}''')
                    
                    import bs4
                    soup = bs4.BeautifulSoup(html, 'html.parser')
                    body_div = soup.select_one('.col-md-12')
                    text = body_div.get_text(separator=' ', strip=True) if body_div else "No body"
                    print(f"[{idx+1}] ID {ann_id}: {text[:150]}")
            await asyncio.sleep(0.5)
        print('Done')

asyncio.run(run())
