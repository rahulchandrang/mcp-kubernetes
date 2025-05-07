import os
import asyncio
from langchain_openai import AzureChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.messages.tool import ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient

# Set environment variables for Azure OpenAI
os.environ["AZURE_OPENAI_ENDPOINT"] = ""
os.environ["AZURE_OPENAI_API_KEY"] = ""

# Initialize AzureChatOpenAI LLM
llm = AzureChatOpenAI(
    azure_deployment="gpt-4o-mini",
    api_version="2025-01-01-preview",
    temperature=0,
    max_tokens=None,
    timeout=None,
    max_retries=2,
)

# Async function to handle agent interaction
async def run_agent():
    # Configure MCP client with the k8s tool server
    async with MultiServerMCPClient(
        {
            "k8s": {
                "command": "uv",
                "args": [
                    "--directory",
                    "<path to mcp kubernetes>",
                    "run",
                    "main_test.py",
                ],
                "transport": "stdio",
            },
        }
    ) as client:
        # Create ReAct agent using the provided tools
        agent = create_react_agent(llm, client.get_tools())

        while True:
            user_input = input("===> ")

            if user_input.lower() == "exit":
                break

            message = {"messages": user_input}

            try:
                response = await agent.ainvoke(message)

                tool_msgs = [msg for msg in response['messages'] if isinstance(msg, ToolMessage)]
                if tool_msgs:
                    print("Tools:", tool_msgs)

                print("Agent:", response['messages'][-1].content)
            except Exception as e:
                print(f"Error occurred: {e}")

# Run the async function
if __name__ == "__main__":
    asyncio.run(run_agent())
