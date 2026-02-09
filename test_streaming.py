#!/usr/bin/env python3
"""Test streaming analyze endpoint with SSE visibility."""

import json
import time
from pathlib import Path

import httpx


def test_streaming_analyze(agent_file: Path):
    """Test the streaming analyze endpoint."""
    print(f"\n{'=' * 80}")
    print(f"Testing streaming analyze with: {agent_file.name}")
    print(f"{'=' * 80}\n")

    # Read agent content
    content = agent_file.read_text()
    print(f"✓ Read {len(content)} chars from {agent_file}")

    # Make streaming request
    url = "http://127.0.0.1:8000/api/stream/analyze"
    print(f"\n→ POST {url}")
    print(f"  Content: {len(content)} chars\n")

    start_time = time.time()
    phase_count = 0
    tool_count = 0
    thinking_count = 0

    with httpx.Client(timeout=120.0) as client:
        with client.stream(
            "POST",
            url,
            json={"content": content},
            headers={"Accept": "text/event-stream"},
        ) as response:
            if response.status_code != 200:
                print(f"✗ Request failed: {response.status_code}")
                print(response.text)
                return

            print("✓ Stream connected, receiving events...\n")

            buffer = ""
            current_event = None

            for chunk in response.iter_bytes():
                buffer += chunk.decode("utf-8")
                lines = buffer.split("\n")
                buffer = lines.pop()  # Keep incomplete line

                for line in lines:
                    if not line.strip() or line.startswith(":"):
                        continue

                    if line.startswith("event: "):
                        current_event = line[7:].strip()
                        continue

                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            elapsed = time.time() - start_time
                            print(f"\n{'=' * 80}")
                            print(f"✓ Stream complete in {elapsed:.1f}s")
                            print(f"  Phases: {phase_count}")
                            print(f"  Tools: {tool_count}")
                            print(f"  Thinking blocks: {thinking_count}")
                            print(f"{'=' * 80}\n")
                            return

                        try:
                            data = json.loads(data_str)

                            # Phase updates
                            if "phase" in data:
                                phase_count += 1
                                phase = data["phase"]
                                message = data.get("message", "")
                                agent = data.get("agent_name", "")
                                print(f"⚡ PHASE {phase_count}: {phase}")
                                print(f"  {message}")
                                if agent:
                                    print(f"  Agent: {agent}")
                                print()

                            # Tool events
                            elif "tool_name" in data:
                                if data.get("success") is not None:
                                    # tool:post
                                    tool_count += 1
                                    success = "✓" if data["success"] else "✗"
                                    preview = data.get("output_preview", "completed")
                                    print(f"{success} TOOL: {data['tool_name']} → {preview}")
                                else:
                                    # tool:pre
                                    print(f"→ TOOL: {data['tool_name']}")

                            # Thinking blocks
                            elif data.get("block_type") == "thinking":
                                thinking_count += 1
                                preview = data.get("content", "")[:80]
                                print(f"▸ THINKING: {preview}...")

                            # Final result
                            elif "metadata" in data:
                                print(f"\n{'=' * 80}")
                                print("📦 RESULT RECEIVED")
                                print(f"{'=' * 80}")
                                meta = data["metadata"]
                                print(f"  Name: {meta['name']}")
                                print(f"  Description: {meta['description'][:100]}...")
                                print(f"  Capabilities: {len(meta.get('capabilities', []))}")
                                print(f"  Similar agents: {len(data.get('similar_agents', []))}")
                                if data.get("similar_agents"):
                                    max_sim = max(
                                        s["similarity_score"] for s in data["similar_agents"]
                                    )
                                    print(f"  Highest similarity: {max_sim * 100:.1f}%")
                                print()

                            # Errors
                            elif "message" in data and current_event == "error":
                                print(f"✗ ERROR: {data['message']}")

                        except json.JSONDecodeError:
                            # Ignore unparseable data
                            pass


if __name__ == "__main__":
    test_agents_dir = Path("test_agents")

    if not test_agents_dir.exists():
        print("✗ test_agents/ directory not found")
        exit(1)

    # Test with first agent
    agents = sorted(test_agents_dir.glob("*.md"))
    if not agents:
        print("✗ No test agents found")
        exit(1)

    test_streaming_analyze(agents[0])
