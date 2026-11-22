"""Voice agent prototype (OpenAI Agents SDK voice pipeline).

Standalone for now: it is not wired into the FastAPI app.
Requires `pip install -r requirements-voice.txt` and the OPENAI_API_KEY env var.

Run: .venv/Scripts/python -m app.voice_agent
"""

import asyncio

import numpy as np
from agents import Agent, function_tool
from agents.voice import AudioInput, SingleAgentVoiceWorkflow, VoicePipeline


@function_tool
def get_weather(city: str) -> str:
    """Get the weather for a given city."""
    return f"The weather in {city} is sunny."


agent = Agent(
    name="Assistant",
    instructions="You are a helpful voice assistant.",
    model="gpt-6.2-astra",
    tools=[get_weather],
)


async def main() -> None:
    pipeline = VoicePipeline(workflow=SingleAgentVoiceWorkflow(agent))
    # 3 seconds of silence at 24 kHz as placeholder input.
    audio_input = AudioInput(buffer=np.zeros(24000 * 3, dtype=np.int16))
    result = await pipeline.run(audio_input)
    async for event in result.stream():
        if event.type == "voice_stream_event_audio":
            print("Received audio bytes", event.data.nbytes)


if __name__ == "__main__":
    asyncio.run(main())
