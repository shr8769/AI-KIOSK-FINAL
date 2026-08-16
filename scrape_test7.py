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
        
        links = await page.evaluate('''async () => {
            const list = document.querySelectorAll('.announcements-inner li a');
            let results = [];
            for (let a of list) {
                const onclick = a.getAttribute('onclick');
                if (onclick && onclick.includes('handleShowMoreAnnouncement')) {
                    const match = onclick.match(/handleShowMoreAnnouncement\\(\\s*\\d+\\s*,\\s*\\d+\\s*,\\s*(\\d+)\\s*\\)/);
                    if (match) {
                        const annId = match[1];
                        // Fetch the HTML
                        const formData = new URLSearchParams();
                        formData.append('menuId', '651');
                        formData.append('url', 'studentProfilePESUAdmin');
                        formData.append('controllerMode', '6401');
                        formData.append('actionType', '5');
                        formData.append('id', annId);
                        formData.append('selectedData', '0');
                        
                        try {
                            const res = await fetch('https://www.pesuacademy.com/Academy/s/studentProfilePESUAdmin', {
                                method: 'POST',
                                body: formData,
                                headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
                            });
                            const html = await res.text();
                            
                            // Parse html
                            const parser = new DOMParser();
                            const doc = parser.parseFromString(html, 'text/html');
                            let pdfs = [];
                            doc.querySelectorAll('a').forEach(link => {
                                if (link.href.includes('handleDownloadAnoncemntdoc')) {
                                    const docMatch = link.href.match(/'(\\d+)'/);
                                    if (docMatch) {
                                        pdfs.push({
                                            title: link.innerText.trim(),
                                            url: `https://www.pesuacademy.com/Academy/s/studentProfilePESU/downloadAnoncemntdoc/${docMatch[1]}`
                                        });
                                    }
                                }
                            });
                            results.push({annId, pdfs});
                        } catch (e) {
                            results.push({annId, error: e.toString()});
                        }
                    }
                }
            }
            return results;
        }''')
        
        print("======== RESULTS ========")
        for r in links[:3]:
            print(r)
            
        await browser.close()

asyncio.run(main())
