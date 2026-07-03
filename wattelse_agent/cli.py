"""Interactive CLI chat loop for the WattElse RAG agent."""

from __future__ import annotations

import asyncio

from agents import Runner
from dotenv import load_dotenv

from wattelse_agent.agent import build_agent, build_mcp_server


async def main() -> None:
    load_dotenv()
    async with build_mcp_server() as mcp_server:
        agent = build_agent(mcp_server)
        print("WattElse RAG agent ready. Type 'exit' to quit.\n")

        conversation: list = []
        while True:
            try:
                question = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not question:
                continue
            if question.lower() in {"exit", "quit"}:
                break

            conversation.append({"role": "user", "content": question})
            result = await Runner.run(agent, conversation)
            print(result.final_output, "\n")
            conversation = result.to_input_list()


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
