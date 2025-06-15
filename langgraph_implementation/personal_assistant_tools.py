from playwright.async_api import async_playwright
from langchain_community.agent_toolkits import PlayWrightBrowserToolkit
from dotenv import load_dotenv
import os
import sys
import requests
from langchain.agents import Tool
from langchain_community.agent_toolkits import FileManagementToolkit
from langchain_community.tools.wikipedia.tool import WikipediaQueryRun
from langchain_experimental.tools import PythonREPLTool
from langchain_community.utilities import GoogleSerperAPIWrapper
from langchain_community.utilities.wikipedia import WikipediaAPIWrapper
import asyncio
import threading

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy()) 

load_dotenv(override=True)

pushover_token = os.getenv("PUSHOVER_TOKEN")
pushover_user = os.getenv("PUSHOVER_USER")
pushover_url = "https://api.pushover.net/1/messages.json"
serper = GoogleSerperAPIWrapper()

# Global variables to store browser instance
_browser_instance = None
_playwright_instance = None

async def playwright_tools():
    """Initialize Playwright tools with better error handling for Streamlit"""
    global _browser_instance, _playwright_instance
    
    try:
        # Try to reuse existing browser instance
        if _browser_instance and _playwright_instance:
            toolkit = PlayWrightBrowserToolkit.from_browser(async_browser=_browser_instance)
            return toolkit.get_tools(), _browser_instance, _playwright_instance
        
        # Create new browser instance
        _playwright_instance = await async_playwright().start()
        
        # Try headless first, fall back to visible browser if needed
        try:
            _browser_instance = await _playwright_instance.chromium.launch(
                headless=True,  # Start with headless
                args=['--no-sandbox', '--disable-dev-shm-usage']  # Additional args for stability
            )
        except Exception as e:
            print(f"Headless browser failed, trying with GUI: {e}")
            _browser_instance = await _playwright_instance.chromium.launch(
                headless=False,
                args=['--no-sandbox', '--disable-dev-shm-usage']
            )
        
        toolkit = PlayWrightBrowserToolkit.from_browser(async_browser=_browser_instance)
        return toolkit.get_tools(), _browser_instance, _playwright_instance
        
    except Exception as e:
        print(f"Error initializing Playwright: {e}")
        # Return empty tools list if Playwright fails
        return [], None, None

def playwright_tools_sync():
    """Synchronous wrapper for Playwright tools initialization"""
    def _init_playwright():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(playwright_tools())
        except Exception as e:
            print(f"Playwright initialization failed: {e}")
            return [], None, None
        finally:
            # Don't close the loop here as it's needed for the browser
            pass
    
    # Run in a separate thread to avoid event loop conflicts
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(_init_playwright)
        return future.result()

def push(text: str):
    """Send a push notification to the user"""
    try:
        if pushover_token and pushover_user:
            response = requests.post(
                pushover_url, 
                data={"token": pushover_token, "user": pushover_user, "message": text},
                timeout=10
            )
            if response.status_code == 200:
                return "Push notification sent successfully"
            else:
                return f"Failed to send notification: {response.status_code}"
        else:
            return "Pushover credentials not configured"
    except Exception as e:
        return f"Error sending notification: {str(e)}"

def get_file_tools():
    """Get file management tools"""
    try:
        # Ensure sandbox directory exists
        os.makedirs("sandbox", exist_ok=True)
        toolkit = FileManagementToolkit(root_dir="sandbox")
        return toolkit.get_tools()
    except Exception as e:
        print(f"Error initializing file tools: {e}")
        return []

async def other_tools():
    """Get other tools (non-Playwright)"""
    tools = []
    
    # Push notification tool
    push_tool = Tool(
        name="send_push_notification", 
        func=push, 
        description="Use this tool when you want to send a push notification to the user"
    )
    tools.append(push_tool)
    
    # File management tools
    try:
        file_tools = get_file_tools()
        tools.extend(file_tools)
    except Exception as e:
        print(f"File tools unavailable: {e}")
    
    # Search tool
    try:
        tool_search = Tool(
            name="search",
            func=serper.run,
            description="Use this tool when you want to get the results of an online web search"
        )
        tools.append(tool_search)
    except Exception as e:
        print(f"Search tool unavailable: {e}")
    
    # Wikipedia tool
    try:
        wikipedia = WikipediaAPIWrapper()
        wiki_tool = WikipediaQueryRun(api_wrapper=wikipedia)
        tools.append(wiki_tool)
    except Exception as e:
        print(f"Wikipedia tool unavailable: {e}")
    
    # Python REPL tool
    try:
        python_repl = PythonREPLTool()
        tools.append(python_repl)
    except Exception as e:
        print(f"Python REPL tool unavailable: {e}")
    
    return tools

def cleanup_browser():
    """Clean up browser resources"""
    global _browser_instance, _playwright_instance
    
    async def _cleanup():
        if _browser_instance:
            try:
                await _browser_instance.close()
            except Exception as e:
                print(f"Error closing browser: {e}")
        
        if _playwright_instance:
            try:
                await _playwright_instance.stop()
            except Exception as e:
                print(f"Error stopping playwright: {e}")
    
    if _browser_instance or _playwright_instance:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_cleanup())
            loop.close()
        except Exception as e:
            print(f"Error during cleanup: {e}")
        finally:
            _browser_instance = None
            _playwright_instance = None
