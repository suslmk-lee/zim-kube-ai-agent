"""
Kubernetes operations module for executing commands on K8s clusters.
"""
from .client import K8sClient

class K8sOperations:
    """
    Operations for interacting with Kubernetes clusters.
    """
    def __init__(self):
        """Initialize the K8s operations with a client."""
        self.client = K8sClient()
    
    def get_namespace_info(self, cluster_name=None):
        """
        Get information about namespaces in the specified cluster.
        
        Args:
            cluster_name: Name of the cluster (currently not used, assuming single cluster)
            
        Returns:
            Dictionary with namespace information
        """
        namespaces = self.client.list_namespaces()
        
        result = {
            "count": len(namespaces),
            "namespaces": []
        }
        
        for ns in namespaces:
            ns_info = {
                "name": ns.metadata.name,
                "status": ns.status.phase,
                "creation_time": ns.metadata.creation_timestamp.isoformat() if ns.metadata.creation_timestamp else None
            }
            
            # Add labels if they exist
            if ns.metadata.labels:
                ns_info["labels"] = ns.metadata.labels
                
            result["namespaces"].append(ns_info)
            
        return result
    
    def get_resource_usage(self, namespace):
        """
        Get resource usage information for pods and deployments in a namespace.
        
        Args:
            namespace: The namespace to check
            
        Returns:
            Dictionary with resource usage information
        """
        # Get pods in the namespace
        pods = self.client.list_pods(namespace)
        
        # Get deployments in the namespace
        deployments = self.client.list_deployments(namespace)
        
        # Try to get metrics if available
        try:
            pod_metrics = self.client.get_pod_metrics(namespace)
        except Exception:
            # Metrics API might not be available
            pod_metrics = {}
        
        # Map pods to deployments
        pod_to_deployment = {}
        for pod in pods:
            if pod.metadata.owner_references:
                for owner in pod.metadata.owner_references:
                    if owner.kind == "ReplicaSet":
                        # Extract deployment name from ReplicaSet name (deployment-hash)
                        rs_name = owner.name
                        for deployment in deployments:
                            if rs_name.startswith(deployment.metadata.name):
                                pod_to_deployment[pod.metadata.name] = deployment.metadata.name
                                break
        
        # Aggregate CPU usage by pod and deployment
        pod_usage = {}
        deployment_usage = {}
        
        for pod_name, metrics in pod_metrics.items():
            pod_usage[pod_name] = metrics["cpu"]
            
            # If pod belongs to a deployment, add its usage to the deployment's total
            if pod_name in pod_to_deployment:
                deployment_name = pod_to_deployment[pod_name]
                if deployment_name in deployment_usage:
                    deployment_usage[deployment_name] += metrics["cpu"]
                else:
                    deployment_usage[deployment_name] = metrics["cpu"]
        
        # Find the pod with the highest CPU usage
        highest_pod = None
        highest_pod_cpu = 0
        for pod_name, cpu in pod_usage.items():
            if cpu > highest_pod_cpu:
                highest_pod_cpu = cpu
                highest_pod = pod_name
        
        # Find the deployment with the highest CPU usage
        highest_deployment = None
        highest_deployment_cpu = 0
        for deployment_name, cpu in deployment_usage.items():
            if cpu > highest_deployment_cpu:
                highest_deployment_cpu = cpu
                highest_deployment = deployment_name
        
        return {
            "highest_cpu_pod": {
                "name": highest_pod,
                "cpu_usage": highest_pod_cpu,
                "deployment": pod_to_deployment.get(highest_pod) if highest_pod else None
            },
            "highest_cpu_deployment": {
                "name": highest_deployment,
                "cpu_usage": highest_deployment_cpu
            }
        }
    
    def get_deployment_description(self, name, namespace):
        """
        Get a detailed description of a deployment.
        
        Args:
            name: Name of the deployment
            namespace: Namespace containing the deployment
            
        Returns:
            Dictionary with detailed deployment information
        """
        try:
            return self.client.get_deployment_description(name, namespace)
        except Exception as e:
            return {"error": f"Failed to get deployment description: {str(e)}"}
    
    def scale_deployment(self, namespace, deployment_name, scale_factor):
        """
        Scale a deployment by the specified factor.
        
        Args:
            namespace: The namespace containing the deployment
            deployment_name: Name of the deployment to scale
            scale_factor: Factor by which to scale the deployment (e.g., 2 for doubling)
            
        Returns:
            Dictionary with scaling result information
        """
        # Get the current deployment
        deployment = self.client.get_deployment(deployment_name, namespace)
        
        # Calculate new replica count
        current_replicas = deployment.spec.replicas
        new_replicas = int(current_replicas * scale_factor)
        
        # Ensure at least 1 replica
        if new_replicas < 1:
            new_replicas = 1
        
        # Scale the deployment
        updated_deployment = self.client.scale_deployment(deployment_name, namespace, new_replicas)
        
        return {
            "deployment": deployment_name,
            "namespace": namespace,
            "previous_replicas": current_replicas,
            "new_replicas": new_replicas,
            "scale_factor": scale_factor
        }
    
    def create_namespace(self, name):
        """
        Create a new namespace.
        
        Args:
            name: Name of the namespace to create
            
        Returns:
            Dictionary with namespace information or error message
        """
        try:
            return self.client.create_namespace(name)
        except Exception as e:
            return {"error": f"Failed to create namespace: {str(e)}"}
