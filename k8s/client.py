"""
Kubernetes client utility for interacting with the Kubernetes API.
"""
import os
from kubernetes import client, config
from kubernetes.client.rest import ApiException

class K8sClient:
    """
    Client for interacting with Kubernetes clusters.
    """
    def __init__(self, kubeconfig_path=None):
        """
        Initialize the Kubernetes client.
        
        Args:
            kubeconfig_path: Path to kubeconfig file. If None, uses default.
        """
        self.kubeconfig_path = kubeconfig_path or os.getenv("KUBECONFIG_PATH")
        
        try:
            if self.kubeconfig_path:
                config.load_kube_config(config_file=self.kubeconfig_path)
            else:
                # Try loading from default location
                config.load_kube_config()
        except Exception:
            # If running inside a pod, use in-cluster config
            try:
                config.load_incluster_config()
            except Exception as e:
                raise Exception(f"Failed to load Kubernetes configuration: {str(e)}")
        
        # Initialize API clients
        self.core_v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        self.custom_objects = client.CustomObjectsApi()
        
    def list_namespaces(self):
        """List all namespaces in the cluster."""
        try:
            return self.core_v1.list_namespace().items
        except ApiException as e:
            raise Exception(f"Error listing namespaces: {str(e)}")
    
    def get_namespace(self, name):
        """Get details of a specific namespace."""
        try:
            return self.core_v1.read_namespace(name)
        except ApiException as e:
            if e.status == 404:
                raise Exception(f"Namespace '{name}' not found")
            raise Exception(f"Error getting namespace: {str(e)}")
    
    def list_pods(self, namespace=None):
        """List pods in the specified namespace or across all namespaces."""
        try:
            if namespace:
                return self.core_v1.list_namespaced_pod(namespace).items
            else:
                return self.core_v1.list_pod_for_all_namespaces().items
        except ApiException as e:
            raise Exception(f"Error listing pods: {str(e)}")
    
    def list_deployments(self, namespace=None):
        """List deployments in the specified namespace or across all namespaces."""
        try:
            if namespace:
                return self.apps_v1.list_namespaced_deployment(namespace).items
            else:
                return self.apps_v1.list_deployment_for_all_namespaces().items
        except ApiException as e:
            raise Exception(f"Error listing deployments: {str(e)}")
    
    def get_deployment(self, name, namespace):
        """Get a specific deployment."""
        try:
            return self.apps_v1.read_namespaced_deployment(name, namespace)
        except ApiException as e:
            if e.status == 404:
                raise Exception(f"Deployment '{name}' not found in namespace '{namespace}'")
            raise Exception(f"Error getting deployment: {str(e)}")
    
    def scale_deployment(self, name, namespace, replicas):
        """Scale a deployment to the specified number of replicas."""
        try:
            # Get the current deployment
            deployment = self.apps_v1.read_namespaced_deployment(name, namespace)
            
            # Update the replica count
            deployment.spec.replicas = replicas
            
            # Apply the update
            return self.apps_v1.patch_namespaced_deployment(
                name=name,
                namespace=namespace,
                body=deployment
            )
        except ApiException as e:
            if e.status == 404:
                raise Exception(f"Deployment '{name}' not found in namespace '{namespace}'")
            raise Exception(f"Error scaling deployment: {str(e)}")
    
    def get_pod_metrics(self, namespace=None):
        """
        Get pod metrics (CPU/Memory usage) from the metrics API.
        
        Returns a dictionary mapping pod names to their metrics.
        """
        try:
            if namespace:
                metrics = self.custom_objects.list_namespaced_custom_object(
                    group="metrics.k8s.io",
                    version="v1beta1",
                    namespace=namespace,
                    plural="pods"
                )
            else:
                metrics = self.custom_objects.list_cluster_custom_object(
                    group="metrics.k8s.io",
                    version="v1beta1",
                    plural="pods"
                )
            
            # Process metrics into a more usable format
            result = {}
            for item in metrics.get("items", []):
                pod_name = item.get("metadata", {}).get("name")
                if pod_name:
                    containers = item.get("containers", [])
                    cpu_usage = sum(int(c.get("usage", {}).get("cpu", "0").rstrip("n")) for c in containers)
                    memory_usage = sum(int(c.get("usage", {}).get("memory", "0").rstrip("Ki")) for c in containers)
                    
                    result[pod_name] = {
                        "cpu": cpu_usage,
                        "memory": memory_usage
                    }
            
            return result
        except ApiException as e:
            # The metrics API might not be available
            raise Exception(f"Error getting pod metrics: {str(e)}")
