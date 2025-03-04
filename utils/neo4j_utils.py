"""
Neo4j utilities for Text2Cypher integration.
"""
import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Neo4jDatabase:
    """
    Neo4j database client for Text2Cypher operations.
    """
    def __init__(self):
        """Initialize the Neo4j database connection."""
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        username = os.getenv("NEO4J_USERNAME", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "password")
        
        self.driver = GraphDatabase.driver(uri, auth=(username, password))
    
    def close(self):
        """Close the database connection."""
        self.driver.close()
    
    def execute_query(self, query, parameters=None):
        """
        Execute a Cypher query.
        
        Args:
            query: The Cypher query to execute
            parameters: Optional parameters for the query
            
        Returns:
            List of records from the query result
        """
        parameters = parameters or {}
        
        with self.driver.session() as session:
            result = session.run(query, parameters)
            return [record.data() for record in result]
    
    def create_k8s_graph_schema(self):
        """
        Create the Neo4j schema for Kubernetes resources.
        This sets up the graph structure for storing K8s resources.
        """
        # Create constraints for unique nodes
        constraints = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Cluster) REQUIRE c.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Namespace) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Deployment) REQUIRE (d.name, d.namespace) IS NODE KEY",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Pod) REQUIRE (p.name, p.namespace) IS NODE KEY"
        ]
        
        for constraint in constraints:
            self.execute_query(constraint)
    
    def store_namespace_info(self, namespace_info):
        """
        Store namespace information in the graph database.
        
        Args:
            namespace_info: Dictionary with namespace information
        """
        # Create cluster node if it doesn't exist
        self.execute_query(
            "MERGE (c:Cluster {name: $cluster_name})",
            {"cluster_name": "cluster1"}  # Default cluster name
        )
        
        # Create namespace nodes and relationships
        for ns in namespace_info["namespaces"]:
            self.execute_query(
                """
                MATCH (c:Cluster {name: $cluster_name})
                MERGE (n:Namespace {name: $ns_name})
                SET n.status = $status,
                    n.creation_time = $creation_time
                MERGE (n)-[:BELONGS_TO]->(c)
                """,
                {
                    "cluster_name": "cluster1",
                    "ns_name": ns["name"],
                    "status": ns["status"],
                    "creation_time": ns["creation_time"]
                }
            )
    
    def store_resource_usage(self, namespace, resource_usage):
        """
        Store resource usage information in the graph database.
        
        Args:
            namespace: The namespace name
            resource_usage: Dictionary with resource usage information
        """
        # Create or update pod with highest CPU usage
        if resource_usage["highest_cpu_pod"]["name"]:
            self.execute_query(
                """
                MATCH (n:Namespace {name: $namespace})
                MERGE (p:Pod {name: $pod_name, namespace: $namespace})
                SET p.cpu_usage = $cpu_usage
                MERGE (p)-[:BELONGS_TO]->(n)
                """,
                {
                    "namespace": namespace,
                    "pod_name": resource_usage["highest_cpu_pod"]["name"],
                    "cpu_usage": resource_usage["highest_cpu_pod"]["cpu_usage"]
                }
            )
        
        # Create or update deployment with highest CPU usage
        if resource_usage["highest_cpu_deployment"]["name"]:
            self.execute_query(
                """
                MATCH (n:Namespace {name: $namespace})
                MERGE (d:Deployment {name: $deployment_name, namespace: $namespace})
                SET d.cpu_usage = $cpu_usage
                MERGE (d)-[:BELONGS_TO]->(n)
                """,
                {
                    "namespace": namespace,
                    "deployment_name": resource_usage["highest_cpu_deployment"]["name"],
                    "cpu_usage": resource_usage["highest_cpu_deployment"]["cpu_usage"]
                }
            )
            
            # If the pod belongs to this deployment, create the relationship
            if (resource_usage["highest_cpu_pod"]["deployment"] == 
                resource_usage["highest_cpu_deployment"]["name"]):
                self.execute_query(
                    """
                    MATCH (p:Pod {name: $pod_name, namespace: $namespace})
                    MATCH (d:Deployment {name: $deployment_name, namespace: $namespace})
                    MERGE (p)-[:PART_OF]->(d)
                    """,
                    {
                        "namespace": namespace,
                        "pod_name": resource_usage["highest_cpu_pod"]["name"],
                        "deployment_name": resource_usage["highest_cpu_deployment"]["name"]
                    }
                )
    
    def store_scaling_result(self, scaling_result):
        """
        Store deployment scaling information in the graph database.
        
        Args:
            scaling_result: Dictionary with scaling result information
        """
        self.execute_query(
            """
            MATCH (d:Deployment {name: $deployment_name, namespace: $namespace})
            SET d.replicas = $new_replicas,
                d.previous_replicas = $previous_replicas,
                d.last_scaled = datetime()
            """,
            {
                "namespace": scaling_result["namespace"],
                "deployment_name": scaling_result["deployment"],
                "new_replicas": scaling_result["new_replicas"],
                "previous_replicas": scaling_result["previous_replicas"]
            }
        )
