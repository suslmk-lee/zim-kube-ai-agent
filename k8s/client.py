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
            # Get the deployment
            deployment = self.apps_v1.read_namespaced_deployment(name, namespace)
            
            # Get the replica sets associated with this deployment
            selector = ""
            for k, v in deployment.spec.selector.match_labels.items():
                selector += f"{k}={v},"
            selector = selector.rstrip(",")
            
            replica_sets = self.apps_v1.list_namespaced_replica_set(
                namespace, 
                label_selector=selector
            )
            
            # Get the pods associated with this deployment
            pods = self.core_v1.list_namespaced_pod(
                namespace,
                label_selector=selector
            )
            
            # Get events related to this deployment
            field_selector = f"involvedObject.name={name},involvedObject.namespace={namespace}"
            events = self.core_v1.list_namespaced_event(
                namespace,
                field_selector=field_selector
            )
            
            # Format the deployment description
            description = {
                "name": deployment.metadata.name,
                "namespace": deployment.metadata.namespace,
                "creation_timestamp": deployment.metadata.creation_timestamp.isoformat() if deployment.metadata.creation_timestamp else None,
                "labels": deployment.metadata.labels,
                "annotations": deployment.metadata.annotations,
                "selector": deployment.spec.selector.match_labels,
                "replicas": {
                    "desired": deployment.spec.replicas,
                    "current": deployment.status.replicas,
                    "updated": deployment.status.updated_replicas,
                    "available": deployment.status.available_replicas,
                    "unavailable": deployment.status.unavailable_replicas
                },
                "strategy": {
                    "type": deployment.spec.strategy.type,
                    "rolling_update": {
                        "max_surge": deployment.spec.strategy.rolling_update.max_surge if deployment.spec.strategy.rolling_update else None,
                        "max_unavailable": deployment.spec.strategy.rolling_update.max_unavailable if deployment.spec.strategy.rolling_update else None
                    } if deployment.spec.strategy.rolling_update else None
                },
                "containers": [],
                "conditions": [
                    {
                        "type": condition.type,
                        "status": condition.status,
                        "reason": condition.reason,
                        "message": condition.message,
                        "last_update": condition.last_update_time.isoformat() if condition.last_update_time else None
                    }
                    for condition in deployment.status.conditions or []
                ],
                "replica_sets": [
                    {
                        "name": rs.metadata.name,
                        "replicas": rs.status.replicas,
                        "ready_replicas": rs.status.ready_replicas
                    }
                    for rs in replica_sets.items
                ],
                "pods": [
                    {
                        "name": pod.metadata.name,
                        "status": pod.status.phase,
                        "ready": all(container.ready for container in pod.status.container_statuses) if pod.status.container_statuses else False,
                        "restart_count": sum(container.restart_count for container in pod.status.container_statuses) if pod.status.container_statuses else 0,
                        "node": pod.spec.node_name,
                        "ip": pod.status.pod_ip
                    }
                    for pod in pods.items
                ],
                "events": [
                    {
                        "type": event.type,
                        "reason": event.reason,
                        "message": event.message,
                        "count": event.count,
                        "first_timestamp": event.first_timestamp.isoformat() if event.first_timestamp else None,
                        "last_timestamp": event.last_timestamp.isoformat() if event.last_timestamp else None
                    }
                    for event in events.items
                ]
            }
            
            # Add container information
            for container in deployment.spec.template.spec.containers:
                container_info = {
                    "name": container.name,
                    "image": container.image,
                    "ports": [
                        {
                            "name": port.name,
                            "container_port": port.container_port,
                            "protocol": port.protocol
                        }
                        for port in container.ports or []
                    ],
                    "resources": {
                        "limits": container.resources.limits if container.resources and container.resources.limits else {},
                        "requests": container.resources.requests if container.resources and container.resources.requests else {}
                    },
                    "liveness_probe": bool(container.liveness_probe),
                    "readiness_probe": bool(container.readiness_probe),
                    "env": [
                        {
                            "name": env.name,
                            "value": env.value if env.value else "(from secret or configmap)"
                        }
                        for env in container.env or []
                    ],
                    "volume_mounts": [
                        {
                            "name": volume.name,
                            "mount_path": volume.mount_path,
                            "read_only": volume.read_only
                        }
                        for volume in container.volume_mounts or []
                    ] if container.volume_mounts else []
                }
                description["containers"].append(container_info)
            
            return description
            
        except Exception as e:
            return {"error": f"Failed to get deployment description: {str(e)}"}
    
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
    
    def create_namespace(self, name):
        """
        Create a new namespace.
        
        Args:
            name: Name of the namespace to create
            
        Returns:
            Dictionary with namespace information or error message
        """
        try:
            # Create namespace object
            from kubernetes.client.models.v1_namespace import V1Namespace
            from kubernetes.client.models.v1_object_meta import V1ObjectMeta
            
            namespace = V1Namespace(
                metadata=V1ObjectMeta(
                    name=name
                )
            )
            
            # Create the namespace
            result = self.core_v1.create_namespace(namespace)
            
            return {
                "name": result.metadata.name,
                "status": result.status.phase,
                "creation_time": result.metadata.creation_timestamp.isoformat() if result.metadata.creation_timestamp else None
            }
            
        except Exception as e:
            if "AlreadyExists" in str(e):
                return {"error": f"Namespace '{name}' already exists"}
            return {"error": f"Failed to create namespace: {str(e)}"}
