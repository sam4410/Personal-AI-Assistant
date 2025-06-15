import streamlit as st
import asyncio
from langgraph_implementation.personal_assistant import Sidekick
import uuid
from datetime import datetime
import time
import json

# Page configuration
st.set_page_config(
    page_title="Personal AI Assistant",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for modern styling
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
    }
    
    .tool-card {
        background: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .success-criteria {
        background: #d4edda;
        border: 1px solid #c3e6cb;
        border-radius: 8px;
        padding: 1rem;
        margin: 1rem 0;
    }
    
    .architecture-box {
        background: #e7f3ff;
        border: 1px solid #b8daff;
        border-radius: 8px;
        padding: 1.5rem;
        margin: 1rem 0;
    }
    
    .status-indicator {
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.875rem;
        font-weight: 500;
    }
    
    .status-active {
        background-color: #d4edda;
        color: #155724;
    }
    
    .status-inactive {
        background-color: #f8d7da;
        color: #721c24;
    }
    
    .chat-message {
        margin: 1rem 0;
        padding: 1rem;
        border-radius: 8px;
    }
    
    .user-message {
        background: #e3f2fd;
        border-left: 4px solid #2196f3;
    }
    
    .assistant-message {
        background: #f3e5f5;
        border-left: 4px solid #9c27b0;
    }
    
    .feedback-message {
        background: #fff3e0;
        border-left: 4px solid #ff9800;
        font-size: 0.9rem;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'sidekick' not in st.session_state:
    st.session_state.sidekick = None
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'session_id' not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if 'setup_complete' not in st.session_state:
    st.session_state.setup_complete = False
if 'clear_inputs' not in st.session_state:
    st.session_state.clear_inputs = False

# Async function wrappers
import threading
import concurrent.futures

def setup_sidekick_sync():
    """Initialize the Personal assistant in a separate thread"""
    def _setup():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            sidekick = Sidekick()
            result = loop.run_until_complete(sidekick.setup())
            return sidekick
        finally:
            loop.close()
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(_setup)
        return future.result()

def process_message_sync(sidekick, message, success_criteria, history):
    """Process a message through the assistant in a separate thread"""
    def _process():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                sidekick.run_superstep(message, success_criteria, history)
            )
            return result
        finally:
            loop.close()
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(_process)
        return future.result()

# Main header
st.markdown("""
<div class="main-header">
    <h1>🤖 Personal AI Assistant</h1>
    <p>An intelligent personal co-worker powered by LangGraph and advanced AI tools</p>
</div>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.header("🎛️ Control Panel")
    
    # Status indicator
    status = "Active" if st.session_state.setup_complete else "Inactive"
    status_class = "status-active" if st.session_state.setup_complete else "status-inactive"
    st.markdown(f'<span class="status-indicator {status_class}">Status: {status}</span>', 
                unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Session info
    st.subheader("📊 Session Info")
    st.text(f"Session ID: {st.session_state.session_id[:8]}...")
    st.text(f"Messages: {len(st.session_state.chat_history)}")
    st.text(f"Started: {datetime.now().strftime('%H:%M:%S')}")
    
    st.markdown("---")
    
    # Controls
    if st.button("🔄 Reset Session", type="secondary"):
        if st.session_state.sidekick:
            st.session_state.sidekick.cleanup()
        st.session_state.sidekick = None
        st.session_state.chat_history = []
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.setup_complete = False
        st.session_state.clear_inputs = False
        st.rerun()
    
    if st.button("🚀 Initialize Personal Assistant", type="primary"):
        if not st.session_state.setup_complete:
            with st.spinner("Setting up Personal Assistant..."):
                try:
                    st.session_state.sidekick = setup_sidekick_sync()
                    st.session_state.setup_complete = True
                    st.success("Personal Assistant initialized successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to initialize: {str(e)}")
                    st.error("Please ensure Playwright is properly installed: `playwright install chromium`")
    
    st.markdown("---")
    
    # Quick actions
    st.subheader("⚡ Quick Actions")
    if st.button("📋 Clear Chat"):
        st.session_state.chat_history = []
        st.rerun()
    
    if st.button("💾 Export Chat"):
        if st.session_state.chat_history:
            chat_data = {
                "session_id": st.session_state.session_id,
                "timestamp": datetime.now().isoformat(),
                "messages": st.session_state.chat_history
            }
            st.download_button(
                label="Download Chat History",
                data=json.dumps(chat_data, indent=2),
                file_name=f"sidekick_chat_{st.session_state.session_id[:8]}.json",
                mime="application/json"
            )

# Main content area
col1, col2 = st.columns([3, 2])

with col1:
    st.header("💬 Chat Interface")
    
    # Input area
    with st.container():
        # Use keys and handle clear state
        message_key = "message_input"
        criteria_key = "criteria_input"
        
        # Clear inputs if flag is set
        if st.session_state.clear_inputs:
            if message_key in st.session_state:
                del st.session_state[message_key]
            if criteria_key in st.session_state:
                del st.session_state[criteria_key]
            st.session_state.clear_inputs = False
        
        message = st.text_area(
            "Your Request",
            placeholder="Ask me anything! I can browse the web, run Python code, manage files, and more...",
            height=100,
            key=message_key,
            value="" if st.session_state.clear_inputs else st.session_state.get(message_key, "")
        )
        
        success_criteria = st.text_input(
            "Success Criteria (Optional)",
            placeholder="What defines a successful response?",
            help="Specify what you consider a complete and satisfactory answer",
            key=criteria_key,
            value="" if st.session_state.clear_inputs else st.session_state.get(criteria_key, "")
        )
        
        col_send, col_clear = st.columns([1, 1])
        with col_send:
            send_button = st.button("📤 Send Message", type="primary", use_container_width=True)
        with col_clear:
            if st.button("🗑️ Clear Input", use_container_width=True):
                st.session_state.clear_inputs = True
                st.rerun()
    
    # Process message
    if send_button and message.strip():
        if not st.session_state.setup_complete:
            st.error("Please initialize the assistant first using the sidebar.")
        else:
            with st.spinner("Personal Assistant is working..."):
                try:
                    results = process_message_sync(
                        st.session_state.sidekick,
                        message,
                        success_criteria or "The answer should be clear and accurate",
                        st.session_state.chat_history
                    )
                    st.session_state.chat_history = results
                    
                    # Clear inputs after successful send
                    st.session_state.clear_inputs = True
                    st.rerun()
                except Exception as e:
                    st.error(f"Error processing message: {str(e)}")
                    if "playwright" in str(e).lower():
                        st.error("Playwright browser issue detected. Try resetting the session.")
    
    # Chat history
    st.subheader("📜 Conversation History")
    
    if st.session_state.chat_history:
        for i, msg in enumerate(st.session_state.chat_history):
            if msg["role"] == "user":
                st.markdown(f"""
                <div class="chat-message user-message">
                    <strong>👤 You:</strong><br>
                    {msg["content"]}
                </div>
                """, unsafe_allow_html=True)
            elif msg["role"] == "assistant":
                if "Evaluator Feedback" in msg["content"]:
                    st.markdown(f"""
                    <div class="chat-message feedback-message">
                        <strong>🔍 Evaluator:</strong><br>
                        {msg["content"]}
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="chat-message assistant-message">
                        <strong>🤖 Sidekick:</strong><br>
                        {msg["content"]}
                    </div>
                    """, unsafe_allow_html=True)
    else:
        st.info("No messages yet. Start a conversation with your Assistant!")

with col2:
    st.header("🛠️ Available Tools")
    
    tools_info = [
        {
            "name": "🌐 Web Browser",
            "description": "Navigate websites, click elements, fill forms, and extract information from web pages using Playwright automation.",
            "capabilities": ["Page navigation", "Element interaction", "Data extraction", "Form filling"]
        },
        {
            "name": "🔍 Web Search",
            "description": "Search the internet using Google's search API to find current information and answers.",
            "capabilities": ["Real-time search", "Current events", "Fact checking", "Research"]
        },
        {
            "name": "🐍 Python REPL",
            "description": "Execute Python code for calculations, data analysis, and complex problem solving.",
            "capabilities": ["Mathematical computations", "Data analysis", "Visualization", "Algorithm implementation"]
        },
        {
            "name": "📁 File Management",
            "description": "Create, read, write, and manage files in the sandbox directory.",
            "capabilities": ["File creation", "Content editing", "Directory management", "File operations"]
        },
        {
            "name": "📚 Wikipedia",
            "description": "Query Wikipedia for encyclopedic information and knowledge.",
            "capabilities": ["Knowledge lookup", "Research", "Fact verification", "Educational content"]
        },
        {
            "name": "📱 Push Notifications",
            "description": "Send push notifications to your devices using Pushover service.",
            "capabilities": ["Alert notifications", "Task completion alerts", "Status updates"]
        }
    ]
    
    for tool in tools_info:
        with st.expander(tool["name"]):
            st.write(tool["description"])
            st.write("**Capabilities:**")
            for cap in tool["capabilities"]:
                st.write(f"• {cap}")

    st.markdown("---")
    
    st.header("🏗️ Architecture")
    
    st.markdown("""
    <div class="architecture-box">
        <h4>🔄 LangGraph Workflow</h4>
        <p>The Sidekick uses a sophisticated graph-based architecture:</p>
        <ul>
            <li><strong>Worker Node:</strong> Main AI agent that processes requests and uses tools</li>
            <li><strong>Tool Node:</strong> Executes tool calls and returns results</li>
            <li><strong>Evaluator Node:</strong> Assesses response quality and success criteria</li>
        </ul>
        <p>The system continues iterating until success criteria are met or user input is needed.</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Usage guide
    with st.expander("📖 Usage Guide"):
        st.markdown("""
        **🚀 Getting Started**
        1. Initialize the assistant using the sidebar
        2. Type your request in the message box
        3. Optionally specify success criteria
        4. Click "Send Message" to get started
        
        **💡 Tips for Better Results**
        - Be specific with your requests
        - Define clear success criteria
        - Break down complex tasks
        - Monitor the assistant's responses for insights
        
        **🔧 Advanced Features**
        - Multi-step task handling
        - Automatic error recovery
        - Session memory maintenance
        - Comprehensive tool integration
        """)

# Footer
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; padding: 1rem;">
    <p>🤖 <strong>Personal AI Assistant</strong> - Powered by LangGraph, OpenAI GPT-4, and Advanced Tool Integration</p>
    <p>Built with ❤️ using Streamlit • Session: {}</p>
</div>
""".format(st.session_state.session_id[:8]), unsafe_allow_html=True)

# Cleanup on session end
def cleanup_resources():
    """Clean up resources when session ends"""
    if st.session_state.sidekick:
        try:
            st.session_state.sidekick.cleanup()
        except Exception as e:
            st.error(f"Cleanup error: {e}")

# Register cleanup callback
if hasattr(st, 'on_session_end'):
    st.on_session_end(cleanup_resources)
