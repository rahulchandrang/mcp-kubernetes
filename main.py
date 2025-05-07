import sys
import os
import json
from kubernetes import client, config
from dotenv import load_dotenv

# Add the current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP

load_dotenv()

# Initialize FastMCP server
mcp = FastMCP("k8s")

# --------------------------
# Serialization Functions
# --------------------------

def serialize_deployment(deployment):
    try:
        return {
            "name": deployment.metadata.name,
            "namespace": deployment.metadata.namespace,
            "replicas": deployment.spec.replicas,
            "labels": deployment.metadata.labels or {},
            "creation_timestamp": deployment.metadata.creation_timestamp.isoformat() if deployment.metadata.creation_timestamp else None
        }
    except Exception as e:
        raise ValueError(f"Error serializing deployment {deployment.metadata.name if deployment.metadata else 'Unknown'}: {e}")

def serialize_service(service):
    try:
        return {
            "name": service.metadata.name,
            "namespace": service.metadata.namespace,
            "type": service.spec.type,
            "selector": service.spec.selector or {},
            "creation_timestamp": service.metadata.creation_timestamp.isoformat() if service.metadata.creation_timestamp else None
        }
    except Exception as e:
        raise ValueError(f"Error serializing service {service.metadata.name if service.metadata else 'Unknown'}: {e}")

def serialize_replica_set(replica_set):
    try:
        return {
            "name": replica_set.metadata.name,
            "namespace": replica_set.metadata.namespace,
            "replicas": replica_set.spec.replicas,
            "labels": replica_set.metadata.labels or {},
            "creation_timestamp": replica_set.metadata.creation_timestamp.isoformat() if replica_set.metadata.creation_timestamp else None
        }
    except Exception as e:
        raise ValueError(f"Error serializing replica set {replica_set.metadata.name if replica_set.metadata else 'Unknown'}: {e}")

def serialize_pod(pod):
    try:
        return {
            "name": pod.metadata.name,
            "namespace": pod.metadata.namespace,
            "status": pod.status.phase,
            "labels": pod.metadata.labels or {},
            "creation_timestamp": pod.metadata.creation_timestamp.isoformat() if pod.metadata.creation_timestamp else None
        }
    except Exception as e:
        raise ValueError(f"Error serializing pod {pod.metadata.name if pod.metadata else 'Unknown'}: {e}")

def serialize_node(node):
    try:
        return {
            "name": node.metadata.name,
            "labels": node.metadata.labels or {},
            "creation_timestamp": node.metadata.creation_timestamp.isoformat() if node.metadata.creation_timestamp else None,
            "status": next((s.type for s in node.status.conditions if s.status == "True"), "Unknown"),
            "internal_ip": next((addr.address for addr in node.status.addresses if addr.type == "InternalIP"), None),
            "hostname": next((addr.address for addr in node.status.addresses if addr.type == "Hostname"), None)
        }
    except Exception as e:
        raise ValueError(f"Error serializing node {node.metadata.name if node.metadata else 'Unknown'}: {e}")

def serialize_secret(secret):
    return {
        "name": secret.metadata.name,
        "namespace": secret.metadata.namespace,
        "labels": secret.metadata.labels or {},
        "creation_timestamp": secret.metadata.creation_timestamp.isoformat() if secret.metadata.creation_timestamp else None,
        "type": secret.type,
        "data": {key: "REDACTED" for key in secret.data}
    }

def serialize_configmap(configmap):
    return {
        "name": configmap.metadata.name,
        "namespace": configmap.metadata.namespace,
        "labels": configmap.metadata.labels or {},
        "creation_timestamp": configmap.metadata.creation_timestamp.isoformat() if configmap.metadata.creation_timestamp else None,
        "data": configmap.data or {}
    }

# --------------------------
# MCP Tools
# --------------------------

@mcp.tool()
async def get_resources(resource_type: str, namespace: str = None):
    """
    Retrieve Kubernetes resources based on type and namespace.

    Args:
        resource_type (str): Type of resource (pods, services, deployments, replica_sets, secrets, configmaps).
        namespace (str, optional): Namespace to look in. If not provided, all namespaces are used.

    Returns:
        str: JSON string of the requested resources.
    """
    try:
        config.load_kube_config()
        v1 = client.CoreV1Api()
        apps_v1 = client.AppsV1Api()
        resource_type = resource_type.lower()
        valid_types = {"pods", "services", "deployments", "replica_sets", "secrets", "configmaps"}

        if resource_type not in valid_types:
            raise ValueError(f"Invalid resource_type '{resource_type}'. Must be one of: {', '.join(valid_types)}")

        if resource_type == "pods":
            items = v1.list_namespaced_pod(namespace).items if namespace else v1.list_pod_for_all_namespaces().items
            return json.dumps([serialize_pod(p) for p in items], indent=2)
        elif resource_type == "services":
            items = v1.list_namespaced_service(namespace).items if namespace else v1.list_service_for_all_namespaces().items
            return json.dumps([serialize_service(s) for s in items], indent=2)
        elif resource_type == "deployments":
            items = apps_v1.list_namespaced_deployment(namespace).items if namespace else apps_v1.list_deployment_for_all_namespaces().items
            return json.dumps([serialize_deployment(d) for d in items], indent=2)
        elif resource_type == "replica_sets":
            items = apps_v1.list_namespaced_replica_set(namespace).items if namespace else apps_v1.list_replica_set_for_all_namespaces().items
            return json.dumps([serialize_replica_set(rs) for rs in items], indent=2)
        elif resource_type == "secrets":
            items = v1.list_namespaced_secret(namespace).items if namespace else v1.list_secret_for_all_namespaces().items
            return json.dumps([serialize_secret(s) for s in items], indent=2)
        elif resource_type == "configmaps":
            items = v1.list_namespaced_config_map(namespace).items if namespace else v1.list_config_map_for_all_namespaces().items
            return json.dumps([serialize_configmap(cm) for cm in items], indent=2)

    except Exception as e:
        raise ValueError(f"Error retrieving {resource_type}: {e}")

@mcp.tool()
async def get_kube_contexts():
    """
    List all available Kubernetes contexts and identify the current one.

    Args:
        None

    Returns:
        str: JSON string containing current and available contexts.
    """
    try:
        contexts, current = config.list_kube_config_contexts()
        return json.dumps({
            "current_context": current['name'],
            "available_contexts": [ctx['name'] for ctx in contexts]
        }, indent=2)
    except Exception as e:
        raise ValueError(f"Error retrieving contexts: {e}")

@mcp.tool()
async def set_kube_context(context_name: str):
    """
    Set the Kubernetes context to the specified one.

    Args:
        context_name (str): Name of the kube context to switch to.

    Returns:
        str: Success message after switching context.
    """
    try:
        config.load_kube_config(context=context_name)
        return f"Switched to context: {context_name}"
    except Exception as e:
        raise ValueError(f"Error switching context: {e}")

@mcp.tool()
async def list_service_accounts(namespace: str = None):
    """
    List service accounts in a specific namespace or across all namespaces.

    Args:
        namespace (str, optional): Namespace to filter by. Lists all if not provided.

    Returns:
        str: JSON string containing service accounts with their secrets.
    """
    try:
        config.load_kube_config()
        v1 = client.CoreV1Api()
        accounts = v1.list_namespaced_service_account(namespace=namespace).items if namespace else v1.list_service_account_for_all_namespaces().items
        sa_list = [{
            "name": sa.metadata.name,
            "namespace": sa.metadata.namespace,
            "secrets": [s.name for s in sa.secrets or []]
        } for sa in accounts]
        return json.dumps(sa_list, indent=2)
    except Exception as e:
        raise ValueError(f"Error listing service accounts: {e}")

@mcp.tool()
async def list_nodes():
    """
    List all nodes in the Kubernetes cluster.

    Args:
        None

    Returns:
        str: JSON string containing details of each node.
    """
    try:
        config.load_kube_config()
        v1 = client.CoreV1Api()
        nodes = v1.list_node().items
        return json.dumps([serialize_node(node) for node in nodes], indent=2)
    except Exception as e:
        raise ValueError(f"Error listing nodes: {e}")

@mcp.tool()
async def list_namespaces():
    """
    List all namespaces in the Kubernetes cluster.

    Args:
        None

    Returns:
        str: JSON string containing namespace names, labels, and creation timestamps.
    """
    try:
        config.load_kube_config()
        v1 = client.CoreV1Api()
        namespaces = v1.list_namespace().items
        detailed_namespaces = [{
            "name": ns.metadata.name,
            "labels": ns.metadata.labels or {},
            "creation_timestamp": ns.metadata.creation_timestamp.isoformat() if ns.metadata.creation_timestamp else None
        } for ns in namespaces]
        return json.dumps(detailed_namespaces, indent=2)
    except Exception as e:
        raise ValueError(f"Error listing namespaces: {e}")

@mcp.tool()
async def create_namespace(namespace_name: str, labels: dict = None):
    """
    Create a new Kubernetes namespace with optional labels.

    Args:
        namespace_name (str): Name of the namespace to create.
        labels (dict, optional): Dictionary of labels to attach to the namespace.

    Returns:
        str: Message confirming creation or that the namespace already exists.
    """
    try:
        config.load_kube_config()
        v1 = client.CoreV1Api()
        metadata = client.V1ObjectMeta(name=namespace_name, labels=labels or {})
        namespace = client.V1Namespace(metadata=metadata)
        v1.create_namespace(namespace)
        return f"Namespace '{namespace_name}' created successfully."
    except client.exceptions.ApiException as e:
        if e.status == 409:
            return f"Namespace '{namespace_name}' already exists."
        else:
            raise ValueError(f"Error creating namespace: {e}")
    except Exception as e:
        raise ValueError(f"Unexpected error: {e}")

@mcp.tool()
async def delete_namespace(namespace_name: str):
    """
    Delete a Kubernetes namespace.

    Args:
        namespace_name (str): Name of the namespace to delete.

    Returns:
        str: Message confirming initiation of deletion or if not found.
    """
    try:
        config.load_kube_config()
        v1 = client.CoreV1Api()
        v1.delete_namespace(name=namespace_name)
        return f"Namespace '{namespace_name}' deletion initiated."
    except client.exceptions.ApiException as e:
        if e.status == 404:
            return f"Namespace '{namespace_name}' not found."
        else:
            raise ValueError(f"Error deleting namespace: {e}")
    except Exception as e:
        raise ValueError(f"Unexpected error: {e}")

# --------------------------
# Run MCP Server
# --------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
