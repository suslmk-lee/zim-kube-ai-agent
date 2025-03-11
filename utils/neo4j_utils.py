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
            "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Deployment) REQUIRE d.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Pod) REQUIRE p.name IS UNIQUE"
        ]
        
        for constraint in constraints:
            try:
                self.execute_query(constraint)
            except Exception as e:
                print(f"Warning: Failed to create constraint: {str(e)}")
                
        # Create indexes for namespace-scoped resources
        indexes = [
            "CREATE INDEX IF NOT EXISTS FOR (d:Deployment) ON (d.namespace)",
            "CREATE INDEX IF NOT EXISTS FOR (p:Pod) ON (p.namespace)"
        ]
        
        for index in indexes:
            try:
                self.execute_query(index)
            except Exception as e:
                print(f"Warning: Failed to create index: {str(e)}")
    
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
            # Create a unique identifier for the pod (name + namespace)
            pod_name = resource_usage["highest_cpu_pod"]["name"]
            pod_id = f"{pod_name}-{namespace}"
            
            self.execute_query(
                """
                MATCH (n:Namespace {name: $namespace})
                MERGE (p:Pod {name: $pod_name})
                SET p.namespace = $namespace,
                    p.pod_id = $pod_id,
                    p.cpu_usage = $cpu_usage
                MERGE (p)-[:BELONGS_TO]->(n)
                """,
                {
                    "namespace": namespace,
                    "pod_name": pod_name,
                    "pod_id": pod_id,
                    "cpu_usage": resource_usage["highest_cpu_pod"]["cpu_usage"]
                }
            )
        
        # Create or update deployment with highest CPU usage
        if resource_usage["highest_cpu_deployment"]["name"]:
            # Create a unique identifier for the deployment (name + namespace)
            deployment_name = resource_usage["highest_cpu_deployment"]["name"]
            deployment_id = f"{deployment_name}-{namespace}"
            
            self.execute_query(
                """
                MATCH (n:Namespace {name: $namespace})
                MERGE (d:Deployment {name: $deployment_name})
                SET d.namespace = $namespace,
                    d.deployment_id = $deployment_id,
                    d.cpu_usage = $cpu_usage
                MERGE (d)-[:BELONGS_TO]->(n)
                """,
                {
                    "namespace": namespace,
                    "deployment_name": deployment_name,
                    "deployment_id": deployment_id,
                    "cpu_usage": resource_usage["highest_cpu_deployment"]["cpu_usage"]
                }
            )
            
            # If the pod belongs to this deployment, create the relationship
            if (resource_usage["highest_cpu_pod"]["deployment"] == 
                resource_usage["highest_cpu_deployment"]["name"]):
                pod_name = resource_usage["highest_cpu_pod"]["name"]
                
                self.execute_query(
                    """
                    MATCH (p:Pod {name: $pod_name, namespace: $namespace})
                    MATCH (d:Deployment {name: $deployment_name, namespace: $namespace})
                    MERGE (p)-[:PART_OF]->(d)
                    """,
                    {
                        "namespace": namespace,
                        "pod_name": pod_name,
                        "deployment_name": deployment_name
                    }
                )
    
    def store_scaling_result(self, scaling_result):
        """
        Store deployment scaling information in the graph database.
        
        Args:
            scaling_result: Dictionary with scaling result information
        """
        deployment_name = scaling_result["deployment"]
        namespace = scaling_result["namespace"]
        
        self.execute_query(
            """
            MATCH (d:Deployment {name: $deployment_name, namespace: $namespace})
            SET d.replicas = $new_replicas,
                d.previous_replicas = $previous_replicas,
                d.last_scaled = datetime()
            """,
            {
                "namespace": namespace,
                "deployment_name": deployment_name,
                "new_replicas": scaling_result["new_replicas"],
                "previous_replicas": scaling_result["previous_replicas"]
            }
        )
    
    def get_namespace_resources(self, namespace):
        """
        Get all resources and their relationships in a namespace.
        
        Args:
            namespace: The namespace name to query
            
        Returns:
            Dictionary with resources and relationships data
        """
        # Check if namespace exists
        namespace_exists = self.execute_query(
            "MATCH (n:Namespace {name: $namespace}) RETURN n",
            {"namespace": namespace}
        )
        
        if not namespace_exists:
            return {"error": f"Namespace '{namespace}' not found in the database."}
        
        # Get all deployments in the namespace
        deployments = self.execute_query(
            """
            MATCH (d:Deployment {namespace: $namespace})
            RETURN d.name as name, 
                   d.replicas as replicas, 
                   d.cpu_usage as cpu_usage,
                   d.previous_replicas as previous_replicas,
                   d.last_scaled as last_scaled
            """,
            {"namespace": namespace}
        )
        
        # Get all pods in the namespace
        pods = self.execute_query(
            """
            MATCH (p:Pod {namespace: $namespace})
            RETURN p.name as name, 
                   p.cpu_usage as cpu_usage
            """,
            {"namespace": namespace}
        )
        
        # Get pod-to-deployment relationships
        relationships = self.execute_query(
            """
            MATCH (p:Pod {namespace: $namespace})-[r:PART_OF]->(d:Deployment)
            RETURN p.name as pod_name, d.name as deployment_name, type(r) as relationship_type
            """,
            {"namespace": namespace}
        )
        
        # Format the relationships for visualization
        formatted_relationships = []
        for rel in relationships:
            formatted_relationships.append({
                "source": rel.get("pod_name"),
                "target": rel.get("deployment_name"),
                "type": rel.get("relationship_type")
            })
        
        # Get other resource types if they exist (services, configmaps, etc.)
        # This can be expanded based on what resource types are stored in Neo4j
        services = self.execute_query(
            """
            MATCH (s:Service {namespace: $namespace})
            RETURN s.name as name, s.type as service_type, s.cluster_ip as cluster_ip
            """,
            {"namespace": namespace}
        )
        
        # Get service-to-deployment relationships if they exist
        service_relationships = self.execute_query(
            """
            MATCH (s:Service {namespace: $namespace})-[r:TARGETS]->(d:Deployment)
            RETURN s.name as service_name, d.name as deployment_name, type(r) as relationship_type
            """,
            {"namespace": namespace}
        )
        
        for rel in service_relationships:
            formatted_relationships.append({
                "source": rel.get("service_name"),
                "target": rel.get("deployment_name"),
                "type": rel.get("relationship_type")
            })
        
        return {
            "namespace": namespace,
            "resources": {
                "deployments": deployments,
                "pods": pods,
                "services": services
            },
            "relationships": formatted_relationships
        }
