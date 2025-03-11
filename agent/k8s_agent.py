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
        
        # Initialize conversation memory using the updated approach
        from langchain_core.messages import HumanMessage, AIMessage
        from langchain_core.runnables.history import RunnableWithMessageHistory
        
        self.chat_history = []
        
        # Define the prompt template for query classification
        self.classify_prompt = PromptTemplate(
            input_variables=["query", "chat_history"],
            template="""
            You are a query classifier for a Kubernetes AI agent. Your task is to classify the user's query into one of the following categories:
            
            1. GET_NAMESPACE_INFO - User wants to get information about namespaces in a cluster
            2. GET_RESOURCE_USAGE - User wants to know which pods or deployments are using the most resources
            3. SCALE_DEPLOYMENT - User wants to scale a deployment
            4. VISUALIZE_RESOURCES - User wants to visualize relationships between resources in a namespace
            5. DESCRIBE_DEPLOYMENT - User wants to describe a deployment
            6. CREATE_NAMESPACE - User wants to create a new namespace
            7. UNKNOWN - User query doesn't match any of the above categories
            
            Pay special attention to CREATE_NAMESPACE requests. If the user asks to create, make, or establish a new namespace, classify it as CREATE_NAMESPACE.
            
            For GET_NAMESPACE_INFO, extract the cluster name if mentioned.
            For GET_RESOURCE_USAGE, extract the namespace name.
            For SCALE_DEPLOYMENT, extract the namespace, deployment name, and scale factor.
            For VISUALIZE_RESOURCES, extract the namespace name.
            For DESCRIBE_DEPLOYMENT, extract the namespace and deployment name.
            For CREATE_NAMESPACE, extract the namespace name to create.
            
            Return your response in the following JSON format:
            {{
                "category": "CATEGORY_NAME",
                "parameters": {{
                    "cluster_name": "extracted_cluster_name",  // Only for GET_NAMESPACE_INFO
                    "namespace": "extracted_namespace",  // For GET_RESOURCE_USAGE, SCALE_DEPLOYMENT, VISUALIZE_RESOURCES, DESCRIBE_DEPLOYMENT, and CREATE_NAMESPACE
                    "deployment_name": "extracted_deployment_name",  // Only for SCALE_DEPLOYMENT and DESCRIBE_DEPLOYMENT
                    "scale_factor": 2.0  // Only for SCALE_DEPLOYMENT, numeric value
                }}
            }}
            
            User Query: {query}
            
            Chat History: {chat_history}
            
            Classification:
            """
        )
        
        # Create the classification chain using modern approach
        self.classify_chain = self.classify_prompt | self.llm
        
        # Define the prompt template for response generation
        self.response_prompt = PromptTemplate(
            input_variables=["query", "result", "chat_history"],
            template="""
            You are an AI assistant for Kubernetes operations. Your task is to respond to user queries about Kubernetes resources based on the provided result.
            
            User Query: {query}
            
            Result: {result}
            
            Chat History: {chat_history}
            
            Guidelines:
            1. Be concise and informative in your response.
            2. If the result contains an error message, explain the error in a user-friendly way and suggest possible solutions.
            3. If the result contains data, present it in a clear and organized manner.
            4. If the result contains deployment description data, format it as markdown tables for better readability.
            5. For visualization data, explain what the visualization shows.
            6. Use appropriate Kubernetes terminology.
            7. Respond in the same language as the user query.
            
            When formatting deployment description as tables, use the following structure:
            
            Basic Info:
            | Field | Value |
            |-------|-------|
            | Name | [name] |
            | Namespace | [namespace] |
            | Creation Time | [creation_timestamp] |
            | Selector | [selector] |
            
            Replicas:
            | Type | Count |
            |------|-------|
            | Desired | [desired] |
            | Current | [current] |
            | Updated | [updated] |
            | Available | [available] |
            | Unavailable | [unavailable] |
            
            Containers:
            | Name | Image | Ports | Resource Requests | Resource Limits |
            |------|-------|-------|-------------------|----------------|
            | [name] | [image] | [ports] | [requests] | [limits] |
            
            Pods:
            | Name | Status | Ready | Restarts | Node | IP |
            |------|--------|-------|----------|------|---|
            | [pod_name] | [status] | [ready] | [restarts] | [node] | [ip] |
            
            Events:
            | Type | Reason | Message | Count | Last Seen |
            |------|--------|---------|-------|-----------|
            | [type] | [reason] | [message] | [count] | [last_seen] |
            
            Your response:
            """
        )
        
        # Create the response chain using modern approach
        self.response_chain = self.response_prompt | self.llm
        
        # Initialize K8s operations
        self.k8s_ops = K8sOperations()
        self.k8s_client = K8sOperations()  # Initialize k8s_client
        
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
        # Get chat history
        chat_history = "\n".join([f"User: {msg['input']}\nAI: {msg['output']}" 
                                 for msg in self.chat_history]) if self.chat_history else ""
        
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
        elif classification["category"] == "VISUALIZE_RESOURCES":
            result = self._handle_visualize_resources(classification["parameters"].get("namespace"))
        elif classification["category"] == "DESCRIBE_DEPLOYMENT":
            result = self._handle_describe_deployment(
                classification["parameters"].get("namespace"),
                classification["parameters"].get("deployment_name")
            )
        elif classification["category"] == "CREATE_NAMESPACE":
            result = self._handle_create_namespace(classification["parameters"].get("namespace"))
        else:
            result = {"error": "I couldn't understand what you're asking for. Please try rephrasing your query."}
        
        # Generate a response based on the result
        response = self.response_chain.invoke({
            "query": query, 
            "result": str(result), 
            "chat_history": chat_history
        })
        
        # Save the interaction to memory
        self.chat_history.append({"input": query, "output": response.content})
        
        return response.content
    
    def _parse_classification(self, classification_text):
        """
        Parse the classification result from the LLM.
        
        Args:
            classification_text: Classification text from the LLM
            
        Returns:
            Dictionary with category and parameters
        """
        try:
            # First try to extract JSON using regex
            import re
            import json
            
            json_match = re.search(r'\{.*\}', classification_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    pass
            
            # If JSON parsing fails, fall back to line-by-line parsing
            lines = classification_text.strip().split('\n')
            category = None
            parameters = {}
            
            for line in lines:
                line = line.strip()
                if line.startswith("Category:") or line.startswith('"category":'):
                    category_value = line.split(":", 1)[1].strip().strip('"').strip(',')
                    category = category_value
                elif ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip().strip('"').strip()
                    value = value.strip().strip('"').strip(',')
                    parameters[key.lower()] = value
            
            return {"category": category, "parameters": parameters}
        except Exception as e:
            print(f"Error parsing classification: {str(e)}")
            return {"category": "UNKNOWN", "parameters": {}}
    
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
            deployment_name: Name of the deployment to scale
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
    
    def _handle_visualize_resources(self, namespace):
        """
        Handle visualization of resources in a namespace.
        
        Args:
            namespace: The namespace to visualize
            
        Returns:
            Dictionary with visualization data or error message
        """
        if not namespace:
            return {"error": "Namespace not specified. Please provide a namespace name."}
            
        if not self.use_neo4j or not self.neo4j_db:
            return {"error": "Neo4j database is not available. Resource visualization requires Neo4j."}
            
        try:
            # Use the dedicated method in Neo4jDatabase for retrieving namespace resources
            if hasattr(self.neo4j_db, 'get_namespace_resources'):
                visualization_data = self.neo4j_db.get_namespace_resources(namespace)
                if "error" in visualization_data:
                    return visualization_data
                
                return {
                    "visualization_data": visualization_data,
                    "message": f"Successfully retrieved resource relationships for namespace '{namespace}'."
                }
            
            # Fallback to direct queries if the method doesn't exist
            # Query Neo4j for all resources in the namespace and their relationships
            cypher_query = """
            MATCH (n:Namespace {name: $namespace})
            OPTIONAL MATCH (d:Deployment)-[:BELONGS_TO]->(n)
            OPTIONAL MATCH (p:Pod)-[:BELONGS_TO]->(n)
            OPTIONAL MATCH (p:Pod)-[:PART_OF]->(d)
            RETURN n, collect(distinct d) as deployments, collect(distinct p) as pods
            """
            
            result = self.neo4j_db.execute_query(cypher_query, {"namespace": namespace})
            
            if not result or not result[0].get('n'):
                return {"error": f"Namespace '{namespace}' not found in the database."}
                
            # Format the result for visualization
            namespace_data = result[0]
            
            # Extract namespace info
            ns_info = {
                "name": namespace,
                "type": "Namespace"
            }
            
            # Extract deployment info
            deployments = []
            for d in namespace_data.get('deployments', []):
                if d:  # Check if deployment is not None
                    deployment_info = {
                        "name": d.get("name"),
                        "type": "Deployment",
                        "namespace": d.get("namespace"),
                        "cpu_usage": d.get("cpu_usage"),
                        "replicas": d.get("replicas")
                    }
                    deployments.append(deployment_info)
            
            # Extract pod info with relationships to deployments
            pods = []
            pod_relationships = []
            for p in namespace_data.get('pods', []):
                if p:  # Check if pod is not None
                    pod_info = {
                        "name": p.get("name"),
                        "type": "Pod",
                        "namespace": p.get("namespace"),
                        "cpu_usage": p.get("cpu_usage")
                    }
                    pods.append(pod_info)
                    
                    # Find relationship to deployment
                    deployment_rel_query = """
                    MATCH (p:Pod {name: $pod_name, namespace: $namespace})-[:PART_OF]->(d:Deployment)
                    RETURN d.name as deployment_name
                    """
                    deployment_rel = self.neo4j_db.execute_query(
                        deployment_rel_query, 
                        {"pod_name": p.get("name"), "namespace": namespace}
                    )
                    
                    if deployment_rel and deployment_rel[0].get('deployment_name'):
                        pod_relationships.append({
                            "source": p.get("name"),
                            "target": deployment_rel[0].get('deployment_name'),
                            "type": "PART_OF"
                        })
            
            # Combine all data for visualization
            visualization_data = {
                "namespace": ns_info,
                "resources": {
                    "deployments": deployments,
                    "pods": pods
                },
                "relationships": pod_relationships
            }
            
            return {
                "visualization_data": visualization_data,
                "message": f"Successfully retrieved resource relationships for namespace '{namespace}'."
            }
            
        except Exception as e:
            return {"error": f"Failed to visualize resources: {str(e)}"}
    
    def _handle_describe_deployment(self, namespace, deployment_name):
        """
        Handle describing a deployment in a specific namespace.
        
        Args:
            namespace: The namespace containing the deployment
            deployment_name: The name of the deployment to describe
            
        Returns:
            Dictionary with deployment description or error message
        """
        if not namespace or not deployment_name:
            return {"error": "Namespace and deployment name must be specified."}
            
        try:
            # Get the deployment description
            description = self.k8s_client.get_deployment_description(deployment_name, namespace)
            
            if "error" in description:
                return description
                
            # Format the description as a table-friendly structure
            formatted_description = {
                "basic_info": {
                    "Name": description["name"],
                    "Namespace": description["namespace"],
                    "CreationTimestamp": description["creation_timestamp"],
                    "Selector": ", ".join([f"{k}={v}" for k, v in description["selector"].items()]) if description["selector"] else "None"
                },
                "replicas": {
                    "Desired": description["replicas"]["desired"],
                    "Current": description["replicas"]["current"],
                    "Updated": description["replicas"]["updated"],
                    "Available": description["replicas"]["available"],
                    "Unavailable": description["replicas"]["unavailable"] if description["replicas"]["unavailable"] else 0
                },
                "strategy": {
                    "Type": description["strategy"]["type"],
                    "RollingUpdate": {
                        "MaxSurge": str(description["strategy"]["rolling_update"]["max_surge"]) if description["strategy"]["rolling_update"] and description["strategy"]["rolling_update"]["max_surge"] else "N/A",
                        "MaxUnavailable": str(description["strategy"]["rolling_update"]["max_unavailable"]) if description["strategy"]["rolling_update"] and description["strategy"]["rolling_update"]["max_unavailable"] else "N/A"
                    } if description["strategy"]["rolling_update"] else {"MaxSurge": "N/A", "MaxUnavailable": "N/A"}
                },
                "containers": [
                    {
                        "Name": container["name"],
                        "Image": container["image"],
                        "Ports": ", ".join([f"{p['container_port']}/{p['protocol']}" for p in container["ports"]]) if container["ports"] else "None",
                        "Resources": {
                            "Limits": ", ".join([f"{k}: {v}" for k, v in container["resources"]["limits"].items()]) if container["resources"]["limits"] else "None",
                            "Requests": ", ".join([f"{k}: {v}" for k, v in container["resources"]["requests"].items()]) if container["resources"]["requests"] else "None"
                        }
                    }
                    for container in description["containers"]
                ],
                "pods": [
                    {
                        "Name": pod["name"],
                        "Status": pod["status"],
                        "Ready": "Yes" if pod["ready"] else "No",
                        "Restarts": pod["restart_count"],
                        "Node": pod["node"] if pod["node"] else "N/A",
                        "IP": pod["ip"] if pod["ip"] else "N/A"
                    }
                    for pod in description["pods"]
                ],
                "events": [
                    {
                        "Type": event["type"],
                        "Reason": event["reason"],
                        "Message": event["message"],
                        "Count": event["count"],
                        "LastSeen": event["last_timestamp"]
                    }
                    for event in description["events"]
                ]
            }
            
            return {
                "deployment_description": formatted_description,
                "message": f"Successfully retrieved description for deployment '{deployment_name}' in namespace '{namespace}'."
            }
            
        except Exception as e:
            return {"error": f"Failed to describe deployment: {str(e)}"}
    
    def _handle_create_namespace(self, namespace):
        """
        Handle creating a new namespace.
        
        Args:
            namespace: The name of the namespace to create
            
        Returns:
            Dictionary with namespace information or error message
        """
        if not namespace:
            return {"error": "Namespace name must be specified."}
            
        try:
            # Create the namespace
            result = self.k8s_client.create_namespace(namespace)
            
            if "error" in result:
                return result
                
            return {
                "namespace_info": result,
                "message": f"Successfully created namespace '{namespace}'."
            }
            
        except Exception as e:
            return {"error": f"Failed to create namespace: {str(e)}"}
