import streamlit as st
import asyncio
from langgraph_implementation.personal_assistant import Sidekick
import uuid
from datetime import datetime
import time
import json
import os
import zipfile
from pathlib import Path
import mimetypes

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
    
    .file-item {
        background: #f8f9fa;
        border: 1px solid #dee2e6;
        border-radius: 5px;
        padding: 0.75rem;
        margin: 0.5rem 0;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    
    .file-info {
        flex-grow: 1;
    }
    
    .file-size {
        color: #6c757d;
        font-size: 0.8rem;
    }
    
    .file-actions {
        display: flex;
        gap: 0.5rem;
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
if 'refresh_files' not in st.session_state:
    st.session_state.refresh_files = False

# File management functions
def ensure_sandbox_dir():
    """Ensure sandbox directory exists"""
    sandbox_path = Path("sandbox")
    sandbox_path.mkdir(exist_ok=True)
    return sandbox_path

def get_sandbox_files():
    """Get list of files in sandbox directory"""
    sandbox_path = ensure_sandbox_dir()
    files = []
    
    for file_path in sandbox_path.rglob("*"):
        if file_path.is_file():
            relative_path = file_path.relative_to(sandbox_path)
            file_size = file_path.stat().st_size
            file_modified = datetime.fromtimestamp(file_path.stat().st_mtime)
            
            files.append({
                'name': str(relative_path),
                'full_path': str(file_path),
                'size': file_size,
                'modified': file_modified,
                'extension': file_path.suffix.lower()
            })
    
    return sorted(files, key=lambda x: x['modified'], reverse=True)

def format_file_size(size_bytes):
    """Format file size in human readable format"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"

def read_file_content(file_path):
    """Read file content with proper encoding detection"""
    try:
        # Try UTF-8 first
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        try:
            # Try with latin-1 encoding
            with open(file_path, 'r', encoding='latin-1') as f:
                return f.read()
        except Exception:
            # If all else fails, read as binary and show hex
            with open(file_path, 'rb') as f:
                content = f.read()
                return f"Binary file ({len(content)} bytes)\n\nHex preview:\n{content[:200].hex()}"

def create_zip_archive(files):
    """Create a zip archive of selected files"""
    sandbox_path = Path("sandbox")
    zip_path = sandbox_path / f"archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_info in files:
            file_path = Path(file_info['full_path'])
            arcname = file_info['name']
            zipf.write(file_path, arcname)
    
    return zip_path

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

# Create tabs for different sections
tab1, tab2, tab3 = st.tabs(["💬 Chat Interface", "📁 File Manager", "🛠️ Tools & Info"])

with tab1:
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
        if st.button("🔄 Reset Session", type="secondary", key="reset_session_sidebar"):
            if st.session_state.sidekick:
                st.session_state.sidekick.cleanup()
            st.session_state.sidekick = None
            st.session_state.chat_history = []
            st.session_state.session_id = str(uuid.uuid4())
            st.session_state.setup_complete = False
            st.session_state.clear_inputs = False
            st.rerun()
        
        if st.button("🚀 Initialize Personal Assistant", type="primary", key="init_assistant_sidebar"):
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
        if st.button("📋 Clear Chat", key="clear_chat_sidebar"):
            st.session_state.chat_history = []
            st.rerun()
        
        if st.button("💾 Export Chat", key="export_chat_sidebar"):
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
                    mime="application/json",
                    key="download_chat_history"
                )
        
        if st.button("🔄 Refresh Files", key="refresh_files_sidebar"):
            st.session_state.refresh_files = True
            st.rerun()

    # Chat interface
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
                send_button = st.button("📤 Send Message", type="primary", use_container_width=True, key="send_message_main")
            with col_clear:
                if st.button("🗑️ Clear Input", use_container_width=True, key="clear_input_main"):
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
                        # Refresh files as they might have been modified
                        st.session_state.refresh_files = True
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
        st.header("📁 Quick File Access")
        
        # Show recent files in sidebar
        try:
            files = get_sandbox_files()
            if files:
                st.subheader("Recent Files")
                for i, file_info in enumerate(files[:5]):  # Added enumerate to get index
                    with st.container():
                        st.markdown(f"""
                        <div class="file-item">
                            <div class="file-info">
                                <strong>{file_info['name']}</strong><br>
                                <span class="file-size">{format_file_size(file_info['size'])} • {file_info['modified'].strftime('%Y-%m-%d %H:%M')}</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # Quick download button
                        with open(file_info['full_path'], 'rb') as file:
                            st.download_button(
                                label=f"📥 Download {file_info['name']}",
                                data=file.read(),
                                file_name=file_info['name'],
                                mime=mimetypes.guess_type(file_info['full_path'])[0] or 'application/octet-stream',
                                key=f"quick_download_{file_info['name']}_{i}",
                                use_container_width=True
                            )
                
                if len(files) > 5:
                    st.info(f"Showing 5 of {len(files)} files. Go to File Manager tab for complete view.")
            else:
                st.info("No files in sandbox directory yet.")
        except Exception as e:
            st.error(f"Error accessing files: {e}")

with tab2:
    st.header("📁 File Manager")
    st.markdown("Manage files created by your AI Assistant in the sandbox directory.")
    
    # File management controls
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        if st.button("🔄 Refresh Files", type="secondary", key="refresh_files_file_manager"):
            st.session_state.refresh_files = True
            st.rerun()
    
    with col2:
        # Create new file
        if st.button("📝 Create New File", key="create_new_file_button"):
            st.session_state.show_create_form = True
    
    with col3:
        # Bulk operations
        if st.button("📦 Create Archive", key="create_archive_button"):
            st.session_state.show_archive_form = True
    
    # Create new file form
    if st.session_state.get('show_create_form', False):
        with st.form("create_file_form"):
            st.subheader("Create New File")
            new_filename = st.text_input("Filename", placeholder="example.txt")
            new_content = st.text_area("File Content", height=200)
            
            col1, col2 = st.columns(2)
            with col1:
                if st.form_submit_button("Create File", type="primary"):
                    if new_filename and new_content:
                        try:
                            sandbox_path = ensure_sandbox_dir()
                            file_path = sandbox_path / new_filename
                            
                            # Create subdirectories if needed
                            file_path.parent.mkdir(parents=True, exist_ok=True)
                            
                            with open(file_path, 'w', encoding='utf-8') as f:
                                f.write(new_content)
                            
                            st.success(f"File '{new_filename}' created successfully!")
                            st.session_state.show_create_form = False
                            st.session_state.refresh_files = True
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error creating file: {e}")
                    else:
                        st.error("Please provide both filename and content.")
            
            with col2:
                if st.form_submit_button("Cancel"):
                    st.session_state.show_create_form = False
                    st.rerun()
    
    # Display files
    try:
        files = get_sandbox_files()
        
        if files:
            st.subheader(f"Files in Sandbox ({len(files)} files)")
            
            # File selection for bulk operations
            selected_files = []
            
            for i, file_info in enumerate(files):
                with st.container():
                    col1, col2, col3, col4, col5 = st.columns([0.5, 3, 1, 1, 1])
                    
                    with col1:
                        select = st.checkbox("", key=f"select_file_{i}")
                        if select:
                            selected_files.append(file_info)
                    
                    with col2:
                        st.markdown(f"""
                        **{file_info['name']}**  
                        {format_file_size(file_info['size'])} • Modified: {file_info['modified'].strftime('%Y-%m-%d %H:%M:%S')}
                        """)
                    
                    with col3:
                        # Download button
                        with open(file_info['full_path'], 'rb') as file:
                            st.download_button(
                                label="📥",
                                data=file.read(),
                                file_name=file_info['name'],
                                mime=mimetypes.guess_type(file_info['full_path'])[0] or 'application/octet-stream',
                                key=f"download_file_{i}",
                                help="Download file"
                            )
                    
                    with col4:
                        # View button
                        if st.button("👁️", key=f"view_file_{i}", help="View file content"):
                            st.session_state[f'show_content_{i}'] = not st.session_state.get(f'show_content_{i}', False)
                    
                    with col5:
                        # Delete button
                        if st.button("🗑️", key=f"delete_file_{i}", help="Delete file"):
                            try:
                                os.remove(file_info['full_path'])
                                st.success(f"Deleted {file_info['name']}")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error deleting file: {e}")
                    
                    # Show file content if requested
                    if st.session_state.get(f'show_content_{i}', False):
                        try:
                            content = read_file_content(file_info['full_path'])
                            
                            # Determine if it's a code file for syntax highlighting
                            if file_info['extension'] in ['.py', '.js', '.html', '.css', '.json', '.xml', '.yaml', '.yml']:
                                language = {
                                    '.py': 'python',
                                    '.js': 'javascript', 
                                    '.html': 'html',
                                    '.css': 'css',
                                    '.json': 'json',
                                    '.xml': 'xml',
                                    '.yaml': 'yaml',
                                    '.yml': 'yaml'
                                }.get(file_info['extension'], 'text')
                                
                                st.code(content, language=language)
                            else:
                                st.text_area(
                                    f"Content of {file_info['name']}",
                                    value=content,
                                    height=300,
                                    key=f"content_display_{i}",
                                    disabled=True
                                )
                        except Exception as e:
                            st.error(f"Error reading file: {e}")
                
                st.markdown("---")
            
            # Bulk operations
            if selected_files:
                st.subheader(f"Bulk Operations ({len(selected_files)} files selected)")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    if st.button("📦 Download Selected as ZIP", key="download_zip_bulk"):
                        try:
                            zip_path = create_zip_archive(selected_files)
                            with open(zip_path, 'rb') as zip_file:
                                st.download_button(
                                    label="📥 Download ZIP Archive",
                                    data=zip_file.read(),
                                    file_name=zip_path.name,
                                    mime='application/zip',
                                    key="download_zip_archive"
                                )
                        except Exception as e:
                            st.error(f"Error creating archive: {e}")
                
                with col2:
                    if st.button("🗑️ Delete Selected Files", type="secondary", key="delete_selected_files"):
                        try:
                            for file_info in selected_files:
                                os.remove(file_info['full_path'])
                            st.success(f"Deleted {len(selected_files)} files")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error deleting files: {e}")
        else:
            st.info("No files found in sandbox directory. Your AI Assistant will create files here when processing requests.")
            
            # Show example commands
            st.markdown("""
            ### Example Commands to Create Files:
            - "Create a Python script that calculates compound interest"
            - "Write a markdown report about renewable energy"
            - "Generate a CSV file with sample data"
            - "Create an HTML page with a simple form"
            """)
    
    except Exception as e:
        st.error(f"Error accessing sandbox directory: {e}")

with tab3:
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
        
        **📁 File Management**
        - Files are stored in the 'sandbox' directory
        - Use the File Manager tab to view, download, and manage files
        - The assistant can create various file types (text, code, data, etc.)
        - Bulk operations available for multiple files
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
