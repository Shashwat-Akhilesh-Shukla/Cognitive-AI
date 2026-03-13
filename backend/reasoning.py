"""
Cognitive Reasoning Engine for CognitiveAI

Implements the cognitive loop: input → recall → plan → respond → update memory.
Orchestrates STM, LTM, and PDF knowledge for coherent AI responses.
"""

import time
import asyncio
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import logging
import os
import json
from backend.memory.stm import STMManager
from backend.memory.ltm import LTMManager
from backend.pdf_loader import PDFLoader
from backend.prompts import THERAPIST_SYSTEM_PROMPT, VOICE_MODE_SYSTEM_PROMPT
from backend.ai_providers import AIProviderBase

logger = logging.getLogger(__name__)


class CognitiveReasoningEngine:
    """
    Cognitive Reasoning Engine that implements the minimal reflection cycle.

    The cognitive loop:
    1. Input: Process user message and context
    2. Recall: Retrieve relevant memories from STM, LTM, and PDF knowledge
    3. Plan: Generate response plan based on recalled information
    4. Respond: Generate coherent response using LLM
    5. Update: Store conversation highlights and update memory
    """

    def __init__(
        self,
        stm_manager: STMManager,
        ltm_manager: LTMManager,
        pdf_loader: PDFLoader,
        provider: Optional[AIProviderBase] = None,
        # Kept for backward compatibility — ignored when provider is supplied
        perplexity_api_key: str = "",
        model: str = "",
    ):
        """
        Initialize the reasoning engine.

        Args:
            stm_manager: Short-term memory manager
            ltm_manager: Long-term memory manager
            pdf_loader: PDF knowledge loader
            provider: Active AIProviderBase instance (Gemini or Perplexity)
            perplexity_api_key: Deprecated — kept for health-check backward compat
            model: Deprecated — model is taken from provider
        """
        self.stm_manager = stm_manager
        self.ltm_manager = ltm_manager
        self.pdf_loader = pdf_loader
        self._provider = provider

        # Backward-compat attributes used by the existing /health endpoint
        self.perplexity_api_key = perplexity_api_key
        self.model = model or (provider.model if provider else "")

        self.max_history_length = 10

    @property
    def provider(self) -> Optional[AIProviderBase]:
        """Return the currently active AI provider."""
        # Allow registry to be queried live so runtime switches take effect
        try:
            from backend.ai_providers import get_registry
            registry = get_registry()
            if registry.active_name:
                return registry.active_provider
        except Exception:
            pass
        return self._provider

    async def process_message(self, user_message: str, user_id: str = "default",
                        stm_memories: Optional[List[Dict[str, Any]]] = None,
                        ltm_memories: Optional[List[Dict[str, Any]]] = None,
                        pdf_snippets: Optional[List[str]] = None,
                        conversation_id: str = None,
                        current_emotion: str = "neutral",
                        voice_mode: bool = False) -> Dict[str, Any]:
        """
        Process a user message through the cognitive loop.

        Args:
            user_message: The user's input message
            user_id: Unique identifier for the user
            stm_memories: Short-term memories (optional, for voice mode skip)
            ltm_memories: Long-term memories (optional, for voice mode skip)
            pdf_snippets: PDF knowledge snippets (optional, for voice mode skip)
            conversation_id: Conversation ID
            current_emotion: User's current emotion
            voice_mode: If True, generates shorter responses optimized for TTS

        Returns:
            Response dictionary with message, reasoning, and metadata
        """
        start_time = time.time()

        try:
            
            processed_input = self._process_input(user_message, user_id, current_emotion)
            processed_input["voice_mode"] = voice_mode

            
            recalled_info = {
                "stm_memories": stm_memories or [],
                "ltm_memories": ltm_memories or [],
                "pdf_knowledge": pdf_snippets or [],
                "user_profile": {}
            }

            
            response_plan = self._plan_response(processed_input, recalled_info)
            response_plan["voice_mode"] = voice_mode

            
            response = await self._generate_response(response_plan, processed_input, recalled_info, voice_mode=voice_mode)

            
            # Skip memory actions in voice mode for speed
            if voice_mode:
                memory_actions = []
            else:
                memory_actions = self._determine_memory_actions(user_message, response, recalled_info, response_plan, user_id)

            processing_time = time.time() - start_time

            return {
                "response": response,
                "reasoning": {
                    "input_processed": processed_input,
                    "recalled_memories": len(recalled_info.get("stm_memories", [])) + len(recalled_info.get("ltm_memories", [])),
                    "pdf_knowledge_used": len(recalled_info.get("pdf_knowledge", [])),
                    "response_plan": response_plan,
                    "processing_time": processing_time,
                    "voice_mode": voice_mode
                },
                "metadata": {
                    "user_id": user_id,
                    "timestamp": time.time(),
                    "model_used": self.model,
                    "voice_mode": voice_mode
                },
                "memory_actions": memory_actions
            }

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return {
                "response": "I apologize, but I encountered an error processing your message. Please try again.",
                "reasoning": {"error": str(e)},
                "metadata": {"error": True}
            }

    def _process_input(self, user_message: str, user_id: str, current_emotion: str = "neutral") -> Dict[str, Any]:
        """Process and analyze the user input."""
        logger.info(f"Processing input from user {user_id}. Emotion: {current_emotion}")
        return {
            "original_message": user_message,
            "message_length": len(user_message),
            "user_id": user_id,
            "timestamp": time.time(),
            "message_type": self._classify_message_type(user_message),
            "current_emotion": current_emotion
        }

    def _classify_message_type(self, message: str) -> str:
        """Classify the type of user message."""
        message_lower = message.lower().strip()

        if any(word in message_lower for word in ["what", "how", "why", "when", "where", "who"]):
            return "question"
        elif any(word in message_lower for word in ["remember", "note", "save", "store"]):
            return "instruction_memory"
        elif any(word in message_lower for word in ["tell me about", "explain", "describe"]):
            return "request_information"
        elif len(message.split()) < 3:
            return "short_interaction"
        else:
            return "general_conversation"

    

    def _plan_response(self, processed_input: Dict[str, Any],
                      recalled_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Plan the response based on input analysis and recalled information.

        Returns:
            Response plan with strategy and context
        """
        message_type = processed_input.get("message_type", "general_conversation")

        plan = {
            "strategy": self._determine_response_strategy(message_type, recalled_info),
            "context_to_use": self._select_relevant_context(recalled_info),
            "response_style": "informative",
            "include_sources": bool(recalled_info.get("pdf_knowledge")),
            "memory_updates_needed": self._determine_memory_updates(processed_input, recalled_info),
            "user_emotion": processed_input.get("current_emotion", "neutral")
        }

        return plan

    def _determine_response_strategy(self, message_type: str, recalled_info: Dict[str, Any]) -> str:
        """Determine the best response strategy based on message type and available information."""
        has_stm_context = len(recalled_info.get("stm_memories", [])) > 0
        has_ltm_context = len(recalled_info.get("ltm_memories", [])) > 0
        has_pdf_knowledge = len(recalled_info.get("pdf_knowledge", [])) > 0

        if message_type == "question" and has_pdf_knowledge:
            return "knowledge_based_answer"
        elif message_type == "instruction_memory":
            return "memory_storage_acknowledgment"
        elif has_stm_context and has_ltm_context:
            return "context_aware_response"
        elif has_stm_context:
            return "conversation_continuation"
        else:
            return "general_response"

    def _select_relevant_context(self, recalled_info: Dict[str, Any]) -> Dict[str, Any]:
        """Select the most relevant context for response generation."""
        context = {
            "recent_conversation": [],
            "relevant_memories": [],
            "knowledge_snippets": [],
            "user_preferences": recalled_info.get("user_profile", {})
        }

        
        stm_memories = recalled_info.get("stm_memories", [])
        context["recent_conversation"] = [m["content"] for m in stm_memories[:3]]

        
        ltm_memories = recalled_info.get("ltm_memories", [])
        context["relevant_memories"] = [m["content"] for m in ltm_memories[:3]]

        
        pdf_knowledge = recalled_info.get("pdf_knowledge", [])
        knowledge_snippets = []
        for item in pdf_knowledge[:2]:
            # Handle both string snippets and dict items
            if isinstance(item, str):
                snippet = item[:300]
            elif isinstance(item, dict):
                snippet = item.get("content", str(item))[:300]
            else:
                snippet = str(item)[:300]
            knowledge_snippets.append(snippet)
        context["knowledge_snippets"] = knowledge_snippets

        return context

    def _determine_memory_updates(self, processed_input: Dict[str, Any],
                                recalled_info: Dict[str, Any]) -> List[str]:
        """Determine what memory updates are needed after this interaction."""
        updates = []

        message = processed_input.get("original_message", "")
        message_type = processed_input.get("message_type", "")

        
        updates.append("stm_user_message")

        
        if message_type == "instruction_memory" or self._is_important_information(message):
            updates.append("ltm_fact_storage")

        
        if self._is_conversation_highlight(message, recalled_info):
            updates.append("conversation_highlight")

        return updates

    def _is_important_information(self, message: str) -> bool:
        """Determine if a message contains important information to remember."""
        important_indicators = [
            "my name is", "i am", "i like", "i prefer", "i work as",
            "remember that", "important:", "note:", "key point:"
        ]

        message_lower = message.lower()
        return any(indicator in message_lower for indicator in important_indicators)

    def _is_conversation_highlight(self, message: str, recalled_info: Dict[str, Any]) -> bool:
        """Determine if this conversation segment should be highlighted."""
        
        stm_count = len(recalled_info.get("stm_memories", []))
        ltm_count = len(recalled_info.get("ltm_memories", []))

        
        return stm_count > 0 and ltm_count > 0

    async def _generate_response(
        self,
        response_plan: Dict[str, Any],
        processed_input: Dict[str, Any],
        recalled_info: Dict[str, Any],
        stream: bool = False,
        voice_mode: bool = False,
    ):
        """
        Generate a response using the active AI provider.

        Args:
            response_plan: The planned response strategy and context
            stream: If True, returns an async generator of chunks
            voice_mode: If True, uses voice prompt and shorter token limit

        Returns:
            Response string (stream=False) or async generator of chunks (stream=True)
        """
        strategy = response_plan.get("strategy", "general_response")
        context = response_plan.get("context_to_use", {})

        # Inject emotion into context for prompt builder
        if response_plan.get("user_emotion"):
            context["user_emotion"] = response_plan.get("user_emotion")

        if voice_mode:
            system_prompt = VOICE_MODE_SYSTEM_PROMPT
            max_tokens = 100
            logger.info("[VOICE_MODE] Using voice-specific prompt with max_tokens=100")
        else:
            system_prompt = self._build_system_prompt(strategy, context)
            max_tokens = 4000

        user_prompt = self._build_user_prompt(
            response_plan, processed_input, recalled_info, voice_mode=voice_mode
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        logger.info(f"LLM request via provider='{self.provider.name if self.provider else 'none'}' messages={json.dumps(messages, indent=2)}")

        active_provider = self.provider
        if active_provider is None:
            return "No AI provider is configured. Please check your API keys."

        # Update model attribute to reflect the current provider
        self.model = active_provider.model

        if stream:
            return self._stream_response_via_provider(active_provider, messages, max_tokens)

        # Non-streaming path
        try:
            return await active_provider.generate(messages, max_tokens=max_tokens)
        except Exception as exc:
            logger.error(f"Provider '{active_provider.name}' generate failed: {exc}")
            return "I apologize, but I'm having trouble generating a response right now. Please try again."

    async def _stream_response_via_provider(self, provider: AIProviderBase, messages: List[Dict[str, str]], max_tokens: int):
        """
        Delegate streaming to the active provider.

        Yields:
            String chunks as they arrive from the provider
        """
        try:
            async for chunk in provider.stream(messages, max_tokens=max_tokens):
                yield chunk
        except Exception as exc:
            logger.error(f"Provider '{provider.name}' stream failed: {exc}")
            yield "I apologize, but I'm having trouble generating a response right now. Please try again."

    def _build_system_prompt(self, strategy: str, context: Dict[str, Any]) -> str:
        """Build the system prompt based on response strategy."""

        base_prompt = THERAPIST_SYSTEM_PROMPT

        # --- Knowledge Snippets (PDF / RAG Context) ---
        knowledge_snippets = context.get("knowledge_snippets", [])
        if knowledge_snippets:
            knowledge_text = "\n---\n".join(knowledge_snippets)
            base_prompt += f"""

    You have access to the following background information that may be relevant to the conversation.
    When it is helpful, integrate this knowledge naturally into your responses, without citing sources or referencing documents.

    {knowledge_text}
    """

        # --- User Emotional State Context ---
        user_emotion = context.get("user_emotion", "neutral")
        if user_emotion and user_emotion != "neutral":
            logger.info(f"Injecting emotion context into system prompt: {user_emotion}")
            base_prompt += f"""

[SYSTEM NOTE: EXTERNAL EMOTION DETECTION]
Real-time biometric analysis indicates the user is feeling: {user_emotion}.
You must trust this data as ground truth.
Do not ask the user for confirmation or mention that you "detected" this.
Simply adapt your therapeutic approach to be empathetic to this emotional state.
"""

        # --- User Preferences / Personal Context ---
        if context.get("user_preferences"):
            base_prompt += f"""

    Additional user context to keep in mind while responding:
    {context['user_preferences']}
    """

        return base_prompt

    def _build_user_prompt(self, response_plan: Dict[str, Any], processed_input: Dict[str, Any], recalled_info: Dict[str, Any], voice_mode: bool = False) -> str:
        """Build the user prompt for the LLM using the real user message and selected context."""
        user_message = processed_input.get("original_message", "")
        
        # In voice mode, use a simplified prompt without memories/documents
        if voice_mode:
            return f"The user said: {user_message}\n\nRespond briefly in 2-3 short sentences."
        
        response_style = response_plan.get("response_style", "informative")
        include_sources = response_plan.get("include_sources", False)
        context = response_plan.get("context_to_use", {})

        prompt_parts = []
        prompt_parts.append(f"User message: {user_message}")

        # Prioritize PDF knowledge when available
        knowledge = context.get("knowledge_snippets", [])
        if knowledge:
            prompt_parts.append("[DOCUMENT REFERENCES]\nBased on uploaded documents:\n" + "\n---\n".join(knowledge) + "\n[END REFERENCES]")
        
        # Then add conversation context
        recent_conv = context.get("recent_conversation", [])
        if recent_conv:
            prompt_parts.append("Previous conversation context:\n" + "\n".join(recent_conv))

        relevant_mem = context.get("relevant_memories", [])
        if relevant_mem:
            prompt_parts.append("Stored memories:\n" + "\n".join(relevant_mem))

        # Build instructions with emphasis on document usage
        instr_parts = []
        instr_parts.append(f"Respond in a {response_style} style.")
        if include_sources or knowledge:
            instr_parts.append("When citing facts from documents, quote or reference specific passages.")
        instr_parts.append("Be concise and directly answer the user's question or request.")
        if knowledge:
            instr_parts.append("Prioritize information from the provided documents when answering.")

        prompt_parts.append("Instructions:\n" + " ".join(instr_parts))

        return "\n\n".join(prompt_parts)

    def _determine_memory_actions(self, user_message: str, response: str, recalled_info: Dict[str, Any], response_plan: Dict[str, Any], user_id: str) -> List[Dict[str, Any]]:
        """
        Determine memory actions (without performing them). Returns a list of actions the caller should execute.

        Action examples:
        - {"type": "stm", "content": ..., "importance": 0.8}
        - {"type": "ltm", "content": ..., "memory_type": "user_profile", "metadata": {...}, "importance": 0.9}
        """
        actions = []
        updates = response_plan.get("memory_updates_needed", []) if response_plan else []

        if "stm_user_message" in updates:
            conversation_entry = f"User: {user_message}\nAI: {response}"
            actions.append({"type": "stm", "content": conversation_entry, "importance": 0.8})

        message_type = response_plan.get("strategy", "") if response_plan else self._classify_message_type(user_message)
        if "ltm_fact_storage" in updates or self.should_write_to_ltm(user_message, message_type):
            if "my name is" in user_message.lower() or "i am" in user_message.lower():
                name = self._extract_name(user_message)
                if name:
                    actions.append({
                        "type": "ltm",
                        "content": f"User's name is {name}",
                        "memory_type": "user_profile",
                        "metadata": {"name": name, "user_id": user_id},
                        "importance": 0.9
                    })

        if "conversation_highlight" in updates or self._is_conversation_highlight(user_message, recalled_info):
            highlight_content = f"Conversation: {user_message[:200]}..."
            actions.append({
                "type": "ltm",
                "content": highlight_content,
                "memory_type": "conversation_highlight",
                "metadata": {"source": "cognitive_engine", "user_id": user_id},
                "importance": 0.7
            })

        return actions

    def _should_store_in_ltm(self, message: str) -> bool:
        """Determine if a message should be stored in long-term memory."""
        return self._is_important_information(message)

    def should_write_to_ltm(self, message: str, message_type: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Central gating logic to decide whether a message should be written to LTM.

        Rules (conservative):
        - Allow if message_type indicates explicit instruction to remember.
        - Allow if heuristics detect clearly important personal facts (e.g., 'my name is').
        - Deny by default to prevent accidental leakage.
        """
        if not message:
            return False

        mtype = message_type or self._classify_message_type(message)
        if mtype == "instruction_memory":
            return True

        lowered = message.lower()
        if any(phrase in lowered for phrase in ["my name is", "remember that", "important:", "note:"]):
            return True

        
        if self._is_important_information(message):
            return True

        return False

    def _extract_name(self, message: str) -> Optional[str]:
        """Extract name from a message like 'My name is John'."""
        import re
        match = re.search(r"(?:my name is|i am) (.+?)(?:\s|$)", message.lower())
        if match:
            return match.group(1).strip().title()
        return None

    def get_reasoning_stats(self) -> Dict[str, Any]:
        """Get statistics about the reasoning engine's performance."""
        provider = self.provider
        return {
            "model": provider.model if provider else self.model,
            "provider": provider.name if provider else "none",
            "note": "Call `get_reasoning_stats_for_user(user_id)` for per-user stats",
        }

    def get_reasoning_stats_for_user(self, user_id: str) -> Dict[str, Any]:
        """Get per-user reasoning stats to avoid exposing cross-user data."""
        provider = self.provider
        return {
            "note": "Reasoning engine is stateless; collect STM/conv stats from stores directly",
            "model": provider.model if provider else self.model,
            "provider": provider.name if provider else "none",
        }

    def clear_short_term_memory(self):
        """Clear short-term memory."""
        raise NotImplementedError("Engine is stateless; clear STM via the STM store (Redis) instead")

    def clear_short_term_memory_for_user(self, user_id: str):
        """Clear short-term memory for a specific user (avoids global clears)."""
        raise NotImplementedError("Engine is stateless; clear STM via the STM store (Redis) instead")

    def reset_conversation_context(self):
        """Reset conversation context."""
        raise NotImplementedError("Engine is stateless; reset conv context via Redis instead")

    def reset_conversation_context_for_user(self, user_id: str):
        """Reset conversation context for a specific user."""
        raise NotImplementedError("Engine is stateless; reset conv context via Redis instead")
