from abc import ABC, abstractmethod
from typing import Any
from loguru import logger

class BaseAgent(ABC):
    name: str
    description: str

    @abstractmethod
    async def run(self, input_data: dict) -> dict:
        """Run the agent's core task logic."""
        pass

    def log(self, msg: str):
        logger.info(f"[{self.name}] {msg}")

    def log_error(self, msg: str):
        logger.error(f"[{self.name}] ERROR: {msg}")
