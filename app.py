#!/usr/bin/env python3
"""
Main application entry point for the Kubernetes AI Agent.
"""
import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from agent.k8s_agent import K8sAgent
from utils.neo4j_utils import Neo4jDatabase

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(title="Kubernetes AI Agent")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Check if Neo4j is required
use_neo4j = os.getenv("USE_NEO4J", "false").lower() == "true"

# Initialize the K8s agent with Neo4j option
try:
    k8s_agent = K8sAgent(use_neo4j=use_neo4j)
except Exception as e:
    print(f"Warning: Failed to initialize K8s agent: {str(e)}")
    print("Starting app without K8s agent functionality. Some features may not work.")
    k8s_agent = None

class QueryRequest(BaseModel):
    query: str

@app.post("/api/query")
async def process_query(request: QueryRequest):
    """
    Process a natural language query about Kubernetes resources.
    """
    if k8s_agent is None:
        raise HTTPException(status_code=503, detail="K8s agent is not available")
    
    try:
        result = k8s_agent.process_query(request.query)
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """
    Health check endpoint.
    """
    status = "healthy" if k8s_agent is not None else "degraded"
    return {"status": status}

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
