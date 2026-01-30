
import asyncio
import os
import sys
from backend.reasoning import CognitiveReasoningEngine
from backend.memory.stm import STMManager

# Mock classes to avoid full initialization
class MockSTM:
    def get_relevant_memories(self, *args, **kwargs): return []
class MockLTM:
    def search_memories(self, *args, **kwargs): return []
    def add_memory(self, *args, **kwargs): pass
class MockPDF:
    def search_pdf_knowledge(self, *args, **kwargs): return []

async def test_emotion_injection():
    print("Testing emotion injection...")
    
    # Initialize engine with mocks
    engine = CognitiveReasoningEngine(
        stm_manager=MockSTM(),
        ltm_manager=MockLTM(),
        pdf_loader=MockPDF(),
        perplexity_api_key="mock_key", # Won't actually call API
        model="sonar"
    )
    
    # Monkey patch _generate_response to capture the plan without calling API
    async def mock_generate(response_plan, processed_input, recalled_info, stream=False):
        print("\n--- Response Plan ---")
        strategy = response_plan.get("strategy")
        print(f"Strategy: {strategy}")
        
        context = response_plan.get("context_to_use", {})
        emotion = context.get("user_emotion")
        print(f"Emotion in Context: {emotion}")
        
        # Build prompt to verify injection
        msg = engine._build_system_prompt(strategy, context)
        
        if "[SYSTEM NOTE: EXTERNAL EMOTION DETECTION]" in msg and "happy" in msg:
            print("\n✅ SUCCESS: Emotion injection prompt found in system message.")
        else:
            print("\n❌ FAILED: Emotion injection prompt NOT found.")
            print("System Prompt Snippet:", msg[-500:])
            
        return "mock_response"

    engine._generate_response = mock_generate
    
    # Run process_message
    await engine.process_message(
        user_message="Hello",
        user_id="test_user",
        current_emotion="happy" # THIS IS THE INPUT EMOTION
    )

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_emotion_injection())
