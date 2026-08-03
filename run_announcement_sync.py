import asyncio
from agents.autonomous.base_autonomous_agent import load_agent_config
from agents.autonomous.announcement_monitor import AnnouncementMonitorAgent
import os
from dotenv import load_dotenv

load_dotenv()
cfg = load_agent_config('agent_config.yaml')
agent = AnnouncementMonitorAgent(cfg)
asyncio.run(agent._execute_cycle())
