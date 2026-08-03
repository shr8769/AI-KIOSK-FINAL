import asyncio
from agents.autonomous.base_autonomous_agent import load_agent_config
from agents.autonomous.announcement_monitor import AnnouncementMonitorAgent
import os
from dotenv import load_dotenv

load_dotenv()
cfg = load_agent_config('agent_config.yaml')
agent = AnnouncementMonitorAgent(cfg)

async def test_scrape():
    ann = await agent._scrape_announcements()
    print("Scraped:", len(ann))
    if ann:
        print("First:", ann[0])

asyncio.run(test_scrape())
