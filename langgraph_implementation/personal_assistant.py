import sys
from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from dotenv import load_dotenv
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from typing import List, Any, Optional, Dict
from pydantic import BaseModel, Field
from .personal_assistant_tools import playwright_tools, other_tools, cleanup_browser
import uuid
import asyncio
from datetime import datetime
import concurrent.futures
import threading

load_dotenv(override=True)

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

class State(TypedDict):
    messages: Annotated[List[Any], add_messages]
    success_criteria: str
    feedback_on_work: Optional[str]
    success_criteria_met: bool
    user_input_needed: bool

class EvaluatorOutput(BaseModel):
    feedback: str = Field(description="Feedback on the assistant's response")
    success_criteria_met: bool = Field(description="Whether the success criteria have been met")
    user_input_needed: bool = Field(description="True if more input is needed from the user, or clarifications, or the assistant is stuck")

class Sidekick:
    def __init__(self):
        self.worker_llm_with_tools = None
        self.evaluator_llm_with_output = None
        self.tools = []
        self.llm_with_tools = None
        self.graph = None
        self.sidekick_id = str(uuid.uuid4())
        self.memory = MemorySaver()
        self.browser = None
        self.playwright = None
        self._setup_complete = False

    async def setup(self):
        """Setup the Sidekick with better error handling"""
        try:
            print("Setting up Sidekick...")
            
            # Initialize tools
            print("Initializing tools...")
            
            # Get browser tools (may fail, that's ok)
            try:
                browser_tools, self.browser, self.playwright = await playwright_tools()
                print(f"Browser tools initialized: {len(browser_tools)} tools")
                self.tools.extend(browser_tools)
            except Exception as e:
                print(f"Browser tools failed to initialize: {e}")
                print("Continuing without browser tools...")
            
            # Get other tools
            try:
                other_tool_list = await other_tools()
                print(f"Other tools initialized: {len(other_tool_list)} tools")
                self.tools.extend(other_tool_list)
            except Exception as e:
                print(f"Some other tools failed to initialize: {e}")
            
            # Ensure we have at least some tools
            if not self.tools:
                print("Warning: No tools were initialized successfully")
            else:
                print(f"Total tools available: {len(self.tools)}")
            
            # Initialize LLMs
            print("Initializing LLMs...")
            try:
                worker_llm = ChatOpenAI(model="gpt-4o-mini")
                if self.tools:
                    self.worker_llm_with_tools = worker_llm.bind_tools(self.tools)
                else:
                    self.worker_llm_with_tools = worker_llm
                
                evaluator_llm = ChatOpenAI(model="gpt-4o-mini")
                self.evaluator_llm_with_output = evaluator_llm.with_structured_output(EvaluatorOutput)
                print("LLMs initialized successfully")
            except Exception as e:
                print(f"Error initializing LLMs: {e}")
                raise
            
            # Build graph
            print("Building workflow graph...")
            await self.build_graph()
            print("Sidekick setup completed successfully!")
            self._setup_complete = True
            
        except Exception as e:
            print(f"Error during setup: {e}")
            self._setup_complete = False
            raise

    def worker(self, state: State) -> Dict[str, Any]:
        """Worker node that processes user requests"""
        system_message = f"""You are a helpful assistant that can use tools to complete tasks.
You keep working on a task until either you have a question or clarification for the user, or the success criteria is met.
You have access to various tools to help you, including tools to browse the internet, manage files, run Python code, and search for information.
When using the Python tool, remember to include print() statements if you want to see output.
The current date and time is {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

This is the success criteria:
{state['success_criteria']}

You should reply either with a question for the user about this assignment, or with your final response.
If you have a question for the user, you need to reply by clearly stating your question. An example might be:

Question: Please clarify whether you want a summary or a detailed answer

If you've finished, reply with the final answer, and don't ask a question; simply reply with the answer.
"""
        
        if state.get("feedback_on_work"):
            system_message += f"""
Previously you thought you completed the assignment, but your reply was rejected because the success criteria was not met.
Here is the feedback on why this was rejected:
{state['feedback_on_work']}
With this feedback, please continue the assignment, ensuring that you meet the success criteria or have a question for the user."""
        
        # Handle system message
        found_system_message = False
        messages = state["messages"][:]
        for i, message in enumerate(messages):
            if isinstance(message, SystemMessage):
                messages[i] = SystemMessage(content=system_message)
                found_system_message = True
                break
        
        if not found_system_message:
            messages = [SystemMessage(content=system_message)] + messages
        
        # Invoke the LLM
        try:
            response = self.worker_llm_with_tools.invoke(messages)
            return {"messages": [response]}
        except Exception as e:
            error_message = f"Error in worker: {str(e)}"
            return {"messages": [AIMessage(content=error_message)]}

    def worker_router(self, state: State) -> str:
        """Route based on whether the last message has tool calls"""
        last_message = state["messages"][-1]
        
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        else:
            return "evaluator"
        
    def format_conversation(self, messages: List[Any]) -> str:
        """Format conversation for the evaluator"""
        conversation = "Conversation history:\n\n"
        for message in messages:
            if isinstance(message, HumanMessage):
                conversation += f"User: {message.content}\n"
            elif isinstance(message, AIMessage):
                text = message.content or "[Tool usage]"
                conversation += f"Assistant: {text}\n"
        return conversation
        
    def evaluator(self, state: State) -> Dict[str, Any]:
        """Evaluator node that assesses response quality"""
        try:
            last_response = state["messages"][-1].content

            system_message = """You are an evaluator that determines if a task has been completed successfully by an Assistant.
Assess the Assistant's last response based on the given criteria. Respond with your feedback, and with your decision on whether the success criteria has been met,
and whether more input is needed from the user."""
            
            user_message = f"""You are evaluating a conversation between the User and Assistant. You decide what action to take based on the last response from the Assistant.

The entire conversation with the assistant, with the user's original request and all replies, is:
{self.format_conversation(state['messages'])}

The success criteria for this assignment is:
{state['success_criteria']}

And the final response from the Assistant that you are evaluating is:
{last_response}

Respond with your feedback, and decide if the success criteria is met by this response.
Also, decide if more user input is required, either because the assistant has a question, needs clarification, or seems to be stuck and unable to answer without help.

The Assistant has access to various tools including file management, web browsing, Python execution, and search.
If the Assistant says they have completed a task using tools, you should generally trust them unless the response is clearly inadequate.
Overall you should give the Assistant the benefit of the doubt if they say they've done something. But you should reject if you feel that more work should go into this.
"""
            
            if state.get("feedback_on_work"):
                user_message += f"\nAlso, note that in a prior attempt from the Assistant, you provided this feedback: {state['feedback_on_work']}\n"
                user_message += "If you're seeing the Assistant repeating the same mistakes, then consider responding that user input is required."
            
            evaluator_messages = [
                SystemMessage(content=system_message), 
                HumanMessage(content=user_message)
            ]

            eval_result = self.evaluator_llm_with_output.invoke(evaluator_messages)
            
            return {
                "messages": [AIMessage(content=f"Evaluator Feedback: {eval_result.feedback}")],
                "feedback_on_work": eval_result.feedback,
                "success_criteria_met": eval_result.success_criteria_met,
                "user_input_needed": eval_result.user_input_needed
            }
            
        except Exception as e:
            error_feedback = f"Error in evaluator: {str(e)}"
            return {
                "messages": [AIMessage(content=f"Evaluator Error: {error_feedback}")],
                "feedback_on_work": error_feedback,
                "success_criteria_met": False,
                "user_input_needed": True
            }

    def route_based_on_evaluation(self, state: State) -> str:
        """Route based on evaluation results"""
        if state.get("success_criteria_met") or state.get("user_input_needed"):
            return "END"
        else:
            return "worker"

    async def build_graph(self):
        """Build the LangGraph workflow"""
        try:
            # Set up Graph Builder with State
            graph_builder = StateGraph(State)

            # Add nodes
            graph_builder.add_node("worker", self.worker)
            if self.tools:
                graph_builder.add_node("tools", ToolNode(tools=self.tools))
            graph_builder.add_node("evaluator", self.evaluator)

            # Add edges
            if self.tools:
                graph_builder.add_conditional_edges(
                    "worker", 
                    self.worker_router, 
                    {"tools": "tools", "evaluator": "evaluator"}
                )
                graph_builder.add_edge("tools", "worker")
            else:
                # If no tools, go directly to evaluator
                graph_builder.add_edge("worker", "evaluator")
                
            graph_builder.add_conditional_edges(
                "evaluator", 
                self.route_based_on_evaluation, 
                {"worker": "worker", "END": END}
            )
            graph_builder.add_edge(START, "worker")

            # Compile the graph
            self.graph = graph_builder.compile(checkpointer=self.memory)
            print("Graph built successfully")
            
        except Exception as e:
            print(f"Error building graph: {e}")
            raise

    async def run_superstep(self, message, success_criteria, history):
        """Run a complete workflow step"""
        try:
            if not self._setup_complete:
                raise Exception("Sidekick not properly initialized")
            
            # Ensure high recursion limit
            config = {
                "configurable": {
                    "thread_id": self.sidekick_id, 
                    "recursion_limit": 100
                }
            }
            
            state = {
                "messages": [HumanMessage(content=message)],
                "success_criteria": success_criteria or "The answer should be clear and accurate",
                "feedback_on_work": None,
                "success_criteria_met": False,
                "user_input_needed": False
            }
            
            # Add timeout as additional safety measure
            import asyncio
            result = await asyncio.wait_for(
                self.graph.ainvoke(state, config=config),
                timeout=300  # 5 minute timeout
            )
            
            # Format the response
            user_msg = {"role": "user", "content": message}
            
            # Find the assistant's main response (not the evaluator feedback)
            assistant_response = None
            evaluator_feedback = None
            
            for msg in result["messages"]:
                if isinstance(msg, AIMessage):
                    if msg.content and "Evaluator Feedback:" in msg.content:
                        evaluator_feedback = {"role": "assistant", "content": msg.content}
                    elif msg.content and not msg.content.startswith("Evaluator"):
                        assistant_response = {"role": "assistant", "content": msg.content}
            
            # Build response history
            response_history = history + [user_msg]
            if assistant_response:
                response_history.append(assistant_response)
            if evaluator_feedback:
                response_history.append(evaluator_feedback)
                
            return response_history
            
        except Exception as e:
            error_msg = f"Error in run_superstep: {str(e)}"
            print(f"Full error details: {e}")  # More detailed logging
            return history + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": f"I encountered an error: {error_msg}"}
            ]
    
    def cleanup(self):
        """Clean up resources"""
        print("Cleaning up Sidekick resources...")
        try:
            cleanup_browser()
        except Exception as e:
            print(f"Error during cleanup: {e}")
        
        # Reset state
        self.browser = None
        self.playwright = None
        self._setup_complete = False
        print("Cleanup completed")
