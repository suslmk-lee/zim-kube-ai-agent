#!/usr/bin/env python3
"""
Command-line interface for testing the Kubernetes AI Agent.
"""
import argparse
import os
from dotenv import load_dotenv

from agent.k8s_agent import K8sAgent

def main():
    """Main entry point for the CLI."""
    # Load environment variables
    load_dotenv()
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Kubernetes AI Agent CLI")
    parser.add_argument("query", nargs="?", help="Natural language query")
    parser.add_argument("--interactive", "-i", action="store_true", help="Run in interactive mode")
    args = parser.parse_args()
    
    # Initialize the agent
    agent = K8sAgent()
    
    if args.interactive:
        print("Kubernetes AI Agent CLI (Interactive Mode)")
        print("Type 'exit' or 'quit' to exit")
        print()
        
        while True:
            query = input("Query: ")
            if query.lower() in ["exit", "quit"]:
                break
            
            if query.strip():
                try:
                    response = agent.process_query(query)
                    print("\nResponse:")
                    print(response)
                    print()
                except Exception as e:
                    print(f"\nError: {str(e)}")
                    print()
    elif args.query:
        try:
            response = agent.process_query(args.query)
            print(response)
        except Exception as e:
            print(f"Error: {str(e)}")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
