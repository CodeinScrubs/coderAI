import sys
import argparse
import time

def main():
    parser = argparse.ArgumentParser(description="CoderAI TUI Mode")
    parser.add_argument("--cli", action="store_true", help="Run in CLI mode")
    args = parser.parse_args()

    if not args.cli:
        print("Please run with --cli")
        return

    from coderai.server import web_app
    from coderai.server.web_app import STATE, _build_final_system_prompt, _build_api_messages, _call_model, _handle_tool_call, _compact_memory_if_needed, _message_summary_line

    print("=========================================")
    print("        CoderAI CLI Mode (TUI)           ")
    print("=========================================")
    print("Welcome! Type your message to chat with the AI.")
    print("Type /exit to quit.\n")

    # Set up basic state
    STATE["memory_session_id"] = "cli_session"
    STATE["messages"] = []
    STATE["active_tools"] = ["run_command", "check_file_diagnostics"] # Add more as needed
    
    # Load settings if needed or use defaults
    STATE["temperature"] = 0.7
    STATE["enable_thinking"] = False
    
    while True:
        try:
            user_input = input("\n[You] > ")
            if user_input.strip().lower() in ["/exit", "exit", "quit"]:
                break
            if not user_input.strip():
                continue
            
            # 1. Add user message
            STATE["messages"].append({"role": "user", "content": user_input})
            
            # 2. Compact if needed
            _compact_memory_if_needed()
            
            # 3. Build messages
            final_system = _build_final_system_prompt()
            history = _build_api_messages(final_system)
            
            print("\n[AI] > ", end="", flush=True)
            
            # 4. Call model (we'll just use synchronous call for simplicity in CLI prototype)
            response = _call_model(history)
            
            content = response.get("content", "")
            if content:
                print(content)
                
            STATE["messages"].append({"role": "assistant", "content": content})
            
            tool_calls = response.get("tool_calls", [])
            for call in tool_calls:
                print(f"\n[AI Tool Call]: {call['name']}({call['arguments']})")
                # A proper TUI would ask for approval here
                try:
                    result = _handle_tool_call(call)
                    print(f"[Tool Result]:\n{result}")
                    STATE["messages"].append({"role": "tool", "content": str(result), "name": call["name"], "tool_call_id": call.get("id", "")})
                except Exception as e:
                    print(f"[Tool Error]: {e}")
                    STATE["messages"].append({"role": "tool", "content": str(e), "name": call["name"], "tool_call_id": call.get("id", "")})
                    
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"\nError: {e}")

if __name__ == '__main__':
    main()
