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
        
        items = await page.query_selector_all('.announcements-inner li')
        for el in items[:2]:
            link = await el.query_selector('a')
            await link.click()
            await page.wait_for_timeout(1000)
            
            data = await page.evaluate('''() => {
                const holder = document.querySelector(".panel-anouncementholder");
                if (!holder) return {text: "", links: []};
                
                let text = holder.innerText;
                let links = [];
                holder.querySelectorAll("a").forEach(a => {
                    const href = a.href;
                    if (href.includes("handleDownloadAnoncemntdoc")) {
                        const match = href.match(/'(\\d+)'/);
                        if (match) {
                            links.push(`[${a.innerText.trim() || 'PDF'}](https://www.pesuacademy.com/Academy/s/studentProfilePESU/downloadAnoncemntdoc/${match[1]})`);
                        }
                    }
                });
                return {text, links};
            }''')
            print("======")
            print("LINKS:", data['links'])
            print("TEXT:", data['text'][:100].replace("\\n", " "))
            
        await browser.close()

asyncio.run(main())
