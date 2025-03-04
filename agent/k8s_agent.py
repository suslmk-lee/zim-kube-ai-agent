"""
Kubernetes AI Agent for processing natural language queries about K8s resources.
"""
import re
import json
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from langchain.chains import LLMChain
from langchain.memory import ConversationBufferMemory
import os
from dotenv import load_dotenv

from k8s.operations import K8sOperations
from utils.neo4j_utils import Neo4jDatabase
from utils.text2cypher import Text2Cypher

# Load environment variables
load_dotenv()

class K8sAgent:
    """
    Agent for processing natural language queries about Kubernetes resources.
    """
    def __init__(self, use_neo4j=False):
        """
        Initialize the K8s agent.
        
        Args:
            use_neo4j: Whether to use Neo4j database (default: False)
        """
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        
        # Initialize the language model
        self.llm = ChatOpenAI(
            model_name="gpt-4o-mini",
            temperature=0.2,
            openai_api_key=openai_api_key
        )
        
        # Initialize conversation memory
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True
        )
        
        # Define the prompt template for query classification
        self.classify_prompt = PromptTemplate(
            input_variables=["query", "chat_history"],
            template="""
            You are an AI assistant that classifies user queries about Kubernetes resources.
            
            Based on the following query and chat history, determine the type of operation the user wants to perform.
            
            Chat History:
            {chat_history}
            
            User Query: "{query}"
            
            Classify the query into ONE of the following categories:
            1. GET_NAMESPACE_INFO - User wants information about namespaces
            2. GET_RESOURCE_USAGE - User wants to know which pods or deployments are using the most resources
            3. SCALE_DEPLOYMENT - User wants to scale a deployment
            4. UNKNOWN - User query doesn't match any of the above categories
            
            For GET_NAMESPACE_INFO, extract the cluster name if mentioned.
            For GET_RESOURCE_USAGE, extract the namespace name.
            For SCALE_DEPLOYMENT, extract the namespace, deployment name, and scale factor.
            
            Return your response in the following JSON format:
            {{
                "category": "CATEGORY_NAME",
                "parameters": {{
                    "cluster_name": "extracted_cluster_name",  // Only for GET_NAMESPACE_INFO
                    "namespace": "extracted_namespace",  // For GET_RESOURCE_USAGE and SCALE_DEPLOYMENT
                    "deployment_name": "extracted_deployment_name",  // Only for SCALE_DEPLOYMENT
                    "scale_factor": 2.0  // Only for SCALE_DEPLOYMENT, numeric value
                }}
            }}
            
            Only include parameters that are relevant to the category and that you can extract from the query.
            """
        )
        
        # Create the classification chain using modern approach
        self.classify_chain = self.classify_prompt | self.llm
        
        # Define the prompt template for response generation
        self.response_prompt = PromptTemplate(
            input_variables=["query", "result", "chat_history"],
            template="""
            You are an AI assistant that helps users manage Kubernetes resources.
            
            Based on the following user query and the result of the operation, generate a helpful response.
            
            Chat History:
            {chat_history}
            
            User Query: "{query}"
            
            Operation Result: {result}
            
            Generate a concise, informative response that answers the user's query based on the operation result.
            Explain what was done and provide the key information the user asked for.
            """
        )
        
        # Create the response chain using modern approach
        self.response_chain = self.response_prompt | self.llm
        
        # Initialize K8s operations
        self.k8s_ops = K8sOperations()
        
        # Initialize Neo4j database and Text2Cypher if needed
        self.use_neo4j = use_neo4j
        if self.use_neo4j:
            try:
                self.neo4j_db = Neo4jDatabase()
                self.text2cypher = Text2Cypher()
                
                # Create Neo4j schema if it doesn't exist
                self.neo4j_db.create_k8s_graph_schema()
            except Exception as e:
                print(f"Warning: Failed to initialize Neo4j: {str(e)}")
                self.use_neo4j = False
                self.neo4j_db = None
                self.text2cypher = None
        else:
            self.neo4j_db = None
            self.text2cypher = None
    
    def process_query(self, query):
        """
        Process a natural language query about Kubernetes resources.
        
        Args:
            query: Natural language query from the user
            
        Returns:
            Response to the user's query
        """
        # Get chat history from memory
        chat_history = self.memory.load_memory_variables({}).get("chat_history", "")
        
        # Classify the query
        classification_result = self.classify_chain.invoke({"query": query, "chat_history": chat_history})
        classification = self._parse_classification(classification_result.content)
        
        # Process the query based on its category
        if classification["category"] == "GET_NAMESPACE_INFO":
            result = self._handle_namespace_info(classification["parameters"].get("cluster_name", "cluster1"))
        elif classification["category"] == "GET_RESOURCE_USAGE":
            result = self._handle_resource_usage(classification["parameters"].get("namespace"))
        elif classification["category"] == "SCALE_DEPLOYMENT":
            result = self._handle_scale_deployment(
                classification["parameters"].get("namespace"),
                classification["parameters"].get("deployment_name"),
                classification["parameters"].get("scale_factor", 2.0)
            )
        else:
            result = {"error": "I couldn't understand what you're asking for. Please try rephrasing your query."}
        
        # Generate a response based on the result
        response = self.response_chain.invoke({
            "query": query, 
            "result": str(result), 
            "chat_history": chat_history
        })
        
        # Save the interaction to memory
        self.memory.save_context(
            {"input": query},
            {"output": response.content}
        )
        
        return response.content
    
    def _parse_classification(self, classification_text):
        """
        Parse the classification result from the LLM.
        
        Args:
            classification_text: Text containing the classification JSON
            
        Returns:
            Dictionary with the parsed classification
        """
        # Extract JSON from the text using regex
        json_match = re.search(r'\{.*\}', classification_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass
        
        # Fallback to a simple parsing approach
        category_match = re.search(r'"category":\s*"([^"]+)"', classification_text)
        category = category_match.group(1) if category_match else "UNKNOWN"
        
        parameters = {}
        
        # Extract cluster_name for GET_NAMESPACE_INFO
        if category == "GET_NAMESPACE_INFO":
            cluster_match = re.search(r'"cluster_name":\s*"([^"]+)"', classification_text)
            if cluster_match:
                parameters["cluster_name"] = cluster_match.group(1)
        
        # Extract namespace for GET_RESOURCE_USAGE and SCALE_DEPLOYMENT
        if category in ["GET_RESOURCE_USAGE", "SCALE_DEPLOYMENT"]:
            namespace_match = re.search(r'"namespace":\s*"([^"]+)"', classification_text)
            if namespace_match:
                parameters["namespace"] = namespace_match.group(1)
        
        # Extract deployment_name and scale_factor for SCALE_DEPLOYMENT
        if category == "SCALE_DEPLOYMENT":
            deployment_match = re.search(r'"deployment_name":\s*"([^"]+)"', classification_text)
            if deployment_match:
                parameters["deployment_name"] = deployment_match.group(1)
            
            scale_match = re.search(r'"scale_factor":\s*([\d.]+)', classification_text)
            if scale_match:
                parameters["scale_factor"] = float(scale_match.group(1))
        
        return {
            "category": category,
            "parameters": parameters
        }
    
    def _handle_namespace_info(self, cluster_name):
        """
        Handle a request for namespace information.
        
        Args:
            cluster_name: Name of the cluster
            
        Returns:
            Dictionary with namespace information
        """
        # Get namespace information from K8s
        namespace_info = self.k8s_ops.get_namespace_info(cluster_name)
        
        # Store the information in Neo4j if available
        graph_result = []
        cypher_query = ""
        if self.use_neo4j and self.neo4j_db:
            try:
                self.neo4j_db.store_namespace_info(namespace_info)
                
                # Get Cypher query for retrieving namespace information
                cypher_query = self.text2cypher.get_cypher_for_namespace_info(cluster_name)
                
                # Execute the Cypher query
                graph_result = self.neo4j_db.execute_query(cypher_query)
            except Exception as e:
                print(f"Warning: Neo4j operation failed: {str(e)}")
        
        # Combine results
        result = {
            "namespace_info": namespace_info
        }
        
        if self.use_neo4j:
            result.update({
                "graph_query": cypher_query,
                "graph_result": graph_result
            })
        
        return result
    
    def _handle_resource_usage(self, namespace):
        """
        Handle a request for resource usage information.
        
        Args:
            namespace: Name of the namespace
            
        Returns:
            Dictionary with resource usage information
        """
        if not namespace:
            return {"error": "Namespace not specified or not found in the query"}
        
        # Get resource usage information from K8s
        resource_usage = self.k8s_ops.get_resource_usage(namespace)
        
        # Store the information in Neo4j if available
        graph_result = []
        cypher_query = ""
        if self.use_neo4j and self.neo4j_db:
            try:
                self.neo4j_db.store_resource_usage(namespace, resource_usage)
                
                # Get Cypher query for retrieving resource usage information
                cypher_query = self.text2cypher.get_cypher_for_resource_usage(namespace)
                
                # Execute the Cypher query
                graph_result = self.neo4j_db.execute_query(cypher_query)
            except Exception as e:
                print(f"Warning: Neo4j operation failed: {str(e)}")
        
        # Combine results
        result = {
            "resource_usage": resource_usage
        }
        
        if self.use_neo4j:
            result.update({
                "graph_query": cypher_query,
                "graph_result": graph_result
            })
        
        return result
    
    def _handle_scale_deployment(self, namespace, deployment_name, scale_factor):
        """
        Handle a request to scale a deployment.
        
        Args:
            namespace: Name of the namespace
            deployment_name: Name of the deployment
            scale_factor: Factor by which to scale the deployment
            
        Returns:
            Dictionary with scaling result information
        """
        if not namespace or not deployment_name:
            return {"error": "Namespace or deployment name not specified or not found in the query"}
        
        # Scale the deployment
        scaling_result = self.k8s_ops.scale_deployment(namespace, deployment_name, scale_factor)
        
        # Store the scaling result in Neo4j if available
        graph_result = []
        cypher_query = ""
        if self.use_neo4j and self.neo4j_db:
            try:
                self.neo4j_db.store_scaling_result(scaling_result)
                
                # Get Cypher query for retrieving deployment information
                cypher_query = self.text2cypher.get_cypher_for_deployment_info(namespace, deployment_name)
                
                # Execute the Cypher query
                graph_result = self.neo4j_db.execute_query(cypher_query)
            except Exception as e:
                print(f"Warning: Neo4j operation failed: {str(e)}")
        
        # Combine results
        result = {
            "scaling_result": scaling_result
        }
        
        if self.use_neo4j:
            result.update({
                "graph_query": cypher_query,
                "graph_result": graph_result
            })
        
        return result
