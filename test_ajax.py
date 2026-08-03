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
        
        # Get the first onclick
        onclick = await page.evaluate('''() => {
            let el = document.querySelector('.announcements-inner li a');
            return el ? el.getAttribute('onclick') : null;
        }''')
        
        print("Onclick:", onclick)
        if onclick:
            match = re.search(r'handleShowMoreAnnouncement\((.*?),(.*?),(.*?)\)', onclick.replace(' ', ''))
            if match:
                c_mode, a_type, ann_id = match.groups()
                print(f"Extracted: {c_mode}, {a_type}, {ann_id}")
                
                # Fetch the detailed HTML via page.evaluate
                html = await page.evaluate(f'''() => {{
                    return new Promise((resolve, reject) => {{
                        var formData = {{
                            controllerMode: {c_mode},
                            actionType: {a_type},
                            AnnouncementId: {ann_id},
                        }};
                        $.ajax({{
                            url: '/Academy/s/studentProfilePESUAdmin',
                            type: 'POST',
                            data: formData,
                            success: function(data) {{ resolve(data); }},
                            error: function(err) {{ reject(err); }}
                        }});
                    }});
                }}''')
                
                with open('ann_detail.html', 'w', encoding='utf-8') as f:
                    f.write(html)
                print("Detailed HTML saved.")

asyncio.run(run())
