"""T029: DeepAgents / LangGraph agent with the three doc retrieval tools.

Registers: query_documents, read_document, grep_documents
Exposes agent via LangServe at /agent
"""

from __future__ import annotations

import logging

from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)


def build_agent():
    """Build and return a DeepAgents / LangGraph ReAct agent.

    Returns a LangChain Runnable suitable for use with LangServe add_routes().
    """
    from langchain.agents import AgentExecutor, create_tool_calling_agent
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

    from src.core.config import settings
    from src.skills.grep_skill import grep_documents
    from src.skills.query_skill import query_documents
    from src.skills.read_skill import read_document

    tools = [query_documents, read_document, grep_documents]

    system_prompt = (
        "You are DocSearch, an expert AI assistant for querying and reading indexed documents.\n"
        "You have access to three tools:\n"
        "- query_documents: semantic/keyword/hybrid search over document chunks\n"
        "- read_document: read a document sequentially by heading block or token count\n"
        "- grep_documents: full-text regex/keyword search over document Markdown\n\n"
        "Always cite the document title and heading_breadcrumb path from the chunk position when answering."
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            MessagesPlaceholder("chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ]
    )

    llm = ChatOpenAI(
        model=settings.chat_model,
        temperature=0,
        streaming=True,
    )

    agent = create_tool_calling_agent(llm=llm, tools=tools, prompt=prompt)
    return AgentExecutor(agent=agent, tools=tools, verbose=False)
