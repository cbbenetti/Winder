from collections import defaultdict, deque
from typing import Optional

from app.models.project import Project


def build_graph(project: Project) -> dict[str, list[tuple[str, str]]]:
    """
    Returns adjacency list: node -> [(neighbor, edge_label), ...]
    Nodes are endpoint strings (detector names, patch port IDs, DAQ channel IDs).
    Edges are cable IDs or patch port IDs connecting them.
    """
    graph: dict[str, list[tuple[str, str]]] = defaultdict(list)

    for cable in project.cables:
        src = cable.from_endpoint.strip()
        dst = cable.to_endpoint.strip()
        if src and dst:
            graph[src].append((dst, cable.id))
            graph[dst].append((src, cable.id))

    for panel in project.patch_panels:
        for port in panel.ports:
            if port.front_cable_id and port.rear_cable_id:
                front_cable = project.cable_by_id(port.front_cable_id)
                rear_cable = project.cable_by_id(port.rear_cable_id)
                if front_cable and rear_cable:
                    graph[port.front_cable_id].append((port.rear_cable_id, port.id))
                    graph[port.rear_cable_id].append((port.front_cable_id, port.id))

    return dict(graph)


def trace_path(project: Project, start: str) -> list[list[tuple[str, str]]]:
    """
    BFS from start node; returns all paths to DAQ channel endpoints.
    Each path is a list of (node, edge_label) tuples, starting from start.
    """
    graph = build_graph(project)
    daq_channel_ids = {
        ch.id
        for crate in project.crates
        for slot in crate.slots
        for ch in slot.channels
    }

    results = []
    queue: deque[list[tuple[str, str]]] = deque()
    queue.append([(start, "")])
    visited_paths: set[tuple] = set()

    while queue:
        path = queue.popleft()
        current_node = path[-1][0]
        visited_nodes = {n for n, _ in path}

        if current_node in daq_channel_ids and len(path) > 1:
            results.append(path)
            continue

        for neighbor, edge in graph.get(current_node, []):
            if neighbor not in visited_nodes:
                new_path = path + [(neighbor, edge)]
                path_key = tuple(n for n, _ in new_path)
                if path_key not in visited_paths:
                    visited_paths.add(path_key)
                    queue.append(new_path)

    return results if results else []


def all_connected(project: Project, start: str) -> list[tuple[str, str]]:
    """BFS returning all reachable (node, via_edge) pairs from start."""
    graph = build_graph(project)
    visited = {start}
    queue = deque([(start, "")])
    result = []
    while queue:
        node, edge = queue.popleft()
        result.append((node, edge))
        for neighbor, next_edge in graph.get(node, []):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, next_edge))
    return result
