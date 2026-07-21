#!/usr/bin/env python3
"""
chat.py

PES University AI Kiosk terminal chat mode.
Allows interactive conversation with the CoordinatorAgent and downstream domain agents.
Supports conversation memory, clean production pipeline output, and a --debug mode.
"""

import argparse
import sys
import uuid
import logging
import warnings
import traceback
import os

# Parse --debug flag early to configure logging before any other module imports
debug_mode = "--debug" in sys.argv

# Ignore standard warnings
warnings.filterwarnings("ignore")

# Disable tqdm loading progress bars globally
os.environ["TQDM_DISABLE"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# Configure logging and redirect stderr early
if not debug_mode:
    # Open kiosk.log in append mode and redirect stderr to it
    try:
        log_file_handle = open("kiosk.log", "a", encoding="utf-8")
        sys.stderr = log_file_handle
    except Exception:
        pass

    # Route all warnings and errors silently to kiosk.log in production mode
    logging.basicConfig(
        filename='kiosk.log',
        level=logging.WARNING,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        force=True
    )
    # Clear stream/console handlers on root to prevent console leaks
    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        if not isinstance(handler, logging.FileHandler):
            root_logger.removeHandler(handler)
            
    # Silence popular third-party loggers
    for logger_name in ["chromadb", "urllib3", "google", "huggingface", "sentence_transformers"]:
        logging.getLogger(logger_name).setLevel(logging.ERROR)
else:
    # Developer/debug mode prints all details to console
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        force=True
    )

# Import agent pipeline after setup
from agents.coordinator.coordinator_agent import CoordinatorAgent

def main():
    parser = argparse.ArgumentParser(description="PES University Campus AI Kiosk Terminal Chat")
    parser.add_argument(
        "--debug", 
        action="store_true", 
        help="Run in debug mode to see routing, similarity scores, LLM used, etc."
    )
    args = parser.parse_args()

    # Clear terminal initialization line for cleaner display
    if args.debug:
        print("Initializing Campus AI Kiosk pipeline in DEBUG mode...")

    try:
        coordinator = CoordinatorAgent()
    except Exception as e:
        if args.debug:
            print("Error initializing CoordinatorAgent:")
            traceback.print_exc()
        else:
            logging.error(f"Error initializing CoordinatorAgent: {e}\n{traceback.format_exc()}")
            print("AI Kiosk pipeline initialization failed. Please check kiosk.log for details.")
        sys.exit(1)

    # Initial separator in normal mode
    if not args.debug:
        print("-" * 52)
    else:
        print("\nType 'exit' to quit the chat.\n")

    # Use a unique session ID for the terminal chat conversation history
    session_id = f"terminal_chat_{uuid.uuid4().hex[:8]}"

    while True:
        try:
            print("You:")
            query = input("> ").strip()
            if not query:
                continue
            if query.lower() == "exit":
                if args.debug:
                    print("\nGoodbye.")
                break
                
            print("\nAI:")
            
            # Query the coordinator agent under proper exception wrapping
            try:
                raw_response = coordinator.answer(query, session_id=session_id, debug=args.debug)
            except Exception as e:
                # Log the exception stack trace silently to file
                logging.error(f"Error handling query '{query}': {e}\n{traceback.format_exc()}")
                if args.debug:
                    traceback.print_exc()
                    raw_response = "Error occurred during query execution."
                else:
                    # Return contact details fallback or retrieved text silently
                    raw_response = "Answer:\nI couldn't process your request at this time. Please try again later.\n\nSources:\n    None"

            # Parse and format final output
            if not args.debug:
                clean_ans = raw_response
                if clean_ans.startswith("Answer:\n"):
                    clean_ans = clean_ans[len("Answer:\n"):]
                if "\n\nSources:\n    " in clean_ans:
                    clean_ans, _ = clean_ans.split("\n\nSources:\n    ", 1)
                print(clean_ans)
            else:
                print(raw_response)
                
            print("\n" + "-" * 52 + "\n")
            
        except (KeyboardInterrupt, EOFError):
            if args.debug:
                print("\nGoodbye.")
            break

if __name__ == "__main__":
    main()
