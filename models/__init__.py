"""
Data models for the Kubernetes AI Agent.
"""
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class NamespaceInfo(BaseModel):
    """Model for namespace information."""
    name: str
    status: str
    creation_time: Optional[str] = None
    labels: Optional[Dict[str, str]] = None

class NamespacesResponse(BaseModel):
    """Model for response containing namespace information."""
    count: int
    namespaces: List[NamespaceInfo]

class PodInfo(BaseModel):
    """Model for pod information."""
    name: Optional[str] = None
    cpu_usage: Optional[int] = None
    deployment: Optional[str] = None

class DeploymentInfo(BaseModel):
    """Model for deployment information."""
    name: Optional[str] = None
    cpu_usage: Optional[int] = None

class ResourceUsageResponse(BaseModel):
    """Model for response containing resource usage information."""
    highest_cpu_pod: PodInfo
    highest_cpu_deployment: DeploymentInfo

class ScalingResult(BaseModel):
    """Model for deployment scaling result."""
    deployment: str
    namespace: str
    previous_replicas: int
    new_replicas: int
    scale_factor: float

__all__ = [
    'NamespaceInfo', 
    'NamespacesResponse', 
    'PodInfo', 
    'DeploymentInfo', 
    'ResourceUsageResponse', 
    'ScalingResult'
]
