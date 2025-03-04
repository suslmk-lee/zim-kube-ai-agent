"""
Text2Cypher utility for converting natural language to Cypher queries.
"""
import os
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from langchain.chains import LLMChain
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Text2Cypher:
    """
    Utility for converting natural language to Cypher queries using LangChain.
    """
    def __init__(self):
        """Initialize the Text2Cypher converter."""
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        
        # Initialize the language model
        self.llm = ChatOpenAI(
            model_name="gpt-4",
            temperature=0,
            openai_api_key=openai_api_key
        )
        
        # Define the prompt template for Text2Cypher conversion
        self.prompt_template = PromptTemplate(
            input_variables=["schema", "query"],
            template="""
            You are a Cypher query generator for a Neo4j graph database that stores Kubernetes resources.
            
            The graph schema is as follows:
            {schema}
            
            Convert the following natural language query into a Cypher query:
            "{query}"
            
            Return ONLY the Cypher query without any explanation or additional text.
            """
        )
        
        # Create the LLMChain
        self.chain = LLMChain(llm=self.llm, prompt=self.prompt_template)
        
        # Define the Kubernetes graph schema
        self.k8s_schema = """
        Nodes:
        - (Cluster): Represents a Kubernetes cluster
          Properties: name
        
        - (Namespace): Represents a Kubernetes namespace
          Properties: name, status, creation_time
        
        - (Deployment): Represents a Kubernetes deployment
          Properties: name, namespace, replicas, cpu_usage
        
        - (Pod): Represents a Kubernetes pod
          Properties: name, namespace, cpu_usage
        
        Relationships:
        - (Namespace)-[:BELONGS_TO]->(Cluster): Namespace belongs to a cluster
        - (Deployment)-[:BELONGS_TO]->(Namespace): Deployment belongs to a namespace
        - (Pod)-[:BELONGS_TO]->(Namespace): Pod belongs to a namespace
        - (Pod)-[:PART_OF]->(Deployment): Pod is part of a deployment
        """
    
    def convert_to_cypher(self, query):
        """
        Convert a natural language query to a Cypher query.
        
        Args:
            query: Natural language query
            
        Returns:
            Cypher query as a string
        """
        result = self.chain.invoke({"schema": self.k8s_schema, "query": query})
        return result["text"].strip()
    
    def get_cypher_for_namespace_info(self, cluster_name):
        """
        Get Cypher query for retrieving namespace information.
        
        Args:
            cluster_name: Name of the cluster
            
        Returns:
            Cypher query as a string
        """
        query = f"Show me all namespaces in the cluster named {cluster_name}"
        return self.convert_to_cypher(query)
    
    def get_cypher_for_resource_usage(self, namespace):
        """
        Get Cypher query for retrieving resource usage information.
        
        Args:
            namespace: Name of the namespace
            
        Returns:
            Cypher query as a string
        """
        query = f"Which pod and deployment in the {namespace} namespace is using the most CPU?"
        return self.convert_to_cypher(query)
    
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
        return self.convert_to_cypher(query)
