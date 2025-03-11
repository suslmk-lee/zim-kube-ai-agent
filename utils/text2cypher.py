"""
Text2Cypher module for converting natural language to Cypher queries.
"""
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate

# Load environment variables
load_dotenv()

class Text2Cypher:
    """
    Text2Cypher converter for Neo4j.
    """
    def __init__(self):
        """Initialize the Text2Cypher converter."""
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        
        # Initialize the language model
        self.llm = ChatOpenAI(
            model_name="gpt-4o-mini",
            temperature=0.1,
            openai_api_key=openai_api_key
        )
        
        # Define the prompt template
        self.prompt_template = PromptTemplate(
            input_variables=["schema", "query"],
            template="""
            You are a Neo4j Cypher query generator. Your task is to convert natural language queries about Kubernetes resources into Cypher queries.
            
            Here is the schema of the Neo4j graph database:
            
            Nodes:
            - Cluster: Properties (name)
            - Namespace: Properties (name, status, creation_time)
            - Deployment: Properties (name, namespace, replicas, cpu_usage)
            - Pod: Properties (name, namespace, cpu_usage)
            
            Relationships:
            - (Namespace)-[:BELONGS_TO]->(Cluster)
            - (Deployment)-[:BELONGS_TO]->(Namespace)
            - (Pod)-[:BELONGS_TO]->(Namespace)
            - (Pod)-[:PART_OF]->(Deployment)
            
            Given the following natural language query, generate a Cypher query that will answer the question:
            
            Query: {query}
            
            Return only the Cypher query without any explanation or additional text.
            """
        )
        
        # Create the chain using the modern approach
        self.chain = self.prompt_template | self.llm
    
    def generate_cypher(self, query):
        """
        Generate a Cypher query from a natural language query.
        
        Args:
            query: Natural language query
            
        Returns:
            Cypher query
        """
        # Define the schema (could be dynamically generated in the future)
        schema = """
        Nodes:
        - Cluster: Properties (name)
        - Namespace: Properties (name, status, creation_time)
        - Deployment: Properties (name, namespace, replicas, cpu_usage)
        - Pod: Properties (name, namespace, cpu_usage)
        
        Relationships:
        - (Namespace)-[:BELONGS_TO]->(Cluster)
        - (Deployment)-[:BELONGS_TO]->(Namespace)
        - (Pod)-[:BELONGS_TO]->(Namespace)
        - (Pod)-[:PART_OF]->(Deployment)
        """
        
        # Generate the Cypher query
        result = self.chain.invoke({"schema": schema, "query": query})
        
        # Extract the Cypher query from the result
        cypher_query = result.content.strip()
        
        return cypher_query
    
    def get_cypher_for_namespace_info(self, cluster_name):
        """
        Get Cypher query for retrieving namespace information.
        
        Args:
            cluster_name: Name of the cluster
            
        Returns:
            Cypher query as a string
        """
        query = f"Show me all namespaces in the cluster named {cluster_name}"
        return self.generate_cypher(query)
    
    def get_cypher_for_resource_usage(self, namespace):
        """
        Get Cypher query for retrieving resource usage information.
        
        Args:
            namespace: Name of the namespace
            
        Returns:
            Cypher query as a string
        """
        query = f"Which pod and deployment in the {namespace} namespace is using the most CPU?"
        return self.generate_cypher(query)
    
    def get_cypher_for_deployment_info(self, namespace, deployment_name):
        """
        Get Cypher query for retrieving deployment information.
        
        Args:
            namespace: Name of the namespace
            deployment_name: Name of the deployment
            
        Returns:
            Cypher query as a string
        """
        query = f"Show me information about the deployment named {deployment_name} in the {namespace} namespace"
        return self.generate_cypher(query)
